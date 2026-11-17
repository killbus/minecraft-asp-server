# Design: Anvil multi-world switching

## Architecture

Run **standard Paper 26.2** as the only active server engine.

- Remove `asp-server.jar` and `plugins/asp-plugin-*.jar` from the active runtime.
- Keep the existing non-ASP plugins: CoreProtect, Geyser, Floodgate, GrimAC, PackManagerPro, SkinsRestorer, ViaVersion, ViaBackwards.
- Add **Multiverse-Core 5.8.1** for world registration, load/unload, teleport, aliases, and per-world configuration.
- Use Anvil worlds for persistent maps. Paper's chunk system loads chunks around players/tickets and unloads idle chunks; no whole-map residency.

The existing `world` remains the hub (`level-name=world`). A second world, `trials`, is registered with Multiverse and is not loaded at startup.

## Runtime layout

Tracked repository files change; `server/` remains ignored runtime state.

```
server/
  paper-server.jar          # replaces asp-server.jar
  plugins/
    Multiverse-Core-5.8.1.jar
    PackManagerPro.jar
    ...existing plugins...
  world/                    # primary level
    dimensions/minecraft/overworld/   # hub
    dimensions/minecraft/trials/      # adventure world, auto-load false
  .rollback/asp-<stamp>/    # old engine/plugin/config, not loaded

artifacts/
  trials-legacy/            # immutable source crop for migration/rollback
```

`server/` is runtime state only. `artifacts/` is gitignored immutable input, described by `artifacts.lock.json` and checked by `scripts/verify_artifacts.py`.

Start scripts and backup scripts move from `asp-server.jar` to `paper-server.jar`. `runtime.lock.json` declares Paper as the single server artifact and Multiverse as a plugin; `scripts/verify_runtime.py` and its tests are updated accordingly.

## World layout and migration

Paper 26.2 stores dimensions under:

```
<world>/level.dat
<world>/dimensions/minecraft/overworld/{region,entities,poi,data}
```

Build `server/world/dimensions/minecraft/trials` from the trimmed
`artifacts/trials-legacy` crop:

- Keep the Paper-generated dimension metadata; do not copy the source
  `level.dat`.
- `dimensions/minecraft/trials/region` from the 47 canonical region files.
- `dimensions/minecraft/trials/entities` and `poi` from the crop.
- Copy `data` where present.

The trimmed crop already covers the documented progression (`x=-5..0`, `z=-1..6`). It keeps `r.-1.3` and `r.0.3`, which hold 644 pre-1.13 chunks without a root `DataVersion`. ASP's importer failed on those chunks; a Paper probe upgraded sampled chunks correctly, so Paper's lazy DataFixer path is used instead of excluding them.

Register the world with `/mv create trials normal --no-adjust-spawn
--no-structures`. Stop Paper after the skeleton exists, then replace the
generated region/entities/poi/data contents with the trimmed crop. Keep the
generated `level.dat`. Restart and load the world through Multiverse.

Set the world spawn to `-1180 59 -131` and apply:

```
execute in minecraft:trials run gamerule keep_inventory true
execute in minecraft:trials run gamerule mob_griefing false
execute in minecraft:trials run gamerule command_block_output false
```

## Multiverse configuration

- `world`: registered as `minecraft:overworld`, `auto-load: true`, hub spawn.
- `trials`: registered as `minecraft:trials`, `auto-load: false`, adventure
  spawn.
- Switching: `/mvtp trials` and `/mvtp world`; console/OP-only initially.
- Load on demand: `/mv load trials` before first teleport if Multiverse does not auto-load; `/mv unload trials` when empty.
- Permissions: use Multiverse permission nodes; no LuckPerms dependency for the MVP.

## Resource packs

PackManagerPro remains the per-world pack layer. Rename the `test_world` entry to the actual Multiverse world name (`trials`) and keep `http://127.0.0.1:8000/pack-a.zip`. The existing HTTP pack server remains external to the Minecraft process.

Verify the world name PackManagerPro receives after Multiverse registration; if Multiverse exposes a namespaced key, use the exact key in `config.yml`.

## Memory model and acceptance

- Hub-only baseline should be materially below the current Slime-loaded 3.49 GB.
- Loading `trials` should add only the chunks around the player and active tickets, not 42,818 chunks.
- With no players in `trials`, `/mv unload trials` should return live heap close to the hub baseline.
- Measure with `jcmd <pid> GC.run` followed by `jcmd <pid> GC.heap_info`; record the numbers in the task notes.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Multiverse import semantics differ on Paper 26.1+ namespaced worlds | Validate the direct import first; fall back to create-then-copy while stopped |
| Paper cannot load some legacy chunks in the crop | Probe test on 2026-11-17 upgraded 12 sampled chunks with no DataFixer failure; watch for `No key p` warnings and validate progression areas |
| Plugin incompatibility after leaving the ASP fork | Start with the existing plugin set, check boot logs, disable only the failing plugin and record it |
| Resource pack key mismatch | Inspect the actual Bukkit world name and update PackManagerPro before testing |
| Geyser/Via/Grim behavior changes | Keep existing versions initially; do not combine the engine migration with plugin upgrades |
| Runtime lock/verifier still assumes `asp-server.jar` | Update verifier, tests, start scripts, and backup scripts in the same change |

## Rollback

- Do not delete `asp-server.jar`, `asp-plugin-*.jar`, `plugins/SlimeWorldManager`, or `slime_worlds` until Paper/Multiverse acceptance passes.
- Move them to `server/.rollback/asp-<timestamp>/` instead of deleting.
- Keep `artifacts/trials-legacy` and the original source archive.
- If Paper fails to boot or the map cannot be loaded, restore the ASP jar/plugin/config and start the old runtime; no world data is overwritten by the Paper attempt if `trials` is a new world folder.

## Branch and delivery

- Do not rename `main` and do not rename the repository in this task.
- Create `feat/paper-anvil-world-switching` at implementation start.
- Engine-profile switching is a later `feat/engine-profiles` task.
