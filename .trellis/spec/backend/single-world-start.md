# Single-world startup and backup contract

## Scope and ownership

`scripts/start.sh` and `scripts/start.cmd` launch plain Paper 26.2 build 135
from the sibling `server/` directory. One process runs one primary native
save and its native dimensions. Paper owns native save state; launchers own
only argument validation, optional pack selection and invocation. Configuration
and plugin data are otherwise shared. No world registry, profile catalog, import, hot switch or plugin
configuration rewrite belongs here.

## Entry points

```text
scripts/start.sh [--world NAME]
scripts/start.cmd [--world NAME] [-pause]
scripts/backup.sh [SERVER_DIR]
scripts/backup.cmd [SERVER_DIR]
scripts/backup-debug.cmd [SERVER_DIR]
scripts/scenes/frpc.sh up (--config PATH | --scene FILE) [--world NAME] ...
scripts/scenes/frpc-shared-tcp.sh up (--config PATH | --scene FILE) [--world NAME] ...
```

Without selection, pass no world argument so `server.properties` remains
authoritative. Explicit `NAME` must match `[A-Za-z0-9_-]+` and refer to an
existing native save with a regular `server/NAME/level.dat` file. Refuse links
or junctions at the selected directory or marker. Refuse invalid arguments
before invoking Java (including its version probe) or backup. Unknown flags,
missing/empty names and duplicate selection exit `2`.

Forward selection as Paper's native `--world NAME`. Preserve Java exit status,
existing heap arguments, Windows `-pause`, `ASP_SKIP_BACKUP`, and the default
60-minute pre-start backup interval. Launchers never edit saves. Paper itself
persists resolved CLI properties, including `--world`, to its selected config
file; fake-Java fixture tests cannot establish otherwise.
Operators stop the previous process before calling a launcher.

Both optional scenes validate explicit selection before starting any sidecar
and forward the quoted argument to the same launcher. A plain scene with
`server = false` refuses selection unless `--defer-server` reserves the server
for composition. No argument preserves the previous default command exactly.

Capture CMD arguments with `%~1` inside the quoted `set` command; raw `%1`
retains outer quotes and can expose a quoted `&` as a command separator.
Distinguish an absent argument from an explicit empty argument. A flag-shaped
value such as `--world --help` is a literal save name: Paper's required string
argument consumes it, so it still requires the matching native save directory.

The marker is an existence check, not a complete-save validator. Never treat
a dimension-only artifact as a complete primary save or fabricate `level.dat`
to pass the check. Whole-save preparation and version compatibility are
operator responsibilities documented in `docs/SINGLE-WORLD-SOP.md`.

## Optional resource-pack policy

`settings/minecraft-server.json` is the fixed host contract. Both launchers invoke
`select_resource_pack.py` when it exists. `host_settings.py` owns shared schema
decoding with the deployment renderer; startup consumes only `resource_packs`
without resolving unrelated `values` env references or applying configs. Scenes
only forward the save name. Missing file or absent section keeps the prior native
config path; only a missing file avoids the Python requirement. An invalid or
unreadable document fails before Java/backup, never falling back silently.

The root schema has `schema_version: 1`, required `values` and optional
`resource_packs`. Its policy has exactly `default`, `worlds` (no nested version).
A descriptor is null
or exactly `{url, sha1}`. Null disables a pack; a missing named override inherits
the default. Validate all save names and descriptors, unknown fields, duplicate
JSON keys, HTTPS/loopback URLs and 40-hex digests. No environment interpolation,
remote fetching, file import, plugin configuration or save creation belongs here.

When the policy exists, deployment renders a neutral canonical PACK_URL and the
startup projection owns active selection. Without it, old PACK_URL deployment
behavior remains; startup does not re-render values. Reject any leftover
`settings/resource-packs.json` with migration guidance, whether or not the new
host file exists. Move its default/worlds under the host document resource_packs
and remove the redundant file manually. Do not auto-migrate or delete host data.

Explicit `--world` selects the policy key; otherwise decode `level-name` using
Java Properties semantics, defaulting to `world`. Decode strict UTF-8 with the
native Latin-1 fallback, continuations, escaping and last-definition behavior.
Backslash-only continuations must not turn comments or blank lines into keys;
literal non-BMP characters and their escaped surrogate pairs denote the same key.
Refuse invalid input rather than discarding unrelated properties.

