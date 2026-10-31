# AdvancedSlimePaper (ASP) Operations SOP

How to take an ASP server from scratch to production-ready.
Target: ASP 26.2 (Minecraft 26.2). Last updated: 2026-11-01.

## 0. Hard rules

- **Do not build from source.** Use prebuilt jars only, from the official
  download page https://infernalsuite.com/download/asp/ (the version
  switcher selects 26.2 / 26.3 experimental builds).
- **Minecraft 26.1 and newer require Java 25 or newer.** The server
  refuses older JDKs at bootstrap with:
  `Minecraft 26.1 and newer requires running the server with Java 25 or above.`

## 1. File classification (back up vs. regenerable)

| Class | Files | Notes |
| --- | --- | --- |
| Program (dropped in by operator) | `asp-server.jar` | The server itself; manifest `Main-Class: io.papermc.paperclip.Main` (Paperclip launcher) |
| Program (dropped in) | `plugins/asp-plugin-*.jar` | SWP (Slime World Plugin) - "the plugin" in the official docs; released together with the server jar |
| Program (dropped in) | other `plugins/*.jar` | Geyser, Floodgate, ViaVersion, SkinsRestorer, ... |
| Config (kept, edited by hand) | `eula.txt`, `server.properties`, `bukkit.yml`, `spigot.yml`, `commands.yml`, `config/paper-global.yml`, `config/paper-world-defaults.yml`, `server-icon.png`, per-plugin yml (`worlds.yml`, ...) | `/reload` or restart after edits |
| Data (not regenerable - back these up) | `world/` (`level.dat`, `data/`, `dimensions/`, `players/`), `whitelist.json`, `ops.json`, `banned-*.json`, `usercache.json` | Backup policy centers on these |
| Regenerable output (safe to delete) | `libraries/`, `versions/`, `cache/`, `logs/`, `.paper/`, `slime_worlds/`, `session.lock`, `level.dat_old`, `*.log` | Rebuilt/re-downloaded at startup; do not copy to a new machine |

`world/` is a tree, not a single file. On this build `level.dat` is a
**slim header** (522 B on the reference world) holding only difficulty,
spawn, GameType, DataPacks, DataVersion, LevelName and Time. The rest of
the world state sits beside it and is **authoritative, not cache**:

| Path | Content |
| --- | --- |
| `world/data/minecraft/*.dat` | scoreboard, custom boss events, random sequences, stopwatches, world clocks |
| `world/dimensions/minecraft/<dim>/data/minecraft/*.dat` | game rules, world generation settings (**including the seed**), weather, raids, world border, scheduled events, chunk tickets |
| `world/dimensions/minecraft/<dim>/data/paper/*.dat` | Paper metadata, level overrides, persistent data container |
| `world/players/` | player data, advancements, stats |

Verified by decompressing `level.dat` on the reference world: it contains
none of `GameRules`, `WorldGenSettings`, `WeatherData`, `Scoreboard`,
`CustomBossEvents`, `WorldBorder`, `ScheduledEvents` or `seed`.
`game_rules.dat` keeps its world-creation mtime across boots, so it is
read at load rather than regenerated.

Consequence: **back up and restore the whole `world/` tree.** Copying only
`level.dat` produces a world with default game rules, a different seed,
reset weather and an empty scoreboard.

`session.lock` and `level.dat_old` are runtime artifacts and are excluded
from backups.

## 2. Deploy from scratch

1. Create a working directory, e.g. `server/`.
2. Download the **two** files for the target version (version switcher):
   - server jar -> `server/asp-server.jar`
   - plugin jar  -> `server/plugins/asp-plugin-4.2.0-SNAPSHOT.jar`
3. First run (auto-downloads the vanilla Mojang jar and applies the
   Paper patch; takes several minutes):
   ```
   java -jar asp-server.jar
   ```
   with a Java 25+ `java` on PATH (section 0).
   The first run exits on the EULA -> write `eula=true` to `eula.txt`
   -> run again.
4. A good boot shows all of the following:
   - `This server is running AdvancedSlimePaper version 26.2-...`
   - `Starting Minecraft server on *:25565`
   - `[ASPaperPlugin] Enabling ASPaperPlugin v...`
   - `Done (xx.xs)! For help, type "help"`
5. Stop gracefully with `stop` in the console. Killing the process skips
   the save path; chunks are already saved right after spawn
   preparation, so a kill is low-risk but not the normal procedure.

## 3. Import an existing world

1. Stop the server.
2. Put the world contents (1.18+ layout: `level.dat` +
   `dimensions/minecraft/{overworld,the_nether,the_end}`) into
   `server/world/`. If the archive is a zip, extract it and move the
   inner directory in.
3. If `server/world` already holds a fresh world, move it aside first
   (e.g. `world-fresh-backup`).
