# Configure backup destinations in host settings

## Goal

Operators configure backup destinations in their ignored
settings/minecraft-server.json instead of editing distributed scripts or
depending on process-wide destination environment variables.

## Requirements

- Add optional host section backup with a required nonempty targets array.
  Backup execution requires this section; renderer and startup may still consume
  older host documents without it.
- Relative destinations resolve from the repository root, independent of caller
  directory. Absolute paths and paths containing spaces remain supported.
- The first target is primary; further targets remain independent mirrors.
  Preserve current copy scope, retention, interval, failure and offline rules.
- No destination list is hard-coded in either shell script. Legacy BACKUP_ROOT
  and BACKUP_TARGETS cannot silently override the configured policy; report
  migration guidance for active legacy overrides.
- Both backup entrypoints and the debug wrapper consume the same schema.
  Backup never resolves unrelated deployment credentials.
- Invalid, missing, overlapping or unsafe destinations fail before copying or
  pruning. Resolve and verify recursive-delete paths remain within their target.
- Keep real host files ignored and included in snapshots. Update example, docs,
  specs and meaningful isolated regression tests.

## Boundaries

No retention-policy redesign, cloud backup integration, automatic migration of
host settings, production SSH, live service changes or changes to map data.
Work only in the existing single-world-start worktree. This request authorizes
implementation and verification; it does not newly authorize commit/push.

## Acceptance

Both platforms snapshot into configured relative/absolute targets from an
unrelated working directory, preserve mirror behavior and manifests, and refuse
invalid inputs without mutating saves or existing backups. Renderer and resource
pack selection accept the extended host document without consuming backup paths.
