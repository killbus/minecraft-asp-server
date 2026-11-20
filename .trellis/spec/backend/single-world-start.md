# Single-world startup and backup contract

## Scope and ownership

`scripts/start.sh` and `scripts/start.cmd` launch plain Paper 26.2 build 135
from the sibling `server/` directory. One process runs one primary native
save and its native dimensions. Paper owns native save state; launchers own
only argument validation and invocation. Configuration and plugin data are
shared. No world registry, profile catalog, import, hot switch or plugin
configuration rewrite belongs here.

## Entry points

```text
scripts/start.sh [--world NAME]
scripts/start.cmd [--world NAME] [-pause]
scripts/backup.sh [SERVER_DIR]
scripts/backup.cmd [SERVER_DIR]
scripts/backup-debug.cmd [SERVER_DIR]
```

Without selection, pass no world argument so `server.properties` remains
authoritative. Explicit `NAME` must match `[A-Za-z0-9_-]+` and refer to an
existing native save with a regular `server/NAME/level.dat` file. Refuse links
or junctions at the selected directory or marker. Refuse invalid arguments
before invoking Java (including its version probe) or backup. Unknown flags,
missing/empty names and duplicate selection exit `2`.

Forward selection as Paper's native `--world NAME`. Preserve Java exit status,
existing heap arguments, Windows `-pause`, `ASP_SKIP_BACKUP`, and the default
60-minute pre-start backup interval. Selection never edits saves or properties.
Operators stop the previous process before calling a launcher.

Capture CMD arguments with `%~1` inside the quoted `set` command; raw `%1`
retains outer quotes and can expose a quoted `&` as a command separator.
Distinguish an absent argument from an explicit empty argument. A flag-shaped
value such as `--world --help` is a literal save name: Paper's required string
argument consumes it, so it still requires the matching native save directory.

The marker is an existence check, not a complete-save validator. Never treat
a dimension-only artifact as a complete primary save or fabricate `level.dat`
to pass the check. Whole-save preparation and version compatibility are
operator responsibilities documented in `docs/SINGLE-WORLD-SOP.md`.

## Runtime and snapshots

The only canonical server path in `runtime.lock.json` and `verify_runtime.py`
is `paper-server.jar`. ASP has no server/plugin entry. Preserve the verifier's
path/hash/error handling and flag leftover undeclared artifacts normally.
The existing `world/datapacks` lock remains scoped to that directory; selection
does not install datapacks into another save.

All backup entrypoints discover top-level directories containing `level.dat`
without consulting selection or a registry. Copy each complete tree under its
original name, active or inactive. Preserve configuration/plugin-data scope,
manifest/completion/retention semantics and regenerable cache exclusions.
Exclude `session.lock` and `level.dat_old` throughout save trees. Detect
`paper-server.jar` in the offline preflight. The debug CMD delegates to the
normal CMD implementation so it cannot drift.

## Executable checks

`tests/test_single_world_scripts.py` runs the real shell/CMD entrypoints with
stand-in Java/process probes and isolated fixtures under `.tmp/`. Verify:

- Explicit names reach Java in the correct working directory; default startup
  has no override; selected files and `server.properties` stay byte-identical.
- Invalid names, absent saves and dimension-only directories launch neither
  Java nor backup. Linked saves and markers are refused. Quoted CMD separators
  remain data and cannot bypass validation. Windows pause ordering and Java
  exit propagation survive.
- Two named saves, nested world state, datapacks and sibling dimensions enter
  snapshots; unrelated directories, runtime files and known caches do not.
- Manifests hash every copied file; online Paper detection refuses snapshots.
- `tests/test_verify_runtime.py` still passes with the Paper canonical path.

Native option support was inspected read-only in the available build's
`org.bukkit.craftbukkit.Main$1`: `w`, `world`, `level-name` share one required
string option. The local Paperclip JAR hash matched the pin. Fixture tests
and bytecode inspection do not establish live gameplay or production rollout.