Generate `.tmp/startup/server.properties` atomically from the canonical file,
overriding only native URL/SHA-1/ID and clearing deprecated `resource-pack-hash`.
Clear ID to let Paper derive its stable URL-based default. Preserve required,
prompt and unrelated keys. Never use a previous projection as the source.
Refuse links/junctions along controlled input/output paths, including a linked
settings directory whose policy is absent. An existing settings path must be a
directory; both launchers refuse an uninspectable path. `--check` is read-only.
Pass native `--config` with this projection; Paper's persistence stays in that
file. Management-API property writes to it are intentionally ephemeral. Host
settings backup already preserves the policy; generated files remain disposable.

The policy applies to a primary save and its native dimensions, not simultaneously
different resource packs per dimension. Configured SHA-1 avoids repeat network
download on a matching Java 26.2/26.3 cache; resource activation/reload on login
is separate and remains client behavior.

On Windows capture `SCRIPT_DIR` before argument shifts. CMD `SHIFT` changes `%0`,
so later `%~dp0` cannot reliably locate sibling scripts from arbitrary caller dirs.

### Policy signatures and validation

```text
python3 -B scripts/select_resource_pack.py [--world NAME] [--check]
```

The helper is scoped to its repository; no alternative policy or server paths
are accepted. Exit 0 reports a generated selection; exit 3 means valid native
fallback without a projection. Exit 2 reports refusal on stderr. `--check`
reports either valid selection with exit 0 and no writes. Launchers explicitly
handle exit 3 without a --config argument and never reuse stale output.
Normal no-policy startup validates host settings but does not inspect native
properties, preserving Paper's first-run creation and implicit native save names
outside the explicit `--world` grammar. `--check` may inspect those properties;
it accepts implicit native names and reports native defaults when the file is
absent. Explicit `--world` values retain validation on both paths.

| Input or event | Result |
| --- | --- |
| Missing host file or absent section | Native startup, no generated config argument |
| Legacy standalone file present | Migration error before Java/backup |
| Default descriptor, absent world override | Inherit descriptor |
| Named null override | Clear pack, SHA-1, ID and legacy hash |
| Unknown key, duplicate key, invalid name/URL/hash | Refuse before Java/backup |
| Linked/junction input or output | Refuse, no writes through the link |
| `--check` | Report only; never create output |
| Invalid Java property Unicode escape | Refuse instead of dropping config |
| Atomic replacement failure | Preserve previous output; remove own temp file |

Good: default null with a `trials` descriptor, so starting `world` clears the
pack from the projection. Base: absent policy preserves the existing native
configuration. Bad: retain a previous generated file's pack when selecting a
save with no override. Wrong: generate a random UUID on every startup. Correct:
keep the URL-derived native identity and supply the served file's SHA-1.

`test_resource_pack_selection.py` covers schema, selection transitions,
read-only checks, path safety, atomic failure, encoding/continuations/duplicates
and canonical file preservation. Launcher tests cover both platforms,
malformed policy before Java/backup, native argv and arbitrary caller
directories. Unified-host regressions cover startup with an unset unrelated
secret, section removal without stale output, legacy document compatibility,
and explicit migration failure for standalone policy files. Native smoke evidence is required before claiming actual Paper
property persistence behavior; fixture tests alone cannot establish it.

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

Host `settings/` enters snapshots except `*.example.json`; `SETTINGS_DIR`
overrides that source. Regenerable pack files remain excluded. Native saves
named `config`, `plugins` or `settings` collide with snapshot destinations and
are refused before any copy rather than being merged with unrelated state.

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
- `tests/test_single_world_scenes.py` covers selection forwarding, validation
  before tmux, default behavior, server-less refusal and TLS/PROXY/owned packs.

Native option support was inspected read-only in the available build's
`org.bukkit.craftbukkit.Main$1`: `w`, `world`, `level-name` share one required
string option. The local Paperclip JAR hash matched the pin. Fixture tests
and bytecode inspection do not establish live gameplay or production rollout.
