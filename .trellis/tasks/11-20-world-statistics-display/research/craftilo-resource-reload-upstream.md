# Research: Upstream keepalive ordering, related fixes, and applicability

- Query: Is the observed Paper 26.2 keepalive out-of-order disconnect a known upstream regression, and is there a verified 26.2/26.3 client or server fix?
- Scope: public primary-source evidence, existing locally verified incident/probe results; read-only outside this report.
- Date: 2026-11-20
- Previous report: `craftilo-resource-reload.md` in this directory contains exact runtime bytecode, hashes, and the first incident timeline. Those disassembly details are not repeated here.

## Findings

### Current evidence and recommendation

There is now a **real, unmodified Minecraft 26.2 method-level reproduction** of a later keepalive response overtaking an older deferred response. This strengthens the vanilla-client mechanism beyond static code speculation. It still does not prove that GLFW window-event polling froze during either real incident, nor that this exact method ordering produced those wire packets.

Public Paper sources explain why multiple outstanding challenges now exist: more frequent sampling and a five-second average improve reported latency. The implementation additionally imposes FIFO reply ordering and disconnects immediately when a known later challenge is answered first. The retrieved patch rationale does not separately justify immediate disconnection for a valid, still-pending out-of-order response.

No verified applicable 26.2/26.3 fix is established by this research. In particular, do not recommend increasing the elapsed timeout as a remedy for the out-of-order branch, installing a mod solely because its name mentions timeout/packets, or upgrading solely to obtain a listener-handoff fix already present in the runtime.

### A second real incident removes identity/prototype assumptions

Root supplied, and this research independently read, the current manual runtime log:

| Time | Event |
| --- | --- |
| 14:53:59 | `Snorlax was kicked due to keepalive timeout!` — elapsed-time expiry, separate event. |
| 14:56:40 | `/wl enter world resume`; formal `MultiverseWorldLifecycle` logs `WL ENTER_OK Snorlax world=world mode=resume`. |
| 14:56:42 | `Disconnecting Snorlax for sending keepalive response (28087380) out-of-order!`. |
| 14:56:49 | Idle unloading of `trials` starts after the disconnect. |

Source: `.tmp/world-lifecycle-manual/runtime/logs/latest.log:119` and `:143` through `:151`, as read on 2026-11-20. Logs are rotatable. The first incident was Craftilo, ID `20969934`, at 12:58:05 under the prototype; this recurrence uses a different player and the formal plugin. Therefore neither Craftilo's identity nor the prototype alone explains the fault. The post-disconnect idle unload is not the trigger for the preceding rejection.

Root also read Snorlax's corresponding client log: 14:56:40 entered world and began a reload without the server pack; 14:56:42–43 atlas work; 14:56:43 client reported `Timed out`. Thus the resource-removal correlation recurs across both identities; its precise causal link remains unproven.

### Paper change and intended behavior

Primary source retrieved during the first research pass on the same date:

