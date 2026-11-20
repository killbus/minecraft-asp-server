# Research: MVI statistics and independent scoreboard behavior

- Query: Establish MVI 5.3.6 statistics/share API behavior and separate per-world player statistics from scoreboard persistence/presentation before adapting the single-server deployment.
- Scope: internal, with official source references; read-only MVI 5.3.6 source, Paper 26.2 implementation facts, and immutable Trials fixture.
- Date: 2026-11-20

## Findings

### Current requirement and conclusion

The user clarified during research that **all `game_statistics` following world/group profiles is the desired behavior**. The task is general and must not be implemented as a Trials-specific feature. Therefore changes to `DEATHS`, `LEAVE_GAME`, `TIME_SINCE_DEATH`, and other statistics during a group transition are expected consequences of the selected policy, not automatic grounds to reject it. Trials is a test fixture only.

Keep three contracts separate:

1. MVI owns saving/restoring the player's world/group statistics.
2. Scoreboard criteria and arbitrary gameplay scores determine how scoreboard values are produced. A statistic-backed display can project the selected statistic; `deathCount` and arbitrary dummy values are different state.
3. Presentation chooses what each viewer sees. A shared main scoreboard does not filter its rows or display slots by the viewer's world.

WorldLifecycle remains responsible for world lifecycle/entry timing. None of these findings calls for adding statistics or scoreboard management to it.

### 1. Built-in `GAME_STATISTICS` is all-statistics, not a configurable subset

At tag 5.3.6, commit `def55c476b16d2cb6f41c48c8498cb5eff9e6bd3`, `Sharables.java:820` defines one `Map`-valued `game_statistics` share. The update handler iterates `Statistic.values()` for untyped, item, block, and entity statistics, including typed material/entity values. The restore handler also iterates the entire set, restores stored integers, and uses zero for absent values (`Sharables.java:892`). It is marked optional at line 979.

No built-in configuration to select only `DEATHS` within that share was found in these handlers/config nodes. `game_statistics` is selected as one complete sharable. This matches the clarified requirement; a death-only replacement is unnecessary for that requirement.

`active-optional-shares` must include `game_statistics`. Worlds in a group share it only if that group's shares include it. An ungrouped world's own profile is used when `use-optionals-for-ungrouped-worlds` permits optional shares. The manual fixture's original config enabled only `last_location`; this research did not change it.

Missing destination data and preexisting global totals need a deliberate adoption policy. A previously global death total does not contain enough provenance to reconstruct how many deaths belonged to each world. New destination defaults must not be described as a historical split.

### 2. MVI public custom-share extension exists

This is an available extension mechanism, not a recommendation to narrow the user's statistics policy.

| API / implementation | Exact role |
| --- | --- |
| `share/Sharable.java:59`, public `Sharable.Builder<T>` | Defines name/type and a handler. |
| `share/SharableHandler.java` | `updateProfile(ProfileData, Player)` snapshots the player; `updatePlayer(Player, ProfileData)` restores it and returns whether an existing value was used. |
| `share/Sharable.java:125` | `defaultSerializer(ProfileEntry)` supports primitives/maps/lists accepted by persistence. |
| `share/Sharable.java:149` | `build()` constructs/registers the sharable and registers its profile entry. |
| `share/DefaultSharable.java:25` | Constructor invokes `Sharables.register`. |
| `share/ProfileEntry.java` | Defines persistent file tag; collision-free names are necessary. |
| `share/Sharables.java:1071` | Registers lookup aliases and standard/optional membership; optional activation remains separate. |
| `share/Sharables.java:1283` | Recalculates enabled shares from standard shares plus active optional configuration. |

A custom `Integer` share could read/write only Bukkit `Statistic.DEATHS`; a custom score share could snapshot a configured player score instead. Those represent different domains. If a score can be unset, its persistent schema must distinguish “unset” from zero rather than accidentally creating a score on restore. Fake-player/global objective values are not player profile data and are not automatically isolated by such a sharable.

Do not enable two handlers that own the same state unintentionally. For example, full `game_statistics` plus an independent DEATHS-stat sharable both restore `DEATHS`; ordering and authority would be ambiguous. A configured custom gameplay-score share may coexist only if it owns a distinct documented value.

