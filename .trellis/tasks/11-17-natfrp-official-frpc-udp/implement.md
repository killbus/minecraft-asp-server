# Implementation plan

## 1. Add manifest parsing to `frpc.sh`

- Add `up --scene FILE` parsing.
- Keep `--config` parsing and output unchanged.
- Parse top-level `session` and `server`, then sections with `binary` and
  `config`.
- Resolve paths relative to the scene file.
- Reject duplicate, unknown, empty, and malformed entries before touching
  tmux.
- Represent parsed sidecars as `section<TAB>binary<TAB>config` records.

## 2. Generalize sidecar command construction

- Change `sidecar_command` to accept the selected binary and config.
- Preserve the configuration-directory working directory rule.
- Apply the per-section binary for manifest mode and the existing `FRPC`
  resolution for legacy mode.
- Ensure paths with spaces and single quotes remain correctly quoted.

## 3. Implement server lifecycle variants

- Add `server = false` support with no server window and no placeholder.
- Keep `server = true` ordering: sidecars first, readiness check, server last.
- Keep `--defer-server` as an internal composition mode.
- Update `down` to handle a session with no server window.
- Keep `status` and `attach` behavior unchanged for both variants.

## 4. Extend `frpc-shared-tcp.sh`

- Add `--scene FILE` and make it mutually exclusive with `--config`.
- Delegate sidecar startup to `frpc.sh` with the scene file and deferred
  server mode.
- Keep HAProxy generation, readiness, reload, and final server start in the
  wrapper.
- Preserve all existing `--config` behavior and options.
- Ensure the wrapper can run two TCP entry sections plus one UDP section.

## 5. Add tracked examples

- `examples/scenes/README.md`: explain the operator-owned boundary, the
  one-section-per-process rule, and the Java-plus-signalling role of a TCP
  entry.
- `examples/scenes/asp-frpc-udp.scene.example`: standalone sidecar-only UDP.
- `examples/scenes/asp-frpc-shared.scene.example`: two TCP entries and one
  UDP process.
- `examples/scenes/frpc/official-frpc-udp.toml.example`: official frpc UDP
  proxy with `transport.proxyProtocolVersion = "v2"`.
- `examples/scenes/frpc/sakura-frpc-entry.toml.example`: TCP entry pointing
  at the shared mux, with placeholder account/provider values.

Use only placeholders:

- `frp.example.net`
- `203.0.113.10`
- `<account>`
- `<public-port>`

Do not include real provider names, account IDs, tokens, domains, or IPs.

## 6. Update `docs/ASP-SOP.md`

- Document `frpc.sh up --scene FILE` and the manifest grammar.
- Explain that multiple TCP entries can share one local HAProxy mux and each
  is both a Java and signalling entry.
- Document per-section binaries and the Sakura/official-frpc split.
- Update section 10.1.2 to use official frpc for the UDP PROXY v2 tunnel and
  remove the outdated implication that the Sakura client is the tested UDP
  path.
- Document the example boundary and that examples are not deployment assets.
- Mention that the UDP probe is optional and not a core/runtime dependency.

## 7. Add regression tests

- Create `tests/test_frpc_scene_manifest.py`.
- Extend shared-TCP tests for `--scene` if the wrapper changes are covered
  separately.
- Add coverage for:
  - relative path resolution;
  - multiple sections and per-section binary selection;
  - duplicate sections and keys;
  - unknown keys and invalid `server` values;
  - `server = false` lifecycle;
  - `server = true` ordering;
  - `--scene`/`--config` mutual exclusion;
  - unchanged legacy `--config` output.

## 8. Validate

Run, in order:

```sh
python -B -m unittest tests.test_frpc_scene_configs -v
python -B -m unittest tests.test_frpc_scene_spawn -v
python -B -m unittest tests.test_frpc_scene_manifest -v
python -B -m unittest tests.test_frpc_shared_tcp_scene -v
python -B -m unittest discover -s tests -v
python ./.trellis/scripts/task.py validate .trellis/tasks/11-17-natfrp-official-frpc-udp
```

If `sh` or `tmux` is unavailable, record the skip explicitly rather than
pretending the scene tests ran.

## Rollback points

- Parser/lifecycle changes are isolated to `scripts/scenes/frpc.sh`.
- Shared-wrapper changes are isolated to `scripts/scenes/frpc-shared-tcp.sh`.
- Examples and docs are additive.
- Reverting the two scripts restores `--config` behavior without touching
  `start.*`, `backup.*`, or the verifier.
