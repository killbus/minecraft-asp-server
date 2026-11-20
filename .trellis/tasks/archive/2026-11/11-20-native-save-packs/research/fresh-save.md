# Research: Fresh independent Trials save

- Query: Can the original Trials archive become a complete independent Paper 26.2 primary save, and does it require a staged legacy upgrade?
- Scope: mixed; local source archive, extracted NBT, pinned engine bytecode, prior validation records, publisher reference.
- Date: 2026-11-20

## Findings

### Recommendation

Use the **complete save from the original RAR**, installed as a new `server/trials/` directory while the server is stopped. It already contains a real `level.dat` and the native 26.2 directory layout. Start it through the existing `--world trials` contract. Do not construct a save from the production dimension-only `world/dimensions/minecraft/trials/`, the cropped 47-region artifact, or a newly generated metadata shell.

**No staged 1.12 -> 1.13 whole-save conversion is indicated for this archive.** Its actual archived `level.dat` is already 26.2/DataVersion 4903. Some region chunks retain older formats; this is a separate lazy chunk-upgrade concern. Do not downgrade the complete 26.2 save to an older server.

This recommendation does not require an import command, world registry, profiles, or plugin-based switching. The required preparation is an ordinary, verified, whole-directory extraction and installation.

### Source identity is verified against the actual RAR

Root paths below are relative to `D:/Repositories/minecraft-asp-server`, not the implementation worktree.

| Source | Size | SHA-256 |
| --- | ---: | --- |
| `.tmp/trials-of-the-past-52637.rar` | 779,464,189 bytes | `2b7710df040aaa37666b6d284bc24122f897317dbcdebb9bd213f62409f7f91c` |
| Archived `Trials of the past/level.dat` | 442 bytes | `d4d37a93df15d590b1e111498a00d9f50dd033fb1e492ae48166861c22d38e4a` |
| `.tmp/world-lifecycle-manual/runtime/versions/26.2/paper-26.2.jar` | 29,268,058 bytes | `7c391444fd5f5fb77d193414924e7a16dbfd1cac87a2a6c858a8ea8dd041f44e` |

The final JAR above is the patched runtime server JAR, **not** the Paperclip download artifact in `runtime.lock.json`; their hashes are expected to differ.

Verification performed:

1. Read `7z l -slt` from the actual RAR, without extracting into or changing any existing runtime.
2. Calculated CRC32 for all 636 files under `.tmp/trials-full/Trials of the past/`; every file matched its archive entry, with zero mismatches.
3. Independently read the archived `Trials of the past\level.dat` using `7z e -so`, captured binary stdout with Python, calculated SHA-256, and parsed its gzip/NBT bytes. It matched the extracted file and contained the 26.2 metadata listed below.

Thus `.tmp/trials-full` was not assumed to be an untouched original merely because of its name. The archive itself establishes the version. The summary describing this whole archive as a 1.12 save was inaccurate.

### Original metadata and complete content

Archived `level.dat` fields:

```text
Data.DataVersion = 4903
Data.Version.Name = "26.2"
Data.Version.Id = 4903
Data.Version.Snapshot = false
Data.Version.Series = "main"
Data.LevelName = "world"
Data.GameType = 2 (adventure)
Data.difficulty_settings.difficulty = "peaceful"
Data.spawn.dimension = "minecraft:overworld"
Data.spawn.pos = [-1180, 59, -131]
Data.spawn.yaw = 0
Data.spawn.pitch = 0
Data.initialized = true
Data.DataPacks.Enabled = ["vanilla"]
Data.ServerBrands = ["vanilla", "fabric"]
```

The complete save contains **636 files, 1,010,681,922 bytes** before Paper's first load, including:

```text
Trials of the past/
  level.dat
  level.dat_old
  icon.png
  session.lock
  data/minecraft/
    scoreboard.dat
    game_rules.dat
    world_gen_settings.dat
    maps/*.dat
    ...
  datapacks/                 (empty)
  players/                   (empty)
  dimensions/minecraft/
    overworld/{region,entities,poi,data,...}
    the_nether/{region,data,...}
    the_end/{region,entities,poi,data,...}
  DIM-1/data/                (source legacy raid files)
  DIM1/data/                 (source legacy raid files)
```

Keep the complete source tree. Do not strip root `data/`, maps, native dimensions, or unfamiliar legacy files as part of this bounded preparation. `session.lock` and `level.dat_old` are source runtime leftovers, not a reason to alter substantive save content; a prepared deployment bundle may omit these two regenerable files if explicitly documented.

