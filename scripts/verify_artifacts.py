#!/usr/bin/env python3
"""Check immutable artifact trees against artifacts.lock.json without changing them."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys


class VerificationError(Exception):
    """Invalid metadata, unsafe paths, or an unreadable artifact tree."""


def require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise VerificationError(f"{label} must be a nonblank string")
    if any(ord(character) < 32 for character in value):
        raise VerificationError(f"{label} must not contain control characters")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise VerificationError(f"{label} must not contain unpaired Unicode surrogates")
    return value


def relative_path(value, label):
    value = require_text(value, label)
    parts = value.split("/")
    if (
        any(part in ("", ".", "..") or part.endswith((" ", ".")) for part in parts)
        or any(character in value for character in '\\:<>"|?*')
    ):
        raise VerificationError(f"{label} must be a normalized relative POSIX path: {value!r}")
    return PurePosixPath(value)


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def read_lock(path):
    try:
        with path.open(encoding="utf-8") as stream:
            lock = json.load(stream, object_pairs_hook=unique_json_object)
    except (OSError, UnicodeError, ValueError) as error:
        raise VerificationError(f"cannot read lock {path}: {error}") from error
    if not isinstance(lock, dict):
        raise VerificationError("lock must be a JSON object")
    if type(lock.get("schema_version")) is not int or lock["schema_version"] != 1:
        raise VerificationError("schema_version must be the integer 1")
    if "notes" in lock and not isinstance(lock["notes"], str):
        raise VerificationError("lock notes must be a string")

    artifacts = lock.get("artifacts")
    if not isinstance(artifacts, list):
        raise VerificationError("artifacts must be an array")
    names, paths = set(), set()
    for index, artifact in enumerate(artifacts):
        label = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            raise VerificationError(f"{label} must be an object")
        name = require_text(artifact.get("name"), f"{label}.name")
        path = relative_path(artifact.get("path"), f"{label}.path")
        require_text(artifact.get("kind"), f"{label}.kind")
        for field in ("source", "sourceArchive", "notes"):
            if field in artifact:
                require_text(artifact[field], f"{label}.{field}")
        for field in ("files", "bytes"):
            value = artifact.get(field)
            if type(value) is not int or value < 0:
                raise VerificationError(f"{label}.{field} must be a non-negative integer")
        digest = artifact.get("treeSha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
            raise VerificationError(f"{label}.treeSha256 must contain exactly 64 hexadecimal digits")
        if name.casefold() in names:
            raise VerificationError(f"duplicate artifact name: {name}")
        if str(path).casefold() in paths:
            raise VerificationError(f"duplicate artifact path: {path}")
        names.add(name.casefold())
        paths.add(str(path).casefold())
    return lock


def safe_path(root, relative):
    path = root
    # Check each component: an intermediate link must not escape and re-enter.
    for part in PurePosixPath(relative).parts:
        path = path / part
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError) as error:
            raise VerificationError(f"cannot resolve {path}: {error}") from error
        if not resolved.is_relative_to(root):
            raise VerificationError(f"path escapes the artifact root through a link: {path}")
    return path


def scan_tree(root, relative=PurePosixPath(".")):
    """Return every regular file as (relative POSIX path, size), sorted by path."""
    directory = safe_path(root, relative)
    try:
        with os.scandir(directory) as entries:
            names = sorted(entry.name for entry in entries)
    except OSError as error:
        raise VerificationError(f"cannot scan {directory}: {error}") from error
    found = []
    for name in names:
        candidate = relative / name
        path = safe_path(root, candidate)
        try:
            info = path.stat(follow_symlinks=False)
        except OSError as error:
            raise VerificationError(f"cannot inspect {path}: {error}") from error
        if stat.S_ISDIR(info.st_mode):
            found.extend(scan_tree(root, candidate))
        elif stat.S_ISREG(info.st_mode):
            found.append((str(candidate), info.st_size))
        else:
            raise VerificationError(f"artifact entry is not a regular file or directory: {path}")
    return sorted(found)


def fingerprint(path):
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise VerificationError(f"cannot read {path}: {error}") from error
    return digest.hexdigest()


def tree_fingerprint(root, files):
    lines = [f"{fingerprint(safe_path(root, relative))}  {relative}" for relative, _ in files]
    digest = hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()
    return len(files), sum(size for _, size in files), digest


def verify(lock, artifact_root):
    try:
        root = artifact_root.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise VerificationError(f"cannot access artifact root {artifact_root}: {error}") from error
    if not root.is_dir():
        raise VerificationError(f"artifact root is not a directory: {root}")

    results = []
    for artifact in lock["artifacts"]:
        name, relative = artifact["name"], PurePosixPath(artifact["path"])
        path = safe_path(root, relative)
        try:
            info = path.stat()
        except FileNotFoundError:
            results.append(("MISSING", name, f"{relative} is absent"))
            continue
        except OSError as error:
            raise VerificationError(f"cannot inspect {path}: {error}") from error
        if not stat.S_ISDIR(info.st_mode):
            results.append(("NOT-DIR", name, f"{relative} is not a directory"))
            continue

        files, total, tree = tree_fingerprint(path, scan_tree(path))
        problems = []
        if files != artifact["files"]:
            problems.append(f"files expected={artifact['files']} actual={files}")
        if total != artifact["bytes"]:
            problems.append(f"bytes expected={artifact['bytes']} actual={total}")
        if tree != artifact["treeSha256"].lower():
            problems.append(f"treeSha256 expected={artifact['treeSha256'].lower()} actual={tree}")
        if problems:
            results.append(("DRIFT", name, "; ".join(problems)))
        else:
            results.append(("OK", name, ""))
    return results


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, f"ERROR: {message}\n")


def main(argv=None):
    repository = Path(__file__).resolve().parent.parent
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=repository)
    parser.add_argument("--lock", type=Path, default=None)
    args = parser.parse_args(argv)
    lock_path = args.lock if args.lock is not None else args.root / "artifacts.lock.json"
    try:
        results = verify(read_lock(lock_path), args.root)
    except VerificationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    for status, name, detail in results:
        print(f"{status:<10} {name}" + (f" - {detail}" if detail else ""))
    ok = sum(1 for status, _, _ in results if status == "OK")
    print(f"{len(results)} artifact(s): {ok} OK, {len(results) - ok} failed")
    return int(ok != len(results))


if __name__ == "__main__":
    sys.exit(main())
