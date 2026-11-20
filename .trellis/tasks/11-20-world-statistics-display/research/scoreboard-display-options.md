# Research: scoped online statistics sidebar components

- Query: Which maintained component can present an online-only death leaderboard for each viewer's effective MVI `game_statistics` scope, preserving native scoreboard state and non-sidebar displays?
- Scope: mixed; official pinned upstream source/releases plus local MVI 5.3.6 source and validated statistics contract.
- Date: 2026-11-20

## Findings

### Selection

Use **PacketEvents 2.14.0 plus a narrow standalone presentation adapter**. The adapter owns effective-scope resolution, current-statistic snapshots, derived rows and per-viewer sidebar ownership. PacketEvents owns protocol encoding and packet interception. WorldLifecycle and MVI remain unchanged.

This is a supported library integration, not a configuration-only scoreboard product. No surveyed product established the complete required combination of live MVI-scoped ranking and durable priority over native sidebar assignments. TAB's documented/source-proven behavior actively conflicts with the ownership requirement. The required display consists of one objective and ordinary numeric score rows, so PacketEvents' public wrappers are sufficient; another renderer is unnecessary for this scope.

The selection was communicated to and chosen by the parent session. No runtime compatibility or integration success is claimed by this research; implementation must validate the exact local Paper 26.2 environment.

### Candidate comparison

| Candidate | Verified capability | Gap for this contract | Decision |
| --- | --- | --- | --- |
| TAB 6.2.1 | Per-viewer scoreboards; public custom player placeholders; source implementations for Paper/Minecraft 26.2 | Deliberately yields to native/other-plugin sidebar assignments, including when API `showScoreboard` is used; needs MVI roster adapter as well | Do not use for exclusive scoped sidebar |
| SimpleScore 4.3.1 | README explicitly supports through 26.2; packet-based per-viewer rendering; personal `%player_deaths%` reads Bukkit `DEATHS` | Personal placeholder is not ranked roster; inspected renderer only sets display slot at objective creation and does not establish persistent ownership against native reassignment | No demonstrated configuration-only solution |
| ajLeaderboards | Maintained persistent/top/timed placeholder leaderboard product | Board+player database/cache model samples values over time; inspected rank lookup does not use viewer scope; direct deaths placeholder would mix active profiles and retain offline entries | Unsuitable for initial online/current-profile scope |
| FastBoard 2.2.2 | Small packet renderer, public create/update/delete API; Maven Central artifact | No native-sidebar interception; reflective runtime compatibility still needs exact 26.2 validation | Unneeded additional dependency when using numeric PacketEvents rows |
| PacketEvents 2.14.0 | Explicit 26.2 and 26.3 protocol support; objective/display/update/reset wrappers and cancellable outbound events | Requires narrow presentation implementation | Selected reusable protocol boundary |

### Exact PacketEvents artifact and compatibility evidence

- Release: https://github.com/retrooper/packetevents/releases/tag/v2.14.0
- Published: 2026-09-23.
- Spigot/Paper runtime JAR: https://github.com/retrooper/packetevents/releases/download/v2.14.0/packetevents-spigot-2.14.0.jar
- GitHub asset size: `5723413` bytes.
- GitHub release asset digest: `sha256:060087c58ec268eae7dd0eb1f17ac3bea1eaadda1693414141ff64e506091bd7`.
- Metadata source: https://api.github.com/repos/retrooper/packetevents/releases/tags/v2.14.0
- 2.13.0 explicitly introduced Minecraft 26.2 support: https://github.com/retrooper/packetevents/releases/tag/v2.13.0
- 2.14.0 adds Minecraft 26.3 and retains `ServerVersion.V_26_2(776)` and `V_26_3(777)` in pinned source: https://github.com/retrooper/packetevents/blob/v2.14.0/api/src/main/java/com/github/retrooper/packetevents/manager/server/ServerVersion.java

The digest above is publisher metadata, not a local download hash computed by this agent. Installer/build validation should download the pinned artifact and verify the digest. No dependency was installed during research.

