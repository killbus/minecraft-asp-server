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


## Session 4: Bedrock media relay: SOP subsection 10.1.2
<!-- trellis-session: v=2 fp=cea156e8fd9f6ba3 -->

**Date**: 2026-11-16
**Task**: Bedrock media relay: SOP subsection 10.1.2
**Branch**: `rewrite/main-20261115`

### Summary

Closed the Bedrock-real-IP task: research proved the reported address is the selected ICE media path (port 0 is Geyser's own literal), and the operator-side relay chain is now documented in the SOP instead of left in chat.

### Main Changes

- docs/ASP-SOP.md: new subsection 10.1.2 forcing Bedrock media through the frpc UDP relay (proxy_protocol_version = v2, advertise-addresses, webrtc-proxy-protocol-relays, webrtc-port: 0), plus cross-refs in 4.2 and the 10.1 frpc example comment.
- docs/ASP-SOP.md: 10.1.1 and 10.1.2 moved to the end of 10.1 so the section tail (dry-run, smoke test, probe, auto_https, plain_website_check) reads as 10.1 body again; pure move, line multiset unchanged.
- Deployment specifics genericized in the new text: no concrete player name, LAN address or provider host name.

### Git Commits

| Hash | Message |
|------|---------|
| `30d56d4` | docs(bedrock): research the NetherNet player address and its switches |
| `acfdb66` | docs(sop): document the Bedrock media relay chain |
| `e1b1179` | chore(task): archive 11-16-bedrock-real-ip |

### Testing

- [OK] python .trellis/scripts/task.py validate .trellis/tasks/11-16-bedrock-real-ip (4 implement + 3 check entries; only the pre-existing SOP size warning)
- [OK] trellis-check sub-agent on the docs diff: heading order, byte-identical relocation of 10.1.1, claim-by-claim traceability to the research files, ASCII/trailing whitespace/newline, scope - no blocking findings
- [OK] git diff --check -- docs/ASP-SOP.md clean

### Status

[OK] **Completed**

### Next Steps

- Host acceptance not yet run: set proxy_protocol_version = v2 on the UDP tunnel, point advertise-addresses at the frp node's numeric public IP and list it in webrtc-proxy-protocol-relays, then confirm the Bedrock login line shows the public address.
- Open question from the task: Geyser config.yml auth-type (online vs offline + Floodgate).


## Session 5: SOP: advertise-addresses may be a host name
<!-- trellis-session: v=2 fp=93884d6a19eda89a -->

**Date**: 2026-11-16
**Task**: SOP: advertise-addresses may be a host name
**Branch**: `rewrite/main-20261115`

### Summary

Recorded the operator decision to write bedrock.signaling.advertise-addresses as a host name, and replaced the earlier 'numeric only' rule with what the code actually does: the name is resolved here at signalling start and every resolved address must pass the usable-address check.

### Main Changes

- docs/ASP-SOP.md: 4.2 now states the rule (numeric or host name; this deployment uses the name), the fake-IP refusal, and the Advertised address ... resolves to ... log line as the value actually advertised.
- docs/ASP-SOP.md: section 5 acceptance item, the section 7 pointer, the 10.1 mapping example, the 10.1.2 settings table and its closing note no longer say numeric only.
- docs/ASP-SOP.md: 10.1.2 notes that webrtc-proxy-protocol-relays resolves names the same way (TrustedProxies.parse -> IpRangeSet.parse -> InetAddress.getAllByName), so both fields depend on this machine's resolver.

### Git Commits

| Hash | Message |
|------|---------|
| `9c8c3ba` | docs(sop): record the host-name advertise-address policy |

### Testing

- [OK] AdvertisedAddresses / TrustedProxies / IpRangeSet disassembled from server/plugins/Geyser-Spigot.jar to confirm the resolve-then-validate path and name handling
- [OK] docs/ASP-SOP.md ASCII, no trailing whitespace, no CR, body lines within the file's wrap

### Status

[OK] **Completed**

### Next Steps

- server/plugins/Geyser-Spigot/config.yml:54-56 still carries the local never-a-host-name NOTE and is not in the repo; decide whether to rewrite it here or on the host.
- Host acceptance of the relay chain is still outstanding (UDP tunnel proxy_protocol_version = v2, webrtc-proxy-protocol-relays, then check the Bedrock login line).


## Session 6: Declarative mixed frpc scenes
<!-- trellis-session: v=2 fp=89da2236fc90968a -->

**Date**: 2026-11-17
**Task**: Declarative mixed frpc scenes
**Branch**: `rewrite/main-20261115`

### Summary

Added per-process frpc scene manifests, official-frpc UDP PROXY v2 support, shared-TCP composition, examples, diagnostics, and SOP contracts.

### Main Changes

- frpc.sh --scene: one binary/config per section and a server-less lifecycle
- frpc-shared-tcp.sh --scene: sidecars, then HAProxy, then the server
- Documented the real-address chain and the LAN 25565 implication

### Git Commits

| Hash | Message |
|------|---------|
| `757c451` | feat(scenes): add declarative mixed frpc manifests |

### Testing

- [OK] python -B -m unittest tests.test_frpc_scene_manifest tests.test_frpc_shared_tcp_scene tests.test_probe_public_udp -v (73 passed)

### Status

[OK] **Completed**

### Next Steps

- Use the operator-owned scene for two TCP entries plus the official frpc UDP tunnel


## Session 7: LAN Java entry under shared-TCP PROXY mode
<!-- trellis-session: v=2 fp=f8125a2f3a3fcb36 -->

**Date**: 2026-11-17
**Task**: LAN Java entry under shared-TCP PROXY mode
**Branch**: `rewrite/main-20261115`

### Summary

Added an automatic plain Java frontend on 0.0.0.0:25564 when frpc-shared-tcp runs with --proxy-protocol; HAProxy injects PROXY v2 so Paper sees the LAN client address. Covered endpoint validation, hand-written-config ownership, and 32 scene tests. Disabled Geyser debug-mode in the local runtime config.

### Git Commits

| Hash | Message |
|------|---------|
| `d499458` | feat(scenes): add LAN Java frontend in PROXY mode |

### Status

[OK] **Completed**


## Session 8: Certificate expiry observability for shared TCP
<!-- trellis-session: v=2 fp=354ce9b115240914 -->

**Date**: 2026-11-17
**Task**: Certificate expiry observability for shared TCP
**Branch**: `rewrite/main-20261115`

### Summary

frpc-shared-tcp now reports each --tls-cert subject, SANs, notAfter, remaining days, and warnings for expired/not-yet-valid or expiring certificates; MUX_CERT_WARN_DAYS defaults to 7 to match the natfrp renewal window. up writes a MUX_CERT_STATE inventory after the mux is listening, status reports it, and down removes it. Renewal/download remain outside the scene. Added tests for warning/non-blocking behavior, status inventory, up/down lifecycle, and invalid threshold input; 79 tests passed with 10 platform skips.

### Git Commits

| Hash | Message |
|------|---------|
| `7512374` | feat(scenes): report certificate expiry from shared TCP |

### Status

[OK] **Completed**


## Session 10: Port deployment tooling to native single-world startup
<!-- trellis-session: v=2 fp=4cdbf1453eca5a29 -->

**Date**: 2026-11-20
**Task**: Port deployment tooling to native single-world startup
**Branch**: `feat/single-world-start`

### Summary

Adapt later deployment commits on feat/single-world-start. Native packs, protected saves, complete snapshots and world forwarding retain main transport behavior. Main and frozen integration remain unchanged.

### Git Commits

| Hash | Message |
|------|---------|
| `36046e9` | feat(scripts): restore commit subject boundary checks |
| `7307c99` | feat(server): restore deployment tooling for native world selection |

### Testing

- [OK] 307 runnable tests pass across full discovery and affected-module rerun; 10 platform checks skipped. No real server deployment.

### Status

[OK] **Completed**

### Next Steps

- Operator tests the published branch on a stopped deployment using SINGLE-WORLD-SOP.
