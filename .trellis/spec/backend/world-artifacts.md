# World Artifacts and Imports

> Executable contract for immutable map artifacts and their rebuild/verify tools.

---

## Scenario: Regenerable Anvil artifact for the Trials map

### 1. Scope / Trigger

This spec applies when changing:

- `artifacts.lock.json`
- `scripts/import_trials.py`
- `scripts/verify_artifacts.py`
- `tests/test_import_trials.py` / `tests/test_verify_artifacts.py`
- the crop range or source-map assumptions in `docs/PAPER-WORLD-SOP.md`

It is triggered because the scripts expose command signatures, a lock-file
format, a path-safety boundary, and exit-code contracts used as a gate.

`artifacts/` is immutable input, gitignored, and never edited in place. The
live Paper world is a copy; restoring means re-running the importer or copying
the artifact while the server is stopped.

### 2. Signatures

```sh
python -B scripts/import_trials.py --source <map-root|.rar> \
    [--dest artifacts/trials-legacy] [--lock artifacts.lock.json] \
    [--prune] [--no-verify]

python -B scripts/import_trials.py --verify-only \
    [--dest artifacts/trials-legacy] [--lock artifacts.lock.json]

python -B scripts/verify_artifacts.py \
    [--root <repo-root|backup-root>] [--lock <lock-file>]
```

`--verify-only` and `--prune` are mutually exclusive.

### 3. Contracts

Artifact layout (paths inside `--dest`):

```text
region/r.<x>.<z>.mca
entities/r.<x>.<z>.mca
poi/r.<x>.<z>.mca
data/minecraft/...
data/...
level.dat
icon.png
```

Crop contract: `x=-5..0`, `z=-1..6`. All three chunk kinds are copied for every
present coordinate. Dimension-local `data/minecraft/*` wins over root `data/*`
for the same relative path. `r.-1.3` and `r.0.3` are inside the crop; their 644
chunks without a root `DataVersion` are genuine pre-1.13 data. Paper's lazy
DataFixer upgrades them on first access, so excluding them is wrong.

Lock contract (`artifacts.lock.json`):

```json
{
  "schema_version": 1,
  "artifacts": [{
    "name": "trials-legacy",
    "path": "artifacts/trials-legacy",
    "kind": "minecraft-anvil-crop",
    "files": 294,
    "bytes": 367030497,
    "treeSha256": "<sha256 over 'sha256  relative/path' lines>",
    "dataVersion": { "min": 922, "max": 4903, "missingRoot": 644 },
    "rebuild": { "tool": "scripts/import_trials.py", "regionCrop": { "x": [-5, 0], "z": [-1, 6] } }
  }]
}
```

`files`, `bytes`, and `treeSha256` are the identity. Descriptive metadata such
as `dataVersion` may be corrected only when the identity is re-verified
afterwards. The rebuild must be idempotent: a second run reports
`copied=0 unchanged=<files> pruned=0`.

Exit codes for both scripts: `0` = match/success, `1` = drift or missing
artifact, `2` = invalid lock, unsafe path, unusable source, or filesystem
failure. Errors go to stderr as `ERROR: ...`, never as a traceback.

Path safety: every lock path is resolved under `--root` and rejected if it
escapes through `..`, a symlink, or a junction. `--prune` only removes paths
under `region/`, `entities/`, `poi/`, `data/`, `level.dat`, and `icon.png`;
anything else is reported and left in place.

### 4. Validation & Error Matrix

| Condition | Result |
| --- | --- |
| Lock matches tree | `OK <name>`, exit 0 |
| Same file count, different bytes/hash | `DRIFT <name>`, exit 1 |
| Artifact directory missing | `DRIFT`/error, exit 1 |
| Lock missing or malformed | `ERROR`, exit 2 |
| Lock path escapes root | `ERROR`, exit 2 |
| Destination inside source (or vice versa) | `ERROR`, exit 2 |
| Source has no map root | `ERROR`, exit 2 |
| Locked file/collision during copy | `ERROR: filesystem operation failed`, exit 2 |

### 5. Good / Base / Bad Cases

- Good: rebuild from the untouched source reports `copied=0 unchanged=294` and
  the documented hash.
- Base: first rebuild into an empty destination copies all files; a second
  rebuild changes nothing and preserves mtimes.
- Bad: hand-editing a file inside `artifacts/trials-legacy` to "fix" a chunk,
  or updating `treeSha256` by hand to silence the drift.

### 6. Tests Required

- Crop: out-of-range regions are not copied; `r.-1.3` / `r.0.3` are copied;
  dimension-local data wins.
- Idempotency: second run reports `copied=0`, tree hash unchanged, mtime kept.
- Prune: in-scope extras are removed only with `--prune`; out-of-scope extras
  survive.
- Lock: OK then deliberate byte change produces `DRIFT` and exit 1.
- Safety: unsafe lock path, destination-inside-source, missing lock, and a
  simulated `OSError` all return exit 2 with an `ERROR:` line and empty stdout
  expectations where applicable.

### 7. Wrong vs Correct

Wrong:

```python
destination.joinpath(relative).write_bytes(source.read_bytes())
```

Correct:

```python
temporary = target.with_name(target.name + ".import-tmp")
shutil.copy2(source, temporary)
os.replace(temporary, target)
```

The first can leave a half-written `.mca`; the second is atomic and preserves
metadata. Similarly, never relax the verifier to make a dirty artifact pass —
regenerate it from the source instead.
