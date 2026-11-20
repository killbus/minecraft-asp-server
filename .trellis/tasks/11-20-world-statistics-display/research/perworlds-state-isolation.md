# Research: PerWorlds player-state and command-isolation boundaries

- Query: Does TheNextLvl-net/per-worlds provide configurable world-group player-state persistence, complete statistics isolation, native scoreboard/selector isolation, or protection from later cross-world game-mode commands?
- Scope: Mixed; upstream source inspected locally, release metadata supplied by the parent researcher. No installation or live-state mutation.
- Date: 2026-11-20
- Source: `.tmp/thenextlvl-per-worlds`, commit `3645aafac4a9196ff3846edad8a7427eb8a8ff20`.
- Release baseline: `1.6.3`, tag commit `5134bdc371acbe54da8b1f47a691a7c9194886da`. Parent verified that HEAD differs from this tag only in ten build/workflow files; the relevant Java logic is identical. The target Modrinth artifact declares Paper 26.1.2/26.2, not 26.3. This is distinct from the similarly numbered MC 1.21.11 variant. Worlds is optional; the source's Folia support declaration is commented out.

## Findings

### 1. PerWorlds implements real group-profile persistence

This candidate supplies a player-state owner comparable in purpose to Multiverse-Inventories. It should not be rejected merely because the separate Worlds plugin does not supply these features.

- `listener/TeleportListener.java:19`: a noncancelled cross-world teleport at MONITOR resolves the source/destination groups and persists the outgoing profile only when the groups differ.
- `listener/TeleportListener.java:27`: `PlayerChangedWorldEvent` at LOWEST loads the destination profile when the groups differ. Same-group transitions intentionally share current state.
- `listener/ConnectionListener.java:19`: join loads the current group's profile with position enabled; quit at line 26 persists it. Teleport intent and cold-world implications are covered by the parent investigation.
- `group/PaperWorldGroup.java:60`: each group owns a folder and NBT configuration. Player records use `<group>/<uuid>.dat`, with `<uuid>.dat_old` backups (`:261`, `:299`). A write moves the prior record to its backup and attempts backup restoration if writing fails.
- `group/PaperWorldGroup.java:469`: persistence snapshots `PaperPlayerData.of(player, this)`.
- `model/PaperPlayerData.java:154`: the snapshot includes inventory, ender chest, game mode, health, food, experience, effects, attributes, statistics, advancements, recipes, respawn/death locations, and other player properties. Loading applies these fields at `:293` onward.

First adoption has an explicit migration condition. `PaperWorldGroup.java:329` refuses a missing-profile load when no migration group is configured, logs instructions, and returns false. At `:361`, migration preserves a player's current state in the designated source group when needed and constructs default state for another destination. This must be configured before treating an existing installation as isolated. MVI importer behavior is outside this report and is examined separately by the parent.

Fixed-source references:

