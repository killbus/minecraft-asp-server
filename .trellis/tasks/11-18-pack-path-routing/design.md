# Design: packs on the plaintext HTTP branch

## Current shape

```
frps -> frpc tcp -> 127.0.0.1:25566   frontend mc_shared (mode tcp)
     is_tls   -> backend geyser_tls -> 127.0.0.1:25567 (ssl termination)
     is_http  -> backend geyser_signaling -> 127.0.0.1:19132
     is_java  -> backend java             -> 127.0.0.1:25565
```

The client fetches a pack as `http://<public-ip>:<port>/packs/<file>`. That
request is plaintext from the first byte, so it already matches the existing
`is_http` ACL on `mc_shared`. No TLS termination is involved, and no name or
certificate is needed.

## Decision

Add one payload ACL on `mc_shared` and one tcp backend:

```haproxy
frontend mc_shared
    ...
    acl is_packs payload(0,11) -m beg "GET /packs/"
    use_backend packs if is_packs
    use_backend geyser_signaling if is_tls or is_http
```

```haproxy
backend packs
    server packs 127.0.0.1:8000
```

Everything else — the TLS branch, the plaintext Geyser branch, Java, the
`--tls-cert` wiring — stays byte-identical.

The prefix is `MUX_PACKS_PREFIX` (default `/packs/`); the ACL's offset/length
are derived from `"GET " + prefix`, so a custom prefix cannot silently match
the wrong bytes.

The backend receives the request path unchanged, so `scripts/serve_packs.py`
serves `server/packs/` under that same prefix. `python -m http.server
--directory server/packs` would look for `server/packs/packs/<file>` and
answer 404.

## Why the payload match is sound here

- A resource-pack fetch is one `GET` on a fresh connection, at offset 0, in
  HTTP/1.1 origin form. That is exactly the case `payload(0,n) -m beg` covers.
- The routing decision is frozen when `tcp-request content accept if is_http`
  matches. That rule needs four bytes, while `is_packs` needs `4 + len(prefix)`.
  A client that has written only `GET ` at that instant is therefore routed to
  Geyser. Minecraft's HTTP client writes the request head in one buffer, so the
  first segment carries the whole request line; the split case is a documented
  limitation, not the expected path.
- A Java handshake cannot produce `GET /packs/` at offset 0, so the ACL cannot
  steal a player connection.
- A TLS ClientHello is classified `is_tls` and never reaches this ACL.
- Keep-alive reuse (a second request later in the stream) and h2c prefaces do
  not match; they fall through to Geyser exactly as today. PackManagerPro opens
  a new connection per download, so this is not on the supported path.

## Why not the HTTPS variant

Terminating TLS and switching `geyser_tls_termination` to `mode http` would
change the production Bedrock branch for every player. The plaintext design
leaves that branch untouched and needs no certificate, no bound name, and no
SNI handling.

## Failure behaviour

| Condition | Result |
| --- | --- |
| packs backend down | `/packs/*` gets 503; Java and Bedrock are unaffected |
| prefix typo | request falls through to Geyser (404/426) |
| pack file missing | `python -m http.server` answers 404 |
| client insists on HTTPS | the ClientHello takes the existing TLS branch |

## Integrity

The pack is public content and travels in clear text. Minecraft verifies the
pack against the SHA-1 declared in the pack metadata, so a modified file is
rejected by the client rather than executed.

## Option contract

| Input | Meaning |
| --- | --- |
| `--packs HOST:PORT` | enable the route and name the backend |
| `MUX_PACKS_PREFIX` | path prefix, default `/packs/` |

Prefix validation:

- starts and ends with `/`;
- characters limited to `A-Za-z0-9._~/-`;
- no `//` and no `..`;
- not `/` (that would swallow every plaintext HTTP request).

## Verification

1. `--dry-run` in both modes; disabled output diffed against HEAD.
2. Enabled config checked with `haproxy -c -f`.
3. On the deployed host: `curl http://127.0.0.1:<mux>/packs/pack-a.zip` and the
   public `http://<ip>:<port>/packs/pack-a.zip`; compare sha256.
