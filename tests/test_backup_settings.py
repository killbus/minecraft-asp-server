"""Host-owned backup targets and destructive-path guards, using isolated trees."""

import io
import json
import os
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from tests import scratch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import backup_settings
from host_settings import read_host_settings
from verify_runtime import VerificationError


class BackupSettingsTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(scratch.directory("backup-settings-"))
        self.server = self.root / "server"
        self.server.mkdir()
        self.settings = self.root / "settings/minecraft-server.json"
        self.settings.parent.mkdir()
        self.enterContext(patch.dict(os.environ))
        os.environ.pop("BACKUP_ROOT", None)
        os.environ.pop("BACKUP_TARGETS", None)

    def write(self, targets):
        self.settings.write_text(json.dumps({"schema_version": 1,
                                            "values": {"SECRET": "env:UNSET_BACKUP_SECRET"},
                                            "backup": {"targets": targets}}), encoding="utf-8")

    def test_targets_resolve_from_repository_and_preserve_order_spaces(self):
        mirror = self.root / "other disk/mirror"
        self.write(["local backups", str(mirror)])
        self.assertEqual([self.root / "local backups", mirror], backup_settings.targets(self.root))
        self.assertFalse(mirror.exists())

    def test_missing_settings_or_backup_section_is_actionable(self):
        with self.assertRaisesRegex(VerificationError, "cannot read settings"):
            backup_settings.targets(self.root)
        self.settings.write_text('{"schema_version":1,"values":{}}', encoding="utf-8")
        with self.assertRaisesRegex(VerificationError, "configure backup.targets"):
            backup_settings.targets(self.root)

    def test_shared_schema_validates_only_raw_backup_paths(self):
        self.write(["missing mount/path"])
        self.assertEqual(["missing mount/path"], read_host_settings(self.settings)["backup"]["targets"])
        for value in (None, {}, {"targets": []}, {"targets": "backup"}, {"targets": [""]},
                      {"targets": [123]}, {"targets": ["path\nother"]}, {"targets": ["path\x7f"]},
                      {"targets": ["env:DESTINATION"]}, {"targets": ["${TARGET}"]},
                      {"targets": ["backup"], "unknown": True}):
            with self.subTest(value=value):
                self.settings.write_text(json.dumps({"schema_version": 1, "values": {}, "backup": value}))
                with self.assertRaises(VerificationError):
                    read_host_settings(self.settings)

    def test_legacy_environment_destinations_refuse_but_empty_is_inert(self):
        self.write(["backups"])
        for name in ("BACKUP_ROOT", "BACKUP_TARGETS"):
            with patch.dict(os.environ, {name: "old-destination"}):
                with self.assertRaisesRegex(VerificationError, "move destinations into backup.targets"):
                    backup_settings.targets(self.root)
            with patch.dict(os.environ, {name: ""}):
                self.assertEqual([self.root / "backups"], backup_settings.targets(self.root))

    def test_duplicates_nested_sources_and_files_refuse_without_creating_targets(self):
        (self.root / "target-file").write_text("keep")
        for targets in (["backup", "./backup"], ["backup/nested", "backup"],
                        ["backup", "server"], ["backup", "server/snapshot"],
                        ["backup", "settings"], ["backup", "."],
                        ["backup", "target-file"], ["backup", "target-file/nested"]):
            with self.subTest(targets=targets):
                self.write(targets)
                with self.assertRaises((VerificationError, OSError)):
                    backup_settings.targets(self.root)
                self.assertFalse((self.root / "backup").exists())
                self.assertEqual("keep", (self.root / "target-file").read_text())

    def test_source_overrides_are_protected(self):
        source = self.root / "alternate source"
        self.write(["alternate source/nested"])
        for arguments in ({"server_dir": source}, {"settings_dir": source}):
            with self.assertRaisesRegex(VerificationError, "overlaps a source"):
                backup_settings.targets(self.root, **arguments)

    def test_target_links_and_timestamp_links_are_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        link = self.root / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        self.write(["linked/backups"])
        with self.assertRaisesRegex(VerificationError, "links or junctions"):
            backup_settings.targets(self.root)
        target = self.root / "backups"
        target.mkdir()
        (target / "20000101-000000").symlink_to(outside, target_is_directory=True)
        self.write(["backups"])
        with self.assertRaisesRegex(VerificationError, "links or junctions"):
            backup_settings.targets(self.root)
        self.assertEqual("keep", (outside / "keep.txt").read_text())

    def test_parent_segments_do_not_hide_linked_components(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.root / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        self.write(["linked/../backups"])
        with self.assertRaisesRegex(VerificationError, "links or junctions"):
            backup_settings.targets(self.root)
        self.write(["backups"])
        with self.assertRaisesRegex(VerificationError, "links or junctions"):
            backup_settings.targets(self.root, server_dir=link / ".." / "server")
        self.write(["server/../backups"])
        self.assertEqual([self.root / "backups"], backup_settings.targets(self.root))
        self.assertFalse((self.root / "backups").exists())

    def test_snapshot_guard_refuses_escape_collision_and_nested_links(self):
        target = self.root / "backup"
        target.mkdir()
        for name in ("../outside", "", "20000101-000000/../other", "unrelated"):
            with self.assertRaises(VerificationError):
                backup_settings.validate_snapshot(target, name)
        snapshot = target / "20000101-000000"
        snapshot.mkdir()
        with self.assertRaisesRegex(VerificationError, "already exists"):
            backup_settings.validate_snapshot(target, snapshot.name, new=True)
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (snapshot / "linked").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaisesRegex(VerificationError, "links or junctions"):
            backup_settings.validate_snapshot(target, snapshot.name)
        self.assertTrue(snapshot.exists())

    def test_resolution_does_not_scan_retained_snapshot_contents(self):
        self.write(["backups"])
        snapshot = self.root / "backups/20000101-000000"
        snapshot.mkdir(parents=True)
        with patch.object(backup_settings, "validate_tree", side_effect=AssertionError("unexpected scan")):
            self.assertEqual([self.root / "backups"], backup_settings.targets(self.root))

    def test_helper_outputs_data_only_and_never_resolves_credentials(self):
        self.write(["backup with spaces"])
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(backup_settings, "REPOSITORY", self.root), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(0, backup_settings.main([]))
        self.assertEqual((self.root / "backup with spaces").as_posix() + "\n", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    def test_cmd_metacharacters_refuse_before_emitting_any_target(self):
        for character in backup_settings.CMD_UNSAFE:
            self.write(["backup", "unsafe" + character + "path"])
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(backup_settings, "REPOSITORY", self.root), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(2, backup_settings.main(["--format", "cmd"]))
            self.assertEqual("", stdout.getvalue())
            self.assertIn("CMD backup paths cannot contain", stderr.getvalue())

    @unittest.skipUnless(os.name == "nt", "Windows native path rules")
    def test_windows_reserved_components_refuse_before_emitting_any_target(self):
        for invalid in ("COM1", "lpt2.txt", "bad:stream", "bad/trailing.", "trailing "):
            with self.subTest(invalid=invalid):
                self.write(["backup", invalid])
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(backup_settings, "REPOSITORY", self.root), \
                        redirect_stdout(stdout), redirect_stderr(stderr):
                    self.assertEqual(2, backup_settings.main(["--format", "cmd"]))
                self.assertEqual("", stdout.getvalue())
                self.assertIn("invalid Windows path component", stderr.getvalue())
                self.assertFalse((self.root / "backup").exists())


if __name__ == "__main__":
    unittest.main()
