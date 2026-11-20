"""The snapshot must carry the untracked per-host settings file.

git holds the example only, so a host's real coordinates exist nowhere else
on that machine. A backup that captured the rendered config but not the input
would restore a server nobody can re-apply.
"""

import os
from pathlib import Path
import shutil
import subprocess
import unittest

from tests import scratch


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "scripts" / "backup.sh"
SH = shutil.which("sh")

SETTINGS = '{"schema_version": 1, "values": {}}' + "\n"


@unittest.skipIf(SH is None, "POSIX sh is not available")
class BackupSettingsTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(scratch.directory("backup-settings-"))
        self.server = self.root / "server"
        self.settings = self.root / "settings"
        self.target = self.root / "backups"
        (self.server / "world").mkdir(parents=True)
        (self.server / "world" / "level.dat").write_bytes(b"level")
        (self.server / "paper-server.jar").write_bytes(b"")
        self.settings.mkdir()
        self.target.mkdir()

    def backup(self, settings):
        return subprocess.run(
            [SH, BACKUP.as_posix(), self.server.as_posix()],
            cwd=ROOT.as_posix(),
            capture_output=True,
            text=True,
            env={
                "PATH": os.environ["PATH"],
                "SETTINGS_DIR": Path(settings).as_posix(),
                "BACKUP_TARGETS": self.target.as_posix(),
            },
        )

    def snapshot(self):
        directories = [path for path in self.target.iterdir() if path.is_dir()]
        self.assertEqual(1, len(directories))
        return directories[0]

    def test_the_production_settings_file_is_snapshotted(self):
        production = self.settings / "minecraft-server.json"
        production.write_text(SETTINGS, encoding="utf-8")
        example = self.settings / "minecraft-server.example.json"
        example.write_text(SETTINGS, encoding="utf-8")

        result = self.backup(self.settings)

        self.assertEqual(0, result.returncode, result.stderr)
        snapshot = self.snapshot()
        self.assertTrue((snapshot / "COMPLETE").is_file())
        self.assertEqual(
            production.read_text(encoding="utf-8"),
            (snapshot / "settings" / production.name).read_text(encoding="utf-8"),
        )
        self.assertFalse((snapshot / "settings" / example.name).exists())
        manifest = (snapshot / "MANIFEST.txt").read_text(encoding="utf-8")
        self.assertIn("./settings/minecraft-server.json", manifest)

    def test_a_host_without_settings_still_snapshots(self):
        result = self.backup(self.root / "absent")

        self.assertEqual(0, result.returncode, result.stderr)
        snapshot = self.snapshot()
        self.assertTrue((snapshot / "COMPLETE").is_file())
        self.assertFalse((snapshot / "settings").exists())

    def test_player_state_and_lifecycle_settings_are_in_the_snapshot(self):
        state_paths = (
            "plugins/Multiverse-Core/worlds.yml",
            "plugins/Multiverse-Inventories/config.yml",
            "plugins/Multiverse-Inventories/groups.yml",
            "plugins/Multiverse-Inventories/playernames.json",
            "plugins/Multiverse-Inventories/worlds/adventure/player.json",
            "plugins/Multiverse-Inventories/groups/shared/player.json",
            "plugins/Multiverse-Inventories/players/player.json",
            "plugins/MultiverseWorldLifecycle/config.yml",
            "world/players/data/player.dat",
        )
        for relative in state_paths:
            path = self.server / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"host state: {relative}".encode())
        jar = "plugins/Multiverse-WorldLifecycle-0.1.0.jar"
        (self.server / jar).write_bytes(b"rebuildable binary")
        production = self.settings / "minecraft-server.json"
        production.write_text(
            '{"schema_version":1,"values":{"WORLD_LIFECYCLE_MANAGED_WORLDS":"[\\"adventure\\"]"}}\n',
            encoding="utf-8",
        )

        result = self.backup(self.settings)

        self.assertEqual(0, result.returncode, result.stderr)
        snapshot = self.snapshot()
        self.assertTrue((snapshot / "COMPLETE").is_file())
        manifest = (snapshot / "MANIFEST.txt").read_text(encoding="utf-8")
        for relative in state_paths:
            self.assertEqual((self.server / relative).read_bytes(), (snapshot / relative).read_bytes())
            self.assertIn(f"./{relative}", manifest)
        self.assertEqual(production.read_bytes(), (snapshot / "settings/minecraft-server.json").read_bytes())
        self.assertIn("./settings/minecraft-server.json", manifest)
        self.assertFalse((snapshot / jar).exists())
        self.assertNotIn(jar, manifest)
