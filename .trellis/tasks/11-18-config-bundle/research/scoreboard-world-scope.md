# Research: scoreboard scope across Multiverse worlds

- Query: Why is a death scoreboard visible/shared across `world` and `trials`, and which component should own a remedy?
- Scope: mixed; read-only local Paper 26.2 build 135 bytecode, MVI 5.3.6 source, current manual-runtime files, map artifact, and public API references.
- Date: 2026-11-20

## Findings

### Verified early conclusions

1. Actual Paper 26.2 `ServerLevel.getScoreboard()` returns `MinecraftServer.getScoreboard()`. The native command scoreboard is server-wide. It is loaded through the server's `savedDataStorage` and saved by `MinecraftServer.saveGlobalData`.
2. The current manual runtime has a native `Deaths` objective with criterion `deathCount`, assigned to `sidebar`, in `world/data/minecraft/scoreboard.dat`. This same objective/criterion/display assignment is present in the Trials source map and immutable imported artifact. The artifact also contains command blocks that create and display this objective. Thus Trials supplies this scoreboard behavior; this research does not establish which particular past copy or command execution populated the current runtime.
3. MVI 5.3.6 has `game_statistics`, implemented through Bukkit `Player.getStatistic` / `setStatistic`. It has no built-in sharable for scoreboard objectives, scores, display slots, or teams. Those are distinct state systems.
4. `game_statistics` is optional in MVI 5.3.6. The current manual runtime enables only `last_location` in `active-optional-shares`. Listing `game_statistics` in a group's shares does not activate it globally. Prior inventory/health success therefore does not establish statistics isolation.
5. Scoreboard display policy, world-qualified gameplay statistics, and compatibility with arbitrary map command logic are separate requirements. None follows automatically from world load/unload orchestration.

### Files found

| File | Purpose / evidence |
| --- | --- |
| `.tmp/world-lifecycle-manual/runtime/versions/26.2/paper-26.2.jar` | Actual Paper runtime inspected with Java 25 `javap -c -p`; SHA-256 `7c391444fd5f5fb77d193414924e7a16dbfd1cac87a2a6c858a8ea8dd041f44e`. |
| `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/share/Sharables.java` | Built-in share definitions; local checkout is tag `5.3.6`, commit `def55c476b16d2cb6f41c48c8498cb5eff9e6bd3`. |
| `.tmp/world-lifecycle-manual/runtime/plugins/Multiverse-Inventories/config.yml` | Only `last_location` enabled as optional; ungrouped worlds can use enabled optional shares. |
| `.tmp/world-lifecycle-manual/runtime/plugins/Multiverse-Inventories/groups.yml` | Main three dimensions share inventory/health and other enabled shares; Trials is outside the group. |
| `.tmp/world-lifecycle-manual/runtime/world/data/minecraft/scoreboard.dat` | Persisted server main scoreboard, including map objectives and sleep datapack objectives. |
| `.tmp/trials-full/Trials of the past/data/minecraft/scoreboard.dat` | Extracted Trials scoreboard. |
| `artifacts/trials-legacy/data/minecraft/scoreboard.dat` | Immutable import artifact retains the same six Trials objectives and two display assignments. |
| `artifacts/trials-legacy/region/r.-3.-1.mca` | Native map command blocks create/display the death objective. |
| `docs/PAPER-WORLD-SOP.md:170` | Existing deployment documentation explicitly copies source `scoreboard.dat` into server top-level `world/data/minecraft`. This documents a pipeline but is not an execution log proving when the current manual state was created. |
| `docs/PAPER-WORLD-SOP.md:503` | Existing known-boundary statement already identifies shared scoreboards/maps/top-level data. |
| `.tmp/worldlifecycle-extraction/project/src` | No scoreboard code found in extracted WorldLifecycle source. |

### Paper 26.2 behavior

Bytecode was inspected from the actual local runtime, not inferred from a generic Minecraft version:

