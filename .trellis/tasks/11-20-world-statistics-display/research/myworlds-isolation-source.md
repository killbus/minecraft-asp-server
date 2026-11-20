# MyWorlds source evaluation: player state versus map isolation

Read-only review on 2026-11-20 of existing shallow checkout
`.tmp/myworlds-src`, origin `bergerhealer/MyWorlds`, commit
`15b4c4757ecdb176510491dbfe2eb5debe1044d8`. Public release compatibility is a
separate check; this report does not equate the checkout with a released JAR.
No installation, runtime start, map adaptation or existing state change.

The coordinating session separately retrieved these current public facts:

- [Spiget resource metadata](https://api.spiget.org/v2/resources/39594)
  mirrors the Spigot listing and declares tested versions 26.1, 26.2 and
  26.3, among older versions. Direct Spigot access was Cloudflare-blocked.
  This is declared support from the mirrored listing, not our compatibility
  test of MyWorlds/BKCommonLib on those versions.
- [Official MyWorlds documentation](https://wiki.traincarts.net/p/MyWorlds)
  documents `useWorldInventories=true` with inventories disabled by default,
  plus merge/split groups, consistent with the inspected implementation.
- `git ls-remote` confirmed the inspected commit was still upstream HEAD.
  [GitHub releases](https://api.github.com/repos/bergerhealer/MyWorlds/releases)
  returned an empty list; this does not mean the project has no distributed
  builds. [Official CI build 377](https://ci.mg-dev.eu/job/MyWorlds/377/) was
  the last successful build, timestamp `1793829376425`, with artifact
  `MyWorlds-2.0.2-SNAPSHOT-377.jar`. No binary was installed or validated here.

## Decision relevant to the incident

MyWorlds provides substantial world management and player-profile switching.
The reviewed implementation does not establish isolation of native command
selectors or the server main scoreboard. Replacing Multiverse with it has no
demonstrated mechanism that would confine `gamemode adventure @a` or `clear @a`
to their source map. A profile restore when entering a world does not prevent
a command in another loaded world from mutating that player's current state.

Two important capabilities also differ from the present accepted contract:
`reloadWhenEmpty` immediately loads the world again after unloading, and the
reviewed ordinary teleport/last-position commands require a loaded target.
Neither is evidence for the current idle-unload plus cold-entry behavior.

## Positive capabilities and exact boundaries

| Capability | Source evidence and qualification |
| --- | --- |
| Separate or shared inventories | `WorldInventory` persists `inventories.yml`, supports detach and merge, and assigns merged worlds one inventory object. [load/save](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/WorldInventory.java#L72), [detach/merge](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/WorldInventory.java#L160). |
| More than item stacks | `MWPlayerDataController.refreshState` reads/migrates the destination NBT profile and restores attributes, inventory/equipment, respawn point, hunger, ender chest, potion effects, XP, air/fire/fall state, absorption, stored gamemode and health. [implementation](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/MWPlayerDataController.java#L660). The feature defaults off via `useWorldInventories=false`; a keep-inventory permission can bypass restoration. |
| Profile ownership | On leaving, MyWorlds saves the old profile; on entering it refreshes state then applies world policy. [world transition handlers](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/WorldConfig.java#L841). `PlayerDataFileCollection` selects the world/group inventory file separately from the world's position file. [file selection](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/playerdata/PlayerDataFileCollection.java#L69). |
| Last position | Records `lastPlayerPositions` in MyWorlds player metadata; `getPlayerWorldSpawn` uses a remembered location when enabled, otherwise falls back to applicable bed/world spawn. [metadata](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/MWPlayerDataController.java#L66), [destination selection](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/WorldManager.java#L872). This is useful resume behavior, not proof of arbitrary exact-destination preservation across every teleport integration. |
| World load/unload | Uses Bukkit world creation/unloading within the existing server. [createWorld](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/WorldManager.java#L530), [unload](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/WorldManager.java#L351). |
| Empty-world action | `updateReload` checks zero players, unloads, then immediately calls `loadWorld`. It is a reload policy, not a persistent idle unload. [exact branch](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/WorldConfig.java#L967). |
| Cold teleport limitation | `/tpp` reports the world is not loaded; `lastposition tp` also returns on an unloaded world. [ordinary teleport](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/commands/TeleportPortal.java#L120), [last-position teleport](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/commands/WorldLastPosition.java#L170). |

## Statistics, selectors and native scoreboard investigation

The source search covered `src/` for `Statistic`, `Scoreboard`,
`ServerCommandEvent`, `PlayerCommandPreprocessEvent`,
`RemoteServerCommandEvent`, `EntitySelector`, `ProcessBuilder`,
`Runtime.getRuntime`, `ServerSocket`, `PluginMessage` and `BungeeCord`.
No implementation matches established game-statistics swapping, a native
selector interception layer, per-world native scoreboards, or separate server
process/proxy orchestration. The actual profile restore method was read rather
than relying only on the absence of terms.

One potentially misleading match is `copyGlobalPlayerData`'s comment
`bukkit player stats`: the code copies `lastPlayed`, `firstPlayed` and
`lastKnownName`, followed by recipe-book data. It does not copy the Bukkit
`Statistic` counters required by MVI's `game_statistics` contract.
[Exact method](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/MWPlayerDataController.java#L1323).
Therefore full game-statistics isolation is **not established** by this source
review; inventory separation must not be presented as proof of it.

Another useful counterexample is `Util.parsePlayerName`: its `@p` handling
does select a nearby player from the sender's world. This is a helper called
by MyWorlds' own commands, not a replacement for vanilla `@a` resolution.
[helper](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/Util.java#L262),
[own command dispatch](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/commands/registry/MyWorldsCommands.java#L27).
No native `gamemode`, `clear` or command-block dispatch override was found.

This is a bounded capability judgement about this revision, not a claim that
no extension or future revision could ever supply such features. Its actual
world creation path creates Bukkit worlds in one server, so the command-scope
problem remains relevant even with independently stored player profiles.

## Dependencies and switching implications

BKCommonLib is a runtime requirement despite appearing in top-level
`softdepend`: the preloader declares it under `depend`, and MyWorlds startup
checks `Common:CommonItemStack` plus `Common:LoadableWorld`, refusing without
the required capabilities (the latter error names a newer BKCommonLib 2.0.0
build). [plugin descriptor](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/plugin.yml#L15),
[startup gates](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/MyWorlds.java#L240).
The compatible pair of published binaries still needs release verification.

The `importFromMultiVerse` setting must not be mistaken for a working migration
path in this checkout: `MultiverseHandler.readWorldConfiguration` immediately
returns `false`; the former implementation is commented out.
[current implementation](https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/external/MultiverseHandler.java#L27).
It supplies no evidence that MVI profiles/group assignments would migrate.

For this deployment, a switch would require explicit ownership and migration
decisions for world registration, profile storage, sharing groups, last
positions, login behavior and idle loading. Enabling both profile restorers
would put two components in charge of the same inventory/health state on
world transitions. The current WorldLifecycle and statistics-board integration
use Multiverse APIs/MVI groups, so removing those dependencies is not a
configuration-only replacement.

MyWorlds remains a credible alternative world/profile manager to evaluate on
its own requirements. On the specific reported cross-world commands, the
review found no added isolation mechanism that justifies migration as the
repair. Existing `gamemode @a` and `clear @a` map commands still need a scoped
command policy, or an architecture providing separate server command state.
