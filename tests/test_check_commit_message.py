"""Boundary gate for commit subjects."""

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_commit_message.py"
SPEC = importlib.util.spec_from_file_location("check_commit_message", SCRIPT)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class CommitMessageTests(unittest.TestCase):
    def assert_clean(self, message):
        self.assertEqual([], checker.check(message))

    def assert_rejected(self, message, fragment):
        errors = checker.check(message)
        self.assertTrue(errors, f"expected a rejection for: {message!r}")
        self.assertTrue(
            any(fragment in error for error in errors),
            f"{fragment!r} not in {errors}",
        )

    def test_runtime_subject_that_names_the_map_is_rejected(self):
        self.assert_rejected(
            "feat(world): run the adventure map on Paper + Multiverse",
            "names runtime machinery",
        )

    def test_content_scope_may_name_the_map(self):
        self.assert_clean("feat(world): import the trials crop")
        self.assert_clean("feat(world): restore two legacy regions")

    def test_runtime_scope_may_not_name_content_counts(self):
        self.assert_rejected(
            "feat(server): upgrade 644 pre-1.13 chunks", "instance metric"
        )
        self.assert_rejected(
            "fix(server): load the anvil world", "names map content"
        )

    def test_runtime_capability_subject_is_allowed(self):
        self.assert_clean(
            "feat(server): replace ASP with Paper + Multiverse world switching"
        )
        self.assert_clean("fix(runtime): unload idle dimensions")

    def test_artifact_metrics_and_hashes_belong_in_the_body(self):
        self.assert_rejected("chore(world): rebuild 294 files", "instance metric")
        self.assert_rejected(
            "chore(world): pin e3896e8ddaac73078bbb379ecb7bcfcedbffe831d4c094000aaf5d91448c67bc",
            "artifact hash",
        )

    def test_format_and_scope_allowlist(self):
        self.assert_rejected("updated some stuff", "subject must be")
        self.assert_rejected("feat(nonsense): add a thing", "unknown scope")
        self.assert_clean("docs(sop): name the relay sender")
        self.assert_clean("chore: record journal")
        self.assert_clean("chore(task): archive 11-17-anvil-world-switching")

    def test_body_needs_a_blank_line_after_subject(self):
        self.assert_rejected(
            "fix(server): stop the worker pool\nbody starts here",
            "blank line",
        )

    def test_merge_and_fixup_messages_are_exempt(self):
        self.assert_clean("Merge pull request #1 from killbus/branch")
        self.assert_clean('Revert "feat(world): run the adventure map"')
        self.assert_clean("fixup! feat(server): something")


if __name__ == "__main__":
    unittest.main()