### PacketEvents public API sufficient for the projection

All paths below are relative to `https://github.com/retrooper/packetevents/blob/v2.14.0/`.

| Source and line | Verified API |
| --- | --- |
| `api/src/main/java/com/github/retrooper/packetevents/wrapper/play/server/WrapperPlayServerScoreboardObjective.java:44` | Constructor `(String name, ObjectiveMode mode, Component displayName, @Nullable RenderType renderType)`; a five-argument overload adds optional `ScoreFormat` |
| Same file:167 | `ObjectiveMode.CREATE`, `REMOVE`, `UPDATE` |
| Same file:189 | `RenderType.INTEGER`, `HEARTS` |
| `api/src/main/java/com/github/retrooper/packetevents/wrapper/play/server/WrapperPlayServerDisplayScoreboard.java` | Constructor `(int position, String scoreName)` and event-reading constructor; `getPosition()`, `getScoreName()`, setters |
| `api/src/main/java/com/github/retrooper/packetevents/wrapper/play/server/WrapperPlayServerUpdateScore.java:44` | Constructor `(String entityName, Action action, String objectiveName, Optional<Integer> value)` |
| Same file:52 | Constructor `(String entityName, Action action, String objectiveName, int value, @Nullable Component entityDisplayName, @Nullable ScoreFormat scoreFormat)` |
| Same file:203 | `Action.CREATE_OR_UPDATE_ITEM`, `REMOVE_ITEM`; modern write path uses numeric score fields |
| `api/src/main/java/com/github/retrooper/packetevents/wrapper/play/server/WrapperPlayServerResetScore.java:36` | Constructor `(String targetName, @Nullable String objective)` |
| `api/src/main/java/com/github/retrooper/packetevents/manager/player/PlayerManager.java:57` | `sendPacket(Object player, PacketWrapper<?> wrapper)`; `sendPacketSilently` overload exists at line 65 |
| `api/src/main/java/com/github/retrooper/packetevents/event/PacketListenerAbstract.java` | `onPacketSend(PacketSendEvent)` with configurable listener priority |
| `api/src/main/java/com/github/retrooper/packetevents/event/EventManager.java:118` | `registerListener(PacketListenerCommon)`; matching `unregisterListener` at line 137 |

Packet types are `SCOREBOARD_OBJECTIVE`, `DISPLAY_SCOREBOARD`, `UPDATE_SCORE`, `RESET_SCORE`. Access is through `PacketEvents.getAPI().getPlayerManager()` and `.getEventManager()`. An outbound listener can inspect the display wrapper and cancel only the assignment being replaced.

Important modern-protocol detail: on 26.2, remove a row with `WrapperPlayServerResetScore`, not `WrapperPlayServerUpdateScore(... REMOVE_ITEM ...)`. The >=1.20.3 `UPDATE_SCORE` write branch does not encode the old action field. Always pass the projection's objective name when removing its row; a null objective in `RESET_SCORE` clears that holder across objectives.

### Sidebar ownership without native state mutation

The projection must be client presentation only. Do not create its objectives on the Bukkit main scoreboard, call `Player.setScoreboard`, clear native scores, or clone and replace the main board.

For an enrolled viewer:

1. Create a uniquely named presentation objective and send its rows.
2. Take over the generic sidebar display slot and neutralize already assigned team-color sidebar slots for that viewer. Native client slots are LIST=0, SIDEBAR=1, BELOW_NAME=2, with color-specific sidebar slots 3–18.
3. Intercept subsequent native sidebar display assignments while the projection is active. A native `/scoreboard objectives setdisplay` remains authoritative on the server, but its sidebar display packet must not displace the derived view. Preserve current suppressed assignments so ownership can be released correctly.
4. Pass native objective, score and team changes, and LIST/BELOW_NAME display assignments through. Handle objective deletion so release never points to an objective that no longer exists.
5. On disable/release, delete only the presentation objective and restore the currently valid native sidebar assignments. Do not restore a stale startup snapshot if native commands changed the assignment while the component was active.

