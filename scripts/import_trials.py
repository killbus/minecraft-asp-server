#!/usr/bin/env python3
"""Rebuild the immutable Trials Anvil crop from an operator-supplied map root."""

import argparse
import importlib.util
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
_VERIFIER_SPEC = importlib.util.spec_from_file_location(
    "verify_artifacts", SCRIPT_DIRECTORY / "verify_artifacts.py"
)
verify_artifacts = importlib.util.module_from_spec(_VERIFIER_SPEC)
_VERIFIER_SPEC.loader.exec_module(verify_artifacts)

ARTIFACT_NAME = "trials-legacy"
REGION_X = range(-5, 1)
REGION_Z = range(-1, 7)
CHUNK_KINDS = ("region", "entities", "poi")
ROOT_FILES = ("level.dat", "icon.png")
PRUNABLE_ROOTS = frozenset(CHUNK_KINDS + ("data",))


class RebuildError(Exception):
    """Unusable source, destination, or lock metadata."""


def sorted_files(root):
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def is_map_root(path):
    return (path / "level.dat").is_file() and (
        path / "dimensions" / "minecraft" / "overworld"
    ).is_dir()


def resolve_map_root(directory):
    directory = directory.resolve()
    if is_map_root(directory):
        return directory
    candidates = sorted(
        {path.parent for path in directory.rglob("level.dat") if is_map_root(path.parent)},
        key=lambda path: path.as_posix(),
    )
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RebuildError(
            f"no map root under {directory}: expected level.dat plus "
            "dimensions/minecraft/overworld"
        )
    listing = ", ".join(str(path) for path in candidates)
    raise RebuildError(f"multiple map roots under {directory}: {listing}")


