# Commit Discipline

> Rules for commit boundaries: what goes in one commit, when to amend,
> when to split.

---

## Core Principle

A commit is one **logical unit of change** that a reviewer can understand
and revert independently. Fragmentation (one concern per tiny commit for
cosmetic reasons) is noise; bundling unrelated changes is worse.

## Commit Boundaries

- One commit = one concern: a feature, a fix, a doc set, a refactor,
  or a scaffolding bootstrap. "Scaffolding + the doc that describes the
  system it bootstraps" may share a commit when the doc exists only for
  that system.
- Never mix user-owned changes (made outside this session) with your own
  edits in the same commit.
- Binary/runtime artifacts belong in `.gitignore`, not in commits, unless
  the artifact *is* the deliverable (e.g. a generated release bundle).
- Commit message: imperative, <= 72 chars, `type: summary` (docs:, fix:,
  feat:, chore:, ops:). Body only when the why is non-obvious.

## When to Amend

Amend is allowed when **all** of these hold:

1. The target commit is the most recent commit (HEAD).
2. It has not been pushed to a shared remote.
3. The change belongs to the same logical unit as that commit
   (follow-up doc fix for the same doc, missed file, message correction).

Typical amend cases:
- Adding a section to a doc committed minutes earlier in the same turn.
- Adding a file the commit's stated purpose already covered.
- Fixing the commit message wording.

Do **not** amend:
- A pushed commit (use a follow-up commit or ask before rebase).
- A commit whose logical unit is already closed and reviewed.
- To hide mistakes from history when an honest follow-up commit is clearer.

## Anti-Fragmentation

- If you would produce >3 commits in one short turn and they are all
  variants of "finish the same doc/config", merge them into one logical
  commit via amend.
- Batch related micro-edits (typo in the same doc, small index update
  that registers that doc) into the same commit.

## Verifying Boundaries Before Committing

1. `git status --porcelain` - review every path that will be staged.
2. Ask: can each staged path be explained by the one-sentence commit
   summary? If no, split or reword.
3. Confirm `.gitignore` covers runtime/generated output before
   `git add -A`; never stage `server/`, build outputs, or scratch dirs
   by accident.

## Message Boundaries: Contract vs. Instance

A commit subject names the **contract boundary that changed**, never the
**instance that exercised it**. This is the first-principles rule behind the
gate; the hook only enforces its mechanical cases.

| Boundary | Scope | Subject talks about | Example |
| --- | --- | --- | --- |
| Runtime / engine | `server`, `runtime`, `plugins` | jars, plugins, launch/backup scripts, world registration, loading policy | `feat(server): replace ASP with Paper + Multiverse world switching` |
| Map content | `world` | a concrete map, its import, crop, regions, chunks, artifact identity | `feat(world): import the trials crop` |
| Tooling | `scripts`, `tests` | importers, verifiers, test harness | `fix(scripts): reject unsafe artifact paths` |
| Docs | `docs`, `sop` | operator docs | `docs(sop): document login destination` |

Forbidden couplings:

- A runtime subject that foregrounds a map instance, e.g.
  `feat(world): run the adventure map on Paper + Multiverse`. The runtime
  change is `server`; the map is the instance being run.
- A content subject that claims runtime capability, e.g.
  `feat(server): import trials`.
- Counts, byte sizes, and hashes in the subject (`47 regions`,
  `644 chunks`, `294 files`, `e3896e8d...`). These are measurements of one
  instance; put them in the body under the content boundary.

When one change genuinely spans boundaries, split it. If it cannot be split,
the subject names the primary contract and the body gets one section per
boundary, with instance facts confined to the content section.

### Enable the gate

```sh
git config core.hooksPath .githooks
python -B -m unittest tests.test_check_commit_message -v
```

The `commit-msg` hook rejects unknown types/scopes, instance metrics and
hashes in the subject, and scope/token mismatches (`world` + runtime tokens,
or `server`/`runtime`/`plugins` + content tokens). `--no-verify` is reserved
for a documented exception, not for convenience.
