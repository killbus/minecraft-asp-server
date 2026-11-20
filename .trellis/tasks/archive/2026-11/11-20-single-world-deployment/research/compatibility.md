# Research: Single-world deployment compatibility

- Query: Which later main changes can be ported independently, how to replace PackManagerPro with native optional resource packs, how production scenes forward world selection, and which snapshot/config preservation contracts must survive.
- Scope: mixed; authoritative main snapshot, existing single-world code/spec, public Paper documentation.
- Date: 2026-11-20
- Source baseline: main `e1d12bf`, supplied by the parent as a read-only `git archive` extraction under `.tmp/main-deployment-source/`; single-world baseline `92aa420`. Source paths/line references below refer to that snapshot unless explicitly labeled single-world. No git operation, server launch, source change, or live-save access was performed by this researcher.

## Findings

### Commit boundaries and dependencies

The supplied `commit-history.txt` covers `4762a55..main`. These changes are useful deployment infrastructure, but not every entire commit is independent of the skipped Paper/Multiverse migration.

| Commit | Classification | Port treatment |
| --- | --- | --- |
| `fd822bf` | Backup/pack infrastructure with old world-layout assumptions | Retain pack/cache exclusions and serving wrappers. Preserve the single-world branch's discovery of every top-level native save instead of accepting the source's fixed `world/` copy. Preserve debug CMD delegation. Historical PAPER-WORLD-SOP additions need adaptation. |
| `fc210ef` | Independent shared-port pack routing | Bring `/packs/` routing and prefix-aware HTTP serving/tests; retain subsequent route fixes. Task/docs references may describe the former Trials deployment. |
| `0c436d7` | Mixed installer plus runtime inventory | Installer and tests are generic. Transfer pinned URLs for retained artifacts; never wholesale replace the lock with main's Multiverse-Core/PackManagerPro entries. |
| `c4496a9` | Mixed config infrastructure and plugin/content templates | Renderer/settings/tests are reusable. Exclude Multiverse-Core and PackManagerPro config entries/directories; retain PACK_URL under native server properties. Adapt docs/spec examples and historical tracked host settings. |
| `c3f1a7e` | Independent test scratch helper | Bring `tests/scratch.py` and config test usage. |
| `22ca771` | Independent test scratch migration with references to omitted tools | Bring changes for retained tests. Do not resurrect Trials importer/artifact tests merely to apply this commit mechanically. |
| `f274d4a` | Independent host settings protection | Keep ignore rule, example-only tracking, settings snapshot additions and tests; compose with all-save snapshots. |
| `785484e` | Independent packs sidecar ownership | Bring shared scene lifecycle ownership and server-prefix tests. Serving remains explicitly optional. |
| `0fcab06` | Independent HTTPS/route validation with PackManager-era settings | Preserve nonempty PACK_URL HTTPS rule, allow explicitly empty selection for the native renderer, update examples. |
| `640fd77` | Independent TLS routing fix | Preserve inspection of the decrypted request before selecting packs backend. |
| `8c74d5c` | Independent transport configuration fix | Keep Paper PROXY support and Geyser's outgoing PROXY header together, including config template hashes/tests. |
| `e1d12bf` | Independent TLS frontend/backend naming refactor | Bring scene/test/spec changes without changing transport behavior. |

`5d6ace4` is named by the PRD but is outside the supplied range; its exact contents were not independently inspected. `01cd4a1` is expressly excluded by the PRD. Main's supplied snapshot has neither WorldLifecycle nor Multiverse-Inventories: later root-worktree specs mentioning them are not authoritative for this port.

### Native resource-pack mapping

Main has `application-type: per-world` in `config/plugins/PackManagerPro/config.yml:2`; only `trials` consumes `${PACK_URL}` at line 23. Main native fields at `config/server.properties:58` already include optional-pack policy and empty URL/id/prompt/SHA1. For one active native save, set `resource-pack=${PACK_URL}`, retain `require-resource-pack=false`, remove PackManagerPro and Multiverse config/runtime records, and regenerate the changed template hash in `config.lock.json`. No registry or world-name mapping is needed.

Keep the key **PACK_URL**. `scripts/apply_config.py:282` derives accepted settings names from manifest declarations and rejects unknown settings keys. Renaming/dropping PACK_URL silently breaks existing host JSON even when the operator's URL remains valid. `GEYSER_ADVERTISE_ADDRESS` and the management-secret environment reference remain independent settings.

Recommended minimum empty-pack contract consistent with the PRD:

- PACK_URL stays a declared required placeholder with no default. An explicit `"PACK_URL": ""`, `--set PACK_URL=`, or empty resolved environment value means no offered pack; missing selection still fails clearly.
- Relax blank-string validation **only for an exactly empty PACK_URL**. Other blank settings and whitespace-only PACK_URL remain invalid. Retain settings schema, duplicate/unknown-key and unresolved-placeholder rejection.
- Apply existing HTTPS/loopback validation only when PACK_URL is nonempty (`scripts/apply_config.py:212`, `:229`). Preserve precedence: CLI > settings > environment > manifest default.
- A no-pack example should explicitly use the empty value, avoiding the currently supplied loopback `pack-a.zip` URL that assumes nonexistent pack content.
- Keeping native `resource-pack-id`, `resource-pack-prompt`, and `resource-pack-sha1` empty is a minimal port. SHA1 is recommended by Paper for verification; introducing a required new key is unnecessary for backward compatibility. No map-specific prompt should remain.

An omitted-PACK_URL/no-pack manifest default is an alternative, but it would change the current defaults contract (only telemetry identities get defaults). The explicit-empty design needs fewer policy changes.

`render()` at `scripts/apply_config.py:258` is raw textual substitution. Moving a value from YAML to Java properties requires care: reject CR/LF/control-character injection and preserve literal backslashes via appropriate property escaping or reject them in URL input. Apply properties encoding only to property placeholders; YAML values have different rules. Test final property value semantics, not merely whether `${PACK_URL}` disappeared.

The shared scene's `--serve-packs`/`--packs` switches are separate transport choices (`scripts/scenes/frpc-shared-tcp.sh:1187`). Config application need not start/stop a pack process or infer pack usage from the save name. Operators choosing no pack can omit both switches. When using a pack, the URL path, shared route prefix, and served directory must agree.

### World selection through production scenes

Both entrypoints hardcode `bash scripts/start.sh`: `scripts/scenes/frpc.sh:822` and `scripts/scenes/frpc-shared-tcp.sh:1479`. Direct launcher selection therefore does not reach production scene launches today.

Minimal addition: `up ... [--world NAME]` on both scripts. Parse once, reject duplicates/empty/unknown arguments with exit 2, validate the same ASCII name grammar and existing unlinked regular `server/NAME/level.dat` as single-world `scripts/start.sh:27` and `:44`, then use existing `quote_sh()` (`frpc.sh:147`, shared `:306`) to append the value to `_server_command`. The default command stays byte-identical. Validation should occur before tmux processes/config generation so an unusable save does not leave sidecars running.

The shared script reconstructs child `frpc.sh` positional arguments at `:1437`, invokes the deferred scene at `:1510`/`:1617`, and independently starts its final server command at `:1699`. Forwarding only to the child is insufficient: the shared wrapper must append the selection to **its own** final command. Passing the same explicit option to the deferred child also keeps its validation coherent. Do not introduce a scene-manifest world key or environment selection registry.

A plain manifest with `server=false` should reject explicit world selection unless `--defer-server` reserves a future server; silently accepting an ignored selection obscures operator intent. Shared topology must remain sidecars -> HAProxy -> optional pack backend readiness -> server. Dry-run output and real tmux invocation should agree on the final `--world` argument.

Useful fixture checks: both script entrypoints, legacy config and manifest modes, default command compatibility, selected command at final respawn, duplicate/missing/unsafe name refusal, absent/dimension-only/linked save refusal before any subprocess lifecycle, deferred and server=false behavior, and unchanged PROXY/TLS/pack ordering. Keep read/stop/reload verbs unchanged.

### Snapshot and configuration preservation

Main `scripts/backup.sh:178` and `scripts/backup.cmd:204` copy only `world/`; the single-world contract instead discovers every top-level save with `level.dat` and copies the complete tree, including native dimensions, datapacks and inactive saves. Retain that discovery and `session.lock`/`level.dat_old` exclusions. Main `backup-debug.cmd` is a duplicate old implementation; the target's delegation to `backup.cmd` must survive.

Settings are instance state: preserve `SETTINGS_DIR` resolution, snapshots under `settings/`, example exclusion, manifest hashing and COMPLETE semantics (`backup.sh:241`, `backup.cmd:234`). Snapshot restoration sends `settings/` back to the repository's host-settings directory on the same host, not into `server/`. Rendered configuration may contain resolved secrets even though settings contains only `env:...` references; existing snapshot access expectations continue to apply.