### Registration and persistence timing

- MVI `onLoad` initializes logging/data directory only. `onEnable` initializes services, calls `Sharables.init`, loads config and groups, and immediately saves config (`MultiverseInventories.java:100`).
- Config deserialization uses `Sharables.fromList`; unknown sharable names are not resolved into a future deferred registration. Profile deserialization also ignores unknown `ProfileEntry` tags (`PlayerProfileJsonSerializer.java:80`).
- Consequently a dependent extension should register its custom share during its **`onLoad`**, before MVI's enable-time config/group/profile parsing, and validate activation/group policy when enabled. This is a source-backed lifecycle recommendation that still needs a fresh-start integration test; no extension was installed here.
- Registration after enable does not itself call `recalculateEnabledShares`. A late registration also risks earlier config serialization having dropped an unrecognized name. Avoid relying on hot reload as the normal bootstrap design.
- Optional shares must be activated explicitly. A group's explicit share list does not gain a newly registered share automatically. `Sharables.register` has special handling for already-enabled groups whose share collection equals all known sharables, but current explicit lists and the predefined `ALL_DEFAULT` group must not be assumed to acquire an extension share. Configure/test the intended group policy directly.
- Default serializer plus a unique non-stat profile entry (for example `ProfileEntry(false, <extension-key>)`) can persist a primitive without writing a parallel player database. This is an example of API shape, not a selected final key/schema.

### Event order and observation

`ShareHandleListener.java:209` handles `PlayerChangedWorldEvent` at LOW priority. `ShareHandler.java:52` performs:

1. Prepare affected profiles.
2. Fire the cancellable `ShareHandlingEvent`.
3. Capture a snapshot of enabled shares from the outgoing player state.
4. Restore destination values into the player synchronously through handlers.
5. Persist the captured source snapshot, potentially asynchronously.

Thus `ShareHandlingEvent` is **before** restoration, not a post-restore notification. A display adapter must not interpret that event as destination data already applied. Observing the outer world-change event after LOW (and respecting any other plugin interaction) can see restored state; durable write completion is a separate concern. The handler's returned future covers persistence but the world-change listener does not block awaiting it.

Join/quit behavior remains governed by MVI's existing native-save/load-on-login policy. Do not turn on `apply-playerdata-on-join` merely to refresh a display. Custom handlers would also run in existing read/write-only share transactions. Death event observation must account for Paper applying native death counters after the Bukkit death event; an immediate callback is not necessarily the final death total.

### 3. Statistic criteria versus score reset semantics

Previously verified actual Paper 26.2 bytecode shows that `CraftStatistic#setStatistic` sets the native statistic and then writes the same value to scoreboard objectives whose criterion matches that statistic. Therefore restoring `DEATHS` can project the active profile into an objective with criterion `minecraft.custom:minecraft.deaths`.

`deathCount` is a separate native criterion. MVI restoring Bukkit `DEATHS` does not make that criterion a per-world profile. Similarly, a dummy score is not captured by `game_statistics`.

Changing an objective from `deathCount` to a statistic criterion changes its synchronization contract:

- Actual deaths increment both systems, but restoring a statistic sets a matching statistic objective to the absolute profile value.
- A scoreboard `set` or `reset` modifies the score, not the underlying player statistic. A subsequent statistic restore may overwrite/recreate that independently modified score.
- A display intended to represent the player's actual profile statistic can appropriately use this projection. A gameplay counter with independent resets/checkpoints must not silently become that projection.
- Criteria on non-player/fake entries do not create a player-statistics source. MVI cannot restore a fake global total from a player's DEATHS value.
- Changing the source of an existing objective needs explicit migration of existing scores/attributes/display and initialization behavior; it is not an ordinary MVI setting. Objective metadata should not be silently repurposed by a generic display plugin.

For a general feature, prefer configuration that explicitly declares the intended source (statistic vs gameplay score), world/group display policy, and row membership. No objective named `Deaths` or world named `trials` should be hard-coded into a general implementation.

### 4. Existing display adapter feasibility

