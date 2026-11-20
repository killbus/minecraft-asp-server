# Research: MVI and WorldLifecycle runtime adoption

- Query: What is the smallest truthful runtime/configuration/backup integration for the validated generic per-world player-state stack?
- Scope: mixed; repository contracts, local source/evidence and one read-only public release lookup.
- Date: 2026-11-20

## Findings

### 1. Add runtime declarations without extending the installer

The existing lock already supports missing artifacts without a download URL.
`scripts/install_runtime.py:66` checks a present file's SHA-256 first, then
returns `MANUAL` with its `source` when the file is absent and no
`download_url` exists. `scripts/install_runtime.py:152` returns exit 1 for
unresolved MANUAL entries. A correctly supplied file becomes OK on rerun.
`scripts/verify_runtime.py:112` requires source to be an absolute HTTP(S)
URL; a filesystem path is not a valid source value. These contracts require
no new local-path field, build command execution or URL fallback.

Recommended artifact declarations:

| Field | MVI | WorldLifecycle |
| --- | --- | --- |
| id | `multiverse-inventories` | `multiverse-worldlifecycle` |
| kind | `plugin` | `plugin` |
| path | `plugins/Multiverse-Inventories-5.3.6.jar` | `plugins/Multiverse-WorldLifecycle-0.1.0.jar` |
| version | `5.3.6` | `0.1.0` |
| source | `https://modrinth.com/plugin/multiverse-inventories` | `https://github.com/killbus/Multiverse-WorldLifecycle` |
| download_url | `https://cdn.modrinth.com/data/qvdtDX3s/versions/86s1EwyC/multiverse-inventories-5.3.6.jar` | omit |
| sha256 | `6e58e89009283f4be8658abe2b7e46c482010ceccf3c8e0b0e8ca6a0a114ff92` | `2f362ee692b00078de108b4aeb5a2b580f1bfa36eead71b6e7f779bc7217d108` |

Both local artifact SHA-256 values were recalculated during this research.
MVI's local SHA-512 also matches the saved official release metadata. The
metadata lists Minecraft 26.2 and 26.3; WorldLifecycle's README limits its
native-save adapter to 26.2, so the complete deployment remains 26.2 only.

Read-only GitHub API request to
`https://api.github.com/repos/killbus/Multiverse-WorldLifecycle/releases`
returned HTTP 200 and `[]` on this date. Therefore there is no published
release asset to claim in the lock. This does not establish whether every
local source file is publicly available. The parent independently confirmed
the sibling repository origin; the source URL is a project reference, not
proof that public HEAD reproduces this binary.

The verified local artifact is at
`.tmp/worldlifecycle-extraction/project/build/libs/Multiverse-WorldLifecycle-0.1.0.jar`.
The sibling README documents `./gradlew clean build` and the same output
basename. Deployment documentation should explain manual transfer/build,
the required hash, and a subsequent verifier run. Do not promise that a
future source checkout necessarily recreates the old hash. Do not publish a
release or place the local JAR in git as part of this task.

`runtime.lock.json` currently says every artifact has a download URL; revise
that note when adding this deliberate MANUAL artifact. The old prototype
must not coexist with the formal plugin. The formal plugin data directory
is `plugins/MultiverseWorldLifecycle/`, independent of the JAR basename.

### 2. MVI policy is source; group topology and profiles are host state

The full tested configuration is
`.tmp/world-lifecycle-manual/runtime/plugins/Multiverse-Inventories/config.yml`.
Its important policy values are:

```yaml
share-handling:
  enable-bypass-permissions: false
  enable-gamemode-share-handling: false
  default-ungrouped-worlds: false
  use-optionals-for-ungrouped-worlds: true
  active-optional-shares:
    - last_location
    - game_statistics
sharables:
  reset-last-location-on-death: false
  apply-last-location-for-all-teleports: false
  use-byte-serialization-for-inventory-data: false
performance:
  apply-playerdata-on-join: false
  always-write-world-profile: true
first-run: false
version: 5.0
```

