# Bedrock/NetherNet real client address behind the relay

## Goal

Find out whether a Bedrock player's own address can reach the Java
backend in this deployment, and if so which switch carries it.

Trigger: a Bedrock player on the server's own LAN, connecting through
the public entry `4-mc.r93085394.nyat.app`, logged in as
`.Dalvek[/10.1.1.120:0]` - a private address with port 0, so neither
the player's public address nor the relay's loopback address.

## Requirements

- R1 Establish where that address comes from: which Geyser/NetherNet
  code path sets the address Geyser hands the Java backend for a
  NetherNet player, and why the port is 0.
- R2 Establish what each candidate switch reports in this topology:
  signalling over the natfrp TCP tunnel and the HAProxy mux, the media
  plane over the separate frpc UDP tunnel, with clients that may sit on
  the server's own LAN.
- R3 Record what each switch requires and what it costs, including any
  path it closes - the Geyser config states some are mutually
  exclusive.
- R4 No runtime, provider or repository config changes until the design
  is agreed. This task decides nothing on its own.

## Research questions

- Q1 Provenance of `10.1.1.120:0`.
- Q2 `advanced.bedrock.webrtc-proxy-protocol-relays` (with
  `bedrock.signaling.advertise-addresses` naming the relays) versus
  `advanced.bedrock.prefer-signaling-proxy-address` (with
  `haproxy-protocol-whitelisted-ips` or `signaling-trusted-proxies`):
  what each needs, and which one fits a UDP relay in front of the
  media port.

## Candidates for "can ICE be turned off"

Raised by the operator after Q1. ICE itself cannot be disabled - the
WebRTC media path is built by it. Three separable readings:

- C1 Disable the direct candidate path so media only flows through the
  relay: this is `webrtc-proxy-protocol-relays` (Q2 row 1). Costs the
  direct/LAN path and rewrites SDP answers to the relays.
  Operator's reading, recorded as a testable hypothesis: a player
  outside the LAN has no direct UDP entry to this host, so their media
  already traverses the frpc UDP tunnel, and their login line should
  today read `[/127.0.0.1:0]` - one remote client settles it.
- C2 Keep ICE, but stop reporting the ICE address: this is
  `prefer-signaling-proxy-address` (Q2 row 2), which reports the
  signalling proxy's address instead. It needs the signalling proxy
  listed in `haproxy-protocol-whitelisted-ips` or
  `signaling-trusted-proxies`.
- C3 C2's missing half in this deployment: the signalling proxy in
  front of Geyser is our own HAProxy mux, which today sends **no**
  header on the signalling backend (`scripts/scenes/frpc-shared-tcp.sh`
  `backend geyser_signaling`). C3 would add `send-proxy-v2` there behind
  an opt-in flag and list the mux (loopback) in
  `haproxy-protocol-whitelisted-ips`, so built-in signalling reports the
  player's real address to Geyser while the media plane keeps its
  direct ICE path. Unverified end to end: whether Geyser's built-in
  signalling HTTP listener consumes the header cleanly once the mux is
  listed, and what the reported port becomes.

## Port forwarding and how little an unverified path costs

## Governing intent (operator, stated last)

**The entry address a player types is their intent.** A player who types
the frp entry chose the public path; a player who wanted the LAN would
type the server's internal address. An ICE decision that quietly reroutes
the media over the LAN contradicts that choice, and so does an
identifier that reports something other than the path that was chosen.

Split into requirements, the intent has two halves that no single switch
covers together:

- R-a The reported address follows the entry. C3 satisfies this and is
  per-entry: a proxied entry reports the address that entry saw, an
  internal entry keeps the LAN/media address.
