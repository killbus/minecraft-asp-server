# Paper Multi-World Operations SOP

How to run the server on standard Paper, keep the adventure map off the startup
path, and switch worlds with Multiverse-Core.

Target: Paper 26.2-135, Multiverse-Core 5.8.1, Java 25.

## 0. Architecture

The active engine is standard Paper, not AdvancedSlimePaper:

| Component | Version | Path |
| --- | --- | --- |
| Paper | 26.2-135 | `server/paper-server.jar` |
| Multiverse-Core | 5.8.1 | `server/plugins/Multiverse-Core-5.8.1.jar` |
| PackManagerPro | 2.0.0 | `server/plugins/PackManagerPro.jar` |

Paper 26.x stores every registered world as a dimension under the primary level:

```text
server/world/
  level.dat
  data/minecraft/                    # maps, scoreboards, shared world data
  dimensions/minecraft/overworld/    # hub
  dimensions/minecraft/the_nether/
  dimensions/minecraft/the_end/
  dimensions/minecraft/trials/       # adventure map, normally unloaded
    region/
    entities/
    poi/
    data/minecraft/
```

`trials` is therefore referenced as `minecraft:trials` internally and as
`trials` by Bukkit, Multiverse, and PackManagerPro commands. All worlds share
the same server process and top-level `data/minecraft`; they are not isolated
game instances.

## 1. Startup behavior

`plugins/Multiverse-Core/worlds.yml` controls startup loading with `auto-load`,
not the older `load-on-startup` spelling:

```yaml
minecraft:overworld:
  auto-load: true

minecraft:trials:
  auto-load: false
  difficulty: peaceful
  gamemode: adventure
  spawn-location:
    ==: MVSpawnLocation
    x: -1180.0
    y: 59.0
    z: -131.0
```

The hub loads at startup. `trials` remains registered but unloaded until an
operator or plugin loads it.

Start normally with:

```text
scripts\start.cmd
```

or, on Linux:

```sh
scripts/start.sh
```

The default heap is `-Xms2G -Xmx4G`. A 4 GB live heap is sufficient for the
current hub plus the on-demand adventure world; the old ASP import requirement
of 8 GB was caused by serializing the full Slime world, not by normal Anvil
play.

## 2. World commands

```text
mvtp trials                 # player switches to the adventure map
mvtp world                  # player returns to the hub
mv list                     # shows registered worlds, including UNLOADED
mv load trials              # load the world before the first player enters
mv unload trials            # unload after no players remain
mv info trials              # inspect Multiverse settings
```

`/mvtp` normally loads an unloaded registered world on demand. Use `/mv load`
when preloading or validating the map from console.

Set the map spawn from console:

```text
mv setspawn trials:-1180,59,-131
```

Required Trials gamerules:

```text
mv gamerule set keep_inventory true trials
mv gamerule set mob_griefing false trials
mv gamerule set command_block_output false trials
```

The equivalent vanilla form, useful inside command blocks or `execute`:

```text
execute in minecraft:trials run gamerule keep_inventory true
execute in minecraft:trials run gamerule mob_griefing false
execute in minecraft:trials run gamerule command_block_output false
```

`server.properties` must contain `enable-command-block=true`; the map uses
command blocks for progression.

## 3. Importing the Trials crop

The imported source is the trimmed Anvil crop at
`artifacts/trials-legacy/`, not the full 175-region source map.

1. Start Paper with the hub only.
2. Create the destination dimension skeleton:

   ```text
   mv create trials normal --no-adjust-spawn --no-structures
   ```

3. Rebuild the immutable crop from the operator-supplied source. This only
   rebuilds `artifacts/trials-legacy`; it never touches the live dimension:

   ```text
   python -B scripts/import_trials.py --source "<extracted map root or .rar>" --dest artifacts/trials-legacy --prune
   python -B scripts/verify_artifacts.py
   ```

   The source map root is operator-supplied; the tool also accepts the original
   `.rar` when `unrar` or `7z` is on `PATH` and extracts it to a temporary
   directory. The tool is idempotent: unchanged files are not rewritten, and a
   matching tree reports `copied=0` with the lock hash.

   `scripts/verify_artifacts.py` treats lock paths as normalized relative POSIX
   paths and refuses a path that escapes the artifact root through a symlink or
   junction. Exit codes are **0** = every tree matches, **1** = an artifact is
   missing or drifts, **2** = invalid lock, unsafe path, or an unreadable tree.

