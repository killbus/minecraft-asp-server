# Design and change boundary

The behavior gap is two deployment intent files plus duplicate pack URL owners.
The owner is host settings decoding, not HAProxy, Minecraft events or plugins.

Extract shared `scripts/host_settings.py` containing strict JSON/schema parsing,
raw value/reference validation, resource_packs validation and shared URL rules.
Read credentials as env references; only the renderer resolves them. Keep
existing apply_config public helper imports/behavior where useful for compatibility.
Use no new dependency or general settings framework.

The optional resource_packs object holds exactly default and worlds (no nested
schema_version). Descriptor shape/validation is unchanged. The current
`settings/minecraft-server.example.json` owns a default-null empty-worlds policy;
docs demonstrate adding a valid descriptor after obtaining the served ZIP hash.
Remove `settings/resource-packs.example.json`.

apply_config parses the shared document and resolves values at deployment time.
When a resource_packs section exists, old PACK_URL in host values/env is inert:
force the canonical placeholder to empty, even when omitted. Reject nonempty
explicit --set PACK_URL as conflicting; accept an explicit empty assignment.
Other placeholder resolution, schema/manifest checks and precedence stay intact.
Without the section keep legacy PACK_URL behavior exactly. No startup world
resolution or per-world rendering belongs in apply_config.

The selector reads fixed settings/minecraft-server.json and consumes the validated
resource_packs section without resolving unrelated env references. Missing file
or absent section selects the existing native config path. For launcher control,
the helper's non-check CLI exits 3 when no policy is present (no projection),
0 when projection was generated, 2 for errors; --check always returns 0 for a
valid selection. Both launchers handle these explicitly and never reuse stale
generated output. No file/no policy compatibility retains native behavior; a
present host file requires Python to parse the shared contract.

If settings/resource-packs.json still exists, refuse with instructions to move
its default/worlds into the host file's resource_packs and remove the redundant
file after review. Detect this before Java even if the unified file is absent.
No automated deletion or host-file migration. Preserve directory/link guards.

Expected files: one shared settings module; selector/renderer integration; both
launchers; consolidated example; focused config/selection/launcher fixtures;
settings README/SOP/two specs; task records. No template or lock edits needed:
PACK_URL remains the internal legacy rendering slot and is neutral under policy.

Refactor proof is existing renderer tests plus new policy/credential-isolation
regressions, both launcher platforms and relevant scene forwarding tests. Native
Java properties/cache mechanisms are unchanged and need not be researched again.
