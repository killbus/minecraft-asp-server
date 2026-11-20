# Independent review

Reviewed the selection helper, both direct launchers, settings example, affected
tests, operator SOP, startup/configuration specs, and native/map research against
the task design. No staging, commit, production access or live-service changes
were performed by the reviewer.

## Findings fixed

- `scripts/select_resource_pack.py`: backslash-only continued lines followed by
  comments or blank lines could introduce spurious properties, including an
  empty key overriding an existing value. Match Java's logical-line behavior,
  including the distinction between EOF and an actual empty next line.
- `scripts/select_resource_pack.py`: literal non-BMP property keys and equivalent
  escaped UTF-16 surrogate pairs were treated as different Python keys. Normalize
  decoded pairs so Java's last-definition semantics are preserved.
- `scripts/start.cmd`: a linked settings directory with no policy, or a regular
  file occupying the settings directory path, silently selected native fallback.
  Inspect the parent first, send links through the helper's refusal path, and
  reject non-directories. Make the Bash directory check explicit too.
- Added two parser regression tests and four cross-platform path regressions;
  synchronized the startup spec. The two CMD regressions reproduced failures
  before their fix and passed afterward.

## Findings not fixed

None remaining within this review's scope. The documented fresh-map pending-tick
conversion caveat, incomplete gameplay validation, and ephemeral management-API
property writes are explicit limits rather than hidden behavior. Parent-owned
native startup, cache-transfer and original-source preservation evidence is in
`validation.md`.

## Verification

- Resource-pack selection: **14 passed**.
- Direct launcher/backup fixtures: **24 passed**, final complete run captured in
  `.tmp/native-pack-review/launcher-tests.log`.
- Existing configuration renderer regression: **49 passed**.
- Existing scene forwarding regression: **6 passed**.
- Total: **93 tests passed**, no skipped tests in these four modules.
- Java 25 `Properties.load(Reader)` differential probe: **3,005 deterministic
  cases, zero differences** after the fixes. The disposable oracle/probe is in
  `.tmp/native-pack-review/`.
- Static checks passed: Bash syntax, AST parsing of the three changed Python
  files, and scoped `git diff --check`.
- No project linter or static type-checker is configured; none was added. No
  claim of a separate lint/type-check tool run is made.

Flag-shaped save names, CMD argument shifting/root capture, duplicate/invalid
arguments, Java exit propagation, explicit null/default/world pack transitions,
deprecated-hash clearing, source-property preservation, atomic output replacement
and controlled-path link rejection are covered by the reviewed implementation
and these tests. Canonical properties remain subject to Paper's native writes
when no policy exists; with a policy, only the generated properties receive
those native writes.
