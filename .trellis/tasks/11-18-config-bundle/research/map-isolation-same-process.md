# Research: isolating complete vanilla-map command state in one server

- Query: What does complete mutual isolation of several vanilla adventure maps cost in one server process, and do existing maintained solutions already supply it?
- Scope: mixed; existing Paper 26.2 and ASP local source evidence, official Cosmos/Sponge, TAB, and Minestom documentation/source/maintenance metadata. Research only; no runtime changes.
- Date: 2026-11-20

## Findings

### Decision-relevant conclusion

There is a real same-process counterexample to the blanket claim that every per-world scoreboard plugin only changes presentation: **Cosmos** has persistent world/group scoreboards and rewrites top-level scoreboard commands into its own world-aware implementation. However, the inspected evidence does **not** establish comprehensive isolation of vanilla command storage, selectors, nested execution, functions, schedules, or all other map state. Its supported ecosystem is Sponge, with an old public release targeting Minecraft 1.12.2 and a development branch targeting Sponge API 8.1.0; it is not a verified Paper 26.2 solution.

For the present Paper 26.2 deployment, no reviewed candidate has demonstrated the requested entire command-state isolation contract. This is a bounded evaluation result, **not proof that no such project exists**. General isolation would be a command/runtime compatibility subsystem rather than one extra world-load listener. Adapting one map narrows the scope, but the existing Trials scoreboard scan is insufficient to promise a low cost or fixed delivery time.

Separate server processes with separate saves give each map an actual native server-state boundary. They do **not** automatically make a legacy map work on a newer Minecraft/Paper version. State isolation, old command syntax, redstone behavior, datapack versions, and Paper behavior compatibility are separate validation axes.

### Evidence levels

- **Runtime evidence**: inspected actual Paper 26.2 build 135 bytecode and saved map data; previous report contains hashes and exact methods.
- **Implementation evidence**: exact candidate source contains the relevant behavior; not an integration test.
- **Author contract**: official documentation/release states support; not proof that this map works.
- **Unknown**: no adequate official claim, source proof, or live test obtained. Unknown is not treated as unsupported by definition.

## Candidate checks

### 1. Cosmos on Sponge: actual per-world data and command implementation, incomplete coverage proof

Official README advertises per-world scoreboards, command blocks, and an “Enhanced vanilla scoreboard commands implementation.” Source on `develop/api-8`, commit `0ee7cf75efa009e2a7a42eb4be66060f3e6dede6`, substantiates more than UI customization:

- `ScoreboardServiceImpl#scoreboardOrCreate(ResourceKey)` finds a world/group board in a registry, loads it from a world-keyed serialized file, or creates a new board. This is actual isolated scoreboard data, not only a different title.
- `AbstractScoreboardCommand#run` resolves a world key and executes against that world's board.
- `ScoreboardListener#onPreExecuteCommandEvent` intercepts qualifying top-level command names and rewrites them to `cm scoreboard <world> ...`.
- `ScoreboardListener` selects boards on join, world change, and respawn, and serializes them on scheduled save/server stop.
- The inspected `CommandBlockListener` implements world/group command enablement by cancelling command execution where commands are disabled. Its “per-world command blocks” feature is **not evidence of private command-state namespaces**.

Coverage gaps directly visible in the inspected code:

- The scoreboard rewrite is based on the root command string beginning with `scoreboard`; this method itself does not rewrite nested `execute ... run scoreboard ...` command trees, `data storage`, functions, or arbitrary NBT-generated commands. Whether another engine hook covers an execution path requires testing; this review did not establish that coverage.
- A separately namespaced invocation such as `minecraft:scoreboard` does not match that literal prefix in this listener.
- The listener condition `!event.command().startsWith("scoreboard") || event.command().startsWith("team")` returns for a top-level `team` command. Cosmos has its own team implementation, but this listener does not prove transparent interception of the modern vanilla `team` command.
- No complete `storage`/selector/function sandbox contract was found in the inspected advertised features and command-source paths. A world-selector API type in the tree is not evidence that all vanilla entity selectors are confined.

Maintenance and compatibility:

