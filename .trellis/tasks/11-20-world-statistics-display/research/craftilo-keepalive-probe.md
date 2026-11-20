# Actual Minecraft 26.2 keepalive method probe

Date: 2026-11-20. Read-only client input; standalone JVM probe. No server or
game client was started or modified. This answers the bounded mechanism
question, not the cause of the Craftilo incident.

## Result

**The actual unmodified 26.2 client can hand a newer keepalive response to
Connection.send before an older deferred response.** Five method-level
cases passed. The reorder requires the later response's send condition to
become true before the client drains the older deferred queue.

| Case | Actual methods called | Observed response IDs |
| --- | --- | --- |
| A condition false; B condition true; drain | private `sendWhen`, `sendDeferredPackets` | `[102, 101]` |
| A condition false; drain after condition true; then B | same methods | `[201, 202]` |
| Both conditions true | same methods | `[301, 302]` |
| A while induced RenderSystem frozen; B after thaw; drain | public `handleKeepAlive`, `sendDeferredPackets` | `[402, 401]` |
| Both keepalives while unfrozen | public `handleKeepAlive`, `sendDeferredPackets` | `[501, 502]` |

In the fourth case, the real `handleKeepAlive` implementation queued response
401, immediately sent 402 after the induced state changed, then sent 401 when
the real drain method was invoked. Thus this is more than a rewritten toy
model of the presumed algorithm.

## Input provenance

Client JAR:
`D:/Applications/Portable/PrismLauncherCracked/libraries/com/mojang/minecraft/26.2/minecraft-26.2-client.jar`

- SHA256: `40896ee9f1e2bec3c934daac7e93d41e9e3d9c2f8ae0ca366d52ffbfd1afa290`
- SHA1: `2dc72797acbc1b63fc16a11c4ac393605f453754`
- The SHA1 matches the installed official-version metadata `mainJar` entry,
  which points to
  `https://piston-data.mojang.com/v1/objects/2dc72797acbc1b63fc16a11c4ac393605f453754/client.jar`.
- Runtime: Temurin OpenJDK 25.0.4+7.
- Dependencies were selected from installed 26.2 metadata and launcher
  libraries, not the mod directory. No Fabric loader or mod was loaded.
  Missing macOS/Linux-only libraries were not downloaded and were unnecessary
  on this Windows host.
- Every included JAR and the version metadata has a SHA256 entry in
  `.tmp/craftilo-keepalive-probe/input-hashes.json`.

## Empirical construction

`KeepAliveProbe.java` allocates the real concrete `ClientPacketListener` using
`Unsafe.allocateInstance`, injects an empty deferred list and a recording
Connection subclass, and invokes existing client bytecode. Only
`Connection.send(Packet)` is overridden, to record the outgoing ID. The
probe does not replace `sendWhen`, `sendDeferredPackets`, `handleKeepAlive`
or the real `RenderSystem.isFrozenAtPollEvents` condition.

The first three cases pass an `AtomicBoolean` supplier to the real private
`sendWhen` method. The final two call public `handleKeepAlive` directly. For
the induced frozen case, reflection sets the standalone JVM's real
RenderSystem `pollingEvents` to true and `pollEventsWaitStart` to
`Util.getMillis() - 1000`, then clears `pollingEvents` before B. Original
values are restored in a finally block. This affects only the probe JVM.

The initial attempt failed because ClientPacketListener class initialization
requires Minecraft registries. The successful run calls the real
`SharedConstants.tryDetectVersion()` and `Bootstrap.bootStrap()` before
allocation; the initial failure log is retained separately. Bootstrap does
not launch a game or a rendering window.

## Bytecode facts

The saved javap output establishes:

- `handleKeepAlive` constructs a ServerboundKeepAlivePacket and calls
  `sendWhen` with a one-minute expiry and condition
  `!RenderSystem.isFrozenAtPollEvents()`.
- `sendWhen` sends immediately when that condition is true; it does not first
  flush or check older pending entries. Otherwise it appends to the list.
- `sendDeferredPackets` sends eligible pending entries during iteration and
  drops expired entries that remain ineligible.
- RenderSystem considers polling frozen when polling is active and the
  elapsed wait is greater than 200ms.
- `ClientPacketListener.tick()` calls `sendDeferredPackets`; a direct later
  response can therefore reach `send` before that later drain.

## Reproduction command and raw evidence

From the repository root:

```powershell
python -B .tmp/craftilo-keepalive-probe/run.py
```

The runner only writes its own `.tmp/craftilo-keepalive-probe/` directory.
It compiles and runs using argument files so the full installed classpath is
preserved without shell quoting ambiguity.

- `KeepAliveProbe.java`, `run.py`: exact probe source and runner.
- `javac.args`, `java.args`, `commands.json`: compiler/runtime arguments.
- `compile.log`, `output.log`: warnings and exact five passing outputs.
- `ClientCommonPacketListenerImpl.javap.txt`, `RenderSystem.javap.txt`:
  actual method bytecode.
- `initial-unbootstrapped-output.log`: the earlier initialization failure.
- `input-hashes.json`: all installed input fingerprints.

## What this does not establish

This is induced-state, method-level proof of a possible response reorder at
the Connection.send boundary. It is **not** a reproduction of Craftilo's
disconnect, actual GPU/GLFW polling, resource-pack loading, network delivery,
server validation, concurrent scheduling, or a particular mod interaction.
No real clock stall, render workload, socket or server is involved. Attribution
of the reported disconnect still requires incident timeline/IDs or a focused
client/server observation proving those conditions actually occurred.