TAB's official scoreboard documentation already demonstrates per-world display conditions and configurable text/placeholder rows. This establishes configurable per-viewer presentation as an existing solution class. It does not demonstrate that TAB automatically adopts an arbitrary native objective or reads the required MVI profile values. A concrete statistic placeholder/provider and runtime version support would still need verification.

A narrow display adapter can read the player's current post-MVI statistic for a personal counter. A world/group leaderboard needs a stronger contract: select the correct set of players/profiles and read that world's value for every row, including offline players if required. Reading the shared main scoreboard's current values for everyone can mix players active in different worlds. This concern is independent of which map is used.

No scoreboard product was installed or selected here. Public custom-share APIs are available if independent gameplay-score persistence later becomes a requirement, but they are not required to enable full `game_statistics`.

## Trials Fixture Evidence

The narrow audit was completed before the user's clarification; it is retained as fixture evidence, not a design dependency. No further map-specific investigation was pursued after the scope correction.

Evidence files beside this report:

- `scan_death_objectives.py`: read-only scanner using the existing `.tmp/nbt.py` parser.
- `death-objective-command-evidence.json`: matching strings with region/chunk/NBT path/coordinate plus all extracted executable command-field values.

The scanner read **43,886 terrain chunks and 4,386 entity chunks**, with **zero decoding failures**. It extracted **1,137 command-field occurrences / 985 distinct strings**, excluding remembered `LastOutput` click-event commands from executable-command counts. It traversed nested NBT strings as well. No loose `.mcfunction`, `.zip`, or `.json` datapack files were found under the inspected imported artifact/source tree listing; this does not establish that other runtime datapacks cannot affect scores.

| Objective | Actual stored executable command uses |
| --- | --- |
| `Deaths` | One `objectives add Deaths deathCount` at `-1197 61 -138`; one `setdisplay sidebar Deaths` at `-1195 61 -138`. No explicit set/reset/operation/read selector involving this exact objective was found in scanned command fields. |
| `total_deaths` | One `objectives add total_deaths dummy` at `-1193 61 -138`; one `setdisplay list total_deaths` at `317 59 502`. No fake-player assignment, add, reset, operation, or transfer from `Deaths` was found. Its name alone does not prove a computed aggregate. |
| `join` | Two creates with `minecraft.custom:minecraft.leave_game`; five `@a[scores={join=1..}]` commands place redstone blocks; five `players reset @a[scores={join=1..}] join` commands. This is an actual command trigger, with independent score resets. |
| `respawn` | One `give @s[scores={respawn=1}] stone` at `-1203 61 -145`. The saved objective criterion is `minecraft.custom:minecraft.time_since_death`. The command's stored presence does not prove it is currently executable/reachable. |

The complete set of stored commands containing `scoreboard` also includes `scoreboard players reset @a death` (lowercase **`death`**, not `Deaths`) and creation of `con dummy`. No objective-unspecified `scoreboard players reset @a`, objective wildcard removal, or other generic reset appeared in that extracted set. This supports a narrowly bounded statement about the artifact; it is not proof of all future generated commands or external plugins' behavior.

Full-statistic transitions restoring `join`/`respawn` criteria are expected under the clarified policy. Whether a particular map's score-reset logic is compatible with that policy is a fixture observation, not justification to change the general requirement to death-only sharing.

## Files Found and References

- `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/share/Sharables.java:820`: full statistics handler; source fixed at tag 5.3.6.
- `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/share/Sharable.java:59`: public share builder and serialization contract.
- `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/config/InventoriesConfigNodes.java:88`: optional activation parser and enabled-share recalculation.
- `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/handleshare/ShareHandler.java:52`: event/snapshot/restore/persist order.
- `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/handleshare/WorldChangeShareHandler.java`: group versus world profile selection.
- `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/listeners/ShareHandleListener.java:209`: LOW-priority world changes; line 257 death handling; native-login policy earlier in the same file.
- `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/profile/PlayerProfileJsonSerializer.java`: custom tag serialization and unknown-tag behavior.
- https://github.com/Multiverse/Multiverse-Inventories/blob/def55c476b16d2cb6f41c48c8498cb5eff9e6bd3/src/main/java/org/mvplugins/multiverse/inventories/share/Sharables.java
- https://github.com/Multiverse/Multiverse-Inventories/blob/def55c476b16d2cb6f41c48c8498cb5eff9e6bd3/src/main/java/org/mvplugins/multiverse/inventories/share/Sharable.java
- https://github.com/NEZNAMY/TAB/wiki/Feature-guide:-Scoreboard

