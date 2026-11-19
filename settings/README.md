# Per-host settings

`config/` holds the bytes that are identical on every host. This directory
holds the values that are not.

The production file is **not tracked**. Git stores the example only, so a
clone never carries one deployment's coordinates:

```sh
cp settings/minecraft-server.example.json settings/minecraft-server.json
$EDITOR settings/minecraft-server.json
python -B scripts/apply_config.py --settings settings/minecraft-server.json
```

`settings/*.json` is gitignored except `*.example.json`. Name the file after
the host it describes and pass it explicitly with `--settings`; nothing reads
this directory implicitly.

Shape:

```json
{
  "schema_version": 1,
  "values": {
    "PACK_URL": "https://<public>:<port>/packs/pack-a.zip",
    "GEYSER_ADVERTISE_ADDRESS": "<public>:34003",
    "MANAGEMENT_SERVER_SECRET": "env:MANAGEMENT_SERVER_SECRET"
  }
}
```

Rules:

- A coordinate (public address, public pack URL, port) is a literal, and it
  is not source: it changes for reasons the code does not. It lives in this
  untracked file, so `git pull` on the host never has to reconcile it.
- A credential is never a literal either. Write `env:VARIABLE`; the tool reads
  the process environment when it renders and refuses if the variable is
  unset. The value never enters the file, so `--check` and a diff stay safe to
  share.
- `--set NAME=VALUE` overrides the file, then the file overrides the
  environment, then the manifest default applies.
- Keys are placeholder names (`PACK_URL`), not paths. A key that no template
  declares is refused, so a typo cannot sit silent.
- The file holds exactly `schema_version` and `values`; the host is named by
  the filename, not by a field the tool would have to validate.
- This file is instance state, and section 7 of
  [PAPER-WORLD-SOP.md](../docs/PAPER-WORLD-SOP.md) includes it in the server
  snapshot precisely because git cannot reproduce it. Restore a snapshot's
  copy only onto the host that snapshot came from; onto another host, start
  from `minecraft-server.example.json` instead.

`PACK_URL` and `GEYSER_ADVERTISE_ADDRESS` both derive from the frp entry.
They are declared here rather than parsed out of the frpc scene, because the
config bundle must not depend on the network layer. When the entry changes,
update this file and the scene in the same change.

`PACK_URL` must be `https://` — the frp entry serves no plaintext http. The
one exception is loopback (`http://127.0.0.1`, `localhost`, `::1`), which
never crosses the entry and stays the template's local-only default.
