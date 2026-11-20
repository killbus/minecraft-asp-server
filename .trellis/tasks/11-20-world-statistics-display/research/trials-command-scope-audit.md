# Research: Imported map command scope audit

- Query: Does adapting six `gamemode adventure @a` commands solve the current symptom, and what definite cross-world command effects remain?
- Scope: internal, read-only command inventory and installed Paper 26.2 bytecode; proposed changes only.
- Date: 2026-11-20

## Findings

### Decision

An exact six-entry adaptation from `gamemode adventure @a` to `gamemode adventure @a[distance=0..]` closes the six identified map commands that can set another dimension's players to adventure. It addresses the confirmed gamemode mechanism, but is **not enough to call this map safe for concurrent independent worlds**. The inventory also contains commands capable of clearing other players' inventories, resetting their effects/spawn points, teleporting them, altering dropped items/entities, and broadcasting UI across dimensions.

These are source-level reachability findings, not claims every command ran against an outside player. Only the gamemode incident has the direct live command output described in `world-gamemode-command-leak.md`. Activation, loaded chunks, redstone state, permissions and command validity determine whether a stored command executes.

### Input and reproducible output

Input: `.trellis/tasks/11-18-config-bundle/research/death-objective-command-evidence.json`, specifically `all_commands` only. Its SHA-256 is `b527c88da63bcbc8a690631d4c230e98df4682599db4c6371a4943fee09646d2`.

The previous immutable-artifact scan reports 43,886 terrain chunks, 4,386 entity chunks, zero parse failures, **1,137 command occurrences / 985 unique command strings**. This analysis does not count historical `LastOutput` click commands as executable fields.

Outputs under `.tmp/trials-command-scope-audit/`:

- `audit.py`: read-only lexical inventory classifier; preserves quoted strings, balances selector brackets, and records source positions. It is an audit helper, **not a command parser or rewrite tool**.
- `audit.json`: all original rows plus detected selectors and scope categories.
- `gamemode-proposal.json`: six exact source positions, NBT paths, expected old strings, and proposed new strings; status `proposal-only; not applied`.
- `EntitySelector.javap.txt`, `EntitySelectorParser.javap.txt`, `EntitySelectorOptions.javap.txt`: disassembly from the actual manual runtime's Paper 26.2 JAR.

Rerun: `python -B .tmp/trials-command-scope-audit/audit.py`. It only writes its scratch audit/proposal files. No live map, player profile, artifact or configuration was changed.

### Actual selector semantics, including nearest-player and entity cases

The finding is based on both parser **and selection** logic:

- `EntitySelectorParser.parseSelector`, saved disassembly line 483: `@a` sets all-player/arbitrary order; `@p` sets one-player/nearest order; `@e` includes entities. These branches do not set `worldLimited`.
- `EntitySelector.findPlayers`, line 369: at bytecode 170 it branches on `isWorldLimited`. True uses source `ServerLevel.getPlayers`; false enumerates **server `PlayerList.getPlayers()`**, applies predicates, and then ordering/limit. The global list invocation is saved at line 466. Thus unbounded `@p` may choose a player in another dimension based on coordinate distance; nearest sorting is not a dimension filter.
- `EntitySelector.findEntities`, line 162: at bytecode 233 it branches on `isWorldLimited`; false enumerates **`MinecraftServer.getAllLevels()`** and adds matching entities. The all-levels path is saved at line 283. Thus unbounded `@e[type=item]`, wardens and area-effect clouds can reach other loaded dimensions too.
- `EntitySelectorOptions`, lines 1509–1724: handlers for `x`, `y`, `z`, `dx`, `dy`, `dz`, and `distance` call `setWorldLimited`. `distance=0..` is an unlimited nonnegative distance in the execution dimension, so it constrains dimension without choosing an arbitrary radius.
- `scores`, `tag`, `type`, `limit`, and `sort` without spatial arguments do not supply this boundary. `@s` inherits whichever executor an earlier command selected.

Changing execution dimension with `execute in` would only change selector context; it would not itself make a bare all-player selector local. Likewise, `execute as` changes executor, not execution position/dimension. A later bare selector is evaluated afresh and does not inherit an earlier selector's candidate set.

### Selector occurrence counts

Counts are tokens across command occurrences, not distinct commands or required edits:

| Selector | Spatially constrained | Unbounded | Executor-relative |
| --- | ---: | ---: | ---: |
| `@a` | 207 | 376 | — |
| `@p` | 31 | 212 | — |
| `@e` | 3 | 78 | — |
| `@s` | — | — | 32 |

**644 command occurrences contain at least one unbounded selector.** This is an audit queue, not 644 confirmed player-harming actions and not permission for 644 automated edits. Some are harmless repetition of map-local `setblock` after a correctly spatially constrained trigger.

### Concrete remaining player effects

| Command family | Occurrences | Exact example and source block | Remaining cross-world effect if executed |
| --- | ---: | --- | --- |
| `clear @a` | 2 | `(-1289,62,-221)` and `(-1197,61,-146)` both `/clear @a` | Clear inventories of online players outside the map. |
| `effect clear @a` | 4 | `(-1195,60,-128)`, `(-1116,25,395)`, `(-1732,66,3002)`, `(-1687,84,3161)` | Remove outside players' effects. The separate targetless `/effect clear` is not counted here. |
| `tp @a ...` | 5 | `(-951,55,427)` → `tp @a -1727 65 2967`; `(-1291,62,-222)` → `tp @a -1186 65 477`; `(-1180,56,-134)` → `/tp @a -1216 64 -142`; `(-2487,25,3306)` and `(-2480,25,3301)` → `/tp @a 210 79 597` | Select outside players and teleport them to the command's target position/dimension. |
| Direct `spawnpoint` | 69 | 59 use bare `@a`, 10 bare `@p`; e.g. `(-1204,61,-144)` → `spawnpoint @a -1216 64 -142` | Rewrite outside players' respawn position/dimension. |
| Nested `execute ... run spawnpoint` | 23 | `(-1081,26,370)` → `/execute positioned ~ ~ ~ as @p[distance=..3] run spawnpoint @a -1129 29 392` | A local trigger still executes a fresh unbounded target selection. Two target `@a`, 21 target bare `@p`. |
| Player item replacement | 2 | `(-1563,76,3238)` and `(-1561,77,3245)` → `execute as @a if items entity @s weapon minecart[!can_place_on] run item replace entity @s weapon with minecart[...]` | A matching held minecart outside the map can be replaced/retagged. Exact item-component syntax was not executed/validated in this audit. |
| Tags | 2 | `(-1191,60,-135)` and `(-1180,76,-133)` → `/tag @a[tag=!newplayer] add newplayer` | Add a shared entity tag to players outside the map. Tag-only filtering is not dimension-local. |
| Player score resets | 6 | `(-1203,61,-146)` → `scoreboard players reset @a death`; five `reset @a[scores={join=1..}] join` | Reset other-world players' global scoreboard entries. |
| Conditional give | 1 | `(-1203,61,-147)` → `execute as @a[scores={death=1..}] at @s run give @s minecraft:compass` | Give an item to an outside player who meets the shared score condition. `at @s` follows the globally selected player. |

Direct presentation commands: 175 `tellraw` (166 bare `@a`, 1 tag-filtered `@a`, 8 bare `@p`) and 48 `title` (46 bare `@a`, 1 tag-filtered `@a`, 1 bare `@p`). There is also one `execute ... run tellraw` and one `execute ... run title` with a global tag selector and bare `@p` destination. These can display map text to another world's player; a private statistics sidebar does not isolate chat/title packets.

### Entities and map progression are also affected

- **54 direct `kill` commands** use unbounded `@e`: 2 dropped-item clears, 8 warden kills, 44 area-effect-cloud deletions (some have nearest sorting/limits). These selectors can select matching entities in other loaded dimensions.
- **10 direct entity teleports** target unbounded wardens. They are separate from the five player teleport commands above.
- **10 nested item-replacement commands** select `@e[type=item]` without a spatial filter, then conditionally rewrite item contents/components (torches, redstone torches, signs). This can touch matching dropped items in other worlds if the stored syntax is accepted.
- Two zombie-villager commands select all matching entities globally: `(-2479,25,3307)` conditionally merges `{ConversionTime:90}` by score; `(-2479,25,3308)` records each selected entity's conversion timer in the global `con` objective. Their coordinate/score selection needs separate review.
- Two `execute unless entity @e[type=warden] run setblock ...` commands use global warden absence, so another world's warden can prevent map progression.
- Five `execute as @a[scores={join=1..}] run setblock ...` commands use global player scores as triggers, including `(-1195,60,-135)`. A matching outside player can trigger redstone in the map. Their paired score reset is also global.
- One command at `(320,59,519)` invokes `function namespace:run_upon_death` for `@a[scores={death_detector=1..}]`. The existence/content of that function was not established; do not assume its effects or silently rewrite it.