## Related Specs

- `.trellis/spec/backend/world-artifacts.md`: immutable inputs and shared native-state boundary.
- Earlier `scoreboard-world-scope.md` and `map-isolation-same-process.md`: runtime bytecode evidence and feature/compatibility distinctions.
- `.tmp/death-statistics-test/plan.md`: isolated validation ownership and acceptance criteria; the later user clarification in this report supersedes any inference that full-statistics behavior itself is unwanted.

## Caveats / Not Found

- Research did not touch runtime 25599, manual runtime 25598, real player data, artifacts, or product source/configuration.
- The research role's write boundary confines evidence to this task's `research/` directory, so scan evidence is colocated here rather than the requested optional `.tmp/death-statistics-test-research/` location.
- Custom-share registration/order guidance is based on source inspection, not a completed fresh-start extension test.
- Source scan is not a reachability proof or gameplay test, and cannot reconstruct per-world provenance of historical global scores.
- No new external search was necessary in this narrow follow-up; the report uses locally pinned source and previously verified official documentation.

## Follow-up: Native Online Activation, Reload, and First Profile Write

### Supported command

For MVI 5.3.6 the native command is:

```text
/mvinv toggle game_statistics
```

Omit the leading slash in the server console. The required permission is `multiverse.inventories.addshares`; the legacy alias `/mvinvtoggle game_statistics` also exists. This is a **toggle**, not an idempotent “enable” command. Confirm `game_statistics` is absent from the current optional list before invoking it once. Existing `last_location` remains in that set.

Source: `commands/InventoriesCommand.java:14` declares the `mvinv` root; `commands/ToggleCommand.java:36` declares `toggle`; lines 49–68 mutate the existing optional-share set, call `setActiveOptionalShares`, and save config.

### Immediate behavior, and why no reload is required

The command does not iterate online players, call a share-transfer handler, restore statistics, write player profiles, or manufacture per-world history. Its immediate mutation is configuration plus the enabled/applicable share sets:

1. Add `GAME_STATISTICS` to the existing optional set.
2. `InventoriesConfig#setActiveOptionalShares` invokes the config-node setter.
3. `InventoriesConfigNodes.java:108` calls `Sharables.recalculateEnabledShares`.
4. `Sharables.java:1283` rebuilds enabled shares and asks groups to recalculate applicable shares.
5. `ToggleCommand.java:68` saves configuration.

MVCore's actual setter (`config/handle/BaseConfigurationHandle.java:177`) invokes node callbacks even though ToggleCommand modified the same mutable set that was previously stored. There is no equality short-circuit in that inspected setter. Therefore a separate `/mvinv reload` or JVM restart is not required to make this optional share active, and a group already listing `game_statistics` becomes applicable immediately.

The command sends its “will now be considered” message before the save operation and does not inspect the returned setter/save `Try` values. A success chat message alone is not proof that the new config reached disk. Inspect the resulting config/logs, and have the isolated test verify restart persistence.

For an online player remaining in `world`, the source supports **no immediate restoration/reset caused by the toggle**. Naturally ticking statistics may still increase; compare deliberately stable fields rather than demand every counter's byte-for-byte equality across elapsed time.

### First world/group transition after activation

With the present policy (`world`, nether, end in `shared`; destination outside the group; `game_statistics` applicable; normal bypass settings), `WorldChangeShareHandler` and `ShareHandler` do this:

1. Capture all enabled current player values into an outgoing snapshot, including current native statistics.
2. Restore the destination world's/group's `game_statistics`.
3. Update source profiles from the captured snapshot and queue persistence.

For `world` → an ungrouped destination, the source group is written because the destination is outside it. With `always-write-world-profile=true`, the source world profile is also written. For a move within `shared`, group-owned `game_statistics` is already handled and is not replaced by an empty world profile; its live counters continue. These selection rules should be included in validation rather than inferred from UI alone.

