# Research: TheNextLvl Worlds isolation boundary

- Query: Does TheNextLvl Worlds isolate each map's command/selectors, native scoreboard or player state more deeply than a conventional single-Paper world manager?
- Scope: exact local source inspection, plus the already installed Paper 26.2 `ServerLevel` implementation; no runtime installation or mutation.
- Date: 2026-11-20
- Source: `.tmp/thenextlvl-worlds`, shallow clone at commit `44885533e557bc7a9f864153189051e95efc767d` as supplied by root. No git operation was performed by this researcher.
- User references: https://modrinth.com/plugin/worlds-1 and https://github.com/TheNextLvl-net/worlds. Root owns release metadata/lifecycle compatibility investigation; this report addresses source boundaries only.

### Release provenance supplied by root

After the initial source inspection, root fetched the public Modrinth project/version APIs and the **4.5.1 release tag**, commit `bc50f825922c79bf4594795d23b31c73d81a3f87`. Root reports release 4.5.1 dated 2026-11-08, Paper/Folia support for 26.1.2, 26.2 and 26.3, and GPL-3.0 licensing. The inspected main branch identifies itself as unreleased 4.5.2.

Root compared 4.5.1 with the inspected main commit: only nine build/telemetry files differ, with one telemetry line changed in WorldsPlugin; the world-creation/listener/selector logic reviewed here is unchanged. Thus the isolation conclusion also applies to the actual published 4.5.1 source, rather than depending on an unreleased implementation.

Preferred release permalinks for the decisive evidence:

