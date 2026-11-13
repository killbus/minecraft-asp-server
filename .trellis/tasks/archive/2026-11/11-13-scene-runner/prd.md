# Optional frpc session script (Linux)

## Goal

Ship one concrete, self-runnable script at `scripts/scenes/frpc.sh` that starts
the ASP server plus one `frpc` process per configuration in a single tmux
session, and stops the server gracefully. It is a composition script, not a
framework: no engine, no DSL, no scene registry. Deleting it must leave the
core deployment path untouched.

## Problem

`scripts/start.sh` ends with `exec java`, so it cannot host additional
processes, and a service manager (`systemd`/`winsw`) was explicitly rejected for
this deployment. Several `frpc` configs must run at the same time, one per frps
endpoint, alongside the server console.

An earlier plan introduced a generic `scene.sh` engine with a `scene_window`
helper and one `.scene` file. It was dropped: with a single composition the
engine is pure overhead, it makes the composition unrunnable on its own, and it
has to be maintained forever.

## Scope

In scope:

- `scripts/scenes/frpc.sh` - the whole deliverable, runnable directly.
- A SOP appendix documenting it as an optional, non-core tool.

Out of scope:

- A scene engine, scene registry, `list` verb, or declarative DSL.
- herdr, Windows, and "new terminal window" backends.
- Where the input assets (the `frpc.toml` files) live and what they contain.
  The script receives paths, never reads them, and assumes no location.
- Crash restart, watchdog, or start-on-boot.
- Changes to `start.sh`, `start.cmd`, `backup.*`, `verify_runtime.py`,
  `runtime.lock.json`, or anything under `server/`.

## Requirements

- **R1 Removability.** Deleting `scripts/scenes/frpc.sh` leaves every core path
  working (`start.sh`, `start.cmd`, `backup.*`, `verify_runtime.py`, `tests/`).
  No other file references it; a repo-wide grep for `frpc.sh` may only hit the
  SOP appendix and the task directory.
- **R2 Concrete, not generic.** No sourcing, no helper API, no dispatch over
  scene names, no `eval`. Every `tmux` call is literal in this one file, and
  `sh -x scripts/scenes/frpc.sh up ...` must be readable end to end. The
  directory `scripts/scenes/` is a container only; it implies no contract.
- **R3 Verbs.** `up`, `down`, `status`, `attach`. Unknown verb prints usage and
  exits 2.
- **R4 `up`.** Session `asp-frpc`. Window 0 is `server` and runs
  `scripts/start.sh`, reusing its backup logic. Every resolved config becomes
  one window named `frpc-<basename without extension>` running
  `frpc -c <path>`. Every created window gets `remain-on-exit on` and
  `monitor-activity on` set on that window, so the user's other tmux sessions
  are untouched; the tmux server gets `history-limit 50000`, which is a
  server-scoped option in tmux 3.x. A failing sidecar must not affect the
  `server` window or abort `up`.
- **R5 Inputs.** `--config PATH`, repeatable, exactly one value per flag. A
  directory expands to its regular non-hidden files sorted by name; a file is
  taken as given. Exact duplicates are dropped. An empty resolved set is an
  error. Two configs that map to the same window name are an error. Both errors
  are raised before any tmux session is created. No default location.
- **R6 Idempotence.** If `asp-frpc` exists, `up` prints one line and attaches
  (`--no-attach`: prints and returns 0). It never creates a second session and
  never appends windows to a running one.
- **R7 `down`.** Send `stop` + Enter to the `server` window, poll
  `#{pane_dead}` every 2s up to `FRPC_STOP_TIMEOUT` (default 180s), then
  `kill-session`. On timeout: warn, leave the session intact, exit 1.
  Never signal the JVM directly and never use `kill -9`.
- **R8 `status`.** One line per window: window name, `pane_dead`,
  `pane_current_command`, and the last non-empty line of `capture-pane`.