- `net.minecraft.server.level.ServerLevel#getScoreboard`, bytecode offsets 0–7: returns `server.getScoreboard()`.
- `net.minecraft.server.MinecraftServer`: owns one `ServerScoreboard`; initial world setup obtains `ScoreboardSaveData.TYPE` from server `savedDataStorage` and calls `ServerScoreboard.load`.
- `MinecraftServer#saveGlobalData`, offsets 0–17: stores the shared board back to `ScoreboardSaveData`.
- `net.minecraft.server.commands.ScoreboardCommand#getScore` and mutation methods obtain `CommandSourceStack.getServer().getScoreboard()`. A command running in a particular dimension still targets that server board. Moving a command block into Trials, or using a dimension execution context, does not create a private scoreboard.
- `ServerPlayer#die` independently processes `ObjectiveCriteria.DEATH_COUNT` through `CraftScoreboardManager.forAllObjectives`, then awards `Stats.DEATHS`. There is no per-world filter in the native `deathCount` criterion path.
- `CraftScoreboardManager#getPlayerBoard` returns the main board when no player override exists; `setPlayerBoard` can override the board shown to a player.
- `CraftScoreboardManager#forAllObjectives` iterates registered scoreboards. Merely assigning a separately created board to players is therefore not an automatic world-sensitive counter design. Paper's plugin-scoreboard tracking/registration behavior also matters; use explicit world-qualified counting when that is the requirement.

Consequence: unloading Trials stops its chunk-based execution, but does not destroy its main-board objectives, remove its display slots, or stop a global `deathCount` objective from being updated by deaths in another loaded world. Reloading Trials does not reload a separate private copy of its scoreboard.

### MVI statistics are separate, with one relevant API interaction

Source locations in `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/share/Sharables.java`:

- Line 820: `GAME_STATISTICS` definition.
- Lines 825–880: snapshots Bukkit `Statistic` values.
- Lines 885–978: restores them through Bukkit `setStatistic` (missing values become zero).
- Line 979: this share is explicitly `.optional()`.
- Lines 1283–1287: enabled shares are standard shares plus configured active optional shares.

The manual `config.yml:41` enables only `last_location`; `groups.yml:31` listing `game_statistics` does not override that activation gate. This also means the current inventory/health validation did not validate independent statistics, advancements, or recipes. `advancements` and `recipes` are themselves optional at source lines 786 and 1014.

Important precision: `CraftStatistic#setStatistic(ServerStatsCounter, Statistic, int, ServerPlayer)` in this Paper JAR does update matching statistic-criterion objectives through `forAllObjectives` after setting the statistic. Consequently enabling `game_statistics` can affect native objectives whose criterion is a Minecraft statistic. It still does not snapshot/restore the entire scoreboard, its arbitrary dummy values, teams, display slots, or the distinct `deathCount` objective. Trials also uses statistic criteria (`respawn` and `join`), so blindly enabling all optional shares is not an established map-compatibility fix.

### What the actual map contains

All three inspected scoreboard files contain these map objectives:

| Objective | Criterion | Display slot |
| --- | --- | --- |
| `Deaths` | `deathCount` | `sidebar` |
| `total_deaths` | implicit default / dummy | `list` |
| `respawn` | `minecraft.custom:minecraft.time_since_death` | none |
| `join` | `minecraft.custom:minecraft.leave_game` | none |
| `health` | `health` (hearts rendering) | none |
| `con` | implicit default / dummy | none |

The manual file also contains `mpp_*` objectives belonging to the sleeping datapack. It has accumulated player scores whereas the imported artifact has no death scores. The installed manual plugin list is MVCore, MVI, PackManagerPro, WorldLifecyclePrototype, and Paper's spark; no dedicated scoreboard plugin was found.

A read-only Python scan reused `.tmp/nbt.py`, decompressed the 43,886 chunks in the immutable artifact, and read command-block NBT. It found these relevant commands with zero parse failures:

| Region / block coordinate | Stored command |
| --- | --- |
| `r.-3.-1.mca`, `-1197 61 -138` | `scoreboard objectives add Deaths deathCount` |
| `r.-3.-1.mca`, `-1195 61 -138` | `scoreboard objectives setdisplay sidebar Deaths` |
| `r.-3.-1.mca`, `-1193 61 -138` | `/scoreboard objectives add total_deaths dummy` |
| `r.0.0.mca`, `317 59 502` | `scoreboard objectives setdisplay list total_deaths` |
| Several chunks | `/scoreboard players reset @a[scores={join=1..}] join` |

