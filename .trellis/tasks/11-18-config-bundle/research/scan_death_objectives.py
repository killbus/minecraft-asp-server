import collections
import gzip
import importlib.util
import json
import pathlib
import re
import struct
import sys
import zlib


sys.dont_write_bytecode = True
repository = pathlib.Path(__file__).resolve().parents[4]
parser_path = repository / ".tmp" / "nbt.py"
parser_spec = importlib.util.spec_from_file_location("research_nbt", parser_path)
parser = importlib.util.module_from_spec(parser_spec)
parser_spec.loader.exec_module(parser)
artifact = repository / "artifacts" / "trials-legacy"
objective_pattern = re.compile(r"(?<![A-Za-z0-9_])(Deaths|total_deaths|join|respawn)(?![A-Za-z0-9_])")
hits = []
commands = []
command_counts = collections.Counter()
failures = []
scanned = collections.Counter()


def inspect(value, file_path, chunk_index, parent_path="", position=None):
    if isinstance(value, dict):
        if all(axis in value for axis in ("x", "y", "z")):
            position = [value[axis] for axis in ("x", "y", "z")]
        elif isinstance(value.get("Pos"), list):
            position = value["Pos"]
        for key, child in value.items():
            inspect(child, file_path, chunk_index, parent_path + "/" + key, position)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, (str, list, dict)):
                inspect(child, file_path, chunk_index, parent_path + "/" + str(index), position)
    elif isinstance(value, str):
        command_field = parent_path.rsplit("/", 1)[-1] in ("Command", "command") and "/LastOutput/" not in parent_path
        if command_field:
            command_counts[value] += 1
            commands.append({"file": str(file_path.relative_to(artifact)), "chunk_index": chunk_index,
                             "position": position, "nbt_path": parent_path, "text": value})
        if objective_pattern.search(value):
            hits.append({"file": str(file_path.relative_to(artifact)), "chunk_index": chunk_index,
                         "position": position, "nbt_path": parent_path, "text": value,
                         "is_command_field": command_field})


for region_kind in ("region", "entities"):
    for region_path in sorted((artifact / region_kind).glob("*.mca")):
        raw = region_path.read_bytes()
        for chunk_index in range(1024):
            offset = int.from_bytes(raw[chunk_index * 4:chunk_index * 4 + 3], "big") * 4096
            if not offset:
                continue
            scanned[region_kind] += 1
            length = struct.unpack(">I", raw[offset:offset + 4])[0]
            compression = raw[offset + 4]
            payload = raw[offset + 5:offset + 4 + length]
            try:
                if compression == 2:
                    uncompressed = zlib.decompress(payload)
                elif compression == 1:
                    uncompressed = gzip.decompress(payload)
                elif compression == 3:
                    uncompressed = payload
                else:
                    raise ValueError(f"Unsupported compression {compression}")
                if b"Command" not in uncompressed and not any(token.encode() in uncompressed for token in ("Deaths", "total_deaths", "join", "respawn")):
                    continue
                (_, root), end = parser.parse(uncompressed)
                inspect(root, region_path, chunk_index)
            except Exception as error:
                failures.append({"file": str(region_path), "chunk_index": chunk_index, "error": str(error)})

report = {"artifact": str(artifact), "scanned_chunks": dict(scanned), "failures": failures,
          "total_command_occurrences": sum(command_counts.values()), "unique_commands": len(command_counts),
          "matching_strings": hits,
          "all_commands": commands,
          "matching_command_counts": {command: count for command, count in command_counts.items() if objective_pattern.search(command)},
          "scoreboard_command_counts": {command: count for command, count in command_counts.items() if "scoreboard" in command.lower()}}
destination = pathlib.Path(__file__).with_name("death-objective-command-evidence.json")
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in report.items() if key not in ("matching_strings", "all_commands")}, ensure_ascii=False, indent=2))
