# Official frpc UDP spike

## Question

Can the official frpc binary carry a NATFRP UDP tunnel while forwarding the
request-side address to Geyser with PROXY protocol v2, without relying on the
Sakura fork?

## Verified setup

- Official frpc: `0.72.0`, operator-provided at
  `~/asp-frpcs/bin/frpc`.
- NATFRP UDP tunnel pointed at local `127.0.0.1:19132`.
- Provider-side tunnel had `proxy_protocol_version = v2`.
- Local probe listened on `127.0.0.1:19132` and was not a Minecraft client.

## Result

The probe received one logical observation containing the PROXY v2 header
and the payload:

```text
received 47 bytes
proxy    v2 PROXY IPv4/DGRAM
source   203.0.113.7:40777
header-dst 127.0.0.1:19133 (metadata; localPort routes)
payload  19 bytes: b'official-frpc-spike'
verdict  frpc supplied the request-side endpoint in a PROXY v2 header
```

The header-destination field is protocol metadata. It is not the local
service selector; `localPort` performs that role.

## Full-path observation

After switching to the relay configuration, Geyser accepted a Bedrock
connection through the PROXY protocol relay path:

```text
ICE_PROXY_PROTOCOL via /127.0.0.1
<bedrock-player>[/<public-client-ip>:0] logged in
```

The `:0` port is the expected Geyser Java-side address shape.

## Decision

- Use official frpc for the NATFRP UDP tunnel.
- Keep Sakura frpc for TCP entries that depend on provider `auto_https` and
  provider-issued certificates.
- Do not add a Go daemon or a Python shim to the runtime path.
- Do not infer that one binary must serve every provider; the scene manifest
  exists to make the per-process binary explicit.

## Security note

This note intentionally omits account names, tokens, real public IPs,
provider-bound domains, and certificate material. Those belong only in the
operator's external scene/config directory.
