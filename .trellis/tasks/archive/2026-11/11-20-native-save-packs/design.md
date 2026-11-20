# Design

Historical design note: the separate policy file below was corrected after user
review. The final implementation stores resource_packs inside the host
minecraft-server.json and shares schema decoding with the renderer. See the
unified-pack-settings task and current startup/configuration specs. Native
projection, cache identity and map evidence below remain applicable.

## Behavior gap and ownership

Native `resource-pack` is server-wide for one running process. Startup selects
one primary save; it must select that process's pack from the same save name.
No plugin or per-dimension event handling is needed. Current global native
properties remain the compatibility path when there is no pack policy.

## Optional host policy

The direct launchers consume the documented fixed path
`settings/resource-packs.json`. It is ignored host state, already included by
the existing settings backup. Track only `resource-packs.example.json`.

Schema version 1 has exactly `schema_version`, `default`, and `worlds`.
`default` is either null (no pack) or `{ "url": "...", "sha1": "..." }`.
`worlds` maps exact primary-save names to the same descriptor or null.
An absent override inherits the default. All descriptors require a valid
HTTPS/loopback HTTP URL and 40 hexadecimal SHA-1 characters. Reject unknown
fields, duplicates, placeholders and malformed names/values before writing.
No shell expansion, environment lookup, URL fetching or asset copying occurs.
This is a pack policy, not a save inventory; absent/inactive saves may be named.

A missing policy retains the existing native `server.properties` unchanged and
does not add Python as a startup requirement for that compatibility path.
An existing invalid/unreadable policy refuses startup, rather than silently
offering the native global pack. This dedicated fixed input is separate from
the explicitly supplied deployment coordinates used by `apply_config.py`.

## Native configuration projection

`scripts/select_resource_pack.py` owns schema validation and Java-properties
decoding/encoding needed for selection. Explicit launcher `--world` wins;
otherwise read native `level-name` (default `world`). Respect Java property
escapes, separators, continuation and last-definition semantics. Do not parse
this independently in Bash and CMD. Reuse existing URL/JSON validation if it
does not introduce duplicate ownership.

For configured policy, derive a complete disposable properties file from the
existing native properties. Override only `resource-pack`, `resource-pack-sha1`
and `resource-pack-id`, clearing deprecated `resource-pack-hash` too. Clear the ID so Paper derives its stable native default
from the URL; null clears all three values. Keep native prompt/required flags
and all unrelated properties. Paper receives `--config` for the generated file
plus the unchanged optional `--world` argument. The original properties/save
remain byte-identical. Effective output is always regenerated from the original,
never from previous output. Use a fixed `.tmp/startup/server.properties` target
and atomic replacement under the existing single-process contract; reject unsafe
linked output/input paths. Offer helper `--check` for read-only inspection.

Pack selection is invoked before Java/backup by both direct launchers. Scenes
continue forwarding `--world`; they do not become another policy consumer.
An invalid policy can leave an already-started scene's sidecars alive, like
other direct-launcher failures, but cannot start Minecraft.

## Fresh map

The RAR itself contains native 26.2 metadata. Preserve the entire source save,
including global scoreboard and dimension data; do not fabricate metadata or
trim region files. Stage a disposable full copy for pinned-engine validation.
The original RAR is already the reproducible source artifact: document full
extraction and naming as `trials/` rather than producing a duplicate archive.
Do not overwrite production `world/` or current
local services. Source hashes and reproducible preparation commands belong in
the task evidence/operator docs, not in the generic launcher implementation.

## Expected changes

- One selection helper and its meaningful policy/property tests.
- Both direct launchers and launcher fixtures for the opt-in path.
- One host-settings example; startup/config specs and operator documentation.
- Task provenance and isolated map verification evidence.

No config-template/lock changes, scene transport changes, new runtime plugin,
save registry, automatic importer, new engine or unrelated refactor.

Native inspection additionally proved Paper persists `--world` into its active
properties file. Correct prior documentation that inferred no native writes from
fake-Java fixtures; preserve this existing behavior when the policy is absent.
With policy, only the generated file receives those native writes.
