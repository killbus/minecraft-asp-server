# Implementation plan

## 1. Research (blocking)

Write `research/urls.md` with one row per artifact: id, version/build,
candidate URL, HTTP status, bytes, SHA-256, matches lock, notes. Download each
candidate outside the repository, never into `server/`.

Stop and report if a candidate cannot be matched to the recorded hash.

## 2. Lock

`runtime.lock.json`: add `download_url` to the artifacts that have a verified
match. Change nothing else - no hash, no version, no path, no note.

## 3. Installer

`scripts/install_runtime.py`:

- argparse: `--lock`, `--server-dir`, `--only` (append), `--dry-run`,
  `--replace`.
- import the verifier's `read_lock`, `safe_path`, `fingerprint`.
- per-artifact status line: `OK`, `INSTALL`, `DRIFT`, `MANUAL`, `FAIL`.
- summary line and exit code per the design.
- `urlopen` with a timeout; write in chunks; hash incrementally; `os.replace`.

## 4. Tests

`tests/test_install_runtime.py`, standard library only:

- local `ThreadingHTTPServer` serving fixture bytes;
- empty destination installs and verifies;
- matching destination is skipped without a request;
- drift refuses; `--replace` fixes it;
- wrong bytes on the wire leave nothing behind;
- URL-less artifact reports `MANUAL` and exit 1;
- `--dry-run` makes zero requests;
- unsafe lock path exits 2.

## 5. Docs

`docs/ASP-SOP.md` install/upgrade section: the command, its exit codes, and
the fact that `MANUAL` entries are expected where no build-specific URL
exists. Note that it does not touch worlds or configs.

## 6. Verification

```sh
python -m unittest tests.test_install_runtime -v
python -m unittest tests.test_verify_runtime -v
python -B scripts/install_runtime.py --dry-run ; echo $?
```

Then, on a host with an empty `server/`, a real run followed by
`python -B scripts/verify_runtime.py`.
