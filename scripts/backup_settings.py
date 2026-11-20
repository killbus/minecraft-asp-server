"""Validate configured backup destinations and timestamp children without writing."""

import argparse
import os
from pathlib import Path
import re
import stat
import sys

from host_settings import read_host_settings
from verify_runtime import VerificationError

REPOSITORY = Path(__file__).absolute().parents[1]
TIMESTAMP = re.compile(r"[0-9]{8}-[0-9]{6}")
CMD_UNSAFE = '!%&^|<>()"'
WINDOWS_DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])", re.IGNORECASE)


def checked_path(path, directory=True):
    path = Path(path).absolute()
    if os.name == "nt":
        for component in path.parts[1:]:
            if component == "..":
                continue
            if (component.endswith((" ", ".")) or
                any(character in ':*?"<>|' or ord(character) < 32 for character in component) or
                WINDOWS_DEVICE.fullmatch(component.partition(".")[0].rstrip(" "))):
                raise VerificationError(f"invalid Windows path component in backup path: {component}")
    for component in (*reversed(path.parents), path):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or (
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise VerificationError(f"backup paths must not contain links or junctions: {component}")
        if (component != path or directory) and not stat.S_ISDIR(metadata.st_mode):
            raise VerificationError(f"backup path is not a directory: {component}")
    return path.resolve()


def validate_tree(path):
    checked_path(path)
    def refuse_walk(error):
        raise error
    if path.exists():
        for directory, subdirectories, filenames in os.walk(path, followlinks=False, onerror=refuse_walk):
            for name in subdirectories + filenames:
                checked_path(Path(directory) / name, directory=False)


def validate_snapshot(target, timestamp, new=False):
    if not TIMESTAMP.fullmatch(timestamp):
        raise VerificationError("backup snapshot name must be a UTC timestamp")
    target = checked_path(target)
    snapshot = checked_path(target / timestamp)
    if snapshot.parent != target or not snapshot.is_relative_to(target):
        raise VerificationError("backup snapshot must stay inside its configured target")
    if new and snapshot.exists():
        raise VerificationError(f"backup timestamp already exists; refusing to overwrite: {snapshot}")
    if not new:
        validate_tree(snapshot)
    return snapshot


def targets(root, server_dir=None, settings_dir=None, format="sh"):
    for name in ("BACKUP_ROOT", "BACKUP_TARGETS"):
        if os.environ.get(name):
            raise VerificationError(f"{name} is no longer supported; move destinations into backup.targets in settings/minecraft-server.json and unset it")
    root = checked_path(root)
    config = checked_path(root / "settings/minecraft-server.json", directory=False)
    document = read_host_settings(config)
    if "backup" not in document:
        raise VerificationError("configure backup.targets in settings/minecraft-server.json before running backup")
    source_paths = [checked_path(server_dir or root / "server"),
                    checked_path(settings_dir or root / "settings"), checked_path(root / "settings")]
    result = []
    for raw in document["backup"]["targets"]:
        path = Path(raw)
        if path.drive and not path.is_absolute():
            raise VerificationError("backup targets must not use drive-relative paths")
        if format == "cmd":
            for candidate in [path, root, *source_paths]:
                if any(character in str(candidate) for character in CMD_UNSAFE):
                    raise VerificationError(f"CMD backup paths cannot contain these characters: {CMD_UNSAFE}")
        path = checked_path(path if path.is_absolute() else root / path)
        for source in source_paths:
            if path.is_relative_to(source) or source.is_relative_to(path):
                raise VerificationError(f"backup target overlaps a source directory: {path}")
        for other in result:
            if path.is_relative_to(other) or other.is_relative_to(path):
                raise VerificationError("backup targets must not duplicate or contain one another")
        if path.exists():
            for child in path.iterdir():
                if TIMESTAMP.fullmatch(child.name):
                    checked_path(child)
        result.append(path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("sh", "cmd"), default="sh")
    parser.add_argument("--server-dir", type=Path)
    parser.add_argument("--settings-dir", type=Path)
    parser.add_argument("--snapshot", nargs=2, metavar=("TARGET", "TIMESTAMP"))
    parser.add_argument("--new", action="store_true")
    args = parser.parse_args(argv)
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(newline="\n")
        if args.snapshot:
            validate_snapshot(Path(args.snapshot[0]), args.snapshot[1], args.new)
        else:
            configured = targets(REPOSITORY, args.server_dir, args.settings_dir, args.format)
            for path in configured:
                print(str(path) if args.format == "cmd" else path.as_posix())
    except (VerificationError, OSError, ValueError) as error:
        print(f"[backup] ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
