# Anvil multi-world switching

## Goal

Replace the large Slime-backed adventure world with an on-demand Anvil world and add a mature world-switching layer, so multiplayer play does not require the whole map to stay resident in JVM heap.

## Background and confirmed facts

- `test_world` is currently an ASP `SlimeInMemoryWorld`; its chunks live in `Long2ObjectMap<SlimeChunk>`.
- Measured on the running server with `test_world` unloaded: about 782 MB live heap. With `test_world` loaded: about 3.49 GB live heap, a resident delta of about 2.7 GB for 42,818 chunks and a 197 MB `.slime` file.
- Importing at 4 GB failed during `SlimeSerializer.serializeChunks`; 8 GB succeeded. The 8 GB is both an import peak and practical headroom for the loaded Slime world.
- The untrimmed source has about 94,819 canonical chunks, including 8,716 pre-1.13 chunks without root `DataVersion`. A full Slime import would be substantially larger than the current trimmed world.
- `artifacts/trials-legacy` is a trimmed Anvil-format crop (`x=-5..0`, `z=-1..6`) covering the documented Trials progression. It is gitignored immutable input, described by `artifacts.lock.json` and checked by `scripts/verify_artifacts.py`. It contains 644 pre-1.13 chunks without a root `DataVersion` in `r.-1.3` and `r.0.3`; Paper upgrades them lazily on first load.
- The server started on AdvancedSlimePaper 26.2 with the ASP/Slime plugin installed. It has now been migrated to standard Paper 26.2-135 with Multiverse-Core 5.8.1.
- Paper 26.1+ stores dimensions under `<level-name>/dimensions/<namespace>/<key>/`. Multiverse-Core 5.8.1 supports Paper 26.1-26.3 and namespaced world keys.
- PackManagerPro already supports per-world resource-pack URLs.
- Multiverse-Core keeps registered worlds as `World` objects, but does not force all Anvil chunks into memory. Paper loads chunks around players/tickets and unloads idle chunks; the current `delay-chunk-unloads-by` is 10 seconds.
- Multiverse-Core 5 supports `auto-load` in `worlds.yml`, plus `/mv load` and `/mv unload`; the adventure world can be loaded only when needed and unloaded when empty.
- On this Paper version, Multiverse creates a new world as a dimension below the primary level (`world/dimensions/minecraft/trials`), not as a sibling `server/trials` directory.

## Requirements

- Run on standard Paper 26.2 rather than the AdvancedSlimePaper fork.
- Remove the ASP/Slime plugin and its runtime worlds from the active server configuration.
- Keep normal Minecraft/Paper Anvil worlds as the primary storage model for large persistent maps; do not use Slime for the large adventure map.
- Add a world-management layer that can load and switch between the hub and one or more Anvil adventure worlds.
- Provide a player-facing switch command that teleports a player to a named world and a way to return to the hub.
- Preserve per-world resource packs, gamerules, difficulty, and spawn behavior.
- Keep the first migration limited to the trimmed Trials crop; do not attempt the full 94k-chunk map unless separately approved.
- Validate that the Anvil world loads on demand and that server memory no longer includes the full map when the world is idle/unloaded.
- Keep only the hub loaded at startup by default; the adventure world is loaded on demand and may be unloaded when no players remain.
- Keep world data and configuration under the existing `server/` runtime layout and document operational commands.

## Acceptance criteria

- [x] The server starts with the hub world only and no Slime-backed `test_world` being loaded.
- [x] The trimmed Trials map exists as an Anvil world and can be loaded through the chosen world manager.
- [x] A player can switch from the hub to the Trials world and back without reconnecting.
- [x] The Trials world uses its documented spawn and map gamerules (`keep_inventory=true`, `mob_griefing=false`, `command_block_output=false`).
- [x] PackManagerPro applies the intended resource pack in the Trials world and the hub pack behavior is unchanged.
- [x] With the Trials world idle/unloaded, JVM live heap is materially below the current Slime-backed 3.49 GB measurement.
- [x] With the Trials world unloaded, only the hub `World` object remains resident; `/mv load` and `/mv unload` change the loaded-world set without restarting.
- [x] Restarting the server preserves the world registration and switch configuration.

