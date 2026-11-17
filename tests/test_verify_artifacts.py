"""Read-only artifact verification, using isolated fixture directories only."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_artifacts.py"
SPEC = importlib.util.spec_from_file_location("verify_artifacts", SCRIPT)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def tree_sha256(root):
    lines = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        lines.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + relative)
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


class ArtifactVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tree = self.root / "artifacts" / "example"
        (self.tree / "region").mkdir(parents=True)
        (self.tree / "region" / "r.0.0.mca").write_bytes(b"region content")
        (self.tree / "level.dat").write_bytes(b"level header")
        self.lock_path = self.root / "artifacts.lock.json"
        self.lock = {
            "schema_version": 1,
            "artifacts": [
                {
                    "name": "example",
                    "path": "artifacts/example",
                    "kind": "minecraft-anvil-crop",
                    "source": "https://example.org/map",
                    "sourceArchive": "example.rar",
                    "files": 2,
                    "bytes": 14 + 12,
                    "treeSha256": tree_sha256(self.tree),
                }
            ],
        }
        self.save_lock()

    def save_lock(self):
        self.lock_path.write_text(json.dumps(self.lock), encoding="utf-8")

    def run_verifier(self):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = verifier.main(["--root", str(self.root), "--lock", str(self.lock_path)])
        return code, output.getvalue(), errors.getvalue()

    def test_matching_tree_is_ok(self):
        code, output, errors = self.run_verifier()
        self.assertEqual(0, code)
        self.assertIn("OK         example", output)
        self.assertIn("1 artifact(s): 1 OK, 0 failed", output)
        self.assertEqual("", errors)

    def test_file_count_mismatch_is_drift(self):
        (self.tree / "extra.mca").write_bytes(b"extra")
        code, output, errors = self.run_verifier()
        self.assertEqual(1, code)
        self.assertIn("DRIFT      example", output)
        self.assertIn("files expected=2 actual=3", output)
        self.assertIn("1 artifact(s): 0 OK, 1 failed", output)
        self.assertEqual("", errors)

    def test_tree_hash_mismatch_is_drift(self):
        # Same length, so files and bytes still match and only the tree hash moves.
        (self.tree / "level.dat").write_bytes(b"LEVEL header")
        code, output, errors = self.run_verifier()
        self.assertEqual(1, code)
        self.assertIn("DRIFT      example", output)
        self.assertNotIn("files expected", output)
        self.assertNotIn("bytes expected", output)
        self.assertIn("treeSha256 expected=", output)
        self.assertEqual("", errors)

    def test_unsafe_lock_path_is_an_error(self):
        for value in ["artifacts/../escape", "/artifacts/example", "artifacts\\example"]:
            with self.subTest(path=value):
                self.lock["artifacts"][0]["path"] = value
                self.save_lock()
                code, output, errors = self.run_verifier()
                self.assertEqual(2, code)
                self.assertIn("ERROR:", errors)
                self.assertIn("normalized relative POSIX path", errors)
                self.assertNotIn("Traceback", errors)


if __name__ == "__main__":
    unittest.main()