The root `data/minecraft/world_gen_settings.dat` has DataVersion 4903, seed `6914705104517454111`, and only the three standard dimensions. No custom Trials dimension is required: Trials becomes the selected save's `minecraft:overworld`.

The original scoreboard has objectives `total_deaths`, `respawn`, `con`, `Deaths`, `health`, and `join`; display slots are `sidebar=Deaths` and `list=total_deaths`. Some author player-name scores are in the published source, while `players/` has no files. Keep this initial source scoreboard: deleting it to make the world “fresh” would also delete gameplay objectives. Fresh here means the publisher's initial state, without this server's prior player data or progress.

Original gamerules include `minecraft:keep_inventory=true`, `minecraft:mob_griefing=false`, `minecraft:command_block_output=false`, `minecraft:command_blocks_work=true`, and `minecraft:respawn_radius=10`. These are not all stored in `level.dat`; preserving the entire tree matters.

### Region counts and residual legacy chunks

Do not describe all 175 overworld `.mca` filenames as 175 active region coordinates. The source includes conflict/backup filenames such as `r.-3.-1-Banshee.mca`.

| Dimension | All region `.mca` files | Canonical `r.x.z.mca` files | Occupied canonical header slots |
| --- | ---: | ---: | ---: |
| Overworld | 175 | 142 | 94,819 |
| Nether | 6 | 6 | 2,147 |
| End | 16 | 16 | 6,032 |

Four canonical overworld source files are zero-byte files: `r.-4.-3.mca`, `r.-5.-2.mca`, `r.-6.-3.mca`, `r.3.1.mca`. They are also zero-byte files in the archive. They contributed no header slots above. This is a source fact, not evidence that a local extraction truncated them. No pruning is recommended here.

Read-only NBT parsing of every occupied slot in three original overworld regions gave:

| Region | Parsed chunks | Root DataVersion distribution | Parse errors |
| --- | ---: | --- | ---: |
| `r.-1.3.mca` | 783 | 4189: 362; 4790: 29; absent: 392 | 0 |
| `r.0.3.mca` | 285 | 4189: 1; 4790: 32; absent: 252 | 0 |
| `r.-3.-1.mca` (lobby region) | 1,024 | 4903: 1,024 | 0 |

This independently reconfirms the 644 missing-root-DataVersion chunks in the previously discussed two regions. The earlier Paper probe, recorded in root `.trellis/tasks/archive/2026-11/11-17-anvil-world-switching/prd.md:58`, successfully upgraded twelve sampled chunks, preserving content. That result does not validate every chunk in the complete map; it does refute importing ASP-specific exclusions as a general Paper requirement.

Default to Paper's ordinary chunk loading. A full `--forceUpgrade` is optional maintenance with additional one-time CPU/I/O cost, not a prerequisite established by this evidence and not a permanent memory requirement. Avoid promising that a successful spawn load validates all 100k+ region slots.

### Native engine boundary

Read-only `javap -p -c` against the available Paper 26.2 runtime JAR established:

- `net.minecraft.server.Main.main`: if the selected storage has world data, calls `getUnfixedDataTagWithFallback`; an unreadable level aborts. `lambda$main$1` uses `LevelStorageSource.getLevelDataAndDimensions` for an existing save and uses `createNewWorldData` only when no existing data is present.
- `io.papermc.paper.world.PaperWorldLoader.getWorldInfoAndData`: runs `WorldFolderMigration.migrateStartupWorld` before `loadWorldData`.
- `io.papermc.paper.world.migration.VanillaWorldMigration.migrate`: reads/fixes source metadata, migrates saved data, builds Paper level overrides, and logs `Starting Vanilla import` / `Completed Vanilla import`.
- `VanillaWorldMigration.migrateSavedData`: migrates world generation, gamerules, weather, clocks and selected overworld saved data to native dimension data roots. Paper may remove migrated root copies after verifying the target exists. A post-start tree need not retain the initial path layout byte-for-byte.
- `PaperLevelOverrides.createFromRawLevelData`: reads source `spawn`, `Time`, `initialized`, `GameType`, and `difficulty_settings`. Do not manually manufacture these files.
- `net.minecraft.server.MinecraftServer.createLevel`: loads root `ScoreboardSaveData` into the server scoreboard, and also assigns root `WorldData` game type from `DedicatedServerProperties.gameMode`.
- `ServerPlayer.calculateGameModeForNewPlayer`: uses a forced game type, then saved player game type, then server default. The source's `GameType=2` alone does **not** prove that a fresh login will start in adventure under shared `gamemode=survival` properties.

