# SOP: NetherNet acceptance and troubleshooting wording

## Goal

Correct the outdated Bedrock acceptance item in docs/ASP-SOP.md and record the verified NetherNet/Geyser/Warden failure modes (fake-IP resolution, stale provider identity) as an operational troubleshooting entry.

## Requirements

- R1 §5 acceptance states the real Bedrock entry point (the Warden
  `*.wdn.gg:443` address, or built-in signalling's TCP port) and that
  UDP 19132 is the NetherNet data plane only.
- R2 §5 acceptance requires a numeric public `IP:UDP port` in
  `bedrock.signaling.advertise-addresses` and the boot log line
  `Registered with the external signaling service`.
- R3 New §4.2 records the three verified failure modes with their exact
  log signatures and fixes: fake-IP/polluted host-name resolution
  (`Advertised address <ip> is special purpose, ...`), a half-broken
  persisted provider identity (`Could not register with the external
  signaling service: ... (500 internal_error)`, fixed only by discarding
  `plugins/Geyser-Spigot/nethernet/`), and using the UDP port as the
  client entry point (Terracotta).
- R4 §4.2 states that `plugins/Geyser-Spigot/nethernet/` is instance
  identity rather than cache (survives restarts, travels with the server
  data, `deregister-on-shutdown` for non-persistent directories).
- R5 The Geyser rows in §4 and §9 stop implying "Bedrock = UDP 19132".
- R6 Docs-only change: no runtime, script or config behaviour changes;
  match the document's existing style (short lines, backticked commands
  and log strings, no new dependencies).

## Acceptance Criteria

- [ ] `docs/ASP-SOP.md` no longer presents UDP 19132 as the Bedrock
      entry point anywhere
- [ ] §4.2 exists and quotes both log signatures plus the exact
      state-reset procedure (`mv nethernet nethernet.bak.<ts>`, full
      restart, confirm the registration line)
- [ ] The evidence for both failure modes is traceable: the Windows dev
      box reproduction (host name resolving to `198.18.103.7`), the
      Linux `getent hosts` result, and the successful numeric-IP boot
      are described in the task notes
- [ ] `python -B scripts/verify_runtime.py` and
      `python -B -m unittest discover -s tests -v` still pass
- [ ] Only `docs/ASP-SOP.md` plus `.trellis/` task artifacts changed;
      `server/` untouched

## Notes

- Evidence, 2026-11-14:
  - dev box, `advertise-addresses: "<udp-node-host>:<udp-port>"` (host name,
    fake-IP resolver) -> `Advertised address 198.18.103.7 is special
    purpose, no player can reach it`, signalling never started;
  - dev box, same entry as `<udp-node-ip>:<udp-port>` -> `NXS: IPv4 is
    available for player connections` then `Registered with the external
    signaling service. Players can join at https://<assigned>.wdn.gg`;
  - Linux deployment, host name resolving to the same `<udp-node-ip>`
    (`Advertised address ... resolves to ...`) -> `Could not register
    with the external signaling service: Warden could not process the
    game-server agent request. (500 internal_error)`;
  - after the first successful registration with the numeric IP, the
    same host-name config also worked, so the address value was not the
    variable; the persisted identity was.
  - Warden's live `register` (new service and recovery) and `complete`
    returned 201 from a clean client, so the 500 was not an outage and
    not a protocol/version mismatch (Geyser 2.12.1-b1302 is the current
    build).
- `<udp-node-host>` has a single public A record and no AAAA/CNAME; the
  numeric value is intentionally not written into the repository document
  (free frp endpoints change, and the runtime config is gitignored).

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
