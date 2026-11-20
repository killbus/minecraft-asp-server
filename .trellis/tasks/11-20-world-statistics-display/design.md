# Design and decision boundaries

## Behavior gap and owners

MVI full statistics isolation is already validated (45 checks) and enabled
on the local manual server. The remaining gap is presentation: a native
deathCount sidebar is cumulative and server-wide. Presentation will project
the active profile's Bukkit statistic to a scoped online roster. It will not
modify a native criterion or switch the server main board.

WorldLifecycle remains independent and unchanged. MVI owns profiles and
sharing groups. Presentation owns its sidebar selection and derived rows.
The server repository owns deployment manifests/configuration and operations.

## Selection gate

Research maintained scoreboard components for actual scoped online roster
support, current runtime compatibility, statistic source and preservation of
native non-sidebar behavior. A personal statistic placeholder alone does
not establish leaderboard support. Record the selected component and any
remaining adapter before implementing it. Prefer the narrowest supported
extension when the component already handles display ownership correctly.

### Selected implementation

TAB 6.2.1 supports the runtime and custom placeholders, but yields the sidebar
to native/foreign display packets even through its forced-board API. No
supported exclusive-sidebar option was found. SimpleScore likewise did not
establish protection against subsequent native sidebar selection. Sampled
persistent leaderboards introduce a second source of statistics and do not
establish the effective MVI roster.

Use PacketEvents 2.14.0's supported packet API in a small independent
`MultiverseStatisticsBoard` integration. Prefer its native objective/display/
score wrappers directly; add no second packet implementation unless needed.
Only sidebar selection packets for managed viewers are arbitrated; native
objectives, scores, teams, LIST and BELOW_NAME continue normally. The custom
objective uses a distinct owned identity. No Bukkit scoreboard is replaced.
This is an initial sidebar owner, not a framework for competing sidebar plugins.

Source belongs in `extensions/world-statistics-board/`, an independently
buildable integration module in this deployment repository. It depends on
Paper, MVI and PacketEvents; it has no WorldLifecycle dependency and stores
no player statistics. Build artifacts remain ignored and are installed using
the existing pinned runtime/MANUAL contract until published externally.

## Data and concurrency

Only currently online players in the viewer's configured statistics scope
participate. Read restored statistics on the main thread after MVI's world
handling, and refresh after native death updates. Sort consistently; native
sidebar capacity bounds the visible list. Presentation state is ephemeral.
Scope resolution must agree with MVI game_statistics sharing; overlapping or
inconsistent group definitions must not silently produce invented grouping.

The main board remains authoritative for native command state. A derived
view must preserve unrelated native objectives/teams/non-sidebar displays,
with sentinel assertions. Never clear the main board to suppress a sidebar.

## Files and deployment

Research and implementation decisions belong in this task. Disposable source
experiments, runtime copies and evidence go under `.tmp/world-statistics-board/`.
Once selected, record the presentation source/artifact ownership explicitly.
Runtime/configuration adoption uses existing runtime.lock.json,
config.lock.json and config/ contracts; only extend installer logic if a
demonstrated requirement cannot use its existing MANUAL artifact contract.
No player/group state belongs in the configuration bundle.

The existing manual server remains running. Isolated validation uses an
independent mutable copy and fresh identities. Any manual replacement of
lifecycle or presentation JARs needs a graceful stop when players are offline.

## Failure and rollback

Configuration or compatibility failures must not overwrite existing data or
claim success. Retain old runtime/config checkpoints; deploy only validated
artifacts. A failed presentation component must leave native gameplay state
intact. Historical aggregated statistics remain as adopted previously.
