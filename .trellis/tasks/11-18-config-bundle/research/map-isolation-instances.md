# Research: on-demand independent Paper instances for map isolation

- Query: What existing open-source tools can start persistent independent Minecraft map servers on demand, stop them when empty, and make the cost acceptable for this deployment?
- Scope: mixed; independent-process orchestration only. No server deployment, SSH, process changes, runtime tests, or player-data changes.
- Date: 2026-11-20 (Asia/Shanghai). GitHub timestamps below are UTC.
- Active task: `.trellis/tasks/11-18-config-bundle`; its original config-bundle PRD is historical context, not an implementation request for this research.

## Findings

### Conclusion

This is an established architecture with existing open-source implementations: an always-running Velocity proxy, persistent Paper directories or volumes, and a controller that starts the selected backend and stops it when empty. It does not require writing a general Minecraft command-state virtualization layer, a cloud platform, or one public port/domain per map.

However, no reviewed project establishes a tested, ready-to-deploy combination of this repository's Paper 26.2, exact plugins, imported Trials map, Floodgate identity, resource-pack transitions, and NetherNet entry. A supported proxy API or a broad Minecraft-version label is not evidence of that complete combination working.

The meaningful shortlist is:

1. **AutoStartStop + Velocity + systemd/shell**: the most directly documented non-container fit. Explicit waiting-server mode and a systemd example. Release maturity and compatibility still need a canary.
2. **AutoStopper + Velocity + Docker**: strongest recent published lifecycle/runtime verification among reviewed candidates; introduces Docker if retained. It owns existing containers, not world cloning.
3. **PterodactylPowerAction + Velocity + shell**: a simpler, directly matching start/wait/transfer/idle-stop implementation, but the author explicitly limits support and no longer uses it in production.
4. **mc-router + a process controller**: strong, actively maintained TCP entry/wake tool; not by itself the equivalent of a Velocity in-session server-switch hook. Prefer it for separately selected server endpoints or as a deliberate backend transport layer, not as a substitute for a switching proxy.

“Existing solution” and “proven mature for our exact stack” must remain distinct. There is enough implemented machinery to conduct a bounded integration test, but insufficient evidence to prescribe a production dependency without that test.

### Three different meanings of sleep

| Mechanism | JVM process | Memory consequence | Re-entry consequence |
| --- | --- | --- | --- |
| Empty-server tick pause / slow ticks | Still alive | Heap, classes, threads, and plugin state remain; lower CPU does not imply released process RAM | Usually resumes without a JVM boot |
| Docker pause / operating-system process suspension | Still alive, execution suspended | Does not release process address space merely by pausing | Resumes that process |
| Graceful Paper shutdown followed by JVM exit / stopped container | Exited | Process memory is released; filesystem cache and controller/proxy memory can remain | Next visit requires a new boot |

World unload in one Paper instance is a fourth, narrower mechanism: it removes selected world state while retaining the server and its global command state. It does not create independent scoreboards or command universes.

For the user's objective of both isolation and releasing inactive-instance RAM, choose actual stop/exit. “Hibernate” in a project title is not evidence of this behavior.

## Candidate details and source evidence

### 1. AutoStartStop: shell/systemd with explicit waiting-server mode

- Official repository: <https://github.com/beyenilmez/autostartstop>
- License: GPL-3.0; repository is not archived.
- Latest GitHub release observed: `v1.1.0-beta`, 2026-01-31T11:36:41Z. The tag contains `beta` even though GitHub's `prerelease` boolean is false. Do not promote it to a stable release merely from that boolean.
- Default-branch HEAD: `b3779e660e3a2ab7cdc5e7a5afd9e679bd447f18`, 2026-07-16T00:45:36Z, dependency-update commit. Repository `pushed_at` is 2026-11-14; this is not the default-branch commit date.
- README states Velocity >=3.4.0 and Java >=21. No end-to-end Paper 26.2/26.3 or Geyser/NetherNet verification was found in the inspected documentation.

The official `start_on_connection` template has four modes: background start, disconnect, hold, and waiting server. Its documentation warns hold mode has a 30-second timeout and recommends waiting-server mode for slower starts. Waiting mode sends the player to a configured server, starts the target, and connects when ready. `stop_on_empty` supplies the empty-period trigger.