- [Paper `0015-Improve-keepalive-ping-system.patch`](https://github.com/PaperMC/Paper/blob/main/paper-server/patches/features/0015-Improve-keepalive-ping-system.patch).
- The patch header identifies author Spottedleaf and original patch date **2025-06-24**.
- Its stated purpose is: send more keepalives for more accurate latency calculation; track all pending challenges because several can be in flight; replace the latency calculation with an average over the previous five seconds.
- Actual logic sends once per second, records all outstanding IDs, accepts the head ID, and rejects a later matching ID as `out-of-order!`.
- The first report's direct comparison found the local Paper 26.2 build 135 bytecode matches that sequence logic.

This establishes deliberate multiple-in-flight bookkeeping. It does **not** establish that the author considered the modern vanilla client's `sendWhen` deferral path or that observed response inversion is intentional cheating behavior. A strict FIFO policy can conflict with application-level response scheduling even though TCP itself preserves bytes in order. TCP ordering does not prove a client generated replies in the same order as requests.

The historical feature source cited by the 2025 report is [Paper commit a5f2f61's feature patch](https://github.com/PaperMC/Paper/blob/a5f2f6140d4cf144d64b3de5f60530ac07965cb7/paper-server/patches/features/0032-Improve-keepalive-ping-system.patch). It establishes that this policy already affected Paper 1.21.8. A complete commit-by-commit history was not obtained in this follow-up; do not claim the first shipped build or introduction PR number.

### Related issue: legacy ViaRewind clients

Primary source [Paper #12888](https://github.com/PaperMC/Paper/issues/12888), including its comments, was retrieved in the first research pass:

- Reported Paper 1.21.8 build 11 with a **1.8.8 client through ViaVersion/ViaBackwards/ViaRewind**.
- Reproduction deliberately caused client stutter with 3D Anaglyph; the logged rejection is the same `out-of-order!` diagnostic.
- The reporter said it did not happen on a 1.12.2 client, and discussion directed the issue toward ViaVersion when current-version clients were not affected.
- The reporter also said Purpur's `use-alternate-keepalive` did not resolve that case.

This confirms the new policy has produced legitimate-client compatibility reports. It is counterevidence against automatically attributing every such message to the modern vanilla `sendWhen` path: the same diagnostic can arise through an older client/protocol bridge. It is not a verified fix or a matching version matrix for this incident. There is no basis to remove ViaVersion here merely from that historical report.

### Related fix: reconfiguration listener handoff

Primary source [Paper PR #13712](https://github.com/PaperMC/Paper/pull/13712) describes a different precise mechanism:

1. PLAY listener sends A.
2. The connection changes to CONFIG while A is pending.
3. The next listener inherits A, sends B, and sees B's response while still waiting for A.
4. Paper rejects the response.

The change uses `KeepAlive.copyForListenerHandoff()` to preserve timing/latency history but reset pending challenges at that protocol boundary. The actual local runtime already contains that behavior. Ordinary same-server world teleport plus resource-pack pop does not by itself demonstrate a PLAY→CONFIG transition. Without a trace showing such a transition and a regression in the reset behavior, this is not an applicable missing fix.

### Client mechanism: stronger local evidence, limited external attribution

Root's completed report [craftilo-keepalive-probe.md](craftilo-keepalive-probe.md) calls the actual installed 26.2 client methods without Fabric or mods:

- Induced frozen event-poll state: A goes into the real deferred queue.
- Clear the event-poll frozen flag, deliver B before draining: B reaches `Connection.send` first.
- Invoke the real queue drain: A follows.
- Public `handleKeepAlive` case observed IDs `[402, 401]`; controls drained A first or kept both unfrozen and preserved order. All five method-level cases passed.

This is a constrained experiment, not a full-client reproduction. The test controls state and invocation order; it does not cause an actual OS window freeze, resource-pack reload, concurrent render/Netty scheduling, or server disconnect. The incident connection still needs observations tying the induced ordering to actual request/reply IDs.

Root additionally reports that the locally installed **26.3** client has the same direct-send-on-true `sendWhen` shape. The inspected 26.3 artifact SHA-256 is `4508d006323f24fa02876310c192d739af56516eb259000ac50f0909a68c9a2d`. That is evidence against claiming a routine 26.3 client upgrade removes this mechanism. Root owns the exact 26.3 comparison; this researcher did not independently repeat it.

Root's bounded local mod survey found no references to the named keepalive/deferral/event-poll methods in 93 scanned archives / 7,545 classes, and the reviewed Fabric common-listener mixin concerned custom payload handling. This reduces one obvious mod-specific hypothesis but is not an audit of transformed classes or proof all indirect modifications are absent.

### Timeout setting and timeout-named mods

The [official Paper property reference](https://docs.papermc.io/paper/reference/system-properties/#paperplayerconnectionkeepalive), retrieved in the first pass, documents a default of 30 seconds for the keepalive response wait limit. Its scope is elapsed waiting, not FIFO acceptance.

[Paper #921](https://github.com/PaperMC/Paper/issues/921) is an old resource-pack timeout report from the 1.12 era. It is a precedent for long pack loading interacting with elapsed timeouts, not proof about the current out-of-order branch.

This follow-up did not obtain applicable primary-source implementations or versioned releases for Debugify, PacketFixer, or TimeoutFix. Their names and general descriptions are insufficient evidence. An applicable candidate must show that it preserves reply order or changes the specific frozen-event-poll deferral path; merely extending socket/read/keepalive deadlines cannot solve the observed immediate FIFO rejection. No such mod is recommended or installed based on this report.

## Counterevidence and unanswered questions

- A pack reload can occur without `RenderSystem.isFrozenAtPollEvents()` becoming true. The predicate is specifically a GLFW polling stall over 200 ms; generic texture upload cost is not enough to establish it.
- Real game-tick drain may run before the next challenge, as shown by the successful control; inversion depends on timing and is not inevitable whenever a pack changes.
- A later pending ID at the server proves response ordering disagreed with its queue. It does not alone locate where the discrepancy originated.
- Two player identities and two lifecycle plugin generations reproduce the symptom, reducing a player-specific/prototype-only explanation but not proving all client mods or server protocol plugins irrelevant.
- No established Mojang bug ID, accepted current-version Paper issue, or maintained 26.2/26.3 patch for this exact modern-client inversion was verified in this bounded pass.
- No direct public report proving that running two client instances triggers this precise path was verified.

## Bounded next step

The most useful next fact is a single request/reply trace correlated with the actual window-event freeze and queue drain. If a passive trace is undecodable, a disposable observed reproduction can instrument only challenge IDs, responses, deferred queue/drain, and the frozen predicate. Keep the real session and resource policy unchanged until this evidence distinguishes an applicable client ordering correction from server-side tolerance. Increasing a timeout should only be assessed against the separate elapsed-time incidents.

## Sources, access, and search limitations

This report uses public primary sources successfully fetched in the immediately preceding research pass and explicitly linked above; it does not claim new successful upstream searches where they failed.

Follow-up search ledger:

| Source | Query / operation | Attempts and result |
| --- | --- | --- |
| OpenCLI live registry/help | Confirm GitHub adapter availability | Preflight only; current registry offers `github/login` and `github/whoami`, no search/code/history adapter. No login/browser operation executed. |
| GitHub API through shell | Planned `repo:PaperMC/Paper keepalive`, exact `"out-of-order" "keepalive"`, feature-patch commit history | Two escalation submissions (one allowed retry), neither executed because automatic approval review timed out. No search results claimed. |
| GitHub API through ordinary sandbox | `repo:PaperMC/Paper keepalive` | One request failed TLS authentication; no results. |
| Google OpenCLI | Read live search help | Preflight only, zero searches; did not use a browser route to circumvent the blocked shell request. |
| Root's public `functions.web_search` | Two bounded keepalive-ordering upstream queries | Root reports provider found nothing / fallback allowance exhausted; no new retrieved evidence. |

Automatic approval timeouts are operational limitations, not findings that a public read is unsafe. Root's separately exposed web-search tool also produced no new evidence; further blocked searches were stopped. Absence of an applicable fix in this report must not be read as exhaustive proof that none exists.

## Related Specs

- `.trellis/spec/backend/multiverse-player-state.md`: preserve component ownership; neither network sequencing nor resource reload belongs in the statistics or lifecycle persistence implementation.
- `.trellis/tasks/11-20-world-statistics-display/prd.md`: preserve the manual user runtime; an unrelated display rollout does not authorize speculative client/network changes.
