# Validation evidence

This records the initial implementation's validation. The later
unified-pack-settings correction consolidates host configuration and records
new consumer/launcher regressions; these cache/native/map probes remain valid
mechanism evidence rather than current settings-schema examples.

## Automated checks

- 14 pack-policy tests passed after review fixes.
- 24 Bash/CMD launcher and backup tests passed; final run56.566 seconds.
- 49 configuration-renderer tests and6 scene world-forwarding tests passed.
- A deterministic3005-case Java `Properties` differential check matched after
  fixing continuation/comment and escaped surrogate-pair duplicate-key cases.
- Python AST parsing, Bash syntax and scoped `git diff --check` passed. No
  project formatter, linter or type checker is configured for this scope.

Review also corrected Windows linked/malformed settings-directory fallback.
Verification completed in the existing test worktree before publication.
The session journal records the subsequent reviewed commits and branch.

## Native Java client cache, 2026-11-20

Executed actual installed vanilla 26.2 and 26.3 `HttpUtil.downloadFile` using a
small Java harness, an isolated cache and a counted loopback HTTP server. Each
case invoked the method twice against the same URL/cache/content. No real
client cache or GUI was changed.

| Client | Expected SHA-1 | Calls | HTTP GETs | Java exit |
| --- | --- | --- | --- | --- |
| 26.2 | Valid content digest | 2 | 1 | 0 |
| 26.2 | Null (blank protocol hash) | 2 | 2 | 0 |
| 26.3 | Valid content digest | 2 | 1 | 0 |
| 26.3 | Null (blank protocol hash) | 2 | 2 | 0 |

Scratch evidence: `.tmp/cache-probe/{CacheProbe.java,run.py,results.json}`.
Valid-hash second calls logged `Returning cached file since actual hash matches
requested`. An initial test with the 28 MB deployed ZIP established a cache hit
but a subsequent case timed out; the complete matrix used a small ZIP to isolate
cache decision behavior from transfer time. These are native method tests, not
a full multiplayer login simulation or observation of production traffic.

Existing Craftilo client logs also show a cache hit immediately followed by
ResourceManager reload; see `research/native-packs.md`. That distinction
explains why the Mojang screen alone cannot establish a repeated download.

## Native Paper configuration

`.tmp/native_pack_smoke.py` copied the pinned Paper runtime into disposable
`.tmp/native-pack-smoke/server`. For `trials` then `world`, generated policy
properties and invoked actual Paper `--config ... --world NAME --initSettings`.
Both exited 0; native persisted `level-name` matched selection, Trials retained
URL/SHA-1, world had both empty, and the canonical properties SHA-256 was
unchanged across both runs. No game service/listener started in this check.
Evidence: `.tmp/native-pack-smoke/results.json` and per-world logs.

## Fresh original map

Original RAR SHA-256:
`2b7710df040aaa37666b6d284bc24122f897317dbcdebb9bd213f62409f7f91c`.
Research verified all 636 extracted files against archive CRCs and separately
read `level.dat` directly from the RAR: version26.2/DataVersion4903. No metadata
fabrication or old cropped artifact was used.

A complete disposable copy booted Paper26.2-135 at `127.0.0.1:25971`, reached
`Done` after92.991 seconds, answered scoreboard/gamerule queries and stopped
with exit0. Six objectives survived: join, health, Deaths, con, respawn,
total_deaths; keep_inventory=true. The temporary process was stopped.
Evidence: `.tmp/fresh-trials-probe/probe-console.log`, `.tmp/run_fresh_probe.py`.

Three original Nether chunks lost nine old pending block updates with missing
priority field `p`. Terrain remained; details and before/after evidence are in
`research/fresh-save.md`. No source chunks were removed or repaired. This is
not a claim of lossless conversion or full adventure gameplay compatibility.
Fresh-player introduction and full-map playthrough remain operator acceptance.

An additional untouched deployment copy is ready at
`.tmp/trials-ready/trials/`. All636 file SHA-256 values matched the extracted
original after copying. Combined sorted-manifest digest:
`a7a8f26e00503cdd7b9bb5037ac67df7b96dc247f2162f1d10d3234f5be0208a`.
The probe's mutated save is separate and is not the deployment copy. Operator
docs also describe reproducing this directly from the original RAR on Linux.

## Isolation

No production SSH, current runtime/service restart, source-map mutation, plugin
installation, external asset commit or main-branch change. Work is confined to
the existing `feat/single-world-start` worktree; original runtime files were
read or copied only. Production still needs the new source and host policy.
