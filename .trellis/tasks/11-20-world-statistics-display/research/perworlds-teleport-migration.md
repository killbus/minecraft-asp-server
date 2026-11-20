# PerWorlds: teleport intent, lifecycle, and migration review

Date: 2026-11-20. Public metadata and source review only; no candidate plugin was installed, no importer was executed, and the manual test server was not changed.

## Evidence scope

- Repository: https://github.com/TheNextLvl-net/per-worlds
- Local shallow clone: `.tmp/thenextlvl-per-worlds`.
- Inspected HEAD: `3645aafac4a9196ff3846edad8a7427eb8a8ff20`.
- Fetched release `1.6.3`: `5134bdc371acbe54da8b1f47a691a7c9194886da`.
- `git diff --stat 1.6.3 HEAD` contains only ten build, wrapper, and workflow files. The Java behavior reviewed here is unchanged between that release and HEAD.
- Modrinth project: https://api.modrinth.com/v2/project/lpfQmSV2
- Release metadata: https://api.modrinth.com/v2/project/lpfQmSV2/version
- Complementary state/statistics review: [perworlds-state-isolation.md](perworlds-state-isolation.md).

## Role and compatibility

The README explicitly describes PerWorlds as an alternative to Multiverse-Inventories. Worlds plus PerWorlds is therefore a meaningful same-author candidate for the world-management and player-profile layers currently covered by Multiverse-Core plus Multiverse-Inventories.

`plugin/build.gradle.kts` declares Worlds as an optional server dependency (`required = false`). PerWorlds can be evaluated independently of replacing the world manager. This does not mean that two player-profile owners should simultaneously manage the same players.

The relevant Modrinth `1.6.3` release lists Paper 26.1.2 and 26.2; it does not list 26.3. Another release artifact is named `1.6.3-mc1.21.11`, so ordering releases by timestamp alone does not select the correct artifact. The implementation uses CraftBukkit/NMS and a Paper 26.2 development bundle. Do not inherit Worlds' 26.3 compatibility claim for PerWorlds without separate verification.

The build comments out `foliaSupported = true`, explaining that too many necessary events are not called on Folia. Worlds' Folia support does not establish support for the combined stack.

## Explicit coordinates and resume have distinct paths

Source paths below are relative to `plugin/src/main/java/net/thenextlvl/perworlds/` at the pinned release commit.

- `listener/TeleportListener.java`: a successful cross-world teleport persists the source profile at MONITOR when the group changes. `PlayerChangedWorldEvent` loads the destination group at LOWEST with `loadPlayerData(player)`.
- `group/PaperWorldGroup.java:324`: that overload delegates with `position = false`.
- `model/PaperPlayerData.java:256`: when the player is already in a member world and `position = false`, restoration applies profile data without teleporting again.
- `command/GroupTeleportCommand.java`: the explicit group teleport command uses `loadPlayerData(player, true)` for players outside the target group.
- `group/PaperWorldGroup.java:125`: position selection prefers the stored last location if enabled, then falls back to group spawn.
- `listener/ConnectionListener.java`: join restores the current group's profile with position enabled; quit persists the current profile.

Thus ordinary cross-world teleport to a chosen entrance B is not unconditionally replaced by a saved location. An explicit group resume operation is separate. This matches the distinction the user requested between intentional coordinates and continuing previous progress.

The persisted location belongs to the group's player profile. This is not evidence of independent saved locations for every member world while those worlds share one inventory profile. Our existing WorldLifecycle per-world resume contract needs separate comparison.

## Cold worlds are an additional responsibility

- `group/PaperWorldGroup.java:165` resolves configured world keys through `Server.getWorld` and omits unloaded worlds.
- `adapter/WorldAdapter.java:23` requires the referenced world to be loaded when deserializing and throws `ParserException("World not found: ...")` otherwise. `LocationAdapter` uses this adapter.
- The reviewed group teleport path does not load/wake a missing world.
- The optional Worlds listener removes deleted worlds from groups; it does not implement idle sleep, wake-on-entry, or pre-login restoration of an unloaded target.

PerWorlds' last-location feature is consequently not demonstrated to replace WorldLifecycle's unloaded-world entry and login behavior. Loading the world first may be a possible integration approach; it has not been implemented or tested here.

## MVI importer exists, but does not establish lossless migration

`importer/multiverse/MVInventoriesImporter.java` reads group membership from `groups.yml` and identities from `playernames.json`. It then selects a `worlds/<world>/<name>.json` profile from an already-loaded group member.

The inspected implementation imports inventory, armor, offhand, ender chest, potions, bed spawn, game mode, and selected scalar state. Its `applyStats` method handles health, food, XP, exhaustion, saturation, fall distance, fire ticks, and remaining air. The word `stats` here does not mean Bukkit game statistics.

No handling of MVI `game_statistics` or `last_location` was found in this importer. It also does not read a group-profile directory in the inspected read path. `selectBestSnapshot` selects by object field count, rather than a stored latest-write timestamp.

The base `importer/Importer.java` imports groups returned by the group reader and resolves loaded worlds only. This does not demonstrate importing an ungrouped world's independent MVI profile or recreating all existing sharing rules.

Before considering deployment, migration must therefore be checked against copies of the actual MVI 5.3.6 data layout and the current sharing/resume requirements. The existence of a migration command is not a guarantee that current inventory, game statistics, positions, and settings all survive.

## Assessment

PerWorlds fills a substantial player-state capability gap when assessing the Worlds ecosystem. It implements real group profiles, statistics persistence, and a useful separation between explicit teleport coordinates and group resume. It is a credible candidate for a separate test environment.

It does not establish native command-selector or shared-main-scoreboard isolation, and it does not supply the currently required sleeping-world lifecycle. Replacing the player-profile plugin alone would therefore not prevent a later Trials `gamemode adventure @a` or `clear @a` from affecting a player in another world. The complementary report also records a source-derived typed-statistics restoration concern that has not been reproduced at runtime.
