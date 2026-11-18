#!/usr/bin/env python3
"""Reject commit subjects that mix a contract boundary with an instance."""

import argparse
from pathlib import Path
import re
import sys


TYPES = frozenset(
    {
        "feat",
        "fix",
        "docs",
        "chore",
        "test",
        "refactor",
        "perf",
        "build",
        "ci",
        "ops",
        "revert",
    }
)
SCOPES = frozenset(
    {
        "server",
        "runtime",
        "plugins",
        "world",
        "scenes",
        "scripts",
        "bedrock",
        "docs",
        "sop",
        "tests",
        "task",
        "workspace",
        "repo",
        "ci",
        "backup",
        "config",
    }
)
RUNTIME_SCOPES = frozenset({"server", "runtime", "plugins", "config"})
CONTENT_SCOPE = "world"

SUBJECT = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9-]+)\))?!?: (?P<summary>\S.*)$"
)
INSTANCE_METRICS = re.compile(
    r"\b\d[\d,]*\s*(regions?|chunks?|files?|bytes?|MiB|MB|GB)\b", re.IGNORECASE
)
LONG_HASH = re.compile(r"\b[0-9a-f]{12,64}\b", re.IGNORECASE)
RUNTIME_TOKENS = re.compile(
    r"\b(paper|multiverse|asp|slime|runtime|engine|jar|plugins?)\b", re.IGNORECASE
)
CONTENT_TOKENS = re.compile(
    r"\b(trials|adventure\s+map|regions?|chunks?|anvil)\b", re.IGNORECASE
)
SKIP_PREFIXES = ("Merge ", "Revert ", "fixup! ", "squash! ")
SCISSORS = "# ------------------------ >8 ------------------------"


def strip_comments(message):
    lines = []
    for line in message.splitlines():
        if line.strip() == SCISSORS:
            break
        if line.startswith("#"):
            continue
        lines.append(line)
    return lines


def check(message):
    """Return a list of human-readable violations for a commit message."""
    lines = strip_comments(message)
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return ["commit message is empty"]

    subject = lines[0].rstrip()
    if subject.startswith(SKIP_PREFIXES):
        return []

    errors = []
    if len(subject) > 72:
        errors.append(f"subject is {len(subject)} chars; keep it <= 72")

    match = SUBJECT.match(subject)
    if match is None:
        errors.append(
            "subject must be '<type>(<scope>): <summary>' "
            "(scope optional, e.g. 'fix: ...')"
        )
        return errors

    commit_type = match.group("type")
    scope = match.group("scope")
    if commit_type not in TYPES:
        errors.append(
            f"unknown type '{commit_type}'; use one of {', '.join(sorted(TYPES))}"
        )
    if scope is not None and scope not in SCOPES:
        errors.append(
            f"unknown scope '{scope}'; use one of {', '.join(sorted(SCOPES))}"
        )

    if INSTANCE_METRICS.search(subject):
        errors.append(
            "subject carries an instance metric (count + region/chunk/file/byte); "
            "name the contract, move the measurement to the body"
        )
    if LONG_HASH.search(subject):
        errors.append(
            "subject carries an artifact hash; keep the hash in the body"
        )

    if scope == CONTENT_SCOPE and RUNTIME_TOKENS.search(subject):
        errors.append(
            "scope 'world' describes map content, but the subject names runtime "
            "machinery; use 'server'/'runtime' or split the commit"
        )
    elif scope in RUNTIME_SCOPES and CONTENT_TOKENS.search(subject):
        errors.append(
            f"scope '{scope}' describes the runtime, but the subject names map "
            "content; use 'world' or move the instance detail to the body"
        )

    if len(lines) > 1 and lines[1].strip():
        errors.append("leave one blank line between the subject and the body")
    return errors


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, f"ERROR: {message}\n")


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("message_file", type=Path)
    args = parser.parse_args(argv)
    try:
        message = args.message_file.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        print(f"ERROR: cannot read {args.message_file}: {error}", file=sys.stderr)
        return 2

    errors = check(message)
    if not errors:
        return 0
    print("ERROR: commit message violates the boundary gate:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    print(
        "See .trellis/spec/guides/commit-discipline.md. "
        "Use --no-verify only for a documented exception.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