- [Teleport save/load events](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/listener/TeleportListener.java#L19)
- [Join/quit profile handling](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/listener/ConnectionListener.java#L19)
- [NBT persistence and first-adoption condition](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/group/PaperWorldGroup.java#L299)
- [Profile application](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/model/PaperPlayerData.java#L293)

### 2. Group sharing and disabled-field semantics differ from this project's MVI configuration

`PaperUnownedWorldGroup.java:15` creates a single group named `unowned`; its `containsWorld` at line 48 accepts every world lacking an explicit group. Therefore all unassigned worlds share one fallback profile scope. This project's MVI policy instead isolates ungrouped worlds. Explicit distinct groups are required to reproduce that topology.

`PaperGroupSettings.java:31` and `:45` enable inventory and statistics by default, among many configurable fields. A disabled field does not generally mean that the existing value carries unchanged across groups:

| Setting | Observed profile-load behavior |
| --- | --- |
| `inventory=false` | `PaperPlayerData.java:307` applies the default empty inventory. |
| `enderChest=false` | Line 308 applies the default ender chest. |
| `statistics=false` | Lines 373/390 clear all statistics and restore no saved values. |
| `gameMode=false` | Lines 297/298 apply the group/server default game mode. |
| `health=false` | Uses default health, constrained by the effective maximum health. |

Sharing follows group membership; toggling these fields cannot be assumed equivalent to disabling an MVI sharable. A candidate migration must compare these semantics explicitly.

- [Single unowned group](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/group/PaperUnownedWorldGroup.java#L15)
- [Group defaults](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/group/PaperGroupSettings.java#L31)
- [Disabled-field application](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/model/PaperPlayerData.java#L297)

### 3. All statistics categories are intended, but sparse typed-stat restoration has a source-derived defect risk

`PaperStatistics.java:99` iterates `Registry.STATISTIC`, covering UNTYPED, ITEM, BLOCK, and ENTITY categories. The snapshot at `PaperPlayerData.java:177` uses it. This is broad statistics support, not only deaths.

However, the persisted restore path has a mismatch:

1. `TypedStatAdapter.java:17` serializes only nonzero material/entity values.
2. `StatisticsAdapter.java:48` stores only statistics with data. Typed deserializers such as `BlockTypeStatAdapter.java:26` restore only the keys actually present; absent zero-valued subtypes are not populated.
3. `PaperSubstatistic.java:38` defines `hasData` as any nonzero subtype value. `PaperStatistics.java:89` forwards that result.
4. `PaperPlayerData.java:392` skips clearing an entire statistic when its destination record has data.
5. `PaperPlayerData.java:375` then restores only the destination's stored subtypes. For blocks, `PaperBlockTypeStat.java:21` simply traverses its values map.

Concrete counterexample derived from these branches: the current source state has `MINE_BLOCK/stone=10`. The persisted destination contains only `MINE_BLOCK/dirt=2`, because its stone count was zero. The destination has data for `MINE_BLOCK`, so clearing that entire statistic is skipped; only dirt is assigned. The source stone count can survive at 10 instead of becoming 0.

This risk applies to sparse ITEM/BLOCK/ENTITY subtype maps. An entirely absent statistic is cleared; a scalar UNTYPED statistic does not have this partial-subtype problem. This is a source-derived defect hypothesis, **not a runtime reproduction**. Full statistics isolation should not be described as verified until a persisted cross-group test exercises zero/nonzero subtype combinations.

- [Complete category snapshot](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/model/PaperStatistics.java#L99)
- [Sparse serialization](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/adapter/statistic/TypedStatAdapter.java#L14)
- [Sparse deserialization](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/adapter/statistic/BlockTypeStatAdapter.java#L26)
- [Any-nonzero presence check](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/model/PaperSubstatistic.java#L38)
- [Restore and clearing logic](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/model/PaperPlayerData.java#L373)

### 4. Profile swapping does not isolate later map commands or the native scoreboard

Searches over plugin/API source for `scoreboard`, `Scoreboard`, `ServerCommandEvent`, `CommandPreprocess`, `CommandBlock`, `EntitySelector`, and `PlayerGameMode` found no corresponding interception or persistence implementation.

`PerWorldsPlugin.java:163` registers Chat, Connection, Message, Plugin, Respawn, Teleport, and World listeners. No `PlayerGameModeChangeEvent` listener is registered. `PaperPlayerData.java:297` restores game mode during loading, but a later command such as `gamemode adventure @a` can still change players in other worlds. The altered active state may subsequently be saved into its profile.

The profile's `score` field maps to `player.setDeathScreenScore` (`PaperPlayerData.java:315`). It is the death-screen scalar, not arbitrary native scoreboard objectives, scores, teams, or fake players. No native global scoreboard replacement, command-source namespace, or selector-scope adapter was found.

Thus PerWorlds addresses state replacement on group transitions. It does not provide a sandbox for commands running after that transition. Native `clear @a`, teleport, game-mode, scoreboard and similar map commands still need their own compatibility policy.

- [Registered listeners](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/PerWorldsPlugin.java#L163)
- [Game mode and death-screen score fields](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/model/PaperPlayerData.java#L297)

### 5. Additional audience isolation is implemented, with specific boundaries

- `listener/ChatListener.java:19` filters other-group players from `AsyncChatEvent.viewers()` when enabled. It does not intercept arbitrary native `/tellraw` or `/title` commands.
- `listener/MessageListener.java:36` handles advancement, death, join, and quit event messages. Its group audience calculation and replacement messages are actual functionality, conditional on configuration; they are not a generic command-output firewall.
- `PaperPlayerData.java:412` updates tab-list visibility with `listPlayer`/`unlistPlayer` according to group and settings. This presentation behavior does not change native selector membership.
- `listener/WorldListener.java` persists players/group state on save, applies group world state on load, and synchronizes enabled difficulty, rules, time/weather, and world-border changes within a group. Group synchronization does not block command effects originating elsewhere.

- [Chat audience filter](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/listener/ChatListener.java#L19)
- [Event-message filtering](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/listener/MessageListener.java#L36)
- [Tab-list visibility](https://github.com/TheNextLvl-net/per-worlds/blob/3645aafac4a9196ff3846edad8a7427eb8a8ff20/plugin/src/main/java/net/thenextlvl/perworlds/model/PaperPlayerData.java#L412)

## Files found

All upstream paths below are relative to `.tmp/thenextlvl-per-worlds/plugin/src/main/java/net/thenextlvl/perworlds/`.

| File | Responsibility |
| --- | --- |
| `listener/TeleportListener.java` | Cross-group outgoing save and destination restore. |
| `listener/ConnectionListener.java` | Join/quit profile lifecycle. |
| `group/PaperWorldGroup.java` | NBT files, backups, load guards, initial adoption, persistence. |
| `group/PaperUnownedWorldGroup.java` | Shared fallback group for all unassigned worlds. |
| `group/PaperGroupSettings.java` | Per-group feature defaults/options. |
| `model/PaperPlayerData.java` | Profile snapshot/application and tab-list update. |
| `model/PaperStatistics.java` | Registry-wide statistics capture and presence check. |
| `model/PaperSubstatistic.java` | Nonzero-data semantics for typed statistics. |
| `model/PaperBlockTypeStat.java` | Iteration of stored block subtype counters. |
| `adapter/statistic/TypedStatAdapter.java` | Sparse subtype serialization. |
| `adapter/statistic/StatisticsAdapter.java` | Statistic-record serialization and dispatch. |
| `adapter/statistic/BlockTypeStatAdapter.java` | Sparse block-stat deserialization. |
| `listener/ChatListener.java` | Group-aware chat audience. |
| `listener/MessageListener.java` | Selected lifecycle/event-message audiences. |
| `listener/WorldListener.java` | Group world-property synchronization. |
| `PerWorldsPlugin.java` | Runtime listener/service registration. |

## Related specs

- `.trellis/spec/backend/multiverse-player-state.md`: current MVI ownership, ungrouped isolation, complete statistics, adoption and validation requirements. PerWorlds is a candidate replacement owner, not an additional owner to enable alongside MVI.
- `.trellis/spec/backend/statistics-sidebar.md`: presentation remains distinct from native objective and arbitrary map-command isolation.
- `.trellis/spec/backend/world-artifacts.md`: Paper's native main scoreboard and imported map-command scope remain server-wide unless a separate mechanism changes them.
- `research/trials-command-scope-audit.md`: concrete command categories demonstrating why profile restoration alone does not contain concurrently running imported maps.
- `research/thenextlvl-worlds-source.md`: separate Worlds plugin's responsibilities; do not conflate it with PerWorlds profile management.

## Caveats / Not Found

- No PerWorlds runtime test, installation, migration, or production change occurred in this research.
- The sparse-stat issue is established by the inspected data/branch flow, but has not been reproduced against a running server or filed upstream.
- Release/tag comparison and Modrinth metadata were supplied by the parent researcher; fixed source links above reference the inspected HEAD whose relevant Java matches release 1.6.3.
- No Paper 26.3 declaration was established for the targeted PerWorlds artifact. A declaration for another plugin or artifact is not transferable.
- Teleport-coordinate intent, cold world loading, native saved-world login, MVI importer completeness, and plugin replacement/dependency compatibility are covered by the parent's complementary investigation.
- A second profile manager must not be enabled on the live server merely to test this candidate; its writes and transition listeners would compete with MVI.
