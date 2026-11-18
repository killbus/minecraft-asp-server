# Inventory: `server/` by class

Walked `server/` on 2026-11-18, 28 source files bundled, everything else
excluded as instance or regenerable. Sizes and mtimes taken from the live
tree; plugin defaults extracted from each jar and compared where the jar
carries one.

Class rule (from `design.md`): would two hosts running the same world
legitimately have different bytes?

- no -> **source**, copied into `config/`
- yes, operator supplies it -> **secret**, a `${NAME}` placeholder
- yes, the host produced it by running -> **instance**, never bundled

## Source, bundled (28)

| Path | Bytes | Placeholder | Note |
| --- | --- | --- | --- |
| `server.properties` | 1840 | `MANAGEMENT_SERVER_SECRET` | CRLF. `rcon.password` is empty and `enable-rcon=false`, so no RCON placeholder |
| `bukkit.yml` | 1141 | - | |
| `spigot.yml` | 4901 | - | |
| `commands.yml` | 491 | - | |
| `permissions.yml` | 146 | - | |
| `config/paper-global.yml` | 4497 | - | velocity disabled, `secret: ''` |
| `config/paper-world-defaults.yml` | 8618 | - | |
| `plugins/bStats/config.yml` | 322 | `BSTATS_SERVER_UUID` | uuid is generated per install; default is the existing one |
| `plugins/CoreProtect/config.yml` | 4533 | - | mysql disabled, `mysql-password` empty |
| `plugins/CoreProtect/language.yml` | 12082 | - | |
| `plugins/floodgate/config.yml` | 3153 | `FLOODGATE_METRICS_UUID` | see discovery 1 |
| `plugins/Geyser-Spigot/config.yml` | 20480 | `GEYSER_ADVERTISE_ADDRESS` | `frp-net.com:34003` is this deployment's public entry |
| `plugins/GrimAC/config.yml` | 11134 | - | |
| `plugins/GrimAC/database.yml` | 4747 | - | sqlite routing, `data/` is instance |
| `plugins/GrimAC/databases/mongo.yml` | 1269 | - | empty password |
| `plugins/GrimAC/databases/mysql.yml` | 2636 | - | empty password |
| `plugins/GrimAC/databases/postgres.yml` | 1967 | - | empty password |
| `plugins/GrimAC/databases/redis.yml` | 1729 | - | empty password |
| `plugins/GrimAC/databases/sqlite.yml` | 1880 | - | |
| `plugins/GrimAC/discord.yml` | 878 | - | webhook empty, `enabled: false` |
| `plugins/GrimAC/messages.yml` | 8357 | - | |
| `plugins/GrimAC/punishments.yml` | 3161 | - | |
| `plugins/Multiverse-Core/config.yml` | 17060 | - | holds `join-destination: world` |
| `plugins/PackManagerPro/config.yml` | 935 | `PACK_URL` | `per-world-application.trials.pack-url` |
| `plugins/SkinsRestorer/config.yml` | 16694 | - | `database.type: FILE`, the SQL block is the plugin's own default |
| `plugins/spark/config.json` | 117 | - | |
| `plugins/ViaBackwards/config.yml` | 3788 | - | byte-identical to the jar default except line endings |
| `plugins/ViaVersion/config.yml` | 13198 | - | differs from the jar default: operator edits |

## Instance, excluded

- `world/` — whole tree, `level.dat`, `dimensions/**`, `players/**`, `data/**`
- `plugins/Multiverse-Core/worlds.yml`, `plugins/Multiverse-Core/anchors.yml`
- `plugins/floodgate/key.pem`
- `plugins/CoreProtect/database.db`, `plugins/CoreProtect/.license`
- `plugins/GrimAC/data/**` (`history.v1.db`, `storage-instance.uuid`)
- `plugins/Geyser-Spigot/nethernet/**` (`identity.pem`, `operator-link.txt`, `provider-state/*`)
- `plugins/SkinsRestorer/players/**`, `plugins/SkinsRestorer/skins/**`,
  `plugins/SkinsRestorer/recommendations.json`
- `plugins/Geyser-Spigot/locales/**`, `plugins/SkinsRestorer/locales/**`
- `plugins/spark/tmp/**`
- `ops.json`, `whitelist.json`, `banned-ips.json`, `banned-players.json`,
  `usercache.json`, `eula.txt`
- `start.cmd`, `*-run.log`, `start-test*.log`, `world.7z`, `world.1.7z`
- `.paper/`, `cache/`, `logs/`, `libraries/`, `versions/`, `packs/`
- `.rollback/**`

## Discoveries that corrected the PRD

1. **`floodgate/config.yml` is source, with one generated field.** The jar's
   own default is `metrics.uuid: ${metrics.uuid}`, and Floodgate substitutes
   a fresh UUID on first start. The key is generated, not operator-declared.
   It is templated as `${FLOODGATE_METRICS_UUID}` with the existing value as
   the manifest default, so a fresh host renders a valid UUID and a live
   host is not churned. No credential may ever get a default.

2. **`bStats/config.yml` is the same shape.** `serverUuid` is the generated
   install identity. `enabled` and `logFailedRequests` are the only
   declarative bytes, so the file is bundled rather than dropped; dropping it
   would silently lose the opt-out.

3. **`plugins/*/databases/` is not instance.** The PRD listed the directory
   with `data/`, but GrimAC keeps one YAML per backend there
   (`mongo.yml`..`sqlite.yml`) and `database.yml` selects between them. The
   rule is now by content: `data/` is instance state, `databases/` carries
   per-backend connection config. None of those files currently holds a live
   password.

4. **`eula.txt` is instance.** It records one host's acceptance, not
   behaviour. Applying it elsewhere would accept a licence on the
   operator's behalf. It starts `eula=false` on a fresh host and the operator
   flips it.

5. **`start.cmd` is not configuration.** It is a local launcher leftover; the
   launcher is `scripts/start.cmd` in this repo.

6. **Two `*.before-direct-test` leftovers exist** in `server/`:
   `config/paper-global.yml.before-direct-test` and
   `plugins/Geyser-Spigot/config.yml.before-direct-test`. They differ from the
   live files only in the HAProxy flag and are not sources.

7. **`plugins/spark/config.json`** is byte-identical to what spark writes on
   first start (`backgroundProfiler: true`), so it is bundled as the
   declared default rather than treated as state.

## Reproducibility check

`python -B scripts/apply_config.py --dry-run` against the live tree with

```text
MANAGEMENT_SERVER_SECRET=<rcon/management secret>
PACK_URL=http://127.0.0.1:8000/packs/pack-a.zip
GEYSER_ADVERTISE_ADDRESS=frp-net.com:34003
```

reports `UNCHANGED` for all 28 files, 0 `CREATE`, 0 `UPDATE`.

## Not bundled, and why it is not a gap

- `paper-server.jar` and `plugins/*.jar` — `runtime.lock.json` plus
  `scripts/install_runtime.py`.
- `packs/pack-a.zip` — externally sourced, recipe and digest in
  `docs/PAPER-WORLD-SOP.md` section 4, served by `scripts/serve_packs.py`.
- `server-icon.png` — absent from this tree. If an operator adds one it is
  declarative; it is a byte copy, not a template, so it is a follow-up rather
  than part of this task.
- `logs/`, `cache/`, `.paper/`, `libraries/`, `versions/` — Paper runtime.