Use the complete generated configuration as the template baseline if the
bundle aims to compare complete files. Avoid changing unrelated options
such as byte serialization during adoption.

`first-run` has a consequential bootstrap behavior. At
`.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/MultiverseInventories.java:246`,
a scheduled first-run action creates a group when none exists, then saves
`first-run: false`. Actual
`profile/group/AbstractWorldGroupManager.java:151` adds the default world
and its loaded `_nether` and `_the_end` worlds with `Sharables.allOf()`.
The interface Javadoc saying all loaded worlds is stale; the implementation
does not do that. ALL nevertheless includes `last_location`, which conflicts
with the intended per-world location policy.

Recommended declared baseline: `first-run: false`, no bundled groups file,
and explicit native group setup during host bootstrap. A fresh deployment
therefore starts with independent ungrouped worlds until an administrator
creates the desired group. To share the base dimensions, use MVI's native
group commands to include those dimensions and all desired shares except
`last_location`. Existing groups survive config application and must be
reviewed rather than overwritten. Optional `game_statistics` activation
and group applicability are separate requirements.

Protect these exact MVI paths as instance state:

- `plugins/Multiverse-Inventories/groups.yml`
- `plugins/Multiverse-Inventories/playernames.json`
- `plugins/Multiverse-Inventories/players/**`
- `plugins/Multiverse-Inventories/worlds/**`
- `plugins/Multiverse-Inventories/groups/**`

`scripts/apply_config.py:74` currently catches `players/` but wrongly
classifies the other paths above as source. Add a plugin-specific rule;
do not classify every file called `groups.yml` across arbitrary plugins.
The group manager itself recommends native commands and writes group
configuration: `profile/group/YamlWorldGroupManager.java:38`, `:62`, `:258`.

### 3. First adoption preserves evidence, not invented history

`.tmp/death-statistics-test/final-report.md:59` records zero defaults for a
missing destination statistics profile. Its activation experiment at `:75`
also covers an existing profile lacking the `game_statistics` field.
The online toggle does not immediately change current stats or profiles;
the next transition snapshots the outgoing live values and restores the
destination. Previous global totals become the source context baseline,
and cannot be retrospectively split into historical world totals.

The source restoration implementation at
`.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/share/Sharables.java:885`
iterates statistics and uses zero for missing values; typed statistics use
`getOrDefault(..., 0)` at `:920`, `:942`, `:964`. Existing profile data must
remain untouched by the deployment tooling. Do not clone records, force
`loadOnLogin`, or clear profiles to make new tests pass.

### 4. Managed world configuration needs a single owner

The sibling README and the inspected extracted artifact agree on these
distributed defaults:

```yaml
managed-worlds: []
idle-seconds: 60
request-timeout-seconds: 30
login-prepare-timeout-seconds: 30
login-completion-timeout-seconds: 60
```

The empty list is intentional. Worlds must already be registered and have
valid data. Neither installation nor config application should assume a
world called `trials` exists. Only the configured managed worlds are idly
unloaded; saved-world login and player entry can load other registered
worlds. The default world is never idly unloaded. Set Multiverse-Core
`auto-load` per host using its native commands. Plugin hot reload is not
supported.

There are two coherent integration contracts:

1. Smallest: leave `plugins/MultiverseWorldLifecycle/config.yml` outside the
   bundle. The plugin creates its empty default; the host owns edits before
   restart and snapshots retain them. Document this explicit ownership
   exception, and protect that exact path from accidental bundle adoption.
2. If this config is bundle-owned, use an explicit host settings input for
   the list. A literal empty-list template plus instructions to edit the
   rendered file is inconsistent: the next apply removes those host edits.
   The existing settings values are strings, so a JSON-flow-list placeholder
   would require bounded parsing/validation rather than trusting arbitrary
   YAML fragments. The settings example must be empty and no host world
   list may be invented as a manifest default.

The first option avoids adding a list-serialization feature solely for this
plugin. The second matches existing declarative-settings ownership. This
research does not select a new owner without the main-session decision.

