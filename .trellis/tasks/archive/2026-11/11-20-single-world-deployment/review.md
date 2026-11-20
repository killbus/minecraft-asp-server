# Deployment port review

Reviewed on 2026-11-20 in the isolated `feat/single-world-start` worktree.
The review used this task's PRD, design, implementation record, check context,
active backend specifications, and comparison against main `e1d12bf`.
The archive checkout, live services and production host were not changed.

## Findings (fixed)

- `scripts/apply_config.py`: an in-root configuration symlink could target a
  subdirectory of a native save, bypassing the lexical source-root guard.
  Reproduced with `server/config -> server/Adventure_A/config` and a native
  `Adventure_A/level.dat`: the original dry run incorrectly planned an update.
  The implementer added resolved native-save containment checks and a
  regression. An independent real apply against the isolated fixture now
  exits 2 before writing, preserving the original marker and state bytes.
- `scripts/backup.sh`, `scripts/backup.cmd`: the older root-file list omitted
  `permissions.yml`, although the ported configuration bundle now applies it.
  The implementer restored the source-main backup entry and added it to the
  existing shell, CMD and debug-CMD snapshot fixture expectations.
- `tests/test_single_world_scenes.py`, `docs/SINGLE-WORLD-SOP.md`: an initial
  expectation named a nonexistent `http_inspection` backend, and the guide
  mentioned a nonexistent `--packs-prefix` scene option. The implementer
  aligned both with the retained generator: `tls_termination`,
  `tls_terminated` with its own decrypted-content wait, and `MUX_PACKS_PREFIX`
  for an external pack backend. The actual lifecycle remains frpc sidecars,
  HAProxy, optional owned packs, then Paper.
- `tests/test_frpc_shared_tcp_scene.py`: four resource-pack fixture tests
  assumed that the checkout already contained the ignored `server/packs/`
  directory. The reviewer isolated the normal scene invocations under each
  test's scratch runtime, copying both scene scripts and creating the pack
  directory there. Existing assertions and specialized mocked lifecycle
  fixtures are preserved. No production behavior or checkout runtime was
  changed.

## Findings (not fixed)

No outstanding scoped implementation defect was found after these fixes.

## Boundary review

- Runtime contains the pinned Paper artifact, independent plugins and the
  existing default-world datapack only: nine artifacts total. Excluded
  Multiverse, inventories, lifecycle, PackManagerPro and sidebar artifacts
  are absent. Installation and verification still share the existing parser,
  path validation and hash implementation.
- Configuration contains 26 declared templates. All committed template
  hashes match and the manifest covers the tree exactly. Native save paths,
  resolved aliases into saves, host settings and plugin instance state remain
  outside the application boundary. `PACK_URL` remains required, accepts an
  explicitly empty value, otherwise enforces HTTPS or loopback HTTP, and
  renders the native property with backslash/control-character handling.
- Backups retain discovery of all top-level native saves, inactive saves,
  host settings, permissions and plugin instance state. The debug CMD still
  delegates. Configuration/plugin/settings directory collisions fail before
  copying. Regenerable pack and known cache exclusions remain intact.
- Both scenes validate `--world` before process/configuration effects and
  forward it to the existing launcher. The shared script constructs one
  quoted server command and uses it in both the preview and actual final
  `tmux respawn-window`; forwarding only to the deferred child was ruled out.
- The shared-TCP generator and lifecycle implementation match source main
  apart from the narrow world-selection extension. TLS/PROXY pairing, LAN
  Java frontend, decrypted inspection, pack sidecar ownership and certificate
  handling were not redesigned.
- The active operator guide explains stopped deployment, ignored leftover
  plugin JARs, explicit settings application, native save preparation and the
  production scene command. No old `PAPER-WORLD-SOP.md` reference remains in
  active docs, settings, scripts, specs or tests.

## Verification

- Focused tests: **pass**, 69 tests in 48.256 seconds. The implementer ran
  this suite; the reviewer inspected `.tmp/deployment-focused-tests.log`.
  It includes the native-save alias and permissions snapshot regressions.
- Independent Python syntax check: **pass**, AST parsing all 30 Python files
  under `scripts/` and `tests/` without producing bytecode.
- Independent shell syntax check: **pass**, `bash -n` on all five shell scripts.
- Independent configuration inventory: **pass**, 26 exact template hashes
  and complete manifest/tree coverage. Runtime exclusion check: **pass**.
- Lint and type checking: no configured lint or static type checker exists in
  this standard-library Python/shell repository. Syntax and fixture checks
  were used; no new toolchain was introduced.
- Diff whitespace: code/docs checks pass with `cr-at-eol` for retained
  Windows line endings. Imported hashed configuration templates contain
  upstream whitespace; it was retained rather than changing source bytes
  merely for formatting. Parent owns the final staged diff check.
- Full repository discovery: the parent ran 317 tests with four failures and
  ten skips. All four failures were the missing pack-directory fixture
  assumption described above. After the fixture-only correction, the entire
  affected module passed: **56 tests in 74.128 seconds**, recorded in
  `.tmp/deployment-shared-scene-tests.log`. The earlier full-run evidence is
  `.tmp/deployment-all-tests.log`. Unaffected modules were not rerun; these
  are full-run plus focused-retest results, not a claim of a second clean
  full run.
- The corrected fixture passes Python syntax and diff whitespace checks.
  The worktree's `server/` directory remains absent after testing.

No real HAProxy/tmux/Minecraft service or production tunnel was started.
The available checks establish fixture behavior and source preservation;
they do not establish client gameplay or a production rollout.