4. Stop the server cleanly. Replace the generated chunk storage in
   `server/world/dimensions/minecraft/trials/` with the rebuilt crop:

   ```text
   set COMPAT=artifacts\trials-legacy
   set DEST=server\world\dimensions\minecraft\trials

   rmdir /s /q "%DEST%\region"
   rmdir /s /q "%DEST%\entities"
   rmdir /s /q "%DEST%\poi"
   mkdir "%DEST%\region" "%DEST%\entities" "%DEST%\poi"
   xcopy "%COMPAT%\region\*" "%DEST%\region\" /E /I /Y
   xcopy "%COMPAT%\entities\*" "%DEST%\entities\" /E /I /Y
   xcopy "%COMPAT%\poi\*" "%DEST%\poi\" /E /I /Y
   xcopy "%COMPAT%\data\minecraft\*.dat" "%DEST%\data\minecraft\" /Y
   ```

   Copy `data/minecraft\*.dat`, not all of `data`: the artifact also keeps a
   few source-world files directly under `data/`, copying `data\*` would add an
   extra `minecraft\` level inside the dimension, and `data/minecraft/maps/` is
   world-level map data copied in step 5.

5. Preserve non-chunk map data from the original extracted map. In particular,
   copy `data/minecraft/maps/`, `scoreboard.dat`, `custom_boss_events.dat`,
   `random_sequences.dat`, `stopwatches.dat`, and `world_clocks.dat` into
   `server/world/data/minecraft/`.
6. Do not copy the source `level.dat`. Keep the Paper-generated level metadata
   and set the spawn and gamerules through Multiverse.

The validated crop contains:

- 47 canonical region files (45 previously imported plus `r.-1.3` and `r.0.3`).
- 43,886 chunks.
- 294 files, 367,030,497 bytes, `treeSha256`
  `e3896e8ddaac73078bbb379ecb7bcfcedbffe831d4c094000aaf5d91448c67bc`.
- All documented progression coordinates from the lobby through the ending.
- 644 chunks without a root `DataVersion`: 392/783 in `r.-1.3` and 252/285 in
  `r.0.3`. These are genuine pre-1.13 chunks with the old `Level` wrapper, not
  corrupt data.

The original ASP import excluded those two regions because the ASP importer
failed on chunks without a root `DataVersion`. That is an ASP limitation, not a
Paper one. A probe dimension loaded the same files, upgraded the sampled chunks
to the current `DataVersion`, and preserved block content; the only output was
two non-fatal `No key p` warnings for stale block ticks. The crop and the live
`trials` dimension therefore include both regions. Paper upgrades each legacy
chunk lazily on first access at roughly 1.5 seconds per chunk, so pre-warm the
two regions from console before players are expected there.

The full source map is intentionally not imported. It contains 175 overworld
regions, including legacy chunks, and is not needed for the first playable
migration.

## 4. Resource packs

PackManagerPro uses the lowercased Bukkit world name. Configure the adventure
map as `trials` in `plugins/PackManagerPro/config.yml`:

```yaml
application-type: per-world

per-world-application:
  world:
    pack-url: ''
    force-pack: false
    prompt-message: ''
  trials:
    pack-url: http://127.0.0.1:8000/pack-a.zip
    force-pack: false
    prompt-message: MS Painted - trials
```

PackManagerPro sends the pack on join and on `PlayerChangedWorldEvent`. A world
with an empty `pack-url` clears the previous pack. Restart the server or run
`pmp reload` after editing the file.

The pack file lives in `server/packs/` and is served by a plain HTTP server:

```powershell
scripts\serve-packs.cmd          # python -m http.server 8000 --directory server\packs
```

```sh
scripts/serve-packs.sh           # PACK_PORT=8000 by default
```

`PackManagerPro` sends the URL to the client, so `127.0.0.1` only reaches a
client running on this machine. For remote Java clients, point `pack-url` at an
address they can reach, or keep the pack behind the same proxy/Geyser path the
players already use. Verify with the HTTP access log after `/mvtp trials`.

`server/packs/` is externally sourced and regenerable, so it is deliberately
**not** part of the server snapshots. Record the variant instead:

- upstream: `MS Painted for 26.1-26.3 (v2.49)` by Stridey;
- local variants differ only in `pack.mcmeta`'s `description`
  (`MS Painted - test_world` for `pack-a.zip`,
  `MS Painted - test_nether` for `pack-b.zip`); all 11,802 archive entries
  are otherwise identical;
- `pack-a.zip` sha256:
  `72cafcfa3a780de9485d686d7afe2d69e07582f7ab10ad9c02ccaf4edb0928bb`.

Rebuild by unzipping the upstream pack, editing that description, and
rezipping. A rezip need not reproduce the byte-identical archive, so use the
hash to detect drift rather than as a download guarantee.

## 5. Permissions

The MVP can run with OP-only staff. For ordinary players, grant the specific
Multiverse destination nodes. `server/permissions.yml` contains a conservative
default:

```yaml
multiverse.core.list.worlds:
  default: true
multiverse.teleport.self.w.trials:
  default: true
multiverse.teleport.self.w.world:
  default: true