These are integration obligations inferred from the requirement and packet model, not a tested implementation. Packet listener callbacks must not read arbitrary mutable Bukkit/MVI state from a Netty thread. Use narrowly scoped concurrent ownership/tracking state; collect gameplay snapshots on the server thread.

Two important preservation cases:

- Clearing/suppressing SIDEBAR=1 alone is insufficient if the client's team color selects an already populated slot 3–18. Cover color-specific sidebar assignment and restore paths while leaving native teams intact.
- A native `RESET_SCORE(realPlayerName, null)` resets that holder across all client objectives. If the projection uses real names as score-holder IDs, an otherwise correct native reset can erase a projected row until it is explicitly resent. Prefer stable presentation-only holder IDs with the modern `entityDisplayName` field for the player's visible name, or detect and repair the affected projected row after the native packet. Do not cancel the native reset merely to protect the projection.

No arbitrary objective isolation is promised. Native map logic, dummy objectives and fake-player values continue to live on the server main scoreboard. The adapter replaces the viewer's sidebar presentation only.

### Why TAB is not selected despite suitable APIs

Pinned version: **6.2.1**, release 2026-10-18.

- General binary: https://github.com/NEZNAMY/TAB/releases/download/6.2.1/TAB.v6.2.1.jar
- Asset size: `8483627` bytes.
- Asset digest: `sha256:0b6a21af6fd3b113c05821daaed00ff92234a84ca94b29b3aec0ef1bd313b8a9`.
- Do not confuse this with the separate artifact whose filename explicitly limits it to Paper 1.20.5–1.21.4.
- Pinned source tree includes `bukkit/paper_26_2/` and `bukkit/v26_2/` packet scoreboard implementations.

The supported extension APIs were verified:

- https://github.com/NEZNAMY/TAB/blob/6.2.1/api/src/main/java/me/neznamy/tab/api/placeholder/PlaceholderManager.java — `registerPlayerPlaceholder(String identifier, int refresh, Function<TabPlayer,String> function)`, where refresh is a multiple of 50 ms; unregister APIs exist.
- https://github.com/NEZNAMY/TAB/blob/6.2.1/api/src/main/java/me/neznamy/tab/api/scoreboard/ScoreboardManager.java — `createScoreboard`, `showScoreboard`, `resetScoreboard`, visibility and removal APIs.
- https://github.com/NEZNAMY/TAB/wiki/Developer-API — plugin/player load events for registration.

These could render MVI-derived ranked rows, but they do not provide the required native-sidebar priority:

- https://github.com/NEZNAMY/TAB/blob/6.2.1/shared/src/main/java/me/neznamy/tab/shared/features/scoreboard/ScoreboardManagerImpl.java — `onDisplayObjective` sets `otherPluginScoreboard` when a foreign sidebar is assigned. Removal/clear restores TAB afterward.
- https://github.com/NEZNAMY/TAB/blob/6.2.1/shared/src/main/java/me/neznamy/tab/shared/features/scoreboard/ScoreboardImpl.java — `addPlayer` calls `setDisplaySlot` only when `otherPluginScoreboard == null`.
- `showScoreboard` still calls that `addPlayer`; its forced selection bypasses conditions, not foreign sidebar ownership.
- https://github.com/NEZNAMY/TAB/blob/6.2.1/shared/src/main/java/me/neznamy/tab/shared/features/scoreboard/ScoreboardConfiguration.java — recognized keys are enabled, toggle-command, remember-toggle-choice, hidden-by-default, delay-on-join-milliseconds and scoreboards; no foreign-sidebar override was found.
- https://github.com/NEZNAMY/TAB/wiki/Feature-guide:-Scoreboard explicitly documents hiding TAB's board when another plugin sends one and restoring it after that board is hidden.

A packet arbiter would therefore be needed even with TAB. For the initial numeric leaderboard, using PacketEvents wrappers directly avoids TAB's unrelated feature surface and competing ownership state. No TAB fork or reflection into `otherPluginScoreboard` is recommended.

### Other candidate evidence

