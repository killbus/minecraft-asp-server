#!/usr/bin/env python3
"""Select the startup save's native resource pack without changing host properties."""

import argparse
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

from host_settings import read_host_settings, require_world
from verify_runtime import VerificationError

REPOSITORY = Path(__file__).absolute().parents[1]
WHITESPACE = " \t\f"


def checked_path(root, relative):
    path = root
    for component in (None, *Path(relative).parts):
        if component is not None:
            path = path / component
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or (
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise VerificationError(f"links and junctions are not allowed: {path}")
    return path


def logical_lines(text):
    pending = ""
    continuing = False
    lines = re.split(r"\r\n|\r|\n", text)
    for index, natural in enumerate(lines):
        if index == len(lines) - 1 and not natural:
            break
        natural = natural.lstrip(WHITESPACE)
        if not pending and (not natural or natural.startswith(("#", "!"))):
            continuing = False
            continue
        pending += natural
        backslashes = len(pending) - len(pending.rstrip("\\"))
        continuing = backslashes % 2 == 1
        if continuing:
            pending = pending[:-1]
        else:
            yield pending
            pending = ""
    if continuing:
        yield pending


def unescape_property(value):
    result = []
    offset = 0
    escapes = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}
    while offset < len(value):
        character = value[offset]
        offset += 1
        if character == "\\":
            if offset == len(value):
                break
            character = value[offset]
            offset += 1
            if character == "u":
                digits = value[offset:offset + 4]
                if not re.fullmatch(r"[0-9a-fA-F]{4}", digits):
                    raise VerificationError("server.properties contains a malformed Unicode escape")
                character = chr(int(digits, 16))
                offset += 4
            else:
                character = escapes.get(character, character)
        result.append(character)
    return "".join(result).encode("utf-16-be", errors="surrogatepass").decode("utf-16-be", errors="surrogatepass")


def read_properties(path):
    payload = path.read_bytes()
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        text = payload.decode("iso-8859-1")
    properties = {}
    for line in logical_lines(text):
        offset = 0
        escaped = False
        while offset < len(line):
            character = line[offset]
            if not escaped and character in WHITESPACE + "=:":
                break
            escaped = character == "\\" and not escaped
            offset += 1
        raw_key = line[:offset]
        separator = line[offset:offset + 1]
        offset += bool(separator)
        if separator in WHITESPACE:
            while offset < len(line) and line[offset] in WHITESPACE:
                offset += 1
            if line[offset:offset + 1] in ("=", ":"):
                offset += 1
        while offset < len(line) and line[offset] in WHITESPACE:
            offset += 1
        properties[unescape_property(raw_key)] = unescape_property(line[offset:])
    return properties


def escape_property(value):
    result = []
    escapes = {"\t": "\\t", "\n": "\\n", "\r": "\\r", "\f": "\\f"}
    for character in value:
        if character in escapes:
            result.append(escapes[character])
        elif character in "\\ =:#!":
            result.append("\\" + character)
        elif 32 <= ord(character) <= 126:
            result.append(character)
        else:
            encoded = character.encode("utf-16-be", errors="surrogatepass")
            result.extend(f"\\u{int.from_bytes(encoded[offset:offset + 2], 'big'):04x}"
                          for offset in range(0, len(encoded), 2))
    return "".join(result)


def write_properties(root, properties):
    output = checked_path(root, ".tmp/startup/server.properties")
    if output.exists() and not output.is_file():
        raise VerificationError(f"generated properties target must be a regular file: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(f"{escape_property(key)}={escape_property(value)}\n"
                      for key, value in properties.items())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", newline="\n",
                                         prefix="server.properties.", dir=output.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
        checked_path(root, ".tmp/startup/server.properties")
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return output


def select(root, world=None, check=False):
    if world is not None:
        require_world(world)
    settings_dir = checked_path(root, "settings")
    if settings_dir.exists() and not settings_dir.is_dir():
        raise VerificationError(f"settings must be a directory: {settings_dir}")
    legacy_path = checked_path(root, "settings/resource-packs.json")
    if legacy_path.exists():
        raise VerificationError(
            "settings/resource-packs.json is no longer supported; move its default and worlds "
            "into resource_packs in settings/minecraft-server.json, then remove the old file after review"
        )
    settings_path = checked_path(root, "settings/minecraft-server.json")
    policy = None
    if settings_path.exists():
        if not settings_path.is_file():
            raise VerificationError(f"host settings must be a regular file: {settings_path}")
        policy = read_host_settings(settings_path).get("resource_packs")
    native_source = "native server.properties (no pack policy)"
    if policy is None and not check:
        return world, native_source, {}, None
    properties_path = checked_path(root, "server/server.properties")
    if not properties_path.exists() and policy is None:
        properties = {}
    elif not properties_path.is_file():
        raise VerificationError(f"native properties file is missing or not a regular file: {properties_path}")
    else:
        properties = read_properties(properties_path)
    selected_world = world if world is not None else properties.get("level-name", "world")
    if policy is None:
        source = native_source
        output = None
    else:
        require_world(selected_world)
        source = f"worlds.{selected_world}" if selected_world in policy["worlds"] else "default"
        descriptor = policy["worlds"].get(selected_world, policy["default"])
        properties["resource-pack"] = descriptor["url"] if descriptor else ""
        properties["resource-pack-sha1"] = descriptor["sha1"] if descriptor else ""
        properties["resource-pack-id"] = ""
        properties["resource-pack-hash"] = ""
        output = checked_path(root, ".tmp/startup/server.properties")
        if not check:
            write_properties(root, properties)
    return selected_world, source, properties, output


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise VerificationError(message)


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--world", help="explicit startup save; otherwise use native level-name")
    parser.add_argument("--check", action="store_true", help="show effective selection without writing")
    try:
        args = parser.parse_args(argv)
        world, source, properties, output = select(REPOSITORY, args.world, args.check)
        print(f"world      {world if world is not None else '(native level-name)'}")
        print(f"source     {source}")
        if args.check or output is not None:
            print(f"url        {properties.get('resource-pack', '') or '(none)'}")
            print(f"sha1       {properties.get('resource-pack-sha1', '') or '(none)'}")
        if output is not None:
            print(f"properties {output}" + (" (not written)" if args.check else ""))
    except (VerificationError, OSError, UnicodeError, ValueError) as error:
        print(f"ERROR: resource-pack selection failed: {error}", file=sys.stderr)
        return 2
    return 0 if args.check or output is not None else 3


if __name__ == "__main__":
    sys.exit(main())