Current source configuration (`config/server.properties:11`, `:13`, `:21`, `:23`) is `difficulty=easy`, `enable-command-block=true`, `force-gamemode=false`, `gamemode=survival`. The publisher's `Failsafe Notable locations and coordinates.txt` says commands must be enabled and entry commands should automatically set adventure and the essential gamerules. Verify fresh-player entry behavior in a disposable run; do not silently change shared global properties or generalize this work into world profiles merely from the metadata difference.

Read-only inspection of the original lobby region `r.-3.-1.mca` found 96 command-block entities. They include actual current-style commands `gamerule keep_inventory true`, `gamerule mob_griefing false`, `gamerule command_block_output false`, `gamemode adventure @a`, `spawnpoint @a -1216 64 -142`, and scoreboard objectives using `minecraft.custom:minecraft.leave_game`. These are not merely instructions in the publisher's text file. This reinforces that the published source has already been maintained for the current format; do not run a blind old-command rewrite. Their presence does not prove all map triggers execute successfully.

### Follow-up: isolated first boot and three malformed tick lists

The parent agent subsequently booted an isolated complete original copy under worktree `.tmp/fresh-trials-probe/` using pinned Paper 26.2 build 135. The researcher read its console log and saved chunks without modifying them.

Evidence in `.tmp/fresh-trials-probe/probe-console.log`:

- Lines 19–23: Paper deliberately waits 30 seconds before first world storage migration.
- Lines 24–25, 45–46, 51–52: completed Vanilla imports for overworld, nether and end.
- Line 54: 355 persistent overworld chunks, rather than loading the entire map.
- Line 77: `Done (92.991s)!`.
- The parent reports a graceful exit 0, retained scoreboard objectives and `keep_inventory=true`.
- Lines 48–50: **three ERROR messages** for malformed `block_ticks` entries: `No key p`. Therefore the result is “complete save starts, with a specific legacy-data compatibility issue,” not “clean/lossless full upgrade.”

The affected locations were traced back to the **source nether**, not the lobby's overworld region:

| Native dimension / chunk | Original tick count | Source encoding | Post-boot saved state |
| --- | ---: | --- | --- |
| Nether `(1,-8)` | 4 | `Level.TileTicks`, integer `i=51`, no `p`, no root `DataVersion` | DataVersion 4903, 16 sections, `block_ticks=[]` |
| Nether `(1,-9)` | 4 | same | DataVersion 4903, 16 sections, `block_ticks=[]` |
| Nether `(0,-11)` | 1 | same | DataVersion 4903, 16 sections, `block_ticks=[]` |

The log's decoded entries say `i:"minecraft:dirt"`, while the source entries contain numeric `i=51`. Do not infer that these were harmless modern dirt ticks simply from the converted log label. The original nine queued updates were not preserved after this first save.

Bounded engine evidence from the same runtime JAR:

- `SavedTick.codec` uses required `TickPriority.CODEC.fieldOf("p")`; it has no missing-priority default in this decode path.
- `SerializableChunkData` creates `BLOCK_TICKS_CODEC` as `SavedTick.codec(...).listOf()`.
- `CompoundTag.read(name, codec, ops)` calls `codec.parse(...).resultOrPartial(errorLogger)`. The exact `Failed to read field` line is emitted here.
- `SerializableChunkData.parse` reads `block_ticks` through that method and applies `.orElse(List.of())`, then filters ticks for the chunk. It continues parsing the chunk; this is not an exception that discards the entire terrain chunk.
- Each affected saved chunk still contains 16 sections and palettes including `minecraft:netherrack`, `minecraft:bedrock`, `minecraft:fire`, `minecraft:lava` and other nether blocks. Its block tick list is empty. Thus the observed loss is those queued updates, not an empty replacement region; this does not prove every terrain block elsewhere was unchanged.

No repairs, tick injection, source edits, region exclusion, or full-map scan were performed. Keep this compatibility caveat explicit. A targeted legacy tick conversion investigation would be separate work if preserving those pending updates is required. A staged downgrade of the complete 26.2 save is not an appropriate response. The first boot does not validate every legacy chunk or complete Trials gameplay.