The shell control documentation explicitly shows `systemctl start minecraft-survival` and `systemctl stop minecraft-survival`; containers and a panel are therefore optional. The operating-system service remains responsible for correct graceful shutdown, exit status, logs, durable working directory, and permissions. A persistent directory is restarted; a fresh map clone is not intrinsic to this design.

Source corroboration at the pinned HEAD:

- `src/main/java/com/autostartstop/trigger/impl/ConnectionTrigger.java:123`: listens to `ServerPreConnectEvent`, reads the original target, and optionally denies the connection while the configured rule executes. This is a backend-connection hook, covering in-proxy switches rather than only an external TCP login.
- Same file `:216`: release signal allows the waiting-server connection to be released while other rule actions continue.

References:

- <https://github.com/beyenilmez/autostartstop/releases/tag/v1.1.0-beta>
- <https://github.com/beyenilmez/autostartstop/blob/b3779e660e3a2ab7cdc5e7a5afd9e679bd447f18/docs/src/rule-templates/start-on-connection.md>
- <https://github.com/beyenilmez/autostartstop/blob/b3779e660e3a2ab7cdc5e7a5afd9e679bd447f18/docs/src/rule-templates/stop-on-empty.md>
- <https://github.com/beyenilmez/autostartstop/blob/b3779e660e3a2ab7cdc5e7a5afd9e679bd447f18/docs/src/control-api/shell.md>
- <https://github.com/beyenilmez/autostartstop/blob/b3779e660e3a2ab7cdc5e7a5afd9e679bd447f18/src/main/java/com/autostartstop/trigger/impl/ConnectionTrigger.java#L123>

Important qualification: inspected default-branch behavior must be checked against the selected release artifact before installation; it may include changes after `v1.1.0-beta`.

### 2. AutoStopper: recent, verified Docker lifecycle integration

- Official repository: <https://github.com/Criseda/AutoStopper>
- License: MIT; not archived.
- Latest release: `2.3.2`, 2026-11-19T17:13:01Z.
- HEAD: `957b885069ead69efb469114c9ee17a1cd5992df`, 2026-11-19T17:01:51Z.
- README documents one Java 21 bytecode artifact tested with Velocity 3.5.1 and 4.0/4.1/4.2; 4.2.1 is explicitly preview. Velocity 4.x uses Java 25 in its matrix.
- The real backend in its E2E test is **Purpur 1.21.4**. Its broad Minecraft compatibility statement through 26.2 is not the same as an actual Paper 26.2 test. Nothing found establishes 26.3/NetherNet acceptance.

The plugin maps existing Velocity server names to existing Docker containers, merges simultaneous arrivals into a shared lifecycle operation, waits on Minecraft status or Docker health readiness, stops idle containers, and retries failed stops. It does not provision maps from templates. Mounting the map in a persistent host directory or volume retains state across stops.

Source corroboration at the pinned HEAD:

- `src/main/java/me/criseda/autostopper/listeners/ServerPreConnectListener.java:26`: observes backend pre-connect, honors an already-denied result, and delegates managed connections to its lifecycle coordinator. This includes in-session switching.
- `src/main/java/me/criseda/autostopper/docker/EngineApiDockerBackend.java:178`: stop calls the Docker stop API; `:199` sends `POST /containers/{name}/stop`. This is actual stop, not pause. The implementation honors the configured container stop grace period.
- `e2e/README.md:3`: packaged artifact with real Velocity 4.2.0 and Purpur 1.21.4; covers initial/simultaneous joins, readiness, idle stop, restart, never-ready, and failed-stop retry.

The documented approach holds a managed connection until startup/readiness completes. It does not document a separate waiting-world product comparable to AutoStartStop's waiting-server mode. Its examples increase proxy read timeout; client behavior for the exact target versions and Bedrock still needs testing. Long backend startup should not be assumed invisible because a proxy timeout was increased.

Costs peculiar to this candidate: Docker runtime and lifecycle permissions, persistent mount definitions, stop-grace/restart-policy alignment, and possibly its recommended socket-proxy helper. Velocity itself can run outside Docker, but the managed backends are containers.

