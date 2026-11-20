# Statistics Sidebar

## 1. Scope / Trigger

Applies to `extensions/world-statistics-board/`, its runtime lock entry and
`config/plugins/MultiverseStatisticsBoard/config.yml`. The component presents
online death rankings for the effective MVI statistics scope. MVI owns all
statistics; WorldLifecycle owns world loading and entry. Neither gains a
display dependency or another statistics store.

The supported baseline is Java 25, Paper 26.2 build 135, Multiverse-Core 5.8.1,
Multiverse-Inventories 5.3.6 and PacketEvents 2.14.0. This is the sole sidebar
owner for eligible viewers, not arbitration between competing sidebar plugins.

## 2. Signatures

Build with `extensions/world-statistics-board/gradlew.bat build` from that
module on Windows, or `sh ./gradlew build` on Linux. The output is
`build/libs/MultiverseStatisticsBoard-0.1.0.jar`. Install the exact locked
bytes using the existing MANUAL contract; no published binary URL exists.

Configuration is a normal bundled YAML asset:

```yaml
title: Deaths
max-rows: 15
refresh-ticks: 20
```

`title` is literal nonblank text, `max-rows` is 1..15, and `refresh-ticks` is
1..1200. A normal server restart applies configuration changes. There are no
environment variables, commands, database files or player profile writes.

## 3. Data and Display Contracts

Read current online players and `Statistic.DEATHS` on the main thread, after
MVI restores the destination profile. Refresh on the next tick after join,
world change, game-mode change, death and quit; periodic refresh catches
share configuration and other statistic changes. Tick delays follow server
tick delays and are not wall-clock guarantees.

Use MVI's active optional and applicable group shares, not a second group
configuration. One applicable statistics group supplies a shared scope;
otherwise an applicable world profile supplies the scope. When MVI enables
game-mode separation, include the mode. Exclude ineligible participants from
all rosters, including their own. Rank descending by deaths, then by stable
UUID-derived holder identity, with at most the configured number of rows.
Ties are deterministic but not alphabetical by player name.

PacketEvents owns packet encoding. Create a private client objective and use
`msb:<uuid>` score holders with explicit player-name display components.
Native score resets for a real player name must not erase projection rows.
Owned removals specify the owned objective. Never call `Player.setScoreboard`
or modify the server main scoreboard to implement this view.

On scope change, remove all owned old rows before adding any target rows,
including the viewer's own row. Packet-by-packet reconstruction must not
combine the previous scope's value with newly added destination participants.

Intercept only sidebar selections: generic protocol slot 1 and team-color
slots 3..18. Use explicit protocol-slot mapping rather than enum ordinals.
Pass native objectives, scores, teams, player-list slot 0 and below-name slot
2. Track the latest suppressed native selections and removed objectives;
restore those selections when eligibility ends or the plugin disables.
Clear colored slots on the client while the private sidebar owns the view.

Packet callbacks touch only synchronized presentation state. Recheck active
view identity under its lock before cancelling a native packet; a callback
for a released view must not hide a later native selection. Bukkit and MVI
access remains on the main thread.

## 4. Validation and Error Matrix

| Condition | Required behavior |
| --- | --- |
| Invalid title or range | Fail enable before registering the projection. |
| Optional statistics inactive | Release private view; log reason transition. |
| Explicit disabled statistics share | Withhold the view. |
| Multiple applicable statistics groups | Withhold rather than invent a scope. |
| Ungrouped optional statistics disabled | Withhold ungrouped view. |
| Effective MVI world/group/mode bypass | Exclude participant and restore native display. |
| Native sidebar assignment while eligible | Remember assignment; keep private sidebar. |
| Native objective deletion | Clear remembered selection before release. |
| Native real-name score reset | Preserve synthetic projection rows. |
| Another player enters another scope | Update rosters without changing this viewer's scope. |
| Plugin stops | Remove owned objective and restore native sidebar selections. |

World bypass checks must include registered worlds after load then unload.
MV-Core 5.8.1's combined world list can lose that entry; merge public loaded
and unloaded collections by world name, as used by MVI permissions. Checking only loaded worlds or the
combined list is insufficient on this baseline.

## 5. Good / Base / Bad Cases

- Good: two same-group dimensions show the same online roster and restored
  statistics; an independent world shows its own participants and values.
- Base: an eligible lone player sees one row; zero deaths is a valid value.
- Bad: replacing an existing native `deathCount` objective, copying profiles
  into a ranking database, or including offline totals without a contract.

This display does not isolate arbitrary command blocks, fake-player totals,
native objectives or other map state. Historical global statistics retain
MVI's existing adoption semantics and cannot be split retrospectively.

## 6. Required Tests

Use isolated mutable saves and fresh identities. Decode actual client packets
to assert visible objective, roster, names, values and ranking; server-side
statistics alone do not verify presentation. Exercise concurrent independent
scopes, shared dimensions, real deaths, quit/rejoin, idle unload and a full
JVM restart. Protocol clients must acknowledge teleport/respawn/chunk flow
before attributing a silent receive stream to a projection failure.

Assert native objectives, scores, fake-player totals, teams, LIST and
BELOW_NAME both in server state and relevant packets. Test later generic and
colored sidebar assignments, real-name score resets, objective deletion,
release and disable. Test inactive/disabled/overlapping/bypassed scopes and
bypass on a world that has been loaded then unloaded.

Raw fixtures live in `.tmp/world-statistics-board/`; independent review is
in `.tmp/world-statistics-board-review/`. Record actual pass counts and
limitations in the task validation report; an implementation contract alone
does not establish successful manual or production deployment.

## 7. Wrong vs Correct

Wrong: declare per-world leaderboard support because MVI changes the native
deaths statistic, or because an own-row placeholder displays the new value.

Correct: derive a same-scope online roster from MVI, project it separately for
each viewer, and verify simultaneous clients while native scoreboard state
continues to operate.