- [4.5.1 shared-server retrieval and creation](https://github.com/TheNextLvl-net/worlds/blob/bc50f825922c79bf4594795d23b31c73d81a3f87/version-specifics/v26.2/src/main/java/net/thenextlvl/worlds/versions/v26_2/SimpleVersionHandler.java#L171).
- [4.5.1 ordinary ServerLevel constructor](https://github.com/TheNextLvl-net/worlds/blob/bc50f825922c79bf4594795d23b31c73d81a3f87/version-specifics/v26.2/src/main/java/net/thenextlvl/worlds/versions/v26_2/SimpleVersionHandler.java#L371).
- [4.5.1 register into existing MinecraftServer](https://github.com/TheNextLvl-net/worlds/blob/bc50f825922c79bf4594795d23b31c73d81a3f87/version-specifics/v26.2/src/main/java/net/thenextlvl/worlds/versions/v26_2/SimpleVersionHandler.java#L408).
- [4.5.1 listener/command registration](https://github.com/TheNextLvl-net/worlds/blob/bc50f825922c79bf4594795d23b31c73d81a3f87/plugin/src/main/java/net/thenextlvl/worlds/WorldsPlugin.java#L189).
- [4.5.1 teleport permission enforcement](https://github.com/TheNextLvl-net/worlds/blob/bc50f825922c79bf4594795d23b31c73d81a3f87/plugin/src/main/java/net/thenextlvl/worlds/listener/TeleportListener.java#L19).
- [4.5.1 player teleport and destination selection](https://github.com/TheNextLvl-net/worlds/blob/bc50f825922c79bf4594795d23b31c73d81a3f87/plugin/src/main/java/net/thenextlvl/worlds/command/WorldTeleportCommand.java#L57).

Detailed links below retain the exact initially inspected commit for audit provenance; root's release comparison establishes the relevant code is the same.

## Findings

### Conclusion

This version of **Worlds creates native dimensions inside the existing MinecraftServer**. It has useful modern creation, generation, storage, portal and permission capabilities, but the inspected source does not supply a separate command universe, native scoreboard or per-world player profile store.

Consequently, replacing Multiverse with this plugin alone would not confine `gamemode adventure @a`, `clear @a`, unbounded `@e`, or native main-scoreboard commands to the imported map. This conclusion comes from its construction/registration path and actual Paper selection/scoreboard behavior, not from its “world manager” label.

### Positive implementation: actual dimension creation

In the 26.2 version handler:

1. [`SimpleVersionHandler.java:171`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/version-specifics/v26.2/src/main/java/net/thenextlvl/worlds/versions/v26_2/SimpleVersionHandler.java#L171) obtains the current `CraftServer` and calls its `getServer()` for `console`.
2. At lines 226–228 it reuses that server's `worldLoaderContext`, registry access and dimension-stem registry. At line 269 it reads the same server's `PrimaryLevelData`.
3. [`:364`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/version-specifics/v26.2/src/main/java/net/thenextlvl/worlds/versions/v26_2/SimpleVersionHandler.java#L364) creates `SavedDataStorage` at the selected dimension's `data` directory and stores generation settings. This is real dimension-local saved data, but it is not a separate server or a replacement native scoreboard.
4. [`:371`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/version-specifics/v26.2/src/main/java/net/thenextlvl/worlds/versions/v26_2/SimpleVersionHandler.java#L371) calls `new ServerLevel(console, ..., console.storageSource, ..., dimensionKey, ...)`. It constructs ordinary `ServerLevel`, not an isolation subclass.
5. [`:408`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/version-specifics/v26.2/src/main/java/net/thenextlvl/worlds/versions/v26_2/SimpleVersionHandler.java#L408) calls `console.addLevel(serverLevel)`, then `console.initWorld` and `console.prepareLevel`.

The 26.3 handler has the same shared-server construction at [`v26_3/SimpleVersionHandler.java:371`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/version-specifics/v26.3/src/main/java/net/thenextlvl/worlds/versions/v26_3/SimpleVersionHandler.java#L371).

The native storage layout is explicit in [`WorldsPlugin.java:450`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/plugin/src/main/java/net/thenextlvl/worlds/WorldsPlugin.java#L450): dimensions resolve under the existing server level directory's `dimensions/<namespace>/<value>`. File separation is useful; it does not change shared command selection or server globals.

### Native scoreboard boundary

The currently installed Paper 26.2 `ServerLevel.getScoreboard()` was rechecked with `javap -p -c`. Its entire effective operation is:

```text
return this.server.getScoreboard();
```

Worlds passes the same `console` to every ordinary ServerLevel. The inspected repository contains no `Scoreboard`/`scoreboard` implementation, accessor override, scoreboard manager swap, or per-player scoreboard projection. A dimension's separate `SavedDataStorage` does not override the getter above. Therefore native objectives, scoreholders, teams and display slots remain subject to the shared Paper server scoreboard behavior described in the existing project spec.

This is an implementation-level conclusion for the source snapshot plus Paper 26.2. It is not a claim that the plugin cannot be extended in the future or that another independently installed plugin could not supply presentation/state behavior.

### Commands and selectors: inspected hooks do not add isolation

[`WorldsPlugin.java:189`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/plugin/src/main/java/net/thenextlvl/worlds/WorldsPlugin.java#L189) registers:

- plugin-enable listener for generator warnings;
- portal listener;
- teleport listener;
- world-load listener;
- optional Folia portal listener.

[`WorldsPlugin.java:200`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/plugin/src/main/java/net/thenextlvl/worlds/WorldsPlugin.java#L200) registers save-all/save-off/save-on, the plugin's world command, and a setworldspawn command. It does not replace `gamemode`, `clear`, `execute`, native scoreboard commands or the selector evaluator.

The source-wide search found no command-block interception, `ServerCommandEvent`, `PlayerCommandPreprocessEvent`, `EntitySelectorParser`/`EntitySelectorOptions` modification or instrumentation replacing those internals. The only selector resolver usage is ordinary Paper `ArgumentTypes.entities()` in the plugin's own teleport command: [`WorldTeleportCommand.java:38`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/plugin/src/main/java/net/thenextlvl/worlds/command/WorldTeleportCommand.java#L38), resolved against the command source at line 57. It is not a global selector policy.

Existing actual-Paper evidence remains applicable: `EntitySelector.findPlayers` uses the server player list when a selector is not world-limited; `findEntities` can iterate `MinecraftServer.getAllLevels()`. Worlds adds levels to that same server registry. See `trials-command-scope-audit.md` and its saved `EntitySelector` disassembly for the exact branches. Creating worlds through a different plugin does not alter those paths.

### Important positive counterexample: teleport access control

[`TeleportListener.java:19`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/plugin/src/main/java/net/thenextlvl/worlds/listener/TeleportListener.java#L19) checks a cross-world teleport's destination entry permission and cancels if denied. This is real enforcement and can block a teleport into a world the player is forbidden to enter.

It is **not** a general map-origin command boundary: permitted users may still be selected by a command in another dimension, and gamemode/inventory/effect/score changes do not run through a teleport event. Default entry permissions are registered `PermissionDefault.TRUE` by [`WorldListener.java:48`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/plugin/src/main/java/net/thenextlvl/worlds/listener/WorldListener.java#L48). Thus its permission system does not substantiate “all commands stay inside their source map.”

Another real capability is explicit per-world gamerule administration: [`WorldGameRuleCommand.java:62`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/plugin/src/main/java/net/thenextlvl/worlds/command/WorldGameRuleCommand.java#L62) gets the chosen Bukkit World and calls `world.setGameRule`. This manages a world property; it does not scope arbitrary native target selectors.

### Persistent player state ownership

The plugin's registry persistence is lightweight world metadata:

- [`SimpleWorldRegistry.java:28`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/plugin/src/main/java/net/thenextlvl/worlds/SimpleWorldRegistry.java#L28) selects `worlds.dat` inside plugin data.
- [`WorldRegistry.java:139`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/api/src/main/java/net/thenextlvl/worlds/WorldRegistry.java#L139) defines each entry as `(Dimension dimension, boolean enabled, Generator generator)`.

Searches found no player inventory/health/statistics snapshots or world-change profile restoration. No `PlayerChangedWorldEvent`, inventory accessor, statistic setter, `playerdata` store, or join profile loader was found. A `PlayerQuitEvent` exists in [`PortalHandler.java:62`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/version-specifics/src/main/java/net/thenextlvl/worlds/versions/PortalHandler.java#L62), but it only removes transient portal-processor/tick-counter entries; it is not player persistence. Teleports operate on the existing Player/Entity with `teleportAsync`.

Therefore Worlds does not itself replace the already validated MVI `game_statistics`/inventory/health profile ownership. This report does not infer MVI compatibility with Worlds; that is a separate integration question owned by root.

### 26.2/26.3 are present in source

This is not an outdated-source rejection:

- [`WorldsPlugin.java:107`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/plugin/src/main/java/net/thenextlvl/worlds/WorldsPlugin.java#L107) explicitly selects version handlers for 26.1.2, 26.2 and 26.3.
- [`settings.gradle.kts:9`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/settings.gradle.kts#L9) includes 26.2 and 26.3 modules.
- [`plugin/build.gradle.kts:18`](https://github.com/TheNextLvl-net/worlds/blob/44885533e557bc7a9f864153189051e95efc767d/plugin/build.gradle.kts#L18) includes both version implementations; their build files target `foliaDevBundle("26.2.+")` and `foliaDevBundle("26.3.+")`.

These establish intended source support. Published artifact/version claims and actual installation validation are separate and were not duplicated here.

## Positive capabilities relevant to evaluating it fairly

The source and README support treating Worlds as a credible modern world-management alternative: native dimension keys/layout, custom dimension stems, flat/void/single-biome generation, biome providers/generators, portal linking, entry permissions, per-world gamerules, and import/clone/backup/regeneration tooling. Its narrower data ownership is intentional: the README emphasizes “Minimal Extra Data.” Those benefits can motivate a management/tooling evaluation independently of the map-command isolation requirement.

For the current symptom, the decisive missing capability is a change to the execution/selection/global-state boundary. The inspected source supplies no such capability. Switching managers to seek that specific result would leave the known map commands' reach intact.

### Integration/lifecycle facts supplied by root

Root's separate review found that enabled registry entries are loaded when the primary world loads; the `WorldArgument` resolver requires an already loaded Bukkit World; and the teleport command defaults to spawn or explicit coordinates, without an MVI-style resume operation. The present Multiverse-WorldLifecycle plugin depends on Multiverse-Core and MVI, and MVI itself declares a Multiverse-Core dependency. Worlds therefore is not a direct binary replacement for the currently validated stack. These observations constrain migration effort; they are not the reason for the independent shared-command/shared-scoreboard conclusion above.

## Files Found

- `version-specifics/v26.2/.../SimpleVersionHandler.java`: current-server native level creation and storage.
- `version-specifics/v26.3/.../SimpleVersionHandler.java`: analogous 26.3 creation path.
- `plugin/.../WorldsPlugin.java`: version dispatch, listeners, commands, native dimension directories.
- `plugin/.../listener/TeleportListener.java`: destination entry permission enforcement.
- `plugin/.../listener/WorldListener.java`: world registry loading and entry-permission registration.
- `plugin/.../command/WorldTeleportCommand.java`: Paper selector resolution and ordinary async teleport.
- `plugin/.../command/WorldGameRuleCommand.java`: chosen-world property administration.
- `plugin/.../SimpleWorldRegistry.java`, `api/.../WorldRegistry.java`: world metadata persistence.
- `version-specifics/.../PortalHandler.java`: transient entity/player portal processing.

All relative paths in this section are rooted in `.tmp/thenextlvl-worlds`.

## Related Specs

- `.trellis/spec/backend/world-artifacts.md`: artifact separation does not establish separate live native scoreboards.
- `.trellis/spec/backend/multiverse-player-state.md`: MVI player state, lifecycle and presentation are separate ownership domains.
- `trials-command-scope-audit.md`: actual selector evaluation and known imported-map cross-world command surface.

## Caveats / Not Found

- This was a bounded exact-source audit, not a runtime install, full compatibility test, build or dependency binary audit.
- Search absence is supported by reviewed creation/listener/command paths; it is not a claim about every future release or external addon.
- Folia scheduling changes execution threading, but the inspected Folia hooks do not establish separate server globals. This report's concrete bytecode verification used the current Paper 26.2 runtime.
- No live fixture, clone source, map, player or settings files were changed. This report is the sole write.
