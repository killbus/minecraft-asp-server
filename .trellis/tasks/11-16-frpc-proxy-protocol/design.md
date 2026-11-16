# Design

## Today

```
player -> frpc (tcp proxy, localPort 127.0.0.1:25566)
       -> HAProxy frontend mc_shared  (sniffs ClientHello/HTTP, plain tcp)
       -> backend java              -> Paper 127.0.0.1:25565
```

Every hop is plain TCP, so Paper sees `127.0.0.1`. `generate_haproxy_config` /
`print_haproxy_config` in `scripts/scenes/frpc-shared-tcp.sh` write that
configuration; `MUX_LISTEN` is the shared port and `--java` is the Paper
endpoint.

## Change

One opt-in switch adds PROXY protocol v2 at two points of the generated file:

| Point | Plain (today) | With the switch |
| --- | --- | --- |
| `frontend mc_shared` | `bind 127.0.0.1:25566` | `bind 127.0.0.1:25566 accept-proxy` |
| `backend java` | `server paper 127.0.0.1:25565` | `server paper 127.0.0.1:25565 send-proxy-v2` |

Nothing else moves: the signalling backends keep their plain server lines,
`backend geyser_tls -> frontend geyser_tls_termination` stays HAProxy-to-HAProxy
on loopback, and the TLS/listen validation is untouched.

### Why the mux needs `accept-proxy`, and what that costs

`accept-proxy` is a property of the whole `bind`: every connection to that port
must then start with a PROXY header. In this deployment that is exactly right -
the single frpc tcp proxy that feeds the mux sends the header on every
connection (frpc applies `proxy_protocol_version` per proxy to the local
service it dials), so Java *and* the NetherNet signalling traffic arrive with
one. HAProxy consumes the header before `tcp-request content` runs, so the
existing `is_tls` / `is_http` sniffing still sees the real payload.

The cost is the one natfrp's page warns about: anything that connects to that
port *locally* without a header (our probes, a manual `curl`, the smoke test)
is refused. Two mitigations, both in scope:

- `scripts/probe_public_entry.py --proxy-protocol` prefixes its `--local-mux`
  connections with a v2 header, so the diagnostic tool keeps working.
- the smoke test gains a PROXY variant that sends the header, which is what a
  real client through frpc does.

The scene keeps supporting `--haproxy-config FILE`, so an operator who wants a
plain local port can still write one by hand. No second bind is generated: one
port with one meaning is easier to reason about than a port that is PROXY-only
for frpc and plain for everyone else.

### Consequence on the backend (documented, not coded here)

Once Paper runs with `proxies.proxy-protocol: true`, **every** connection to its
port must carry the header, including Geyser's internal one. Geyser speaks it:
`advanced.java.use-haproxy-protocol: true` in
`plugins/Geyser-Spigot/config.yml`. Both sides must be set together;
`server.properties` already has `prevent-proxy-connections=false` and
`log-ips=true` on both hosts.

The switchover is atomic on our side because the scene already starts frpc
sidecars, then HAProxy, then the server: one `down` + `up` applies frpc +
mux + backend at once.

## Contract

- CLI: `--proxy-protocol` on `scripts/scenes/frpc-shared-tcp.sh`, boolean,
  default off; accepted anywhere the other options are parsed; listed in
  `usage()`.
- No environment variable: the switch belongs to the invocation, like
  `--tls-cert`.
- `scripts/probe_public_entry.py --proxy-protocol` affects only the
  `--local-mux` half (the public half is real traffic; there the header is
  added by frpc, not by the client).

## Verification

| Test | Proves |
| --- | --- |
| `tests/test_frpc_shared_tcp_scene.py` | R1 (both lines), R2 (plain output unchanged), R3 (validation) |
| `tests/smoke_frpc_shared_tcp_tls.py` | real HAProxy accepts the header and still routes Java bytes and HTTP/TLS signalling; plain mode still works |
| `tests/test_probe_public_entry.py` | R4 header construction |
| `python -m unittest discover -s tests` | no regression in the four mux/scene suites |

Live acceptance (operator, on the host): the boot/login line
`<name>[/<real-public-ip>:<port>] logged in with entity id ...` replaces
`[/127.0.0.1:<port>]`.

## Rollback

Drop `--proxy-protocol` from the scene invocation and set Paper's
`proxies.proxy-protocol` back to `false` (and Geyser's
`use-haproxy-protocol` to `false`). The generated config then matches today's
byte-for-byte, which is what R2 keeps testable.