References:

- <https://github.com/Criseda/AutoStopper/releases/tag/2.3.2>
- <https://github.com/Criseda/AutoStopper/blob/957b885069ead69efb469114c9ee17a1cd5992df/README.md>
- <https://github.com/Criseda/AutoStopper/blob/957b885069ead69efb469114c9ee17a1cd5992df/src/main/java/me/criseda/autostopper/listeners/ServerPreConnectListener.java#L26>
- <https://github.com/Criseda/AutoStopper/blob/957b885069ead69efb469114c9ee17a1cd5992df/src/main/java/me/criseda/autostopper/docker/EngineApiDockerBackend.java#L178>
- <https://github.com/Criseda/AutoStopper/blob/957b885069ead69efb469114c9ee17a1cd5992df/e2e/README.md>
- Release's linked build evidence: <https://github.com/Criseda/AutoStopper/actions/runs/44572837755>. This research inspected its documented reference, not a reproduction of that CI run.

### 3. PterodactylPowerAction: small matching design, limited support

- Official repository: <https://github.com/Quozul/PterodactylPowerAction>. Older Pickaria URLs redirect here.
- License: MIT; not archived.
- Latest release: `1.7.0`, 2025-05-31T15:37:01Z.
- HEAD: `858ecbec1a3872620b7fababecac475d15e5a7f8`, 2026-07-17T11:47:58Z; “Adventure 5 update”.
- README explicitly says support is limited because the author no longer uses it in production, with a version-2 rewrite planned.

Contrary to its name, it can use shell commands instead of Pterodactyl. The lifecycle is directly suitable for persistent maps:

- `ConnectionListener.java:59`: backend `ServerPreConnectEvent`.
- `:73`: a player already connected to another backend stays there while the target starts; only initial entry redirects to the waiting server, or disconnects if none is available.
- `StartingServer.java:47`: one starting operation with waiting players; `:98` creates a connection to the ready target.
- `ShutdownManager.java:109`: empty-server test followed by `stop`.
- `api/ShellCommandAPI.java:28` and `:40`: configured stop/start commands; `:82` runs a command and waits for it to exit.

That last detail matters: configure a bounded service-manager command that starts a managed process and returns, not an indefinitely running `java -jar ...` invocation whose exit means the server has stopped. The stop command must actually stop/save the service; plugin naming alone does not enforce that.

References:

- <https://github.com/Quozul/PterodactylPowerAction/releases/tag/1.7.0>
- <https://github.com/Quozul/PterodactylPowerAction/blob/858ecbec1a3872620b7fababecac475d15e5a7f8/README.md>
- <https://github.com/Quozul/PterodactylPowerAction/blob/858ecbec1a3872620b7fababecac475d15e5a7f8/src/main/java/fr/pickaria/pterodactylpoweraction/ConnectionListener.java#L59>
- <https://github.com/Quozul/PterodactylPowerAction/blob/858ecbec1a3872620b7fababecac475d15e5a7f8/src/main/java/fr/pickaria/pterodactylpoweraction/StartingServer.java#L47>
- <https://github.com/Quozul/PterodactylPowerAction/blob/858ecbec1a3872620b7fababecac475d15e5a7f8/src/main/java/fr/pickaria/pterodactylpoweraction/api/ShellCommandAPI.java#L82>

### 4. mc-router: initial Java connection routing and wake, different abstraction

- Official repository: <https://github.com/itzg/mc-router>
- License: MIT; not archived.
- Latest release: `v1.56.5`, 2026-11-17T14:16:30Z.
- HEAD: `bc9198334912099c9bbdfde986e6b019f14c5a43`, 2026-11-17T14:16:20Z.

The router reads a Java handshake's requested server address and connects to its configured route. It supports stopping/starting Docker containers, Kubernetes scale-to-zero, and **a webhook scaler for static backends**. Thus it does not strictly require containers; a webhook receiver can control local services. It can hold a login during wake, or respond with a configurable “starting” disconnect message so the player retries. It also handles asleep/loading status responses. These are not a waiting world.

