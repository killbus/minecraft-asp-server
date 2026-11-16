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
