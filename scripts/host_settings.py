"""Decode host settings without resolving credentials or applying configuration."""

import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from verify_runtime import VerificationError, require_text, unique_json_object

VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
ENV_REFERENCE = "env:"
WORLD_NAME = re.compile(r"[A-Za-z0-9_-]+")
SHA1 = re.compile(r"[0-9a-fA-F]{40}")


def require_world(value):
    if not isinstance(value, str) or not WORLD_NAME.fullmatch(value):
        raise VerificationError("world name must use ASCII letters, digits, _ or -")
    return value


def validate_pack_url(value):
    if value == "":
        return
    valid = False
    try:
        parsed = urlsplit(value)
        valid = (
            not any(character.isspace() or ord(character) < 32 or ord(character) == 127
                    for character in value)
            and "\\" not in parsed.netloc
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and (parsed.port is None or 0 < parsed.port <= 65535)
            and (parsed.scheme == "https" or (
                parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            ))
        )
    except ValueError:
        pass
    if not valid:
        raise VerificationError(
            "value for PACK_URL must be https:// with a host, loopback http://, "
            "or an explicit empty string for no pack"
        )


def validate_resource_packs(policy):
    if not isinstance(policy, dict) or set(policy) != {"default", "worlds"}:
        raise VerificationError("resource_packs must contain exactly default and worlds")
    if not isinstance(policy["worlds"], dict):
        raise VerificationError("resource_packs worlds must be an object")
    for name in policy["worlds"]:
        require_world(name)
    for label, descriptor in [("default", policy["default"]), *policy["worlds"].items()]:
        if descriptor is None:
            continue
        if not isinstance(descriptor, dict) or set(descriptor) != {"url", "sha1"}:
            raise VerificationError(f"resource_packs {label}: use null or exactly url and sha1")
        url = require_text(descriptor["url"], f"resource_packs {label} url")
        if "${" in url or "<" in url or ">" in url:
            raise VerificationError(f"resource_packs {label} url must not contain a placeholder")
        validate_pack_url(url)
        digest = descriptor["sha1"]
        if not isinstance(digest, str) or not SHA1.fullmatch(digest):
            raise VerificationError(f"resource_packs {label} sha1 must contain 40 hexadecimal characters")
        descriptor["sha1"] = digest.lower()


def read_host_settings(path):
    if path is None:
        return {"schema_version": 1, "values": {}}
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise VerificationError(f"cannot read settings {path}: {error}") from error
    except UnicodeError as error:
        raise VerificationError("settings must use UTF-8") from error
    try:
        settings = json.loads(raw, object_pairs_hook=unique_json_object)
    except ValueError as error:
        raise VerificationError(f"settings are not valid JSON: {error}") from error
    if not isinstance(settings, dict):
        raise VerificationError("settings must be a JSON object")
    unknown = sorted(set(settings) - {"schema_version", "values", "resource_packs", "backup"})
    if unknown:
        raise VerificationError(f"settings hold an unknown key {unknown[0]!r}")
    if type(settings.get("schema_version")) is not int or settings["schema_version"] != 1:
        raise VerificationError("settings must declare schema_version 1 as an integer")
    declared = settings.get("values")
    if not isinstance(declared, dict):
        raise VerificationError("settings must hold a `values` object")
    for name, value in declared.items():
        if not VARIABLE.fullmatch(name):
            raise VerificationError("settings values keys must be placeholder names")
        if not isinstance(value, str) or (
            not value.strip() and not (name == "PACK_URL" and value == "")
        ):
            raise VerificationError(f"settings value {name} must be a nonblank string")
        if "${" in value:
            raise VerificationError(f"settings value {name} must not hold a placeholder")
        if value.startswith(ENV_REFERENCE) and not VARIABLE.fullmatch(value[len(ENV_REFERENCE):]):
            raise VerificationError(f"settings value {name} must be {ENV_REFERENCE}NAME")
    if "resource_packs" in settings:
        validate_resource_packs(settings["resource_packs"])
    if "backup" in settings:
        backup = settings["backup"]
        if not isinstance(backup, dict) or set(backup) != {"targets"}:
            raise VerificationError("backup must contain exactly targets")
        if not isinstance(backup["targets"], list) or not backup["targets"]:
            raise VerificationError("backup targets must be a nonempty array")
        for target in backup["targets"]:
            require_text(target, "backup target")
            if any(ord(character) == 127 for character in target):
                raise VerificationError("backup targets must not contain control characters")
            if target.startswith("env:") or "${" in target:
                raise VerificationError("backup targets must be literal paths, not environment references")
    return settings
