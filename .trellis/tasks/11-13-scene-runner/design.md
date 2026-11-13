# Design: scripts/scenes/frpc.sh

## Shape

One file, one function per verb, no sourcing, no shared helper. tmux
vocabulary lives here because this file is the only thing that has to be a tmux
composition.

```
frpc.sh
  usage
  resolve_configs <path...>    -> "<bare>\t<abs>" lines on stdout
  cmd_up <path...>
  cmd_down
  cmd_status
  cmd_attach
  dispatch                     -> case "$1" in up|down|status|attach|help
```

Constants at the top: `SESSION=asp-frpc`, `SERVER_WINDOW=server`,
`STOP_TIMEOUT=${FRPC_STOP_TIMEOUT:-180}`.

## Why the engine was dropped

The engine existed so one runner could serve N scenes. N was one. It cost a DSL,
a subshell source step, an environment contract, and the property that a scene
could not be run on its own - and it would have stayed the permanent interface
between this repository and a tmux session. A composition script that names its
own processes directly is smaller in every dimension that matters here: lines,
indirection, debugging steps.

The one property worth keeping survives: core stays independent. `start.sh`
does not know this file exists.

## Data flow

```
argv -> case $1 in
  up)
    parse: --config (repeat), --no-attach, --dry-run
    resolve_configs "$@"        # fail fast; tmux not touched yet
    if session exists: message; attach or return
    tmux new-session -d -s asp-frpc -n server -c "$ROOT" -- scripts/start.sh
    tmux set-option   -t asp-frpc remain-on-exit on
    tmux set-option   -t asp-frpc monitor-activity on
    tmux set-option   -t asp-frpc history-limit 50000
    for each <bare>\t<abs>:
        tmux new-window -t asp-frpc -n "frpc-$bare" -c "$ROOT" -- frpc -c "$abs"
    attach unless --no-attach or stdin is not a tty
  down)
    tmux send-keys -t asp-frpc:server 'stop' Enter
    poll tmux list-panes -t asp-frpc:server -F '#{pane_dead}'
    dead -> tmux kill-session -t asp-frpc
    timeout -> warn, exit 1
```

## Input resolution

- `--config` takes exactly one value and is repeatable. A space-separated list
  was rejected: one typo silently swallows the next flag.
- Directory: `find "$dir" -maxdepth 1 -type f ! -name '.*' | LC_ALL=C sort`.
  Not recursive, hidden files skipped, one level only.
- File: taken as given and made absolute; symlinks are not resolved.
- Anything else: `no such config: <path>`, exit 2.
- Dedupe on the absolute string, so a directory plus one of its own files
  collapses.
- Bare name: basename, strip the last extension when there is one
  (`a.toml` -> `a`, `a.b.toml` -> `a.b`, `frpc` -> `frpc`), then keep
  `[A-Za-z0-9_-]` and map the rest to `_`. Two inputs mapping to the same bare
  name, or to `server`, exit 2 before tmux runs.
- Order: argv order, with directory contents sorted inside each directory.
  No global re-sort; `--config` order is the operator's order.

## Failure isolation

`remain-on-exit on` is the whole mechanism: a sidecar that dies keeps its pane,
so `status` still names it and its last output is still readable. The script
never waits on or reaps sidecars and never restarts one - a restart is an
explicit `down` then `up`.

`down` cannot distinguish "server is slow" from "server is wedged". After
`FRPC_STOP_TIMEOUT` it reports and stops. It never escalates to a signal,
because a half-written region file is worse than the consequence.

## Testing

- Syntax: `sh -n`.
- Verb/flag matrix: `up`, `down`, `status`, `attach`, `help`, no verb, unknown
  verb, `--config` with no value, unknown flag.
- Resolution: dir, file, dir+file duplicate, two dirs with the same basename,
  empty dir, missing path, hidden file, nested dir (must not recurse), config
  named `server.toml`.
- Dry-run with tmux removed from `PATH`.
- Live: only on a Linux host, per the acceptance list.

## Rollback

One file: `rm scripts/scenes/frpc.sh`, plus the SOP appendix. No migration, no
state under `server/`, and nothing to undo in tmux beyond
`tmux kill-session -t asp-frpc`.
