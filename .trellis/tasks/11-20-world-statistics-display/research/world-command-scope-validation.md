# Native selector scope: isolated Paper validation

Date: 2026-11-20, 15:26–15:27 Asia/Shanghai.

## Result

Real Paper 26.2 build 135 confirms that bare `@a` reaches players across
worlds. Adding `distance=0..` restricts this selector to the command execution
dimension. `execute in minecraft:trials` alone does not restrict bare `@a`.

Two fresh offline protocol clients stayed connected throughout:

- ScopeA1120: Bukkit `world`, dimension `minecraft:overworld`.
- ScopeB1120: Bukkit `trials`, dimension `minecraft:trials`.

Each case explicitly reset both players to survival. After waiting 1.2 seconds,
the observer confirmed both still had survival before executing the case.
After another 1.2 seconds it read actual Bukkit game modes on the main thread.

| Console command | A in world | B in trials | Observed ticks A/B |
| --- | --- | --- | --- |
| `execute at ScopeB1120 run gamemode adventure @a` | Adventure | Adventure | 196 / 199 |
| `execute in minecraft:trials run gamemode adventure @a` | Adventure | Adventure | 256 / 260 |
| `execute at ScopeB1120 run gamemode adventure @a[distance=0..]` | Survival | Adventure | 308 / 311 |

`execute at ScopeB1120` supplies the Trials dimension and position to the
native command parser. It does not change the executor to that player.
The bounded experiment did not reconstruct or trigger a command block.

## Fixture and controls

The runtime is an independent regular-file copy of the stopped
`.tmp/death-statistics-test/runtime`, made with `shutil.copytree/copy2` into
`.tmp/world-command-scope-test/runtime`. It uses the existing copied map,
Multiverse-Core 5.8.1, MVI 5.3.6 and MultiverseWorldLifecycle 0.1.0. It is not
the manual gameplay runtime. No source artifact was changed.

Core's existing `enforce-gamemode: true` and one-tick enforcement delay were
left enabled. Both clients entered their destinations using `/wltp ... exact`.
Before the cases, settled destination policy was observed as A survival and
B adventure (ticks 134/138). No later world transitions occurred. Stable
survival resets at ticks 165/168, 226/229 and 274/281 show that delayed Core
enforcement did not overwrite or mask the tested commands.

The fixture observer disabled ambient map command blocks with
`minecraft:command_blocks_work=false` to isolate each command. It set test
subjects invulnerable and gravity-free and granted entry permissions; it
never called `setGameMode`. Explicit native console resets were the only
game-mode setup mutations. The copied statistics observer was disabled in
this fixture before startup.

The bots used the existing login/configuration implementation with corrected
26.2 chunk-batch ACK and respawn/player-loaded packet handling. No real user
identity or production connection participated.

## Evidence and limits

- `.tmp/world-command-scope-test/run.py`: fixture, native commands and assertions.
- `.tmp/world-command-scope-test/ScopeObserver.java`: actual main-thread reads.
- `.tmp/world-command-scope-test/results.json`: 10/10 assertions passed.
- `.tmp/world-command-scope-test/server-run-1.log`: version, joins, commands'
  effects and graceful shutdown.
- `.tmp/world-command-scope-test/runtime/query-r1-81001.json` through
  `query-r1-81014.json`: raw world/mode/tick observations.
- Paper bootstrap JAR SHA256:
  `ef3dbc68b013deafdbbee3bebf1ba351671ebcda94a8f136809b7532d5ba2fe1`.

The test server stopped gracefully with exit 0 at 15:27:36; its owned port
25599 was confirmed closed. The existing manual server on 25598 was untouched.

This proves the selected native command's scope, not general map isolation
or a repaired map. The manual Trials command blocks remain unchanged. Other
unbounded selectors, commands that intentionally change execution dimension,
and server-wide scoreboard/team state require their own policy and audit.
Changing six gamemode commands alone cannot establish safe full-map play.