SimpleScore's old repository URL redirects to `RuiPereiraDev/SimpleScore`. Version **v4.3.1** was published 2026-08-23 and its README claims support through 26.2:

- https://github.com/RuiPereiraDev/SimpleScore/tree/v4.3.1
- https://github.com/RuiPereiraDev/SimpleScore/blob/v4.3.1/bukkit/src/main/kotlin/com/r4g3baby/simplescore/bukkit/scoreboard/VarReplacer.kt — `%player_deaths%` evaluates `viewer.getStatistic(Statistic.DEATHS)`; `%player_world_online%` is the viewer world's player count. Neither constructs the required ranked roster.
- https://github.com/RuiPereiraDev/SimpleScore/blob/v4.3.1/bukkit/src/main/kotlin/com/r4g3baby/simplescore/bukkit/protocol/modern/ModernProtocolHandler.kt — creates a display assignment during objective creation; score/title updates do not resend ownership.
- https://github.com/RuiPereiraDev/SimpleScore/blob/v4.3.1/bukkit/src/main/kotlin/com/r4g3baby/simplescore/bukkit/protocol/ChannelInjector.kt — channel lookup and outbound writes; no interception in this class.
- https://github.com/RuiPereiraDev/SimpleScore/wiki/Placeholders — placeholder handling is asynchronous by default, with a configuration toggle. A custom scope provider would need safe snapshots.

This review does not prove no extension is possible. It establishes no ready configuration-only scoped leaderboard and no simpler demonstrated ownership solution.

ajLeaderboards evidence:

- https://github.com/ajgeiss0702/ajLeaderboards — active upstream, repository pushed 2026-10-15 during this inspection; README explicitly names support through 26.1 rather than exact 26.2 validation.
- `src/main/java/us/ajg0702/leaderboards/placeholders/placeholders/lb/Name.java` — rank parsing calls `getTopManager().getStat(rank, board, type)`; viewer argument is not used to resolve MVI scope.
- `BoardPlayer` uses board and player UUID; configuration provides sampled refresh, join/leave updates and optional offline updates.

Sampling a personal active `DEATHS` placeholder into that persistent board would not itself mean same-scope online membership. Excluding this product is a fit decision for this task, not a statement that custom integration is impossible.

FastBoard evidence:

- https://github.com/MrMicky-FR/FastBoard/tree/v2.2.2 — released 2026-09-21; Maven Central coordinate `fr.mrmicky:fastboard:2.2.2`.
- README describes packet-only rendering, no dependencies, async capability and broad Minecraft support starting at 1.7.10.
- `src/main/java/fr/mrmicky/fastboard/FastBoardBase.java` exposes `getId()`, updates and `delete()`, and sets its display objective at construction. It uses reflective NMS resolution and does not arbitrate native outbound sidebar assignments.
- Its ViaBackwards section requires explicit handling of older clients and custom-number support. This is another compatibility obligation, not proof of local failure.

### MVI scope and statistics contracts

Use the already validated full MVI statistics policy. Do not introduce a second death counter or read stale profile files as the live leaderboard source.

Local source findings at MVI 5.3.6 (source baseline previously recorded as commit `def55c476b16d2cb6f41c48c8498cb5eff9e6bd3`):

| Local file and line | Meaning |
| --- | --- |
| `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/MultiverseInventoriesApi.java:43` | Public `MultiverseInventoriesApi.get()` access |
| Same file:70 | Public inventories configuration accessor |
| Same file:115 | Public `getWorldGroupManager()` |
| `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/profile/group/AbstractWorldGroupManager.java:86` | `getGroupsForWorld` resolves configured groups and optional default group fallback for MV-managed worlds |
| `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/profile/group/WorldGroup.java:263` | Share-specific `isSharing` query |
| Same file:281 | Applicable shares distinguish enabled/effective shares from raw configuration |
| `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/share/Sharables.java:820` | Full `GAME_STATISTICS` share implementation |
| `.tmp/mvi-src/src/main/java/org/mvplugins/multiverse/inventories/handleshare/WorldChangeShareHandler.java:103` | Applicable and disabled group shares both affect handled-share accounting |
| Same file:129 | Group read uses applicable shares |
| Same file:137 | Missing shares fall back to world profile subject to optional-share policy |

