# Implement: scripts/scenes/frpc.sh

## Steps

1. `scripts/scenes/frpc.sh` - header (purpose / usage / verbs / dependencies),
   `set -eu`, `ROOT` from `scripts/scenes/../..`, constants `SESSION`,
   `SERVER_WINDOW`, `STOP_TIMEOUT`.
2. `usage` + `dispatch`: `up|down|status|attach|help`; unknown verb or no verb
   prints usage and exits 2.
3. `resolve_configs`: reject a `--config` without a value; expand directories
   (`-maxdepth 1 -type f ! -name '.*' | LC_ALL=C sort`); absolutise; dedupe;
   strip one extension; sanitise to `[A-Za-z0-9_-]`; reject an empty set and a
   bare name equal to `server` or colliding with an earlier one.
4. `cmd_up`: parse `--config` / `--no-attach` / `--dry-run`; resolve before
   touching tmux; idempotence check; `new-session -d -s asp-frpc -n server -c
   "$ROOT" -- scripts/start.sh`; the three `set-option`s; one `new-window` per
   config; attach only when stdin is a tty and `--no-attach` is absent.
5. `cmd_down`: `send-keys ... stop Enter`; poll `pane_dead` every 2s for
   `STOP_TIMEOUT / 2` iterations; then `kill-session`; on timeout warn once and
   exit 1. Missing session prints one line and exits 0.
6. `cmd_status` and `cmd_attach`: `list-windows -F
   '#{window_name}\t#{pane_dead}\t#{pane_current_command}'`, then
   `capture-pane -p -J` reduced to the last non-empty line.
7. `--dry-run`: print every command `up` would run, skip the tmux preflight and
   the idempotence probe, exit 0.
8. `docs/ASP-SOP.md` - appendix `## 10. Optional scenes (not core)`:
   what it is, tmux prerequisite, the verbs, one `up` / `down` example with
   `--config`, `remain-on-exit` behaviour, and an explicit note that it is
   outside the acceptance checklist.

## Validation

Local (no tmux needed; `sh` is on this workstation):

```sh
sh -n scripts/scenes/frpc.sh
sh scripts/scenes/frpc.sh                          # usage, exit 2
sh scripts/scenes/frpc.sh up                       # no --config, exit 2, no session
sh scripts/scenes/frpc.sh up --config             # missing value, exit 2
mkdir -p /tmp/frpc/a /tmp/frpc/b
: > /tmp/frpc/a/one.toml; : > /tmp/frpc/a/two.toml; : > /tmp/frpc/b/one.toml
sh scripts/scenes/frpc.sh up --config /tmp/frpc/a --dry-run        # 2 new-window lines
sh scripts/scenes/frpc.sh up --config /tmp/frpc/a --config /tmp/frpc/a/one.toml --dry-run
sh scripts/scenes/frpc.sh up --config /tmp/frpc/a --config /tmp/frpc/b --dry-run   # collision, exit 2
env -i PATH=/usr/bin:/bin sh scripts/scenes/frpc.sh up --config /tmp/frpc/a --dry-run
```

Linux acceptance (needs tmux and frpc):

```sh
scripts/scenes/frpc.sh up --config ~/frp --no-attach
tmux list-windows -t asp-frpc -F '#{window_name} #{pane_current_command}'
scripts/scenes/frpc.sh status
scripts/scenes/frpc.sh down           # waits for the server to save
tmux has-session -t asp-frpc; echo $?  # 1
```

## Review gates

- PRD review before `task.py start`.
- After implementation: re-run every local command above; `git status` must show
  exactly `scripts/scenes/frpc.sh` and `docs/ASP-SOP.md`; the R1 grep must hit
  only the SOP appendix and the task directory.

## Rollback

Delete `scripts/scenes/frpc.sh`, revert the SOP appendix. Nothing else changes.