4. Start. ASP runs `WorldFolderMigration` + `VanillaWorldMigration`
   automatically: a 30-second countdown, then per-dimension
   `Completed Vanilla import for world '...'`, then `Done (..s)`.
5. Migration completes when `world/level.dat` grows (a placeholder is a
   few bytes) and `world/level.dat_old` appears.

### Restoring from a backup

A backup directory is valid only when it contains `COMPLETE`. Directories
without it are partial leftovers: `backup.cmd` / `backup.sh` delete them on
the next run and never count them against retention.

1. Stop the server with `stop`. Never restore under a running server.
2. Verify the backup before touching anything:
   `cd backups/<timestamp> && sha256sum -c MANIFEST.txt`
   Every line must read `OK`. If any line fails, the backup is unusable -
   pick an older one.
3. Move the current world aside rather than deleting it:
   `world/` -> `world.broken-<date>/`.
4. Copy the **entire** `world/` tree from the backup into `server/world/`.
   That includes `data/` and `dimensions/*/data/` - see section 1 for why
   `level.dat` alone is not enough.
5. Restore the rest of the backup over the server dir: `config/`,
   `plugins/<name>/`, `plugins/*.yml`, and the top-level `*.json`, `*.yml`,
   `server.properties`, `eula.txt`, `server-icon.png`. Plugin jars are not
   in the backup - they stay as they are.
6. Start the server and confirm `Done (..s)!` with no `Failed to load
   world` and no `Exception`.
7. Keep `world.broken-<date>/` until the restored world has been played on
   once and looks right, then delete it.

Drill result (backup `20261031-163649`, restored into an isolated copy of
`server/`): 256/256 files matched the manifest, the server booted to
`Done (45.454s)!`, all eight plugins enabled, and `stop` exited with code
0. After the boot only 13 files differed from the manifest - the two port
edits, `world/level.dat`, and the world state `.dat` files written on save.

## 4. Third-party plugins

Current deployment:

| Plugin | Version | Notes |
| --- | --- | --- |
| SWP (ASPaperPlugin) | 4.2.0-SNAPSHOT | shipped with the server jar |
| Geyser-Spigot | 2.12.0-b1259 | Bedrock bridge, UDP 19132 |
| Floodgate | 2.2.5-SNAPSHOT (b141) | Bedrock accounts joining; depends on Geyser |
| ViaVersion / ViaBackwards | 5.12.2-SNAPSHOT | cross-version protocol bridge |
| SkinsRestorer | 15.12.6 | runs in Floodgate Mode while Floodgate is present |

Download endpoints:

- Geyser / Floodgate (official page buttons):
  `https://download.geysermc.org/v2/projects/<geyser|floodgate>/versions/latest/builds/latest/downloads/spigot`
  The legacy `api.geysermc.org/v1` and `download.geysermc.org/v1` APIs
  are gone (Not Found); the GeyserMC GitHub repos publish no
  Releases/tags.
- ViaVersion / ViaBackwards (official CI lastStableBuild):
  `https://ci.viaversion.com/job/<ViaVersion|ViaBackwards>/lastStableBuild/artifact/build/libs/<Name>-<ver>.jar`
  Query the artifact name first via
  `api/json?tree=buildNumber,artifacts[fileName]`.

Generic acceptance: the boot log shows `[Plugin] Enabling Plugin vX`
with no `Failed to load plugin` / stack traces; plugin visible in
`/plugins`.

## 5. Acceptance checklist (production gate)

- [ ] Boot log version line matches the target MC version (26.2)
- [ ] `Done (..s)` present, no ERROR-level log lines
- [ ] All target plugins `Enabling`
- [ ] Port 25565 listening (`netstat -ano | findstr 25565`)
- [ ] Java client can join TCP 25565; Bedrock client can join UDP 19132
      (Geyser port; a Bedrock client pointed at 25565 fails with no
      server-side connection record)
- [ ] `stop` exits cleanly; second cold start reaches `Done` quickly
      (no migration/patch phase)
- [ ] Data dirs are in the backup set: `world/` + whitelist/ban/usercache
- [ ] A backup with `COMPLETE` exists and `sha256sum -c MANIFEST.txt`
      passes inside it

## 6. Running the server

- Official guidance (README + setup page): run the downloaded jar as a
  normal dedicated-server jar, foreground, in a terminal:
  `java -jar asp-server.jar` (Java 25+ on PATH). The project ships no
  launcher, GUI or service wrapper of its own.
