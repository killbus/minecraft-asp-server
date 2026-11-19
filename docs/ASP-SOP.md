# AdvancedSlimePaper (ASP) Operations SOP

> **Legacy / reference only.** The active runtime is standard Paper 26.2 with
> Multiverse-Core. Use [PAPER-WORLD-SOP.md](./PAPER-WORLD-SOP.md) for normal
> operations. There is no archived ASP engine to restore: no `.rollback` copy
> exists on the host, and `server/` is gitignored so the repository never
> carried one. This document describes the ASP layout and is not a rollback
> path.

How to take an ASP server from scratch to production-ready.
Target: ASP 26.2 (Minecraft 26.2). Last updated: 2026-11-14.

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
| Program (dropped in) | `world/datapacks/*.zip` | World datapacks, not plugins; included in the whole-world backup |
| Config (source, in git) | `server.properties`, `bukkit.yml`, `spigot.yml`, `commands.yml`, `permissions.yml`, `config/paper-global.yml`, `config/paper-world-defaults.yml`, per-plugin declarative yml | Lives in `config/` and `config.lock.json`; apply with section 2a, not by hand |
| Operator state (instance) | `eula.txt`, `whitelist.json`, `ops.json`, `banned-*.json`, `usercache.json` | Never applied from the bundle |
| Generated state (instance) | `plugins/*/worlds.yml`, `anchors.yml`, `key.pem`, `*.db`, caches, `nethernet/` | Never applied from the bundle |
| Data (not regenerable - back these up) | `world/` (`level.dat`, `data/`, `dimensions/`, `players/`), `whitelist.json`, `ops.json`, `banned-*.json`, `usercache.json` | Backup policy centers on these |
| Sensitive instance state (back up, never commit) | `plugins/Geyser-Spigot/nethernet/` (`provider-state/`, `identity.pem`, `operator-link.txt`) | NetherNet/Warden identity; restoring it keeps the same `*.wdn.gg` name. Contains a private key - never commit, share or paste it |
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

Known-regenerable plugin caches (`plugins/Geyser-Spigot/cache/`,
`plugins/SkinsRestorer/cache/`) are also excluded from backups. Do not
generalize this to every `*/cache/` directory: a plugin may keep real
state under that name, so each exclusion needs the same evidence.

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

### 2a. Declarative configuration

Do not hand-edit `server.properties`, `config/paper-*.yml` or a plugin's
declarative yml on a deployed host. They are tracked in this repository:
`config/` holds the templates and `config.lock.json` holds each SHA-256.

```text
[ -f settings/minecraft-server.json ] || cp settings/minecraft-server.example.json settings/minecraft-server.json
python -B scripts/apply_config.py --check --settings settings/minecraft-server.json
python -B scripts/apply_config.py --dry-run --settings settings/minecraft-server.json
python -B scripts/apply_config.py --settings settings/minecraft-server.json
```

Run it only with the server stopped. `--check` exits 0 when the host already
matches, 1 when it differs, and 2 when the bundle is unsafe (hash drift, an
instance path, a missing value). See
[PAPER-WORLD-SOP.md](./PAPER-WORLD-SOP.md) section 7b for the class rule.

