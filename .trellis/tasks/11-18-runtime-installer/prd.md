# Install the pinned runtime from the lock

## Goal

`runtime.lock.json` declares every server, plugin, and datapack file with a
SHA-256, but the repository can only check an installation, not create one:
`scripts/verify_runtime.py` is read-only. A host that still runs the old ASP
server cannot be moved to Paper by `git pull`, because `server/` and `*.jar`
are ignored and must be installed out of band.

Deliver a provisioning command that materialises the locked runtime, and make
the lock complete enough for that command to work unattended.

## Requirements

- R1. Every artifact in `runtime.lock.json` carries a concrete
  `download_url` for the locked version and build. `latest` and
  `lastStableBuild` endpoints are not acceptable.
- R2. The URL's content must hash to the `sha256` already recorded for that
  artifact. A candidate that does not match is reported, not adopted.
- R3. New `scripts/install_runtime.py`:
  - reads the lock and reuses the path/URL validation in
    `scripts/verify_runtime.py` rather than re-implementing it;
  - present and matching -> `OK`, skip;
  - present and different -> refuse with `DRIFT`, unless `--replace`;
  - missing and downloadable -> download to a temporary file, verify the
    SHA-256, then atomically rename into place;
  - missing and not downloadable -> `MANUAL` with the `source` URL;
  - `--dry-run` prints the plan and touches neither the network nor the disk;
  - `--only ID` (repeatable), `--lock`, `--server-dir`, `--replace`.
- R4. The command writes only the locked paths. It never creates plugin data
  directories, never edits configs, and never touches `world/`.
- R5. Exit codes match the verifier's vocabulary: 0 = every artifact present
  and matching, 1 = at least one unresolved artifact, 2 = invalid input.
- R6. A failed or truncated download leaves no file at the destination and no
  stray `.part` behind.

## Acceptance Criteria

- [ ] `runtime.lock.json` has a `download_url` on all 11 artifacts, each
      verified against the recorded hash in this task's `research/`.
- [ ] Unit tests (local HTTP server only, no external network) cover: install
      from empty, skip when matching, refuse drift, `--replace` after a
      verified download, `MANUAL` for a URL-less entry, `--dry-run` making no
      request, a hash-mismatched response leaving nothing behind, and an
      unsafe path from the lock.
- [ ] `python -B scripts/install_runtime.py --dry-run` lists every artifact
      and exits 1 while `server/` is empty.
- [ ] After a real install, `python -B scripts/verify_runtime.py` exits 0.
- [ ] Existing `tests/test_verify_runtime.py` stays green.

## Notes

- The operator still supplies the world, configs, and plugin data; this
  command only installs files the lock describes.
- The lock is the single source of truth for what "installed" means.
