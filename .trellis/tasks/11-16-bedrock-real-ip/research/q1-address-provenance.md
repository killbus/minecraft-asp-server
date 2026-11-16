# Research: Q1 - provenance of the reported Bedrock address (`10.1.1.120:0`)

- Query: which Geyser/NetherNet code path sets the address Geyser hands the
  Java backend for a NetherNet player, and why is the port `0`?
- Scope: internal (installed `server/plugins/Geyser-Spigot.jar`, its config,
  and this server's logs). No runtime changes were made.
- Date: 2026-11-16

## Answer

The address is the **remote address of the selected WebRTC/ICE media path** -
the address the player's Bedrock media actually arrives from - carried through
`NetherNetChannel.reportedAddress()` into `GeyserBedrockPeer` and then into the
`LocalSession` Geyser opens to the Java backend. For a client on the server's
own LAN, ICE selects a direct host-to-host pair, so that address is the
client's own LAN address (`10.1.1.120`). It is **not** the relay's address and
**not** the signalling address.

The port `0` is a literal that Geyser itself writes: the local Java connection
is a Netty `LocalChannel`, and Geyser spoofs the remote address as
`new InetSocketAddress(host, 0)`. The port is not derived from the ICE
candidate and not "because WebRTC data channels have no port" - the port is
deliberately dropped by Geyser.

## Verified evidence

All bytecode offsets below are from `javap -p -c` against the installed
`server/plugins/Geyser-Spigot.jar`; the class/offset pairs reproduce exactly.

### 1. The Paper log line is written on Geyser's direct-connection path

`org/geysermc/geyser/session/GeyserSession` (method that builds the downstream
session):

- offset 130-142: `if (geyser.getBootstrap().getSocketAddress() != null)`
- offset 145-182: `new LocalSession(bootstrap.getSocketAddress(),
  upstream.getAddress().getAddress().getHostAddress(), protocol, tickEventLoop)`
  and stores it as the downstream session (offset 225-234,
  `new DownstreamSession(...)` -> `this.downstream`).
- offset 240-292: the `else` branch builds a plain
  `new ClientNetworkSession(new InetSocketAddress(remoteServer.address(),
  remoteServer.port()))` - no spoof, no port 0.
- offset 350-386: `if (config.advanced().java().useHaproxyProtocol())
  session.setFlag(BuiltinFlags.CLIENT_PROXIED_ADDRESS, upstream.getAddress())`.

This deployment sets `advanced.java.use-direct-connection: true`
(`server/plugins/Geyser-Spigot/config.yml:258`), so the first branch runs and
the Java backend receives the spoofed address instead of a real TCP peer.

### 2. The port `0` is hard-coded by Geyser

`org/geysermc/geyser/network/java/LocalSession` constructor bytecode:

```
10: aload_0
11: new           java/net/InetSocketAddress
14: dup
15: aload_2
16: iconst_0
17: invokespecial java/net/InetSocketAddress.<init>:(Ljava/lang/String;I)V
20: putfield      spoofedRemoteAddress
```

So `this.spoofedRemoteAddress = new InetSocketAddress(hostString, 0)` - the
`0` is the constant in the constructor, independent of any WebRTC candidate.

`LocalSession$1.initChannel(Channel)` then applies it:

```
0:  aload_1 ; checkcast LocalChannelWithRemoteAddress
8:  getfield  LocalSession.spoofedRemoteAddress
11: invokevirtual LocalChannelWithRemoteAddress.spoofedRemoteAddress(SocketAddress)
19: invokestatic  NettyHelper.initializeHAProxySupport(Session, Channel)
```

`org/geysermc/geyser/network/java/LocalChannelWithRemoteAddress` is a
`io.netty.channel.local.LocalChannel` with a settable `spoofedAddress`, so the
Java backend's in-process channel reports exactly `InetSocketAddress(host, 0)`.

### 3. `hostString` is `UpstreamSession.getAddress()`

`org/geysermc/geyser/session/UpstreamSession.getAddress()`:

```
4:  invokevirtual BedrockServerSession.getPeer()
7:  checkcast     GeyserBedrockPeer
10: invokevirtual GeyserBedrockPeer.getRealAddress()
13: checkcast     java/net/InetSocketAddress
```

`org/geysermc/geyser/network/bedrock/GeyserBedrockPeer.getRealAddress()`:

```
1: getfield     proxiedAddress
(null branch) 10: invokevirtual getSocketAddress()
```

i.e. `proxiedAddress != null ? proxiedAddress : getSocketAddress()`. For
NetherNet the channel's socket address is the NetherNet channel's
`remoteAddress`, which NetherNet rewrites from the media path (step 4).

### 4. NetherNet rewrites `remoteAddress` from the selected ICE path

`org/cloudburstmc.netty.channel.nethernet.NetherNetChannel.adoptSelectedPath()`
bytecode (offsets as dumped):

```
0-17:   path = selectedPath(); remote = (path == null) ? null : path.remote()
18-30:  if (remote == null || remote.isUnresolved()) return path;
31-36:  relay = relayOf(remote)
37-64:  source = isRelay(path) ? TURN
                 : (relay != null ? ICE_PROXY_PROTOCOL : ICE)
66-78:  mediaAddress = new SourcedAddress(remote, source, relay)
81-99:  if (remoteAddress instanceof InetSocketAddress)
            remoteAddress = reportedAddress().address();
102:    return path
```

`selectedPath()` is built from libdatachannel's selected candidate pair:

```
new NetherNetChannel$Path(pair.local(), pair.localType(),
                          pair.remote(), pair.remoteType())
   where pair = peerConnection.selectedCandidatePair()
```

so `path.remote()` is the **remote candidate of the selected ICE pair** - the
address the player's media comes from.

### 5. `reportedAddress()` chooses media vs signalling

`NetherNetChannel.reportedAddress()` calls
`reported(signaledAddress, mediaAddress, preferProxiedAddress)`, and the static
`reported(...)`:

```
if (media.source == UNKNOWN) return signalled;
if (preferProxied && proxied(signalled)) return signalled;   // proxied = source in
                                                            //   { SIGNALING_PROXY_PROTOCOL,
                                                            //     SIGNALING_FORWARDED_FOR }
if (media.source == TURN && unforged(signalled)) return signalled;
return media;
```

`mediaAddress` starts as `SourcedAddress.unknown()` in the constructor and only
becomes a real address in `adoptSelectedPath()`. So once a media path exists,
the media (ICE) address wins over the signalling address unless a switch
deliberately prefers a proxied signalling address.

`org.cloudburstmc.netty.channel.nethernet.AddressSource` has exactly these ten
values: `SIGNALING`, `SIGNALING_PROXY_PROTOCOL`, `SIGNALING_FORWARDED_FOR`,
`SIGNALING_LAN`, `HOST`, `NXS_ADMISSION`, `ICE`, `ICE_PROXY_PROTOCOL`, `TURN`,
`UNKNOWN`.

### 6. Where the address reaches the Java side and the debug log

`org/geysermc/geyser/network/bedrock/nethernet/NetherNetChannelInitialiser$ConnectionGate.channelActive`:

```
32-36: reported = ((NetherNetChannel) channel).reportedAddress()
37-43: logSignaled(channel.signaledAddress(), reported)
46-70: ConnectionRequests.accept(geyser, reported.address(),
                                 reported.via(), reported.source().name())
       if false -> ctx.close(); else fireChannelActive()
```

`logSignaled` builds its message from the string constants
`"NetherNet signaling met \u0001 (\u0001\u0001)"` and `" via \u0001"`, gated on
`GeyserLogger.isDebug()` and on `config.logPlayerIpAddresses()`. The
`AddressSource` name is printed directly, so a debug run names the source
(`ICE`, `TURN`, `SIGNALING_PROXY_PROTOCOL`, ...) for each connection.

### 7. Log corroboration

- `server/logs/2026-10-17-4.log.gz`: the Bedrock player `.Dalvek` always logs
  as `.Dalvek[/127.0.0.1:0] logged in with entity id ...`, while the Java
  player in `server/logs/latest.log:197` logs as
  `Snorlax[/127.0.0.1:6670]` (a real ephemeral port). Same client on the server
  host -> media/ICE path is loopback `127.0.0.1`, and the `:0` is Geyser's own.
  Moving the same client to another LAN host makes that same field the client's
  LAN address (`10.1.1.120`), which is exactly what the media path reports.

### 8. Deployment context that makes this the active path

- `server/plugins/Geyser-Spigot/config.yml:30` `transport: nethernet`
- `:22` `port: 19132`, `:25` `webrtc-port: 0`
- `:45` `signaling.mode: builtin`, `:58` `advertise-addresses: ["frp-net.com:34003"]`
- `:252` `use-haproxy-protocol: true`, `:258` `use-direct-connection: true`
- `server/config/paper-global.yml:114` `proxies.proxy-protocol: true`
- `server/server.properties:51` `prevent-proxy-connections=false`, `:32` `log-ips=true`

## Caveats / Not Found

- The exact `10.1.1.120:0` line is not present in the logs kept in this
  checkout (`server/logs/`); the newest `.Dalvek` entries are
  `[/127.0.0.1:0]`. The value `10.1.1.120` is therefore explained from the
  code path plus the loopback analogue, not from a captured log line.
- The exact ICE candidate pair that was selected for that one session is not
  recorded anywhere on the host (it is libdatachannel's choice at connect
  time). That the media source was `ICE` is an inference from "same LAN ->
  direct host candidate" plus the observed LAN address; the debug log in
  step 6 is the observation that would settle it.
- `signaling.port` is absent from `server/plugins/Geyser-Spigot/config.yml`;
  `javap -v` shows `SignalingConfig.port()` has no `@Default*` annotation, so
  the bytecode alone does not pin the value the deployment binds (it feeds
  `NetherNetServer.startInbuilt`'s `separateMediaPort` check and the
  `NETHER_SERVER_ICE_ADDRESS` option). This does not affect Q1, which only
  depends on the media/ICE path.

## Related

- `.trellis/tasks/archive/2026-11/11-16-frpc-proxy-protocol/research/natfrp-realip.md`
  (natfrp PROXY-protocol side)
- `.trellis/tasks/11-16-bedrock-real-ip/research/q2-switch-comparison.md`
  (which switch changes the reported address)
