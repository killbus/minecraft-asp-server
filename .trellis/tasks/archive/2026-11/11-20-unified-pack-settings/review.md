# Independent review

Reviewed the shared host decoder, renderer integration, selector, both launchers,
example, tests, current SOP/specs and task design. Reviewer edits stayed in this
worktree; no live service, production SSH, staging, commit or history operation
was performed.

## Findings fixed

- `scripts/select_resource_pack.py`: a valid legacy host document without
  `resource_packs` still caused the helper to read canonical properties and apply
  the explicit-world ASCII grammar to native `level-name`. Consequently, adding
  the shared startup consumer broke valid native names containing spaces and
  Paper's first startup with no properties file. After shared schema/migration
  validation, normal no-policy selection now returns exit 3 without inspecting
  native properties. Read-only `--check` accepts implicit native names and uses
  native defaults when the file is absent. Explicit `--world` validation and all
  policy-enabled parsing/path guards remain intact.
- Added two helper and two launcher regressions. All four reproduced the gap
  before the fix and passed afterward. Updated SOP/startup spec with the exact
  compatibility behavior; removed an unsupported claim that missing-Python
  behavior had dedicated launcher test coverage.

## Findings not fixed

None remaining within the reviewed scope. `apply_config.py` retains explicit
settings selection, manifest enforcement and deployment-time environment
resolution; startup consumes only the fixed host file's validated pack section.
Unused legacy PACK_URL references remain inert when policy exists, while a
nonempty explicit CLI override is refused. Legacy standalone-file refusal,
exit-3 fallback and stale-output avoidance are consistent on Bash and CMD.

## Verification

| Module | Final passing count | Evidence |
| --- | ---: | --- |
| `test_apply_config` | 54 | Implementer run; unchanged by reviewer |
| `test_resource_pack_selection` | 21 | Reviewer rerun after fix |
| `test_single_world_scripts` | 28 | Reviewer rerun after fix, 72.203 seconds |
| `test_single_world_scenes` | 6 | Reviewer scene forwarding regression |
| **Total** | **109** | No skips in these modules |

The implementer's initial combined run passed 99 tests before the four new
regressions. The reviewer reused its renderer results instead of repeating that
unchanged suite. No separate schema test module exists; shared decoding is
covered by both consumer suites. No unrelated full-suite run was performed.

Static verification passed: Bash syntax, AST parsing for six changed Python
files, shared-schema loading of the committed example, and scoped
`git -c core.whitespace=cr-at-eol diff --check`. No project linter or static type
checker is configured; none was introduced or claimed as run. No new native
engine/cache/gameplay probe was needed because this correction preserves those
mechanisms; prior native evidence remains in the archived original task.