- `server/connector.go:350` decodes the Java handshake; `:390` chooses the backend using `handshake.ServerAddress` and protocol next state.
- `server/webhook_scaler.go:93` and `:115` construct up/down operations; the receiver owns process lifecycle.
- Official README says automatic Docker down-scaling gracefully stops the container, while wake can also unpause a container paused by something else. Those are distinct states.

An **edge** mc-router does not see a player selecting `/server trials` inside Velocity: the external TCP connection has not changed. A designed router placed on Velocity's backend connections could observe new backend handshakes, but that is another integration with its own route, forwarding, readiness, connection-count, and timeout contracts. Do not present edge auto-wake as if it already implements internal cross-server selection. Its Kubernetes proxy annotation likewise documents initial route-driven scaling; it does not establish all later proxy switches.

References:

- <https://github.com/itzg/mc-router/releases/tag/v1.56.5>
- <https://github.com/itzg/mc-router/blob/bc9198334912099c9bbdfde986e6b019f14c5a43/README.md>
- <https://github.com/itzg/mc-router/blob/bc9198334912099c9bbdfde986e6b019f14c5a43/server/connector.go#L350>
- <https://github.com/itzg/mc-router/blob/bc9198334912099c9bbdfde986e6b019f14c5a43/server/webhook_scaler.go#L93>

## Alternatives screened out of the primary shortlist

