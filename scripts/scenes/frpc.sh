#!/bin/sh
# ============================================================
#  ASP frpc session script (POSIX sh, for Linux deployments)
#
#  Starts the ASP server plus one frpc process per configuration in
#  one tmux session. Optional composition script: the core deployment
#  scripts do not call or depend on this file.
#
#  Usage:
#    scripts/scenes/frpc.sh up --config <dir|file> \
#        [--config <dir|file>]... [--no-attach] [--dry-run]
#    scripts/scenes/frpc.sh down
#    scripts/scenes/frpc.sh status
#    scripts/scenes/frpc.sh attach
#
#  A --config directory expands to its immediate non-hidden regular
#  files in name order; a file is used as given. Repeat --config for
#  more than one input.
#
#  Requires: POSIX sh, tmux, frpc. --dry-run does not need tmux.
# ============================================================
set -eu

SESSION=asp-frpc
SERVER_WINDOW=server
STOP_TIMEOUT=${FRPC_STOP_TIMEOUT:-180}

LC_ALL=C
export LC_ALL

case "$0" in
    */*)
        SCRIPT_DIR=${0%/*}
        ;;
    *)
        SCRIPT_DIR=.
        ;;
esac
if ! SCRIPT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR" 2>/dev/null && pwd -P); then
    echo "[frpc] ERROR: cannot resolve the script directory" >&2
    exit 1
fi
if ! ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." 2>/dev/null && pwd -P); then
    echo "[frpc] ERROR: cannot resolve the repository root" >&2
    exit 1
fi

usage() {
    printf '%s\n' \
        'Usage:' \
        '  scripts/scenes/frpc.sh up --config <dir|file> [--config <dir|file>]... [--no-attach] [--dry-run]' \
        '  scripts/scenes/frpc.sh down' \
        '  scripts/scenes/frpc.sh status' \
        '  scripts/scenes/frpc.sh attach' \
        '  scripts/scenes/frpc.sh help'
}

# Set _q_result to a POSIX single-quoted representation of $1.
quote_sh() {
    _q_text=$1
    _q_result="'"
    while [ -n "$_q_text" ]; do
        _q_char=${_q_text%"${_q_text#?}"}
        _q_text=${_q_text#?}
        if [ "$_q_char" = "'" ]; then
            _q_result="$_q_result'\\''"
        else
            _q_result=$_q_result$_q_char
        fi
    done
    _q_result=$_q_result"'"
}

# Append one resolved config, rejecting duplicate window names.
add_config() {
    _ac_path=$1

    case "
$_seen_paths
" in
        *"
$_ac_path
"*)
            return 0
            ;;
    esac

    _ac_base=${_ac_path##*/}
    case "$_ac_base" in
        .*)
            _ac_name=$_ac_base
            ;;
        *.*)
            _ac_name=${_ac_base%.*}
            ;;
        *)
            _ac_name=$_ac_base
            ;;
    esac

    _ac_bare=
    _ac_rest=$_ac_name
    while [ -n "$_ac_rest" ]; do
        _ac_char=${_ac_rest%"${_ac_rest#?}"}
        _ac_rest=${_ac_rest#?}
        case "$_ac_char" in
            [A-Za-z0-9_-])
                _ac_bare=$_ac_bare$_ac_char
                ;;
            *)
                _ac_bare=${_ac_bare}_
                ;;
        esac
    done

    if [ "$_ac_bare" = "$SERVER_WINDOW" ]; then
        echo "[frpc] ERROR: config window name '$SERVER_WINDOW' is reserved: $_ac_path" >&2
        return 2
    fi

    case "
$_seen_bares
" in
        *"
$_ac_bare
"*)
            echo "[frpc] ERROR: two configs map to window name 'frpc-$_ac_bare'" >&2
            return 2
            ;;
    esac

    _seen_paths=$_seen_paths$_ac_path'
'
    _seen_bares=$_seen_bares$_ac_bare'