```

For production membership management, LuckPerms is the mature choice: assign
`multiverse.teleport.self.w.trials` and `multiverse.teleport.self.w.world` to a
player group, and reserve `/mv load`, `/mv unload`, `/mv import`, and
`/mv setspawn` for staff. Multiverse's own permission checks remain the source
of truth; LuckPerms only stores and assigns the nodes.

## 6. Memory and chunk behavior

Measured on 2026-11-17 with Paper 26.2-135, Java 25, and
`-Xms2G -Xmx4G -XX:+UseG1GC`, after `jcmd <pid> GC.run`:

| State | Live heap (`GC.heap_info`) |
| --- | ---: |
| Hub only, `trials` unloaded | 446,137 KB (~436 MB) |
| `trials` loaded, 355 persistent chunks | 494,863 KB (~483 MB) |
| After `/mv unload trials` | 446,428 KB (~436 MB) |

For comparison, the previous ASP `test_world` kept all 42,818 chunks resident
and measured about 3.49 GB live heap. Paper loads chunks around players and
active tickets, then releases them; the full map is never resident merely
because the world is registered.

Check the current process with:

```powershell
Get-Process -Name java | Select-Object Id,StartTime
& 'D:\Applications\Scoop\apps\temurin25-jdk\current\bin\jcmd.exe' <pid> GC.run
& 'D:\Applications\Scoop\apps\temurin25-jdk\current\bin\jcmd.exe' <pid> GC.heap_info
```

Do not judge memory by `-Xmx`. Use live heap after GC and compare the loaded,
unloaded, and no-player states.

### Load latency

Measured on 2026-11-17 against the migrated crop, with 355 persistent chunks:

| Event | Duration |
| --- | ---: |
| First `/mv load trials` after import | 12,989 ms |
| Second `/mv load trials` after `/mv unload` | 994 ms |

The first load paid a one-time chunk upgrade from the legacy `DataVersion`
range (922-4903) to 26.2 and rewrote the region files. It held the server
thread long enough to trigger Paper's 10-second watchdog thread dump, which is
expected during that one-time upgrade and is not a crash. After the rewrite,
the same world loads in about one second.

`/mv load` and `/mvtp` into an unloaded world run on the server thread, so a
switch briefly stalls every player. At ~1 second this is acceptable; after
importing or replacing a legacy map, run `mv load trials` once from console
before opening the server so players do not pay the upgrade cost. If a future
map stays slow to load, switching that world to `auto-load: true` trades the
one-time stall for a small resident-chunk cost (~50-120 MB measured here).

## 7. Backup and rollback

Paper 26.x keeps all registered dimensions under `server/world/dimensions/`.
Backing up the whole `server/world/` tree therefore covers the hub, nether,
end, and `trials` together. The backup scripts also include:

- `plugins/Multiverse-Core/worlds.yml`
- `plugins/PackManagerPro/config.yml`
- `permissions.yml`
- `server.properties` and `config/`

Geyser and SkinsRestorer `cache/` directories are regenerable and excluded;
do not widen that exclusion to other plugins without checking their state.
Resource packs under `packs/` are excluded for the same reason; their
rebuild recipe and `pack-a.zip` hash are in section 4.
With the Trials dimension imported, one snapshot is roughly 0.5 GB; the
default `KEEP=5` therefore needs about 2.5 GB per target.

`server/world/data/minecraft/maps/` is shared by all dimensions. Increasing
the map count changes this directory, so it must stay in world backups.

`artifacts/` is immutable input: it stays out of git and out of the server
runtime tree, is described by `artifacts.lock.json`, and is verified with
`python -B scripts/verify_artifacts.py` after any copy or restore.

Because the tree never changes, one verified mirror is enough; do not rotate
it with the server backups. Mirror it next to the lock file and verify the
copy:

```text
robocopy artifacts <backup-root>\artifacts /MIR /R:1 /W:1
copy artifacts.lock.json <backup-root>\artifacts.lock.json
python -B scripts/verify_artifacts.py --root <backup-root>
```

A new map import adds a new artifact entry; do not replace an existing
artifact's tree in place, otherwise the recorded hashes stop describing it.
Correcting descriptive metadata is safe when `files`, `bytes`, and
`treeSha256` are re-verified afterwards.

## 7a. Login destination and unloaded worlds

Paper resolves a returning player's saved dimension on login. If that
dimension is not registered and loaded, the player can land in the default
overworld at the saved coordinates, which may be ungenerated terrain. With
`trials` set to `auto-load: false`, pin every login to the hub in
`plugins/Multiverse-Core/config.yml`:

```yaml
spawn:
  enable-join-destination: true
  join-destination: world
```

The current server config has these values, so a returning player logs in at
the hub even if they logged out inside `trials`.

Change `join-destination` to `trials` to make the adventure map the login
world instead. Either value is preferable to leaving it empty while an
on-demand world is registered.

The previous ASP engine and its Slime worlds were moved, not deleted, to:

```text
server/.rollback/asp-<timestamp>/
```

To roll back, stop Paper, restore the ASP server JAR, ASP plugin,
`plugins/SlimeWorldManager/`, `slime_worlds/`, and the ASP config from that
directory, then start the old JAR. Keep a stopped-server snapshot before any
rollback trial.

## 8. Known boundaries

- Multiverse worlds are dimensions of one Paper server. Scoreboards, maps, and
  other top-level data are shared; use a separate server or a later
  engine-profile switch if strict isolation is required.
- This task does not implement hot switching between Paper and ASP.
- This task imports only the trimmed Trials crop, not the full source map.
- Geyser's built-in NetherNet signaling still fails on this host because the
  advertised address is in a special-purpose range. That is independent of
  the world migration; the relay configuration remains authoritative.