Of 224 `execute ... run setblock` entries, 217 have a spatial trigger, 5 use global join scores, and 2 use global warden absence. **65** contain a spatial first selector followed by `as @a run setblock`. For those 65, the second selector is global but `as` does not move the execution location: its immediate effect is multiplying execution of a map-local block write, not writing those same coordinates in all selected players' worlds. This is why a blanket “any unbounded selector means cross-world block destruction” claim would be wrong.

### Native shared state is a separate review

The inventory has 13 direct scoreboard commands: 6 player-score resets, 5 objective additions (`total_deaths`, `Deaths`, `join` twice, `con`), and 2 global display assignments (`sidebar Deaths`, `list total_deaths`). Selector localization cannot namespace these objectives or display slots. The established Paper main-scoreboard boundary still applies; simply localizing `@a` does not isolate arbitrary map score state.

There are also 21 gamerule, 8 difficulty, 6 time, 3 weather, 10 forceload and 1 setworldspawn commands. This bounded audit does not label all of them global: source-level/per-world behavior differs by command and Paper adaptation. They need command-specific validation before a complete coexistence claim. A universal selector replacement does not address commands without selectors.

### Minimum reviewable gamemode proposal

All six source strings are exactly `gamemode adventure @a`:

| Region | Chunk index | Block position |
| --- | ---: | --- |
| `r.-3.-1.mca` | 725 | `(-1199,60,-147)` |
| `r.-3.-1.mca` | 757 | `(-1195,60,-133)` |
| `r.-3.0.mca` | 794 | `(-1116,25,397)` |
| `r.-3.0.mca` | 881 | `(-1260,98,435)` |
| `r.-4.5.mca` | 883 | `(-1733,66,3005)` |
| `r.-4.6.mca` | 182 | `(-1688,84,3164)` |

The authoritative region/chunk/NBT paths are in `gamemode-proposal.json`, derived directly from the inventory. Proposed replacement is `gamemode adventure @a[distance=0..]`. A separate targetless `gamemode adventure` at `(-1204,61,-143)` is left unchanged; the prior live evidence shows it failed for lacking a player executor.

Apply only as a deliberate adaptation to a derived import/runtime copy after checking each expected old command, never by modifying the immutable source artifact or by applying a global string substitution. Test the exact symptom with two players in distinct dimensions while the map remains loaded, then verify in-map mode enforcement still works. That would complete a **gamemode-only correction**, not the broader command isolation review.

The next gameplay-safety tranche should review destructive/player-state selectors first (`clear`, `tp`, `spawnpoint`, `effect`, item replacement, entity deletion), then progression triggers/UI, and finally shared state. This is bounded map adaptation work, distinct from implementing a general per-world command engine. No reliable time estimate or “all safe” statement follows merely from the 644 lexical hits.

## Files Found and Related Specs

- `research/world-gamemode-command-leak.md`: live incident attribution and component ownership.
- `.trellis/tasks/11-18-config-bundle/research/death-objective-command-evidence.json`: immutable map command inventory with source coordinates.
- `.tmp/world-lifecycle-manual/runtime/versions/26.2/paper-26.2.jar`: actual selector evaluation implementation.
- `.trellis/spec/backend/world-artifacts.md`: immutable source and native shared-scoreboard boundary.
- `.trellis/spec/backend/multiverse-player-state.md`: MVI persistence does not prevent subsequent commands modifying active player state.

## Caveats / Not Found

- Lexical counts are not execution counts or complete Brigadier validation. Quoted JSON/SNBT content is not treated as current top-level selector syntax; recursive generated commands/functions require their own audit.
- Existing inventory captures stored `Command` fields; datapack functions, text click actions, plugins and later generated commands are not exhaustively covered.
- No source/runtime/player edits or network requests were made. Scratch outputs and this report are the only writes.
