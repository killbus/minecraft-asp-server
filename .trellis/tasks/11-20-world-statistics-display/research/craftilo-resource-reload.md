# Research: Craftilo resource reload and keepalive disconnect

- Query: Why did Craftilo remain at the Mojang loading screen after `/wl enter world resume`, and does Paper expose an appropriate keepalive setting or known fix?
- Scope: mixed; read-only local runtime/client bytecode and logs, PackManagerPro source, current upstream Paper patch/docs/issues.
- Date: 2026-11-20

## Findings

### Bounded conclusion

The 12:58 disconnect is an explicit **out-of-order keepalive response** rejection, not expiration of the keepalive time limit. Paper received a response for a challenge it still knew about, but an older challenge was still at the head of its pending queue. This branch immediately disconnects with the generic client-facing reason `Timed out`.

The world entry completed before the disconnect. Leaving the world with the resource pack triggered expected client resource removal and reload. The reload and disconnect overlap in time; this does not establish why the response order changed. Vanilla 26.2 has a concrete deferred-reply path that can permit an older queued reply to be overtaken by a new immediate reply after a window event stall. That path is a supported hypothesis, not an observed packet trace for this incident.

Changing `paper.playerconnection.keepalive` cannot fix this particular FIFO mismatch branch. No server/client/runtime change was made in this investigation.

### Incident evidence

| Time | Evidence | Meaning |
| --- | --- | --- |
| 12:50:55 | Server: `Craftilo was kicked due to keepalive timeout!` | Earlier, separate incident used the actual elapsed-time expiry branch. |
| 12:51:25 | Server: Craftilo joined in `trials` | The next connection succeeded. |
| 12:58:02 | Server: `/wl enter world resume`, followed by `WL ENTER_OK Craftilo world=world mode=resume` | Lifecycle entry reported success. |
| 12:58:03 | Client: `WL entered world`; `Reloading ResourceManager` list no longer contains the server pack | Expected removal of the previous world's pack began. |
| 12:58:04–06 | Client: default-size texture atlas creation | Client resource reload progressed. |
| 12:58:05 | Server Netty thread: `Disconnecting Craftilo for sending keepalive response (20969934) out-of-order!` | Exact immediate-rejection branch identified. |
| 12:58:05 | Server: Craftilo lost connection / left | Server session ended. |
| 12:58:06 | Client: `Client disconnected with reason: Timed out` | Client processed the generic reason after atlas work. |

Source locations:

- `.tmp/world-lifecycle-manual/runtime/logs/latest.log:451`: earlier actual keepalive timeout.
- `.tmp/world-lifecycle-manual/runtime/logs/latest.log:464`: entry command and subsequent immediate rejection through line 468.
- `D:/Applications/Portable/PrismLauncherCracked/instances/26.2.Cartilo/minecraft/logs/latest.log:856`: client world-entry acknowledgement and reload through line 880.

These are live/rotatable logs. The timestamps and diagnostic lines above preserve the useful facts without relying on those line numbers staying fixed.

### Exact Paper 26.2 behavior

Inspected the **actual manual runtime** with `javap -p -c`, not merely a different branch's source:

- `.tmp/world-lifecycle-manual/runtime/versions/26.2/paper-26.2.jar`
- Runtime baseline: Paper 26.2 build 135.
- SHA-256: `7c391444fd5f5fb77d193414924e7a16dbfd1cac87a2a6c858a8ea8dd041f44e`.

`net.minecraft.server.network.ServerCommonPacketListenerImpl.handleKeepAlive`:

1. Read `keepAlive.pendingKeepAlives.peek()`.
2. If non-null and its `challengeId` equals received ID, remove that pending challenge, update latency averages, and return.
3. Otherwise iterate the pending queue. If the ID matches a remaining challenge, remove it, log `out-of-order!`, and immediately invoke `disconnectAsync(TIMEOUT_DISCONNECTION_MESSAGE, DisconnectionReason.TIMEOUT)`.
4. If no ID matches, log the distinct message `without matching challenge!` and disconnect.

Relevant bytecode offsets: head match at 19–34; valid return at 103; iterator search at 104–148; out-of-order log at 161 and disconnect at 189; unknown-challenge log at 199. Existing matching disassembly is readable at `.tmp/login-deadline-fix/ServerCommonPacketListenerImpl.javap.txt:137` and the out-of-order literal at line 206; a fresh direct `javap` of the live runtime was also checked.

`keepConnectionAlive`:

- Sends another challenge after at least one second since `lastKeepAliveTx`.
- Appends `(System.nanoTime(), Util.getMillis())` as the pending challenge before sending it. The millisecond value is the echoed challenge ID, not a player/world identifier.
- Separately checks the age of the **oldest** pending challenge against `KEEPALIVE_LIMIT` and emits `was kicked due to keepalive timeout!` only on that age branch.
- `KEEPALIVE_LIMIT` is initialized as `Long.getLong("paper.playerconnection.keepalive", 30) * 1000`.

