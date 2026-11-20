"""Native save selection through isolated frpc and shared-TCP scene fixtures."""

import os
from pathlib import Path
import shutil
import subprocess
import unittest

from tests import scratch
from tests.test_frpc_scene_manifest import STUB_TMUX
from tests.test_frpc_shared_tcp_scene import FAKE_PEM


ROOT = Path(__file__).resolve().parents[1]
GIT_BASH = Path("D:/Applications/Scoop/apps/git/current/bin/bash.exe")
SHELL = str(GIT_BASH) if os.name == "nt" and GIT_BASH.is_file() else shutil.which("sh")


@unittest.skipIf(SHELL is None, "POSIX shell unavailable")
class SingleWorldSceneTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(scratch.directory("world-scenes-"))
        self.scenes = self.root / "scripts/scenes"
        self.scenes.mkdir(parents=True)
        for name in ("frpc.sh", "frpc-shared-tcp.sh"):
            path = self.scenes / name
            path.write_text((ROOT / "scripts/scenes" / name).read_text(encoding="utf-8"),
                            encoding="utf-8", newline="\n")
            path.chmod(0o755)
        self.server = self.root / "server"
        (self.server / "Adventure_A").mkdir(parents=True)
        (self.server / "Adventure_A/level.dat").write_bytes(b"native save")
        (self.server / "DimensionOnly/region").mkdir(parents=True)
        (self.server / "packs").mkdir()
        self.config = self.root / "frpc.toml"
        self.config.write_text("serverAddr = 'example.com'\n", encoding="utf-8")
        self.manifest = self.root / "production.scene"
        self.manifest.write_text(
            "session = world-test\nserver = false\n[entry]\nbinary = frpc\nconfig = frpc.toml\n",
            encoding="utf-8",
        )
        self.pem = self.root / "entry.pem"
        self.pem.write_text(FAKE_PEM, encoding="utf-8")
        self.stubs = self.root / "stubs"
        self.stubs.mkdir()
        self.log = self.root / "tmux.log"
        for name, text in (("tmux", STUB_TMUX), ("frpc", "#!/bin/sh\nexit 0\n")):
            path = self.stubs / name
            path.write_text(text, encoding="utf-8", newline="\n")
            path.chmod(0o755)

    def run_scene(self, name, *arguments, manifest=False):
        environment = dict(os.environ)
        environment.update(
            PATH=os.pathsep.join([self.stubs.as_posix(), environment["PATH"]]),
            TMUX_STUB_LOG=self.log.as_posix(), FRPC_READY_TIMEOUT="0", FRPC_SESSION="world-test",
        )
        self.log.write_text("", encoding="utf-8")
        selection = ["--scene", self.manifest.as_posix()] if manifest else ["--config", self.config.as_posix()]
        return subprocess.run(
            [SHELL, (self.scenes / name).as_posix(), "up", *selection, *arguments],
            cwd=self.root, env=environment, text=True, capture_output=True, timeout=30,
        )

    def test_plain_scene_launches_selected_save_after_sidecars(self):
        result = self.run_scene("frpc.sh", "--world", "Adventure_A", "--no-attach")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        log = self.log.read_text(encoding="utf-8")
        command = "bash scripts/start.sh --world 'Adventure_A'"
        self.assertIn(command, log)
        self.assertLess(log.index("frpc.toml"), log.index(command))
        self.assertEqual(b"native save", (self.server / "Adventure_A/level.dat").read_bytes())

    def test_shared_scene_combines_world_tls_proxy_and_owned_pack_server(self):
        result = self.run_scene(
            "frpc-shared-tcp.sh", "--world", "Adventure_A", "--dry-run",
            "--tls-cert", self.pem.as_posix(), "--proxy-protocol", "--serve-packs",
            manifest=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        for expected in ("bash scripts/start.sh --world 'Adventure_A'", "frontend lan_java",
                         "send-proxy-v2", "backend tls_termination", "frontend tls_terminated",
                         "serve-packs.sh", "use_backend packs if is_packs"):
            self.assertIn(expected, result.stdout)
        self.assertLess(result.stdout.index("serve-packs.sh"), result.stdout.index("bash scripts/start.sh"))
        self.assertEqual("", self.log.read_text(encoding="utf-8"))

    def test_default_scene_command_is_unchanged(self):
        for name in ("frpc.sh", "frpc-shared-tcp.sh"):
            with self.subTest(name=name):
                result = self.run_scene(name, "--dry-run")
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn("bash scripts/start.sh", result.stdout)
                self.assertNotIn("start.sh --world", result.stdout)

    def test_invalid_selection_fails_before_tmux(self):
        for name in ("frpc.sh", "frpc-shared-tcp.sh"):
            for arguments in (("--world",), ("--world", ""), ("--world", "../escape"),
                              ("--world", "missing"), ("--world", "DimensionOnly"),
                              ("--world", "Adventure_A", "--world", "Adventure_A"),
                              ("--world", "quoted&name")):
                with self.subTest(name=name, arguments=arguments):
                    result = self.run_scene(name, *arguments)
                    self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                    self.assertEqual("", self.log.read_text(encoding="utf-8"))

    def test_serverless_scene_refuses_selection_unless_deferred(self):
        result = self.run_scene("frpc.sh", "--world", "Adventure_A", "--dry-run", manifest=True)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertIn("scene that starts a server", result.stderr)
        result = self.run_scene("frpc.sh", "--world", "Adventure_A", "--dry-run", "--defer-server", manifest=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_linked_save_is_refused(self):
        try:
            (self.server / "Linked").symlink_to(self.server / "Adventure_A", target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation unavailable")
        for name in ("frpc.sh", "frpc-shared-tcp.sh"):
            with self.subTest(name=name):
                result = self.run_scene(name, "--world", "Linked")
                self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                self.assertEqual("", self.log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
