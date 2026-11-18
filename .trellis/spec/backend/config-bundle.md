# Configuration Bundle

> Executable contract for tracking `server/` configuration as source and
> applying it to a host.

---

## Scenario: Declarative server configuration lives in git

### 1. Scope / Trigger

This spec applies when changing:

- `config/`
- `config.lock.json`
- `scripts/apply_config.py`
- `tests/test_apply_config.py`
- the backup/snapshot descriptions in `docs/PAPER-WORLD-SOP.md` section 7
  and `docs/ASP-SOP.md` section 2a

It is triggered because the tree, the manifest, and the tool form one
contract: the manifest describes the tree, the tool refuses to drift from
the manifest, and the docs tell an operator which bytes may be copied.

`server/` stays gitignored. It is instance state plus downloaded binaries, and
it is never a commit target.

### 2. Signatures

```sh
python -B scripts/apply_config.py \
    [--config-dir config] [--lock config.lock.json] [--server-dir server] \
    [--set NAME=VALUE]... [--dry-run | --check]
```

Values resolve as: `--set` first, then the process environment, then the
manifest default, then refuse. `--dry-run` and `--check` are
mutually exclusive in effect; `--check` never writes.

### 3. Contracts

Manifest shape:

```json
{
  "schema_version": 1,
  "files": [{
    "path": "plugins/PackManagerPro/config.yml",
    "class": "source",
    "sha256": "<sha256 of the committed template>",
    "placeholders": [{ "name": "PACK_URL", "default": null }]
  }]
}
```

`path` is server-relative POSIX. `sha256` describes the template as
committed, placeholders and all. `default` is optional.

Class rule - would two hosts running the same world legitimately have
different bytes?

- no -> source: copied into `config/`, applied by the tool
- yes, the operator supplies it -> secret: a `${NAME}` placeholder
- yes, the host produced it by running -> instance: never bundled,
  never applied

The tool enforces `class == "source"` and independently re-derives the class
from the path via `apply_config.classify`. A manifest edit cannot smuggle
`worlds.yml`, `key.pem`, `*.db`, `playerdata`, caches, `logs/`, `nethernet/`,
`ops.json`, `whitelist.json`, `banned-*.json`, `usercache.json` or `eula.txt`
past it.

Apply contract:

1. every manifest entry's packed template must hash to `sha256` (else exit 2)
2. every `${NAME}` in a template must be declared for that file (else exit 2)
3. every declared placeholder must resolve a value (else exit 2)
4. no rendered value may contain `${` (else exit 2 sanity check)
5. destination = `safe_path(server_dir, path)` from `verify_runtime`
6. status is `CREATE`, `UPDATE`, or `UNCHANGED` from a byte comparison
7. a changed file is written to `<name>.tmp.<pid>` and `os.replace`d
8. any file in the tree absent from the manifest makes the run refuse

A `default` in the manifest is permitted only for a plugin-generated
telemetry identity (`FLOODGATE_METRICS_UUID`, `BSTATS_SERVER_UUID`): the value
carries no behaviour, so a fresh host may share it and an existing host is
not churned. A credential never gets a default.

Exit codes: `0` = applied (or `--check` clean), `1` = `--check` found a
difference, `2` = refused, nothing written. Errors go to stderr as
`ERROR: ...`, never as a traceback.

### 4. Validation & Error Matrix

| Condition | Result |
| --- | --- |
| Host matches the bundle | `UNCHANGED` per file, exit 0 |
| Destination absent | `CREATE`, exit 0 |
| Destination differs | `UPDATE`, exit 0 |
| Server dir absent | every entry `CREATE`, exit 0; `apply` creates the tree |
| Server path is a file | `ERROR: server directory is not a directory`, exit 2 |
| `--check` and anything differs | statuses printed, exit 1, no write |
| `--dry-run` | statuses printed, exit 0, no write |
| Template byte changed after the lock | `ERROR: ... drifted from the manifest`, exit 2 |
| Manifest path resolves to an instance path | `ERROR: ... is instance state`, exit 2 |
| `class` is not `source` | `ERROR: ... only source may be applied`, exit 2 |
| Template holds an undeclared `${NAME}` | `ERROR: ... which the manifest does not declare`, exit 2 |
| No value for a declared placeholder | `ERROR: no value for ${NAME}`, exit 2 |
| A value still holds `${` | `ERROR: ... still contains a placeholder`, exit 2 |
| File in the tree, absent from the manifest | `ERROR: ... not in the manifest`, exit 2 |
| Manifest entry, absent from the tree | `ERROR: ... missing from`, exit 2 |
| `..`, absolute path, or symlink escape | `ERROR`, exit 2 |
| Duplicate JSON key | `ERROR: duplicate JSON key`, exit 2 |

### 5. Good / Base / Bad Cases

- Good: `--check` on the live tree exits 0 with 28 `UNCHANGED` lines.
- Base: a fresh host gets 28 `CREATE` lines and needs `PACK_URL`,
  `GEYSER_ADVERTISE_ADDRESS` and `MANAGEMENT_SERVER_SECRET` supplied.
- Bad: adding `plugins/Multiverse-Core/worlds.yml` to `config/` so "the host
  gets the same worlds". Multiverse writes that file from the worlds it
  finds; a copied one declares worlds the host does not have and
  `join-destination: world` sends players to a missing destination.
- Bad: giving `PACK_URL` a default so the tool "just works". The default
  would point every host at one host's address.

### 6. Tests Required

- render, second-run `UNCHANGED`, `UPDATE` over a differing destination
- value from the environment; `--set` wins over the environment
- missing value, malformed `--set`, undeclared placeholder, value holding `${`
- `class: instance` refused; instance path refused even when class says source
- template hash drift refused before any write
- `--dry-run` and `--check` write nothing; `--check` exit 1 vs 0
- tree file absent from the manifest, and manifest entry absent from the tree
- `..` path never reaches the server dir; duplicate JSON key
- CRLF template keeps CRLF (server.properties is CRLF on this host)
- round-trip against a fixture `server/`, and against the live `server/` when present

### 7. Wrong vs Correct

Wrong:

```text
copy server/plugins/Multiverse-Core server/plugins/PackManagerPro ...
```

Correct:

```text
git pull
python -B scripts/apply_config.py --check
python -B scripts/apply_config.py --set PACK_URL=... --set GEYSER_ADVERTISE_ADDRESS=... --set MANAGEMENT_SERVER_SECRET=...
```

Wrong:

```python
destination.write_bytes(rendered)
```

Correct:

```python
temporary = destination.with_name(f"{destination.name}.tmp.{os.getpid()}")
temporary.write_bytes(payload)
os.replace(temporary, destination)
```

The first leaves a truncated config immediately after a crash or a full
disk; the second keeps the old file. Never "fix" a hash mismatch by
editing `config.lock.json` - the mismatch means the template changed under
the manifest, so re-derive the lock from the reviewed template.