def extract_archive(archive, destination):
    commands = (
        ("unrar", ["x", "-o+", "-y", str(archive), str(destination)]),
        ("7z", ["x", "-y", f"-o{destination}", str(archive)]),
    )
    for tool, arguments in commands:
        executable = shutil.which(tool)
        if executable is None:
            continue
        result = subprocess.run(
            [executable, *arguments], capture_output=True, text=True, errors="replace"
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise RebuildError(
                f"{tool} failed with exit code {result.returncode}"
                + (f": {detail[-1]}" if detail else "")
            )
        return destination
    raise RebuildError(
        f"cannot extract {archive}: neither unrar nor 7z is available on PATH"
    )


def build_plan(source):
    overworld = source / "dimensions" / "minecraft" / "overworld"
    plan = {}

    for kind in CHUNK_KINDS:
        for x in REGION_X:
            for z in REGION_Z:
                relative = PurePosixPath(kind, f"r.{x}.{z}.mca")
                candidate = overworld / relative
                if candidate.is_file():
                    plan[str(relative)] = candidate
    if not any(name.startswith("region/") for name in plan):
        raise RebuildError(
            f"no region files in crop x={REGION_X.start}-{REGION_X.stop - 1} "
            f"z={REGION_Z.start}-{REGION_Z.stop - 1} under {overworld / 'region'}"
        )

    for path in sorted_files(overworld / "data" / "minecraft"):
        relative = path.relative_to(overworld / "data" / "minecraft").as_posix()
        plan[f"data/minecraft/{relative}"] = path

    # The dimension-local data wins; root-level map data only fills the gaps.
    for path in sorted_files(source / "data"):
        relative = path.relative_to(source / "data").as_posix()
        plan.setdefault(f"data/{relative}", path)

    for name in ROOT_FILES:
        candidate = source / name
        if candidate.is_file():
            plan[name] = candidate
        elif name == "level.dat":
            raise RebuildError(f"map root has no level.dat: {source}")
    return plan


def same_content(left, right):
    if left.stat().st_size != right.stat().st_size:
        return False
    return verify_artifacts.fingerprint(left) == verify_artifacts.fingerprint(right)


def copy_plan(plan, destination):
    copied = unchanged = 0
    for relative, source in sorted(plan.items()):
        target = destination.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and not target.is_symlink() and same_content(source, target):
            unchanged += 1
            continue
        temporary = target.with_name(target.name + ".import-tmp")
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
        copied += 1
    return copied, unchanged


def in_prune_scope(relative):
    return relative in ROOT_FILES or relative.split("/", 1)[0] in PRUNABLE_ROOTS


def remove_empty_directories(destination):
    for root_name in sorted(PRUNABLE_ROOTS):
        root = destination / root_name
        if not root.is_dir():
            continue
        directories = sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            root.rmdir()
        except OSError:
            pass


def prune_extras(plan, destination, prune):
    extras = [
        relative
        for relative, _ in verify_artifacts.scan_tree(destination)
        if relative not in plan
    ]
    pruned = 0
    for relative in extras:
        if not prune:
            print(f"extra {relative}")
            continue
        if not in_prune_scope(relative):
            print(f"extra {relative} (outside prune scope, left in place)")
            continue
        print(f"prune {relative}")
        destination.joinpath(*PurePosixPath(relative).parts).unlink()
        pruned += 1
    if prune:
        remove_empty_directories(destination)
    return len(extras), pruned


def verify_destination(destination, lock_path):
    destination = destination.resolve()
    if not destination.is_dir():
        raise RebuildError(f"destination is not a directory: {destination}")
    if not lock_path.is_file():
        raise RebuildError(f"lock file not found: {lock_path} (pass --no-verify to skip)")
    lock = verify_artifacts.read_lock(lock_path)
    artifact = next(
        (entry for entry in lock["artifacts"] if entry["name"] == ARTIFACT_NAME), None
    )
    if artifact is None:
        raise RebuildError(f"lock has no artifact named {ARTIFACT_NAME}: {lock_path}")

    files, total, tree = verify_artifacts.tree_fingerprint(
        destination, verify_artifacts.scan_tree(destination)
    )
    expected_tree = artifact["treeSha256"].lower()
    if (files, total) == (artifact["files"], artifact["bytes"]) and tree == expected_tree:
        print(f"OK {ARTIFACT_NAME} files={files} bytes={total} treeSha256={tree}")
        return 0
    print(
        f"DRIFT {ARTIFACT_NAME}"
        f" files expected={artifact['files']} actual={files};"
        f" bytes expected={artifact['bytes']} actual={total};"
        f" treeSha256 expected={expected_tree} actual={tree}"
    )
    return 1


def reject_overlap(source, destination):
    source = source.resolve()
    destination = destination.resolve()
    if destination == source or destination.is_relative_to(source):
        raise RebuildError(
            f"destination {destination} must not be inside the source map root {source}"
        )
    if source.is_relative_to(destination):
        raise RebuildError(
            f"source {source} must not be inside the destination {destination}"
        )


def rebuild(source_root, args):
    reject_overlap(source_root, args.dest)
    plan = build_plan(source_root)
    print(f"plan source={source_root} files={len(plan)}")
    destination = args.dest.resolve()
    destination.mkdir(parents=True, exist_ok=True)

    copied, unchanged = copy_plan(plan, destination)
    extras, pruned = prune_extras(plan, destination, args.prune)
    print(f"copied={copied} unchanged={unchanged} pruned={pruned}")
    if extras and not args.prune:
        print(f"extras={extras} (rerun with --prune to remove them)")

    if args.no_verify:
        return 0
    return verify_destination(destination, args.lock)


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, f"ERROR: {message}\n")


def main(argv=None):
    repository = Path(__file__).resolve().parent.parent
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--dest", type=Path, default=repository / "artifacts" / ARTIFACT_NAME)
    parser.add_argument("--lock", type=Path, default=repository / "artifacts.lock.json")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-only", action="store_true")
    mode.add_argument("--no-verify", action="store_true")
    parser.add_argument("--prune", action="store_true")
    args = parser.parse_args(argv)

    if args.verify_only and args.prune:
        parser.error("--verify-only cannot be combined with --prune")
    if not args.verify_only and args.source is None:
        parser.error("--source is required unless --verify-only is used")

    try:
        if args.verify_only:
            return verify_destination(args.dest, args.lock)
        source = args.source
        if source.is_file():
            if source.suffix.lower() != ".rar":
                raise RebuildError(f"source file must be a .rar archive: {source}")
            with tempfile.TemporaryDirectory(prefix="trials-import-") as temporary:
                extracted = extract_archive(source, Path(temporary))
                return rebuild(resolve_map_root(extracted), args)
        if not source.is_dir():
            raise RebuildError(f"source does not exist or is not a directory: {source}")
        return rebuild(resolve_map_root(source), args)
    except (RebuildError, verify_artifacts.VerificationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"ERROR: filesystem operation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