- **Impulse** (<https://github.com/Arson-Club/Impulse>): AGPL-3.0, latest `v0.3.2` 2025-03-16; default HEAD `76afa002adc3e2d0cde2cddd85ee5b0718653c5e` dated 2025-04-30. Has real `ServerPreConnectEvent` handling, Docker and JAR brokers. Persistent directories/volumes are supported, not inherently disposable templates. But official command-broker docs say it should be used with caution/testing and recommend a proper broker for production; JAR inherits its limitations. `CommandBroker.kt:100` uses `Process.destroy()` without a Minecraft-specific stop protocol or waiting for exit there. Docker `stopServer()` actually calls Docker stop even though general config docs loosely say “pause”. Lower priority than candidates with clearer current lifecycle contracts.
- **lazymc** (<https://github.com/timvisee/lazymc>): GPL-3.0, latest release `v0.2.11` 2024-03-16; HEAD `204324f1d0ec9ded20c5985a1b4aba9c74095373` dated 2026-07-16. Real process stop via RCON/SIGTERM and TCP-triggered start. Its documented emulated-lobby feature explicitly says experimental, never use in production, offline mode, and Minecraft 1.16.3–1.17.1 only. That lobby is not a 26.2 solution. README's tiny “~3KB RAM” claim has no suitable reproducible measurement context and is not a capacity estimate for our deployment. See <https://github.com/timvisee/lazymc/blob/204324f1d0ec9ded20c5985a1b4aba9c74095373/docs/join-method-lobby.md>.
- **Server Hibernate / Naptime** (<https://github.com/gvk/MinecraftPluginServerHibernate>): last HEAD 2024-04-11, latest `v1.0` 2023-07-19. `ServerNaptimeMain.java:156` sleeps the server thread and may suspend other threads; this leaves the JVM alive. CPU reduction claims do not prove stopped-instance RAM savings. Not suitable evidence for the requested independent-process sleep budget.
- **Hammock**: no verifiable matching server-lifecycle project was found through the targeted GitHub repository search. Do not recommend a project based on an unverified name. It is not needed to establish feasibility given the concrete candidates above.
- A full cloud/template manager or map-per-session cloning platform adds a provisioning problem this use case has not requested. Existing durable instances with one map environment each are sufficient; no reviewed shortlist requires cloning/resetting the map on every visit.

## Cost evidence and what remains to measure

No reviewed official material supplies a trustworthy comparable benchmark for this deployment's total RAM, cold-join duration, player capacity, or engineering days. Avoid fixed GB-per-map or time-to-implement claims.

The repeatable components explain the costs without invented numbers:

- Always running: existing network ingress, one Velocity JVM, its Geyser/Floodgate deployment where chosen, the lifecycle controller, and any waiting server. A waiting server can be an existing always-running gameplay server or a compatible lightweight limbo; it need not be another full Paper lobby. If initial-join retry is acceptable, a waiting world is optional.
- Per **running** map instance: one JVM, engine classes/native overhead, selected plugins, active chunks/entities, command data, caches, and filesystem work. Two concurrently occupied maps require both processes. A short transition may also run source and target together.
- Per **stopped** map instance: its durable map, player files, configurations, plugin databases, logs, and backups stay on disk. Runtime JAR bytes can be provisioned reproducibly; game state must remain separate. Stopping does not delete progress.
- Per cold activation: JVM initialization, engine/plugin load, world preparation, readiness validation, then player transfer. A server “port open” is not necessarily “safe to enter”; the readiness contract matters.
- Operations: process ownership, bounded graceful stop, startup/stop race handling, simultaneous requests, failure feedback, proxy restart recovery, map-data backups, and one versioned configuration/dependency inventory per distinct backend role. These are present even without Docker.

A useful canary measurement would hold versions, host hardware, JVM options, view/simulation distances, plugins, maps, and test players fixed, then observe:

1. Proxy/controller only, all map backends stopped.
2. One map running idle, then representative gameplay in that map.
3. Both maps occupied, including simultaneous cold starts and a source-to-target switch.
4. Last player leaves, backend saves and exits, and re-entry restores its native scoreboard, inventory/health, location, and world changes.
5. Startup failure, never-ready backend, interrupted join, stop/start overlap, and proxy restart while maps are running.

Record process PSS/RSS and cgroup memory if used, actual live/committed heap separately from `-Xmx`, CPU/MSPT, startup-to-ready and request-to-playable timings, and retained disk growth. On Linux, `/proc/<pid>/smaps_rollup`, process/cgroup metrics and Paper logs provide useful evidence. Compare cold/warm filesystem caches and repeated runs; report ranges and the exact fixture. `-Xmx3G` is a ceiling, not evidence that each instance needs 3 GB.

No such benchmark was run for this research. Historical local Paper startup logs from previous work are useful observations but are not a measurement of the proposed proxy/multi-instance topology.

## Existing repository files and relevant boundary

| File | Description / relevant evidence |
| --- | --- |
| `.trellis/tasks/11-18-config-bundle/prd.md` | Source/secret/instance-state separation; world and player state must not be copied as declarative configuration. |
| `.trellis/tasks/11-18-config-bundle/design.md` | Host-specific runtime state and template boundary; not a multi-instance implementation design. |
| `.trellis/spec/backend/frpc-scenes.md` | Existing shared TCP ingress, NetherNet media/signaling, and paired PROXY configuration contracts. |
| `scripts/scenes/frpc-shared-tcp.sh:483` | Generated shared ingress frontend. |
| `scripts/scenes/frpc-shared-tcp.sh:520` | Current Java backend targets Paper, with optional generated `send-proxy-v2` at `:450`. |
| `config/config/paper-global.yml:111` | Current Paper PROXY protocol enabled; Velocity forwarding disabled. |

Moving the Java endpoint to Velocity requires matching the receiver and backend identity-forwarding configuration. It is not just starting one more process. This sub-research did not re-verify Geyser's current Velocity/NetherNet support; the main research thread owns that evidence. None of these Java lifecycle project READMEs proves the complete Bedrock/NetherNet path, so do not infer that from their Java wake claims.

## Caveats / Not Found

- This is a source/documentation investigation, not installation or acceptance testing.
- Official GitHub API repository metadata, latest releases, commit endpoints, and raw source at the listed SHAs were read live. `updated_at`/`pushed_at` are not substitutes for the default-branch maintenance date.
- Default-branch documentation may describe behavior newer than the latest release; pin the actual artifact in any future canary.
- “Per-map independent process” isolates engine-local state only if persistent directories and stateful plugin stores are also independent; deliberately shared database plugins can reintroduce shared state.
- Supporting a proxy runtime, supporting Java protocol versions, and having verified the exact Paper+map+plugin+Bedrock stack are different claims.
- No service was started/stopped, no configuration was changed, no remote host was accessed, and no player data was written.
