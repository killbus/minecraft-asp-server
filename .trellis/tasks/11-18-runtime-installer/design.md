# Design: runtime installer

## Boundary

`verify_runtime.py` already owns the lock grammar, relative-path safety, and
fingerprinting. The installer must not fork those rules: it imports
`read_lock`, `safe_path`, and `fingerprint` from it. Anything the verifier
rejects, the installer rejects with the same exit code 2.

The installer owns only one new decision: how a missing file becomes a
present one. It does not own server startup, world content, or plugin data.

## Flow

```
load lock
for each selected artifact:
    if exists and sha256 == lock.sha256      -> OK
    if exists and sha256 != lock.sha256      -> DRIFT (stop unless --replace)
    if missing and no download_url           -> MANUAL (unresolved)
    if missing and download_url:
        stream to <path>.part.<pid>
        hash while writing
        if hash != lock.sha256: delete part, FAIL
        os.replace(part, path)
```

`--dry-run` stops before any `urlopen` and before any `mkdir`, and prints the
same four verdicts from filesystem state alone.

## Failure semantics

| Condition | Result |
| --- | --- |
| destination directory missing | create parents of the declared path only |
| HTTP error / timeout | FAIL for that artifact, keep going, exit 1 |
| short read or hash mismatch | delete the `.part`, FAIL, leave the destination untouched |
| disk full mid-write | same as above; `OSError` becomes a clean FAIL line |
| lock path escapes `server/` | exit 2 before any network or write |

Sequential downloads are deliberate: the set is small and a failed artifact
must not hide behind concurrent progress output.

## URL pinning

Seven artifacts have no `download_url`. Each candidate must be the exact build
that hashes to the lock entry. The research note records, per artifact:
upstream version/build, direct URL, HTTP status, byte count, SHA-256, and
whether it matches. A version whose published bytes do not match the lock is
reported as a conflict; the lock hash is not rewritten to fit a URL.

Where no pinned URL can be found (a vendor that only serves `latest`), the
artifact keeps no `download_url` and the installer prints `MANUAL`; that is a
truthful result, not a gap to paper over.

## Exit codes

- 0: every selected artifact is present and matches.
- 1: at least one `MANUAL`, `DRIFT`, or download failure.
- 2: invalid lock, unsafe path, or bad arguments.