Also update the existing tracked Multiverse-Core join policy if formal
WorldLifecycle adoption is selected: the old SOP section 7a and tracked
config force the hub destination, which conflicts with native saved-world
login. Keep explicit entry intent and MVI global teleport rewriting disabled.

### 5. Backup already covers the new state

`scripts/backup.sh:214` and `scripts/backup.cmd:220` recursively copy every
plugin data directory except JARs and two explicitly named regenerable
caches. Therefore all MVI player/group/world profiles, its groups.yml and
playernames.json, and formal WorldLifecycle configuration are already
included. Host settings are included at `backup.sh:241` / `backup.cmd:234`.
The entire native `world/` tree is also included.

Do not add a second backup command or broaden exclusions. Add fixture
coverage proving these files survive into the snapshot and its manifest,
while plugin JARs stay excluded. Restore native player data and MVI profiles
from the same stopped-server snapshot to avoid mixing state generations.
No backup or production restoration was run by this research.

### 6. Minimal implementation and verification list

- Runtime lock: add two pinned artifacts and correct the all-downloadable
  note; retain existing MANUAL semantics.
- Config bundle: add tested MVI policy and corresponding template hash;
  choose one explicit WorldLifecycle config owner; preserve host group state.
- Classifier: guard MVI groups.yml/playernames.json/groups/worlds paths.
- Documentation: dependency/build transfer instructions, fresh group
  bootstrap, first-stat activation behavior, saved-world login, lifecycle
  config ownership and whole-snapshot restore boundary.
- Tests: classification and malicious-manifest refusal for those paths;
  apply twice leaves instance records byte-identical; settings/list tests
  only if that path is chosen; runtime MANUAL/OK/hash behavior already has
  baseline tests; snapshot fixture asserts MVI/WL files and manifest hashes.
- Runtime acceptance: retain previously proven 45 statistics checks and 30
  lifecycle checks; add integration checks only for changed contract paths.

## Files Found

- `runtime.lock.json`: current deployment inventory, lacks MVI and WL.
- `scripts/install_runtime.py`: verified-download writer with MANUAL support.
- `scripts/verify_runtime.py`: shared lock grammar, hashing and scope checks.
- `scripts/apply_config.py`: declarative renderer and instance-path barrier.
- `tests/test_install_runtime.py:155`: existing URL-less MANUAL regression.
- `tests/test_apply_config.py:466`: source/instance classification matrix.
- `tests/test_backup_settings.py`: existing stopped fixture snapshot tests.
- `docs/PAPER-WORLD-SOP.md:357`: whole-snapshot and rollback contract.
- `.tmp/mvi-5.3.6-release.json`: captured official release URL/hashes/support.
- `.tmp/worldlifecycle-extraction/artifact.json`: verified formal plugin metadata.
- `.tmp/death-statistics-test/final-report.md`: five-JVM, 45-check evidence.
- `.tmp/world-lifecycle-manual-running.md`: preserved user test environment.
- `D:/Repositories/Multiverse-WorldLifecycle/README.md`: independent build,
  compatibility, lifecycle/configuration and installation contract.

## Related Specs

- `.trellis/spec/backend/runtime-inventory.md`
- `.trellis/spec/backend/config-bundle.md`
- `.trellis/spec/backend/multiverse-player-state.md`
- `.trellis/spec/backend/world-artifacts.md`

## External References

- MVI version: `https://modrinth.com/plugin/multiverse-inventories/version/86s1EwyC`
- MVI documentation: `https://mvplugins.org/inventories/`
- MVI source: `https://github.com/Multiverse/Multiverse-Inventories`
- WL project: `https://github.com/killbus/Multiverse-WorldLifecycle`
- WL release-list observation: `https://api.github.com/repos/killbus/Multiverse-WorldLifecycle/releases`

## Caveats / Not Found

- No public WL release asset was available; no public-source build was run.
- No source, runtime, player file, production host or git state was changed.
- MVI 26.3 support does not establish WL or complete-stack 26.3 support.
- This integration does not isolate native scoreboards; display ownership is
  the separate main task, and should not be added to WorldLifecycle.