## Verification log

2026-11-17, Paper 26.2-135, Java 25, `-Xms2G -Xmx4G -XX:+UseG1GC`:

- `mv list` after restart: `world` / `world_nether` / `world_the_end` loaded, `trials - UNLOADED`.
- `/mv load trials`: 355 persistent chunks; first load 12,989 ms, causing a one-time watchdog thread dump during the legacy `DataVersion` upgrade (922-4903 -> 26.2). After unload, the region files were rewritten and the next `/mv load trials` took 994 ms.
- Live heap after `jcmd GC.run`: 446 MB hub-only, ~550 MB with `trials` loaded, back to 446 MB after `/mv unload trials`. Old ASP `test_world` was ~3.49 GB.
- `execute in minecraft:trials run gamerule ...`: `keep_inventory=true`, `mob_griefing=false`, `command_block_output=false`.
- Spawn chunk region `r.-3.-1` is present in the imported crop; spawn is `-1180 59 -131`.
- Resource pack server: `http://127.0.0.1:8000/pack-a.zip` returns 200, 28,745,227 bytes.
- Three players (Snorlax, Craftilo, Maychi) played for about one hour across `world` and `trials` with no server ERROR/WARN and TPS `19.9/20.0/20.0`; `/mvtp trials` and `/mvtp world` were used repeatedly without reconnecting.
- Pack delivery confirmed in the HTTP access log: `GET /pack-a.zip 200` at 20:14:14 (Craftilo) and 20:14:53 (Maychi), both immediately after `/mvtp trials`. Later switches produced no new GET, confirming client-side pack caching.
- Before `enable-join-destination` was enabled, players who rejoined resumed the dimension they logged out in (playerdata). Return logins are now pinned to `world` so an unloaded `trials` cannot resolve to ungenerated terrain; new players also land in `world`.
- The ASP-era exclusion of `r.-1.3` / `r.0.3` was re-tested on Paper in an isolated `trials_probe` dimension. Twelve sampled legacy chunks (six per region) upgraded to the current `DataVersion` in about 17 seconds total, preserved block content (ores, deepslate, chests), and produced only two non-fatal `No key p` warnings for stale block ticks. Both regions are now part of the artifact and the live `trials` dimension; the live files report 0 chunks missing `DataVersion` after the sampled warm-up.

## Decisions

- Do not add engine-profile or restart-based Paper/ASP switching in this task. Paper plus Multiverse already covers multi-world play; ASP remains rollback-only, and ASP's only unique capability (Slime worlds) is deliberately unused.
- Do not import the full 175-region source map or its nether/end dimensions in this task. The 47-region crop is the validated playable scope and the provenance/re-init source.
- Keep the pre-1.13 regions `r.-1.3` and `r.0.3`. The old ASP exclusion did not reproduce on Paper and left holes in the map.
- Pin every login to the hub with Multiverse `enable-join-destination: true` and `join-destination: world`. With `trials` on `auto-load: false`, a saved non-hub logout dimension would otherwise be resolved without the world being loaded. Change `join-destination` to `trials` only if the adventure map should become the login world.

## Out of scope

- Importing the full untrimmed 94k-chunk source map.
- Building portals, menus, or a custom GUI for world selection.
- A full LuckPerms permission redesign; OP-only operation is acceptable for the first validation.
- Rewriting the ASP server jar or patching its importer.
- Runtime hot-swapping between server engines.
- Running Paper and ASP simultaneously behind a proxy.
- Restart-based engine-profile switching; this is a separate follow-up task so the Paper/Anvil migration can be validated independently.

## Follow-up

- A separate `engine-profile-switching` task may add restart-based selection between Paper and ASP, with profile-specific jars/plugins/config and shared Anvil world data. It is not part of this migration.
