# Per-host settings

`config/` holds the bytes that are identical on every host. This directory
holds the values that are not.

A settings file is named after the host it describes and is passed explicitly:

```sh
python -B scripts/apply_config.py --settings settings/minecraft-server.json
```

Shape:

```json
{
  "schema_version": 1,
  "values": {
    "PACK_URL": "http://<public>:<port>/packs/pack-a.zip",
    "GEYSER_ADVERTISE_ADDRESS": "<public>:34003",
    "MANAGEMENT_SERVER_SECRET": "env:MANAGEMENT_SERVER_SECRET"
  }
}
```

Rules:

- A coordinate (public address, public pack URL, port) is a literal. It is not
  a secret, so committing it makes the deploy reviewable and reproducible.
- A credential is never a literal. Write `env:VARIABLE`; the tool reads the
  process environment when it renders and refuses if the variable is unset.
  The value never enters the file, so `--check` and a diff stay safe to share.
- `--set NAME=VALUE` overrides the file, then the file overrides the
  environment, then the manifest default applies.
- Keys are placeholder names (`PACK_URL`), not paths. A key that no template
  declares is refused, so a typo cannot sit silent.
- The file holds exactly `schema_version` and `values`; the host is named by
  the filename, not by a field the tool would have to validate.
- Nothing reads this directory implicitly. No `--settings`, no file, and the
  environment fallback is exactly the old behaviour.
- If the coordinates themselves should stay out of git, gitignore `settings/`
  and distribute the file out of band. The tool does not care.

`PACK_URL` and `GEYSER_ADVERTISE_ADDRESS` both derive from the frp entry.
They are declared here rather than parsed out of the frpc scene, because the
config bundle must not depend on the network layer. When the entry changes,
update this file and the scene in the same commit.
