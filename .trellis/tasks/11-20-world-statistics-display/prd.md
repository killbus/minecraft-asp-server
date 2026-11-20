# Per-world statistics presentation and runtime adoption

## Goal

Players should see a statistics leaderboard for their configured world/group
while MVI continues owning the underlying statistics. The first delivery is
an online-player death leaderboard. Existing worlds are test inputs; no map
or native objective name may be hardcoded into the implementation.

The user approved proceeding with mature-plugin evaluation, implementation,
two-player validation and adoption through the repository's existing runtime,
configuration and backup contracts.

## Requirements

- R1. Read each online participant's current Bukkit DEATHS after MVI restores
  the configured profile. No second statistics database or death-event counter.
- R2. A viewer sees only online participants in the same configured statistics
  scope. Same-group dimensions share the view; independent scopes do not.
- R3. Each viewer's sidebar is independent. Another player's world transition
  must not replace the viewer's board or expose other-scope values.
- R4. Preserve main-board objectives, scores, fake-player totals and teams.
  Existing non-sidebar display behavior must be explicitly checked.
- R5. Prefer a maintained existing plugin when its actual capabilities meet
  this contract. Any necessary adaptation belongs to a presentation component,
  not WorldLifecycle or a map importer.
- R6. Test two simultaneous players, real deaths, world changes, same-group
  dimensions, quit/rejoin, idle unload and restart. Existing resume/exact entry
  and inventory policy remain owned by their current components.
- R7. Adopt verified MVI/lifecycle/presentation artifacts and declarative
  configurations into the deployment contracts. Preserve host world registry,
  MVI/player profiles, native saves and existing operator group assignments.
- R8. Rebuild/install instructions must be truthful and reproducible. No
  invented release URLs, production access, publishing or commits.

## Non-goals

Offline leaderboards, arbitrary native command/objective state isolation,
historical global-statistics splitting, an engine/proxy migration, new death
storage, map-specific fixes and world-loading performance work.

## Acceptance

- Demonstrated different visible rosters/values for concurrent independent
  scopes, consistent shared-group view, and stable views when others move.
- The main scoreboard's unrelated state and non-sidebar display survive.
- Statistics remain correct across rejoin, unload and JVM restart.
- Applicable runtime/config checks pass; backups cover new instance data.
- The existing manual server is preserved until a verified rollout; no forced
  restart while the user is online. Automatic isolated tests are sufficient
  to prepare the integration before a manual rollout window.
