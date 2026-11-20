# Implementation and validation

1. Apply selected main deployment commits with `cherry-pick --no-commit`,
   resolving historical assumptions while retaining native save selection.
2. Remove excluded runtime/config plugin entries and adapt the native resource
   pack setting, named-save protection, backup settings and scene forwarding.
3. Update the active operator guide and executable configuration/runtime/scene
   specifications. Retain source commit provenance in the task record.
4. Run the affected executable fixture suites and the repository test suite,
   shell syntax checks and diff checks. Review source/instance boundaries and
   investigate actual failures before publishing.
5. Commit coherent changes and push only `feat/single-world-start`. Verify the
   remote branch hash and report the operator's fetch/switch/test steps.

## Source provenance

Selected main commits, in source order:

| Commit | Contract retained |
| --- | --- |
| `5d6ace4` | Commit message gate |
| `fd822bf` | Regenerable pack backup exclusions |
| `fc210ef` | Shared-port resource-pack routing |
| `0c436d7` | Pinned runtime installer |
| `c4496a9` | Source configuration and host settings |
| `c3f1a7e` | Configuration test scratch location |
| `22ca771` | Shared repository-local test scratch |
| `f274d4a` | Ignored and backed-up host settings |
| `785484e` | Scene ownership of the pack sidecar |
| `0fcab06` | Public HTTPS resource-pack policy |
| `640fd77` | Decrypted HTTP inspection before routing |
| `8c74d5c` | Paper/Geyser PROXY alignment |
| `e1d12bf` | TLS stage names reflecting their roles |

`01cd4a1` and its multiworld/map-content integration are excluded. Mixed
manifest and documentation changes are adapted rather than adopted verbatim.

## Validation boundary

Use isolated fixtures under `.tmp/`, mocked process/Java probes, and loopback
HTTP for installer tests where needed. Existing live services and ignored
server saves are outside scope. Fixture verification is not a gameplay test.
