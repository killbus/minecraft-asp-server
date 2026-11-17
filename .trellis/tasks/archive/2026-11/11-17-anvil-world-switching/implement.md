# Implementation plan: Anvil multi-world switching

## 0. Branch and baseline

- Create `feat/paper-anvil-world-switching` from clean `main`. Do not rename `main` or the repository.
- Confirm no server is running and `git status` is clean.
- Record the current server jar, plugin inventory, `worlds.yml`, and PackManagerPro config for rollback.
- Rollback point: delete the feature branch; no runtime files have changed yet.

## 1. Acquire and verify artifacts

- Resolve the exact Paper 26.2 build from the PaperMC API; record version/build and SHA-256.
- Download Multiverse-Core 5.8.1 from its official Modrinth/Hangar source; record version and SHA-256.
- Do not upgrade the existing plugins in the same change.
- Rollback point: artifacts are only downloaded, not installed.

## 2. Update repository runtime plumbing

- Rename the declared server artifact from `asp-server.jar` to `paper-server.jar` in `runtime.lock.json`.
- Update `scripts/verify_runtime.py` and `tests/test_verify_runtime.py` for the new server filename.
- Update `scripts/start.cmd`, `scripts/start.sh`, `scripts/backup.cmd`, `scripts/backup-debug.cmd`, and `scripts/backup.sh`:
  - replace the ASP jar check/launch with `paper-server.jar`
  - remove ASP-only launch comments/properties
  - keep the 4 GB default heap with a documented tuning note
- Update `runtime.lock.json`: remove the ASP plugin entry, add Multiverse-Core.
- Validation:
  - `python -m unittest tests.test_verify_runtime`
  - `python -B scripts/verify_runtime.py` (after installation)

## 3. Prepare the Trials Anvil world

- Build `server/world/dimensions/minecraft/trials/` from
  `artifacts/trials-legacy` in the Paper 26.2 layout:
  - `region`, `entities`, `poi`, and `data/minecraft`
  - Keep the Paper-generated `level.dat`; do not copy the source level header.
- Verify the region set contains the 47 canonical files and no `r.*.mca` duplicates.
- Verify the 644 chunks without root `DataVersion` are confined to `r.-1.3` and
  `r.0.3`; Paper upgrades them lazily instead of excluding those regions.
- Rollback point: replace the dimension contents from the unchanged source crop.

## 4. Stage the Paper runtime

- Stop the server cleanly.
- Move the old engine artifacts to `server/.rollback/asp-<timestamp>/`:
  - `asp-server.jar`
  - `plugins/asp-plugin-*.jar`
  - `plugins/SlimeWorldManager/`
  - `slime_worlds/`
- Install `server/paper-server.jar` and `server/plugins/Multiverse-Core-5.8.1.jar`.
- Keep the existing non-ASP plugins and their configs unchanged.
- Rollback point: restore the moved artifacts and start the old jar.

## 5. Configure Multiverse and packs

- Start Paper with the hub only.
- Register `trials` with `/mv create trials normal --no-adjust-spawn --no-structures`,
  then stop Paper and replace the generated dimension chunk storage.
- Set `trials` to `auto-load: false` in `plugins/Multiverse-Core/worlds.yml`.
- Set the Trials spawn to `-1180 59 -131`.
- Apply gamerules:
  - `execute in minecraft:trials run gamerule keep_inventory true`
  - `execute in minecraft:trials run gamerule mob_griefing false`
  - `execute in minecraft:trials run gamerule command_block_output false`
- Update PackManagerPro: rename the `test_world` entry to the actual Multiverse world key and keep `pack-a.zip`.
- Add focused Multiverse permission notes for operators/players.
- Rollback point: remove the world registration and restore the PackManagerPro entry; no shared world data is modified.

## 6. Validate switching and gameplay

- Join the client and confirm the hub spawn.
- Run `/mvtp trials`; confirm the map spawn, command blocks, and resource pack.
- Return with `/mvtp world`.
- Confirm `/mv unload trials` works when no players are in that world.
- Confirm restarting the server keeps the world registration and does not auto-load `trials`.
- Check the boot log for `Failed to load`, datafixer exceptions, or plugin errors.

## 7. Validate memory behavior

- With only the hub loaded, run `jcmd <pid> GC.run` then `jcmd <pid> GC.heap_info`; record live heap.
- Load `trials`, teleport one player in, wait for chunks to settle, and measure again.
- Leave the world, unload it, run GC, and measure again.
- Acceptance: hub-only is materially below 3.49 GB; loaded Trials memory follows active chunks rather than all 42,818 chunks; unloaded memory returns near the hub baseline.
- Record the numbers in the task notes or a short `research/memory.md`.

## 8. Documentation and finish

- Add `docs/PAPER-WORLD-SOP.md` covering:
  - Paper + Multiverse startup
  - world import/layout
  - `/mv load`, `/mv unload`, `/mvtp`
  - per-world packs and gamerules
  - memory measurement and rollback
- Mark `docs/ASP-SOP.md` as legacy/rollback-only.
- Re-run the relevant tests and `verify_runtime.py`.
- Commit the repository changes on the feature branch; do not commit `server/` runtime artifacts.
- Follow-up task (not this branch): `engine-profile-switching` for restart-based Paper/ASP selection.

## Validation commands

```powershell
python -m unittest tests.test_verify_runtime
python -B scripts/verify_runtime.py
python -m unittest discover -s tests -p "test_*.py"
```

```text
/mv list
/mvtp trials
/mvtp world
/mv unload trials
```

```powershell
& 'D:\Applications\Scoop\apps\temurin25-jdk\current\bin\jcmd.exe' <pid> GC.run
& 'D:\Applications\Scoop\apps\temurin25-jdk\current\bin\jcmd.exe' <pid> GC.heap_info
```