- GitHub repository metadata: `archived=false`, last `pushed_at=2022-07-10T21:32:36Z`.
- Latest returned public release: `v1.2.0-7.3.0`, 2021-04-20, release text targets Minecraft **1.12.2**.
- Development build file: plugin version `2.0.0-8.1.0`, Sponge API **8.1.0**, Java target 8.
- Sponge's current inspected default branch `api-12` is actively updated but declares `minecraftVersion=1.21.1`. This is branch-specific evidence, not a claim about every Sponge branch or download.
- No Paper 26.2 compatibility evidence was found. This is a Sponge plugin, not a Bukkit plugin to drop into the present server. Moving to Sponge changes the engine/plugin API surface; current MVCore/MVI/WorldLifecycle/PackManagerPro compatibility cannot be assumed.

Assessment: a useful proven design precedent and an older-version candidate requiring its own evaluation, **not a demonstrated current-stack turnkey solution**.

Sources:

- https://github.com/thibaulthenry/cosmos
- https://github.com/thibaulthenry/cosmos/releases/tag/v1.2.0-7.3.0
- https://github.com/thibaulthenry/cosmos/blob/0ee7cf75efa009e2a7a42eb4be66060f3e6dede6/src/main/java/cosmos/services/perworld/impl/ScoreboardServiceImpl.java
- https://github.com/thibaulthenry/cosmos/blob/0ee7cf75efa009e2a7a42eb4be66060f3e6dede6/src/main/java/cosmos/executors/commands/scoreboard/AbstractScoreboardCommand.java
- https://github.com/thibaulthenry/cosmos/blob/0ee7cf75efa009e2a7a42eb4be66060f3e6dede6/src/main/java/cosmos/registries/listener/impl/perworld/ScoreboardListener.java
- https://github.com/thibaulthenry/cosmos/blob/0ee7cf75efa009e2a7a42eb4be66060f3e6dede6/src/main/java/cosmos/registries/listener/impl/perworld/CommandBlockListener.java
- https://github.com/thibaulthenry/cosmos/blob/0ee7cf75efa009e2a7a42eb4be66060f3e6dede6/build.gradle.kts
- https://api.github.com/repos/thibaulthenry/cosmos
- https://github.com/SpongePowered/Sponge/blob/api-12/gradle.properties

### 2. TAB: maintained per-world presentation, not command-state isolation

The official scoreboard feature guide explicitly scopes the feature to the **SIDEBAR slot** and shows per-world boards selected with `display-condition: "%world%=world1"`. Its API creates a board from a title and text lines and shows it to a particular player. This is a mature display-layer example but does not claim private vanilla objectives, command storage, or selectors.

The guide also says TAB hides its own board when another plugin supplies one, then restores its board afterwards. Thus installing it is not itself evidence that it can transparently hide the imported native board according to the desired policy; that concrete interaction would still need testing.

Maintenance evidence: repository `archived=false`, `pushed_at=2026-11-11T16:19:44Z`; latest release returned `6.2.1` dated 2026-10-18. That release states Forge 26.3 support with Forge 26.2 retained and mentions Canvas 26.3 fixes. **Those statements must not be repurposed as a Paper 26.2 test result.** We did not install TAB or verify its current Paper matrix because its documented feature scope already fails the full-isolation requirement.

Sources:

- https://github.com/NEZNAMY/TAB/wiki/Feature-guide:-Scoreboard
- https://github.com/NEZNAMY/TAB/releases/tag/6.2.1
- https://api.github.com/repos/NEZNAMY/TAB

### 3. AdvancedSlimePaper: fast world loading/cloning does not establish command isolation

ASP's official/local README describes its goal as faster world loading and reduced storage through Slime Region Format. The existing local checkout is branch `ver/26.2`, commit `031913915008f865e13746ae6e661899542b72cf`.

Local implementation evidence:

- `.tmp/AdvancedSlimePaper/aspaper-server/src/main/java/com/infernalsuite/asp/SlimeNMSBridgeImpl.java:75` begins `loadOverworldOverride`.
- Lines 83–86 load the default overworld and assign one CraftServer scoreboard manager and `instance.getServer().commandStorage = new CommandStorage(...)`.
- The relevant references found in the inspected ASP source are server-wide initialization, not one private command-storage service per cloned world.

Maintenance metadata: current repository `archived=false`, `pushed_at=2026-11-19T04:52:11Z`. There is local 26.2 source/runtime history, so this is materially stronger version evidence than Cosmos. It nevertheless does not establish the requested isolation. A world clone copies world data; it does not automatically change how vanilla commands resolve the server's state services.

