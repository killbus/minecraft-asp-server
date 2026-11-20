# Review: Worlds official comparison page

Date: 2026-11-20. Read-only review of the user-supplied page:
https://thenextlvl.net/docs/worlds/comparison

Fetched HTML: `.tmp/thenextlvl-worlds-comparison.html`. The first sandboxed
HTTP read failed TLS authentication; the authorized public read succeeded.
No browser session, plugin installation or runtime change was made.

## What the table actually compares

The major-alternatives table covers server software, Folia support,
Minecraft version range, world presets, portal linking, import/export,
custom generators, world entry permissions, developer API, license,
maintenance status and external plugin dependencies.

It does not compare player inventory/health/statistics ownership, last
location, idle unload plus cold entry, native selector confinement, native
scoreboard scope, or arbitrary map-command state isolation. Therefore it
cannot rank the candidates against those requirements.

Worlds' positive features are real: the reviewed release has Paper/Folia
version implementations, preset-based generation, portal handling, world
entry permission checks and a dedicated API module. Its Gradle build shades
libraries, so external dependencies "None" describes separately installed
plugin dependencies, not an absence of software dependencies. Compare
deployment responsibilities rather than library counts.

The table's "1.19 – latest" range spans historical plugin releases. The
current Modrinth 4.5.1 release specifically lists 26.1.2, 26.2 and 26.3;
the README links older plugin versions for older Minecraft releases.

## One concrete inaccurate row

The page marks **MyWorlds / World Entry Permissions = unsupported**.
The inspected current MyWorlds source provides the feature:

- `Permission.java:56` declares parameterized `world.enter` permission.
- `Permission.java:91` checks `useWorldEnterPermissions`, then the selected
  world's permission. Same-world movement is allowed.
- `MyWorlds.java:382` exposes `useWorldEnterPermissions`, default false.
- `listeners/MWListener_Post.java:73` calls the permission check for the
  target world; its `onPlayerTeleportPerm` handler at line 111 cancels
  disallowed teleports. Portal handling also uses that permission method.

Source permalinks:

- https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/Permission.java#L91
- https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/MyWorlds.java#L382
- https://github.com/bergerhealer/MyWorlds/blob/15b4c4757ecdb176510491dbfe2eb5debe1044d8/src/main/java/com/bergerkiller/bukkit/mw/listeners/MWListener_Post.java#L111

Disabled by default is not the same as unsupported. This evidence corrects
that specific row; it does not imply every other table entry is wrong.
The table invites corrections, but no external issue/comment was posted.
The ambiguous "Developer API" row was not treated as disproved merely
because public Java classes exist; supported API contracts require separate
evidence.

## Decision boundary

For a new Paper/Folia deployment prioritizing world generation, dimension
configuration and portal management, Worlds is a credible candidate. The
table offers useful management-feature context. Selecting it still needs
separate evaluation of player profiles and lifecycle requirements.

For the current confirmed Trials incident, world entry permissions do not
constrain `gamemode adventure @a` or `clear @a`: those commands need not
teleport anyone. The source findings in `thenextlvl-worlds-source.md` and
`myworlds-isolation-source.md` therefore remain applicable.

The current MVI/WL/statistics integration has explicit Multiverse dependencies
and persisted profiles. A manager migration is a different decision from
fixing map command scope; the table does not establish that migration will
preserve these contracts or eliminate the observed fault.
