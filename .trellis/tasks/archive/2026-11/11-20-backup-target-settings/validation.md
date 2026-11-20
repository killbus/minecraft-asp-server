# Validation

Implementation and independent review are complete. The user authorized
commit and push on `feat/single-world-start` after reviewing both the backup
configuration and the separate multi-certificate template fix.

## Executed checks

The implementer ran the final affected suite after all review fixes:

```text
python -B -m unittest tests.test_backup_settings tests.test_single_world_scripts tests.test_apply_config tests.test_resource_pack_selection
Ran 129 tests in 351.934s
OK
```

No tests were skipped: 13 backup settings, 41 launcher/backup, 54 renderer and
21 resource-pack selector tests passed. Coverage includes configured mirrors,
relative paths from an unrelated working directory, invalid destination
preflight, legacy override refusal, credential isolation, cleanup containment,
timestamp ownership and preservation of completed snapshots after prune errors.

The independent reviewer passed Bash syntax, PowerShell parsing, Python AST
checks for six changed files and CRLF-aware whitespace validation. The parent
also ran `git -c core.whitespace=cr-at-eol diff --check` after documentation
wording changes; it passed. No configured linter or type checker exists.

See `review.md` for the resolved findings and detailed review boundaries.

## Limits

Tests ran locally on Windows using CMD/PowerShell and Git Bash. No production
Linux execution, SSH or live Minecraft process occurred. Existing scene
forwarding behavior was unchanged.

## Separate multi-certificate template fix

The user reported `crt: not found` when starting the shared-TCP scene with two
certificates. An unquoted heredoc executed backticks in a generated HAProxy
comment. Removing those backticks preserves the actual certificate bind
arguments. The regression uses a PATH sentinel to detect command execution
even when the scene returns success; it failed before the fix and passed after.

The implementer ran `python -B -m unittest tests.test_frpc_shared_tcp_scene`:
57 tests passed, no skips, in 79.812 seconds. Shell syntax, Python AST and
whitespace checks passed; independent review found no remaining issue. This
fix, its test and the scene spec are committed separately from backup policy.

## Separate local map delivery

At the user's request, the original Trials archive was extracted locally to
`D:/Repositories/minecraft-asp-server/.tmp/trials-deploy/trials` for whole-folder
upload. The save contains 636 files totaling 1,010,681,922 bytes; extraction
reported success. The source archive SHA-256 is
`2b7710df040aaa37666b6d284bc24122f897317dbcdebb9bd213f62409f7f91c`.
The extracted `level.dat` SHA-256 is
`d4d37a93df15d590b1e111498a00d9f50dd033fb1e492ae48166861c22d38e4a`.
No server boot, map conversion or upload was performed on this fresh copy.
