# Bring independent deployment capabilities to single-world startup

## Authorization

The user asked to cherry-pick relevant later work after the single-world branch was published for server testing. This authorizes porting and adapting the independent deployment contracts onto `feat/single-world-start`, committing and updating that published test branch. It does not authorize replacing main, accessing the server by SSH, changing live saves, or reintroducing in-process multi-map management.

## Goal and boundary

Keep native Paper primary-save selection from `92aa420`, while restoring the later runtime installer, configuration bundle, host-settings protection/backups, commit discipline, resource-pack serving, and frpc/HAProxy fixes from main `e1d12bf`. Use commit provenance and selectively adapt mixed changes. No new engine/profile system, lifecycle plugin, map importer, or player-state adapter.

The source commits under review are `5d6ace4`, `fd822bf`, `fc210ef`, `0c436d7`, `c4496a9`, `c3f1a7e`, `22ca771`, `f274d4a`, `785484e`, `0fcab06`, `640fd77`, `8c74d5c`, and `e1d12bf`. Do not cherry-pick the Paper+Multiverse/map-content commit `01cd4a1` or its archive/journal. The source state is main, not the later frozen integration branch.

## Acceptance

- Runtime installation and verification share the existing grammar, pinned URLs/hashes and descriptive User-Agent. No ASP, Multiverse, MVI, lifecycle, PackManagerPro, or statistics sidebar artifact is introduced. Keep other existing plugin versions/hashes; retain verified download URLs where available.
- Configuration applies only declared source templates and preserves native save trees, player data, host settings and plugin instance state. No Multiverse or PackManagerPro template/manifest entry. Use native server resource-pack settings for the one active save; preserve PACK_URL HTTPS validation and allow an explicit empty pack selection if no pack is desired. No per-world pack registry.
- Host JSON remains ignored and included in backups. Examples alone are tracked. Default engine/save behavior stays coherent with start.*. Native saves with level.dat (active and inactive) remain included in backups. Regenerable packs/caches remain excluded.
- Preserve the production shared-TCP topology: frpc -> HAProxy, optional PROXY v2, LAN Java frontend, TLS termination, decrypted-request inspection before routing, packs sidecar ownership, and existing certificate/mux lifecycle contracts.
- World selection must be usable through the production scenes as well as direct start.*. Add only a narrow optional --world NAME forwarding path if required; keep existing no-argument behavior and no second process/instance model. All paths must use the same accepted name grammar and existing native-save check; no config/environment selection registry.
- Restore commit-message gate and temporary-test .tmp conventions.
- Tests cover installer/config idempotence and instance preservation, empty/HTTPS pack selection, host backup coverage plus native saves, scenes with resource-pack/TLS/PROXY and world selection, and existing launch tests. Run applicable baseline tests; no real server or network services are started for these fixtures.
- Operator documentation explains stop/backup, git update, extra plugin JAR handling, settings/dry-run/apply, native save selection and scene start without silently overwriting existing host settings or converting dimension-only maps. Production deployment remains user-operated.

## Files and ownership

Target worktree: `D:/Repositories/minecraft-asp-server/.tmp/single-world-start`. Expected changes span scripts/install_runtime.py, apply_config.py, start/backup/scenes/serve-packs, runtime/config manifests and templates, settings examples/docs, ignore rules, commit gate and their tests/specs. Keep original single-world implementation. Docs belong primarily in SINGLE-WORLD-SOP.md; historical ASP notes may link to it. Avoid resurrecting an obsolete multi-world SOP as the active guide.

Root checkout and its pending journal edits, server/, artifacts/, manual runtime and sibling lifecycle repository remain untouched. Public main source is staged for read-only comparison under this worktree's ignored `.tmp/main-deployment-source/`.
