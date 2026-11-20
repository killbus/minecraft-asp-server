# Design boundary

The gap is destination ownership, not snapshot contents. Add backup.targets to
the shared raw host schema in host_settings.py. The section has exactly targets;
targets is a nonempty array of nonblank path strings without controls or template
references. No nested schema version or destination environment references.

Use one small backup-specific Python consumer for config/path validation and
safe handoff to existing shell copy implementations. Read fixed repository
settings/minecraft-server.json; resolve relative targets against repository root.
Do not generate executable shell code, eval values, or pass interpolated paths
across shells for deletion. Treat configuration values as data. Preserve spaces;
test shell metacharacters and either support them safely or refuse unsupported
native path characters before mutations, with a clear message.

Validate every target before any write: canonicalize paths, reject target/source
overlap (server and snapshotted settings), duplicate/nested targets, existing
non-directories and unsafe links/junctions. Existing deletion/cleanup paths must
be verified contained in the intended target, including timestamp child paths.
Use native PowerShell cmdlets end-to-end for Windows recursive deletion if any
PowerShell path enumeration is involved; never hand enumerated paths to CMD.
Do not broaden this to a full backup engine rewrite without reporting need.

Missing host file/backup section is an actionable error for backup, never a
silent fallback to a script default. The example declares targets ["backups"].
BACKUP_ROOT and BACKUP_TARGETS are legacy external destination inputs and must
produce migration guidance when nonempty. Do not introduce replacement public
environment variables. Remaining existing controls (KEEP, interval, mirror
requirement, ALLOW_ONLINE, SETTINGS_DIR source override, ASP_SKIP_BACKUP) retain
their behavior. Startup retains its current warning-and-continue handling of a
backup failure; no lifecycle change is part of this task.

Expected files: shared schema; backup target consumer; backup.sh/backup.cmd;
example; isolated backup/schema/launcher regressions; current SOP/settings README
and two backend specs. The parent owns docs/specs/task records; implementer owns
code/example/tests. Tests must not touch real runtime/backups or spawn Minecraft.
