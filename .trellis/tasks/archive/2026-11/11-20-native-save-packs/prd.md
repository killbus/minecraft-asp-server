# Fresh native save and resource-pack selection

## Goal

Restart Trials from its original map as a complete independent native save,
and offer a resource pack only for the startup saves the operator selects.
Explain whether reconnecting downloads bytes again or reloads cached resources.

## Requirements

- Prepare original Trials content in disposable local storage. Preserve the
  original archive and the existing runtime, saves and artifacts.
- Validate full-save compatibility with pinned Paper 26.2 before recommending
  production placement. A dimension directory without metadata is insufficient.
- Support an optional global pack default, exact startup-save overrides, and
  explicit no-pack selection. One Paper process still owns one primary save and
  its native dimensions; changing it requires a restart.
- Keep host pack coordinates in ignored, backed-up settings. No system
  environment contract, multiworld plugin, engine/profile framework or hot swap.
- Give native clients a content SHA-1 and stable pack identity. Document server
  offer, client cache/download and client resource reload as distinct events.
- Preserve existing startup behavior when no new pack policy is configured.

## Acceptance

- Original source provenance and migration findings are recorded, including any
  compatibility limits that prevent a reliable fresh-map deployment.
- Starting different saves selects the expected native pack tuple, including
  global fallback and explicit disable; changing selection cannot retain a
  previous save's pack. Policy projection does not rewrite canonical properties
  or save contents; native Paper writes only to the generated properties target.
- Invalid policy fails before Java startup. Both shell and CMD launchers retain
  argument validation and exit status behavior.
- Tests cover meaningful selection transitions and configuration failure modes.
- Operator instructions include fresh-save placement, pack configuration, startup
  and a way to observe actual HTTP downloads across reconnects.

## Out of scope

Production SSH or edits; replacing production world; restoring player progress;
modifying existing local services; plugin data isolation; gameplay redesign;
client resource-reload suppression; rewriting main or committing host settings.