`settings/<host>.json` holds the public per-host coordinates. The `cp` above
is the first deploy on a host only: the real file is gitignored, the tracked
one is `settings/<host>.example.json`, and the snapshot in section 7 is the
copy that survives. The credential is written as
`env:MANAGEMENT_SERVER_SECRET` and exported in the shell, so the file holds no
secret. Precedence is `--set` > settings > environment > manifest default;
`--set` remains the one-off override. Never put the settings file in
`config/` - every file there must mirror a `server/` path.

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
   `plugins/<name>/` (including `plugins/Geyser-Spigot/nethernet/`, which
   keeps the server's Warden host name), `plugins/*.yml`, and the top-level
   `*.json`, `*.yml`, `server.properties`, `eula.txt`, `server-icon.png`.
   Restore `settings/*.json` under the repository's `settings/` directory,
   not `server/`: it is the deploy input, and a snapshot's copy belongs to
   the host it came from.
   Plugin jars are not in the backup. Reconcile them with the lock revision
   associated with this backup before starting; a newer plugin may not work
   with older restored data. See section 4.1.

   Restoring the instance files is correct here because the backup came from
   this host and describes this world set. Onto a *different* host the same
   copy is a deploy, not a restore: use `scripts/apply_config.py` (section 2a)
   and leave `worlds.yml`, `key.pem`, the databases and the player files alone.
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

Plugin roles (exact installed versions, paths and hashes live in
[`runtime.lock.json`](../runtime.lock.json)):

| Plugin | Notes |
| --- | --- |
| SWP (ASPaperPlugin) | shipped with the server jar; keep the builds paired |
| Geyser-Spigot | Bedrock bridge; NetherNet needs signalling before any UDP traffic, see 4.2 |
| Floodgate | Bedrock accounts joining; used alongside Geyser |
| ViaVersion / ViaBackwards | cross-version protocol bridge |
| SkinsRestorer | runs in Floodgate Mode while Floodgate is present |
| CoreProtect | block logging and rollback; local file is CE-named |
| GrimAC | anti-cheat |
| LoginTo (fork) | offline Java accounts, `/register` + `/login`; see 4.3 |

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

### 4.1 Runtime inventory and offline verification

Keep `server/` ignored by Git. Track **metadata, not binaries**, in
`runtime.lock.json`. The lock records the intended file inventory, not
whether a plugin or datapack is enabled. It contains no compatibility
status or acceptance workflow: a matching hash is not a compatibility or
security guarantee.

Run from the repository root with Python 3.10+ (standard library only):

```sh
python -B scripts/verify_runtime.py
```

On systems where Python 3 is named `python3`, use that instead. Default
lock and server paths are relative to the script's repository, regardless
of the current directory. Explicit `--lock` and `--server-dir` paths are
relative to the caller's current directory:

```sh
python -B scripts/verify_runtime.py --lock runtime.lock.json --server-dir server
```

The command is offline and read-only: no downloads, file replacement,
automatic hash adoption, lock rewriting, or server startup. It is not
wired into the start scripts. Run it manually after an installation,
upgrade or restore, with no artifact changes in progress.

| Result | Meaning |
| --- | --- |
| `OK` | Declared file exists and its SHA-256 matches |
| `MISSING` | Declared file is absent |
| `MODIFIED` | Content differs; expected and actual SHA-256 are printed |
| `UNMANAGED` | An installation file is present but not in the lock |
| `ERROR` | Invalid lock, unsafe path, or incomplete check due to an I/O error |

Exit codes: **0** = all match, **1** = inventory drift, **2** = invalid
input or an incomplete check. Fix the input/read error before trusting
a result; do not overwrite a stored hash just to make the check green.

Scan boundaries are deliberately narrow:

- Direct `server/*.jar` (the declared server must be `paper-server.jar`).
- Direct `server/plugins/*.jar`; no recursion into plugin directories.
- Direct ZIP files in each explicitly listed `datapack_directories`
  entry, currently `world/datapacks`. An unpacked directory containing
  `pack.mcmeta` is reported as `UNMANAGED`; v1 locks ZIPs only.
- No scanning of other worlds, caches, remapped JARs, dependencies,
  configuration or player data. Add another world's datapack directory
  explicitly when needed; changing `level-name` does not change the lock.

Missing scan directories are allowed if no declared file requires them;
a missing server root is an error. Paths resolving outside the server
root through symlinks or junctions are refused.

**Lock format:** `schema_version` is `1`; `datapack_directories` is an
array of paths; `artifacts` contains exactly one server and any plugins
or datapacks. Each artifact requires:

| Field | Meaning |
| --- | --- |
| `id` | Stable, unique component identifier |
| `kind` | `server`, `plugin` or `datapack` |
| `path` | Exact install path relative to `server/`, using `/` |
| `version` | Human-readable version string, including SNAPSHOT if applicable |
| `source` | HTTP(S) project or specific release URL |
| `sha256` | 64 hexadecimal digits identifying the installed file |

Optional fields are `build` (nonblank string), `download_url` (fixed
artifact URL), and `notes` (string). Top-level `notes` is also optional.
Record a build number or commit for snapshots when known. Omit unknown
builds/URLs rather than inventing them; do not use `latest` or
`lastStableBuild` as a pinned download URL. Those endpoints in section 4
are discovery aids, not reproducible artifact references. A `source`
project link does not prove where an existing local file was downloaded.

Paths must be normalized relative paths with no `..`, backslashes, or
Windows-invalid punctuation. IDs must be unique; duplicate paths and
scan directories are rejected case-insensitively for portability.
The initial lock is an observed local inventory, with evidence limits
noted in the file. It does not assert that every existing JAR was matched
against an upstream release.

**Install or upgrade:**

`python -B scripts/install_runtime.py` materialises the lock instead of
leaving each file to a manual download. It treats the lock as the only
source of truth: a present file whose SHA-256 matches is `OK` and skipped;
a present file that differs is `DRIFT` and is not touched without
`--replace`; a missing file with a `download_url` is streamed to a
`.part` file, hashed, and renamed into place only after the hash matches;
one without a URL is `MANUAL` and named with its `source`. `--dry-run`
makes no request and writes nothing, `--only ID` narrows the selection,
and exit codes are **0** = every selected artifact is present and
matching, **1** = something is `MANUAL`, `DRIFT` or failed, **2** = invalid
lock or arguments. It never creates plugin data, edits a config, or
touches `world/`.

1. Choose the exact artifact and record its project/release URL and
   version. Stop the server and run `scripts/backup.cmd` (Windows) or
   `sh scripts/backup.sh` (POSIX); confirm a successful complete backup.
2. Keep the old lock revision and old JARs outside the scanned install
   directories. Put plugin JARs in `server/plugins/`. Put datapack ZIPs
   directly in `server/world/datapacks/`, without extracting them; their
   archive root must contain `pack.mcmeta` and `data/`. Move obsolete
   versions aside rather than leaving two copies installed.
3. Calculate SHA-256 and deliberately edit the relevant lock entry with
   its path, version, source and hash. For example, PowerShell:
   `Get-FileHash -Algorithm SHA256 -LiteralPath 'server/plugins/Geyser-Spigot.jar'`;
   POSIX: `sha256sum server/plugins/Geyser-Spigot.jar`.
4. Run the verifier, resolve any unexpected difference, then start the
   server normally. Commit the reviewed lock change to record the
   installation. No separate compatibility sign-off is required by this
   inventory mechanism.

For removal, stop the server, move the artifact outside its installation
directory, remove its lock entry, and verify again. Follow the component's
own uninstall instructions for any persistent data; this tool only tracks
files.

**Backups and rollback:** backup `MANIFEST.txt` checks the integrity of
that backup; `runtime.lock.json` identifies the intended runtime files.
Before an upgrade, record the old lock commit with the backup (or keep a
copy of that lock beside it). The backup scripts do not do this
automatically. They exclude program JARs, while the whole-world copy
includes datapack ZIPs. Retain old JARs outside Git since upstream may
remove a build. On rollback, restore matching binaries and lock revision;
if an upgrade changed world/config/plugin data, restore the corresponding
backup as well. A Git lock change alone does not roll back the server.

Verifier regression tests use isolated temporary fixtures:

```sh
python -B -m unittest discover -s tests -v
```

`tests/test_frpc_shared_tcp_scene.py` covers the configuration the optional
shared-TCP scene generates (section 10.1); it only runs `--dry-run`, so it
needs POSIX `sh` and nothing else.

### 4.2 NetherNet Bedrock entry points and troubleshooting

Bedrock 26.60 and newer join over NetherNet, not RakNet: the client first
fetches the server's connection details over HTTP signalling, then plays
over WebRTC UDP. UDP 19132 is the data plane only, so it is never the
address a player types in. Geyser also has to advertise an address the
player can reach directly, because signalling hands that address to the
client.

Two signalling arrangements exist:

- `nxs` (default): Geyser registers with an external signalling service
  (`bedrock.signaling.nxs.endpoint`, default
  `https://agent.warden.cloud`). Players join the address that service
  prints at boot, e.g. `Registered with the external signaling service.
  Players can join at https://<name>.wdn.gg`, on port 443. Geyser opens
  no local signalling port in this mode.
- `builtin`: Geyser serves signalling on the Bedrock port over TCP, so
  that TCP port has to be reachable too (port forward, or a second frpc
  TCP proxy beside the UDP one). Plain HTTP works but shows a one-time
  "trust on first use" prompt; HTTPS needs a certificate for a real host
  name, either in Geyser or terminated in front of it by HAProxy. When
  only one public TCP port is available, 10.1 shares it between Java and
  this signalling listener with HAProxy.

`bedrock.signaling.advertise-addresses` holds the public endpoint that
really reaches the NetherNet media listener - the frp entry and the
external UDP port (`"<entry>:<udp-port>"`). It may be written as a numeric
address or as a host name; this deployment uses the host name, and the
address it resolves to is what players get:

- the name is looked up here, when signalling starts, and every address
  it resolves to gets the same usable-address check a literal entry gets:
  a fake-IP resolver (common with proxy/VPN fake-IP modes) answers
  `198.18.0.0/15` and Geyser refuses to start signalling with
  `Advertised address <ip> is special purpose, no player can reach it`;
- `advanced.nxs.connection-checks` (on by default) has the service probe
  the advertised address from several regions, so the resolved value has
  to be the real public endpoint;
- the boot log prints `Advertised address <name> resolves to <ips>`, the
  fastest way to see what was actually advertised.

A name buys nothing a player can use - it never leaves this machine, and
the candidates in the answer are addresses - so it is safe exactly as long
as this machine's resolver keeps returning the node's real public address.

`advanced.bedrock.webrtc-proxy-protocol-relays`, with
`advertise-addresses` naming the public entry players are given, is the
media-plane real-address chain of 10.1.2.

`plugins/Geyser-Spigot/nethernet/` is instance identity, not cache: the
P-384 machine key, the saved registration/challenge and
`operator-link.txt` live there (`provider-state/`, `identity.pem`).

- Changing `advertise-addresses` does not re-register anything; the saved
  identity keeps the same Warden host name. Keep the directory with the
  server's own data: it is in the backup set (section 1), and it is
  sensitive - never commit or share it.
- A directory that is wiped on every restart registers a new service per
  boot (new `*.wdn.gg` name) and leaves orphans behind. Set
  `advanced.nxs.deregister-on-shutdown: true` on container-style hosts.
- If Geyser holds an identity the service can no longer serve, startup
  fails with `Could not register with the external signaling service:
  ... (500 internal_error)` and never self-heals: a saved registration
  makes Geyser take the recovery path, and only a `recovery_unavailable`
  answer makes it discard that state and register fresh. Any other error
  is rethrown on every boot, so changing the advertised address or DNS
  cannot fix it - the recovery request carries no address.
  Fix: stop the server, `mv plugins/Geyser-Spigot/nethernet
  nethernet.bak.<timestamp>`, start again, confirm the
  `Registered with the external signaling service` line, then hand
  players the new address.

Diagnostics: `advanced.bedrock.nethernet-debug: true` for request-level
logs, and `/geyser nethernet status`, `/geyser nethernet diagnostics` or
`/geyser nethernet advertised` from the console.

### 4.3 LoginTo (offline Java accounts)

This backend runs `online-mode=false`, so a Java name by itself proves
nothing. LoginTo gives Java players `/register` and `/login` and keeps one
password row per UUID in `plugins/LoginTo/_pluginData/database.db` (its
`cache.db` beside it only holds the name lookup the fork no longer does;
`rockyou.txt.gz` is the common-password list). Bedrock players are
not part of that flow: Floodgate already identifies them (name prefix `.`,
UUID namespace `00000000-0000-0000-0009-`) and LoginTo auto-registers them
on first join, so they never see a password prompt.

Upstream LoginTo decides whether a name is "premium" by forcing an
encryption handshake and then asking Mojang `hasJoined`. On an offline
backend that handshake is the failure mode: a launcher without a Mojang
session cannot fetch the profile key pair the handshake needs, so it drops
the connection and the player only sees `Failed to log in: Invalid
session`. The build used here is a fork of upstream that drops the
handshake, so every non-Bedrock player is authenticated as cracked, the
way a name-only offline server behaves.

Account rules, which follow from how the offline UUID is derived:

- The account key is the player name, exactly and case-sensitively. The
  UUID is the offline UUID of that name, so `Snorlax` and `snorlax` are two
  accounts, and the same name typed on a second device is the same account
  with the same password.
- A name that Mojang has issued still belongs to that name here, and the
  first player to reach a free name owns it. It is not held back for the
  Mojang account holder, and no name is reserved.
- There is no rename or migration path. A player who changes their name
  gets a fresh empty account and registers again; the old row keeps the old
  name and password.
- `/unregister <player>` (operator only) is the only way to free a name. It
  deletes that account and its password.
- `/premium` and `/cracked` exist only for a Mojang-linked flow, so they
  stay disabled while `settings.premium.enabled: false`. The flag no longer
  gates authentication at all; it only toggles those two commands.

Baseline `plugins/LoginTo/config.yml` on this server:

- `settings.premium.enabled: false`, `settings.premium.auto-register: true`
  (Bedrock players only - see the fork notes above).
- `settings.sessions.enabled: false`. Session reuse is keyed on the
  recorded IP, and both frpc entries in section 10 arrive as `127.0.0.1`
  while the mux relays without PROXY protocol (10.1, the default), so
  sessions would log in every player after the first one. The opt-in
  chain of 10.1.1 gives the backend the player's own address again, so
  with it on that blocker is gone and turning sessions back on is a
  separate decision rather than something this list rules out.
- `settings.password.authentication-timeout: 0`, so a slow typist is not
  kicked while registering. `max-login-attempts` still applies.

## 5. Acceptance checklist (production gate)

- [ ] Boot log version line matches the target MC version (26.2)
- [ ] `Done (..s)` present, no ERROR-level log lines
- [ ] All target plugins `Enabling`
- [ ] Port 25565 listening (`netstat -ano | findstr 25565`)
- [ ] Java client can join the configured entry: TCP `25565` directly only
      while PROXY protocol is off; with `--proxy-protocol`, use the public
      frpc entry or the default LAN Java frontend (10.1.1). A Bedrock
      client joins the NetherNet entry point, not the UDP port: the
      `*.wdn.gg:443` address from the `Registered with the external signaling
      service. Players can join at ...` line, or the built-in signalling TCP
      port (see 4.2). A client pointed at UDP 19132 or at the wrong Java
      entry fails with no server-side connection record
- [ ] `bedrock.signaling.advertise-addresses` names the public entry and
      external UDP port of the NetherNet listener (here: a host name, see
      4.2), and the boot log shows enabled signalling plus the
      registration line above
- [ ] `stop` exits cleanly; second cold start reaches `Done` quickly
      (no migration/patch phase)
- [ ] Data dirs are in the backup set: `world/` + whitelist/ban/usercache,
      plus `plugins/Geyser-Spigot/nethernet/` when Bedrock uses NetherNet
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
- Both wrappers pass `-Dpaper.disableStartupVersionCheck=true`. Paper's
  startup version fetch is asynchronous (`MCUtil.ASYNC_EXECUTOR`), so a
  blocked request or an HTTP 403 such as
  `fill.papermc.io/v3/projects/paper` does not stop the server - but it
  logs ERROR/WARN noise and can hold an async thread while a filtered
  connection times out. `MinecraftServer` reads the property before
  scheduling the fetch, so it disables the check independently of
  `config/paper-global.yml` `update-checker.enabled` (still `true` by
  default). The upstream Paper version feed does not describe this ASP
  fork anyway; keep upgrades on the 4.1 lock process instead.
- Plugin update checks are separate toggles:
  `plugins/ViaVersion/config.yml` and `plugins/GrimAC/config.yml` each
  have `check-for-updates`; `plugins/Geyser-Spigot/config.yml`
  `notify-on-new-bedrock-update` only reports Bedrock support, it is not
  a Geyser self-update. Disabling a check removes only the notification,
  not plugin functionality.
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
- Bedrock players cannot join at all until NetherNet signalling works;
  see 4.2 for the entry points, the advertise-address rule and the stale
  `nethernet/` identity failure.
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
| Geyser | Bedrock bridge; NetherNet signalling + UDP 19132 data plane (see 4.2) | https://github.com/GeyserMC/Geyser | https://geysermc.org/download/ | 2.12.1-b1302 |
| Floodgate | Bedrock accounts joining Java servers | https://github.com/GeyserMC/Floodgate | https://geysermc.org/wiki/floodgate/ | 2.2.5-SNAPSHOT (b141) |
| ViaVersion / ViaBackwards | cross-version protocol bridge | https://github.com/ViaVersion/ViaVersion | https://viaversion.com | 5.12.2-SNAPSHOT |

Deprecated sources (do not cite):
- https://docs.geysermc.org/ (404; current docs live under https://geysermc.org/wiki/)
- https://api.geysermc.org/v1 and https://download.geysermc.org/v1 (Not Found; v2 works)
- GeyserMC repos have no GitHub Releases/tags; artifacts come from download.geysermc.org/v2

## 10. Optional frpc session script (not core)

`scripts/scenes/frpc.sh` is an optional Linux composition script for running
the server console and several `frpc` tunnels in one tmux session. It is not
part of the deployment path and is outside the section 5 acceptance
checklist. The core `start.*`, `backup.*` and runtime verification scripts
neither call nor depend on it; deleting the script leaves them unchanged.

The verbs are `up`, `down`, `status`, `attach` and `help`.
`FRPC_SESSION` overrides the tmux session name (default `asp-frpc`);
letters, digits, `_` and `-` only.
`FRPC` overrides the `frpc` binary (default: first `frpc` on PATH).

It requires `tmux` and an frpc executable. In `--config` mode the executable is
`FRPC` or the first `frpc` on PATH; in `--scene` mode each section's `binary`
is authoritative. The script does not read or copy frp configuration files:
pass each file, or a directory of files, with `--config`. Directory inputs
expand to that directory's immediate non-hidden regular files that are named
like frpc configurations (`.ini`, `.toml`, `.yaml`, `.yml`) in name order;
every other file is reported on stderr as
`note: ignoring <path>` and left alone, so a certificate, a backup or a note
may sit beside the configs. A file named explicitly with `--config` is used
whatever it is called.

`--scene` reads a small operator-owned manifest instead, and is mutually
exclusive with `--config`. It exists for what a `--config` list cannot say:
which binary runs which configuration, and whether the scene owns a server at
all. One section is one frpc process, one configuration and one
`frpc-<section>` window:

```ini
session = asp-frpc
server = false

[udp]
binary = /home/operator/asp-frpcs/bin/frpc
config = /home/operator/asp-frpcs/official-frpc-udp.toml
```

`session` and `server` are required, `server` is exactly `true` or `false`,
and a scene needs at least one section. A relative `binary` or `config`
resolves against the *scene file's* directory, never the caller's; a bare
`binary` is a command name looked up on PATH, while a bare `config` is still a
file next to the scene. Blank lines and whole-line `#` comments are ignored;
inline comments are not, so a `#` inside a value is part of that value. The
parser only reads the file - nothing in a manifest is sourced or evaluated -
and duplicate keys or sections, unknown keys, empty values, control characters
and invalid names all exit 2 before tmux is touched. `FRPC_SESSION` still
overrides `session`, which is how 10.1 aligns the wrapper with the sidecars it
starts.

`server = false` is the sidecar-only form: the first sidecar becomes the
session's initial window, and neither a `server` window nor the deferred
placeholder exists. `down` notices the missing window and kills the session
instead of sending it `stop`. `down`, `status` and `attach` take no scene
file, so a manifest that names a session other than the default needs
`FRPC_SESSION` set for those verbs (`up` prints the hint); a scene that keeps
`session = asp-frpc` needs nothing.

Several TCP entries are several sections even when they point at the same
local port, because they may come from different provider accounts and run
different binaries. Several tunnels that one frpc process owns are several
`[[proxies]]` in one configuration, and so one section.

Each `frpc-<name>` window runs frpc with the directory of *its own*
configuration as the working directory, because frpc resolves the relative
paths inside a configuration (certificates, logs, plugin files) against it.
A relative path in a config therefore means "next to this file", not "next
to the repository". The server window is unaffected: `start.sh` still runs
from the repository root.

```
scripts/scenes/frpc.sh up --config ~/frp --no-attach
scripts/scenes/frpc.sh up --scene ~/asp-frpcs/udp.scene --no-attach
scripts/scenes/frpc.sh status
scripts/scenes/frpc.sh down
```

`up` creates the `asp-frpc` session with a `server` window and one
`frpc-<name>` window per config. It starts every sidecar first and only
respawns the server window after each `frpc` process has stayed alive for
`FRPC_READY_TIMEOUT` seconds (default 5); a sidecar that exits aborts the
start and leaves the session up for inspection. `remain-on-exit` keeps a
failed pane visible; restart with `down` followed by `up`. `down` sends
`stop` to the server console and waits up to `FRPC_STOP_TIMEOUT` seconds
(default 180) before removing the session; a session whose server is still
deferred is killed immediately. `--defer-server` stops after the sidecar
check and leaves the server window as a placeholder, which is what the
shared-TCP scene in 10.1 composes with. A manifest that says
`server = false` creates no server window at all, so its first sidecar is the
session and the scene simply stays up. Use `--dry-run` to print the tmux
commands without starting anything. Three test files cover all of this
without tmux or frpc being installed: `tests/test_frpc_scene_configs.py`
(which files a `--config` directory contributes),
`tests/test_frpc_scene_spawn.py` (what each window is started with, against
a stub tmux that records its arguments) and `tests/test_frpc_scene_manifest.py`
(manifest grammar, path resolution and the server-less lifecycle).

Tracked examples live in `examples/scenes/`: one sidecar-only UDP scene, one
scene with two TCP entries and the UDP process, and a matching frpc config for
each side. They are documentation, not deployment assets - every path,
account field, host name and port is a placeholder, and the configs they name
do not exist in the repository. Copy one outside the repository and keep the
real values there.

### 10.1 Shared TCP entry for Java and Bedrock signalling (Linux only)

`scripts/scenes/frpc-shared-tcp.sh` is a variant of the frpc scene for
hosts where one public TCP port has to carry both Java Minecraft and
Bedrock NetherNet built-in signalling. It is optional in the same way
as `frpc.sh`: `start.*`, `backup.*` and the verifier do not call it, and
deleting the scene scripts leaves them unchanged.

It creates the `asp-frpc-shared` session with a placeholder `server`
window plus one `frpc-<name>` window per config, then adds a `mux`
window running HAProxy as an L4 demultiplexer in front of two local
listeners, and only then starts the server in its window. The order is
deliberate: sidecars first (`frpc.sh --defer-server`), HAProxy second
(the window must stay alive and bind the listen port within
`MUX_READY_TIMEOUT` seconds, default 10), server last. A sidecar or mux
that fails leaves the other prerequisites untouched and the server
unstarted. The sidecar windows inherit the working directory rule of 10:
each frpc runs in the directory of its own configuration, while HAProxy and
the server run from the repository root.

`up` takes `--scene FILE` as well as `--config`, mutually exclusive, and
hands the sidecar set to `frpc.sh` unchanged. That is the arrangement for
several TCP entries from different provider accounts plus the UDP media
tunnel: the manifest names one binary per section, and the wrapper still
defers the server and starts it after the mux, so a manifest that says
`server = false` composes with it exactly like one that says `true`.

Its verbs are `up`, `reload`, `down`, `status`, `attach` and `help`. The mux
runs HAProxy in master-worker mode (`-W -db`) with a pidfile
(`.tmp/frpc-shared-tcp/haproxy.pid`; `MUX_PIDFILE` overrides it), and
`reload` is what that arrangement is for: it sends `SIGUSR2` to the master,
which re-reads the configuration and hands the listening socket to a new
worker, so the port never drops and the players on it are not disconnected.
Respawning the mux window would do the opposite, which is why the reload is
a signal and not a restart.

That master is also why the mux has a lifetime of its own. It ignores the
`SIGHUP` that destroying its tmux session sends it - its reload signal is
`SIGUSR2` and its stop signal is `SIGTERM` - so `down` cannot leave it to
tmux: it would keep the listen port with no window left to show it. `down`
stops the master named by the pidfile itself (`SIGTERM`, then `SIGKILL`
after `MUX_STOP_TIMEOUT` seconds, default 10) and only then drops the
pidfile with the session. `up` refuses to start when the pidfile already
names a live master, or when something already listens on the mux port, so
the failure is one line about the process that is in the way instead of an
`Address already in use` pane seen after the frpc sidecars have come up
(exit 3, as for a session that already exists).
`status` reports the mux from the pidfile rather than from the session,
which is what makes a master that outlived its session visible; a manual
recovery from one whose pidfile was lost is
`kill -TERM "$(pgrep -x haproxy)"`.

`reload`, `down`, `up` and `status` all read that pidfile, check that the
process it names is HAProxy rather than trusting the file, and refuse
anything else: a stale pidfile plus a recycled pid would otherwise aim a
signal at an unrelated process. `down` still removes a pidfile it refuses
to act on, because dropping it is what lets the next `up` proceed, but it
exits non-zero then: a mux was not stopped. Since the check compares the
running process name with the name of the `HAPROXY` binary, `reload` and
`down` have to see the same `HAPROXY` value the mux was started with.

`status` also prints the TLS binds of the configuration the mux reads, as
that configuration writes them. That line is where "which certificate is
being served" is actually answered, and its silence is the failure it
breaks: reloading after writing a PEM the configuration does not mention
re-reads the old certificate and reports success, which looks exactly like a
renewal that worked. `MUX_HAPROXY_CONFIG` says which file to read, so a
status call can follow an `up --haproxy-config`; without it, the scene's own
generated configuration is the one reported.

Certificate expiry is observed, not managed, by this scene. `up` prints
each `--tls-cert` file's subject, SANs, `notAfter`, and remaining days when
`openssl` can parse it. It warns when expiry is inside
`MUX_CERT_WARN_DAYS` (default 7, the same window in which the provider
accepts renewal), but an expired or nearly expired PEM
does not stop HAProxy by default: validation still fails only for a missing
file, missing key, or unusable configuration. `up` records the resolved
paths in `MUX_CERT_STATE` (default `.tmp/frpc-shared-tcp/certs`) after the
mux is confirmed listening; `status` reports that inventory, and `down`
removes it. Failing to write the inventory is a warning, not a reason to
stop a working mux. A hand-written
`--haproxy-config` remains untracked because the scene does not parse its
quoting; `status` says so instead of guessing.

Downloading, renewing, and scheduling the certificate stay outside this
scene (10.2). After a PEM is replaced, `reload` is still the explicit step
that makes HAProxy read it; the scene neither watches files nor reloads on
its own.

| Local endpoint | Role |
| --- | --- |
| `127.0.0.1:25566` (mux, default) | public TCP entry, demultiplexed |
| `127.0.0.1:25565` | Java server (default backend) |
| `127.0.0.1:19132` | Geyser NetherNet TCP signalling |
| `127.0.0.1:25567` (TLS, default) | TLS termination for the ClientHello, only with `--tls-cert` |
| `0.0.0.0:25564` (LAN, default with PROXY) | plain Java entry that injects PROXY v2 when `--proxy-protocol` is used |
| `127.0.0.1:8000` (opt-in) | resource-pack HTTP server, reached only through `--packs`/`--serve-packs` (10.1.3) |

Classification: a TLS ClientHello (`req.ssl_hello_type 1`) or an HTTP
method / HTTP/2 preface goes to Geyser; a Java legacy ping (`0xFE`) or a
handshake packet (`0x00` at offset 1) goes to Java; anything still
unclassified after `inspect-delay 3s` falls through to Java.

With `--packs`, a plaintext `GET <prefix>` is decided before that: it is an
HTTP method too, so the packs rule has to come first (10.1.3).

Without `--tls-cert` the mux is a transparent byte pipe: the ClientHello
is forwarded untouched, so a certificate has to live in Geyser
(`bedrock.signaling.builtin.https.*`). With `--tls-cert FILE` the scene
terminates TLS instead: the ClientHello is handed to a second loopback
bind (`--tls-listen`, default `127.0.0.1:25567`) that decrypts it and
passes the plain bytes to the same signalling backend. Geyser then keeps
its plain HTTP listener (`signaling.mode: builtin`, no certificate
configured), and plain HTTP arriving on the shared port still goes
straight to Geyser. Geyser can answer such a plaintext client with
`426 Upgrade Required` (`Upgrade: TLS/1.2`) so that TLS starts on the
same connection, and an in-place upgrade like that happens inside the
connection the mux already classified - it cannot be redirected to the
terminating bind. Give players the host name, never the raw IP, so the
client starts with TLS.

`--tls-cert` may be given more than once, one file per name: every file
becomes its own `crt` on that bind, in the order given, and HAProxy chooses
between them by the SNI the ClientHello carries. That is what serving
several names on one port needs - several accounts, each with the
certificate its own provider issued (10.2) - and it is why the tunnels of
two accounts can share this mux while each one's players still get the
right certificate. A ClientHello no certificate covers is served the first
one, so a name added later has to bring its certificate with it;
`--strict-sni` refuses such a handshake instead, which turns a wrong
certificate into a visible failure rather than a mobile client's confusing
complaint. Java carries no SNI at all, so none of this changes how Java is
routed. The cost is that every private key on that bind is held by the one
HAProxy process, which is what SNI selection is.

Each `--tls-cert` takes one combined PEM, because that is what one HAProxy
`bind ... ssl crt` line reads, and they live outside the repository next
to the frpc configs. One file per fully qualified name, never a bare
subdomain: `~/asp-frpcs/tls/` is a shared directory, and with more than one
account in it `1-mc.pem` no longer says whose `1-mc` it is. Name it for the
name the certificate covers, so the file and the certificate identify each
other:

```sh
mkdir -p ~/asp-frpcs/tls
cat fullchain.pem privkey.pem > ~/asp-frpcs/tls/<fqdn>.pem
sh scripts/scenes/frpc-shared-tcp.sh up --config ~/asp-frpcs \
    --tls-cert ~/asp-frpcs/tls/<fqdn>.pem --no-attach
```

Two accounts are then two files on one bind - and two sync runs, because
one token answers for its own account only:

```sh
sh scripts/scenes/frpc-shared-tcp.sh up --config ~/asp-frpcs --no-attach \
    --tls-cert ~/asp-frpcs/tls/<sub>.<account>.nyat.app.pem \
    --tls-cert ~/asp-frpcs/tls/<sub>.<other-account>.nyat.app.pem \
    --strict-sni
```

Repeating `--tls-cert` is not a way to route by account: the mux sees only
the bytes on its own loopback port, and nothing in them says which tunnel a
connection arrived through. Two accounts that have to reach two servers
need one mux per local port, or PROXY protocol pointed at one backend
only (10.1.1).

`fullchain.pem` / `privkey.pem` are the issuer's file names, not something
the scene produces: the PEM has to come from a certificate authority for a
name you control. A tunneled port cannot answer HTTP-01 (the node owns the
port and it carries Java as well), so issue over DNS-01:

```sh
acme.sh --issue --dns dns_<provider> -d <fqdn> --keylength ec-256
cat <fullchain.cer> <fqdn>.key > ~/asp-frpcs/tls/<fqdn>.pem
```

A name bound to the provider is the exception to that route: its DNS belongs
to the provider, so no challenge can be answered for it and the certificate
comes from the provider's own API instead (10.2).

Two provider-side prerequisites come with that. The name has to reach the
node the tunnel lands on (an A record to the node IP, or a CNAME to the
node's domain), and the node has to accept that name for this tunnel -
NATFRP binds a domain to a tunnel and verifies the binding first. Without a
domain, keep signalling on the external service (`nxs`, or `hybrid` to
serve both) and hand players the `*.wdn.gg:443` address; players then need
the address that service printed, not this port.

The certificate is not core content and never enters Git: it belongs with
the frpc configuration outside the repository, which is also outside
section 1's backup classes and section 5's acceptance checklist. The
scene refuses a file that holds no certificate or no private key, refuses
`--tls-cert` together with `--haproxy-config` (which owns the whole
configuration), and refuses a `--tls-listen` that collides with
`--listen`, `--java` or `--bedrock`. None of this needs anything special
from frpc: keep `type = "tcp"` and leave NATFRP's `auto_https` off, since
frpc terminating TLS would reverse-proxy the whole stream and Java cannot
speak that. `transport.tls.enable` only wraps the frpc-to-frps transport
and is unrelated. It may sit in the same directory as the configs, or a
subdirectory of it: a `--config` directory only takes `.ini`, `.toml`,
`.yaml` and `.yml`, and reports anything else it skipped. The scene
resolves `--tls-cert` to an absolute path before HAProxy reads it, so that
path does not depend on the working directory.

Two things HAProxy cannot fix. An frps node that whitelists SNI or Host
against domains bound to the tunnel rejects an unknown name before the
bytes reach this machine, so the host name still has to be set up on the
provider side (the datacenter's "domain not whitelisted" interception page
is that check, not a fault in the mux). And the client has to type the
host name the certificate covers - a raw public IP cannot have a public
certificate, so the mobile clients that refuse plain HTTP still fail
against one.

Prerequisites: `tmux`, `haproxy`, and an frpc executable. `HAPROXY` overrides
the mux binary; `FRPC` overrides the frpc binary in `--config` mode; a
`--scene` section's `binary` is used instead of `FRPC`. Every executable is
resolved to an absolute path because the tmux server does not have to share
the caller's PATH. Run it from the repository root:

```
sh scripts/scenes/frpc-shared-tcp.sh up --config ~/asp-frpcs --no-attach
sh scripts/scenes/frpc-shared-tcp.sh status
sh scripts/scenes/frpc-shared-tcp.sh down
```

The frpc side needs two tunnels for one public address, and they are two
processes: the TCP entry runs under the provider's fork because it needs that
provider's `auto_https` and certificate, and the UDP media plane runs under
the official frpc client because only that client was verified to forward UDP
PROXY protocol v2 (10.1.2). One scene section each:

```ini
# TCP entry, provider fork: Java + Bedrock built-in signalling -> HAProxy mux
[common]
user = 10000                # replace with the provider account id
server_addr = frp.example.net
server_port = 8088

[minecraft_tcp]
type = tcp
local_ip = 127.0.0.1
local_port = 25566          # the mux, never the Java server
remote_port = 24000         # replace with the provider-assigned port
```

```toml
# UDP media plane, official frpc: -> Geyser (not behind HAProxy; see 10.1.2)
[[proxies]]
name = "minecraft_bedrock_media"
type = "udp"
localIP = "127.0.0.1"
localPort = 19132
remotePort = 24001          # replace with the provider-assigned UDP port
transport.proxyProtocolVersion = "v2"
```

The two live in different configs, so they are two `--scene` sections with
different `binary` values; a single config with both `[[proxies]]` is only
possible when one binary serves both, which is not the case here (and the
provider fork above uses its INI schema, not the official client's TOML
schema). Working examples are in `examples/scenes/`.

With that mapping Java is joined at `<public-ip>:<tcp-port>` and the Bedrock
entry point is the same `<public-ip>:<tcp-port>`; the media plane is reached
through `bedrock.signaling.advertise-addresses`, which names the public
entry and the UDP remote port (`"<entry>:<udp-port>"`, see 4.2).

`bedrock.signaling.mode` decides what the Geyser backend serves:
`builtin` binds the TCP signalling listener that HAProxy forwards to and
does not register with the external service (no `*.wdn.gg` name);
`hybrid` serves that listener and still registers with the external
service, so the `*.wdn.gg:443` address stays available as a fallback.
`nxs` (the default) leaves the `geyser_signaling` backend with nothing
to talk to. Signalling is only HTTPS when the certificate presented to
the player is valid for the name the player typed, whichever side
terminates TLS - Geyser (`bedrock.signaling.builtin.https.*`) without
`--tls-cert`, HAProxy with it.

Two deliberate limits. By default HAProxy relays without speaking PROXY
protocol, so with no `--proxy-protocol` leave frpc's
`transport.proxyProtocolVersion` unset and do not configure the backends
to expect it. And it shares TCP only; the WebRTC media plane is UDP and
still needs its own frpc proxy.

`--dry-run` prints the HAProxy configuration and the tmux commands
without starting tmux, frpc or HAProxy. `--listen`, `--java` and
`--bedrock` override the three local endpoints; `--tls-cert` and
`--tls-listen` switch on the terminating variant described above, and
`--proxy-protocol` the real-address variant of 10.1.1.
`--haproxy-config FILE` substitutes a hand-written configuration, which is
checked with `haproxy -c -f` before anything starts and is never
rewritten. Without it the scene creates `.tmp/frpc-shared-tcp/` as needed
and atomically rewrites `.tmp/frpc-shared-tcp/haproxy.cfg` (gitignored) on
every `up`. `up` refuses to run while `asp-frpc-shared` already exists;
use `down` first.

Everything above can be checked on the host without touching NATFRP,
tmux or frpc:

```sh
python3 tests/smoke_frpc_shared_tcp_tls.py
```

This needs `sh`, `haproxy` and `openssl`. It generates a throwaway
certificate, starts two loopback backends, builds the HAProxy
configuration through the scene's own `--dry-run`, validates it with
`haproxy -c -f`, and then checks on the real proxy that the certificate is
presented, that a TLS ClientHello on the shared port reaches the
signalling backend, that plain HTTP on the shared port still reaches it,
and that Java bytes reach the Java backend. It exits 0 only when all four
checks pass. What it cannot cover is the path beyond this machine: the
frps tunnel, an frps node's SNI/Host whitelist and a real Bedrock client.

The path beyond this machine needs no certificate to check either, but it
does need the whole chain up (frpc, the mux and the server), otherwise a
`NO DATA` line cannot be attributed to a layer. `--local-mux` adds the
local half as a control:

```sh
python3 scripts/probe_public_entry.py --host <node> --port <remote-port> \
    --local-mux 127.0.0.1:25566
```

It opens the public port with a Minecraft legacy ping, a plain HTTP GET and
a TLS handshake carrying the SNI followed by the same HTTP request inside
it, and reports for each whether the server, an interception page or
nothing answered; the certificate is judged in a separate step, so "the
path is broken", "nothing answers inside TLS" and "the certificate is
untrusted" cannot be mistaken for each other. It refuses to overstate a result when
the host resolves into `198.18.0.0/15`, the fake-IP range a proxy resolver
hands out: that answer describes the resolver, not the node. A Java answer
is the proof that the tunnel carries the port end to end. In the control
block a `NO DATA` on the local `http` line is expected while
`bedrock.signaling.mode` is `nxs`, because nothing serves that backend in
that mode. An HTML page
from an IDC (the page carries `0632idc.com` and `sorry.png`) is a
datacenter domain-whitelist interception, and no certificate, trusted or
self-signed, lifts it - signalling has to move to the external service
instead, which is what `hybrid` exists for.

The probe lives in `scripts/` rather than `tests/` on purpose: what it
measures is the node and the datacenter in front of it, which no local
fixture can stand in for, so it is an operator diagnostic and not part of
the regression suite. Its judgement - a datacenter page versus a server
answer, a `198.18.0.0/15` address as a resolver artefact, the exit codes -
does not need a live node and is covered against loopback fakes by
`tests/test_probe_public_entry.py`.

One topology the mux cannot decide by itself: NATFRP's `auto_https` terminates
TLS in frpc, not in the node and not in the datacenter in front of it. frpc
accepts the TLS connection, removes the TLS layer and hands the bytes inside
it to the local service; the mode decides how. The default probes the local
service at startup and picks a mode, `http` is an HTTP reverse proxy that
adds `X-Forwarded-For`, `https` reverses to an HTTPS local service, and
`passthrough` forwards the bytes inside TLS untouched - which is for a
non-HTTP protocol whose client wraps it in TLS itself, not for a client that
speaks no TLS at all. A Java client speaks no TLS, so on an `auto_https` port
Java never completes a handshake and is gone before the mux sees a byte. The
provider's documentation puts game traffic under what must not use the
feature, and its NetherNet recipe turns it on for the signalling tunnel only
(`localPort` at Geyser's 19132, mode `http`, the panel's reverse-proxy-to-HTTP
option) while the UDP media tunnel stays without it. Certificate
provenance follows the same setting: `auto` self-signs unless a subdomain
binding exists, in which case frpc loads that domain's certificate from the
server, and a comma-separated domain list makes frpc read `<domain>.crt` and
`<domain>.key` from its working directory - the per-config working directory
in 10 is what puts those files next to the configuration. For a bound name
like `<sub>.<account>.nyat.app` that loaded certificate is also the only
practical one, because the name's DNS belongs to the provider and DNS-01
cannot be run for it.

The tunnel is a byte stream in every one of these arrangements: `type = "tcp"`
relays at the transport layer on both hops, and `auto_https` only moves a TLS
session into the frpc process. That is what makes `http` and `https` modes
application-layer reverse proxying - they are why frpc can add
`X-Forwarded-For`, rewrite `Host` or answer with its own error page - while
`passthrough` strips the TLS layer and keeps no application-layer semantics.
The mux is the other kind of element: `mode tcp` with ACLs over the first
packets, so a ClientHello, an HTTP method prefix and a Java handshake are
classified at the transport layer and no application protocol is parsed.
A Java client has no TLS layer for anything to strip, which is the whole
reason it cannot share a port with a TLS-terminating frpc.

A shared port therefore has to be one of two things. With `auto_https` on,
the mux sees plain HTTP, the `is_http` branch is the signalling path and
`--tls-cert` is redundant - but Java on that port is dead and needs its own
tunnel and remote port. With `auto_https` off, the ClientHello reaches
`is_tls` and either `--tls-cert` terminates it here or Geyser holds the
certificate itself, and that certificate has to be for a name you control,
which a provider-bound name is not. Measure which arrangement you have with
the probe instead of assuming it.

Keeping `auto_https` on for the provider's certificate and pointing the tunnel
at the mux anyway is possible - `passthrough` only changes the shape of what
comes out of the TLS layer, it does not move the termination - but it buys
nothing. The ClientHello is gone by the time the mux sees the connection,
`is_tls` never matches, `--tls-cert` becomes dead configuration, and Java is
excluded exactly as above, so the mux is left serving one branch that a plain
TCP tunnel to 19132 would serve without it. The extra process is worth its
place only in the second arrangement, the one that owns the certificate.

To separate "the provider and the tunnel carry this port" from "the server
answers on it", the same port can be served by a throwaway website instead:

```sh
tmux new -d -s plain-frpc 'frpc -c ~/asp-frpcs/frpc.toml'   # tunnel only
python3 scripts/plain_website_check.py --host <name> --port <remote-port>
tmux kill-session -t plain-frpc
```

That check starts a throwaway directory plus a very ordinary HTTP reverse
proxy configuration on the port the tunnel forwards to (`--listen`,
default `127.0.0.1:25566`), proves locally that the proxy and the site
work, and then asks the public name for the same random page - over plain
HTTP, over TLS, and once more with certificate verification. A page that
arrives through the public name with no Geyser, no Paper and no mux in the
path means anything still broken is in the server; a page that never
arrives means the server was never in question. It refuses to start while
the scene holds the listen port, and its judgement is covered by
`tests/test_plain_website_check.py`, which runs the whole check against a
stand-in proxy and a stand-in tunnel instead of haproxy and frpc.

#### 10.1.1 Real client addresses (opt-in PROXY protocol v2)

Java players reach Paper as `127.0.0.1`, so every offline account shares
one IP: sessions, bans and LoginTo's recorded address cannot tell two
players apart, and the login line prints the loopback address. That
suits this deployment until something needs the real address, and then
it is a four-part switch. `--proxy-protocol` makes the generated
configuration accept a PROXY protocol v2 header on the shared port
(`bind ... accept-proxy`) and give the Java backend one of its own
(`server paper ... send-proxy-v2`, the IP frpc named). Every other
generated line is untouched, so plain mode's output does not move.

*Only the scene's own generated configuration carries the two
directives: `--haproxy-config` takes over the whole file, so add them
there by hand.*

All four have to be set in one move, because the tunnel is unusable
while they disagree - a plain service behind a mux that demands a
header, or a service that demands one behind a mux that sends none, both
refuse every connection:

| Where | Setting |
| --- | --- |
| frpc, per tunnel | `transport.proxyProtocolVersion = "v2"` in that `[[proxies]]` block; the provider's launcher writes the same thing from its `proxy_protocol_version = v2` custom setting |
| the scene | `sh scripts/scenes/frpc-shared-tcp.sh up ... --proxy-protocol` |
| Paper | `config/paper-global.yml`: `proxies.proxy-protocol: true` |
| Geyser | `plugins/Geyser-Spigot/config.yml`: `advanced.java.use-haproxy-protocol: true` |

The port then only accepts a header, so anything that reaches it without
one is refused - which is what makes frpc's half mandatory, and what
breaks a local `curl` or a raw client aimed at the mux. The two local
tools know it: `scripts/probe_public_entry.py --proxy-protocol` prefixes
its `--local-mux` connections with a header (the public half is real
traffic, where frpc adds it), and the smoke test runs its checks both
plain and with headers, including that a headerless connection is
refused.

On the backend side, Paper's `proxies.proxy-protocol: true` applies to
its whole Java listener, so Geyser's own connection to it has to carry a
header too: that is `advanced.java.use-haproxy-protocol: true`.
Bedrock's built-in signalling is not forced: the mux's `server geyser ...`
line carries no `send-proxy-v2`, and Geyser's NetherNet listeners still
take a connection without one. `server.properties` already has
`prevent-proxy-connections=false` and `log-ips=true` on both hosts.

This also means that a listening `25565` socket is not a LAN entry while
PROXY protocol is on: a vanilla LAN client reaches Paper directly, without
the header, and is refused. A LAN client has to arrive through a frontend
that accepts the plain connection and adds `send-proxy-v2` to the Java
backend (or through the public frpc entry); alternatively turn the whole
four-part switch off and use `25565` directly.

The scene generates that LAN frontend automatically whenever
`--proxy-protocol` is used:

```sh
sh scripts/scenes/frpc-shared-tcp.sh up \
  --scene ~/asp-frpcs/minecraft.scene \
  --proxy-protocol --serve-packs --no-attach
```

It adds a plain `frontend lan_java` bound to `0.0.0.0:25564` by default.
That frontend accepts a normal Java client and routes it to the same
`backend java` as the public mux, so HAProxy still supplies the PROXY v2
header and Paper keeps the LAN client's address. `MUX_LAN_JAVA=HOST:PORT`
overrides the bind. The default binds every interface; choose an explicit
LAN address or firewall the port if that exposure is not wanted. A
hand-written `--haproxy-config` still owns the whole file, so add the
frontend there if that mode is used.

Acceptance, on the host: a boot/login line `<name>[/<real-public-ip>:
<port>] logged in with entity id ...` where the address is the player's,
not `127.0.0.1`. Roll back by dropping `--proxy-protocol` from the scene
and turning both `proxies.proxy-protocol` and
`advanced.java.use-haproxy-protocol` back to `false`; the generated file
then matches the plain output byte-for-byte.

#### 10.1.2 Bedrock media: forcing the relay (real client addresses)

The address a player types is their choice: this deployment hands out the
frp entry and nothing else, so a Bedrock client's media belongs on the
relay too. The WebRTC path, though, is picked by ICE, and a client on the
server's own LAN finds a direct candidate and takes it - a path nobody
asked for. `advanced.bedrock.webrtc-proxy-protocol-relays` is what closes
it. It is the media-plane counterpart of 10.1.1: that chain carries a Java
player's address through the shared TCP port, this one carries a Bedrock
player's address through the UDP tunnel, and neither needs the other.

Three settings, in one move, because the media port is unusable while they
disagree:

| Where | Setting |
| --- | --- |
| frpc, the UDP tunnel in front of the media port | `proxy_protocol_version = v2` in that tunnel block (the INI form; a TOML config spells it `transport.proxyProtocolVersion = "v2"`) |
| Geyser | `bedrock.signaling.advertise-addresses` names the relay: the frp entry and the media port; a host name is fine here, since Geyser resolves it when signalling starts |
| Geyser | `advanced.bedrock.webrtc-proxy-protocol-relays: ["127.0.0.1"]` - the sender as this machine sees it, not the public node; addresses, subnets or a link to a plain-text list |
| Geyser (already so) | `bedrock.webrtc-port: 0` puts the media port on `bedrock.port` (19132), which is the fixed ICE port the relay code requires |

Once the relay is listed the SDP answer names only the relays, so every
Bedrock client is steered through them - including one on the server's own
LAN, which is the point and also the cost. The media port then stops
accepting a headerless connection, and TURN servers cannot work behind
these relays, so nothing but the relay reaches the media plane.

The UDP tunnel needs v2 - v1 is not an option - and the client has to put
that header *in front of a datagram*, which the provider fork does not do
for UDP. The official frpc client does: `0.72.0` was verified against a live
tunnel, where a plain 19-byte UDP payload arrived as one datagram of the 28
byte PROXY v2 header plus that payload, with the request-side address in it.
On the local side the header and the payload may arrive as two datagrams;
both shapes are the same tunnel. That is why the media plane runs under its
own official-frpc process while the TCP entries keep the fork for
`auto_https` and certificates - the manifest of 10.1 names a binary per
section precisely so one scene can hold both.

What the operator then sees: the address Paper logs for a Bedrock player
becomes the address the relay saw. For a client on the server's own LAN
that is the household's public address, because its traffic leaves through
the same router. The port stays `0` - Geyser itself builds the Java-side
address as `<host>:0` (`LocalSession`) - so `[/<public-address>:0]` is the
expected shape and not a fault.

Acceptance, on the host: the same Bedrock client that logs
`<name>[/<its-own-LAN-address>:0]` today (the observed case) now logs the
household's public address in that field and still reaches the world.
Roll back by removing the relay from `webrtc-proxy-protocol-relays` and
clearing `proxy_protocol_version` on the UDP tunnel; the direct path
returns for everyone.

Two addresses answer two different questions. `advertise-addresses` is
what a player is told to reach, so it is the public entry and may be a
host name. `webrtc-proxy-protocol-relays` is who may claim to be the
sender on the media port, so it is that sender as this machine sees it -
with frpc forwarding to `127.0.0.1:19132` it is `127.0.0.1`, and the
node's public address would never match. It is also the one field that
stays numeric: addresses, subnets or a link to a plain-text list are the
documented forms, so a host name is not one of them. For the entry-point
settings themselves, including the signalling modes, see 4.2.

`advanced.bedrock.prefer-signaling-proxy-address` is a different lever: it
moves the signalling-side address only, and is not part of this chain.

`scripts/probe_public_udp.py` answers the narrow question without any
Minecraft traffic at all: run `listen --bind 127.0.0.1:19132` on the host that
owns the frpc process, `send --host <node> --port <udp-port>` one datagram
from another machine, and it prints whether a PROXY v2 header arrived, the
request-side address it carried, and the payload behind it. It needs no
server, no Geyser and no scene, and nothing starts it for you - it is an
operator diagnostic. It cannot say whether Geyser accepts the header or which
ICE path a real client picked; those still need a Bedrock client and the
Geyser log lines above.

#### 10.1.3 Resource packs on the shared port (opt-in, plaintext or TLS)

`--packs HOST:PORT` adds one more destination to the shared port: a
connection whose first bytes are `GET <prefix>` is handed to that local HTTP
server instead of Geyser, so clients fetch
`<public-ip>:<port>/packs/<file>` from the entry they already know. Without
`--tls-cert` the branch is plaintext from the client's first byte, which is
why it needs no certificate, no bound name and no TLS work: the request
already has the form the mux can read. The ACL sits ahead of the Geyser line
because the same `GET` also matches `is_http`. With `--tls-cert` the route
cannot be read at all from the first byte - that is a ClientHello - so the
same ACL and backend ride the TLS-terminating frontend
(`geyser_tls_termination`) ahead of `default_backend geyser_signaling`,
deciding the decrypted request line there instead. That frontend repeats
the content-wait pair with an `is_http` ACL of its own:
`tcp-request inspect-delay 3s` and
`tcp-request content accept if is_http`. In `mode tcp` the switching rules
otherwise run at the accept event, before the decrypted bytes exist, so
`is_packs` is never true and every request falls to Geyser - which answers
`404` with `content-length: 0`. That is the failure mode to look for if the
pair is dropped while moving the rule between frontends.

The match is exactly `payload(0,<len>) -m beg "GET <prefix>"`, where
`<len>` is the length of `GET ` plus the prefix: offset 0 of a fresh
connection, which is where a resource-pack download starts. A second
request on a kept-alive connection, an h2c preface, or an upgraded stream
does not start there and falls through to Geyser, which answers its usual
404/426. PackManagerPro opens a new connection per download, so that is not
on the supported path.

`MUX_PACKS_PREFIX` sets the prefix, `/packs/` by default. It has to be one
literal path segment - leading and trailing `/`, only `A-Za-z0-9._~/-`, no
`//` and no `..` - and `/` is refused because it would swallow every
plaintext request. The backend stays in `mode tcp` like the rest of the
mux: HAProxy reads the bytes for the ACL and forwards the connection
unchanged. Only `--packs` takes it: that form declares a backend this scene
does not own, so the operator is also the one who has to state the prefix
that backend serves.

`--serve-packs` declares that the backend is this entry's own and removes
that second statement. The endpoint is `127.0.0.1:8000` (`--packs-port`
moves the port), the prefix is the served directory's name - `server/packs`
is `/packs/` - and the entry starts `scripts/serve-packs.sh` in a `packs`
window with exactly those two values on its command line. Nothing in that
mode reads `PACK_PORT` or `MUX_PACKS_PREFIX` to get them: a value with one writer and
two readers cannot disagree with itself, but two independent readers of a
host-level environment variable can, and the failure looks like a working
mux plus a 503.

Either form serves `server/packs/`, because the mux forwards the request path
unchanged; without the mapping the backend would look for
`server/packs/packs/<file>`. Point PackManagerPro at the public address:

```yaml
pack-url: https://<public-ip>:<port>/packs/pack-a.zip
```

The production form uses `--tls-cert` and `https://`: the frp entry serves
no plaintext http, so a pack URL that a remote client follows across the
network must be TLS. The backend is still plain loopback - HAProxy
terminates the certificate - and Minecraft verifies the pack against the
SHA-1 in the pack metadata, so a modified file is rejected by the client.
Without `--tls-cert` the route is plaintext and the form is `http://`, for
hosts whose entry allows it.

The scene refuses both forms with a malformed endpoint, a port already used
by `--listen`, `--java`, `--bedrock`, `--tls-listen` or `MUX_LAN_JAVA`, a
malformed prefix, or a hand-written `--haproxy-config` (that file owns the
whole configuration). With `--packs` it warns, without failing, when nothing
listens on that endpoint yet: the process is not this entry's to check. With
`--serve-packs` the same silence is a failed start, because the entry started
that process. While the backend is down, only `<prefix>*` answers 503; Java
and Bedrock are unaffected.

`reload` only re-reads the file already on disk; it does not regenerate it.
So rollback is `down` and then `up` without `--packs`: `up` is what rewrites
the generated file, and it refuses while the mux is live. The other route is
to edit `.tmp/frpc-shared-tcp/haproxy.cfg` by hand and `reload` - the next
`up` overwrites that edit.

The matcher reads a request line in HTTP/1.1 origin form. A JVM configured
with an HTTP proxy sends an absolute-form line (`GET http://...`) and falls
through to Geyser, as do keep-alive reuse, h2c, and HTTPS.

### 10.2 Keeping the certificate for the shared port current (Linux only)

The `--tls-cert` file of 10.1 is the one input of that arrangement no ACME
client can produce: the name is bound to a NATFRP tunnel and its DNS belongs
to the provider, so no DNS-01 challenge can be answered for it. The provider
issues the certificate itself and hands the pair to the account holder
through its API, and its documentation asks for the written files to be
updated when the certificate is renewed, so taking it from the API is the
documented arrangement rather than a workaround.

`scripts/sync_natfrp_cert.py` does that and nothing else: standard library
only, one run per invocation, no daemon. It is not core content in the sense
of 10 - `start.*`, `backup.*` and the verifier do not call it - and the PEM
it writes holds a private key, so it lives with the frpc configuration
outside the repository, outside section 1's backup classes and section 5's
acceptance checklist.

```sh
NATFRP_TOKEN=... python3 scripts/sync_natfrp_cert.py \
    --domain <sub>.<account>.nyat.app \
    --out ~/asp-frpcs/tls/<sub>.<account>.nyat.app.pem \
    --reload-command 'sh scripts/scenes/frpc-shared-tcp.sh reload'
```

`--out` names one file and nothing negotiates it: the only rule is that the
scene's `--tls-cert` has to point at that same path. Name it for the fully
qualified name (10.1) - the script notes it when the name is a bare
subdomain, because with several accounts in one directory that is where a
certificate and a tunnel get paired wrongly.

The API key is an account credential and never a command line argument
(every process on the host can read those), so the script takes it from
`NATFRP_TOKEN` or from a file named by `--token-file`.

One thing that looks like a bad key and is not: the provider's edge answers
HTTP 403 with the body `error code: 1010` to client signatures it dislikes -
Python's `urllib` default among them - before the request reaches the API.
The script therefore names its own `User-Agent`, and the two answers are
told apart by the body: the API answers JSON carrying a `code` and a `msg`
(a rejected key is HTTP 500 with code 401), while the edge answers one short
line of text. What the edge holds is a list of banned signatures rather than
a browsers-only rule - `curl`, `python-requests` and a made-up name all get
through - so the honest name is enough, and a browser's would be an
impersonation that also chases the browser's version numbers.

One run does this, in order:

1. `GET /domain/get` for the account's domain records and certificate
   state. A `--domain` that is not one of that account's records is refused
   before anything else, because the API answers for the account and not for
   the name: a key and a name from different accounts would otherwise be
   paired silently.
2. When the certificate expires inside `--renew-window-days` (default 7),
   ask for a renewal (`POST /domain/cert`) and poll until the account holds
   a certificate that is not the old one. The API accepts a renewal request
   only inside that window, and it keeps the old certificate until the new
   one is issued.
3. Download the pair (`GET /domain/cert`) - but only when the file does not
   already hold this certificate, because the API asks callers not to
   download it repeatedly. A `.created` sidecar next to the PEM records
   which certificate the file holds.
4. Prove the certificate and the key belong together
   (`ssl.load_cert_chain`, the check HAProxy would otherwise make much later
   and much less visibly) and, when openssl is installed, that the leaf
   covers `--domain`.
5. Write the chain and the key into one combined PEM, the form a single
   `bind ... ssl crt` line reads, through a temporary file and a rename, so
   a reader never sees half a file, and with no group or other access,
   because the file holds a private key and the umask must not decide that.
6. Run `--reload-command`, and only when the file changed.

The sync script owns renewal; the shared scene owns the read-only check.
After a run, `frpc-shared-tcp.sh status` shows the loaded certificate's
subject, SANs, and expiry from its `MUX_CERT_STATE` inventory, so a file
that was written but not reloaded, or one that is still near expiry, is
visible without opening the provider API.

The reload command is the one in the example, because the scene already owns
the arrangement it needs: the mux runs in master-worker mode with a pidfile,
so `reload` swaps the certificate under a running server by signalling the
master, and nothing on the shared port drops (10.1). An operator who passes
their own `--haproxy-config` and runs HAProxy some other way writes the
command themselves; if that HAProxy is a master with a pidfile of its own,
`kill -USR2` on it is the equivalent, and `haproxy -sf` on a pidfile is the
older form of the same handover.

One run answers for one name, because a token answers for one account: two
bound names in one account are two runs, and two accounts are two tokens and
two more. A crontab line is therefore one line per name, and a wrapped
invocation is not needed for that. It must hold no key - a crontab is not a
place for a secret, and neither is an argument list - so the key is read
from a file, and the commands are absolute, because a cron `PATH` is not this
shell's. The two accounts of this installation are two lines, one token file
each, and both PEMs are the ones the mux binds (10.1):

```cron
17 4 * * * /usr/bin/python3 /root/srv/minecraft-asp-server/scripts/sync_natfrp_cert.py --domain <sub>.<account>.nyat.app --out /root/asp-frpcs/tls/<sub>.<account>.nyat.app.pem --token-file /root/asp-frpcs/tokens/<account> --reload-command "/bin/sh /root/srv/minecraft-asp-server/scripts/scenes/frpc-shared-tcp.sh reload" >>/var/log/asp-cert-sync.log 2>&1
19 4 * * * /usr/bin/python3 /root/srv/minecraft-asp-server/scripts/sync_natfrp_cert.py --domain <sub>.<other-account>.nyat.app --out /root/asp-frpcs/tls/<sub>.<other-account>.nyat.app.pem --token-file /root/asp-frpcs/tokens/<other-account> --reload-command "/bin/sh /root/srv/minecraft-asp-server/scripts/scenes/frpc-shared-tcp.sh reload" >>/var/log/asp-cert-sync.log 2>&1
```

The two lines overlap by design rather than by accident: a reload re-reads
the whole configuration, so the reload of either run also takes in whatever
the other certificate file holds by then. One name renewing two minutes
before the other is not a reason to order them.

Daily is enough, and often a no-op twice over: a run asks the provider to
reissue only inside `--renew-window-days` (7) and downloads only when the
`.created` sidecar says the file is not the certificate the account holds
now. Nothing needs to be rotated or expired by hand, and a non-zero exit is
the only signal there is, so the log line is what turns the schedule into
something that can be noticed.

Exit codes: `0` the file is current or was updated, `1` the API, the
certificate or a command failed, `2` usage. `--dry-run` reports and
downloads, and writes nothing. A failed `--reload-command` is one of the
`1`s, and deliberately so: the file was written while the running server
still serves the old certificate, which is a failure even though nothing was
lost.

Two provider-side facts shape how this has to be run. The first certificate
for a name is issued when frpc first fetches it with `auto_https` on, so an
account that never turned that on is told there is no certificate yet and
needs one throwaway `auto_https` run first. And the provider renews a
certificate automatically only while it counts as active, which its
documentation defines as loaded through `auto_https` within the last five
days - exactly what keeping `auto_https` off for the mux gives up. The
explicit renewal in step 2 is what replaces that, so scheduling this script
(cron, a systemd timer, the operator's choice) is not optional decoration.

The `<name>.crt` and `<name>.key` files frpc writes into its working
directory are self-signed stand-ins it generates at startup; the certificate
on the wire, and the pair the API returns, is the issuer's. None of this
disturbs the `--config` directory rule of 10: it takes only `.ini`, `.toml`,
`.yaml` and `.yml`, and `~/asp-frpcs/tls/` is a subdirectory it never looks
into.
