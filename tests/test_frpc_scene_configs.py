"""Which files a `--config` directory contributes to the frpc scene.

Every file the scene selects is handed to frpc, so a directory that also
holds a certificate, a backup or a note must not turn into a dead sidecar
that aborts the start. `--dry-run` needs neither tmux nor frpc, which is
what makes the selection testable here.
"""

from pathlib import Path
import re
import shutil
import subprocess
import unittest

from tests import scratch


ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "scripts" / "scenes" / "frpc.sh"
SHARED_SCENE = ROOT / "scripts" / "scenes" / "frpc-shared-tcp.sh"
SH = shutil.which("sh")


@unittest.skipIf(SH is None, "POSIX sh is not available")
class FrpcConfigDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(scratch.directory("frpc-configs-")) / "frpcs"
        self.directory.mkdir()

    def write(self, name):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# frpc\n", encoding="utf-8")
        return path

    def dry_run(self, scene, *arguments):
        return subprocess.run(
            [SH, scene.as_posix(), "up", "--dry-run", *arguments],
            cwd=ROOT, capture_output=True, text=True,
        )

    def windows(self, output):
        return sorted(re.findall(r"-n (frpc-\S+)", output))

    def sidecar_names(self, output):
        """Basenames the scene handed to frpc, paths aside (sh and Python
        spell the same temporary directory differently on Windows)."""
        return sorted(Path(path).name for path in re.findall(r"'frpc' -c '([^']+)'", output))

    def ignored_names(self, stderr):
        return sorted(Path(path).name for path in re.findall(r"note: ignoring (.+?) \(not ", stderr))

    def test_a_directory_selects_only_frpc_config_names(self):
        for name in [
            "one.toml", "two.ini", "three.YAML", "four.yml",
            "notes.txt", "staging.pem", "frpcs.ini.bak", ".hidden.toml",
        ]:
            self.write(name)
        self.write("nested/deep.toml")

        result = self.dry_run(SCENE, "--config", self.directory.as_posix())

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            ["frpc-four", "frpc-one", "frpc-three", "frpc-two"], self.windows(result.stdout),
        )
        self.assertEqual(
            ["four.yml", "one.toml", "three.YAML", "two.ini"], self.sidecar_names(result.stdout),
        )
        self.assertEqual(["frpcs.ini.bak", "notes.txt", "staging.pem"], self.ignored_names(result.stderr))
        self.assertNotIn("hidden", result.stdout)
        self.assertNotIn("nested", result.stdout)

    def test_an_explicit_file_is_used_whatever_it_is_called(self):
        path = self.write("staging.pem")
        result = self.dry_run(SCENE, "--config", path.as_posix())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["frpc-staging"], self.windows(result.stdout))
        self.assertEqual(["staging.pem"], self.sidecar_names(result.stdout))
        self.assertNotIn("note: ignoring", result.stderr)

    def test_a_directory_without_a_config_file_is_an_error(self):
        self.write("notes.txt")
        result = self.dry_run(SCENE, "--config", self.directory.as_posix())
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("resolved to no files", result.stderr)
        self.assertIn("note: ignoring", result.stderr)

    def test_ignored_files_are_named_on_stderr_only(self):
        self.write("one.toml")
        self.write("cert.pem")
        result = self.dry_run(SCENE, "--config", self.directory.as_posix())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("cert.pem", result.stderr)
        self.assertNotIn("cert.pem", result.stdout)

    def test_a_mixed_directory_still_starts_every_real_config(self):
        self.write("frpc.toml")
        self.write("frpc2.ini")
        self.write("tls/staging.pem")
        result = self.dry_run(SCENE, "--config", self.directory.as_posix())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["frpc-frpc", "frpc-frpc2"], self.windows(result.stdout))
        self.assertEqual(["frpc.toml", "frpc2.ini"], self.sidecar_names(result.stdout))
        self.assertNotIn("note: ignoring", result.stderr)

    def test_the_shared_scene_inherits_the_same_selection(self):
        self.write("one.toml")
        self.write("staging.pem")
        result = self.dry_run(SHARED_SCENE, "--config", self.directory.as_posix())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("note: ignoring", result.stderr)
        self.assertEqual(["frpc-one"], self.windows(result.stdout))

    def test_names_come_from_the_basename_without_its_extension(self):
        self.write("mc-bedrock.toml")
        result = self.dry_run(SCENE, "--config", self.directory.as_posix())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["frpc-mc-bedrock"], self.windows(result.stdout))


if __name__ == "__main__":
    unittest.main()
