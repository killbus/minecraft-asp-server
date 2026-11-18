"""Deterministic Trials crop rebuild, using isolated fixture trees only."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest

from tests import scratch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import_trials.py"
SPEC = importlib.util.spec_from_file_location("import_trials", SCRIPT)
importer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(importer)


def tree_sha256(root):
    lines = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        lines.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + relative)
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class ImportTrialsTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(scratch.directory("import-trials-"))
        self.source = self.root / "source" / "Trials of the past"
        self.destination = self.root / "artifacts" / "trials-legacy"
        self.lock_path = self.root / "artifacts.lock.json"
        self.build_source()

    def build_source(self):
        overworld = self.source / "dimensions" / "minecraft" / "overworld"
        write(overworld / "region" / "r.-5.-1.mca", b"region west")
        write(overworld / "region" / "r.0.6.mca", b"region east")
        write(overworld / "region" / "r.1.0.mca", b"outside the crop")
        write(overworld / "region" / "r.-1.3.mca", b"legacy chunks")
        write(overworld / "region" / "r.0.3.mca", b"legacy chunks")
        write(overworld / "entities" / "r.0.0.mca", b"entities inside")
        write(overworld / "entities" / "r.1.0.mca", b"entities outside")
        write(overworld / "entities" / "r.-1.3.mca", b"legacy entities")
        write(overworld / "poi" / "r.-1.2.mca", b"poi inside")
        write(overworld / "poi" / "r.0.3.mca", b"legacy poi")
        write(overworld / "data" / "minecraft" / "world_border.dat", b"border")
        write(overworld / "data" / "minecraft" / "shared.dat", b"dimension wins")
        write(self.source / "data" / "raids.dat", b"raids")
        write(self.source / "data" / "minecraft" / "shared.dat", b"root loses")
        write(self.source / "data" / "minecraft" / "maps" / "0.dat", b"map zero")
        write(self.source / "level.dat", b"level header")
        write(self.source / "icon.png", b"icon")

    def run_tool(self, *arguments):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = importer.main([*arguments])
        return code, output.getvalue(), errors.getvalue()

    def rebuild(self, *extra):
        return self.run_tool(
            "--source", str(self.source), "--dest", str(self.destination), *extra
        )

    def test_crop_copies_only_the_planned_range(self):
        code, output, errors = self.rebuild("--no-verify")
        self.assertEqual(0, code, errors)
        self.assertIn("plan source=", output)
        self.assertIn("files=14", output)
        self.assertIn("copied=14 unchanged=0 pruned=0", output)

        copied = sorted(
            path.relative_to(self.destination).as_posix()
            for path in self.destination.rglob("*")
            if path.is_file()
        )
        self.assertEqual(
            [
                "data/minecraft/maps/0.dat",
                "data/minecraft/shared.dat",
                "data/minecraft/world_border.dat",
                "data/raids.dat",
                "entities/r.-1.3.mca",
                "entities/r.0.0.mca",
                "icon.png",
                "level.dat",
                "poi/r.-1.2.mca",
                "poi/r.0.3.mca",
                "region/r.-1.3.mca",
                "region/r.-5.-1.mca",
                "region/r.0.3.mca",
                "region/r.0.6.mca",
            ],
            copied,
        )
        self.assertFalse((self.destination / "region" / "r.1.0.mca").exists())
        self.assertFalse((self.destination / "entities" / "r.1.0.mca").exists())
        merged = self.destination / "data" / "minecraft" / "shared.dat"
        self.assertEqual(
            b"dimension wins", merged.read_bytes()
        )

    def test_second_run_copies_nothing_and_keeps_mtime(self):
        self.assertEqual(0, self.rebuild("--no-verify")[0])
        fingerprint = tree_sha256(self.destination)
        preserved = self.destination / "region" / "r.0.6.mca"
        os.utime(preserved, (1_000_000_000, 1_000_000_000))

        code, output, errors = self.rebuild("--no-verify")
        self.assertEqual(0, code, errors)
        self.assertIn("copied=0 unchanged=14 pruned=0", output)
        self.assertEqual(fingerprint, tree_sha256(self.destination))
        self.assertEqual(1_000_000_000, int(preserved.stat().st_mtime))

    def test_prune_removes_only_files_inside_the_plan_scope(self):
        self.assertEqual(0, self.rebuild("--no-verify")[0])
        extra = self.destination / "region" / "r.9.9.mca"
        extra.write_bytes(b"stale")

        code, output, errors = self.rebuild("--no-verify")
        self.assertEqual(0, code, errors)
        self.assertIn("extra region/r.9.9.mca", output)
        self.assertTrue(extra.exists())

        code, output, errors = self.rebuild("--no-verify", "--prune")
        self.assertEqual(0, code, errors)
        self.assertIn("prune region/r.9.9.mca", output)
        self.assertIn("pruned=1", output)
        self.assertFalse(extra.exists())

    def test_lock_verification_reports_ok_then_drift(self):
        self.assertEqual(0, self.rebuild("--no-verify")[0])
        copied = [path for path in self.destination.rglob("*") if path.is_file()]
        lock = {
            "schema_version": 1,
            "artifacts": [
                {
                    "name": "trials-legacy",
                    "path": "artifacts/trials-legacy",
                    "kind": "minecraft-anvil-crop",
                    "files": len(copied),
                    "bytes": sum(path.stat().st_size for path in copied),
                    "treeSha256": tree_sha256(self.destination),
                }
            ],
        }
        self.lock_path.write_text(json.dumps(lock), encoding="utf-8")

        code, output, errors = self.rebuild("--lock", str(self.lock_path))
        self.assertEqual(0, code, errors)
        self.assertIn("OK trials-legacy", output)

        target = self.destination / "level.dat"
        original = target.read_bytes()
        target.write_bytes(b"X" + original[1:])
        code, output, errors = self.run_tool(
            "--verify-only", "--dest", str(self.destination), "--lock", str(self.lock_path)
        )
        self.assertEqual(1, code)
        self.assertIn("DRIFT trials-legacy", output)
        self.assertIn("treeSha256 expected=", output)
        self.assertEqual("", errors)

    def test_destination_inside_source_is_an_error(self):
        destination = self.source / "crop"
        code, output, errors = self.run_tool(
            "--source", str(self.source), "--dest", str(destination), "--no-verify"
        )
        self.assertEqual(2, code)
        self.assertIn("must not be inside the source map root", errors)
        self.assertNotIn("Traceback", errors)

    def test_verify_only_without_a_lock_is_an_error(self):
        self.destination.mkdir(parents=True)
        code, output, errors = self.run_tool(
            "--verify-only",
            "--dest", str(self.destination),
            "--lock", str(self.root / "missing-lock.json"),
        )
        self.assertEqual(2, code)
        self.assertIn("lock file not found", errors)
        self.assertNotIn("Traceback", errors)

    def test_filesystem_failure_is_a_clean_error(self):
        self.destination.mkdir(parents=True)
        (self.destination / "region").write_bytes(b"not a directory")
        code, output, errors = self.run_tool(
            "--source", str(self.source), "--dest", str(self.destination), "--no-verify"
        )
        self.assertEqual(2, code)
        self.assertIn("ERROR:", errors)
        self.assertNotIn("Traceback", errors)


if __name__ == "__main__":
    unittest.main()
