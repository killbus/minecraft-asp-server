# Example frpc scenes

These files document the optional `scripts/scenes/frpc.sh --scene` manifest
and the frpc configuration shapes it pairs with. They are **examples, not
deployment assets**:

- every path points at a made-up operator directory;
- every credential and account field is a placeholder, and the example host
  names and ports are illustrative values marked for replacement
  (`frp.example.net`, `203.0.113.10` from the documentation range);
- the configs they name do not exist here, so the examples are not meant to
  run as they stand.

Copy one outside the repository into the operator's own directory (for
example `~/asp-frpcs/`), replace the placeholders with real values, and keep
the result there. Nothing under this directory is read by `start.*`,
`backup.*` or the runtime verifier.

## One section is one process

A manifest section is one frpc process, one configuration and one tmux
window named `frpc-<section>`:

```ini
[udp]
binary = /home/operator/asp-frpcs/bin/frpc
config = /home/operator/asp-frpcs/official-frpc-udp.toml
```

Several tunnels that one frpc process serves belong in one configuration as
several `[[proxies]]`, and therefore in one section. Several processes - a
provider fork for the TCP entries and the official client for the UDP media
tunnel, or one entry per provider account - are several sections. They may
name different `binary` values.

`session` and `server` are required. `server = false` means the scene owns no
server: the first sidecar is the session's initial window. `server = true`
means the server window starts last, after every sidecar has stayed alive for
`FRPC_READY_TIMEOUT` seconds.

## A TCP entry is Java and signalling

Each TCP entry points `localPort` at the shared mux in
`scripts/scenes/frpc-shared-tcp.sh`. The mux classifies the stream: a TLS
ClientHello or an HTTP request goes to Geyser's built-in signalling listener,
and Java goes to the server. The same public port therefore serves both, and
a section has no `role` key - the mux owns that decision.

The UDP section is the NetherNet media plane. It is independent of how many
TCP entries exist, and it must name the official frpc binary: it is the
client that was verified to forward UDP PROXY protocol v2.

## The files

| File | Shows |
| --- | --- |
| `asp-frpc-udp.scene.example` | one official-frpc UDP sidecar, no server window |
| `asp-frpc-shared.scene.example` | two TCP entries and one UDP process behind the shared mux |
| `frpc/official-frpc-udp.toml.example` | UDP proxy with PROXY protocol v2 |
| `frpc/sakura-frpc-entry.toml.example` | one provider-fork TCP entry pointing at the mux |

Never put a token, account identifier, public address or certificate in this
directory. The operator's configuration and certificate files belong outside
the repository.
