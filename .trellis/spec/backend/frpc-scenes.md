# frpc Scenes

> Executable contract for the optional Linux frpc/tmux composition layer.

---

## Scenario: Declarative frpc process composition

### 1. Scope / Trigger

This spec applies when changing:

- `scripts/scenes/frpc.sh`
- `scripts/scenes/frpc-shared-tcp.sh`
- scene manifests, examples, or tests
- operator documentation for frpc/HAProxy/tmux composition

It is triggered because the scene adds a command signature, a file-format
contract, environment precedence, lifecycle ordering, and a secrets boundary.

The scene is optional. `start.*`, `backup.*`, and runtime verification must
never depend on it. Deleting the scene scripts must leave core ASP behavior
unchanged.

### 2. Signatures

Legacy mode:

```sh
scripts/scenes/frpc.sh up --config <dir|file> \
    [--config <dir|file>]... [--no-attach] [--defer-server] [--dry-run]
```

Manifest mode:

```sh
scripts/scenes/frpc.sh up --scene <file> \
    [--no-attach] [--defer-server] [--dry-run]
```

Shared-TCP composition:

```sh
scripts/scenes/frpc-shared-tcp.sh up --config <dir|file> ...
scripts/scenes/frpc-shared-tcp.sh up --scene <file> ...
scripts/scenes/frpc-shared-tcp.sh up --scene <file> --proxy-protocol
```

`--config` and `--scene` are mutually exclusive in both scripts.

Other verbs remain unchanged:

```sh
scripts/scenes/frpc.sh down
scripts/scenes/frpc.sh status
scripts/scenes/frpc.sh attach
scripts/scenes/frpc-shared-tcp.sh reload
scripts/scenes/frpc-shared-tcp.sh down
scripts/scenes/frpc-shared-tcp.sh status
scripts/scenes/frpc-shared-tcp.sh attach
```

The read/stop verbs do not accept a scene file. A non-default scene session is
addressed with `FRPC_SESSION`.

`--proxy-protocol` also emits the default LAN Java frontend. It uses
`MUX_LAN_JAVA=0.0.0.0:25564` and adds:

```haproxy
frontend lan_java
    bind 0.0.0.0:25564
    default_backend java
```

The frontend accepts an ordinary LAN Java connection; the shared `java`
backend carries `send-proxy-v2`, so Paper still sees a PROXY v2 header. The
frontend is emitted only for the generated configuration. A hand-written
`--haproxy-config` owns the whole file and must add the frontend itself.

### 3. Contracts

#### Manifest grammar

The manifest is INI-like text, not TOML/YAML/JSON/shell:

```ini
session = asp-frpc
server = false

[udp]
binary = /root/asp-frpcs/bin/frpc
config = /root/asp-frpcs/official-udp.toml
```

Top-level keys:

| Key | Required | Contract |
| --- | --- | --- |
| `session` | yes | tmux session name; letters, digits, `_`, `-` |
| `server` | yes | exactly `true` or `false` |

Section keys:

| Key | Required | Contract |
| --- | --- | --- |
| `binary` | yes once | executable path, relative path, or bare command |
| `config` | yes once | readable regular file |

Section names use letters, digits, `_`, `-`. One section is exactly one frpc
process, one configuration, and one tmux window named
`frpc-<section>`.

Several tunnels owned by one frpc process are several `[[proxies]]` in one
configuration and therefore one section. Different accounts, provider
addresses, or binaries are different sections.

#### Parsing and path rules

- The manifest is read, never sourced or evaluated.
- Blank lines and whole-line `#` comments are ignored.
- Inline comments are not interpreted; `#` is part of a value.
- Values are split from keys at the first `=`.
- Control characters in values are rejected because records are
  tab-delimited internally.
- Relative path values resolve against the scene file's directory.
- Absolute paths stay absolute.
- A bare `binary` is resolved on `PATH` at start time.
- A bare `config` is still a file next to the scene.
- `--dry-run` parses and resolves config paths but does not require a bare
  binary to be installed.

#### Environment precedence

| Variable | Contract |
| --- | --- |
| `FRPC_SESSION` | overrides scene `session`; also addresses down/status/attach |
| `FRPC` | single binary for legacy `--config` mode only |
| `FRPC_READY_TIMEOUT` | seconds all sidecars must stay alive |
| `FRPC_STOP_TIMEOUT` | seconds the server gets to stop |
| `FRPC_PANEL_LOCALE` | UTF-8 locale for tmux panes |

Manifest mode uses each section's `binary`, never the global `FRPC`.

#### Lifecycle

`server = true`:

1. Create the session with a `server` placeholder.
2. Start every sidecar window.
3. Require every sidecar to remain alive for `FRPC_READY_TIMEOUT`.
4. Start the server last with `bash scripts/start.sh`.

`server = false`:

1. Make the first sidecar the session's initial window.
2. Start the remaining sidecars.
3. Require every sidecar to remain alive.
4. Leave the session running with no server window and no deferred server
   placeholder.

`--defer-server` is an internal composition switch: it reserves the server
placeholder even when the manifest says `server = false`. This is what
`frpc-shared-tcp.sh` uses before it starts HAProxy and then the server.

