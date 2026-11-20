# Independent review

Reviewed the shared backup schema, fixed host-file consumer, Bash/CMD backup
entrypoints, native PowerShell cleanup, example, regressions and current
SOP/specs. Review and fixes stayed in the single-world-start worktree. No live
server, production connection, root-checkout change, staging or commit occurred.

## Findings fixed

- `scripts/backup_settings.py`: Windows native reserved names such as `COM1`,
  stream components such as `bad:stream`, and trailing dot/space aliases passed
  preflight. An invalid mirror could therefore fail after the primary copy had
  begun. Refuse native invalid components before emitting any target. This
  applies on Windows, including Git Bash, without rejecting POSIX literal colon
  paths. Five failing pre-fix cases now pass; both CMD and Windows Bash have
  no-first-copy integration regressions.
- `scripts/backup_settings.py`: `abspath` erased `..` before checking ancestors,
  hiding a link in a raw source path subsequently consumed by the shell. Check
  lexical ancestors first, then resolve. A regression rejects linked-parent
  traversal while retaining ordinary `server/../backups` resolution.
- During coordinated review, the implementer hardened timestamp ownership:
  failed directory creation does not adopt an existing snapshot, cleanup tracks
  only this invocation's partial directory, and pruning failure preserves a
  newly completed snapshot on both platforms. The implementer also fixed LF
  output for Windows Python consumed by Bash and made deletion-tree walk errors
  fail closed. Final tests exercise these paths.

## Findings not fixed

None remaining within scope. Target validation precedes path emission/copy;
all target/source overlap, duplicate/nested destination and link checks remain
in the backup consumer. Shared-schema loading by renderer/startup does not
inspect backup disks or resolve unused credentials. Timestamp collision refusal
leaves the existing snapshot untouched. Windows deletion uses native literal
PowerShell paths end-to-end, and POSIX cleanup validates contained timestamp
paths before removal. Retained snapshot contents are inspected only when that
snapshot is being considered for deletion, not on every backup invocation.

## Verification

Final combined affected-suite run, performed by the implementer after review
fixes: **129 passed, no skips**, in **351.934 seconds**.

| Module | Passing tests |
| --- | ---: |
| `tests.test_backup_settings` | 13 |
| `tests.test_single_world_scripts` | 41 |
| `tests.test_apply_config` | 54 |
| `tests.test_resource_pack_selection` | 21 |

The reviewer reused that definitive run instead of repeating passing suites.
It includes configured mirrors, retention/interval behavior, whole-set refusal,
unrelated working directories, shared-settings isolation, source/target links,
metacharacter data handling, partial cleanup containment and complete-snapshot
preservation. The scene code/forwarding contract was unchanged and was not
rerun. No unrelated full suite or Minecraft process was started.

Reviewer static checks passed: Bash syntax, PowerShell script parsing, AST
parsing of six changed Python files, and scoped CRLF-aware `git diff --check`.
No project linter or type-checker is configured; none was added or claimed as
run. Runtime validation occurred on Windows with CMD/PowerShell and Git Bash,
not on a production Linux host.
