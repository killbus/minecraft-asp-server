# Research: cost of isolating imported adventure maps

Date: 2026-11-20. Scope: evidence gathering only. No production access,
configuration changes, plugin installation, map edits, or new runtime tests.
The active config-bundle task is a historical research container, not an
instruction to implement a proxy migration.

## Decision supported by the evidence

For arbitrary imported maps that must keep their original global command state,
separate persistent server instances are the strongest native boundary. Existing
projects can provide on-demand startup/shutdown; implementing a generic command
virtualization layer inside Paper is not a prerequisite.

This is an isolation decision, not a guarantee of map-version compatibility.
An old map may still need command/data conversion, a compatible Minecraft
version, or validation of Paper behavior even on its own server.

Same-process work is not limited to hiding sidebars: Cosmos on Sponge is a
concrete historical example of per-world scoreboards and command handling.
It is not evidence of complete state virtualization on current Paper. No
reviewed candidate establishes that guarantee for the current Paper 26.2 stack.
This is a bounded research result, not proof that no such project exists.

## Candidate investigations

- [Same-process solutions and counterexamples](map-isolation-same-process.md).
- [Independent instance lifecycle projects](map-isolation-instances.md).
- [Actual Paper/MVI/map scoreboard evidence](scoreboard-world-scope.md).

AutoStartStop's documented Velocity shell/systemd integration is the closest
candidate for a non-container proof of concept. Its beta status and the lack
of a local compatibility test must remain explicit. PterodactylPowerAction
also documents shell integration and waiting-server behavior, but advertises
limited maintenance. AutoStopper is a more container-oriented candidate;
mc-router primarily routes new Java TCP handshakes and does not by itself
replace in-session Velocity server-switch orchestration.

## Existing entry architecture and migration work

The current generated scene demultiplexes Java TCP and Geyser signaling/assets
behind the existing frpc/HAProxy entry. It sends PROXY v2 to Paper; the bundled
Paper configuration expects it. Geyser-Spigot currently lives with that backend.

Geyser's current official setup documentation explicitly supports Geyser-Velocity
with NetherNet and says to install Geyser only on the proxy. Therefore multiple
private backends do not require one public Bedrock listener, domain, or Geyser
installation each. This does not imply the current scene can be reused without
configuration changes or that its exact NetherNet path has been retested.

Velocity exposes `haproxy-protocol` for receiving the outer PROXY header.
Its modern player-information forwarding is a separate authenticated protocol
for UUID/IP/profile information on backend connections. A migration must update
the receiving side, Paper forwarding settings, and shared secrets consistently;
it must not leave Paper expecting the previous direct PROXY-v2 stream.

The current Geyser setup page requires backends to accept Java 26.3 protocol.
It points older backends to ViaVersion. This is a protocol compatibility
requirement, not evidence that the existing Paper 26.2 world must be upgraded.

Remaining integration costs:

1. Preserve Java/offline and Floodgate player identity across the new proxy;
   changing identity rules can select different existing player files.
2. Divide persistent native player/world data and existing MVI profiles between
   backends. Copying a world folder alone does not define inventory, last-login,
   scoreboard, or group-profile migration. Existing global death totals have no
   reliable per-world history to split automatically.
3. Define startup waiting, initial joins versus server switches, readiness,
   concurrent wake requests, failure/timeout fallback, graceful empty shutdown,
   and protection against a new arrival during shutdown.
4. Retain persistent map directories rather than reset-from-template instances;
   integrate backups and ensure a startup hook does not overwrite live state.
5. Validate resource-pack changes, proxy/backend permissions, Java and Bedrock
   rejoin behavior, and existing frpc/TLS/asset routes together.

An extra playable hub is a product choice, not a requirement of state
isolation. An existing running server can provide a waiting destination.
Alternatively the entry can report that a backend is starting and require a
retry. Keeping a client online without any running backend needs an explicit
waiting/limbo mechanism whose protocol compatibility must also be tested.

## Resource cost model and measured limits

Memory while active is approximately the entry/proxy/Geyser/controller overhead
plus each running backend's resident memory. Each backend duplicates JVM,
server, and installed-plugin baseline costs; map/chunk/player workloads add
variable cost. Do not equate `-Xmx` with actual RSS or with a minimum requirement.
Sharing a JAR on disk does not share its full runtime heap across processes.

A backend process that has stopped has no JVM resident memory. Its persistent
worlds and profiles still occupy disk. The ingress and lifecycle controller
remain available to wake it. If two independent maps both have players, both
backends must run; on-demand orchestration does not remove that active cost.

Tick pausing or freezing a process is not the same operation as stopping it.
It may reduce CPU work while leaving the process address space resident. The
current deployment explicitly sets `pause-when-empty-seconds=-1`.

Existing extraction regression logs provide observations, not a comparison of
the proposed architecture:

- `server-run-1.log:75`: Paper `Done (37.020s)`.
- `server-run-2.log:77`: Paper `Done (56.459s)`.
- Recorded Trials `LOAD_START` to `LOAD_OK` intervals were approximately 1--8
  seconds using second-resolution timestamps.
- These were two JVM runs in the existing Windows test environment with
  `-Xms512M -Xmx3G`, already populated caches, and an observed spark timeout
  warning in the second run. They establish neither cold-boot percentiles nor
  a Linux production memory requirement. `Done` alone is not full first-join
  latency, and no resource-pack download is included in those load intervals.

There is no defensible minimum RAM, maximum concurrent-map count, engineering
day estimate, or cost saving percentage from the evidence collected so far.
A bounded proof of concept should measure total host/process RSS (and JVM heap
separately), empty and occupied CPU/tick times, concurrent active maps, startup
through first playable spawn, repeated wake/stop cycles, and graceful-save
latency. Compare actual in-game load, not only an empty-server screenshot.

## Cost interpretation

- A per-world death display is a presentation feature with a limited surface.
- World-qualified death/progress state needs map logic adaptation and tests;
  the prior scoreboard scan is not an audit of all map commands, selectors,
  functions, or global data. Calling the whole Trials conversion cheap would
  go beyond the evidence.
- A universal same-process compatibility layer has an open-ended coverage and
  version-maintenance burden. A plugin's per-world scoreboard feature alone
  does not establish that all map state is isolated.
- Independent instances move most work to known service composition and data
  migration boundaries. Mature proxy foundations exist, but wake/sleep plugin
  maintenance and exact-version compatibility still require acceptance tests.

The recommended next experiment for full map isolation is two persistent
backends behind Velocity with one selected shell/systemd lifecycle controller,
using disposable data and the existing entry design. No production migration
or abandonment of the delivered WorldLifecycle plugin is implied by this
research; that plugin remains relevant to the single-Paper deployment model.

## Primary references

- Geyser official setup, including Velocity and NetherNet:
  https://geysermc.org/wiki/geyser/setup/
- Velocity modern forwarding and Paper backend configuration:
  https://docs.papermc.io/velocity/player-information-forwarding/
- Velocity `haproxy-protocol` and connection timeout configuration:
  https://docs.papermc.io/velocity/configuration/
- Local current entry contract: `.trellis/spec/backend/frpc-scenes.md`.
- Actual test observations: `.tmp/worldlifecycle-extraction/server-run-1.log`,
  `server-run-2.log`, and `validate_live.py`.

Primary pages above were retrieved during this research. Candidate versions,
source revisions, licensing, and limits are recorded in the linked detailed
reports rather than assumed from generic project descriptions.
