# Per-world/group statistics: live validation

Date: 2026-11-20. Policy: complete MVI `game_statistics` follows configured
world/group profiles. World names in the fixture are inputs, not product
conditions. No new plugin, death-only share or map-specific adapter is needed.

## Result

Paper 26.2 build 135, Multiverse-Core 5.8.1 and MVI 5.3.6 passed **45 checks
across five JVM runs** in an independent mutable runtime on loopback 25599.
An independent reviewer checked the results, observer behavior, persisted
profiles and first-login events. All owned JVMs stopped gracefully.

| Suite | Checks | Coverage |
| --- | ---: | --- |
| Actual death and persistence | 18 | Two actors, real death/respawn, cross-world restores, idle unload, native rejoin, restart. |
| Statistic categories | 17 | JUMP, USE_ITEM, MINE_BLOCK, KILL_ENTITY; shared overworld/nether group, independent destination, concurrent actors, cold login and restart. |
| Live activation | 10 | Native toggle preserves current values and profile bytes, retains last_location, snapshots source on next transition, defaults missing destination data to zero. |

The scoreboard observations remained distinct: actor A died twice in one
world, entered another with `DEATHS=0`, died once there, then returned with
`DEATHS=2`. The original `deathCount` objective retained its cumulative 3;
the statistic-criterion objective followed the active statistic (2/0/1/2).
This validates statistics isolation and does not provide per-viewer scoreboard
isolation or arbitrary command-state isolation.

One cold world load in JVM 4 produced a 10-second watchdog dump while loading
entities, then recovered and completed the assertions. No loading-performance
fix or guarantee is claimed. Map commands were disabled in the isolated
fixture only. No production host, immutable artifact or WorldLifecycle source
was changed.

## Local manual adoption

At 11:32:36 Asia/Shanghai, the already-running local manual instance on 25598
enabled the optional share using `mvinv toggle game_statistics`. Prior
inspection confirmed it was absent, the existing group included the share,
and ungrouped-world optionals were enabled. No reload or restart was used.
Persisted configuration now includes both `last_location` and
`game_statistics`; all seven other checkpointed files remained byte-identical
immediately after activation.

The checkpoint contains eight files: MVI config/groups, three named player
profiles, player metadata, native player data and native statistics. It was
taken after `save-all flush`. The last observed player dimension before
activation was `minecraft:trials`; the source snapshot on the next transition
uses the actual outgoing world. Previously aggregated totals cannot be
split into authentic historical per-world values. No histories were edited.

Manual policy remains one shared group for world/world_nether/world_the_end,
with trials using its own ungrouped profile. This is a configurable group
policy. The original sidebar still has native scoreboard semantics.

## Evidence

- `.tmp/death-statistics-test/final-report.md` and `evidence.json`: versions,
  artifact hashes, test results and event indices.
- `.tmp/death-statistics-test/manual-before/manifest.json`: pre-activation
  file hashes and the targeted local checkpoint.
- `.tmp/death-statistics-review/review.md`: independent review and limitations.
- `death-statistics-adaptation.md`: pinned upstream source and activation order.
- `../../../spec/backend/multiverse-player-state.md`: generic contract.

The tracked runtime/configuration bundle has not yet adopted MVI or this
local policy. No commit, push or production deployment was performed.
