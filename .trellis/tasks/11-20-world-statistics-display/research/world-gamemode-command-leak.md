# Research: adventure mode after entering world

Date: 2026-11-20. Read-only manual-runtime investigation; no player, map,
configuration or plugin changes.

## Finding

Entering `world` is configured to apply survival. A Trials command block
subsequently targets players across dimensions with `gamemode adventure @a`.
The current runtime preserves direct command output naming Snorlax at the
same time as the latest exit from Trials. This is map-command scope leakage,
not the intended destination-world policy or a WorldLifecycle mode feature.

## Configuration and ownership

- Manual `plugins/Multiverse-Core/worlds.yml`: `minecraft:overworld` has
  `gamemode: survival`; `minecraft:trials` has `gamemode: adventure`.
- Core `world.enforce-gamemode: true`; enforcement delay is one tick.
- Core `MVPlayerListener.playerChangedWorld` schedules the destination-world
  enforcement; `EnforcementHandler.handleGameModeEnforcement` reads the
  player's current world and applies its configured mode unless bypassed.
- Manual `ops.json` is empty and the manual permission group grants entry/
  status/teleport permissions, without gamemode bypass.
- Formal WorldLifecycle source has no `setGameMode` call; `/wltp` delegates
  lifecycle-aware entry to the Multiverse teleporter.
- MVI saves/restores selected profile state on transitions. It does not
  prevent a later native command from changing a player in another world.

## Incident and live-save evidence

At 15:07:43 the server accepted `/wltp world`; at 15:07:44 it recorded
`WL ENTER_OK Snorlax world=world mode=resume`. The client recorded both
`Entered world.` and `Your game mode has been updated to Adventure Mode`
at 15:07:44.

During investigation the player repeated the transition at 15:14:36:

- Server: `WL ENTER_OK Snorlax world=world mode=resume`.
- Trials unloaded at 15:14:46 after the existing idle delay.
- At 15:14:49, read-only console query
  `execute as Snorlax run data get entity @s playerGameType` returned `2`
  (adventure). Queries of Trials command blocks at that time returned
  unknown dimension because the world had already unloaded; they did not
  load it or alter blocks.

The just-saved region file was then read without modification:

`.tmp/world-lifecycle-manual/runtime/world/dimensions/minecraft/trials/region/r.-3.-1.mca`

Chunk index 757, command block at **(-1195, 60, -133)**:

```text
Command: gamemode adventure @a
SuccessCount: 1
LastExecution: 18564623
LastOutput timestamp: [15:14:36]
LastOutput translate: commands.gamemode.success.other
LastOutput arguments: Snorlax; gameMode.adventure
```

This directly connects a Trials command to the affected player and latest
exit timestamp. It does not claim every command executed in the earlier
15:07 transition was individually captured. The older immutable artifact
survey also contains this command at the same coordinate, so it was not
introduced by the lifecycle or statistics work.

The artifact survey found six explicit `gamemode adventure @a` commands
plus one targetless `gamemode adventure`. The live region reads retain
those commands. The latter targetless command has an old
`permissions.requires.player` failure and is not evidence for this change.

## Boundary and next action

The expected policy remains survival in `world`, adventure in `trials`.
Dimension-local command blocks do not automatically confine bare `@a` to
that dimension. MVI profile isolation and private sidebar presentation
cannot isolate arbitrary map commands.

An adaptation belongs in the imported map's command policy, with an audit
of selectors and other shared command state. A selector with an appropriate
spatial constraint such as `@a[distance=0..]` is dimension-local in the
command's execution context; `execute in <dimension>` alone does not make
bare `@a` dimension-local. Any adaptation still needs review of commands
that intentionally target another execution dimension.

No adaptation or repeated gamemode override was applied. A periodic plugin
override would compete with map commands and would not repair their scope.

The follow-up `trials-command-scope-audit.md` audits all 1,137 stored command
occurrences. It identifies six exact gamemode adaptations, but also unbounded
inventory clearing, effects, teleports, spawnpoint changes and entity/item
operations. Its 644 lexical review candidates are not 644 required edits.
Therefore fixing only the mode commands cannot establish safe concurrent
independent gameplay in this imported map. Keeping arbitrary maps' original
global command assumptions calls for an independent server boundary; reviewed
on-demand orchestration candidates are documented in
`../../11-18-config-bundle/research/map-isolation-costs.md`. This is a design
recommendation, not a deployed architecture change.

## Evidence references

- Manual server/client rotatable logs at the timestamps above.
- `.trellis/tasks/11-18-config-bundle/research/death-objective-command-evidence.json`:
  immutable artifact command inventory (`all_commands`).
- `.tmp/mv-core-src/src/main/java/org/mvplugins/multiverse/core/listeners/MVPlayerListener.java`.
- `.tmp/mv-core-src/src/main/java/org/mvplugins/multiverse/core/world/helpers/EnforcementHandler.java`.