The scope cannot simply be the viewer's world name or the first group returned. Resolve groups that actually share `GAME_STATISTICS`; same-group dimensions belong together. Ungrouped worlds use independent profiles under the adopted `default-ungrouped-worlds:false` and `use-optionals-for-ungrouped-worlds:true` policy. Detect ambiguous multiple statistics-sharing groups rather than silently choosing one. Disabled shares, bypass permissions, game-mode profile policies or changed optional activation can invalidate assumptions and should be explicitly validated or rejected by the presentation configuration contract.

Read current online players' Bukkit `Statistic.DEATHS` on the main thread after MVI handling has settled. Death increments occur after the death event; world transitions can involve profile loading. Refresh/debounce after those operations and use a periodic reconciliation rather than assuming an immediate event read is final. Group membership/profile policy changes need reevaluation. Derived rows and display state are ephemeral; no additional player database is required.

### Validation needed before adoption

- Two simultaneous viewers in independent scopes see disjoint rosters and current restored values.
- Same statistics-sharing group dimensions show the same online roster.
- Real deaths, world transitions, join/quit, rejoin, unloaded-world reentry and restart refresh correctly.
- Main-board sentinel objectives, native score/fake-player values and teams survive unchanged.
- Native LIST and BELOW_NAME remain visible and continue updating.
- Native generic and team-color sidebar `setdisplay` while enrolled cannot replace the scoped view; current native assignments return on release.
- Native objective removal and unqualified score reset do not break projected rows or corrupt native state.
- Empty roster, zero deaths, equal values and more than 15 online entries behave deterministically; native sidebar capacity is bounded.
- Actual client packet observations confirm display/roster behavior. Inspecting server-side objective values alone does not prove viewer isolation.
- PacketEvents startup and listener ordering coexist with the actual server plugin set, including GrimAC, ViaVersion/ViaBackwards and Geyser. Current release compatibility evidence is not that integration test.

## Files found

- `.trellis/tasks/11-20-world-statistics-display/prd.md` — approved presentation requirements and exclusions.
- `.trellis/tasks/11-20-world-statistics-display/design.md` — ownership, concurrency and deployment constraints.
- `.trellis/spec/backend/multiverse-player-state.md` — validated full MVI statistics behavior and native scoreboard boundary.
- `.trellis/spec/backend/world-artifacts.md` — world artifact ownership boundary.
- `.tmp/death-statistics-test/final-report.md` — prior 45-check, five-JVM statistics validation; not sidebar validation.
- `.trellis/tasks/11-18-config-bundle/research/death-statistics-adaptation.md` — MVI source/event-order evidence and adoption details.
- `.trellis/tasks/11-18-config-bundle/research/scoreboard-world-scope.md` — native scoreboard versus player-statistics distinction.
- `.tmp/mvi-src/` — existing MVI 5.3.6 source used for public API and effective-share checks.

## Related specs

- `.trellis/spec/backend/multiverse-player-state.md`
- `.trellis/spec/backend/world-artifacts.md`
- `.trellis/tasks/11-20-world-statistics-display/design.md`

## Caveats / Not Found

- Research read official source/API/release metadata; it did not install, build, launch or modify any runtime, source plugin, profile or map.
- No surveyed product was demonstrated to provide the complete live MVI-scoped leaderboard by configuration alone. The market survey was intentionally limited after decisive source evidence.
- PacketEvents exact-version protocol support and public constructors are verified. The selected adapter remains to be implemented and tested on the local baseline.
- The first product requirement is online-only current-profile deaths. This report does not justify offline ranking, historical per-world reconstruction, scoreboard command isolation or moving statistics ownership into WorldLifecycle.
- Native sidebar ownership is exclusive while enrolled. Arbitrary other packet-only sidebar plugins are not covered by preserving the Bukkit main scoreboard alone; coexistence would need an explicit ownership policy.
