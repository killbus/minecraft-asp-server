# Startup selection validation

Date: 2026-11-20. Branch `feat/single-world-start`, based on pre-Multiverse commit `10c794e25981e8d5625dbcc9655b79db572d4b30`.

## Implemented boundary

Both launchers pass a validated existing save name through Paper's native `--world` option. Default selection still belongs to `server.properties`. Plain Paper replaces the historical ASP lock entry and ASP plugin; no multi-world plugin, instance supervisor, engine switch, or profile system is introduced.

The historical backup entrypoints now discover top-level native saves by `level.dat`, including inactive saves and native sibling dimensions. The debug Windows entry delegates to the normal backup. Source changes do not modify installed runtime files or migrate any existing save.

## Verification

- `python -B -m unittest tests.test_single_world_scripts -v`: 13 tests passed, no skips on this Windows host with Git Bash available. These execute real Bash/CMD/backup scripts against disposable `.tmp/` fixtures with stand-in Java/process probes.
- `python -B -m unittest tests.test_verify_runtime -v`: 37 tests passed.
- Bash syntax validation and `git diff --check` passed.
- Python AST parsing passed for the changed Python files. No project static type-check configuration exists.
- The new test file passes available Ruff. A wider optional Ruff run reported six pre-existing findings in the runtime verifier/tests; unchanged lines were not reformatted as unrelated cleanup.
- The runtime lock parses with one canonical Paper server artifact and no ASP/Multiverse/lifecycle/sidebar plugin.
- The available Paperclip file's SHA-256 matches the pinned 26.2 build 135 artifact. Read-only inspection of the cached `org.bukkit.craftbukkit.Main$1` confirms `w`, `world`, and `level-name` use a required String argument.
- A standalone Java probe against the actual cached jopt-simple 5.0.4 confirms flag-shaped names such as `--help` are consumed as literal required world values. It does not invoke Minecraft. Evidence lives in ignored `.tmp/native-cli/`.

## Independent review

The reviewer reproduced and fixed a Windows argument bug: embedding raw `%1` in a quoted assignment allowed an unknown quoted token containing `&` to execute another command and launch Java. `%~1` capture plus explicit empty-token handling now rejects it with exit 2. Regression tests cover that case, flag-shaped names, and linked save directories/markers.

The revised suite verifies argument propagation and working directory, no default override, Windows pause ordering, Java exit propagation, missing/unsafe/duplicate arguments before side effects, save-marker checks, unchanged input bytes, backup coverage/manifests/exclusions, and refusal while a Paper process is reported running. No functional review blocker remains.

## Limits and preservation

The `level.dat` check is not an NBT or complete-save validator. A cropped dimension or Slime save is not made into a primary save by this launcher. Native ownership of player data/statistics/scoreboards does not imply isolation of shared plugin databases or server configuration.

No real Minecraft server was launched for this task. Live gameplay, old-map upgrade behavior, copied player state, networking and production plugin compatibility were not tested. The existing manual server was not stopped or changed. No host settings, player data, runtime JARs or maps were staged. No remote push was requested.

The prior integration remains available at server tag `freeze/multiverse-2026-11-20` (commit `b7837eb`) and the separate lifecycle repository's tag of the same name (commit `2bfab4c`). The new branch deliberately does not inherit later deployment or resource-pack pipeline changes from main.