- R-b The media path follows the entry. No Geyser switch does this
  per-entry. `webrtc-proxy-protocol-relays` is **global**: once set, the
  SDP answer names only the relays, so players who typed the internal
  address are pushed through the relay as well ("players can only reach
  the media port through these relays"). C1 therefore implements
  "everyone goes public", not "the entry decides".

## Decision

C1. The deployment hands every player the frp entry and nothing else, so
"the media goes through the entry the player typed" means the media goes
through the relay. A LAN client that reaches the server directly chose a
path it did not ask for; that path is to be closed.

Known boundary, recorded rather than asked: `webrtc-proxy-protocol-relays`
forces the relay globally, so it is right for this deployment only
because the internal address is not an entry the players are given. If
that ever changes, the entry-vs-path question returns and only a
per-entry media design can answer it.

### Changes (operator side; no repository code)

1. frpc UDP tunnel in front of the media port: `proxy_protocol_version = v2`
   (their config is INI, so this key rather than
   `transport.proxyProtocolVersion`).
2. `bedrock.signaling.advertise-addresses`: the frp host's **numeric
   public IP** with the media port, not the host name. Evidence
   quality, corrected: the "never the frp host name" NOTE in
   `server/plugins/Geyser-Spigot/config.yml:54-56` is **not upstream
   text** - scanning the jar's configuration classes finds no `frp
   host` and no `special purpose`, and the `stun-discovery` prose
   differs from the jar's annotations, so that config.yml's comments
   have been rewritten locally. What is upstream-verified is the
   behaviour: the advertised name is resolved when signalling starts,
   and `Advertised address 198.18.103.7 is special purpose, no player
   can reach it` appears in this deployment's own `latest.log:127,:165`.
   In relay mode the numeric requirement is stronger and independent of
   fake-IP: the announced address has to be the node that actually
   forwards to this tunnel. Operator ruling: the fake-IP case was
   already settled (a private answer is reported rather than fatal) and
   there is no multi-node today, so this is a recorded note, **not** a
   gate on doing the work.
3. `advanced.bedrock.webrtc-proxy-protocol-relays: [<that IP>]`.
4. Confirm the media port is fixed (`bedrock.webrtc-port: 0` means the
   media port is `bedrock.port`, 19132) - the relay code warns
   `"PROXY protocol relays need a fixed ICE port"`.

### Acceptance and rollback

- Acceptance: the same LAN client that logged
  `.Dalvek[/10.1.1.120:0]` now logs the household public address, and the
  player still reaches the world.
- Rollback: remove the relay entry, clear `proxy_protocol_version` on the
  UDP tunnel, and the direct path returns.

### Repository deliverable

One `docs/ASP-SOP.md` subsection for the media plane, in the shape of
10.1.1: the four changes above, the fact that the direct path closes,
the acceptance line and the rollback. Nothing else in the repository
changes.

Recorded after operator questions; these are conclusions of this task,
not changes to make.

- Remote Java players and Bedrock signalling need no port forwarding:
  both arrive over the TCP relay (frpc + mux).
- Remote Bedrock **media** needs no port forwarding either, in this
  design: `advertise-addresses` names the frp node, so clients are told
  to send media there and frpc brings it back to `127.0.0.1:19132`. Port
  forwarding is only needed for the alternative where clients reach the
  household's own public IP directly (the case `config.yml:50-51`
  describes).
- Geyser's own comment for `prefer-signaling-proxy-address`
  ("Enable this when the WebRTC port is forwarded without PROXY
  protocol, so every player would otherwise show the forwarder's
  address") describes exactly this deployment, so C3 is the documented
  shape for it.
- Verifying either C1 or C3 does not need an off-LAN Bedrock client: the
  operator has none, and both routes are observable with the existing
  LAN client, because a relay or the signalling path sees that client's
  household public address. A phone on cellular (or a hotspot) is the
  way to manufacture an off-LAN client if reachability itself is what is
  being tested.
- Both C1 and C3 turn the LAN player's address into the household's
  public address. With only LAN Bedrock players today, neither makes the
  logged address more useful - the current `10.1.1.120` distinguishes
  devices, the public address does not. Their value only appears once a
  Bedrock player connects from outside the LAN.

## Acceptance Criteria

- [x] `research/` answers Q1 with the code path that sets the address,
      not only an inference from the observed login line -
      `research/q1-address-provenance.md`.
- [x] `research/` answers Q2 as a switch table: switch, what Geyser
      then reports, what it requires, what it breaks -
      `research/q2-switch-comparison.md`.
- [x] The cheapest discriminating observation to run on the host is
      written down (a Bedrock client outside the server's own LAN).

## Notes

- Non-goals: changing any config now; deciding what product behaviour
  Bedrock addresses should have.
- Prior research: `.trellis/tasks/archive/2026-11/11-16-frpc-proxy-protocol/research/natfrp-realip.md`
  covers the natfrp side (UDP tunnels need v2, frpc >=
  `0.42.0-sakura-4`).
- Evidence on hand: the comments in
  `server/plugins/Geyser-Spigot/config.yml`, the installed
  `server/plugins/Geyser-Spigot.jar`, and the `javap` dumps in `.tmp/`.
- This is expected to be PRD-only until the research lands; no
  `design.md` / `implement.md` before the switch set is chosen.