The source scripts copy **all files except `*.example.json`** from SETTINGS_DIR, despite comments saying `settings/*.json`; they therefore also include README and any unrelated files present. Either preserve this existing behavior explicitly or narrow it deliberately with tests; do not claim a JSON-only copy without checking implementation.

Two data-preservation issues deserve checks during adaptation:

1. `apply_config.classify()` guards literal `world/` (`scripts/apply_config.py:24`, `:71`), not every selected native save. A forged source manifest for `Adventure_A/level.dat` or another file below that root currently passes classification. Protect named native-save trees and nested player/save state before writes; unknown top-level configuration trees need a deliberate policy. Case aliases and symlinks must retain existing path safety.
2. A native save named `settings` is accepted by the current name grammar and would collide with the snapshot's host-settings destination. Fixed snapshot roots such as `plugins` and `config` raise similar conflicts. Do not silently merge or overwrite state in such a case; use a clear refusal or an explicitly documented reserved-name restriction if this edge case is addressed. Avoid imposing a new instance/profile layout merely for this port.

Installer scope is already enforced by shared `verify_runtime.read_lock()` at `scripts/verify_runtime.py:114`: one canonical server JAR, plugin JARs directly under plugins, and datapack ZIPs only in declared directories. The existing datapack scope remains `world/datapacks`; selecting another save does not install that datapack there. New installation must not delete undeclared plugin JARs automatically. Existing-host deployment must stop the server and deliberately remove/move old world-manager JARs after backup, because pruning manifest entries alone leaves them loadable by Paper.

### Files found and related specs

- `.tmp/main-deployment-source/commit-history.txt` — parent-supplied main commit/path provenance.
- `.tmp/main-deployment-source/scripts/install_runtime.py` — pinned download/hash/atomic-install implementation using verifier grammar.
- `.tmp/main-deployment-source/scripts/apply_config.py` — settings parsing, source classification, placeholder resolution and atomic writes.
- `.tmp/main-deployment-source/config.lock.json`, `runtime.lock.json` — declarations that must be filtered with their templates/artifacts.
- `.tmp/main-deployment-source/config/server.properties`, `config/plugins/PackManagerPro/config.yml` — native and plugin pack ownership before porting.
- `.tmp/main-deployment-source/settings/` — explicit host JSON schema, example and operator instructions.
- `.tmp/main-deployment-source/scripts/scenes/frpc.sh`, `frpc-shared-tcp.sh` — lifecycle, shared transport and final server command assembly.
- `.tmp/main-deployment-source/scripts/backup.sh`, `backup.cmd`, `backup-debug.cmd` — source snapshot behavior and host-settings additions.
- `.trellis/spec/backend/single-world-start.md` — target launcher/save/snapshot authority.
- `.tmp/main-deployment-source/.trellis/spec/backend/config-bundle.md` — manifest/source/settings/default contracts to adapt.
- `.tmp/main-deployment-source/.trellis/spec/backend/runtime-inventory.md` — shared lock grammar, pinning, install/verify statuses.
- `.tmp/main-deployment-source/.trellis/spec/backend/frpc-scenes.md` — optional scene boundaries, transport and lifecycle expectations.
- `.trellis/tasks/11-20-single-world-deployment/prd.md` — exact port exclusions and acceptance, read after the parent created it.

### External references

- Paper server.properties reference, retrieved 2026-11-20: https://docs.papermc.io/paper/reference/server-properties/ — `resource-pack` is the server pack URL; `require-resource-pack=false` makes acceptance optional; ID is a UUID; prompt is the download prompt; SHA1 is recommended for verification. Current online docs are rolling documentation, not proof of a live test on build 135.
- Pinned target runtime from source lock: Paper 26.2 build 135, SHA256 `ef3dbc68b013deafdbbee3bebf1ba351671ebcda94a8f136809b7532d5ba2fe1`. PackManagerPro 2.0.0 and Multiverse-Core 5.8.1 are source-main artifacts to exclude.

## Caveats / Not Found

- This is compatibility research, not completed implementation review. The parent and implementer were modifying the target worktree concurrently; authoritative source observations use the frozen main snapshot, not transient cherry-pick conflict markers.
- No network service, Minecraft runtime, player session, real pack download, or Bedrock resource-pack conversion was tested. Java native pack settings alone do not establish Bedrock pack compatibility.
- Main-history extraction did not include `5d6ace4`; exact per-commit patches were not available under this researcher's no-git scope. Classification uses commit path lists and the authoritative final source.
- Root-worktree WorldLifecycle/MVI/sidebar specs were encountered during initial discovery but excluded from conclusions after the parent supplied the clean main snapshot.