'
    _cfg_count=$((_cfg_count + 1))
    _resolved=$_resolved$_ac_bare'	'$_ac_path'
'
    return 0
}

# Resolve directory and file arguments into "<bare>\t<absolute path>" lines.
resolve_configs() {
    _cfg_count=0
    _seen_paths='
'
    _seen_bares='
'
    _resolved=

    for _cfg_input do
        if [ -d "$_cfg_input" ]; then
            if ! _cfg_dir=$(CDPATH= cd -- "$_cfg_input" 2>/dev/null && pwd -L); then
                echo "[frpc] ERROR: cannot resolve config directory: $_cfg_input" >&2
                return 2
            fi
            for _cfg_path in "$_cfg_dir"/*; do
                if [ ! -f "$_cfg_path" ]; then
                    continue
                fi
                if ! add_config "$_cfg_path"; then
                    return 2
                fi
            done
        elif [ -f "$_cfg_input" ]; then
            _cfg_base=${_cfg_input##*/}
            case "$_cfg_input" in
                */*)
                    _cfg_parent=${_cfg_input%/*}
                    if [ -z "$_cfg_parent" ]; then
                        _cfg_parent=/
                    fi
                    ;;
                *)
                    _cfg_parent=.
                    ;;
            esac
            if ! _cfg_parent=$(CDPATH= cd -- "$_cfg_parent" 2>/dev/null && pwd -L); then
                echo "[frpc] ERROR: cannot resolve config directory for: $_cfg_input" >&2
                return 2
            fi
            _cfg_path=${_cfg_parent%/}/$_cfg_base
            if ! add_config "$_cfg_path"; then
                return 2
            fi
        elif [ -e "$_cfg_input" ]; then
            echo "[frpc] ERROR: not a regular file or directory: $_cfg_input" >&2
            return 2
        else
            echo "[frpc] ERROR: no such config: $_cfg_input" >&2
            return 2
        fi
    done

    if [ "$_cfg_count" -eq 0 ]; then
        echo "[frpc] ERROR: --config resolved to no files" >&2
        return 2
    fi

    printf '%s' "$_resolved"
}

# Create a window with a placeholder process, apply its window options, then
# run the real command. Creating the placeholder first avoids a race where a
# command that exits immediately destroys the window before remain-on-exit
# can be applied, which makes the following tmux target lookup fail.
spawn_window() {
    _sw_session=$1
    _sw_name=$2
    _sw_command=$3

    if ! _sw_id=$(tmux new-window -P -F '#{window_id}' -t "$_sw_session" -n "$_sw_name" -c "$ROOT" -- cat); then
        return 1
    fi
    if ! tmux set-window-option -t "$_sw_id" remain-on-exit on; then
        return 1
    fi
    if ! tmux set-window-option -t "$_sw_id" monitor-activity on; then
        return 1
    fi
    tmux respawn-window -k -t "$_sw_id" "$_sw_command"
}

cmd_up() {
    _config_inputs=
    _have_config=0
    _no_attach=0
    _dry_run=0

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --config)
                if [ "$#" -lt 2 ]; then
                    echo "[frpc] ERROR: --config needs one path" >&2
                    exit 2
                fi
                _config_inputs=$_config_inputs$2'
'
                _have_config=1
                shift 2
                ;;
            --no-attach)
                _no_attach=1
                shift
                ;;
            --dry-run)
                _dry_run=1
                shift
                ;;
            *)
                echo "[frpc] ERROR: unknown up option: $1" >&2
                usage >&2
                exit 2
                ;;
        esac
    done

    if [ "$_have_config" -eq 0 ]; then
        echo "[frpc] ERROR: up needs at least one --config <dir|file>" >&2
        exit 2
    fi

    _old_ifs=$IFS
    IFS='
'
    set -f
    set -- $_config_inputs
    set +f
    IFS=$_old_ifs

    if _resolved=$(resolve_configs "$@"); then
        :
    else
        _resolve_status=$?
        exit "$_resolve_status"
    fi

    quote_sh "$ROOT"
    _root_quoted=$_q_result
    quote_sh 'bash scripts/start.sh'
    _server_command_quoted=$_q_result

    if [ "$_dry_run" -eq 1 ]; then
        printf 'tmux new-session -d -P -F %s -s %s -n %s -c %s -- cat\n' \
            "'#{window_id}'" "$SESSION" "$SERVER_WINDOW" "$_root_quoted"
        printf 'tmux set-option -s history-limit 50000\n'
        printf 'tmux set-window-option -t <server-window-id> remain-on-exit on\n'
        printf 'tmux set-window-option -t <server-window-id> monitor-activity on\n'
        printf 'tmux respawn-window -k -t <server-window-id> %s\n' "$_server_command_quoted"
        while IFS= read -r _line; do
            _bare=${_line%%'	'*}
            _path=${_line#*'	'}
            quote_sh "$_path"
            _path_quoted=$_q_result
            _sidecar_command="frpc -c $_path_quoted"
            quote_sh "$_sidecar_command"
            _sidecar_command_quoted=$_q_result
            printf 'tmux new-window -P -F %s -t %s -n %s -c %s -- cat\n' \
                "'#{window_id}'" "=$SESSION" "frpc-$_bare" "$_root_quoted"
            printf 'tmux set-window-option -t <window-id> remain-on-exit on\n'
            printf 'tmux set-window-option -t <window-id> monitor-activity on\n'
            printf 'tmux respawn-window -k -t <window-id> %s\n' "$_sidecar_command_quoted"
        done <<EOF
$_resolved
EOF
        return 0
    fi

    if ! command -v tmux >/dev/null 2>&1; then
        echo "[frpc] ERROR: tmux not found (install it or add it to PATH)" >&2
        exit 2
    fi

    if tmux has-session -t "=$SESSION" 2>/dev/null; then
        if [ "$_no_attach" -eq 1 ]; then
            printf '[frpc] session %s already exists; not attaching\n' "$SESSION"
            return 0
        fi
        if [ ! -t 0 ]; then
            printf '[frpc] session %s already exists; stdin is not a terminal\n' "$SESSION"
            return 0
        fi
        printf '[frpc] session %s already exists; attaching\n' "$SESSION"
        tmux attach-session -t "=$SESSION"
        return 0
    fi

    if ! _server_window_id=$(tmux new-session -d -P -F '#{window_id}' -s "$SESSION" -n "$SERVER_WINDOW" -c "$ROOT" -- cat); then
        echo "[frpc] ERROR: could not create tmux session $SESSION" >&2
        exit 1
    fi
    if ! tmux set-option -s history-limit 50000; then
        echo "[frpc] ERROR: could not configure the tmux server" >&2
        exit 1
    fi
    if ! tmux set-window-option -t "$_server_window_id" remain-on-exit on; then
        echo "[frpc] ERROR: could not configure the server window" >&2
        exit 1
    fi
    if ! tmux set-window-option -t "$_server_window_id" monitor-activity on; then
        echo "[frpc] ERROR: could not configure the server window" >&2
        exit 1
    fi
    tmux respawn-window -k -t "$_server_window_id" 'bash scripts/start.sh'

    while IFS= read -r _line; do
        _bare=${_line%%'	'*}
        _path=${_line#*'	'}
        quote_sh "$_path"
        _sidecar_command="frpc -c $_q_result"
        if ! spawn_window "=$SESSION" "frpc-$_bare" "$_sidecar_command"; then
            echo "[frpc] WARNING: could not create window frpc-$_bare" >&2
        fi
    done <<EOF
$_resolved
EOF

    if [ "$_no_attach" -eq 1 ]; then
        printf '[frpc] started session %s without attaching\n' "$SESSION"
        return 0
    fi
    if [ ! -t 0 ]; then
        printf '[frpc] started session %s; stdin is not a terminal\n' "$SESSION"
        return 0
    fi
    tmux attach-session -t "=$SESSION"
}

cmd_down() {
    if [ "$#" -ne 0 ]; then
        usage >&2
        exit 2
    fi
    case "$STOP_TIMEOUT" in
        ''|*[!0-9]*)
            echo "[frpc] ERROR: FRPC_STOP_TIMEOUT must be a whole number of seconds" >&2
            exit 2
            ;;
    esac
    if ! command -v tmux >/dev/null 2>&1; then
        echo "[frpc] ERROR: tmux not found (install it or add it to PATH)" >&2
        exit 2
    fi
    if ! tmux has-session -t "=$SESSION" 2>/dev/null; then
        printf '[frpc] no session %s\n' "$SESSION"
        return 0
    fi

    tmux send-keys -t "=$SESSION:$SERVER_WINDOW" stop Enter
    _dead=0
    _elapsed=0
    while [ "$_elapsed" -lt "$STOP_TIMEOUT" ]; do
        if ! _dead=$(tmux list-panes -t "=$SESSION:$SERVER_WINDOW" -F '#{pane_dead}' 2>/dev/null); then
            _dead=1
            break
        fi
        if [ "$_dead" = 1 ]; then
            break
        fi
        sleep 2
        _elapsed=$((_elapsed + 2))
    done

    if [ "$_dead" != 1 ]; then
        echo "[frpc] WARNING: server did not stop within ${STOP_TIMEOUT}s; session left running" >&2
        return 1
    fi

    if tmux has-session -t "=$SESSION" 2>/dev/null; then
        tmux kill-session -t "=$SESSION"
    fi
}

cmd_status() {
    if [ "$#" -ne 0 ]; then
        usage >&2
        exit 2
    fi
    if ! command -v tmux >/dev/null 2>&1; then
        echo "[frpc] ERROR: tmux not found (install it or add it to PATH)" >&2
        exit 2
    fi
    if ! tmux has-session -t "=$SESSION" 2>/dev/null; then
        printf '[frpc] no session %s\n' "$SESSION"
        return 0
    fi

    if ! _windows=$(tmux list-windows -t "=$SESSION" -F '#{window_name}	#{pane_dead}	#{pane_current_command}'); then
        echo "[frpc] ERROR: cannot list windows for $SESSION" >&2
        return 1
    fi

    while IFS= read -r _line; do
        _name=${_line%%'	'*}
        _rest=${_line#*'	'}
        _dead=${_rest%%'	'*}
        _command=${_rest#*'	'}
        _last=
        if _capture=$(tmux capture-pane -p -J -t "=$SESSION:$_name" 2>/dev/null); then
            while IFS= read -r _log_line; do
                if [ -n "$_log_line" ]; then
                    _last=$_log_line
                fi
            done <<EOF
$_capture
EOF
        fi
        if [ -z "$_last" ]; then
            _last='<no output>'
        fi
        printf '%s\t%s\t%s\t%s\n' "$_name" "$_dead" "$_command" "$_last"
    done <<EOF
$_windows
EOF
}

cmd_attach() {
    if [ "$#" -ne 0 ]; then
        usage >&2
        exit 2
    fi
    if ! command -v tmux >/dev/null 2>&1; then
        echo "[frpc] ERROR: tmux not found (install it or add it to PATH)" >&2
        exit 2
    fi
    if ! tmux has-session -t "=$SESSION" 2>/dev/null; then
        printf '[frpc] no session %s\n' "$SESSION" >&2
        return 1
    fi
    tmux attach-session -t "=$SESSION"
}

if [ "$#" -eq 0 ]; then
    usage >&2
    exit 2
fi

_verb=$1
shift
case "$_verb" in
    up)
        cmd_up "$@"
        ;;
    down)
        cmd_down "$@"
        ;;
    status)
        cmd_status "$@"
        ;;
    attach)
        cmd_attach "$@"
        ;;
    help)
        if [ "$#" -ne 0 ]; then
            usage >&2
            exit 2
        fi
        usage
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