### Bounded operator preparation

These commands are a proposed Linux runbook, **not executed on production**. Stop the server first. Require a new target; do not merge into an existing `server/trials` or move the old dimension out of `server/world`.

```bash
cd ~/srv/minecraft-asp-server
(
  set -eu
  test ! -e server/trials
  test ! -L server/trials
  printf '%s  %s\n' \
    2b7710df040aaa37666b6d284bc24122f897317dbcdebb9bd213f62409f7f91c \
    .tmp/trials-of-the-past-52637.rar | sha256sum -c -
  mkdir -p .tmp
  stage=$(mktemp -d "$PWD/.tmp/trials-fresh.XXXXXXXX")
  7z x ".tmp/trials-of-the-past-52637.rar" "-o$stage"
  test -f "$stage/Trials of the past/level.dat"
  test -f "$stage/Trials of the past/data/minecraft/scoreboard.dat"
  test -d "$stage/Trials of the past/dimensions/minecraft/overworld/region"
  mv -T -- "$stage/Trials of the past" server/trials
)
```

Use `7zz` instead of `7z` when that is the installed extractor. The two source text files remain in the temporary stage. This keeps extraction reproducible without adding another permanent script. A Windows-created transport bundle may instead contain the complete save as `trials/`; record its archive hash and verify that it originated from the RAR hash above.

Then use the existing direct launcher or scene with `--world trials`. The exact production scene retains the current PROXY/TLS/packs arguments; adding this flag selects the primary save and does not need any content moved beneath the old `world/`.

Before promoting a prepared copy, an isolated first boot should verify: successful Paper Vanilla import; all three expected native dimensions; spawn at the source lobby; source scoreboard objectives and gamerules; command blocks and a fresh player entering the tutorial; graceful save/shutdown and a second boot. Legacy-region samples can extend that evidence without claiming full-map playthrough coverage.

## Files found

- Root `.tmp/trials-of-the-past-52637.rar` — original archive, verified identity above.
- Root `.tmp/trials-full/Trials of the past/` — complete extracted source, every archived file CRC-verified.
- Root `.tmp/trials-full/Failsafe Notable locations and coordinates.txt` — publisher's command prerequisites and progression coordinates.
- Root `.tmp/nbt.py` — small existing read-only gzip/NBT parser; loaded with no file arguments for this research.
- Root `.tmp/world-lifecycle-manual/runtime/versions/26.2/paper-26.2.jar` — actual native loader bytecode.
- Root `.trellis/tasks/archive/2026-11/11-17-anvil-world-switching/prd.md:58` — earlier bounded legacy-chunk Paper validation; not full-save import evidence.
- Worktree `scripts/start.sh:45` — existing native-save marker/link check; forwards `--world` at line 49.
- Worktree `docs/SINGLE-WORLD-SOP.md:76` — complete-save preservation boundary; no import command is provided.

## External references

- Publisher: https://www.minecraftmaps.com/52637-trials-of-the-past — source identity supplied by the user. This pass relies on the actual downloaded archive rather than a fresh fetch of mutable page metadata.
- Pinned Paperclip download: https://fill-data.papermc.io/v1/objects/ef3dbc68b013deafdbbee3bebf1ba351671ebcda94a8f136809b7532d5ba2fe1/paper-26.2-135.jar — repository runtime pin; bytecode findings above use its available patched runtime JAR.

## Related specs

- `.trellis/spec/backend/single-world-start.md` — launchers select an existing complete primary save; preparation/version compatibility remain operator responsibilities.
- `.trellis/spec/backend/runtime-inventory.md` — installer owns pinned runtime artifacts, not save import or initialization.

## Caveats / Not Found

- No production host connection, server startup, save mutation, or archive extraction occurred in this research. No existing live service was touched.
- The parent agent's disposable boot now establishes startup of the complete original save, with the three tick-list errors documented above. This researcher did not launch a server. No full-map lossless conversion or complete gameplay result is established.
- Do not preserve old server player files, existing Trials dimension data, or cropped artifact state for this fresh start. Also do not delete those unrelated production trees as part of this installation.
- Do not “clean” the source scoreboard, backup-looking filenames, or legacy directories without a separate validated reason. Complete-source preservation is the simplest bounded practice here.
- SHA-256 fingerprints the archive/build; archive CRC checks establish extraction equivalence, not map authorship or exhaustive semantic validity.
