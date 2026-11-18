# Design: configuration as source

## Boundary rule

One question decides the class: **would two hosts running the same world
legitimately have different bytes?**

- No -> source; commit it.
- Yes, and it is a value the operator supplies -> secret; template it.
- Yes, because the host generated it by running -> instance; never commit,
  never apply.

`worlds.yml` fails that test twice (generated, and host-specific), which is
why copying it breaks a host that has a different world set.

## Shape

```
config/
  server.properties              # with ${RCON_PASSWORD}
  bukkit.yml
  spigot.yml
  commands.yml
  permissions.yml
  config/paper-global.yml
  config/paper-world-defaults.yml
  plugins/Geyser-Spigot/config.yml
  plugins/Floodgate/config.yml   # no key material; key.pem stays instance
  plugins/PackManagerPro/config.yml   # with ${PACK_URL}
  ...
config.lock.json
```

Templates keep the original formatting; only the secret positions become
`${NAME}`. Rendering is textual, not YAML-aware, so a value never changes the
document's shape.

## Apply

```
for each manifest entry:
    template = config/<path>
    verify sha256(template) == entry.sha256      else REFUSE (2)
    render ${NAME} from --set/ENV                 else REFUSE (2)
    destination = safe_path(server_dir, entry.path)
    classify(entry.path) must be source           else REFUSE (2)
    compare with destination
    UNCHANGED | UPDATE | CREATE
    write to <dest>.tmp.<pid> and os.replace
```

`apply_config.py` reuses `verify_runtime.safe_path` for the same reason the
installer does: one escape rule in the project, not two.

## Relationship to backups

`scripts/backup.*` already snapshots every class in one tree: `world/`,
`plugins/*/` minus jars, `config/`, and the top-level `*.yml`/`*.json`.
So a full restore already returns both source and instance state, verified
by `MANIFEST.txt`, and this task is **not** a recovery mechanism.

The two differ in what they are for. A backup is one host at one instant,
restored onto a host that expects that same world set and key material. It
cannot be used selectively: copying `plugins/*/` out of a snapshot onto a
different host is exactly the failure this task removes. `apply_config.py`
is idempotent, selective, and renders host values, so it converges a host
to a declared state instead of reproducing a past one.

Known gap, out of scope here: the snapshot does not carry
`runtime.lock.json`, so a restore is only reproducible while the operator
kept the lock revision beside it (`docs/ASP-SOP.md` section 4.1). Fixing
that touches `scripts/backup.*`, not the config contract.

## Why not a zip bundle

Git already transports files with review, diff, and history. A zip adds a
second artefact to keep in sync and hides the diff at deploy time. The
manifest plus the tracked tree is the bundle.

## Failure semantics

| Condition | Result |
| --- | --- |
| server still running | documented precondition; the tool does not detect it |
| missing placeholder value | exit 2, nothing written |
| template drifted from the manifest | exit 2 |
| destination is instance state | exit 2 |
| write failure | the `.tmp` sibling is removed, the destination is untouched |
