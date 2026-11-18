# Implementation plan

## 1. Classification

Walk `server/` and write `research/inventory.md`: every file with its class
and, for source files, whether it needs a placeholder. The list in `prd.md`
is the starting point; add anything discovered.

## 2. `config/` tree

Copy the source files from `server/`, replace secret or host values with
`${NAME}`, and keep bytes otherwise identical. `config.lock.json` records
`path`, `class`, `sha256` of the template, and `placeholders` (the names it
needs).

## 3. `scripts/apply_config.py`

- `--config-dir` (default `config`), `--lock`, `--server-dir`, `--set NAME=VALUE`
  (repeatable), `--settings`, `--dry-run`, `--check`.
- values from `--set` first, then `--settings`, then the environment, then
  the manifest default. A settings key no template declares is refused.
- a settings value written `env:NAME` is read from the environment; an unset
  variable is refused rather than rendered blank.
- import `safe_path` from `verify_runtime`.
- class check against an explicit instance-pattern list, not only the
  manifest, so an edited manifest cannot smuggle `worlds.yml` in.

## 4. Tests

`tests/test_apply_config.py`: render, missing value, unknown placeholder,
unescaped `${` in a value, instance path, path escape, hash drift, dry-run,
check, settings precedence, `env:` resolution and refusal, and a round-trip
against a fixture `server/`.

## 5. Docs

- `docs/PAPER-WORLD-SOP.md` section 7: three classes and what may be copied.
- `docs/ASP-SOP.md`: deploy flow for a host.
- `settings/README.md`: the file shape, what may be a literal, and why a
  credential is only ever `env:NAME`.
- `.trellis/spec/backend/runtime-inventory.md` or a sibling: the apply
  contract, since it shares the lock/manifest discipline.
- Remove the two claims that a rollback copy exists at
  `server/.rollback/asp-<timestamp>/` (`docs/ASP-SOP.md` header,
  `docs/PAPER-WORLD-SOP.md` section 7a): no such directory exists on the
  host. State the actual position — the ASP engine is gone and there is no
  rollback copy — rather than describing a path an operator will look for
  and not find.

## 6. Verification

```sh
python -m unittest tests.test_apply_config -v
python -B scripts/apply_config.py --dry-run
```

Then apply into a scratch `server/` and diff against the real tree after
rendering with the values recorded for this host.
