# Journal - killbus (Part 1)

> AI development session journal
> Started: 2026-10-16

---



## Session 1: Optional frpc tmux helper
<!-- trellis-session: v=2 fp=1640712d42f8ba23 -->

**Date**: 2026-11-13
**Task**: Optional frpc tmux helper
**Branch**: `main`

### Summary

Added optional scripts/scenes/frpc.sh for server + N frpc windows in tmux; documented it as non-core; fixed exec bits on shell entry points.

### Git Commits

| Hash | Message |
|------|---------|
| `ff9f677` | feat(scripts): add optional frpc tmux session helper |
| `5af0a8f` | chore(scripts): mark shell entry points executable |

### Status

[OK] **Completed**


## Session 2: NetherNet/Terracotta root cause and SOP 4.2
<!-- trellis-session: v=2 fp=ff4398e5bb2516f3 -->

**Date**: 2026-11-14
**Task**: NetherNet/Terracotta root cause and SOP 4.2
**Branch**: `main`

### Summary

Bedrock Terracotta traced to NetherNet signalling, not frp/ports: the advertised address must be a numeric public IP, and a stale plugins/Geyser-Spigot/nethernet identity makes registration fail with a non-retryable Warden 500. Corrected the SOP acceptance gate and documented both failure modes.

### Main Changes

- docs/ASP-SOP.md: new 4.2 entry-point/troubleshooting section, rewritten section 5 Bedrock acceptance items, Geyser rows in 4/9 and a section 7 pointer
- local reproduction: advertise-addresses as <udp-node-host>:<udp-port> gave 'Advertised address 198.18.103.7 is special purpose, no player can reach it'; the same entry as <udp-node-ip>:<udp-port> registered and printed https://<assigned>.wdn.gg
- live Warden NXS probes: anonymous register, recovery register, PoW complete and a java.net.http client all returned 201, so the reported 500 was persisted-state related rather than an outage

### Git Commits

| Hash | Message |
|------|---------|
| `fda2c49` | docs(sop): correct Bedrock/NetherNet acceptance and add 4.2 |

### Testing

- [OK] python -B scripts/verify_runtime.py: all artifacts OK
- [OK] python -B -m unittest discover -s tests -v: 37 passed
- [OK] ASP boot with the numeric advertised address: NetherNet registered with Warden, clean stop

### Status

[OK] **Completed**

### Next Steps

- Linux deployment: keep advertise-addresses numeric, keep nethernet/ persistent, hand players the wdn.gg:443 address
- On a repeat 500: stop, mv nethernet nethernet.bak.<ts>, restart, confirm the registration line


## Session 3: Opt-in PROXY protocol v2 on the frpc shared-port mux
<!-- trellis-session: v=2 fp=d5770001bc42edcc -->

**Date**: 2026-11-16
**Task**: Opt-in PROXY protocol v2 on the frpc shared-port mux
**Branch**: `rewrite/main-20261115`

### Summary

Shipped the opt-in PROXY-protocol chain for the shared-port mux: --proxy-protocol on scripts/scenes/frpc-shared-tcp.sh (accept-proxy on the shared bind, send-proxy-v2 to Paper, default output byte-identical), probe and smoke test speak the header, SOP 10.1.1 records the four switches and the rollback. Verified on the host (smoke test plain + PROXY, live login line with the real public IP) and locally (139 tests, 10 pre-existing skips). Also silenced the smoke harness client-reset tracebacks and rescoped LoginTo's disabled sessions to the mux mode. Bedrock real IP stays a non-goal: a same-LAN client showed the WebRTC ICE address 10.1.1.120:0, which the UDP tunnel PROXY switch would not change.

### Git Commits

| Hash | Message |
|------|---------|
| `f2f2530` | docs(sop): document LoginTo's offline Java accounts |
| `f38b748` | feat(scripts): let the shared-port mux speak PROXY protocol |
| `1121dd1` | fix(tests): stop the smoke harness printing client resets |
| `245ca88` | docs(sop): scope LoginTo's disabled sessions to the mux mode |

### Status

[OK] **Completed**
