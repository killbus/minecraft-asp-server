# MultiverseStatisticsBoard

An online death leaderboard for the player's active Multiverse-Inventories
statistics scope. MVI owns all statistics and profiles. This plugin reads
`Statistic.DEATHS` and projects the online roster into a packet-only sidebar;
it does not count deaths, save player data, replace a Bukkit scoreboard or
depend on WorldLifecycle.

## Runtime and build

The validated target is Java 25, Paper 26.2 build 135, Multiverse-Core 5.8.1,
Multiverse-Inventories 5.3.6 and PacketEvents 2.14.0. PacketEvents must be
installed as a separate plugin. The module compiles against pinned Maven
artifacts and includes a Gradle 9.7.1 wrapper with a distribution checksum.

```sh
cd extensions/world-statistics-board
sh ./gradlew build
```

On Windows use `gradlew.bat build`. The result is
`build/libs/MultiverseStatisticsBoard-0.1.0.jar`. Archive timestamps and file
order are normalized. There is no published release URL. Under the repository's
`MANUAL` artifact contract, copy the locally built, hash-matching JAR to the
locked `plugins/` path and rerun the runtime installer or verifier.

## Statistics policy

Enable MVI's optional `game_statistics` share. Groups that intentionally share
statistics must include that share. The effective MVI API determines scope:
one applicable statistics group shares a roster; otherwise an applicable
world profile has its own roster. When MVI separates game modes, the game
mode is also part of the scope. No world or group name is hardcoded.

The sidebar is withheld when statistics are inactive, explicitly disabled,
or multiple statistics groups overlap at the viewer's world. With MVI bypass
permissions enabled, players with a world/group bypass are excluded because
their active statistics may have crossed boundaries unchanged. The check
includes registered unloaded Multiverse worlds. Unsupported scope warnings
are logged once per player/reason transition, and native sidebar selection
is restored until the policy becomes applicable.

Only online, eligible players in the same scope appear. At most 15 players
are selected by descending deaths, then a stable UUID-based row identity.
Names and numeric scores sent to the client are the actual player names and
death statistics. Equal-score ties use the stable hidden row identity, not
alphabetical player-name order. Offline rankings and historical repartition
of formerly global statistics are outside this component's contract.

## Display ownership

This component owns the sidebar while a viewer has an applicable scope.
Native generic and team-colored sidebar selection packets are suppressed
for that viewer. The latest native selections are remembered, including
objective removal, and restored when ownership ends. Existing colored slots
are cleared only on the client when the projection starts.

Native objectives, scores, teams, player-list and below-name packets continue
normally. The component never modifies their server state. Synthetic score
holders with explicit player-name display components prevent a native
`resetScores(playerName)` from deleting derived rows. All owned score removals
specify the projection objective. A native sidebar command remains effective
for unmanaged viewers and becomes visible to managed viewers on release.

Configure this as the only plugin owning the sidebar. It is not an arbitration
framework for multiple competing sidebar plugins. PacketEvents callbacks
touch only synchronized presentation state; Bukkit/MVI reads and projection
refreshes run on the main thread.

## Configuration

`plugins/MultiverseStatisticsBoard/config.yml`:

```yaml
title: Deaths
max-rows: 15
refresh-ticks: 20
```

`title` is literal nonblank text. `max-rows` accepts 1–15 and
`refresh-ticks` accepts 1–1200. Event-driven updates run on the next server
tick after world changes, death processing, game-mode changes and logins;
periodic refresh also picks up configuration/share and statistic changes.
Refresh timing is measured in server ticks, so a stalled server also delays
display updates. Restart the plugin through a normal server restart to apply
this component's configuration changes.

The local integration run passed 84 checks using three protocol clients across
two JVM runs. It reconstructed actual received scoreboard packets and checked
native state alongside shared/independent scopes, real deaths, world changes,
idle unload/rejoin, restart, game-mode separation, rejected policies, native
sidebar attempts and normal disable cleanup. The 15-row selection limit was
checked with an 18-row synthetic input; this is not a load benchmark or a
26.3 compatibility claim. Disposable evidence lives under
`.tmp/world-statistics-board/` at the repository root.

The first activation retains MVI's existing statistics adoption semantics;
this component cannot reconstruct per-world historical totals. Native
`deathCount`, arbitrary dummy objectives, fake-player map totals and command
state remain server-wide. The sidebar only presents the selected statistic
and roster.
