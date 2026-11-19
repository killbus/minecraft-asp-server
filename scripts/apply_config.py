#!/usr/bin/env python3
"""Render the tracked configuration tree into a server directory, and nothing else."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

from verify_runtime import (
    VerificationError,
    relative_path,
    require_text,
    safe_path,
    unique_json_object,
)

PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
VARIABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ENV_REFERENCE = "env:"

# Instance state is never written from the bundle. These paths are produced by
# the host while it runs, so a second host legitimately holds different bytes.
INSTANCE_TOP_PREFIXES = (
    "world/",
    "logs/",
    "cache/",
    ".paper/",
    "libraries/",
    "versions/",
    "packs/",
)
INSTANCE_PLUGIN_DIRS = (
    "data/",
    "players/",
    "skins/",
    "cache/",
    "tmp/",
    "logs/",
    "nethernet/",
    "locales/",
)
INSTANCE_SUFFIXES = (
    ".db",
    ".db-shm",
    ".db-wal",
    ".sqlite",
    ".sqlite3",
    ".player",
    ".playerskin",
    ".customskin",
    ".lock",
    ".log",
    ".7z",
    ".zip",
)
INSTANCE_BASENAMES = (
    "worlds.yml",
    "anchors.yml",
    "key.pem",
    ".license",
    "ops.json",
    "whitelist.json",
    "banned-ips.json",
    "banned-players.json",
    "usercache.json",
    "eula.txt",
    "start.cmd",
)


def classify(relative):
    """Return the class of a server-relative path: `source` or `instance`."""
    parts = PurePosixPath(relative).parts
    if not parts:
        return "instance"
    if f"{parts[0]}/" in INSTANCE_TOP_PREFIXES:
        return "instance"
    if parts[0] == "plugins":
        if len(parts) < 3:
            return "instance"
        inside = "/".join(parts[2:])
        for component in INSTANCE_PLUGIN_DIRS:
            if inside == component or inside.startswith(component):
                return "instance"
    basename = parts[-1]
    if basename in INSTANCE_BASENAMES or basename.endswith(INSTANCE_SUFFIXES):
        return "instance"
    return "source"


def read_manifest(path):
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise VerificationError(f"cannot read manifest {path}: {error}") from error
    try:
        manifest = json.loads(raw, object_pairs_hook=unique_json_object)
    except ValueError as error:
        raise VerificationError(f"manifest is not valid JSON: {error}") from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise VerificationError("manifest must hold a `files` list")
    entries = {}
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            raise VerificationError(f"manifest entry must be an object: {entry!r}")
        for key in ("path", "class", "sha256"):
            if key not in entry:
                raise VerificationError(f"manifest entry is missing {key!r}: {entry}")
        relative = relative_path(entry["path"], "manifest path")
        if relative in entries:
            raise VerificationError(f"manifest declares {relative} twice")
        specs = {}
        for placeholder in entry.get("placeholders", []) or []:
            if not isinstance(placeholder, dict):
                raise VerificationError(f"{relative}: a placeholder must be an object")
            name = require_text(placeholder.get("name"), "placeholder name")
            if name in specs:
                raise VerificationError(f"{relative} declares ${{{name}}} twice")
            default = placeholder.get("default")
            if default is not None and not isinstance(default, str):
                raise VerificationError(f"{relative}: default for {name} must be a string")
            specs[name] = default
        entries[relative] = {
            "path": relative,
            "class": require_text(entry["class"], "manifest class"),
            "sha256": require_text(entry["sha256"], "manifest sha256"),
            "placeholders": specs,
        }
    return entries


def fingerprint(path):
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise VerificationError(f"cannot read template {path}: {error}") from error
    return digest.hexdigest()


def read_values(assignments):
    values = {}
    for assignment in assignments:
        name, separator, value = assignment.partition("=")
        if not separator or not name:
            raise VerificationError(f"--set expects NAME=VALUE, got {assignment!r}")
        if name in values:
            raise VerificationError(f"--set names {name} twice")
        values[name] = value
    return values


def read_settings(path):
    """Read the per-host settings file.

    A settings file holds deployment coordinates - values that are per host,
    public, and worth reviewing in a diff. A credential is named as
    ``env:VARIABLE`` and resolved from the process environment, so the file
    stays safe to commit.
    """
    if path is None:
        return {}
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise VerificationError(f"cannot read settings {path}: {error}") from error
    try:
        settings = json.loads(raw, object_pairs_hook=unique_json_object)
    except ValueError as error:
        raise VerificationError(f"settings are not valid JSON: {error}") from error
    if not isinstance(settings, dict):
        raise VerificationError("settings must be a JSON object")
    unknown = sorted(set(settings) - {"schema_version", "values"})
    if unknown:
        raise VerificationError(f"settings hold an unknown key {unknown[0]!r}")
    if settings.get("schema_version") != 1:
        raise VerificationError("settings must declare schema_version 1")
    declared = settings.get("values")
    if not isinstance(declared, dict):
        raise VerificationError("settings must hold a `values` object")
    resolved = {}
    for name, value in declared.items():
        if not isinstance(value, str) or not value.strip():
            raise VerificationError(f"settings value {name} must be a nonblank string")
        if "${" in value:
            raise VerificationError(f"settings value {name} must not hold a placeholder")
        if value.startswith(ENV_REFERENCE):
            variable = value[len(ENV_REFERENCE):]
            if not VARIABLE.match(variable):
                raise VerificationError(
                    f"settings value {name} must be {ENV_REFERENCE}NAME, got {value!r}"
                )
            if variable not in os.environ:
                raise VerificationError(
                    f"settings value {name} needs {variable} in the environment"
                )
            resolved[name] = os.environ[variable]
        else:
            resolved[name] = value
    return resolved



# The frp entry point serves no plaintext http: a pack URL that a client follows
# across the network must be https://. Loopback (127.0.0.1 / localhost / ::1)
# never crosses the entry point, so it stays allowed as the local default.
PACK_URL_RULE = (
    r"^(?:"
    r"https://\S+"
    r"|"
    r"http://(?:127\.0\.0\.1|localhost|\[?::1\]?)(?::\d+)?(?:/\S*)?"
    r")$"
)

VALUE_RULES = {
    "PACK_URL": (
        PACK_URL_RULE,
        "must be https:// (the frp entry point serves no plaintext http); "
        "loopback (127.0.0.1/localhost/::1) stays allowed as the local default",
    ),
}


def resolve(name, values, default, settings):
    if name in values:
        value = values[name]
    elif name in settings:
        value = settings[name]
    elif name in os.environ:
        value = os.environ[name]
    elif default is not None:
        value = default
    else:
        value = None
    if value is None:
        raise VerificationError(
            f"no value for ${{{name}}}; pass --set {name}=VALUE or export {name}"
        )
    if "${" in value:
        raise VerificationError(
            f"value for {name} still contains a placeholder: {value!r}"
        )
    rule = VALUE_RULES.get(name)
    if rule is not None and not re.match(rule[0], value):
        raise VerificationError(f"value for {name} {rule[1]}: {value!r}")
    return value


def render(payload, relative, specs, values, settings):
    def replace(match):
        name = match.group(1)
        if name not in specs:
            raise VerificationError(
                f"{relative} uses ${{{name}}}, which the manifest does not declare"
            )
        value = resolve(name, values, specs[name], settings)
        return value

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise VerificationError(f"{relative} is not UTF-8: {error}") from error
    rendered = PLACEHOLDER.sub(replace, text)
    return rendered.encode("utf-8")


def plan(config_dir, server_dir, manifest, values, settings):
    """Return [(status, relative, destination, payload)] without writing anything."""
    root = Path(server_dir)
    if root.exists() and not root.is_dir():
        raise VerificationError(f"server directory is not a directory: {server_dir}")
    root = root.resolve()
    declared = {name for entry in manifest.values() for name in entry["placeholders"]}
    unknown = sorted(set(settings) - declared)
    if unknown:
        raise VerificationError(
            f"settings names {unknown[0]}, which no template declares"
        )
    results = []
    for relative, entry in manifest.items():
        if entry["class"] != "source":
            raise VerificationError(
                f"{relative} is classed {entry['class']!r}; only source may be applied"
            )
        if classify(relative) != "source":
            raise VerificationError(
                f"{relative} is instance state; it is never applied from the bundle"
            )
        template = safe_path(Path(config_dir).resolve(), relative)
        if not template.is_file():
            raise VerificationError(
                f"{relative} is in the manifest but missing from {config_dir}"
            )
        actual = fingerprint(template)
        if actual != entry["sha256"].lower():
            raise VerificationError(
                f"{relative} drifted from the manifest:"
                f" expected={entry['sha256'].lower()} actual={actual}"
            )
        destination = safe_path(root, relative)
        payload = render(
            template.read_bytes(), relative, entry["placeholders"], values, settings
        )
        if not destination.exists():
            results.append(("CREATE", relative, destination, payload))
        elif destination.is_file() and destination.read_bytes() == payload:
            results.append(("UNCHANGED", relative, destination, payload))
        else:
            results.append(("UPDATE", relative, destination, payload))

    declared = {str(entry["path"]) for entry in manifest.values()}
    for path in sorted(Path(config_dir).rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(config_dir).as_posix()
        if relative not in declared:
            raise VerificationError(
                f"{relative} is in {config_dir} but not in the manifest"
            )
    return results


def apply(results):
    for status, relative, destination, payload in results:
        if status == "UNCHANGED":
            continue
        temporary = destination.with_name(f"{destination.name}.tmp.{os.getpid()}")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(payload)
            os.replace(temporary, destination)
        except OSError as error:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise VerificationError(f"cannot write {relative}: {error}") from error


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, f"ERROR: {message}\n")


def main(argv=None):
    repository = Path(__file__).resolve().parent.parent
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, default=repository / "config")
    parser.add_argument("--lock", type=Path, default=repository / "config.lock.json")
    parser.add_argument("--server-dir", type=Path, default=repository / "server")
    parser.add_argument("--settings", type=Path, default=None)
    parser.add_argument("--set", dest="values", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        manifest = read_manifest(args.lock)
        settings = read_settings(args.settings)
        results = plan(
            args.config_dir,
            args.server_dir,
            manifest,
            read_values(args.values),
            settings,
        )
    except VerificationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if args.settings is not None:
        print(f"settings   {args.settings}")
    for status, relative, _, _ in results:
        print(f"{status:<9} {relative}")
    if args.check:
        return int(any(status != "UNCHANGED" for status, _, _, _ in results))
    if not args.dry_run:
        try:
            apply(results)
        except VerificationError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