- **R9 Preflight.** `tmux` missing prints exactly one actionable line and exits
  2, before any session exists. `--dry-run` skips this check.
- **R10 `--dry-run`.** Prints the commands `up` would run, in order, without
  executing them and without requiring tmux.
- **R11 Assets.** The script never reads, parses, or stores a config file,
  and never assumes a directory for them. It only expands arguments. The
  assets are not covered by `scripts/backup.sh`.
- **R12 Style.** POSIX `sh` (not bash), `set -eu`, no third-party dependencies,
  header comment block matching the sibling scripts (purpose / usage /
  dependencies).

## Contracts

```
scripts/scenes/frpc.sh up --config <dir|file> [--config <dir|file>]... \
                          [--no-attach] [--dry-run]
scripts/scenes/frpc.sh down
scripts/scenes/frpc.sh status
scripts/scenes/frpc.sh attach
```

- `FRPC_STOP_TIMEOUT` - grace period in seconds for `down` (default 180).
- Session name: `asp-frpc`. Window names: `server`, `frpc-<name>`.
- Exit codes: 0 ok, 2 usage/preflight/input error, 1 runtime failure
  (including a `down` timeout).

Typical use:

```
scripts/scenes/frpc.sh up --config ~/frp/home.toml --config ~/frp/cloud.toml
scripts/scenes/frpc.sh status
scripts/scenes/frpc.sh down
```

## Acceptance Criteria

- [ ] `sh -n scripts/scenes/frpc.sh` passes.
- [ ] `up` with no `--config` exits 2, creates no session, prints one hint.
- [ ] `up --config <dir with 2 toml>` creates `asp-frpc` with exactly three
      windows: `server`, and one per config.
- [ ] Inside each sidecar window, `ps` shows `frpc -c <that absolute path>`.
- [ ] Repeating the same file, or passing a dir plus one of its own files,
      yields one window, not two.
- [ ] Two configs with the same basename in different directories exit 2 before
      any session is created.
- [ ] A second `up` against a live session creates no windows and prints one
      line.
- [ ] A config that makes `frpc` exit immediately leaves its window in place
      (`remain-on-exit`) while the `server` window keeps running.
- [ ] `down` reaches a saved-and-stopped server before tearing the session down;
      `tmux has-session -t asp-frpc` returns 1 afterwards.
- [ ] `down` against an idle session blocks for `FRPC_STOP_TIMEOUT`, warns once,
      returns 1, and leaves the session alive.
- [ ] `--dry-run` works with `tmux` absent from `PATH` and prints `new-session`,
      the `set-option`s, and one `new-window` per config.
- [ ] `status` prints one line per window, including each window's last log
      line.
- [ ] Deleting the script leaves the core working, and a repo-wide grep for
      `frpc.sh` hits only the SOP appendix and this task.

## Constraints

- No new dependencies: tmux and frpc are provided by the operator.
- No changes under `server/`, and no frp config content in the repository.
- Linux is the only acceptance target. macOS may work by accident; Windows is
  out of scope.

## Decisions

- **D1 Backend:** tmux only.
- **D2 No engine.** A generic `scene.sh` with `scene_window` and sourced
  `.scene` files was designed, then rejected. With one composition the engine
  buys nothing, hides the commands behind an interpreter, and makes the
  composition unrunnable on its own. `scripts/scenes/` stays as a plain folder
  for future composition scripts.
- **D3 herdr dropped.** Its value is agent-state awareness, which `frpc` and
  the server do not have; the local herdr server also runs elevated and rejects
  ordinary clients.
- **D4 Asset location is not a repository decision.** Config files are passed
  with `--config`; the repository ships no default path and no real frp config.
- **D5 `status` included**, because `remain-on-exit` makes dead windows easy to
  miss and `tmux list-windows` alone does not show the last log line.

## Notes

- The config assets live outside the repository and outside `server/`, so
  `scripts/backup.sh` does not copy them. Backing them up is an operator
  decision, and so is whether the frp token belongs in those backups.
