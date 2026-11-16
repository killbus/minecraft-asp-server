# Research: Q2 - `webrtc-proxy-protocol-relays` vs `prefer-signaling-proxy-address`

- Query: what does each switch need, what does Geyser then report, what does it
  break, and which one fits a UDP relay in front of the NetherNet media port?
- Scope: mixed. Internal: installed jar bytecode + its config comments, the
  deployment's mux/frpc scene scripts, and this server's logs. External: the
  natfrp real-IP page already captured in the archived frpc research.
- Date: 2026-11-16

## Topology this has to fit

- Java TCP and Bedrock NetherNet **built-in signalling** share one public TCP
  port through an HAProxy L4 demux; the **WebRTC media plane needs its own
  frpc UDP proxy** (`scripts/scenes/frpc-shared-tcp.sh:5-9`, `:321-357`).
- The demux routes to `backend geyser_signaling` (bedrock port) and
  `backend java`; only the **Java** backend gets `send-proxy-v2`. The
  signalling backend never sends a PROXY header
  (`scripts/scenes/frpc-shared-tcp.sh:353-357`).
- Current config: `webrtc-proxy-protocol-relays: []`,
  `haproxy-protocol-whitelisted-ips: []`, `signaling-trusted-proxies: []`,
  `prefer-signaling-proxy-address: false`
  (`server/plugins/Geyser-Spigot/config.yml:284`, `:290`, `:300`, `:306`).
- `advertise-addresses` currently names a **host name**, not a numeric IP:
  `["frp-net.com:34003"]` (`config.yml:58`).

## Switch table

| Switch | What Geyser then reports | What it requires | What it closes / breaks |
| --- | --- | --- | --- |
| `webrtc-proxy-protocol-relays: [<relay IPs/CIDRs>]` (with `bedrock.signaling.advertise-addresses` naming the relays) | The address the **relay** writes into the PROXY v2 header on each media packet - i.e. the player's address as seen by that relay (its real address on the relay's side) | A fixed ICE port (`NetherNetServerChannel`: `"PROXY protocol relays need a fixed ICE port"`); every media packet must start with a PROXY v2 header from a listed relay; `advertise-addresses` must name the relays, else **external signalling will not start** (`NetherNetServer`: `"will not start! \"webrtc-proxy-protocol-relays\" is set, so \"advertise-addresses\" ... has to name the relays"`) | Players can *only* reach the media port through those relays; direct/LAN clients that reach the media port themselves send no header and are refused; TURN servers are dropped (`NetherNetServerChannel`: `"TURN servers ... cannot work behind the ... relays"`, `"Leaving out TURN servers ..."`); SDP answers are rewritten to the relays (`SdpUtil.withRelayedCandidates`, `"None of the relays {} can be announced ..."`) |
| `prefer-signaling-proxy-address: true` | The **signalling** proxy address (`SIGNALING_PROXY_PROTOCOL` from a HAPROXY header, or `SIGNALING_FORWARDED_FOR` from `X-Forwarded-For`) instead of the media/ICE address | Built-in signalling must be running, **and** `haproxy-protocol-whitelisted-ips` or `signaling-trusted-proxies` must list the proxy in front of signalling; otherwise Geyser warns `"prefer-signaling-proxy-address" does nothing ...` and nothing changes | Nothing in the media plane is touched, so a forwarded-but-unprotected UDP media port still shows the forwarder; it only helps when the *signalling* path is what reached Geyser and carries the player address |
| Neither (current) | The media/ICE remote address (Q1) - here the client's own LAN/host address, port `0` | - | - |

## How each is wired in the jar (verified)

`javap` on the installed jar:

- `NetherNetServer.startInbuilt` builds the NetherNet server bootstrap and sets:
  - `NETHER_SERVER_PROXY_PROTOCOL` <- `TrustedProxies.parse(config.advanced().bedrock().webrtcProxyProtocolRelays())`
    (offsets ~852-880);
  - `NETHER_SERVER_PREFER_PROXIED_ADDRESS` <- `advanced.bedrock.preferSignalingProxyAddress()`
    (offsets ~886-898);
  - `NETHER_SERVER_ICE_ADDRESS` only when the media port differs from the
    signalling port (offsets ~912-943).
  - The built-in signalling builder is fed `signalingTrustedProxies` ->
    `setForwardedForProxies` (offsets ~466-498) and
    `haproxyProtocolWhitelistedIps` -> `setProxyProtocolProxies`
    (offsets ~501-526).
- `NetherNetServer.warnIfBuiltinSettingsUnused` prints (string constants):
  - `"prefer-signaling-proxy-address" does nothing, as built-in signaling is not running.`
  - `"prefer-signaling-proxy-address" does nothing, as neither "haproxy-protocol-whitelisted-ips" nor "signaling-trusted-proxies" lists a proxy in front of built-in signaling.`
- `NetherNetServer` (external-signalling branch) errors with:
  `... will not start! "webrtc-proxy-protocol-relays" is set, so "advertise-addresses" under "bedrock.signaling" has to name the relays players reach this server through.`
- `NetherNetServerChannel` strings: `"PROXY protocol relays need a fixed ICE port"`,
  `"TURN servers in NETHER_PEER_CONNECTION_CONFIG cannot work behind the NETHER_SERVER_PROXY_PROTOCOL relays, which pass nothing but STUN lookups"`,
  `"Leaving out TURN servers, as nothing but STUN lookups passes the PROXY protocol relays on the ICE port"`,
  and the connect-failure hint `"... nothing arrived through the PROXY protocol relays this server advertises. Each relay has to forward to UDP port ... and be listed."`