- Project convenience wrappers (not official, in `scripts/`, start the
  server in the sibling `server/` dir):
  - `scripts/start.cmd` (Windows): pins the JDK path, heap flags
    `-Xms2G -Xmx4G -XX:+UseG1GC`; plain call runs in the current
    terminal with no extra window; `-pause` pauses on exit (used by the
    `server/start.cmd` double-click entry, which only `call`s it).
  - `scripts/start.sh` (Linux/macOS): `JAVA` env override, fails fast
    on a missing or non-25 JDK, runs foreground via `exec`.
    Unattended: `nohup scripts/start.sh &` or a systemd unit.
- Both wrappers take a backup before launching (`scripts/backup.cmd` /
  `scripts/backup.sh`). The server is stopped at that moment, so the
  snapshot is consistent - for a server that is not running 24/7 this is
  the natural backup point and needs no scheduler.
  - `ASP_SKIP_BACKUP=1` starts without backing up.
  - `BACKUP_MIN_INTERVAL` skips the backup only when *every* target
    already holds a complete backup that recent (60 minutes when called
    from a start script, 0 when `backup.*` is run directly). This keeps
    restart loops from pushing older backups out of the retention
    window, while a target that fell behind still gets a catch-up run.
  - A failed pre-start backup prints a warning and the server still
    starts. A missing backup is a reason to read the log, not a reason
    to keep the world offline.
- **Targets are a list at the top of each backup script**
  (`BACKUP_TARGETS`), not a single directory. The default is one entry,
  `../backups`; add more to keep a copy on a second disk. This matters
  because backups on the same volume as `server/` are one copy with five
  timestamps, not five copies.
  - Entries are newline-separated in `backup.sh` and semicolon-separated
    in `backup.cmd`. A relative path resolves against the script's own
    directory; absolute paths are used as-is.
  - The **first** entry is the primary target: if it fails, the run
    fails. Later entries are mirrors: a mirror failure prints a warning
    and the run still succeeds, so an unplugged USB disk does not stop
    the local backup. `BACKUP_REQUIRE_ALL=1` makes any mirror failure
    fatal.
  - Every target gets its own full copy and its own `MANIFEST.txt`, so
    the copies are independent - one bad disk cannot corrupt the other.
    Cost is one extra read of `server/` per target (53 MB here).
- Backups land in `<target>/<UTC timestamp>/` (53 MB for the reference
  world, ~96% of it `world/`). Retention is the newest 5 complete
  backups **per target**; partial directories are deleted and never
  counted.
- Pruning only touches directories named like our own timestamps
  (`YYYYMMDD-HHMMSS`). A target may therefore point at a shared folder
  without the script deleting anything else in it.
- `backup.*` refuses to run while the server is up, because copying a
  live world can produce torn region files and SQLite databases
  (CoreProtect, GrimAC). `ALLOW_ONLINE=1` overrides it and prints a
  warning; use it only when you accept an inconsistent snapshot.
- `online-mode=false` is intentional on this deployment: it is
  Floodgate's operating model (section 7).

## 7. Notes and known issues

- `[oshi]` WMI warnings early in the boot and the
  "outdated version ... behind" banner on the 26.2 experimental build are
  expected; safe to ignore.
