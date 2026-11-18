"""Applying the tracked configuration bundle, using isolated fixture directories only."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("apply_config", SCRIPTS / "apply_config.py")
apply_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apply_config)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


class ApplyConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.config = self.directory / "config"
        self.config.mkdir()
        self.server = self.directory / "server"
        self.server.mkdir()
        self.lock_path = self.directory / "config.lock.json"
        self.settings_path = self.directory / "settings.json"
        self.files = []
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for name in (
            "PACK_URL",
            "SECRET",
            "PORT",
            "GEYSER_ADVERTISE_ADDRESS",
            "BSTATS_SERVER_UUID",
            "MANAGEMENT_SERVER_SECRET",
        ):
            os.environ.pop(name, None)

    def add(self, relative, payload, placeholders=(), classification="source"):
        path = self.config / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        self.files.append(
            {
                "path": relative,
                "class": classification,
                "sha256": digest(payload),
                "placeholders": list(placeholders),
            }
        )
        return path

    def save(self):
        self.lock_path.write_text(
            json.dumps({"schema_version": 1, "files": self.files}), encoding="utf-8"
        )

    def save_settings(self, values, schema_version=1):
        self.settings_path.write_text(
            json.dumps({"schema_version": schema_version, "values": values}),
            encoding="utf-8",
        )

    def run_tool(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = apply_config.main(
                [
                    "--config-dir",
                    str(self.config),
                    "--lock",
                    str(self.lock_path),
                    "--server-dir",
                    str(self.server),
                    *args,
                ]
            )
        return code, output.getvalue(), errors.getvalue()

    def assert_refused(self, contains=None, *args):
        code, output, errors = self.run_tool(*args)
        self.assertEqual(2, code, (output, errors))
        self.assertIn("ERROR:", errors)
        self.assertNotIn("Traceback", errors)
        if contains is not None:
            self.assertIn(contains, errors)
        return errors

    def test_render_writes_the_rendered_bytes(self):
        self.add("server.properties", b"motd=Hi\nurl=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        code, output, errors = self.run_tool("--set", "PACK_URL=http://host/packs/a.zip")
        self.assertEqual(0, code, errors)
        self.assertIn("CREATE", output)
        self.assertEqual(
            b"motd=Hi\nurl=http://host/packs/a.zip\n",
            (self.server / "server.properties").read_bytes(),
        )

    def test_second_run_is_unchanged(self):
        self.add("server.properties", b"port=${PORT}\n", [{"name": "PORT"}])
        self.save()
        self.assertEqual(0, self.run_tool("--set", "PORT=25565")[0])
        code, output, errors = self.run_tool("--set", "PORT=25565")
        self.assertEqual(0, code, errors)
        self.assertIn("UNCHANGED", output)
        self.assertNotIn("CREATE", output)

    def test_update_replaces_an_existing_difference(self):
        self.add("server.properties", b"port=${PORT}\n", [{"name": "PORT"}])
        self.save()
        (self.server / "server.properties").write_bytes(b"port=1\n")
        code, output, errors = self.run_tool("--set", "PORT=25565")
        self.assertEqual(0, code, errors)
        self.assertIn("UPDATE", output)
        self.assertEqual(b"port=25565\n", (self.server / "server.properties").read_bytes())

    def test_value_comes_from_the_environment(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        os.environ["PACK_URL"] = "http://env/packs/a.zip"
        code, _, errors = self.run_tool()
        self.assertEqual(0, code, errors)
        self.assertIn(b"http://env/packs/a.zip", (self.server / "server.properties").read_bytes())

    def test_set_wins_over_the_environment(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        os.environ["PACK_URL"] = "http://env/a.zip"
        self.assertEqual(0, self.run_tool("--set", "PACK_URL=http://flag/a.zip")[0])
        self.assertIn(b"http://flag/a.zip", (self.server / "server.properties").read_bytes())

    def test_missing_value_is_refused_before_any_write(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.assert_refused("no value for ${PACK_URL}")
        self.assertFalse((self.server / "server.properties").exists())

    def test_malformed_set_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.assert_refused("NAME=VALUE", "--set", "PACK_URL")

    def test_duplicate_set_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.assert_refused("twice", "--set", "PACK_URL=a", "--set", "PACK_URL=b")

    def test_unused_set_value_is_not_inspected(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        code, _, errors = self.run_tool("--set", "UNUSED=${X}")
        self.assertEqual(0, code, errors)

    def test_settings_supply_the_values(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.save_settings({"PACK_URL": "http://host/a.zip"})
        code, output, errors = self.run_tool("--settings", str(self.settings_path))
        self.assertEqual(0, code, errors)
        self.assertIn("settings   ", output)
        self.assertIn(
            b"url=http://host/a.zip",
            (self.server / "server.properties").read_bytes(),
        )

    def test_set_wins_over_settings(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.save_settings({"PACK_URL": "http://host/a.zip"})
        code, _, errors = self.run_tool(
            "--settings",
            str(self.settings_path),
            "--set",
            "PACK_URL=http://flag/b.zip",
        )
        self.assertEqual(0, code, errors)
        self.assertIn(
            b"url=http://flag/b.zip",
            (self.server / "server.properties").read_bytes(),
        )

    def test_settings_win_over_the_environment(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.save_settings({"PACK_URL": "http://host/a.zip"})
        os.environ["PACK_URL"] = "http://env/b.zip"
        code, _, errors = self.run_tool("--settings", str(self.settings_path))
        self.assertEqual(0, code, errors)
        self.assertIn(
            b"url=http://host/a.zip",
            (self.server / "server.properties").read_bytes(),
        )

    def test_settings_env_reference_is_resolved(self):
        self.add("server.properties", b"seed=${SECRET}\n", [{"name": "SECRET"}])
        self.save()
        self.save_settings({"SECRET": "env:SOURCE"})
        with patch.dict(os.environ, {"SOURCE": "s3cret"}):
            code, _, errors = self.run_tool("--settings", str(self.settings_path))
        self.assertEqual(0, code, errors)
        self.assertIn(b"seed=s3cret", (self.server / "server.properties").read_bytes())

    def test_settings_env_reference_that_is_unset_is_refused(self):
        self.add("server.properties", b"seed=${SECRET}\n", [{"name": "SECRET"}])
        self.save()
        self.save_settings({"SECRET": "env:ABSENT_VARIABLE"})
        self.assert_refused("ABSENT_VARIABLE", "--settings", str(self.settings_path))
        self.assertFalse((self.server / "server.properties").exists())

    def test_settings_name_no_template_declares_is_refused(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        self.save_settings({"TYPO": "x"})
        self.assert_refused("no template declares", "--settings", str(self.settings_path))

    def test_settings_blank_value_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.save_settings({"PACK_URL": ""})
        self.assert_refused("nonblank", "--settings", str(self.settings_path))

    def test_settings_value_that_holds_a_placeholder_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.save_settings({"PACK_URL": "${HOST}/a.zip"})
        self.assert_refused("must not hold", "--settings", str(self.settings_path))

    def test_settings_require_schema_version_one(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        self.save_settings({"PACK_URL": "http://host/a.zip"}, schema_version=2)
        self.assert_refused("schema_version 1", "--settings", str(self.settings_path))

    def test_settings_file_that_is_absent_is_refused(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        self.assert_refused(
            "cannot read settings", "--settings", str(self.directory / "nope.json")
        )

    def test_settings_unknown_top_level_key_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.settings_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "value": {"PACK_URL": "http://host/a.zip"},
                }
            ),
            encoding="utf-8",
        )
        self.assert_refused("unknown key", "--settings", str(self.settings_path))

    def test_default_renders_when_the_host_supplies_nothing(self):
        self.add(
            "plugins/bStats/config.yml",
            b"serverUuid: ${BSTATS_SERVER_UUID}\n",
            [{"name": "BSTATS_SERVER_UUID", "default": "11111111-2222"}],
        )
        self.save()
        code, _, errors = self.run_tool()
        self.assertEqual(0, code, errors)
        self.assertIn(
            b"serverUuid: 11111111-2222",
            (self.server / "plugins/bStats/config.yml").read_bytes(),
        )

    def test_placeholder_the_manifest_does_not_declare_is_refused(self):
        self.add(
            "server.properties",
            b"url=${PACK_URL}\nport=${PORT}\n",
            [{"name": "PACK_URL"}],
        )
        self.save()
        self.assert_refused("${PORT}", "--set", "PACK_URL=http://a/b.zip")

    def test_value_that_still_holds_a_placeholder_is_refused(self):
        self.add("server.properties", b"url=${PACK_URL}\n", [{"name": "PACK_URL"}])
        self.save()
        self.assert_refused(
            "still contains a placeholder", "--set", "PACK_URL=${HOST}/p.zip"
        )

    def test_instance_class_is_refused(self):
        self.add(
            "plugins/Multiverse-Core/worlds.yml",
            b"world: {}\n",
            classification="instance",
        )
        self.save()
        self.assert_refused("only source may be applied")

    def test_instance_path_is_refused_even_when_the_manifest_says_source(self):
        self.add("plugins/Multiverse-Core/worlds.yml", b"world: {}\n")
        self.save()
        self.assert_refused("instance state")

    def test_template_hash_drift_is_refused(self):
        self.add("server.properties", b"port=${PORT}\n", [{"name": "PORT"}])
        self.save()
        (self.config / "server.properties").write_bytes(b"port=${PORT}\n# edited\n")
        self.assert_refused("drifted from the manifest", "--set", "PORT=1")
        self.assertFalse((self.server / "server.properties").exists())

    def test_a_refusal_does_not_apply_the_entries_before_it(self):
        self.add("a.yml", b"a=1\n")
        self.add("b.yml", b"b=${B}\n", [{"name": "B"}])
        self.save()
        (self.config / "b.yml").write_bytes(b"b=${B}\n# edited\n")
        self.assert_refused("drifted from the manifest", "--set", "B=2")
        self.assertFalse((self.server / "a.yml").exists())
        self.assertFalse((self.server / "b.yml").exists())

    def test_dry_run_writes_nothing(self):
        self.add("server.properties", b"port=${PORT}\n", [{"name": "PORT"}])
        self.save()
        code, output, errors = self.run_tool("--dry-run", "--set", "PORT=1")
        self.assertEqual(0, code, errors)
        self.assertIn("CREATE", output)
        self.assertFalse((self.server / "server.properties").exists())

    def test_check_exits_one_on_a_difference_without_writing(self):
        self.add("server.properties", b"port=${PORT}\n", [{"name": "PORT"}])
        self.save()
        code, output, errors = self.run_tool("--check", "--set", "PORT=1")
        self.assertEqual(1, code, errors)
        self.assertIn("CREATE", output)
        self.assertFalse((self.server / "server.properties").exists())

    def test_check_exits_zero_when_the_host_matches(self):
        self.add("server.properties", b"port=${PORT}\n", [{"name": "PORT"}])
        self.save()
        self.assertEqual(0, self.run_tool("--set", "PORT=1")[0])
        code, output, errors = self.run_tool("--check", "--set", "PORT=1")
        self.assertEqual(0, code, errors)
        self.assertIn("UNCHANGED", output)

    def test_file_outside_the_manifest_is_refused(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        (self.config / "stray.yml").write_bytes(b"x: 1\n")
        self.assert_refused("not in the manifest")
        self.assertFalse((self.server / "server.properties").exists())

    def test_manifest_entry_without_a_template_is_refused(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        (self.config / "server.properties").unlink()
        self.assert_refused("missing from")

    def test_escaping_path_never_reaches_the_server_dir(self):
        self.files.append(
            {
                "path": "../outside.yml",
                "class": "source",
                "sha256": digest(b"x"),
                "placeholders": [],
            }
        )
        self.save()
        self.assert_refused()
        self.assertFalse((self.directory / "outside.yml").exists())

    def test_plain_crlf_survives_rendering(self):
        self.add(
            "server.properties",
            b"motd=Hi\r\nurl=${PACK_URL}\r\n",
            [{"name": "PACK_URL"}],
        )
        self.save()
        code, _, errors = self.run_tool("--set", "PACK_URL=http://a/b.zip")
        self.assertEqual(0, code, errors)
        payload = (self.server / "server.properties").read_bytes()
        self.assertEqual(b"motd=Hi\r\nurl=http://a/b.zip\r\n", payload)

    def test_duplicate_manifest_key_is_refused(self):
        self.lock_path.write_text('{"files": [], "files": []}', encoding="utf-8")
        self.assert_refused("duplicate JSON key")

    def test_absent_server_tree_is_created(self):
        self.add("plugins/GrimAC/config.yml", b"alerts: true\n")
        self.save()
        self.server.rmdir()
        code, output, errors = self.run_tool()
        self.assertEqual(0, code, errors)
        self.assertIn("CREATE", output)
        self.assertEqual(
            b"alerts: true\n",
            (self.server / "plugins/GrimAC/config.yml").read_bytes(),
        )

    def test_server_path_that_is_a_file_is_refused(self):
        self.add("server.properties", b"port=1\n")
        self.save()
        self.server.rmdir()
        self.server.write_bytes(b"not a directory")
        self.assert_refused("not a directory")

    def test_round_trip_against_a_fixture_server(self):
        expected = self.directory / "fixture"
        (expected / "plugins/GrimAC").mkdir(parents=True)
        self.add(
            "server.properties",
            b"motd=Fixture\r\nurl=${PACK_URL}\r\nsecret=${SECRET}\r\n",
            [{"name": "PACK_URL"}, {"name": "SECRET"}],
        )
        self.add("plugins/GrimAC/config.yml", b"alerts:\n  print-to-console: true\n")
        self.save()
        (expected / "server.properties").write_bytes(
            b"motd=Fixture\r\nurl=http://host/packs/a.zip\r\nsecret=s3cret\r\n"
        )
        (expected / "plugins/GrimAC/config.yml").write_bytes(
            b"alerts:\n  print-to-console: true\n"
        )
        code, output, errors = self.run_tool(
            "--set",
            "PACK_URL=http://host/packs/a.zip",
            "--set",
            "SECRET=s3cret",
        )
        self.assertEqual(0, code, errors)
        for relative in ("server.properties", "plugins/GrimAC/config.yml"):
            self.assertEqual(
                (expected / relative).read_bytes(),
                (self.server / relative).read_bytes(),
                relative,
            )
        self.assertEqual(2, output.count("CREATE"))


class ClassificationTests(unittest.TestCase):
    def test_source_and_instance_boundary(self):
        source = (
            "server.properties",
            "bukkit.yml",
            "config/paper-global.yml",
            "plugins/GrimAC/config.yml",
            "plugins/GrimAC/databases/mysql.yml",
            "plugins/Multiverse-Core/config.yml",
            "plugins/PackManagerPro/config.yml",
        )
        instance = (
            "world/level.dat",
            "logs/latest.log",
            "cache/foo",
            ".paper/x",
            "libraries/a.jar",
            "versions/a.jar",
            "packs/pack-a.zip",
            "plugins/Multiverse-Core/worlds.yml",
            "plugins/Multiverse-Core/anchors.yml",
            "plugins/floodgate/key.pem",
            "plugins/CoreProtect/.license",
            "plugins/CoreProtect/database.db",
            "plugins/GrimAC/data/history.v1.db",
            "plugins/Geyser-Spigot/nethernet/identity.pem",
            "plugins/SkinsRestorer/players/a.player",
            "plugins/SkinsRestorer/skins/b.playerskin",
            "plugins/SkinsRestorer/cache/x",
            "ops.json",
            "usercache.json",
            "eula.txt",
            "world.7z",
        )
        for relative in source:
            self.assertEqual("source", apply_config.classify(relative), relative)
        for relative in instance:
            self.assertEqual("instance", apply_config.classify(relative), relative)


class RepositoryConfigTests(unittest.TestCase):
    """The committed bundle must reproduce the live server byte for byte."""

    @classmethod
    def setUpClass(cls):
        cls.repository = Path(__file__).resolve().parents[1]

    def live_text(self, relative):
        path = self.repository / "server" / relative
        if not path.is_file():
            self.skipTest(f"live server file is absent: {relative}")
        return path.read_text(encoding="utf-8")

    def live_property(self, relative, key):
        """Read `key=value` out of a .properties file."""
        for line in self.live_text(relative).splitlines():
            if line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name == key:
                return value
        self.skipTest(f"{key} is absent from the live {relative}")

    def live_yaml(self, relative, *path):
        """Read a scalar at a YAML key path, honouring indentation."""
        stack = []
        for line in self.live_text(relative).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("- "):
                continue
            if ":" not in stripped:
                continue
            indent = len(line) - len(line.lstrip(" "))
            name, _, value = stripped.partition(":")
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, name.strip()))
            if tuple(part for _, part in stack) == path and value.strip():
                return value.strip().strip("\"'")
        self.skipTest(f"{'/'.join(path)} is absent from the live {relative}")

    def live_list_first(self, relative, key):
        """Read the first `- item` under a bare `key:` in a YAML file."""
        capture = False
        for line in self.live_text(relative).splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith(f"{key}:"):
                capture = True
                continue
            if capture and stripped.startswith("- "):
                return stripped[2:].strip().strip("\"'")
        self.skipTest(f"{key} is absent from the live {relative}")

    def run_tool(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = apply_config.main(list(args))
        return code, output.getvalue(), errors.getvalue()

    @unittest.skipUnless(
        (Path(__file__).resolve().parents[1] / "server").is_dir(), "no live server tree"
    )
    def test_committed_bundle_round_trips_the_live_server(self):
        # The coordinates live only in the gitignored server tree; the
        # credential comes from the environment. This is the documented deploy
        # shape, so the settings path is exercised for real.
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary) / "minecraft-server.json"
            settings.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "values": {
                            "PACK_URL": self.live_yaml(
                                "plugins/PackManagerPro/config.yml",
                                "per-world-application",
                                "trials",
                                "pack-url",
                            ),
                            "GEYSER_ADVERTISE_ADDRESS": self.live_list_first(
                                "plugins/Geyser-Spigot/config.yml",
                                "advertise-addresses",
                            ),
                            "MANAGEMENT_SERVER_SECRET": "env:MANAGEMENT_SERVER_SECRET",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "MANAGEMENT_SERVER_SECRET": self.live_property(
                        "server.properties", "management-server-secret"
                    )
                },
            ):
                code, output, errors = self.run_tool(
                    "--check", "--settings", str(settings)
                )
        self.assertEqual(0, code, errors)
        self.assertNotIn("CREATE", output)
        self.assertNotIn("UPDATE", output)
        self.assertEqual(28, output.count("UNCHANGED"))


if __name__ == "__main__":
    unittest.main()
