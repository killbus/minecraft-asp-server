"""Read-only runtime verification, using isolated fixture directories only."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_runtime.py"
SPEC = importlib.util.spec_from_file_location("verify_runtime", SCRIPT)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class RuntimeVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.server = self.directory / "server"
        self.server.mkdir()
        self.lock_path = self.directory / "runtime.lock.json"
        self.lock = {"schema_version": 1, "datapack_directories": ["world/datapacks"], "artifacts": []}
        self.install("server", "paper-server.jar", b"server content")
        self.install("plugin", "plugins/example.jar", b"plugin content")
        self.install("datapack", "world/datapacks/example.zip", b"datapack content")
        self.save_lock()

    def write(self, relative, content=b"extra content"):
        path = self.server / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def install(self, kind, relative, content):
        self.write(relative, content)
        self.lock["artifacts"].append({
            "id": kind,
            "kind": kind,
            "path": relative,
            "version": "1.0.0",
            "source": "https://example.org/releases/1.0.0",
            "sha256": hashlib.sha256(content).hexdigest(),
        })

    def save_lock(self):
        self.lock_path.write_text(json.dumps(self.lock), encoding="utf-8")

    def run_verifier(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = verifier.main(["--lock", str(self.lock_path), "--server-dir", str(self.server), *args])
        return code, output.getvalue(), errors.getvalue()

    def assert_error(self, contains=None):
        code, output, errors = self.run_verifier()
        self.assertEqual(2, code, (output, errors))
        self.assertIn("ERROR:", errors)
        self.assertNotIn("Traceback", errors)
        if contains:
            self.assertIn(contains, errors)

    def test_all_matching_files_are_ok(self):
        code, output, errors = self.run_verifier()
        self.assertEqual(0, code)
        self.assertEqual(3, output.count("OK"))
        self.assertEqual("", errors)

    def test_missing_file_is_drift(self):
        (self.server / "plugins/example.jar").unlink()
        code, output, errors = self.run_verifier()
        self.assertEqual(1, code)
        self.assertIn("MISSING    plugins/example.jar", output)
        self.assertEqual("", errors)

    def test_modified_file_shows_expected_and_actual_hash(self):
        self.write("plugins/example.jar", b"changed")
        code, output, errors = self.run_verifier()
        self.assertEqual(1, code)
        self.assertIn("MODIFIED   plugins/example.jar", output)
        self.assertIn("expected=" + self.lock["artifacts"][1]["sha256"], output)
        self.assertIn("actual=" + hashlib.sha256(b"changed").hexdigest(), output)
        self.assertEqual("", errors)

    def test_unmanaged_files_and_unpacked_datapack(self):
        extras = ["old-server.jar", "plugins/extra.JAR", "world/datapacks/extra.ZIP"]
        for relative in extras:
            self.write(relative)
        self.write("world/datapacks/unpacked/pack.mcmeta", b"{}")
        code, output, errors = self.run_verifier()
        self.assertEqual(1, code)
        self.assertEqual(4, output.count("UNMANAGED"))
        for relative in extras + ["world/datapacks/unpacked"]:
            self.assertIn("UNMANAGED  " + relative, output)
        self.assertIn("directory hashing is unsupported", output)
        self.assertEqual("", errors)

    def test_ignores_nested_caches_dependencies_config_and_backups(self):
        for relative in [
            "cache/server.jar", "libraries/dependency.jar", "plugins/.paper-remapped/remapped.jar",
            "plugins/Example/dependency.jar", "plugins/Example/config.yml", "backups/old.jar",
            "other-world/datapacks/extra.zip", "world/datapacks/not-a-pack/nested.zip",
            "world/datapacks/README.txt", "plugins/config.yml", "server.properties",
        ]:
            self.write(relative)
        code, output, errors = self.run_verifier()
        self.assertEqual(0, code, output)
        self.assertEqual("", errors)

    def test_missing_empty_scan_directories_are_allowed(self):
        self.lock["artifacts"] = self.lock["artifacts"][:1]
        self.save_lock()
        shutil.rmtree(self.server / "plugins")
        shutil.rmtree(self.server / "world")
        self.assertEqual(0, self.run_verifier()[0])

    def test_missing_scan_directory_with_declared_file_is_missing(self):
        shutil.rmtree(self.server / "plugins")
        code, output, errors = self.run_verifier()
        self.assertEqual(1, code, errors)
        self.assertIn("MISSING    plugins/example.jar", output)

    def test_missing_server_directory_is_error(self):
        shutil.rmtree(self.server)
        self.assert_error("server directory")

    def test_file_instead_of_server_directory_is_error(self):
        shutil.rmtree(self.server)
        self.server.write_text("not a directory", encoding="utf-8")
        self.assert_error("not a directory")

    def test_file_instead_of_scan_directory_is_error(self):
        self.lock["artifacts"] = self.lock["artifacts"][:1]
        self.save_lock()
        shutil.rmtree(self.server / "plugins")
        (self.server / "plugins").write_bytes(b"wrong type")
        self.assert_error("scan directory is not a directory")

    def test_directory_instead_of_declared_file_is_error(self):
        path = self.server / "plugins/example.jar"
        path.unlink()
        path.mkdir()
        self.assert_error("not a regular file")

    def test_duplicate_artifact_id_is_error(self):
        self.lock["artifacts"][1]["id"] = "server"
        self.save_lock()
        self.assert_error("duplicate artifact id")

    def test_duplicate_artifact_path_casefold_is_error(self):
        artifact = copy.deepcopy(self.lock["artifacts"][1])
        artifact.update(id="duplicate", path="plugins/EXAMPLE.jar")
        self.lock["artifacts"].append(artifact)
        self.save_lock()
        self.assert_error("duplicate artifact path")

    def test_duplicate_scan_directory_casefold_is_error(self):
        self.lock["datapack_directories"].append("WORLD/datapacks")
        self.save_lock()
        self.assert_error("duplicate datapack directory")

    def test_bad_schema_and_top_level_types_are_errors(self):
        original = copy.deepcopy(self.lock)
        for field, value in [
            ("schema_version", True), ("schema_version", "1"), ("schema_version", 1.0),
            ("schema_version", 2), ("artifacts", {}), ("artifacts", ["bad"]),
            ("datapack_directories", "world/datapacks"), ("notes", []),
        ]:
            with self.subTest(field=field, value=value):
                self.lock = copy.deepcopy(original)
                self.lock[field] = value
                self.save_lock()
                self.assert_error()
        for value in [[], None, 1]:
            self.lock_path.write_text(json.dumps(value), encoding="utf-8")
            self.assert_error("JSON object")

    def test_missing_required_fields_are_errors(self):
        original = copy.deepcopy(self.lock)
        for field in ["id", "kind", "path", "version", "source", "sha256"]:
            with self.subTest(field=field):
                self.lock = copy.deepcopy(original)
                del self.lock["artifacts"][1][field]
                self.save_lock()
                self.assert_error()

    def test_bad_artifact_metadata_is_error(self):
        original = copy.deepcopy(self.lock)
        for field, value in [
            ("id", " "), ("id", []), ("kind", "mod"), ("version", ""),
            ("version", 1), ("version", "1\n2"), ("source", "local-file"),
            ("source", "ftp://example.org/file"), ("source", "https://"),
            ("source", "https://example.org:invalid"), ("source", "https://bad host/path"),
            ("source", "https://[bad"), ("sha256", "f" * 63), ("sha256", "g" * 64),
            ("sha256", 0), ("build", ""), ("build", 12), ("notes", None),
            ("download_url", "file:///tmp/plugin.jar"),
        ]:
            with self.subTest(field=field, value=value):
                self.lock = copy.deepcopy(original)
                self.lock["artifacts"][1][field] = value
                self.save_lock()
                self.assert_error()

    def test_optional_metadata_and_uppercase_digest_are_valid(self):
        self.lock["notes"] = "Approved baseline"
        self.lock["artifacts"][0].update(
            build="123", notes="Locally reviewed", download_url="https://example.org/server.jar"
        )
        self.lock["artifacts"][0]["sha256"] = self.lock["artifacts"][0]["sha256"].upper()
        self.save_lock()
        self.assertEqual(0, self.run_verifier()[0])

    def test_unpaired_surrogate_path_is_error(self):
        for surrogate in ["\ud800", "\udfff"]:
            with self.subTest(surrogate=repr(surrogate)):
                self.lock["artifacts"][1]["path"] = f"plugins/{surrogate}.jar"
                self.save_lock()
                self.assert_error("unpaired Unicode surrogates")

    def test_invalid_and_out_of_scope_artifact_paths_are_errors(self):
        original = copy.deepcopy(self.lock)
        for value in [
            "../outside.jar", "/plugins/a.jar", "C:/plugins/a.jar", "C:a.jar",
            "plugins\\a.jar", "plugins/../a.jar", "plugins//a.jar", "plugins/./a.jar",
            "plugins/a.jar/", "plugins/a.jar:stream", "plugins/a.jar.", "plugins/a.jar ",
            "plugins/nested/a.jar", "config/a.jar", "plugins/a.zip", "", "plugins/\x00.jar",
        ]:
            with self.subTest(path=value):
                self.lock = copy.deepcopy(original)
                self.lock["artifacts"][1]["path"] = value
                self.save_lock()
                self.assert_error()

    def test_invalid_datapack_directories_are_errors(self):
        for value in ["../packs", "/packs", "D:/packs", "world\\datapacks", ".", "", None, 3]:
            with self.subTest(directory=value):
                self.lock["datapack_directories"] = [value]
                self.save_lock()
                self.assert_error()

    def test_datapacks_must_be_zips_in_explicit_directories(self):
        for value in ["other/datapacks/example.zip", "world/datapacks/example", "world/datapacks/sub/example.zip"]:
            with self.subTest(path=value):
                self.lock["artifacts"][2]["path"] = value
                self.save_lock()
                self.assert_error("installation scope")

    def test_exactly_one_canonical_server_artifact_is_required(self):
        self.lock["artifacts"][0]["path"] = "other-server.jar"
        self.save_lock()
        self.assert_error("installation scope")
        self.lock["artifacts"].pop(0)
        self.save_lock()
        self.assert_error("exactly one server")

    def test_invalid_json_and_duplicate_keys_are_errors(self):
        for content in [b"{", b"\xff", b'{"schema_version":1,"schema_version":1}']:
            with self.subTest(content=content):
                self.lock_path.write_bytes(content)
                self.assert_error()

    def test_missing_lock_is_error(self):
        self.lock_path.unlink()
        self.assert_error("cannot read lock")

    def test_unreadable_lock_is_error(self):
        with patch.object(Path, "open", side_effect=PermissionError("permission denied")):
            self.assert_error("cannot read lock")

    def test_unreadable_artifact_is_error(self):
        original = Path.open

        def open_file(path, *args, **kwargs):
            if path.name == "example.jar":
                raise PermissionError("permission denied")
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", open_file):
            self.assert_error("cannot read artifact")

    def test_unreadable_scan_directory_is_error(self):
        with patch.object(verifier.os, "scandir", side_effect=PermissionError("permission denied")):
            self.assert_error("cannot scan")

    def test_unreadable_stat_is_not_treated_as_missing(self):
        original = Path.stat

        def inspect(path, *args, **kwargs):
            if path.name == "example.jar":
                raise PermissionError("permission denied")
            return original(path, *args, **kwargs)

        with patch.object(Path, "stat", inspect):
            self.assert_error("permission denied")

    def symlink(self, path, target, is_directory=False):
        try:
            path.symlink_to(target, target_is_directory=is_directory)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlinks unavailable: {error}")

    def test_declared_symlink_outside_root_is_refused_before_read(self):
        outside = self.directory / "outside.jar"
        outside.write_bytes(b"outside")
        path = self.server / "plugins/example.jar"
        path.unlink()
        self.symlink(path, outside)
        with patch.object(verifier, "fingerprint", wraps=verifier.fingerprint) as fingerprint:
            self.assert_error("escapes server directory")
            self.assertNotIn(outside, [call.args[0] for call in fingerprint.call_args_list])

    def test_unmanaged_symlink_outside_root_is_refused(self):
        outside = self.directory / "outside.jar"
        outside.write_bytes(b"outside")
        self.symlink(self.server / "extra.jar", outside)
        self.assert_error("escapes server directory")

    def test_scan_directory_symlink_outside_root_is_refused(self):
        shutil.rmtree(self.server / "world/datapacks")
        outside = self.directory / "packs"
        outside.mkdir()
        self.symlink(self.server / "world/datapacks", outside, True)
        self.assert_error("escapes server directory")

    def test_symlink_inside_root_is_supported(self):
        target = self.write("cache/example.jar", b"plugin content")
        path = self.server / "plugins/example.jar"
        path.unlink()
        self.symlink(path, target)
        self.assertEqual(0, self.run_verifier()[0])

    def test_relative_overrides_use_caller_working_directory(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--lock", "runtime.lock.json", "--server-dir", "server"],
            cwd=self.directory, capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(3, result.stdout.count("OK"))

    def test_defaults_are_anchored_to_script_not_working_directory(self):
        scripts = self.directory / "scripts"
        scripts.mkdir()
        copied_script = scripts / SCRIPT.name
        shutil.copyfile(SCRIPT, copied_script)
        elsewhere = self.directory / "elsewhere"
        elsewhere.mkdir()
        result = subprocess.run(
            [sys.executable, "-B", str(copied_script)], cwd=elsewhere, capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(3, result.stdout.count("OK"))

    def test_cli_invalid_arguments_exit_two(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--adopt"], capture_output=True, text=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("ERROR:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_verification_does_not_write_runtime_or_lock(self):
        def snapshot():
            return {
                path.relative_to(self.directory).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.directory.rglob("*") if path.is_file()
            }

        self.write("world/datapacks/unpacked/pack.mcmeta", b"{}")
        self.write("plugins/extra.jar")
        self.write("paper-server.jar", b"modified")
        (self.server / "plugins/example.jar").unlink()
        before = snapshot()
        self.assertEqual(1, self.run_verifier()[0])
        self.assertEqual(before, snapshot())
        self.assertFalse(list(self.directory.rglob("__pycache__")))


if __name__ == "__main__":
    unittest.main()
