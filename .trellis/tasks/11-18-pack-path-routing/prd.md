# Route resource packs through the plaintext HTTP branch

## Goal

Java clients download resource packs from a URL that `PackManagerPro` sends
them. Today it is `http://127.0.0.1:8000/pack-a.zip`, which only a client on
the server host can reach. The public entry is one TCP port shared by Java,
Bedrock signalling, and plaintext HTTP; there is no second public port.

Serve `http://<public-ip>:<port>/packs/<file>` from that same entry by routing
the plaintext `GET` to the local pack server, and leave every existing branch
byte-identical.

## Requirements

- R1. New `--packs HOST:PORT`; `MUX_PACKS_PREFIX` defaults to `/packs/`.
- R2. The route is a payload ACL on `mc_shared`: `GET <prefix>` at offset 0.
  It must be evaluated before `use_backend geyser_signaling if is_tls or
  is_http`, because the same request also matches `is_http`.
- R3. No TLS, no certificate, no name requirement: the request is plaintext
  from the client's first byte.
- R4. With the option absent, `print_haproxy_config` output is byte-identical
  to HEAD, including ACL order and the TLS termination block.
- R5. The TLS branch (`geyser_tls`, `geyser_tls_termination`), the plaintext
  Geyser branch, and the Java backend are unchanged when the option is on.
- R6. Refuse with exit 2: malformed endpoint, port collision with
  `--listen`/`--java`/`--bedrock`/`--tls-listen`/`MUX_LAN_JAVA`, malformed
  prefix, or a hand-written `--haproxy-config`.
- R7. Document that the match is a single `GET` at offset 0 on a fresh
  connection. The decision is frozen when the existing 4-byte `is_http` accept
  fires, so a client that has sent fewer than N bytes by that instant falls
  through to Geyser; keep-alive reuse and h2c fall through too.
- R8. Document the operator step: `scripts/serve-packs.*` must be running and
  `PackManagerPro` must use `http://<public-ip>:<port>/packs/pack-a.zip`.

## Acceptance Criteria

- [ ] Enabled dry-run shows `acl is_packs payload(0,N) -m beg "GET /packs/"`,
      `use_backend packs if is_packs` before the Geyser line, and a tcp-mode
      `backend packs` pointing at the endpoint.
- [ ] `mc_shared` stays `mode tcp`; no `mode http` appears anywhere new.
- [ ] Disabled output is identical to HEAD with and without `--tls-cert`.
- [ ] Refusals exit 2 and name the offending value.
- [ ] `haproxy -c -f` accepts the enabled config.
- [ ] `curl http://<ip>:<port>/packs/pack-a.zip` returns the file; sha256
      matches `72cafcfa...28bb`.

## Notes

- The pack is public content; the client verifies it against the SHA-1 in the
  pack metadata.
- Content-hash file naming and cache headers are out of scope.
