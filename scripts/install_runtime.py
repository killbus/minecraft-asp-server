#!/usr/bin/env python3
"""Install the runtime artifacts declared by runtime.lock.json.

The lock is the single source of truth: this command only places the files it
names, verifies each against its recorded SHA-256, and never edits configs,
plugin data, or world content. ``verify_runtime.py`` remains the read-only
check; this is the command that turns a missing file into a present one.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

try:
    from scripts import verify_runtime as verifier
except ImportError:  # Running as `python scripts/install_runtime.py`.
    import verify_runtime as verifier


REPOSITORY = Path(__file__).resolve().parent.parent
CHUNK = 1024 * 1024


def _destination(server_dir, artifact):
    return verifier.safe_path(server_dir, artifact["path"])


def _download(url, destination, expected):
    """Stream url into destination.part, verify, then rename atomically."""
    part = destination.with_name(f"{destination.name}.part.{os.getpid()}")
    digest = hashlib.sha256()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            url, headers={"User-Agent": "asp-runtime-installer/1"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise OSError(f"HTTP {status}")
            with part.open("wb") as stream:
                for block in iter(lambda: response.read(CHUNK), b""):
                    digest.update(block)
                    stream.write(block)
        actual = digest.hexdigest()
        if actual != expected:
            raise ValueError(f"sha256 mismatch: got {actual}, expected {expected}")
        os.replace(part, destination)
    except BaseException:
        try:
            part.unlink()
        except OSError:
            pass
        raise


def _install(artifact, server_dir, replace):
    destination = _destination(server_dir, artifact)
    expected = artifact["sha256"].lower()

    if destination.exists():
        actual = verifier.fingerprint(destination)
        if actual == expected:
            return "OK", destination, None
        if not replace:
            return "DRIFT", destination, f"sha256 {actual}"

    url = artifact.get("download_url")
    if not url:
        return "MANUAL", destination, artifact["source"]

    try:
        _download(url, destination, expected)
    except (OSError, ValueError, urllib.error.URLError) as error:
        return "FAIL", destination, str(error)
    return "INSTALL", destination, None


def _select(lock, only):
    artifacts = lock["artifacts"]
    if not only:
        return artifacts
    known = {artifact["id"] for artifact in artifacts}
    unknown = [name for name in only if name not in known]
    if unknown:
        raise verifier.VerificationError(
            "unknown artifact id: " + ", ".join(unknown)
        )
    return [artifact for artifact in artifacts if artifact["id"] in set(only)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=REPOSITORY / "runtime.lock.json")
    parser.add_argument("--server-dir", type=Path, default=REPOSITORY / "server")
    parser.add_argument("--only", action="append", default=[], metavar="ID")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace", action="store_true")
    arguments = parser.parse_args(argv)

    try:
        lock = verifier.read_lock(arguments.lock)
        selected = _select(lock, arguments.only)
        # safe_path compares against a resolved root; a relative server-dir
        # would make every join look like an escape.
        arguments.server_dir = arguments.server_dir.resolve()
    except verifier.VerificationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"ERROR: cannot resolve server directory: {error}", file=sys.stderr)
        return 2

    counts = {}
    try:
        for artifact in selected:
            if arguments.dry_run:
                destination = _destination(arguments.server_dir, artifact)
                if destination.exists():
                    if verifier.fingerprint(destination) == artifact["sha256"].lower():
                        status, detail = "OK", None
                    else:
                        status, detail = "DRIFT", "would not be replaced"
                elif artifact.get("download_url"):
                    status, detail = "INSTALL", artifact["download_url"]
                else:
                    status, detail = "MANUAL", artifact["source"]
            else:
                status, destination, detail = _install(
                    artifact, arguments.server_dir, arguments.replace,
                )
            counts[status] = counts.get(status, 0) + 1
            line = f"{status:8} {artifact['id']:20} {destination}"
            if detail:
                line += f"  ({detail})"
            print(line)
    except verifier.VerificationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    summary = ", ".join(f"{counts[name]} {name}" for name in sorted(counts))
    print(f"summary: {summary or 'nothing selected'}")
    unresolved = counts.get("DRIFT", 0) + counts.get("MANUAL", 0) + counts.get("FAIL", 0)
    if arguments.dry_run:
        unresolved += counts.get("INSTALL", 0)
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
