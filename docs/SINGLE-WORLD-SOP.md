# Single-world Paper startup

This branch runs one Paper 26.2 build 135 process with one selected primary
native save. Stop the process, select a save, then start again. Its normal
Nether and End dimensions remain part of that game's world family.

## Update a stopped deployment

1. Stop the scene with `scripts/scenes/frpc-shared-tcp.sh down` (or `frpc.sh
   down` for the plain scene). For direct startup, enter `stop` in the console.
   Wait for Java to exit, then run `scripts/backup.sh` or `scripts\backup.cmd`.
   Check the snapshot's `COMPLETE` marker and `MANIFEST.txt` before updating.
2. Fetch the published test branch and update it without replacing local work:

   ```sh
   git fetch origin
   git switch feat/single-world-start
   git pull --ff-only origin feat/single-world-start
   ```

3. Review the stopped runtime with `python -B scripts/verify_runtime.py`.
   Git updates do not remove ignored JARs. Move any old ASP, Multiverse-Core,
   Multiverse-Inventories, PackManagerPro, WorldLifecycle or statistics-sidebar
   JARs out of `server/plugins/` into an operator-owned quarantine outside the
   runtime. Review every other unmanaged JAR too. Preserve plugin data for
   rollback; these scripts perform no plugin migration or removal.
4. Install the pinned runtime and review/apply configuration as described below.
   Keep existing host settings; create an example copy only when no host file
   exists. Prepare the selected complete native save and start one scene or
   one direct launcher. Check the console and client behavior before admitting
   players. The repository's fixture tests do not establish gameplay safety.

For rollback, stop all processes and restore the previous complete runtime,
configuration, saves, plugin state and host settings from operator-owned
copies. Git alone cannot restore ignored binaries or data. Never overwrite a
newer save with an older snapshot without first preserving the newer state.

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

The scripts pass Paper's native `--world NAME` argument. Paper itself saves
resolved properties, including this selected `level-name`, into its active
properties file. With the optional pack policy below, that file is disposable
and the canonical `server/server.properties` is unchanged. Without a policy,
Paper uses and may update the canonical file. Repeat `--world` on each start
to make the intended selection explicit. Switching requires a graceful stop.
Do not start a second process against this directory.

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

### Restart Trials from the original download

