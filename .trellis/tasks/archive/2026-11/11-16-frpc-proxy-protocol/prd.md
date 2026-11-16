# frpc shared-port mux: opt-in PROXY protocol for the real client IP

## Goal

Let scripts/scenes/frpc-shared-tcp.sh emit an opt-in PROXY-protocol chain so Paper sees Java players' real public IP instead of 127.0.0.1, without breaking the plain (non-PROXY) mode and without breaking local tooling.

## Requirements

- R1 The shared-port scene gains an opt-in switch (default **off**) that makes
  the generated HAProxy configuration accept PROXY protocol on the shared
  listen port and hand it to the Java backend.
- R2 With the switch off the generated configuration is unchanged
  byte-for-byte, so existing hosts and the four mux tests keep behaving as before.
- R3 The switch is validated like the other endpoints (`--listen`, `--java`,
  `--bedrock`, `--tls-*`): misuse is refused before anything is started.
- R4 The local diagnostic path stays usable - `scripts/probe_public_entry.py`
  can speak PROXY v2 for its `--local-mux` checks, covered by its tests.
- R5 `docs/ASP-SOP.md` 10.1 documents the whole chain (frpc setting, scene
  switch, Paper `proxies.proxy-protocol`, Geyser
  `advanced.java.use-haproxy-protocol`), the acceptance line and the rollback.
- R6 Start order, lifetime and reload behaviour of the scene do not change.

## Acceptance Criteria

- [ ] `tests/test_frpc_shared_tcp_scene.py` proves R1, R2 and R3.
- [ ] `tests/smoke_frpc_shared_tcp_tls.py` passes with PROXY v2 headers on the
      shared port (real HAProxy, real sockets) and still passes in plain mode.
- [ ] `tests/test_probe_public_entry.py` covers R4.
- [ ] `python -m unittest discover -s tests` is green.
- [ ] SOP 10.1 lists every switch and the line to check on the server.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Evidence for the mechanism (natfrp's own best-practice page, read with
  opencli profile `fx2wmxgs`) is in `research/natfrp-realip.md`.
- Non-goals: Bedrock/NetherNet real IP
  (`advanced.bedrock.webrtc-proxy-protocol-relays`), signalling whitelists,
  enabling LoginTo sessions, and touching the live host's `~/asp-frpcs`.
