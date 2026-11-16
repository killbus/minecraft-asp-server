# PRD: Declarative frpc scenes for mixed NATFRP entries

## Context

The current optional `scripts/scenes/frpc.sh` accepts one or more `--config`
files or directories and starts one frpc process per selected configuration.
That works when every configuration is run by the same frpc binary. The
deployment now needs a mixed set:

- Sakura frpc for TCP entries, because those entries use provider-specific
  `auto_https` behavior and provider-issued certificates.
- Official frpc for the UDP NetherNet media tunnel, because the verified
  official client forwards UDP PROXY protocol v2 correctly.
- Several TCP entries from different providers or accounts, all pointing at
  the same local HAProxy mux (`127.0.0.1:25566`).

Each TCP entry that reaches the HAProxy mux is both a Java entry and a
Bedrock NetherNet built-in-signalling entry. The two protocols are separated
by HAProxy after they arrive; no second tunnel is required for signalling.
The UDP media plane remains a separate tunnel to Geyser's `19132`.

## Goals

- Make the optional scene declarative instead of encoding process selection
  in command-line switches.
- Allow one scene to mix different frpc binaries and configurations.
- Allow multiple TCP entries without treating each proxy in one config as a
  separate process.
- Start the ASP server only after every declared sidecar has passed its
  readiness check.
- Support a sidecar-only scene that has no server window and no deferred
  server placeholder.
- Preserve the existing `--config` behavior for operators who do not need a
  manifest.
- Keep every repository example free of credentials, account identifiers,
  real public addresses, certificates, and provider-bound host names.

## Functional requirements

### R1. Manifest input

`scripts/scenes/frpc.sh up --scene FILE` starts a scene from a small
operator-owned manifest. `--scene` and `--config` are mutually exclusive.
The manifest is a simple INI-like text file, not TOML, YAML, JSON, or a
shell script.

Top-level keys:

- `session`: tmux session name.
- `server`: `true` or `false`, stating whether a standalone `frpc.sh` scene
  owns the ASP server.

`FRPC_SESSION`, when set, overrides the scene's `session`; this is the
existing composition/test hook and is how `frpc-shared-tcp.sh` keeps the
wrapper and the sidecars on the same tmux session.

Each section describes exactly one frpc process:

```ini
[entry_account_a]
binary = /path/to/sakura-frpc
config = /path/to/frpc-entry-a.toml
```

- The section name becomes the tmux window name `frpc-<section>`.
- `binary` selects the executable for that process.
- `config` selects that process's configuration file.
- A single section may contain a config with multiple `[[proxies]]`; those
  proxies stay in one process and one window.

### R2. Path and validation rules

- Relative `binary` and `config` paths resolve against the directory of the
  scene file, not the caller's current directory.
- Absolute paths are accepted.
- Config files must exist and be regular readable files before startup.
- A binary path must be executable. A bare command name may be resolved on
  `PATH`.
- Duplicate top-level keys, duplicate section names, duplicate keys within a
  section, unknown keys, empty values, and invalid section names are rejected
  with a concise error and exit status 2.
- A scene must contain at least one section.

### R3. Lifecycle

- Every sidecar starts before the server.
- Every sidecar must stay alive for `FRPC_READY_TIMEOUT` seconds before the
  server starts.
- A failed sidecar leaves the session available for inspection and prevents
  the server from starting.
- `server = true` creates the server window and starts it last.
- `server = false` creates no server window and no deferred server
  placeholder when used directly.
- `--defer-server` remains an internal composition switch for the shared-TCP
  scene and creates the placeholder the composer needs.
- `down` stops a running server when one exists and otherwise tears down the
  sidecar-only session without sending `stop`.
- Existing `--config` scenes keep their current lifecycle and window naming.

### R4. Multiple Java/signalling entries

- A scene may declare multiple TCP sections, each with its own binary and
  config.
- All TCP sections may point at the same HAProxy mux port. They may come from
  different providers or accounts.
- Each such TCP entry is both a Java entry and a signalling entry when the
  mux forwards HTTP/TLS to Geyser and Geyser runs `builtin` or `hybrid`
  signalling.
- The scene must not assume that a TCP entry is Java-only or
  signalling-only; the mux's protocol classification owns that decision.
- The UDP section is independent of the number of TCP sections.

### R5. Shared-TCP composition

`scripts/scenes/frpc-shared-tcp.sh up --scene FILE` must be able to start a
manifest-provided sidecar set, add the HAProxy mux, and start the server only
after both the sidecars and the mux are ready.

The shared-TCP wrapper remains responsible for HAProxy and for the final
server start. It must not require a command-line `--no-server` switch.

### R6. Backward compatibility

- `frpc.sh up --config ...` keeps its current behavior, output shape, window
  names, and error handling.
- `frpc.sh down/status/attach` and `frpc-shared-tcp.sh`'s existing options
  continue to work.
- No core `start.*`, `backup.*`, or verifier script depends on a scene.

### R7. Examples and documentation

- Tracked examples live under `examples/scenes/`.
- Examples demonstrate:
  - one standalone official-frpc UDP sidecar;
  - several TCP entries plus one UDP process;
  - per-section binary selection.
- Example configs use placeholders only. They never contain real tokens,
  account names, public IP addresses, provider domains, certificates, or
  private keys.
- `docs/ASP-SOP.md` explains the manifest, the mixed-binary reason, the
  Java-plus-signalling role of each TCP entry, and the official-frpc UDP
  requirement.

### R8. Diagnostic probe

The existing UDP PROXY v2 probe may remain as an optional operator diagnostic
under `scripts/`. It is not a runtime dependency of any scene and is not
invoked by `start.*` or `backup.*`.

## Acceptance criteria

- A temporary scene with two TCP sections and one UDP section produces three
  sidecar windows, each using the binary named in its section.
- Relative paths in a scene resolve against the scene file directory even
  when the command is run from the repository root.
- A scene with `server = false` creates no `server` window and no deferred
  placeholder.
- A scene with `server = true` starts every sidecar first and starts the
  server only after the readiness check.
- `--scene` rejects duplicate sections, duplicate keys, unknown keys, missing
  required values, and missing config files before creating a tmux session.
- The existing `tests/test_frpc_scene_configs.py` and
  `tests/test_frpc_scene_spawn.py` continue to pass unchanged.
- A shared-TCP dry run with `--scene` emits the sidecar commands, HAProxy
  configuration, and the server-last ordering.
- The tracked examples contain no secret-shaped values and are described by
  an `examples/scenes/README.md`.
- `python -B -m unittest discover -s tests -v` passes.

## Non-goals

- Do not add a daemon, systemd unit, Windows service wrapper, or `frps`.
- Do not parse frpc TOML/YAML/JSON or rewrite provider configuration.
- Do not move provider configs, certificates, tokens, or binaries into Git.
- Do not make core ASP startup, backup, or runtime verification depend on
  tmux, frpc, HAProxy, or a scene.
- Do not create a separate wrapper for each provider or tunnel.
- Do not auto-sync NATFRP certificates from this scene; that remains the
  separate certificate workflow.