Existing disassembly references: `.tmp/login-deadline-fix/ServerCommonPacketListenerImpl.javap.txt:579` (periodic send/expiry), `:1095` (property initialization).

The actual out-of-order branch reads no timeout property and no configurable boolean. Current upstream `0015-Improve-keepalive-ping-system.patch` has the same strict sequence logic. The public property is a JVM system property, not a Paper YAML key, and its documented scope is how long to wait without receiving keepalives. Increasing it could affect the earlier 12:50 silence incident; it cannot make the observed 12:58 mismatch acceptable.

### Client 26.2 behavior and inference boundary

Inspected vanilla classes from the actual installed 26.2 client artifact:

- `D:/Applications/Portable/PrismLauncherCracked/libraries/com/mojang/minecraft/26.2/minecraft-26.2-client.jar`
- SHA-256: `40896ee9f1e2bec3c934daac7e93d41e9e3d9c2f8ae0ca366d52ffbfd1afa290`.
- This is the vanilla base artifact. Running Fabric mixins may alter behavior; no claim of a complete transformed-class audit is made.

`ClientCommonPacketListenerImpl.handleKeepAlive` has no main-thread handoff. It constructs an echo reply and calls:

```text
sendWhen(reply, () -> !RenderSystem.isFrozenAtPollEvents(), Duration.ofMinutes(1))
```

Bytecode evidence:

- `handleKeepAlive`: constructs `ServerboundKeepAlivePacket` from received ID at offsets 1–9; `sendWhen` invocation at 21.
- `lambda$handleKeepAlive$0`: calls `RenderSystem.isFrozenAtPollEvents()` and negates the result.
- `RenderSystem.isFrozenAtPollEvents`: true only when `pollingEvents` is true and elapsed time since `pollEventsWaitStart` exceeds **200 ms**. `pollEvents` sets/clears those atomics around `GLFW.glfwPollEvents()`.
- `sendWhen`: if condition is true, sends immediately at offset 11. It does **not** first drain or inspect `deferredPackets`. Otherwise it adds the reply, condition, and an expiration time to that list.
- `sendDeferredPackets`: iterates the queued replies and sends/removes those whose condition is now true; expired entries can be removed without sending.
- `ClientPacketListener.tick`: calls `sendDeferredPackets` at offset 68.

Consequently, this sequence is possible in the unmodified base code:

1. A arrives while window event polling is frozen for over 200 ms; A is deferred.
2. Event polling unfreezes.
3. B arrives before the next queue drain and is sent immediately.
4. Paper receives B while A is still the expected head and disconnects.

This requires the relevant timing/window-poll conditions. A generic slow resource reload alone does not prove those conditions; the send predicate checks GLFW event polling, not a resource-reload flag. The available logs do not show the pending head ID, A's receipt/defer time, the exact client outbound order, or transformed networking methods. A stack sampled after disconnect cannot reconstruct those facts.

### Why a resource reload occurred

The existing PackManagerPro source has a direct, normal path:

- `.tmp/PackManagerPro/src/main/kotlin/dev/naspo/packmanagerpro/listeners/PlayerChangedWorldListener.kt:17`: handles world change, and at line 22 calls `sendResourcePack` when per-world application is enabled.
- `.tmp/PackManagerPro/src/main/kotlin/dev/naspo/packmanagerpro/resourcepack/SendResourcePack.kt:28`: obtains the destination world's cached request.
- The same file at line 37–38: absent request calls `player.clearResourcePacks()`.
- Client `ClientCommonPacketListenerImpl.handleResourcePackPop` handles the pop packet on the main thread and calls the downloaded-pack source's `popAll` or `popPack`.

Therefore seeing the Mojang resource screen on exit from a packed world is expected. Pack warnings or large atlas sizes can help investigate load cost, but they do not demonstrate the cause of a keepalive sequence inversion. Do not blame malformed pack JSON, lifecycle coordinates, MVI statistics, or the second player's identity based on this log alone.

### Upstream evidence and applicability

