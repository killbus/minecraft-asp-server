# Per-host settings

`config/` holds the bytes that are identical on every host. This directory
holds the values that are not.

The production file is **not tracked**. Git stores the example only, so a
clone never carries one deployment's coordinates:

```sh
[ -f settings/minecraft-server.json ] || cp settings/minecraft-server.example.json settings/minecraft-server.json
$EDITOR settings/minecraft-server.json
python -B scripts/apply_config.py --settings settings/minecraft-server.json
```

`settings/*.json` is gitignored except `*.example.json`. The normal host file is
`settings/minecraft-server.json`: the renderer takes it explicitly with
`--settings`, while direct launchers read its optional resource-pack section
automatically. Alternative filenames remain supported by the renderer but are
not startup inputs. Both consumers share `scripts/host_settings.py` for schema
validation; the launcher never resolves unrelated credentials or reapplies configs.

Shape:

```json
{
  "schema_version": 1,
  "values": {
    "GEYSER_ADVERTISE_ADDRESS": "<public>:34003",
    "MANAGEMENT_SERVER_SECRET": "env:MANAGEMENT_SERVER_SECRET"
  },
  "resource_packs": {
    "default": null,
    "worlds": {}
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
- `--set NAME=VALUE` overrides `values`, then the file overrides the
  environment, then the manifest default applies. Resource-pack policy ownership
  is the exception described below.
- Keys inside `values` are placeholder names, not paths. A key that no template
  declares is refused, so a typo cannot sit silent.
- The file requires `schema_version: 1` and `values`; `resource_packs` is optional.
  Unknown fields, duplicate keys and malformed sections are rejected by both
  consumers. Syntactically valid `env:` references are resolved only by the
  renderer, so starting with existing native config does not require those secrets.
- This file is instance state, and the backup contract in
  [SINGLE-WORLD-SOP.md](../docs/SINGLE-WORLD-SOP.md) includes it in the server
  snapshot precisely because git cannot reproduce it. Restore a snapshot's
  copy only onto the host that snapshot came from; onto another host, start
  from `minecraft-server.example.json` instead.

Resource-pack URLs and `GEYSER_ADVERTISE_ADDRESS` both derive from the frp entry.
They are declared here rather than parsed out of the frpc scene, because the
config bundle must not depend on the network layer. When the entry changes,
update this file and the scene in the same change.

`resource_packs` holds exactly `default` and `worlds`. A pack is either `null`
(disabled) or `{ "url": "...", "sha1": "..." }`, where SHA-1 is the 40-hex
digest of the exact ZIP served. `default` applies to unspecified startup saves;
`worlds` maps save names to overrides, including null to disable a global pack.
Use HTTPS for public URLs; HTTP is accepted only on loopback. No environment
references are allowed inside resource-pack descriptors.

When this section exists, the renderer writes an empty canonical native pack
and startup projects the selected descriptor into disposable native properties.
Old `values.PACK_URL` or environment `PACK_URL` cannot override it; remove the
old value after migration. A nonempty `--set PACK_URL=...` is rejected as a
conflict. Without the section, the old required PACK_URL behavior remains:
explicit empty disables the pack, a valid URL selects it globally. Absence of the
section at startup preserves existing native properties; it does not re-render
legacy values automatically.

If an earlier checkout used `settings/resource-packs.json`, move its `default`
and `worlds` into `minecraft-server.json` under `resource_packs` (omit its nested
schema_version), then remove the redundant file after checking the merge.
Startup refuses a leftover standalone file with migration guidance. Both files
remain host-owned; the tool never migrates or deletes them automatically.

See [SINGLE-WORLD-SOP.md](../docs/SINGLE-WORLD-SOP.md) for a per-save example and
the read-only `select_resource_pack.py --world NAME --check` command.
