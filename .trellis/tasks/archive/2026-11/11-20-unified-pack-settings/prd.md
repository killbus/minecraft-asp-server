# Unified host resource-pack settings

## Goal

Keep deployment values and startup resource-pack intent in one host-owned
`settings/minecraft-server.json`. Correct the published feature with fixup and
rebase, as explicitly requested, then update only the existing test branch.

## Requirements and acceptance

- Schema version 1 accepts `schema_version`, `values`, and optional
  `resource_packs: {default, worlds}`. One shared decoder validates structure;
  consumers retain their own behavior and consumption timing.
- Startup reads only the resource-pack policy and never resolves unrelated
  `env:` credentials or reapplies plugin configuration.
- Deployment applies `values`. With resource_packs present it renders an empty
  canonical native pack; the startup policy exclusively selects actual packs.
  Old PACK_URL is compatibility-only when no resource_packs section exists.
- Existing host files without the new section retain native startup behavior.
  Invalid documents fail clearly. Legacy standalone policy files must cause an
  actionable migration error, never a silent change in selection.
- Existing default/override/null behavior, hash validation, path protections,
  native properties projection and Bash/CMD parity remain covered by tests.
- Update the one example, operator docs, specs and migration instructions;
  remove the separate resource-packs example. Host state remains ignored and
  backed up, and never enters a commit.
- Fold code/docs correction into the original feature commit, preserving the
  independent map-documentation commit and task provenance. Publish via an
  explicit old-OID lease; do not overwrite unexpected remote work.

## Boundaries

No new world/profile/engine registry, network transport changes, production SSH,
live server changes, map re-preparation, or main-branch rewrite. Do not broaden
the launch CLI with custom settings path options in this correction; launchers
document their fixed host path while apply_config retains explicit --settings.
