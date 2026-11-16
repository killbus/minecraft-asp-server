# natfrp: real visitor IP (Proxy Protocol)

Source: `https://doc.natfrp.com/bestpractice/realip.html`, section *Proxy
Protocol*, read on 2026-11-16 with `opencli --profile fx2wmxgs browser ...`
(sandbox has no direct network). Page language: zh-CN.

## Page facts

- The switch is written in the tunnel's custom settings (professional mode) as
  `proxy_protocol_version = <v1|v2|simple>`; frpc then applies PROXY protocol
  when it connects to the local service. v2 is recommended; UDP tunnels always
  need v2 and need frpc >= `0.42.0-sakura-4`; `simple` is Cloudflare's variant
  and almost nothing supports it.
- "只修改 frp 配置会造成隧道完全不可用" - the local service must be configured
  in the same move.
- Most applications force the handshake once enabled: they cannot accept
  connections without the header, so local/LAN direct connections stop working
  (their suggested escape hatch is the 内网访问 feature).
- Minecraft tabs:
  - **Paper**: 1.18.2+ supports v2. `server.properties` needs
    `prevent-proxy-connections = false` (that is the default), and
    `config/paper-global.yml` needs `proxies.proxy-protocol: true`.
  - **Geyser**: inbound traffic only needs Geyser's proxy-protocol switch;
    outbound traffic (Geyser -> Java backend) needs `use-proxy-protocol: true`
    plus the Paper-side switch.
  - Other servers: HAProxyDetector (Spigot), per-mod options for
    Fabric/Forge - the page itself warns these carry "vibe coding" traces.
  - For "tunnel and direct connection at the same time" they point at
    `Wuchang325/HAProxyReduce` (Velocity/Paper/Folia) and
    `melodytik/ProxyProtocolDetector` (Paper).

## How it maps to this deployment

- Our installed Geyser build names the outbound switch
  `advanced.java.use-haproxy-protocol` (`plugins/Geyser-Spigot/config.yml:252`),
  and replaces the single inbound `enable-proxy-protocol` with
  `advanced.bedrock.haproxy-protocol-whitelisted-ips`,
  `signaling-trusted-proxies` and `webrtc-proxy-protocol-relays`. Its comment
  states built-in signalling still accepts connections *without* a header, so
  the signalling port is not forced.
- `prevent-proxy-connections=false` and `log-ips=true` are already set on both
  hosts (`server/server.properties:51`, `:32`); `proxies.proxy-protocol` is
  still `false` (`server/config/paper-global.yml:114`).
- The frpc side is a hand-written `frpc.toml`, so the switch is
  `transport.proxyProtocolVersion = "v2"` under `[[proxies]]` (the sakura
  launcher writes the same thing from `proxy_protocol_version`).
