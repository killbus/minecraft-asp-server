# Design: retain deployment contracts on native single-world startup

## Source and target

Target `feat/single-world-start` starts at published `92aa420`, whose parent
is the pre-Multiverse `10c794e`. Main `e1d12bf` supplies the later deployment
work. The frozen integration branch is not a source for this port.

Apply selected source commits without committing intermediate states, resolve
their dependencies against the single-world baseline, and commit the reviewed
result with source provenance. Preserve the published branch history. Leave
main and the integration freeze tag unchanged.

## Contracts

- The runtime lock keeps plain Paper and existing independent plugins. The
  installer and verifier share artifact parsing, path checks and pinned hashes.
- The configuration manifest contains source templates only. A positive set of
  configuration roots and destination save checks protect arbitrary named saves.
  Host settings remain ignored deployment inputs and enter offline backups.
- Native `server.properties` consumes the existing `PACK_URL` key. An explicit
  empty value offers no pack; a nonempty URL retains HTTPS/loopback validation.
  There is no per-world plugin, resource-pack registry or startup profile.
- Both frpc scene entrypoints forward an optional `--world NAME` to the existing
  launcher, validating it before lifecycle effects. Transport remains the main
  branch's shared TCP/TLS pipeline, including PROXY alignment and packs sidecar.
- Offline snapshots retain discovery of every top-level native save. Restoring
  later backup features must not regress to copying only `world/`.

## Deployment boundary

Code and fixture tests use only this worktree. No server process is restarted,
no production host is accessed, and no player or map data is converted. Git
switching does not remove ignored plugin binaries; operator guidance explicitly
addresses obsolete world-manager JARs and complete native save preparation.

The active guide is `docs/SINGLE-WORLD-SOP.md`. Old task records are historical
source provenance, not the current deployment contract.
