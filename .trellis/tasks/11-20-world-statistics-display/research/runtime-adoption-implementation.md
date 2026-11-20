# Runtime and configuration adoption implementation

Date: 2026-11-20. Scope: the previously verified MVI and formal WorldLifecycle
components; statistics presentation is a separate implementation.

## Decisions implemented

- `runtime.lock.json` adds Multiverse-Inventories 5.3.6 using its pinned
  Modrinth artifact and SHA-256, plus Multiverse-WorldLifecycle 0.1.0 using
  the existing MANUAL contract. No installer behavior, release URL, build
  invocation, or hash adoption was added.
- `config/plugins/Multiverse-Inventories/config.yml` supplies the validated
  policy: optional `last_location` and `game_statistics`, independent
  ungrouped worlds, native login, no global teleport rewriting, and
  `first-run: false`. It preserves the generated configuration comments and
  formatting because MVI saves configuration unconditionally on enable.
  The source uses LF; the validated Windows-generated file has CRLF. Their
  decoded text is identical after newline normalization.
- MVI's `groups.yml`, `playernames.json`, `worlds/`, `groups/`, and `players/`
  are independently rejected by the config path classifier, even if a
  manifest falsely marks them source. They are never deployed or migrated.
- WorldLifecycle's template requires `WORLD_LIFECYCLE_MANAGED_WORLDS`, a
  string containing a JSON array of unique printable nonblank names without
  surrounding whitespace. It is normalized to a single YAML flow list.
  Invalid or omitted values fail during planning before any file is written.
  The example supplies `"[]"`; the manifest has no behavior default.
- The managed list belongs to the untracked host settings, not a literal
  map name or an operator edit that the next apply would erase. The plugin
  retains its verified idle/request/login-prepare/login-completion budgets
  of 60/30/30/60 seconds.
- Multiverse-Core's `spawn.enable-join-destination` changes to false to
  preserve the formal plugin's native saved-world login contract. The old
  inactive `join-destination` scalar remains unchanged.
- Existing backup code already snapshots the complete plugin data
  directories. Only regression coverage was added; there is no second
  backup mechanism or broad exclusion change.

## Files

- `runtime.lock.json`, `config.lock.json`
- `config/plugins/Multiverse-Inventories/config.yml`
- `config/plugins/MultiverseWorldLifecycle/config.yml`
- `config/plugins/Multiverse-Core/config.yml` (one behavior flag)
- `scripts/apply_config.py`
- `tests/test_apply_config.py`, `tests/test_backup_settings.py`
- `settings/minecraft-server.example.json`, `settings/README.md`
- `docs/PAPER-WORLD-SOP.md`

The operations guide replaces the previous forced-hub login explanation,
documents the MANUAL artifact and build boundary, required settings upgrade,
permissions, first adoption of statistics, and explicit fresh-host group
bootstrap. The command syntax was checked against MVI 5.3.6 source:
`create-group`, `add-shares`, `remove-shares`, `add-worlds`, and `info`.
Using separate commands avoids the inconsistent create-group syntax
annotation versus Java parameter order. `all` includes `game_statistics`
and `last_location`; removing the latter preserves each world's position.
The guide explicitly prohibits treating that fresh-host recipe as an
existing-profile migration.

## Verification

1. `python -B -m unittest tests.test_apply_config tests.test_backup_settings
   tests.test_install_runtime tests.test_verify_runtime -v`: 99 tests run,
   passing with one explicit skip. The skip is the optional comparison to
   `server/`, where the formal plugin configuration has not been installed.
2. After preserving generated MVI formatting and tightening printable-name
   validation, `python -B -m unittest tests.test_apply_config -q`: 48 tests
   run, passing with the same optional live-tree skip.
3. The repository bundle was applied twice into an isolated fixture. All
   entries were created, then all were UNCHANGED. Existing native player
   saves, MV world registry, MVI assignments and profiles kept both bytes
   and mtimes. Missing managed settings, malformed/non-list/duplicate/blank/
   non-string/control-character names were refused through settings,
   environment and one-off override inputs before writes.
4. A fixture backup included every MVI profile family, assignments, player
   lookup, WorldLifecycle config, native player save, and untracked host
   settings in `MANIFEST.txt`; plugin JARs were excluded and COMPLETE was
   written. No original server or real backup was used.
5. Both actual artifact hashes were recalculated and matched the new lock.
   In `.tmp/runtime-adoption-nv24et16/`, the absent WorldLifecycle artifact
   produced MANUAL/exit 1. After supplying both matching local JARs, the
   unchanged installer reported two OK/exit 0 without downloads.
6. `git -c core.whitespace=cr-at-eol diff --check` passed. The ordinary
   whitespace check reports the existing CRLF convention as trailing
   whitespace; no line-ending policy was changed.

The first targeted test attempt found a Windows default-GBK read in the new
fixture assertion. Explicit UTF-8 fixed it; no product behavior failed.

## Independent-review correction: path case aliases

Review found that a forged manifest could spell protected MVI paths with
different capitalization. Windows resolves those spellings to the existing
instance file, while the previous classifier compared case-sensitively.

`scripts/apply_config.py:76` now case-folds every path component before
classification. Protection is deliberately consistent across hosts; the
original path remains unchanged for destination resolution. The MVI plugin
guard uses the normalized plugin name. Existing source configuration remains
permitted under case variants, and protected native/world/database paths
cannot become source solely through capitalization.

`tests/test_apply_config.py:362` exercises seven forged source-manifest paths
across plugin-root, plugin-name, file-name and profile-directory case changes.
Each test seeds canonical instance data and proves that refusal preserves its
bytes and mtime, with no earlier manifest entry written. Classification
regressions also cover allowed source configuration and uppercase native
world/database paths.

Final focused command: `python -B -m unittest tests.test_apply_config -v`.
Result: 49 tests run, OK with one skip because the optional original
`server/plugins/MultiverseWorldLifecycle/config.yml` is absent. The complete
repository fixture and malicious manifest tests ran and passed. The CRLF-aware
`git diff --check` also passed. No server or plugin process was started.

## Boundaries and follow-up

No production access, local manual-server restart, original `server/` write,
world/profile migration, backup execution on real data, source publication,
commit, or branch operation occurred. The source project URL is a reference,
not evidence that public HEAD reproduces the local artifact. A future public
release needs its own artifact verification and lock update.

The main session still owns presentation adoption, independent review,
spec updates, and final combined validation. The generated-config LF/CRLF
difference may yield newline-only drift after a Windows plugin save; the
config tool intentionally retains its existing byte-exact semantics.