These are definite map instructions, but presence in stored chunks does not prove a particular block is currently loaded/powered or has recently executed. This was a scoreboard-focused command-block scan, not a complete semantic audit of every selector, entity command, datapack, or gameplay mechanism.

### Recommended boundary by actual requirement

| Requirement | Suitable ownership and approach | Limit |
| --- | --- | --- |
| Do not show the Trials death sidebar while a player is in `world` | A display component chooses a player's scoreboard presentation on join/world change; keep the map's underlying objectives intact. A per-player view or carefully scoped packet presentation can implement this. | Hiding a display does not stop counting, does not isolate commands, and must preserve other teams/sidebar/list behavior. Changing the main board's display slot on each player's world change changes it globally and fails with players in two worlds. |
| Deaths in `world` must not increase Trials deaths | A gameplay/statistics owner counts events by the player's world/group and persists values by world identity plus player UUID; namespaced objectives can project that data. Adapt Trials' original `deathCount` setup if it is to consume the new data. | Merely renaming a `deathCount` objective or making one per world does not add a world filter. The map can recreate its original objective from command blocks unless the adaptation handles that setup. |
| Preserve arbitrary imported-map command behavior while giving multiple maps independent objective names/state | Separate server save/process boundaries provide the native isolation. In one server, audit and adapt every relevant map command/objective/selector/shared-state dependency, or implement and thoroughly verify a dedicated command-state isolation layer. | Bukkit per-player scoreboards do not redirect vanilla command evaluation. Swapping one server main board on player movement cannot satisfy simultaneous players in different worlds. Saving one scoreboard per world and swapping on load/unload has the same concurrent-state problem. |

For the immediate report, first distinguish visible leakage from incorrectly accumulated deaths. If the only problem is the sidebar appearing in `world`, use a display policy. If separate adventure progress is expected, a display-only fix would conceal shared data rather than meet the expectation. This research intentionally does not select an unverified plugin or expand WorldLifecycle into a scoreboard manager.

For a future implementation, validate two players in two worlds, deaths in each, map command resets, explicit objective name collisions, quit/rejoin, unload/reload, and JVM restart. Persisted lightweight score data does not require keeping the world loaded. Existing global death totals have no world provenance in the inspected scoreboard; they cannot be reliably split retrospectively without independent event history.

## External References

- Paper 26.2 API `ScoreboardManager`: https://jd.papermc.io/paper/26.2/org/bukkit/scoreboard/ScoreboardManager.html — retrieved documentation states that the main scoreboard is saved by the server, affected by `/scoreboard`, and shown by default. A new board is tracked while referenced by a player/plugin.
- MVI 5.3.6 exact source revision, corresponding to the locally inspected checkout: https://github.com/Multiverse/Multiverse-Inventories/blob/def55c476b16d2cb6f41c48c8498cb5eff9e6bd3/src/main/java/org/mvplugins/multiverse/inventories/share/Sharables.java — the local checkout is the primary evidence for method-level findings.

## Related Specs

- `.trellis/spec/backend/world-artifacts.md`: map artifacts are immutable input; live-world state is a copy. This research read but did not modify the artifact.
- `.trellis/spec/backend/config-bundle.md`: declarative configuration and host/player-produced state are separate. A scoreboard snapshot is instance/gameplay state, not a configuration template.
- `.trellis/spec/backend/index.md`: project-scoped backend entry point.
- The active configuration-bundle task is historical context only; this report does not alter deployment scope or approve a new scoreboard feature.

## Caveats / Not Found

- No commands were sent to the running server, and no runtime/configuration/player data was modified.
- Disk scoreboard snapshots can lag currently running state. The inspected persisted layout and map identity are confirmed; no new live death test was performed.
- Exact historical insertion of the current board into the manual runtime was not traced. The map's matching scoreboard file, creating command blocks, and documented import pipeline are verified separately.
- No claim is made that MVI, MVCore, or a generic scoreboard plugin provides complete vanilla-command state isolation.
- The findings are pinned to the local Paper 26.2 build and MVI 5.3.6. Broader version compatibility was not tested.