- [Current Paper keepalive feature patch](https://github.com/PaperMC/Paper/blob/main/paper-server/patches/features/0015-Improve-keepalive-ping-system.patch): retrieved 2026-11-20; still sends once per second, uses a pending FIFO, rejects out-of-order replies, and copies keepalive history without pending expectations at listener handoff.
- [Paper system properties](https://docs.papermc.io/paper/reference/system-properties/#paperplayerconnectionkeepalive): documents `paper.playerconnection.keepalive`, default 30 seconds, silence/response wait limit.
- [Paper PR #13712](https://github.com/PaperMC/Paper/pull/13712): describes stale PLAY expectations surviving into CONFIG during Velocity reconfiguration. **That specific fix is already present locally**: `createCookie` calls `KeepAlive.copyForListenerHandoff`, which creates a new tracker and copies timestamp/latency history without pending queue entries. Existing disassembly: `.tmp/login-deadline-fix/KeepAlive.javap.txt:41`; caller at `ServerCommonPacketListenerImpl.javap.txt:1066`. This incident is not established as that bug, and merely upgrading to obtain that fix is not a grounded recommendation.
- [Paper #12888](https://github.com/PaperMC/Paper/issues/12888): similar out-of-order message after stutter, but reported on **1.8.8 ViaRewind** against Paper 1.21.8. Discussion explicitly found it did not affect current-version clients or 1.12.2. This is related precedent, not a verified 26.2 fix.
- [Paper #921](https://github.com/PaperMC/Paper/issues/921): historical resource-pack timeout report from the 1.12 era. It concerns elapsed timeout and is not evidence for this modern FIFO mismatch.

## Next bounded observation

Root should first assess a passive loopback packet trace for a single repeated transition, correlated with the existing server/client logs. Needed observations are server challenge IDs in send order and client response IDs in return order, with timestamps; include pack pop/push and teleport timing if the capture is decodable. A trace must account for encryption/compression rather than assume TCP bytes directly reveal packet IDs.

If passive observation cannot expose the required sequence, use a disposable reproduction with minimal scoped diagnostic instrumentation or an unmodified current-version client control. Keep that separate from the user's current live state. An exact capture can distinguish an omitted/late reply, a client-side reorder, a protocol transition, and any server bookkeeping issue. Do not blanket-cancel kick events, suppress validation, change the resource policy, modify the user's clients, or increase timeouts as a purported fix for the known mismatch.

### Local capture feasibility checked by root

The manual runtime declares `online-mode=false`, loopback port 25598 and
`network-compression-threshold=256`. `dumpcap -D` exposes
`\\Device\\NPF_Loopback`; both dumpcap and tshark are installed. A bounded
capture filtered to TCP port 25598, starting before a fresh connection,
can retain login/compression negotiation and both directions for this local
offline-mode session. It still needs TCP reassembly, Minecraft VarInt
framing and compression decoding; individual TCP frames are not Minecraft
packets. Do not assume a comparable production session is unencrypted.

By 13:15:44 both real players had disconnected; Craftilo's client log records
`Stopping!` at 13:15:40. No further transition occurred to capture. No capture
was started, no GUI client was launched and no diagnostic instrumentation
was installed. A future repeat should capture only this bounded local game
connection, then compare challenge IDs and responses against the FIFO rule.

## Follow-up evidence at 15:00

The later investigation is recorded in `craftilo-resource-reload-upstream.md`
and `craftilo-keepalive-probe.md` in this directory. Snorlax encountered the
same out-of-order branch at 14:56:42 after formal WL reported entry success;
the client again reloaded resources without the server pack. This excludes
a Craftilo-only or prototype-only explanation.

Five controlled experiments invoking the actual unmodified 26.2 client
methods passed, including actual `handleKeepAlive` with an induced frozen
RenderSystem state. A queued A can be overtaken by immediate B, producing
`[402, 401]` at the recording Connection boundary. This establishes
method-level capability, not the actual incident's GLFW/network timing.

The installed 26.3 client (SHA256
`4508d006323f24fa02876310c192d739af56516eb259000ac50f0909a68c9a2d`)
retains the inspected `handleKeepAlive`, `sendWhen`, and
`sendDeferredPackets` behavior: the condition is still
`!RenderSystem.isFrozenAtPollEvents()`, with immediate send on true and no
older-queue check. Disassembly is under
`.tmp/craftilo-keepalive-research/ClientCommonPacketListenerImpl-26.3.javap.txt`.
No 26.3 full-client reproduction or fix claim follows from this comparison.

## Related Specs

- `.trellis/spec/backend/multiverse-player-state.md`: MVI owns state; lifecycle owns entry/unloading; display is separate. This failure does not justify moving networking or pack reload policy into WorldLifecycle.
- `.trellis/tasks/11-20-world-statistics-display/prd.md`: preserve manual runtime while user is online; the urgent incident is diagnosis alongside, not an expansion of the statistics display implementation.

## Caveats / Not Found

- Exact root cause of the response inversion is **unproven** without a packet/timing trace.
- No direct applicable Paper 26.2 resource-reload/out-of-order fix was found in the bounded upstream search. This is not proof no such issue exists.
- No supported switch to relax this FIFO check was present in the inspected handler or current feature patch.
- No runtime/client/plugin changes, restart, SSH, or production actions were performed.