Sources:

- https://github.com/InfernalSuite/AdvancedSlimePaper
- https://github.com/InfernalSuite/AdvancedSlimePaper/blob/031913915008f865e13746ae6e661899542b72cf/aspaper-server/src/main/java/com/infernalsuite/asp/SlimeNMSBridgeImpl.java
- https://api.github.com/repos/InfernalSuite/AdvancedSlimePaper

### 4. Minestom instances: purpose-built game isolation is not imported-map compatibility

Minestom's official README says it is a library without Mojang code, contains no vanilla features by default, does not implement Bukkit/Forge/Sponge APIs, and targets servers that benefit little from vanilla features. Instances are collections of blocks/entities useful for custom minigames. This can be a strong design for a game whose behavior the developer owns; it is not a direct substitute for executing an existing adventure map's command blocks, redstone, mobs, functions, and gameplay.

The official VanillaReimplementation README warns it has “only a very limited list of features” and recommends alternatives or implementing one's own. GitHub metadata reports that project **archived=true**, last push 2026-08-15. Minestom itself remains active (`archived=false`, last push 2026-11-15). The active core library must not be confused with a complete maintained vanilla compatibility layer.

Paper 26.2 plugin compatibility is not applicable as a claim: Minestom explicitly does not implement Bukkit. No Trials gameplay test was performed.

Sources:

- https://github.com/Minestom/Minestom/blob/master/README.md
- https://github.com/Minestom/VanillaReimplementation/blob/master/README.md
- https://api.github.com/repos/Minestom/Minestom
- https://api.github.com/repos/Minestom/VanillaReimplementation

## Why full isolation is larger than per-world scoreboard persistence

The actual local Paper 26.2 JAR demonstrates the server-wide routes:

- `ServerLevel#getScoreboard` returns `MinecraftServer#getScoreboard`.
- `ScoreboardCommand` resolves that server board regardless of source world.
- `StorageDataAccessor#getStorage` resolves `CommandSourceStack.getServer().getCommandStorage()`.
- `EntitySelector` has both world-limited and non-world-limited paths. Non-world-limited entity selection iterates `getAllLevels`; non-world-limited player selection uses the server player list. A changed execution dimension alone does not prove all selectors are private to it.

A general compatibility layer needs an explicit map/session context and consistent handling of at least:

1. Objectives, scores, teams, dummy/fake-player values, criteria updates, selectors that read scores/teams, display slots, and persistence.
2. Player/entity selector scope, including names/UUIDs, nested execution, source-context changes, and deliberately cross-dimension map mechanics. An adventure map may require its own overworld/nether/end group, so “single Bukkit world” is not necessarily the right isolation unit.
3. Command storage IDs; functions, function tags, scheduled functions, generated command text/macros where supported, and namespaced resource references. Rewriting visible command-block strings does not establish closure over commands generated later.
4. Other shared resources the particular map uses: boss bars, recipes/advancements, loot/predicates, map IDs, datapack registration, scheduled or persistent state, and player data/permissions.
5. Save/load/unload/restart behavior, including queued execution after a world unload, and two maps active simultaneously with identical original names.

These are cost drivers and acceptance obligations, not a claim that every map uses every mechanism. A plugin, mixin/mod, or server fork can theoretically implement the required context. A simple Bukkit command-preprocess hook is not enough evidence because native command blocks, function execution, selectors and engine-owned criteria have additional paths. A fork additionally carries Minecraft/Paper upgrade maintenance and plugin-interaction costs.

Saving a board per world and swapping the server singleton when a player teleports fails the concurrent case: two players can be in different maps at once. Swapping when worlds load/unload has the same problem while both worlds are loaded. Hiding a sidebar does not fix data contamination. Renaming a `deathCount` objective does not make its criterion world-sensitive.

## Cost comparison without invented estimates