The inspected `trials-of-the-past-52637.rar` from
[Trials of the Past](https://www.minecraftmaps.com/52637-trials-of-the-past)
already contains a complete native 26.2 save. Its SHA-256 is
`2b7710df040aaa37666b6d284bc24122f897317dbcdebb9bd213f62409f7f91c`.
Use that whole save, not the old
`world/dimensions/minecraft/trials` directory. Keep `world/` intact.

Upload the original RAR to `.tmp/` on the stopped host. These commands assume
7-Zip's `7z` command is installed; both the staging path and destination must
be absent. Run from the repository root:

```sh
(
  set -eu
  printf '%s  %s\n' \
    2b7710df040aaa37666b6d284bc24122f897317dbcdebb9bd213f62409f7f91c \
    .tmp/trials-of-the-past-52637.rar | sha256sum -c -
  test ! -e .tmp/trials-fresh
  test ! -L .tmp/trials-fresh
  test ! -e server/trials
  test ! -L server/trials
  7z x .tmp/trials-of-the-past-52637.rar -o.tmp/trials-fresh
  test -f '.tmp/trials-fresh/Trials of the past/level.dat'
  mv -nT -- '.tmp/trials-fresh/Trials of the past' server/trials
  test ! -e '.tmp/trials-fresh/Trials of the past'
)
```

This preserves root metadata, scoreboard/objectives, map data, and all dimensions.
No generated metadata, region trimming or staged 1.12 conversion is needed for
this particular archive. Another download revision must be inspected separately.

A disposable full copy reached `Done` on pinned Paper 26.2-135 and saved cleanly
on stop. Its six original scoreboard objectives and `keep_inventory=true`
remained. This is startup validation, not a complete gameplay test. Three old
Nether chunks `(1,-8)`, `(1,-9)`, `(0,-11)` logged missing tick-priority field
`p`; their nine old pending block updates were discarded on conversion, while
their terrain remained. The archive is preserved unchanged; do not describe
this conversion as lossless or delete those chunks to suppress the message.
The current template's default game mode/difficulty differ from the map's
adventure/peaceful metadata. Its entry command blocks include adventure-mode
setup; verify the fresh-player introduction before opening play to everyone.

Native player state, statistics, advancements, scoreboard/objectives/teams
and dimension data belong to the selected save. Server configuration,
whitelist/ban/operator lists and plugin configuration/databases are shared.
Plugins can impose their own state rules; selecting a save does not provide
per-map plugin-data isolation. There is no hot switching or Multiverse,
Multiverse-Inventories, WorldLifecycle or statistics-board integration here.

## Runtime installation

`runtime.lock.json` pins Paper and the independent plugins. The installer
downloads those exact URLs, checks SHA-256 and installs Paper as
`server/paper-server.jar`:

```text
Paper 26.2 build 135
SHA-256: ef3dbc68b013deafdbbee3bebf1ba351671ebcda94a8f136809b7532d5ba2fe1
```

```sh
python -B scripts/install_runtime.py --server-dir server --dry-run
python -B scripts/install_runtime.py --server-dir server
python -B scripts/verify_runtime.py --server-dir server
```

The installer reports `OK`, `INSTALL`, `DRIFT`, `MANUAL` or `FAIL`. Existing
matching artifacts are unchanged; differing artifacts require an explicit
`--replace` after review. `--only paper` selects one declared artifact. A
missing pinned download fails; it never substitutes a latest build or changes
the lock hash. Installer exit `1` includes planned downloads in a dry run.

Verifier exit `0` means the declared inventory matches, `1` means missing/modified/
unmanaged artifacts and `2` means invalid metadata or an incomplete check.
The verifier is read-only. The historical default-world datapack remains
locked under `world/datapacks`; another selected save owns its own datapacks.
The verifier only inventories the explicitly listed datapack directories.

## Apply configuration and host settings

`config/` and `config.lock.json` hold reviewed templates. Application replaces
only declared configuration files; native save trees, player files, databases,
plugin instance state and host settings are protected. Review host-specific
configuration changes before applying: source configuration is deliberately
replaced, so manual edits to those files must be reconciled first.

On first deployment only:

```sh
[ -f settings/minecraft-server.json ] || cp settings/minecraft-server.example.json settings/minecraft-server.json
```

On Windows, use `if not exist settings\minecraft-server.json copy
settings\minecraft-server.example.json settings\minecraft-server.json`.
Edit `values` for the public Geyser UDP advertisement and deployment coordinates.
Configure optional global or save-specific packs in `resource_packs`, as below.
Supply `MANAGEMENT_SERVER_SECRET` through the host environment; the example
contains `env:MANAGEMENT_SERVER_SECRET`, not a credential. Keep any existing
host JSON instead of replacing it with the example during an update.

```sh
python -B scripts/apply_config.py --settings settings/minecraft-server.json --dry-run
python -B scripts/apply_config.py --settings settings/minecraft-server.json
python -B scripts/apply_config.py --settings settings/minecraft-server.json --check
```

`--set NAME=VALUE` overrides `values`, then settings override environment,
then declared defaults apply. When `resource_packs` exists, it owns pack selection:
the renderer clears the canonical native pack and refuses a conflicting nonempty
`--set PACK_URL`. Required values missing from every source fail
before any write. `--dry-run` previews `CREATE`, `UPDATE` and `UNCHANGED`;
`--check` exits `1` for differences and writes nothing. Invalid input exits `2`.
Host JSON is ignored by git and backed up with the server. The renderer uses
explicit `--settings`; startup reads `settings/minecraft-server.json` for its
optional pack policy without resolving unrelated `env:` credentials. Restore
the file only to its originating host.

The default template uses `level-name=world`; applying it sets that default.
Always pass `--world NAME` for a named existing save when that is your intended
selection. There is no settings or environment world registry.

## Native resource packs and production scenes

For legacy host files without `resource_packs`, `PACK_URL` renders Paper's native `resource-pack` property
for the active process. Choose `"PACK_URL": ""` explicitly to offer no pack, or set a public
`https://<entry-host>:<port>/packs/<file>.zip` URL. The key remains required;
`--set PACK_URL=` explicitly clears it for one apply. Plain HTTP is allowed
only for loopback testing (`127.0.0.1`, `localhost`, `[::1]`). The template uses
`require-resource-pack=false`; SHA-1, ID and prompt remain empty. For cached
downloads and automatic selection by startup save, use the policy below.
Java packs are not automatically converted into Bedrock resource packs.

### Global or save-specific pack policy

Add `resource_packs` alongside `values` in your existing
`settings/minecraft-server.json`. Both direct launchers read that section
automatically; deployment continues using the same file with
`apply_config.py --settings settings/minecraft-server.json`. Keep existing values and credentials.
The single host file stays ignored by Git and enters host-settings backups.
The new example has `default: null` and empty `worlds`, so it offers no pack
until configured.

For Painted only when starting `trials`:

```json
{
  "schema_version": 1,
  "values": {
    "GEYSER_ADVERTISE_ADDRESS": "<your-existing-UDP-entry>:<port>",
    "MANAGEMENT_SERVER_SECRET": "env:MANAGEMENT_SERVER_SECRET"
  },
  "resource_packs": {
    "default": null,
    "worlds": {
      "trials": {
        "url": "https://<your-existing-entry-host>:<port>/packs/pack-a.zip",
        "sha1": "<40 hexadecimal characters from the served ZIP>"
      }
    }
  }
}
```

Compute the digest from the exact file being served, not from a differently
repacked original download:

```sh
sha1sum server/packs/pack-a.zip
python3 -B scripts/select_resource_pack.py --world trials --check
python3 -B scripts/select_resource_pack.py --world world --check
```

Windows equivalent: `Get-FileHash -Algorithm SHA1 server/packs/pack-a.zip` and
`python -B scripts/select_resource_pack.py --world trials --check`.

With the section present, `apply_config.py` always renders an empty canonical
`resource-pack`; startup supplies the actual selection. Remove old
`values.PACK_URL` after migration: its value and environment `PACK_URL` are
ignored under this policy, while a conflicting nonempty `--set PACK_URL` fails.
Without the section, startup retains native properties and does not apply
deployment values itself. Removing a policy does not automatically clear an
older canonical pack setting, so inspect that file when reverting to legacy mode.
The no-policy path leaves native first-run properties creation and implicit
`level-name` handling to Paper; the explicit `--world NAME` validation is unchanged.

If you already created `settings/resource-packs.json` from the earlier version,
move its `default` and `worlds` into this section, leaving schema_version only
at the host document root. Then remove the redundant file after reviewing the
merge. Startup reports a migration error while that old file exists, avoiding
a silent fallback or two competing sources. Do not replace the host file with
the example during an update.

- `default: null`: unspecified saves offer no pack.
- A pack object in `default`: all saves inherit that pack.
- A named entry in `worlds`: that save overrides the default.
- A named entry set to `null`: that save explicitly disables even a global pack.

Names refer to the selected primary save (`--world`, otherwise `level-name`),
not dimensions within it. The selected pack covers that running game's Nether
and End too. Changing selection still requires stop/start; no additional scene
argument is needed. An invalid host document refuses Java startup. Python 3 is
needed when the host file exists, including legacy files without the new section.
Without a host file the native launcher path does not require Python.
Scene sidecars may already be running when that validation fails;
use the helper's `--check` before scene startup to inspect the selection.

Startup projects the URL and mandatory SHA-1 into
`.tmp/startup/server.properties`, clears legacy pack hash/ID fields, and passes
Paper `--config` for that file. Paper derives a stable ID from the URL. Native
required/prompt flags and other canonical properties remain effective. Neither
the save nor canonical properties are modified by this projection. Paper may
write to the generated file while running; property changes made through its
management API therefore do not persist across regeneration. Make durable
changes in the canonical configuration. Do not edit or delete the active
generated file while Paper is running.

### Reconnect, download and reload

On login the server offers the pack again. The Java client chooses whether to
fetch bytes or reuse its cache, then activates the resources. The Mojang reload
screen can appear on a cache hit too. In inspected 26.2 and 26.3 clients, a valid
matching SHA-1 allows a cache return before opening HTTP. An empty/invalid hash
instead downloads the bytes before deduplicating by their computed hash.
Changing the URL also changes the native default ID and can require one new
download; keep the URL stable while the content is unchanged.

To distinguish these cases, observe the packs sidecar's access log during a
reconnect. A new `GET /packs/pack-a.zip` with a full `200` transfer is download
evidence. Client `latest.log` may instead say `Returning cached file since
actual hash matches requested` followed by `Reloading ResourceManager`.
Repeated entries in the client's `downloads/log.json` alone do not prove HTTP
traffic: it records cache returns as well. These facts concern Java edition;
Geyser does not turn this ZIP into a Bedrock pack.

### Serving packs through the existing entry

Place regenerable pack ZIPs under `server/packs/` and retain their source and
hash separately. The packs server strips `/packs/` and serves this directory.
The shared scene owns it with `--serve-packs`, or forwards to an independently
managed server with `--packs 127.0.0.1:8000`. These modes are mutually exclusive.
Owned serving derives the prefix from the served directory name (`/packs/`
by default). For an external backend, `MUX_PACKS_PREFIX` selects its prefix;
use the same prefix in the public URL and backend server configuration.

For production, keep frpc manifests/configs, binaries, combined certificate/key
PEMs and credentials outside the repository. `examples/scenes/` demonstrates
the manifest format. Each section owns one frpc process; relative paths resolve
beside the manifest. The official frpc binary carries the UDP media tunnel;
provider frpc can own TCP entries. Point TCP frpc at HAProxy `127.0.0.1:25566`,
not directly at Paper. A typical preview is:

```sh
scripts/scenes/frpc-shared-tcp.sh up --scene /path/to/production.scene \
  --tls-cert /path/to/entry-combined.pem --proxy-protocol \
  --serve-packs --packs-port 8000 --world Adventure_A --dry-run
```

Review the preview, then repeat without `--dry-run`, adding `--no-attach` when
desired. Optional `--world NAME` follows the same grammar, native-save and link
checks as direct startup, before orchestration begins. Plain `frpc.sh up
--scene ... --world Adventure_A` supports selection too. A plain server-less
scene cannot select a world. Omit the option to retain the existing default.

The shared scene starts frpc sidecars, then HAProxy, then its packs sidecar
when requested, and starts Paper only after prerequisites are ready. TCP traffic
enters the shared frontend: Java goes to Paper, TLS goes through termination,
and decrypted HTTP is inspected before routing `/packs/` to the pack server
or signaling to Geyser. The TLS frontend waits for decrypted HTTP bytes before
making that routing decision.
NetherNet media uses the separate UDP tunnel to Geyser `19132`.

The tracked configuration enables Paper `proxies.proxy-protocol` and Geyser
`advanced.java.use-haproxy-protocol`. Pair it with `--proxy-protocol` and frpc
TCP `transport.proxyProtocolVersion = "v2"`. The generated LAN frontend at
`0.0.0.0:25564` accepts ordinary Java connections and supplies the header to
Paper; use `MUX_LAN_JAVA` to choose another LAN bind. Direct Java clients must
use that frontend while Paper expects PROXY. A custom `--haproxy-config` owns
the entire configuration, including any LAN frontend and pack routes.

`status` reports mux and certificate state; `attach` opens the scene. Use the
same `FRPC_SESSION` for non-default sessions. Certificate renewal remains an
external operation: replace the combined PEM, then run
`scripts/scenes/frpc-shared-tcp.sh reload`. Near expiry warns but does not
prevent startup; missing/unusable certificate material does. `down` gracefully
stops the owned server/sidecars and stops the owned mux. Do not start another
launcher while the scene still owns Paper.

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
The repository's `settings/` contents are included except `*.example.json`;
`SETTINGS_DIR` overrides the source. Keep this directory limited to host settings.
JARs, libraries, logs, `session.lock`, `level.dat_old` and the documented
Geyser/SkinsRestorer caches and regenerable `server/packs/` remain excluded.
There is no world registry. Save names must not collide with the configuration,
plugin or snapshot-settings directories (`config`, `plugins`, `settings`);
backups refuse such a tree instead of mixing state.
`backup-debug.cmd` delegates to the same Windows backup with tracing enabled.

Backups refuse a detected `paper-server.jar` process unless `ALLOW_ONLINE=1`
is explicitly set; that override cannot guarantee a consistent snapshot.
Detection is conservative across matching processes on the host. Use a
completed snapshot with its `COMPLETE` marker and verify `MANIFEST.txt` before
restoring complete save trees while stopped. Select the restored primary
name with `--world`. Preserve a separate copy of the previous state first.
