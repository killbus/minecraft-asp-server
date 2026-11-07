#!/usr/bin/env python3
"""Check installed runtime artifacts against a lock file without changing either."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from urllib.parse import urlsplit


class VerificationError(Exception):
    """Invalid metadata, unsafe paths, or an incomplete filesystem check."""


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


def require_url(value, label):
    value = require_text(value, label)
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in ("http", "https") and parsed.hostname
        parsed.port  # Validate malformed ports as well as malformed host syntax.
    except ValueError as error:
        raise VerificationError(f"{label} is not a valid HTTP(S) URL: {error}") from error
    if not valid or any(character.isspace() for character in value):
        raise VerificationError(f"{label} must be an absolute HTTP(S) URL")


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
    directories = lock.get("datapack_directories")
    if not isinstance(directories, list):
        raise VerificationError("datapack_directories must be an array")
    directory_keys = set()
    for index, directory in enumerate(directories):
        relative_path(directory, f"datapack_directories[{index}]")
        if directory.casefold() in directory_keys:
            raise VerificationError(f"duplicate datapack directory: {directory}")
        directory_keys.add(directory.casefold())

    artifacts = lock.get("artifacts")
    if not isinstance(artifacts, list):
        raise VerificationError("artifacts must be an array")
    ids, paths = set(), set()
    server_count = 0
    for index, artifact in enumerate(artifacts):
        label = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            raise VerificationError(f"{label} must be an object")
        for field in ("id", "kind", "version"):
            require_text(artifact.get(field), f"{label}.{field}")
        path = relative_path(artifact.get("path"), f"{label}.path")
        require_url(artifact.get("source"), f"{label}.source")
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
            raise VerificationError(f"{label}.sha256 must contain exactly 64 hexadecimal digits")
        if "build" in artifact:
            require_text(artifact["build"], f"{label}.build")
        if "notes" in artifact and not isinstance(artifact["notes"], str):
            raise VerificationError(f"{label}.notes must be a string")
        if "download_url" in artifact:
            require_url(artifact["download_url"], f"{label}.download_url")
        if artifact["id"] in ids:
            raise VerificationError(f"duplicate artifact id: {artifact['id']}")
        if str(path).casefold() in paths:
            raise VerificationError(f"duplicate artifact path: {path}")
        ids.add(artifact["id"])
        paths.add(str(path).casefold())

        kind = artifact["kind"]
        if kind == "server":
            server_count += 1
            valid_scope = str(path) == "asp-server.jar"
        elif kind == "plugin":
            valid_scope = str(path.parent) == "plugins" and path.suffix.lower() == ".jar"
        elif kind == "datapack":
            valid_scope = str(path.parent) in directories and path.suffix.lower() == ".zip"
        else:
            raise VerificationError(f"{label}.kind must be server, plugin, or datapack")
        if not valid_scope:
            raise VerificationError(f"{label}.path is outside the {kind} installation scope: {path}")
    if server_count != 1:
        raise VerificationError("artifacts must declare exactly one server at asp-server.jar")
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
            raise VerificationError(f"path escapes server directory through a link: {path}")
    return path


def file_status(path):
    try:
        return path.stat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise VerificationError(f"cannot inspect {path}: {error}") from error


def fingerprint(path):
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise VerificationError(f"cannot read artifact {path}: {error}") from error
    return digest.hexdigest()


def scan_directory(root, relative, suffix, unpacked=False):
    directory = safe_path(root, relative)
    info = file_status(directory)
    if info is None:
        return []
    if not stat.S_ISDIR(info.st_mode):
        raise VerificationError(f"scan directory is not a directory: {directory}")
    try:
        with os.scandir(directory) as entries:
            names = sorted(entry.name for entry in entries)
    except OSError as error:
        raise VerificationError(f"cannot scan {directory}: {error}") from error
    found = []
    for name in names:
        candidate = PurePosixPath(relative) / name
        matches_suffix = candidate.suffix.lower() == suffix
        if not matches_suffix and not unpacked:
            continue
        path = safe_path(root, candidate)
        info = file_status(path)
        if info is None:
            raise VerificationError(f"scan entry is missing or a broken link: {path}")
        if stat.S_ISDIR(info.st_mode) and unpacked:
            marker = safe_path(root, candidate / "pack.mcmeta")
            if file_status(marker) is not None:
                found.append((str(candidate), "unpacked datapack; directory hashing is unsupported in v1"))
        elif matches_suffix:
            if not stat.S_ISREG(info.st_mode):
                raise VerificationError(f"installed artifact is not a regular file: {path}")
            found.append((str(candidate), "not declared in lock"))
    return found


def verify(lock, server_dir):
    try:
        root = server_dir.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise VerificationError(f"cannot access server directory {server_dir}: {error}") from error
    info = file_status(root)
    if info is None or not stat.S_ISDIR(info.st_mode):
        raise VerificationError(f"server directory is not a directory: {root}")
    results = []
    declared = set()
    for artifact in lock["artifacts"]:
        relative = artifact["path"]
        declared.add(Path(relative))
        path = safe_path(root, relative)
        info = file_status(path)
        if info is None:
            results.append(("MISSING", relative, "declared file is absent"))
            continue
        if not stat.S_ISREG(info.st_mode):
            raise VerificationError(f"declared artifact is not a regular file: {path}")
        actual = fingerprint(path)
        expected = artifact["sha256"].lower()
        if actual == expected:
            results.append(("OK", relative, ""))
        else:
            results.append(("MODIFIED", relative, f"expected={expected} actual={actual}"))

    found = scan_directory(root, ".", ".jar") + scan_directory(root, "plugins", ".jar")
    for directory in lock["datapack_directories"]:
        found.extend(scan_directory(root, directory, ".zip", unpacked=True))
    for relative, detail in found:
        if Path(relative) not in declared:
            results.append(("UNMANAGED", relative, detail))
    return results


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, f"ERROR: {message}\n")


def main(argv=None):
    repository = Path(__file__).resolve().parent.parent
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=repository / "runtime.lock.json")
    parser.add_argument("--server-dir", type=Path, default=repository / "server")
    args = parser.parse_args(argv)
    try:
        results = verify(read_lock(args.lock), args.server_dir)
    except VerificationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    for status, path, detail in results:
        print(f"{status:<10} {path}" + (f" - {detail}" if detail else ""))
    return int(any(status != "OK" for status, _, _ in results))


if __name__ == "__main__":
    sys.exit(main())
