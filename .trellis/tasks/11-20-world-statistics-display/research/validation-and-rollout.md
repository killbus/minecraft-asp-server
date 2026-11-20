# Final validation and local rollout

Date: 2026-11-20. Implementation and independent review passed. Changes remain
uncommitted; no branch, push, release publication or production access occurred.

## Accepted implementation

`extensions/world-statistics-board/` builds MultiverseStatisticsBoard 0.1.0.
It reads MVI-owned live DEATHS and presents a same-scope online roster through
PacketEvents. It does not modify native scoreboard state, own profiles or
depend on WorldLifecycle. Two clean builds produced the same SHA-256:

`128c64cc02422d8b6ae2160a6253a02aa76a8b396ef562dffeb56b10a59a011d`

The runtime lock declares MVI, formal lifecycle, PacketEvents and this
presentation component. Unpublished lifecycle/presentation artifacts use the
existing MANUAL contract. Source configuration includes their policies;
host world/group/player state remains protected instance data. Existing
backup coverage is verified rather than replaced.

## Verification

- `python -B -m unittest tests.test_apply_config tests.test_backup_settings
  tests.test_install_runtime tests.test_verify_runtime -q`: 100 tests run,
  OK with one optional original-server comparison skipped. All isolated
  application, instance-preservation, backup and installer cases ran.
- After adding the final presentation lock entry, runtime installer/verifier
  suites ran again: 48 tests, OK. A relative `source` field was initially
  rejected by the existing URL grammar, then corrected to the real project
  URL with a note distinguishing unpublished local module source. The lock
  grammar was not loosened.
- Three concurrent TCP protocol clients in isolated JVM runs 5 and 6:
  **84/84 live integration checks passed** against the exact JAR above.
  This includes shared dimensions, independent scopes, real server deaths,
  transition packets, native sidebars and score resets, unload/rejoin/restart,
  disabled/overlapping/bypassed scopes, game modes and normal plugin disable.
- Independent review reconstructed **1060 received packets across seven
  connections**, and checked **37 settled views** against server statistics
  and unchanged main-board identity. No implementation blocker remained.
- Capacity selection used 18 synthetic rows and retained 15; actual live
  concurrency was three clients. No load/performance benchmark, graphical
  visual acceptance, Paper 26.3 run or production plugin combination is claimed.
- CRLF-aware `git diff --check` passed. Build inputs remain pinned and Gradle
  archive order/timestamps normalized. The Linux command uses `sh ./gradlew`
  so it does not rely on an uncommitted executable-mode bit from Windows.

Detailed disposable evidence: `.tmp/world-statistics-board/final-report.md`,
`summary.json`, `results.json`, `observations.json`, `wire-run-{5,6}-*.jsonl`
and server logs. Independent evidence is in
`.tmp/world-statistics-board-review/final-review.md` and `final-audit.json`.
Earlier failed/obsolete attempts remain preserved and are not final evidence.

## Local manual deployment

Confirmed zero players at 13:34:44, then gracefully stopped the existing
manual JVM at 13:35:12. Its full stopped runtime was copied to
`.tmp/world-statistics-board/manual-before-20261120-133512/runtime`.
The sibling `manifest.json` verifies all 851 files / 719,842,109 bytes.

The only replaced original file is `plugins/WorldLifecyclePrototype.jar`,
moved to the checkpoint's `disabled-prototype.jar`. Added formal lifecycle,
PacketEvents and presentation JARs at the locked paths. Copied the existing
prototype configuration to `plugins/MultiverseWorldLifecycle/config.yml`,
preserving managed trials, idle 8 seconds and 30/30/60-second request/login
budgets. Added the default presentation configuration. The old inactive
prototype data directory remains available; no duplicate lifecycle JAR runs.

All other **850 original runtime files remained hash-identical before
startup**, including native saves, MVI profiles/groups, MV registry, network
and resource-pack configuration. The production configuration bundle was
not applied to this local offline/loopback experiment. Installer dry-run
reported three OK for the newly supplied, hash-matching JARs.

The first launch command was rejected by PowerShell argument parsing before
Paper started. Quoting the unchanged JVM arguments fixed command invocation.
The accepted launch uses the existing Java 25, 512M/3G heap and flags:

```text
-Xms512M -Xmx3G -Dterminal.jline=false -Dterminal.ansi=false
-Dpaper.disablePluginRemapping=true -jar paper-server.jar --nogui
```

The running JVM is PID **5052**, interactive console session **18420**, on
**127.0.0.1:25598**. Formal lifecycle announced READY with managed trials at
13:38:56; Paper announced Done at 13:38:57. The six intended plugins enabled.
No test observer is installed. The existing pack helper remains on port18000
(session73042), with its original ZIP and settings.

A new disposable identity, BoardSmoke1120, logged in and received the owned
`Deaths` objective with its own zero-death row. The pack URL returned HTTP200
and Content-Length28,745,280. The probe disconnected normally without
teleporting, killing or altering either real player's records. The probe's
receiver reports a closed-socket exception during its deliberate close;
the server records normal Disconnected. Evidence is `manual-smoke.json`,
`manual-smoke.py` and `wire-run-100-BoardSmoke1120.jsonl` in the board fixture.

At 13:40:30, console status reports trials registered/unloaded with no pending
entry, the base dimensions loaded, and zero online players. The manual server
and pack helper remain available for human testing. Native startup and new
probe activity can legitimately update metadata after the pre-start hash
comparison; the preservation claim is explicitly about deployment itself.

## Craftilo incident remains a separate diagnosis

At 12:58, world entry succeeded, then Paper rejected an out-of-order keepalive
reply. The generic client reason is Timed out, but increasing the expiry
limit cannot fix this FIFO mismatch branch. Expected resource-pack removal
caused a reload at the same time. The vanilla deferred-reply/window-event
path supplies a plausible inversion mechanism; it is not a packet-trace proof
of this incident. Both real clients subsequently closed, so no repeat trace
was available. No timeout, kick handling or client behavior was changed.

`research/craftilo-resource-reload.md` records exact logs/bytecode/upstream
applicability and local passive-capture feasibility. The next reproduction
needs challenge/reply order captured from a fresh connection. Neither this
presentation deployment nor its successful smoke test is a fix claim for
Craftilo's disconnect.
