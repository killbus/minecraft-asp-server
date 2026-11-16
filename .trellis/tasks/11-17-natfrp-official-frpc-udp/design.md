# Design: Declarative frpc scenes

## Boundary

Scenes are an optional Linux operator composition layer:

```text
scene manifest (operator-owned, outside the repository)
        |
        +-- frpc.sh parser and lifecycle
        |       +-- one tmux window per declared process
        |
        +-- frpc-shared-tcp.sh (optional)
                +-- HAProxy mux
                +-- final ASP server start
```

The repository owns the parser, lifecycle, examples, and tests. The operator
owns real frpc binaries, configs, certificates, credentials, and provider
account data under a directory such as `~/asp-frpcs/`.

`examples/scenes/` is the only tracked scene/config boundary. Examples are
documentation, not runnable deployment assets.

## Manifest grammar

The parser recognizes only these lines:

```text
# whole-line comment

session = asp-frpc
server = false

[entry_account_a]
binary = /home/operator/asp-frpcs/bin/sakura-frpc
config = /home/operator/asp-frpcs/entry-account-a.toml

[udp]
binary = /home/operator/asp-frpcs/bin/frpc
config = /home/operator/asp-frpcs/official-udp.toml
```

Rules:

- Blank lines and whole-line comments beginning with `#` are ignored.
- Inline comments are not interpreted, so paths may contain `#`.
- `key = value` is split at the first `=`, then surrounding whitespace is
  removed.
- Top-level keys must appear before the first section.
- `session` and `server` are required. `server` is exactly `true` or `false`.
- `session` uses the same character set as the existing `FRPC_SESSION`
  validation.
- `FRPC_SESSION` has precedence over the scene's `session` value, preserving
  the existing environment override and letting the shared-TCP wrapper align
  the session it owns with the sidecars it delegates.
- Every section requires exactly one `binary` and one `config`.
- Section names use letters, digits, `_`, and `-` only.
- Unknown keys, repeated keys, repeated sections, empty values, and malformed
  lines are errors.
- The parser does not source the file or execute substitutions.

The parser returns records shaped as:

```text
<section>\t<resolved binary>\t<resolved config>
```

The existing legacy path keeps its `<bare>\t<config>` records and is not
forced through the manifest parser.

## Path resolution

Resolve paths in this order:

1. If the value is absolute, use it as-is.
2. If it contains `/`, resolve it relative to the scene file's directory.
3. Otherwise, treat it as a command name and resolve it through `PATH` when
   the scene starts.

For `config`, a bare name is still a path relative to the scene directory,
because a config is data, not an executable. This asymmetry is deliberate:
`binary = frpc` is a natural command name, while `config = frpc.toml` is a
natural file next to the scene.

The scene file itself is resolved to an absolute path before parsing. No
relative path is interpreted against the caller's current directory.

## Lifecycle

### `server = true`

```text
create session + server placeholder
start all sidecar windows
wait for every sidecar to remain alive
respawn server window with `bash scripts/start.sh`
```

This is the existing lifecycle, with the sidecar list coming from the
manifest instead of `--config`.

### `server = false`

```text
create session with the first sidecar as its initial window
start remaining sidecar windows
wait for every sidecar to remain alive
leave the session running without a server window
```

No `server` window and no `@asp-server-deferred` placeholder are created.
`down` checks for an actual server window; when absent it kills the session
directly.

### `--defer-server`

This remains an internal option used by `frpc-shared-tcp.sh`. It means
"create/reserve the server window, but do not start it yet". It is not a
sidecar-only mode and does not replace the manifest's `server` setting.

## Multiple TCP entries

Each of these configs is a separate frpc process because they may use
different provider accounts, server addresses, and binaries:

```ini
[entry_account_a]
binary = /root/asp-frpcs/bin/sakura-frpc
config = /root/asp-frpcs/entry-a.toml

[entry_account_b]
binary = /root/asp-frpcs/bin/sakura-frpc
config = /root/asp-frpcs/entry-b.toml
```

Both configs point their TCP proxy at `127.0.0.1:25566`. The HAProxy mux
classifies the stream:

