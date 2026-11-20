"""Verify optional startup pack selection and native properties semantics."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
import select_resource_pack as selection
from verify_runtime import VerificationError

PACK_DEFAULT = {"url": "https://assets.example.com/default.zip", "sha1": "a" * 40}
PACK_TRIALS = {"url": "https://assets.example.com/trials.zip?edition=2&size=full", "sha1": "B" * 40}


class ResourcePackSelectionTests(unittest.TestCase):
    def setUp(self):
        scratch = REPOSITORY / ".tmp"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="pack-selection-", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.properties = self.root / "server/server.properties"
        self.properties.parent.mkdir()
        self.properties.write_bytes(
            b"level-name=world\r\nresource-pack=https://legacy.example.com/old.zip\r\n"
            b"resource-pack-sha1=legacy\r\nresource-pack-id=old-id\r\n"
            b"resource-pack-hash=deprecated-hash\r\n"
            b"require-resource-pack=true\r\nresource-pack-prompt=Custom prompt\r\n"
            b"management-server-secret=keep-me\r\n")
        self.policy = self.root / "settings/minecraft-server.json"
        self.policy.parent.mkdir()
        self.output = self.root / ".tmp/startup/server.properties"
        self.before = self.properties.read_bytes()

    def write_policy(self, default=None, worlds=None):
        policy = {"schema_version": 1, "values": {},
                  "backup": {"targets": ["unavailable-backup-mount/snapshots"]},
                  "resource_packs": {"default": default, "worlds": worlds or {}}}
        self.policy.write_text(json.dumps(policy), encoding="utf-8")

    def assert_pack(self, world, url, sha1, source):
        selected, actual_source, _, output = selection.select(self.root, world)
        self.assertEqual(world, selected)
        self.assertEqual(source, actual_source)
        self.assertEqual(self.output, output)
        actual = selection.read_properties(output)
        self.assertEqual(url, actual["resource-pack"])
        self.assertEqual(sha1, actual["resource-pack-sha1"])
        self.assertEqual("", actual["resource-pack-id"])
        self.assertEqual("", actual["resource-pack-hash"])
        self.assertEqual("true", actual["require-resource-pack"])
        self.assertEqual("Custom prompt", actual["resource-pack-prompt"])
        self.assertEqual("keep-me", actual["management-server-secret"])
        self.assertEqual(self.before, self.properties.read_bytes())

    def test_default_overrides_null_and_repeated_transitions(self):
        self.write_policy(PACK_DEFAULT, {"trials": PACK_TRIALS, "world": None})
        self.assert_pack("Adventure_A", PACK_DEFAULT["url"], "a" * 40, "default")
        self.assert_pack("trials", PACK_TRIALS["url"], "b" * 40, "worlds.trials")
        self.assert_pack("world", "", "", "worlds.world")
        self.output.write_text("level-name=stale\nresource-pack=https://stale.example.com/a.zip\n")
        self.assert_pack("Adventure_A", PACK_DEFAULT["url"], "a" * 40, "default")
        self.write_policy(None, {"trials": PACK_TRIALS})
        self.assert_pack("world", "", "", "default")

    def test_absent_policy_does_not_reuse_generated_properties(self):
        self.write_policy(PACK_TRIALS)
        selection.select(self.root)
        previous = self.output.read_bytes()
        self.policy.unlink()
        world, source, properties, output = selection.select(self.root, check=True)
        self.assertEqual("world", world)
        self.assertIn("native", source)
        self.assertEqual("https://legacy.example.com/old.zip", properties["resource-pack"])
        self.assertIsNone(output)
        self.assertEqual(previous, self.output.read_bytes())
        self.assertEqual(self.before, self.properties.read_bytes())

    def test_check_is_read_only_and_reports_selection(self):
        self.write_policy(None, {"trials": PACK_TRIALS})
        stdout = io.StringIO()
        with patch.object(selection, "REPOSITORY", self.root), contextlib.redirect_stdout(stdout):
            result = selection.main(["--world=trials", "--check"])
        self.assertEqual(0, result)
        for expected in ("trials", "worlds.trials", PACK_TRIALS["url"], "b" * 40, "not written"):
            self.assertIn(expected, stdout.getvalue())
        self.assertFalse((self.root / ".tmp").exists())
        self.assertEqual(self.before, self.properties.read_bytes())

    def test_absent_section_returns_native_status_without_reusing_projection(self):
        self.write_policy(PACK_DEFAULT)
        selection.select(self.root)
        previous = self.output.read_bytes()
        self.policy.write_text(json.dumps({"schema_version": 1, "values": {
            "MANAGEMENT_SERVER_SECRET": "env:UNSET_CREDENTIAL",
            "PACK_URL": "env:UNSET_LEGACY_PACK",
        }}), encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True), patch.object(selection, "REPOSITORY", self.root):
            for arguments, expected in (([], 3), (["--check"], 0)):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(expected, selection.main(arguments))
        self.assertIsNone(selection.select(self.root)[3])
        self.assertEqual(previous, self.output.read_bytes())

    def test_missing_host_settings_has_native_exit_status(self):
        with patch.object(selection, "REPOSITORY", self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(3, selection.main([]))
            self.assertEqual(0, selection.main(["--check"]))
        self.assertFalse(self.output.exists())

    def test_legacy_startup_does_not_read_native_properties(self):
        self.policy.write_text('{"schema_version":1,"values":{}}', encoding="utf-8")
        self.properties.write_bytes(b"level-name=Native save name\n")
        with patch.object(selection, "REPOSITORY", self.root), \
                patch.object(selection, "read_properties", side_effect=AssertionError("must not read")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(3, selection.main([]))
        self.properties.unlink()
        with patch.object(selection, "REPOSITORY", self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(3, selection.main([]))
        self.assertFalse(self.output.exists())

    def test_legacy_check_accepts_implicit_native_names_and_missing_properties(self):
        self.policy.write_text('{"schema_version":1,"values":{}}', encoding="utf-8")
        self.properties.write_bytes(b"level-name=Native save name\n")
        self.assertEqual("Native save name", selection.select(self.root, check=True)[0])
        self.properties.unlink()
        self.assertEqual("world", selection.select(self.root, check=True)[0])
        self.assertFalse(self.output.exists())

    def test_startup_never_resolves_or_reports_unrelated_values(self):
        self.policy.write_text(json.dumps({"schema_version": 1, "values": {
            "MANAGEMENT_SERVER_SECRET": "env:UNSET_CREDENTIAL",
            "PACK_URL": "env:UNSET_LEGACY_PACK",
            "EXTRA_VALUE": "sensitive-text-not-for-output",
        }, "resource_packs": {"default": PACK_DEFAULT, "worlds": {}}}), encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch.object(selection, "REPOSITORY", self.root), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(0, selection.main([]))
        self.assertEqual("", stderr.getvalue())
        for value in ("UNSET_CREDENTIAL", "UNSET_LEGACY_PACK", "sensitive-text-not-for-output"):
            self.assertNotIn(value, stdout.getvalue())
        self.assertEqual(PACK_DEFAULT["url"], selection.read_properties(self.output)["resource-pack"])

    def test_standalone_policy_requires_migration_even_without_host_settings(self):
        legacy = self.policy.with_name("resource-packs.json")
        legacy.write_text(json.dumps({"schema_version": 1, "default": None, "worlds": {}}))
        for unified_present in (False, True):
            with self.subTest(unified_present=unified_present):
                if unified_present:
                    self.write_policy(PACK_DEFAULT)
                with self.assertRaisesRegex(VerificationError, "move its default and worlds.*resource_packs"):
                    selection.select(self.root)
                self.assertFalse(self.output.exists())
                self.assertTrue(legacy.is_file())

    def test_native_default_name_and_explicit_override(self):
        self.write_policy(None, {"trials": PACK_TRIALS})
        self.properties.write_bytes(b"level-name=old\nlevel\\u002dname : tri\\\r\n\tals\n")
        world, source, _, _ = selection.select(self.root, check=True)
        self.assertEqual(("trials", "worlds.trials"), (world, source))
        world, source, _, _ = selection.select(self.root, "world", check=True)
        self.assertEqual(("world", "default"), (world, source))
        self.properties.write_bytes(b"motd=empty\n")
        self.assertEqual("world", selection.select(self.root, check=True)[0])

    def test_properties_decoding_and_projection_keep_unrelated_values(self):
        self.write_policy()
        self.properties.write_bytes((
            "# ignored\\\r\n!ignored\r\n"
            "level-name=world\n"
            "motd=old\nmotd : 雨\\u0020world\\nnext\\\\path\n"
            "space\\ key\\:part\\=end\t:\f\\ first\\tlast \n"
            "escaped=slash\\\\\ncontinued = alpha\\\n \t#beta\n"
            "unicode=\\ud83c\\udf0d\nunknown=\\z\n"
            "no-value\n=empty-key\ntrailing=tail\\"
        ).encode("utf-8"))
        expected = {
            "level-name": "world", "motd": "雨 world\nnext\\path",
            "space key:part=end": " first\tlast ", "escaped": "slash\\",
            "continued": "alpha#beta", "unicode": "🌍", "unknown": "z",
            "no-value": "", "": "empty-key", "trailing": "tail",
        }
        self.assertEqual(expected, selection.read_properties(self.properties))
        before = self.properties.read_bytes()
        selection.select(self.root)
        projected = selection.read_properties(self.output)
        for key, value in expected.items():
            self.assertEqual(value, projected[key], key)
        self.assertEqual(before, self.properties.read_bytes())

    def test_empty_continuations_preserve_comments_and_empty_keys(self):
        cases = {
            "\\\n# ignored\nx=value\n": {"x": "value"},
            "\\\r\n! ignored\\\r\nx=value\n": {"x": "value"},
            "=kept\n\\\n\nx=value\n": {"": "kept", "x": "value"},
            "value=\\\n#content\n": {"value": "#content"},
            "\\\n": {"": ""},
            "\\\n\n": {},
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.properties.write_bytes(text.encode("utf-8"))
                self.assertEqual(expected, selection.read_properties(self.properties))

    def test_literal_and_escaped_unicode_keys_share_last_definition(self):
        self.properties.write_bytes("🌍=first\n\\ud83c\\udf0d=second\n".encode("utf-8"))
        self.assertEqual({"🌍": "second"}, selection.read_properties(self.properties))
        self.properties.write_bytes("\\ud83c\\udf0d=first\n🌍=second\n".encode("utf-8"))
        self.assertEqual({"🌍": "second"}, selection.read_properties(self.properties))

    def test_invalid_utf8_falls_back_to_latin1_like_paper(self):
        self.properties.write_bytes(b"motd=caf\xe9\nlevel-name=world\n")
        self.assertEqual("café", selection.read_properties(self.properties)["motd"])

    def test_invalid_policy_refuses_before_output(self):
        valid = {"default": None, "worlds": {}}
        cases = [None, [], {}, {**valid, "unexpected": True},
                 {**valid, "schema_version": 1},
                 {**valid, "worlds": []}, {**valid, "worlds": {"../escape": None}},
                 {**valid, "worlds": {"trials ": None}},
                 {**valid, "default": "disabled"},
                 {**valid, "default": {**PACK_DEFAULT, "extra": True}},
                 {**valid, "default": {"url": PACK_DEFAULT["url"]}}]
        for url in ("", "http://assets.example.com/a.zip", "env:PACK_URL",
                    "https://user:password@example.com/a.zip", "https://example.com:0/a.zip",
                    "https://${HOST}/a.zip", "https://<host>/a.zip", "https://example.com/\nprop=x"):
            cases.append({**valid, "default": {**PACK_DEFAULT, "url": url}})
        for digest in ("", "<SHA-1 of the served ZIP>", "g" * 40, "f" * 39, 123):
            cases.append({**valid, "worlds": {"inactive": {**PACK_DEFAULT, "sha1": digest}}})
        for policy in cases:
            with self.subTest(policy=policy):
                self.policy.write_text(json.dumps({"schema_version": 1, "values": {},
                                                   "resource_packs": policy}), encoding="utf-8")
                with self.assertRaises(VerificationError):
                    selection.select(self.root)
                self.assertFalse(self.output.exists())
                self.assertEqual(self.before, self.properties.read_bytes())

    def test_duplicates_malformed_json_and_unicode_fail_cleanly(self):
        for payload in (b'{"schema_version":1,"schema_version":1,"values":{}}',
                        b'{"schema_version":1,"values":{},"resource_packs":{"default":null,"worlds":{"world":null,"world":null}}}',
                        b"not json", b"\xff"):
            self.policy.write_bytes(payload)
            stderr = io.StringIO()
            with patch.object(selection, "REPOSITORY", self.root), contextlib.redirect_stderr(stderr):
                self.assertEqual(2, selection.main([]))
            self.assertIn("ERROR:", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertFalse(self.output.exists())

    def test_startup_validates_entire_host_structure_without_echoing_values(self):
        valid = {"schema_version": 1, "values": {},
                 "resource_packs": {"default": None, "worlds": {}}}
        for document in ([], {**valid, "schema_version": True}, {**valid, "schema_version": 1.0},
                         {**valid, "values": None}, {**valid, "extra": "unknown"},
                         {**valid, "values": {"SECRET": "env:sensitive-bad-reference"}},
                         {**valid, "values": {"SECRET": "sensitive-${VALUE}"}}):
            with self.subTest(document=document):
                self.policy.write_text(json.dumps(document), encoding="utf-8")
                stderr = io.StringIO()
                with patch.object(selection, "REPOSITORY", self.root), contextlib.redirect_stderr(stderr):
                    self.assertEqual(2, selection.main([]))
                self.assertNotIn("sensitive-", stderr.getvalue())
                self.assertFalse(self.output.exists())

    def test_invalid_native_world_and_unicode_escape_fail(self):
        self.write_policy()
        for payload in (b"level-name=../escape\n", b"level-name=\n", b"motd=\\u12xy\n"):
            self.properties.write_bytes(payload)
            with self.assertRaises(VerificationError):
                selection.select(self.root)
        self.properties.write_bytes(self.before)
        with self.assertRaises(VerificationError):
            selection.select(self.root, "../escape")
        self.assertFalse(self.output.exists())

    def test_loopback_http_and_url_escapes_round_trip(self):
        for hostname in ("127.0.0.1", "localhost", "[::1]"):
            url = f"http://{hostname}:8000/packs/test.zip?value=a=b&name=pack%20a#zip"
            self.write_policy({"url": url, "sha1": "f" * 40})
            selection.select(self.root)
            self.assertEqual(url, selection.read_properties(self.output)["resource-pack"])

    def test_failed_atomic_replace_preserves_previous_output(self):
        self.write_policy(PACK_DEFAULT)
        selection.select(self.root)
        previous = self.output.read_bytes()
        self.write_policy(PACK_TRIALS)
        with patch.object(selection.os, "replace", side_effect=OSError("replace refused")):
            with self.assertRaisesRegex(OSError, "replace refused"):
                selection.select(self.root)
        self.assertEqual(previous, self.output.read_bytes())
        self.assertEqual([self.output], list(self.output.parent.iterdir()))
        self.assertEqual(self.before, self.properties.read_bytes())

    def test_links_at_input_and_output_boundaries_are_refused(self):
        self.write_policy(PACK_DEFAULT)
        outside = self.root / "outside"
        outside.mkdir()
        marker = outside / "server.properties"
        marker.write_bytes(b"outside")
        for relative, target, is_directory in (
            (".tmp", outside, True),
            (".tmp/startup", outside, True),
            (".tmp/startup/server.properties", marker, False),
            ("settings/minecraft-server.json", outside / "missing.json", False),
            ("settings/resource-packs.json", outside / "missing.json", False),
            ("server/server.properties", marker, False),
        ):
            with self.subTest(relative=relative):
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                previous = path.read_bytes() if path.is_file() else None
                if previous is not None:
                    path.unlink()
                try:
                    path.symlink_to(target, target_is_directory=is_directory)
                except (OSError, NotImplementedError) as error:
                    if previous is not None:
                        path.write_bytes(previous)
                    self.skipTest(f"symlinks unavailable: {error}")
                try:
                    with self.assertRaisesRegex(VerificationError, "links and junctions"):
                        selection.select(self.root)
                    self.assertEqual(b"outside", marker.read_bytes())
                finally:
                    path.unlink()
                    if previous is not None:
                        path.write_bytes(previous)


if __name__ == "__main__":
    unittest.main()
