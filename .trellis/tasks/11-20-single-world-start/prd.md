# Single-process primary world selection

## Authorization and boundary

On 2026-11-20 the user authorized freezing the Multiverse work and creating a new branch from the commit before Multiverse was introduced. The requested replacement is startup selection of one world, with one server process and no in-process multi-map manager or multi-instance orchestration.

Branch: `feat/single-world-start`. Base: `10c794e25981e8d5625dbcc9655b79db572d4b30`, the parent of `01cd4a1` which introduced both Paper and Multiverse. The base still launches ASP. Retain the plain Paper engine needed for native Anvil saves, without the Multiverse/Slime integration. Historical networking remains at the base revision; do not merge unrelated later deployment changes.

## Behavior gap and owner

The start scripts hardcode the server JAR and cannot choose a primary save. Pass a validated explicit `--world NAME` to Paper's native CLI. Stop the process before choosing another save. Each selected save owns native player data, statistics, advancements, scoreboard and dimensions; server configuration and plugins remain shared. This is not per-map plugin-data isolation. Normal Nether/End dimensions remain part of the selected game's world family.

## Acceptance

- `scripts/start.sh --world NAME` and `scripts/start.cmd --world NAME` launch Paper with the selected primary save. Preserve Windows `-pause` behavior. No argument preserves the normal server.properties default behavior.
- Explicit names are simple relative directory basenames, using ASCII letters, digits, underscores and hyphens. Reject missing arguments, unknown flags, traversal and absolute paths before backup or Java launch. Explicit selection requires an existing `server/NAME/level.dat`, avoiding accidental empty-map creation on typos. No additional create/import command.
- Do not rename, move, overwrite or symlink existing saves; do not silently import a dimension-only Multiverse folder as a complete primary save. Document preparing a full native save separately.
- Keep the runtime lock and verifier consistent with Paper and no ASP plugin. Use the already verified Paper 26.2 build135 artifact: sha256 `ef3dbc68b013deafdbbee3bebf1ba351671ebcda94a8f136809b7532d5ba2fe1`, URL `https://fill-data.papermc.io/v1/objects/ef3dbc68b013deafdbbee3bebf1ba351671ebcda94a8f136809b7532d5ba2fe1/paper-26.2-135.jar`.
- Existing backups must cover inactive as well as active top-level native saves (directories containing `level.dat`), preserve names and exclude runtime artifacts as before. Avoid a separate registry/config framework. Keep shell/CMD/debug backup entrypoints consistent and detect the Paper process for offline snapshots. No destructive runtime migration.
- Add focused executable script tests for argument propagation, invalid input, default behavior, and backup coverage of two named saves while excluding unrelated directories. Use `.tmp/` for fixtures. Verify the existing runtime suite. Native CLI support should be verified against the available Paper JAR/source; do not claim live gameplay verification from mocked launch tests.
- Document concise stop/select/start usage and native data ownership. One process runs one selected primary save; no hot switching, MVI, WL, scoreboard adapter, proxy migration, engine selector, profile catalog or automatic plugin/config rewriting.

## Expected files

`scripts/start.sh`, `scripts/start.cmd`, `scripts/backup.sh`, `scripts/backup.cmd`, `scripts/backup-debug.cmd`, `runtime.lock.json`, `scripts/verify_runtime.py`, focused tests, `docs/SINGLE-WORLD-SOP.md`, a historical notice in `docs/ASP-SOP.md`, and an executable startup spec/index entry. Only touch runtime verifier behavior if its hardcoded ASP assumption actually requires it.

## Preservation

Implementation occurs in this isolated worktree. The root checkout, its `server/`, all `.tmp/world-lifecycle-manual` state, immutable artifacts and sibling lifecycle repository are not implementation targets. Do not start/stop the existing server. No remote push is authorized.
