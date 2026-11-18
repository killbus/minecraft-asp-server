# Version the server configuration as source

## Goal

`server/` is gitignored as one blob, so declarative configuration and
instance state travel together. Deploying today means copying `plugins/*/`
directories by hand, which carries `worlds.yml`, key files, databases, caches,
and player data onto a host that does not have the matching worlds.

Separate the three classes and give the declarative one a versioned source
tree plus an apply command, the same way `runtime.lock.json` does for
binaries.

## Classes

- **source** - a human edits it to define behaviour. Portable across hosts.
  `server.properties`, `bukkit.yml`, `spigot.yml`, `commands.yml`,
  `permissions.yml`, `config/paper-*.yml`, and each plugin's declarative
  config (`config.yml`, `database.yml`, `discord.yml`, `messages.yml`,
  `punishments.yml`, `language.yml`).
- **secret** - a value inside a source file that must not be committed, or a
  host-specific value that must be rendered at apply time. Rendered from
  placeholders; never stored.
- **instance** - produced by play or by the host: `world/`,
  `plugins/*/worlds.yml`, `*.db`, `playerdata`, `players`, `skins`, `cache/`,
  `logs/`, `usercache.json`, `ops.json`, `whitelist.json`, `banned-*.json`,
  `anchors.yml`, `nethernet/`, `packs/`, anything under `plugins/*/data/`, and
  database files under `plugins/*/databases/`.

## Requirements

- R1. A tracked `config/` tree mirrors `server/`-relative paths and contains
  only class `source` files, with `${NAME}` placeholders for every class
  `secret` or host-specific value.
- R2. `config.lock.json` lists each bundled file with its class and the
  SHA-256 of the committed template.
- R3. `scripts/apply_config.py` renders the templates and writes them into
  `--server-dir`, atomically, and only for paths the manifest names.
- R4. The command refuses: a path outside the manifest, a path classed as
  instance, an unknown `${NAME}`, a missing value, or a template whose hash
  no longer matches the manifest. Exit 2 for all of them.
- R5. `--dry-run` prints `CREATE`/`UPDATE`/`UNCHANGED` per file and writes
  nothing; `--check` exits 1 if any destination differs.
- R6. No instance path can be added to the manifest: the apply tool and its
  tests enforce the class rule, not a comment.
- R7. Documentation states the operator flow: stop the server, `git pull`,
  `apply_config.py --set PACK_URL=...`, start.

## Acceptance Criteria

- [x] `config/` holds every file from the `source` list above and nothing
      from `instance`.
- [x] `apply_config.py` reproduces the current `server/` configuration in a
      scratch directory, byte for byte after rendering.
- [x] Tests cover: render, missing value, unknown placeholder, path escape,
      instance-path refusal, hash drift, `--dry-run` writing nothing.
- [x] `docs/PAPER-WORLD-SOP.md` section 7 and `docs/ASP-SOP.md` describe the
      class boundary and the apply command.

## Notes

- `worlds.yml` is instance: Multiverse writes it from the live worlds. A
  copied one declares worlds the host does not have.
- `floodgate/key.pem` is instance, not secret: Floodgate generates it on
  first start, so by the boundary rule it is host-produced state. It is
  still key material, which is why overwriting it breaks existing XUID
  links; that is a consequence of the class, not a reason to template it.
- `plugins/GrimAC/databases/*.yml` is source, not instance: those five files
  declare backend targets (`host`, `port`, `password`, pool sizes). The
  instance glob has to name the database files, not the directory.
- `ops.json`, `whitelist.json`, and `banned-*.json` are operator state, not
  configuration; a deploy must not overwrite them.