If the destination profile exists but has no `game_statistics`, or if the profile does not exist, the built-in handler uses an empty map and restores zero for missing statistics. This is the **new profile default**. If destination statistics already exist, those stored values are restored instead. Activation does not prepopulate every world with the current counters.

`ShareHandler.java:62` captures the outgoing snapshot before `updatePlayer()` at line 63, so the source is not intended to receive the newly zeroed destination values. `ProfileDataSnapshot.java:39` merges selected captured shares into the existing source profile instead of clearing unrelated fields. That supports retaining known inventory/health/location fields during normal writes. The source `game_statistics` field itself, if previously stale, is replaced by current live values under the new active policy.

An online player who quits before changing worlds is handled by the existing `WriteOnlyShareHandler` (`ShareHandleListener.java:157–166`), which snapshots the now-enabled statistics into the current applicable world/group profiles. Normal plugin shutdown also uses write-only handling. No forced logout, forced switch, profile clone, or synthetic import is required merely to activate the setting.

### Historical-data limitation

The first source snapshot records the player's **current live aggregate counters as the baseline for the world/group occupied at that snapshot**. It does not know where earlier deaths or actions happened. Consequently:

- Activating while the player is in `world` does not immediately reset their live statistics.
- Their first source snapshot can preserve the current aggregate under `world`/`shared`.
- A different previously untracked destination starts with the defined empty-profile defaults.
- This is forward isolation with an adopted source baseline, **not reconstruction of historical per-world statistics**.

“Enable without editing player files by hand” is possible. “Enable and all future world changes leave every current statistic/history value unchanged” is incompatible with the desired per-world restore behavior. No historical split or migration guarantee should be implied.

### What `/mvinv reload` actually does

`commands/ReloadCommand.java:30` calls `MultiverseInventories#reloadConfig`. That method at lines 219–253:

- Loads the configuration and world groups.
- Clears profile-container and profile caches.
- Schedules first-run/group-conflict checks.

It does not enumerate online players or call `ReadOnlyShareHandler`, `WorldChangeShareHandler`, or `WriteOnlyShareHandler`. Thus reload itself is not a first-activation snapshot, an online-player restore, or a guaranteed pending-write flush. The direct toggle is narrower and avoids unnecessary cache invalidation. Editing YAML then using `/mvinv reload` is a separate supported reload path but adds no migration guarantee.

### Facts still requiring isolated runtime verification

Source inspection establishes the intended command path, but cannot certify the current real player's history or success of filesystem writes. Before applying to the manual session, the disposable test should verify:

- One toggle retains `last_location`, enables `game_statistics`, and does not immediately restore stable statistics for an online player.
- First outgoing world/group writes contain the pre-transition baseline, while a missing destination defaults as documented; returning restores the baseline.
- Existing known non-statistics profile values remain correct, and transitions within the same group do not reset group statistics.
- Config and profiles persist across quit/rejoin and restart, with no write errors or pending-operation races observed.

No claim of crash-atomic capture is made: source profile writes are asynchronous, and this review did not test process termination during first transfer. This follow-up did not invoke any command on manual runtime 25598 or read/change Snorlax's player-state contents.

Additional exact-source references:

- https://github.com/Multiverse/Multiverse-Inventories/blob/def55c476b16d2cb6f41c48c8498cb5eff9e6bd3/src/main/java/org/mvplugins/multiverse/inventories/commands/ToggleCommand.java
- https://github.com/Multiverse/Multiverse-Inventories/blob/def55c476b16d2cb6f41c48c8498cb5eff9e6bd3/src/main/java/org/mvplugins/multiverse/inventories/MultiverseInventories.java
- https://github.com/Multiverse/Multiverse-Inventories/blob/def55c476b16d2cb6f41c48c8498cb5eff9e6bd3/src/main/java/org/mvplugins/multiverse/inventories/handleshare/ShareHandler.java
- https://github.com/Multiverse/Multiverse-Inventories/blob/def55c476b16d2cb6f41c48c8498cb5eff9e6bd3/src/main/java/org/mvplugins/multiverse/inventories/handleshare/WorldChangeShareHandler.java