`frpc-shared-tcp.sh` ordering is always:

```text
all frpc sidecars -> HAProxy binds -> server starts
```

#### Transport roles

- A TCP section points at the HAProxy mux, normally
  `127.0.0.1:25566`.
- The same TCP entry is both a Java entry and a NetherNet built-in-signalling
  entry when the mux forwards Java to Paper and HTTP/TLS to Geyser and Geyser
  runs `builtin` or `hybrid`.
- The UDP section is the NetherNet media plane to Geyser `19132`.
- Official frpc is the verified carrier for UDP PROXY protocol v2.
- Sakura/provider frpc remains appropriate for TCP entries that depend on
  provider `auto_https` and provider-issued certificates.

#### Secrets and repository boundary

- Real frpc configs, binaries, tokens, account identifiers, certificates,
  private keys, public addresses, and provider-bound names live outside the
  repository.
- `examples/scenes/` contains placeholders only and is not a deployment
  asset.
- `docs/ASP-SOP.md` is the operator-facing source of truth. Task research is
  evidence, not normative documentation.

### 4. Validation & Error Matrix

| Condition | Result |
| --- | --- |
| missing `--config` and `--scene` | exit 2 |
| `--scene` and `--config` together | exit 2, mutually exclusive |
| duplicate scene path option | exit 2 |
| invalid `MUX_LAN_JAVA` in generated PROXY mode | exit 2 |
| `MUX_LAN_JAVA` collides with another bind | exit 2 |
| missing/unreadable scene file | exit 2 |
| missing `session` or `server` | exit 2 |
| invalid `server` value | exit 2 |
| invalid session/section name | exit 2 |
| duplicate section/key | exit 2 |
| unknown top-level/section key | exit 2 |
| malformed line or empty key/value | exit 2 |
| control character in value | exit 2 |
| missing/unreadable config | exit 2 before tmux |
| missing/non-executable binary | exit 2 before tmux |
| no sections | exit 2 |
| sidecar exits during readiness | exit 1; session retained for inspection; server not started |
| shared wrapper receives parser exit 2 | must preserve exit 2, not collapse to 1 |
| shared wrapper has an existing session/mux conflict | exit 3 |

### 5. Good/Base/Bad Cases

Good:

```ini
session = asp-frpc-shared
server = true

[entry_account_a]
binary = /root/asp-frpcs/bin/provider-frpc
config = /root/asp-frpcs/entry-a.toml

[entry_account_b]
binary = /root/asp-frpcs/bin/provider-frpc
config = /root/asp-frpcs/entry-b.toml

[udp]
binary = /root/asp-frpcs/bin/frpc
config = /root/asp-frpcs/official-udp.toml
```

Base:

```ini
session = asp-frpc
server = false

[udp]
binary = frpc
config = udp.toml
```

Bad:

```ini
session = asp-frpc
server = false

[udp]
binary = frpc
binary = /other/frpc
config = udp.toml
```

### 6. Tests Required

`tests/test_frpc_scene_manifest.py` must assert:

- per-section binary/config selection;
- scene-relative path resolution from different caller directories;
- bare binary and bare config behavior;
- server-less lifecycle and no deferred placeholder;
- server-last ordering;
- dead sidecar prevents server start;
- duplicate/unknown/malformed keys and sections;
- CRLF and control-character handling;
- missing binary/config rejection before tmux;
- `FRPC_SESSION` precedence;
- down without a server window kills the session without `send-keys`;
- legacy `--config` output remains unchanged.

`tests/test_frpc_shared_tcp_scene.py` must assert:

- `--scene`/`--config` mutual exclusion;
- multiple sidecars start before the mux and server;
- a manifest parser error keeps exit 2 through the wrapper.
- `--proxy-protocol` adds the LAN frontend by default, and its traffic
  reaches the `send-proxy-v2` backend;
- `MUX_LAN_JAVA` can override the bind and is rejected when malformed or
  when it collides with another endpoint;
- a hand-written config keeps ownership of its whole file.

`tests/test_probe_public_udp.py` must assert PROXY v2 parsing, including that
`LOCAL` ignores populated address fields. The probe is diagnostic only and
must not become a runtime dependency.

### 7. Wrong vs Correct

#### Wrong: infer record shape from whether a tab appears

```sh
# A legal legacy path containing a tab would be misread as a binary field.
if [ "${rest#*"$TAB"}" != "$rest" ]; then
    binary=...
fi
```

#### Correct: make the mode explicit

```sh
if [ "${_records_have_binary:-0}" -eq 1 ]; then
    _line_binary=${_dr_rest%%"$TAB"*}
    _line_config=${_dr_rest#*"$TAB"}
else
    _line_binary=
    _line_config=$_dr_rest
fi
```

#### Wrong: use one frpc binary for every selected config

```sh
FRPC=/path/to/provider-frpc frpc.sh up --config ~/asp-frpcs
```

#### Correct: declare the process owner explicitly

```ini
[entry]
binary = /root/asp-frpcs/bin/provider-frpc
config = /root/asp-frpcs/entry.toml

[udp]
binary = /root/asp-frpcs/bin/frpc
config = /root/asp-frpcs/official-udp.toml
```