- `org.cloudburstmc.netty.util.nethernet.IceProxyProtocol` is created as
  `new IceProxyProtocol(InetAddress, int, IpRangeSet)` (via
  `NetherNetServerChannel` -> libdatachannel
  `IceUdpMuxListener.setProxyProtocol(InetAddress, int, Collection<String>)`),
  and `relayOf(addr)` maps a media source to a listed relay via
  `IceUdpMuxListener.proxyRelay(...)`. `TrustedProxies.parse(Collection)`
  accepts plain IPs, subnets, and `http(s)://` list URLs.
- `SdpUtil` announces relays / advertised addresses when answering:
  `withRelayedCandidates(relays, ...)`, `withAdvertisedCandidates(...)`,
  `"None of the gathered ICE candidates match the advertised addresses {}, announcing all of them instead"`,
  `"None of the relays {} can be announced from the gathered ICE candidates, so the answer names none"`.

## Which one fits a UDP relay in front of the media port

`webrtc-proxy-protocol-relays` is the media-plane switch: it is the only one of
the two that changes the address on the WebRTC/UDP path, because it makes
Geyser require and parse a PROXY v2 header on every media packet. The natfrp
page (archived in `.../11-16-frpc-proxy-protocol/research/natfrp-realip.md`)
confirms the relay side: the switch there is
`transport.proxyProtocolVersion = "v2"` under `[[proxies]]` (the sakura launcher
writes it from `proxy_protocol_version = v2`), UDP tunnels always need v2, and
`frpc >= 0.42.0-sakura-4`. In this deployment that means:

1. The frpc **UDP** tunnel in front of the media port must send PROXY v2.
2. `advertise-addresses` must name the relays (the frp host's **numeric public
   IP:port**, never the host name - a fake-IP answer makes Geyser refuse it as
   "special purpose"; `config.yml:54-56`).
3. `prefer-signaling-proxy-address` is irrelevant here: it only moves the
   *signalling* proxy address, which has nothing to do with a UDP media relay.

`prefer-signaling-proxy-address` would only help if the **built-in signalling**
were reached through a proxy that the config lists in
`haproxy-protocol-whitelisted-ips` or `signaling-trusted-proxies`, and if the
signalling source were the only address available. In this deployment the demux
sends **no** PROXY header on the signalling backend
(`scripts/scenes/frpc-shared-tcp.sh:353-357`) and both lists are empty, so the
switch would warn and do nothing until the mux itself is changed too.

## Refutation: the relay switch could not change the observed `.Dalvek` line

For the recorded session the player was on the server's own LAN, so the
selected ICE path was direct host-to-host and the media source was `ICE` - the
reported address was the client's own LAN address (`10.1.1.120`), per Q1.
`webrtc-proxy-protocol-relays` only rewrites the media address when a packet
actually arrives through a listed relay (`relayOf` -> `ICE_PROXY_PROTOCOL`, or
`TURN`). A relay-side header therefore could not have produced that line, and
enabling the switch would in fact **stop** that same direct LAN client from
reaching the media port (no header). Confirmed-by-code; the residual
uncertainty (which ICE pair was selected) is the same as Q1's.

## Cheapest discriminating observation to run on the host

1. Connect a Bedrock client that is **outside the server's own LAN** (e.g. a
   phone on cellular) through the public entry and read the Java-side name
   line. If the IP becomes the client's public address while the port stays
   `0`, Q1 is confirmed (media/ICE address; port `0` is Geyser's own).
2. Or, with `debug-mode` on (`advanced.bedrock.nethernet-debug: true` is
   optional), read the Geyser logger debug line
   `"NetherNet signaling met <addr> (<AddressSource>)"` (+ ` via <relay>`). The
   enum name printed there (`ICE`, `ICE_PROXY_PROTOCOL`, `TURN`,
   `SIGNALING_PROXY_PROTOCOL`, `SIGNALING_FORWARDED_FOR`, ...) settles the
   source directly. Enabling debug is a config change, so it is an operator
   action outside this task; reading the line is not.

## Caveats / Not Found

- Built-in signalling is currently **failing** in this deployment: the
  advertised host name resolves to a proxy fake-IP
  (`198.18.103.7`), which Geyser refuses as special-purpose -
  `server/logs/latest.log:126-170` and `server/logs/2026-11-15-2.log.gz`.
  Any switch experiment must first make `advertise-addresses` a *numeric*
  public IP (`config.yml:54-56`); on 2026-11-14 the server instead started via
  the **external** signalling service (`2026-11-14-2.log.gz`:
  "Registered with the external signaling service ...").
- Whether the currently configured HAProxy mux is in front of the media port
  at all is not evidenced by these files; the scene script only guarantees the
  *signalling* backend. The relay side of `webrtc-proxy-protocol-relays` is the
  frpc UDP tunnel, which is configured outside this repository
  (`transport.proxyProtocolVersion`).
- `signaling.port` is absent from the deployment config, so the exact port the
  media/signalling bind uses, and therefore whether the
  `"PROXY protocol relays need a fixed ICE port"` check is satisfied, cannot be
  settled from the artifacts here.
