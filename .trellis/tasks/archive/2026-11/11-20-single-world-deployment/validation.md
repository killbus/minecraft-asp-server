# Validation record

## Scope

All checks run in the isolated `feat/single-world-start` worktree. Production
hosts, the existing local manual server, live saves and sibling repositories
are outside this validation. The environment has Windows, Python and Git Bash;
it does not provide a real HAProxy binary for a live transport smoke test.

## Completed checks

- `python -B -m unittest tests.test_check_commit_message -v`: 8 passed.
- `python -B -m unittest tests.test_install_runtime tests.test_verify_runtime -q`:
  48 passed. Installer requests target a disposable loopback fixture only.
- Selected source commits were applied cumulatively with `--no-commit`.
  Conflicts retained native save backups, Paper inventory, the historical ASP
  notice and runtime tests. Omitted map importer/artifact tests remain absent.
- Commit gate port is recorded separately as `36046e9` (source `5d6ace4`),
  including its Linux executable bit.
- Focused config, settings backup, single-world launcher/backup and scene tests:
  69 passed in 48.256 seconds (`.tmp/deployment-focused-tests.log`).
- Independent review reproduced and verified fixes for configuration aliases
  into native saves and missing `permissions.yml` snapshot coverage. It also
  corrected test/documentation references to retained scene stages/options.
- Independent static checks: 30 Python files parse; five shell scripts pass
  `bash -n`; all 26 configuration hashes and exact tree coverage match; all
  nine runtime artifacts stay within the intended inventory boundary.
- Code/docs diff checks pass with `core.whitespace=cr-at-eol`, excluding
  imported `config/` templates whose existing whitespace is hashed source.
- Full discovery (`python -B -m unittest discover -s tests -v`) ran 317 tests
  in 227.925 seconds: four failed because inherited pack scene fixtures assumed
  the checkout already contained `server/packs`; ten were skipped for platform
  prerequisites. Log: `.tmp/deployment-all-tests.log`.
- The failing scene fixture now copies both scene scripts into its own scratch
  runtime and creates its pack directory there. Production code is unchanged.
  Rerunning the entire affected module passed all 56 tests in 74.128 seconds
  (`.tmp/deployment-shared-scene-tests.log`). Combined with the full run, all
  307 runnable tests passed; ten platform checks remain skipped. The whole
  suite was not repeated after this test-only correction.
- The skipped checks require Linux process-table or listening-socket tools.
  No lint or type-check toolchain is configured. Real HAProxy and client
  gameplay remain operator validation.

## Publication boundary

Work commits are `36046e9` (gate) and `7307c99` (deployment port). Publication
targets only `feat/single-world-start`; main and the integration freeze remain
unchanged. No gameplay or production deployment result is claimed.
