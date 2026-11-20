# Multiverse Player State

## 1. Scope

This contract governs generic per-world/group player statistics on the local
Paper 26.2 build 135, Multiverse-Core 5.8.1 and Multiverse-Inventories (MVI)
5.3.6 validation baseline. World names are configuration inputs. A particular
map, objective name or death counter must not define the implementation.

MVI owns player-state profiles. WorldLifecycle owns world loading, entry and
unloading. Enabling statistics must not add a second persistence owner to
WorldLifecycle. The tracked runtime lock and configuration bundle declare
this policy. WorldLifecycle currently uses the installer's MANUAL artifact
contract; configuration integration does not establish production deployment.

## 2. Configuration and Commands

Relevant MVI `config.yml` settings, preserving the existing location policy:

```yaml
share-handling:
  default-ungrouped-worlds: false
  use-optionals-for-ungrouped-worlds: true
  active-optional-shares:
    - last_location
    - game_statistics
sharables:
  apply-last-location-for-all-teleports: false
performance:
  apply-playerdata-on-join: false
  always-write-world-profile: true
```

A group must also include `game_statistics` in its shares. Group membership
defines intentional sharing; ungrouped worlds use their own profiles under
this policy. Use supported MVI group commands to change membership.

The template sets `first-run: false`. Fresh hosts remain ungrouped until
deliberately configured; MVI's generated default group would share
`last_location` across the default dimensions. Keep that share out of
cross-world groups. Existing host `groups.yml`, `worlds/`, `groups/`,
`players/` and `playernames.json` are instance state and must never be
overwritten by configuration application. Multiverse-Core's forced join
destination is disabled so native saved-world login remains authoritative.

The supported console command is `mvinv toggle game_statistics` (prefix `/`
in game, permission `multiverse.inventories.addshares`). It toggles rather
than idempotently enables: inspect `active-optional-shares` first and run it
only when the requested state differs. It recalculates enabled/applicable
shares and saves configuration; no reload or JVM restart is needed.

## 3. State and Adoption Contract

`game_statistics` snapshots/restores the complete Bukkit statistics set,
including untyped, block, item and entity statistics. Restoring all of them is
the requirement. Do not substitute a custom death-only share or add a second
handler restoring the same statistics.

Enabling the optional share does not immediately rewrite online players or
their profiles. On the next applicable world transition, MVI snapshots the
outgoing live statistics, restores destination values (absent statistics
default to zero), and writes the outgoing snapshot to its source profiles.
Previously combined totals become the initial source-world/group baseline;
they cannot be reconstructed into historical per-world totals. Preserve
existing destination profiles instead of cloning, deleting or fabricating
them. Keep native login authoritative with the existing
`apply-playerdata-on-join: false` policy; do not force a player-specific
`loadOnLogin` flag to make a validation pass.

## 4. Validation Matrix

| Condition | Required behavior |
| --- | --- |
| Group lists the share, optional activation absent | Game statistics remain inactive. |
| Activate while a player is online | Current statistics remain unchanged until normal handling. |
| Change worlds within one sharing group | The same statistics continue across dimensions. |
| Enter another group or an ungrouped world | Destination statistics replace the active values; source values persist. |
| Destination has no statistics data | Missing values start at zero, then normal game increments apply. |
| Another player switches or dies | This player's statistics do not acquire the other player's values. |
| Quit, unload, rejoin or restart | Current native state and later profile restores retain their respective values. |

Observe dynamic counters after engine processing: death handling updates
counters after the death event, time counters advance each tick, and
`LEAVE_GAME` increments before the quit snapshot. An immediate event value
is not always the settled result.

## 5. Statistics and Scoreboard Boundaries

- Good: MVI restores a player's `DEATHS` statistic from the selected profile.
- Base: a `minecraft.custom:minecraft.deaths` objective follows that player's
  statistic because Paper's statistic setter updates matching criteria.
- Bad: treating this as isolation of native `deathCount`, arbitrary dummy
  objectives, teams, fake-player totals or the shared sidebar audience.

Paper's main scoreboard is server-wide. A matching statistic objective
contains each player's currently active value; its rows are not selected
according to the viewer's world. `deathCount` is a separate native counter
and remains cumulative without its own policy. Even private boards with
native criteria can receive matching native updates across registered boards.

Display isolation is a separate contract: define the statistic/profile
source, viewer world/group, and roster. Per-viewer dummy projections can
represent that selection without taking ownership of native objectives.
Do not clear or swap the server main scoreboard on one player's transition.
No general scoreboard adapter is supplied by enabling `game_statistics`.

The separate `MultiverseStatisticsBoard` integration projects an online
death leaderboard under [Statistics Sidebar](./statistics-sidebar.md).
Its presence does not change this native-state boundary.

## 6. Required Checks and Evidence

Validate actual deaths, four statistic category representatives, same-group
sharing, cross-group round trips, two simultaneous players, cold rejoin,
idle unload and full JVM restart. Observers must only read state; seeding
must be explicit and separate from restore assertions. Read persisted
profiles after graceful save and never claim exhaustive coverage of every
statistic from category representatives.

The disposable fixture and raw observations are under
`.tmp/death-statistics-test/`; independent review is under
`.tmp/death-statistics-review/`. Map commands are disabled only in that
fixture for deterministic observations. This does not change the generic
requirement or prove arbitrary map-command compatibility. Source references
and event ordering are recorded in
`../../tasks/11-18-config-bundle/research/death-statistics-adaptation.md`.

## 7. Wrong vs Correct

Wrong: add `game_statistics` only to a group's share list, then infer it is
active from successful inventory isolation.

Correct: activate the optional share, verify group applicability and test
independent statistics across configured boundaries. Verify scoreboard
presentation separately before describing it as per-world.
