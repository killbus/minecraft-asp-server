# Runtime Inventory

> Executable contract for `runtime.lock.json` and the two commands that read it.

---

## Scenario: Installing and checking the server runtime

### 1. Scope / Trigger

Applies when changing:

- `runtime.lock.json`
- `scripts/verify_runtime.py`
- `scripts/install_runtime.py`
- tests that exercise either command

The lock describes files under `server/`, which is gitignored. Git delivers
the declaration, never the binaries.

### 2. Contracts

- The lock is the single source of truth. A file is "installed" only when its
  SHA-256 equals the recorded value.
- `verify_runtime.py` is read-only. It never downloads, adopts a hash, rewrites
  the lock, or starts the server.
- `install_runtime.py` is the only writer. It creates only the parents of a
  declared path, writes a sibling `.part` file, verifies the digest, and
  renames with `os.replace`. It never touches `world/`, configs, or plugin
  data.
- Both commands share one lock grammar and one path-safety rule: the installer
  imports `read_lock`, `safe_path`, and `fingerprint` from the verifier rather
  than re-implementing them.
- `download_url`, when present, is a build-specific artifact for the locked
  version. `latest` and `lastStableBuild` are forbidden: they cannot reproduce
  a hash.
- HTTP requests carry a descriptive User-Agent with the repository URL.
  PaperMC answers 403 to a generic or contact-less agent, and that failure
  looks like a broken URL otherwise.
- A present file that differs is `DRIFT` and is not replaced without
  `--replace`. A URL that serves different bytes is a failure, never a reason
  to rewrite the lock.

### 3. Status Vocabulary

| Status | Meaning |
| --- | --- |
| `OK` | present and matching |
| `INSTALL` | missing, downloaded, verified, renamed |
| `DRIFT` | present with different bytes |
| `MANUAL` | missing and no `download_url`; `source` is printed |
| `FAIL` | download or write failed; no destination file remains |

Exit codes: 0 = no unresolved artifact, 1 = any `DRIFT`/`MANUAL`/`FAIL` (and,
under `--dry-run`, `INSTALL`), 2 = invalid lock, unsafe path, or bad arguments.

### 4. Forbidden Patterns

- Writing to the URL's basename instead of the lock `path`; upstream names
  differ for several plugins.
- Falling back to a "latest" endpoint when a pinned build disappears. A 404 is
  the truthful result; substitute nothing.
- Rewriting a lock hash so a convenient download passes.
- Creating `plugins/<name>/` data directories, editing configuration, or
  scanning/altering `world/`.