- TLS ClientHello or HTTP method prefix -> Geyser built-in signalling.
- Java legacy ping or handshake -> Paper.

Thus each public TCP entry is simultaneously a Java entry and a signalling
entry. The scene does not need a `role = java` or `role = signaling` key.
The UDP media tunnel is separate and is declared as its own section.

## Shared-TCP integration

`frpc-shared-tcp.sh` keeps its current `--config` mode and gains
`--scene FILE`:

```text
parse/defer sidecars through frpc.sh
start HAProxy
wait for HAProxy to bind
start the server last
```

The wrapper passes `FRPC_SESSION` to `frpc.sh`, so the existing environment
override continues to align the session name even when a manifest also names
one. The scene manifest is the source of process selection and per-process
binaries; the wrapper remains the source of the HAProxy and final-server
ordering.

The wrapper must not require `--no-server`. If the manifest says
`server = false`, `--defer-server` still creates the composition placeholder;
the wrapper owns the eventual `start.sh`.

## Data flow

```text
Java client
  -> provider TCP entry A/B
  -> frpc TCP proxy (Sakura)
  -> HAProxy mux :25566
  -> Paper :25565

Bedrock client
  -> provider TCP entry A/B
  -> frpc TCP proxy (Sakura)
  -> HAProxy mux :25566
  -> Geyser signalling :19132 (HTTP/TLS)

Bedrock media
  -> provider UDP entry
  -> official frpc UDP proxy :19132
  -> Geyser NetherNet media listener
```

The TCP and UDP paths have different proxies and different failure modes.
The scene must report which sidecar failed rather than collapsing them into
one generic "frpc failed" message.

## Error handling

- Parse errors exit 2 before tmux or frpc is started.
- Missing/unreadable configs and non-executable binary paths exit 2 before
  session creation.
- A sidecar that exits during readiness leaves the tmux session running and
  prints the last 20 captured lines.
- A duplicate section or key names the offending line or section.
- A sidecar-only `down` does not attempt to send `stop` to a nonexistent
  server window.
- The shared wrapper reports sidecar, mux, and server phases separately.

## Compatibility

The new parser is additive. `--config` remains the default mode and uses the
existing directory selection rules:

- immediate non-hidden regular files;
- `.ini`, `.toml`, `.yaml`, `.yml`;
- explicit files accepted regardless of extension;
- ignored files reported on stderr.

`FRPC_SESSION`, `FRPC`, `FRPC_READY_TIMEOUT`, and `FRPC_STOP_TIMEOUT` retain
their existing meanings. In manifest mode, each section's `binary` overrides
`FRPC`; in legacy mode, `FRPC` remains the single binary.

## Security and secrets

- The repository never stores real provider configs, tokens, account IDs,
  public IPs, certificates, or private keys.
- Examples use placeholders and `.example` suffixes.
- The manifest parser only reads files; it does not source or evaluate them.
- The scene does not print config contents. Sidecar failures print only the
  last tmux output, which is operator-visible and may contain provider
  messages; docs must say not to paste those logs into public issues.

## Testing strategy

Add `tests/test_frpc_scene_manifest.py` with temporary files and a stub tmux:

- parse multiple sections and assert per-section binary/config commands;
- resolve relative paths against the scene directory;
- reject duplicate sections, duplicate keys, unknown keys, and missing
  required values;
- reject malformed `server` values and invalid section names;
- assert `server = false` creates no server window or placeholder;
- assert `server = true` starts sidecars before the server;
- assert `--scene` and `--config` are mutually exclusive;
- assert legacy `--config` output remains unchanged;
- exercise `frpc-shared-tcp.sh --scene --dry-run` and assert the server-last
  order.

Keep the existing tests intact. Use only POSIX `sh` and Python's standard
library so the suite runs on Linux and in the current development
environment.

## Rollout and rollback

Rollout is operator-controlled and optional:

1. Keep the current `--config` invocation working.
2. Add a scene file outside the repository.
3. Switch one invocation from `--config` to `--scene`.
4. Remove the scene file to roll back; core ASP behavior is unchanged.

Rollback of the shared wrapper is the same: return to `--config` and keep
the manifest on disk unused.