- Floodgate sets `online-mode` to false in `server.properties`; the
  server will not authenticate accounts and any username can connect.
  This is the documented trade-off of Floodgate
  (https://geysermc.org/wiki/floodgate/).
- `white-list=false` is an intentional, recorded decision (not an
  oversight). Combined with `online-mode=false` it means anyone can join
  with any username. Accepted for this small private SMP; if that changes,
  set `white-list=true` and populate `whitelist.json` (it is in the backup
  set) before exposing the port.
- Without ViaVersion, Geyser on 26.2 warns that it targets a newer Java
  protocol (26.3); installing ViaVersion removes the warning.
- The SWP install doc page
  (https://infernalsuite.com/docs/asp/swp/installation) only says
  "download from our Discord" without a link (page defect); the correct
  source is the download page, same release as the server jar.

## 8. Slime World Plugin (SWP)

Build-locked facts: every statement in this section holds for the build
in `asp-server.jar` / `asp-plugin-*.jar` at SHA `817eeca`
(`26.2.build.128-stable`, develop, 2026-09-22). The `ver/26.2` branch has
moved past this build (tip `0319139` at the time of writing, 15 commits
ahead, including `AnvilWorldReader` / datafixer changes - anvil world
upgrade fixes and a data-version guard on import). If the jar is
upgraded, re-verify this section before relying on it.

Build provenance: the plugin jar's `paper-plugin.yml` `version:` field
contains the build commit SHA, and the boot log prints
`AdvancedSlimePaper version 26.2-...@<sha>`; server and plugin must come
from the same build.

### 8.1 What it is

- Plugin released together with the server jar; stores worlds in the
  Slime Format (SRF) on a pluggable data source; commands under
  `/swp` (aliases `aswm`, `swm`).
- Value: multi-instance operation (one writable + N read-only servers on
  the same world), database storage (mysql/mongodb/redis/api), per-world
  settings, whole-world in-RAM operation. For a single-server survival
  world it adds little.

### 8.2 Where things land

| Path | Class | Content |
| --- | --- | --- |
| `plugins/SlimeWorldManager/worlds.yml` | config | one entry per slime world: `source`, `loadOnStartup`, `readOnly`, `spawn`, `difficulty`, `allowMonsters`, `allowAnimals`, `pvp`, `environment`, `worldType` |
| `plugins/SlimeWorldManager/sources.yml` | config | data sources; `file` active by default, `mysql`/`mongodb`/`redis`/`api` present and disabled |
| `slime_worlds/<name>.slime` | data (regenerable from an Anvil source world) | one file per world for the file source |

### 8.3 Import (Anvil -> slime)

Command: `/swp import <path-to-world> <data-source> [new-world-name]`
(permission `swm.importworld`; requires typing the command twice).

- Non-destructive save-as: reads the world directory, writes a new named
  world into the data source; the source `world/` is not modified;
  duplicate names are rejected; already-loaded worlds cannot be imported.
- One import = one environment. Environment detection heuristic:
  `<dir>/region` exists -> `normal`; else `<dir>/DIM-1/region` ->
  `nether`; else `<dir>/DIM1/region` -> `the_end`. On 1.18+ layouts
  (each dimension has its own `region/` under
  `dimensions/minecraft/<dim>/`), importing `the_nether` or `the_end`
  is misdetected as `normal` and sections are encoded with overworld
  height (384, minY -64) instead of 256/0 -> do not import those
  dimensions on this build. Upstream carries an open TODO for this.
- Import drops POI, block ticks and fluid ticks (not serialized by
  `convertChunk` on this build).
- Size guard: import aborts with a "world too big" error for large
  survival worlds (trim with MCASelector first).

### 8.4 Hosting the main level (optional)

At boot the plugin reads `level-name` from `server.properties`. If a
slime world with that name (and optionally `<level-name>_nether` /
`<level-name>_the_end` when `allow-nether` / `allow-end` are on) is in
`worlds.yml` with `loadOnStartup`, it replaces the vanilla main level
via a Paper patch (`0005-World-overrides`). If the default world fails
to load, the server shuts down. Without such entries the main level
stays a normal Anvil world.

### 8.5 Command set

`help`, `version`, `reload`, `list [slime]`, `goto <world> [player]`,
`dslist <ds>`, `import <path> <ds> [name]`, `create <world> <ds>`,
`clone`, `load`, `load-template`, `unload`, `save`, `setspawn <w> <x y z yaw pitch>`,
`migrate <w> <new-ds>`, `delete <w> [ds]` (delete requires a typed
confirmation twice). `migrate` moves a slime world between data
sources; it is not a format conversion.

Full docs: https://infernalsuite.com/docs/asp/swp/configuration/,
https://infernalsuite.com/docs/asp/swp/commands,
https://infernalsuite.com/docs/asp/swp/converting_worlds

## 9. Fact providers (canonical repos / docs)

Versions are as of this revision. All links below resolve (see the dead
list at the end).

| Component | Role | Repo | Docs / download | Version |
| --- | --- | --- | --- | --- |
| AdvancedSlimePaper | server (MC 26.1+ needs Java 25+) | https://github.com/InfernalSuite/AdvancedSlimePaper | https://infernalsuite.com/download/asp/ | 26.2.build.128-stable @ `817eeca` (2026-09-22, experimental) |
| SWP (ASPaperPlugin) | slime-world management plugin, released with the server jar | as above | as above | 4.2.0-SNAPSHOT @ `817eeca` (same build as server) |
| SkinsRestorer | skin restore/change | https://github.com/SkinsRestorer/SkinsRestorer | https://skinsrestorer.net/ | 15.12.6 |
| Geyser | Bedrock compatibility (UDP 19132) | https://github.com/GeyserMC/Geyser | https://geysermc.org/download/ | 2.12.0-b1259 |
| Floodgate | Bedrock accounts joining Java servers | https://github.com/GeyserMC/Floodgate | https://geysermc.org/wiki/floodgate/ | 2.2.5-SNAPSHOT (b141) |
| ViaVersion / ViaBackwards | cross-version protocol bridge | https://github.com/ViaVersion/ViaVersion | https://viaversion.com | 5.12.2-SNAPSHOT |

Deprecated sources (do not cite):
- https://docs.geysermc.org/ (404; current docs live under https://geysermc.org/wiki/)
- https://api.geysermc.org/v1 and https://download.geysermc.org/v1 (Not Found; v2 works)
- GeyserMC repos have no GitHub Releases/tags; artifacts come from download.geysermc.org/v2