| Route | What is actually reduced | Main remaining cost |
| --- | --- | --- |
| Per-world UI only | Presentation leakage | Does not meet whole command-state isolation. |
| Adapt one map to one existing Paper server | Fixed map/content scope instead of arbitrary third-party maps | Complete map dependency audit, scoped selectors and identifiers, legacy behavior fixes, migration and end-to-end gameplay testing. Cost is currently unknown. |
| Generic same-process isolation on Paper | Reuses one process and current deployment platform | Context propagation through all native execution/state paths, persistence, coexistence and version maintenance. No reviewed turnkey candidate met the full contract. |
| Evaluate Cosmos/Sponge | Reuses an implemented per-world scoreboard subsystem | Older supported versions, unverified broader isolation, engine migration, replacement/porting of current Bukkit plugins, and separate map compatibility validation. |
| Rewrite game on Minestom | Explicit instance-owned game state | Reimplementing required vanilla/game mechanics and plugin integrations; substantial scope shift for an imported adventure map. |
| Independent native server saves/processes | Native separation of scoreboard/storage/functions/players for each map instance | More runtime instances, routing/auth/transfer and on-demand lifecycle, backups, cross-server UX; legacy-version compatibility remains separate. |

No evidence supports a precise person-day estimate or a hardware minimum. Development cost and resident-memory cost are different questions. A separate process can be started on demand; simultaneous active maps still require their active server resources. Benchmark the actual runtime/map/player workload rather than turning JVM heap maxima into measured demand.

## Trials-specific audit boundary

The previous report already scanned 43,886 artifact chunks with zero NBT parse errors, specifically looking for scoreboard/death strings in command blocks. Do not repeat that scan as if it were a full audit. It established original `Deaths`, `total_deaths`, `join`, and related commands. It did not establish the total command graph or complete gameplay compatibility.

A reliable estimate requires an inventory of all executable content and state dependencies: command-block chains and activation, command minecarts/entities, functions/datapacks if any, selectors and nested execute paths, state IDs and collision domains, checkpoints/respawn/win conditions, and the map's intended Minecraft version. The artifact contains mixed historical chunk versions; NBT DataFixer success is not proof that all old commands/redstone/gameplay have current-version semantics.

The deliverable of that audit should be a dependency map plus an explicit compatibility target and test scenarios. Only then can work be split into bounded adaptations and estimated. “Only adapt Trials” is narrower than “support every map”, but cannot honestly be called cheap or assigned a small timeline yet.

## Files Found / Related Specs

- `.trellis/tasks/11-18-config-bundle/research/scoreboard-world-scope.md`: prior actual-runtime bytecode, persisted objectives, artifact command coordinates, and MVI source findings.
- `.tmp/world-lifecycle-manual/runtime/versions/26.2/paper-26.2.jar`: read-only native selector/storage verification; version/hash recorded in prior report.
- `.tmp/AdvancedSlimePaper/README.md`: project goal is world loading/storage.
- `.tmp/AdvancedSlimePaper/aspaper-server/src/main/java/com/infernalsuite/asp/SlimeNMSBridgeImpl.java:75`: global default-world initialization behavior.
- `.trellis/spec/backend/world-artifacts.md`: immutable artifact and shared native-state boundaries; not modified by this research.
- `docs/PAPER-WORLD-SOP.md:503`: existing same-server top-level-state boundary.

## Caveats / Not Found

- No candidate was installed, executed, or certified on Paper 26.2 during this research. Official/source evidence and live integration evidence are separated above.
- No proof of a current ready-made full command-state isolation product emerged from this bounded candidate review. This is not an exhaustive ecosystem census and does not justify saying no solution exists.
- Cosmos was checked at the API-8 development commit and old public release metadata. Broad compatibility is not inferred across versions or Sponge variants.
- A limited Sponge source/index check did not establish a full per-world native command-state contract; absence of matches in those files is not proof of absence across the engine.
- No SSH, player login, scoreboard mutation, world load/unload, configuration edit, or map/source-code modification occurred.

## Search Summary

- Official GitHub repository search: `perworldscoreboard OR "per-world scoreboard"`, 1 query; broad results did not establish a full-isolation candidate.
- Official GitHub issue search: `"per world" scoreboard repo:PaperMC/Paper`, 1 query; no full-isolation solution was established, and unrelated issue bodies were not treated as authority.
- Other calls were direct reads of the listed official README/source/release/metadata URLs and local files. OpenCLI registry/help were checked; its GitHub adapter exposes login/whoami but no search command, so bounded public GitHub HTTP queries were used. No AI website or logged-in browser search was used.
