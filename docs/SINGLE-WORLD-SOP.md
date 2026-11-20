# Single-world Paper startup

This branch runs one Paper 26.2 build 135 process with one selected primary
native save. Stop the process, select a save, then start again. Its normal
Nether and End dimensions remain part of that game's world family.

## Stop, select, start

1. Enter `stop` in the running server console and wait for Java to exit.
2. Choose an existing complete save directly under `server/`, for example
   `server/Adventure_A/level.dat` or `server/Puzzle-2/level.dat`.
3. Run one of these commands from the repository:

   ```sh
   scripts/start.sh --world Adventure_A
   ```

   ```bat
   scripts\start.cmd --world Adventure_A
   scripts\start.cmd --world Puzzle-2 -pause
   ```

Without `--world`, startup uses Paper's normal `server.properties`
`level-name` behavior, including world creation when the default is absent.
Explicit selection is for existing saves only: a missing `level.dat` refuses
startup before backup or Java. A name must contain only ASCII letters,
digits, underscores and hyphens. Paths, spaces, extra arguments and repeated
`--world` flags are refused. The explicit save directory and its `level.dat`
must not be links or junctions. `-pause` is Windows-only and may appear before
or after the world option.

The scripts pass Paper's native `--world NAME` argument. They do not rewrite
`server.properties`, rename saves or remember the last selection. Repeat the
option on every start that needs it. Switching requires another graceful
stop. Do not start a second process against this directory.

Java 25+ is required. Bash uses `JAVA` or `java` on PATH. CMD uses `JAVA` when
set to the full Java executable path, otherwise the existing local Scoop JDK
25 path. The existing heap settings remain in `scripts/start.*`.

## Prepare a complete native save

Prepare the save separately while the server is stopped. Keep an untouched
source copy and put the complete compatible native save tree under its chosen
name. Preserve its `level.dat`, region/entity/POI files, `data/`, dimensions,
datapacks and player files. Minecraft versions differ in their storage layout;
copy the entire tree instead of selecting individual files. Preserve any
associated native dimension directories if the source uses sibling worlds.

The launcher's `level.dat` check prevents a misspelling from creating an empty
world. It does not validate NBT, upgrade old formats or prove that the save is
complete. A lone Multiverse dimension folder, a cropped dimension artifact,
or a Slime-format world is not automatically a complete primary save. Prepare
and validate a complete native save in a separate disposable server first.
This branch supplies no import or migration command.

Native player state, statistics, advancements, scoreboard/objectives/teams
and dimension data belong to the selected save. Server configuration,
whitelist/ban/operator lists and plugin configuration/databases are shared.
Plugins can impose their own state rules; selecting a save does not provide
per-map plugin-data isolation. There is no hot switching or Multiverse,
Multiverse-Inventories, WorldLifecycle or statistics-board integration here.

## Runtime installation

Use the `paper` entry in `runtime.lock.json` for the exact download URL and
SHA-256, and install it as `server/paper-server.jar`:

```text
Paper 26.2 build 135
SHA-256: ef3dbc68b013deafdbbee3bebf1ba351671ebcda94a8f136809b7532d5ba2fe1
```

This branch replaces the ASP server and removes ASP's plugin from the lock.
It does not remove installed files or alter any existing runtime. Prepare a
separate stopped runtime with the declared artifacts; an old ASP JAR or plugin
left beside them is reported as unmanaged. Other plugin hashes remain the
historical inventory and require compatibility validation on the intended
host. No new host installation or gameplay validation is claimed here.

```sh
python -B scripts/verify_runtime.py --server-dir server
```

Exit `0` means the declared inventory matches, `1` means missing/modified/
unmanaged artifacts and `2` means invalid metadata or an incomplete check.
The verifier is read-only. The historical default-world datapack remains
locked under `world/datapacks`; another selected save owns its own datapacks.
The verifier only inventories the explicitly listed datapack directories.

## Backups and restore

Pre-start backups retain the existing 60-minute minimum interval and retention
policy. `ASP_SKIP_BACKUP=1` remains the compatibility override. To force a
fresh pre-start copy, set `BACKUP_MIN_INTERVAL=0`. To back up while stopped:

```sh
scripts/backup.sh
```

```bat
scripts\backup.cmd
```

Every top-level directory containing a `level.dat` file is copied under its
original name, including inactive saves and any native sibling dimensions.
Server and plugin configuration/data retain the existing backup scope.
JARs, libraries, logs, `session.lock`, `level.dat_old` and the documented
Geyser/SkinsRestorer caches remain excluded. There is no world registry.
`backup-debug.cmd` delegates to the same Windows backup with tracing enabled.

Backups refuse a detected `paper-server.jar` process unless `ALLOW_ONLINE=1`
is explicitly set; that override cannot guarantee a consistent snapshot.
Detection is conservative across matching processes on the host. Use a
completed snapshot with its `COMPLETE` marker and verify `MANIFEST.txt` before
restoring complete save trees while stopped. Select the restored primary
name with `--world`. Preserve a separate copy of the previous state first.
