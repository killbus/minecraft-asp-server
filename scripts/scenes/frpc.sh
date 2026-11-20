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
#        [--config <dir|file>]... [--no-attach] [--defer-server] [--dry-run]
#    scripts/scenes/frpc.sh up --scene <file> \
#        [--no-attach] [--defer-server] [--dry-run]
#    scripts/scenes/frpc.sh down
#    scripts/scenes/frpc.sh status
#    scripts/scenes/frpc.sh attach
#
#  A --config directory expands to its immediate non-hidden regular
#  files that are named like frpc configurations (.ini, .toml, .yaml,
#  .yml), in name order; anything else in the directory is reported on
#  stderr and ignored, so a key file or a backup cannot be handed to
#  frpc. A file is used as given whatever it is called. Repeat --config
#  for more than one input.
#
#  --scene reads a small operator-owned manifest instead. It exists for
#  arrangements --config cannot express: several frpc processes run by
#  different binaries (a provider fork for the TCP entries, the official
#  client for a UDP tunnel, whose PROXY v2 header the fork does not
#  forward) and a scene that owns no server at all. One section is
#  exactly one frpc process, one configuration and one window:
#
#    session = asp-frpc
#    server = false
#
#    [udp]
#    binary = /root/asp-frpcs/bin/frpc
#    config = /root/asp-frpcs/official-udp.toml
#
#  session and server are required; server is true or false and says
#  whether this scene owns the server window. A relative binary or config
#  means "next to the scene file", while a bare binary is a command name
#  looked up on PATH. --scene and --config are mutually exclusive.
#
#  Every sidecar starts in the directory of its own configuration, so the
#  relative paths inside a configuration (certificates, logs, plugin
#  files) resolve against the file the operator wrote, not against the
#  repository.
#
#  The server window is started last, after every frpc sidecar has stayed
#  alive for FRPC_READY_TIMEOUT seconds. --defer-server leaves it as a
#  placeholder so a composing scene can start other prerequisites first.
#  A scene that says server = false gets no server window at all: its
#  first sidecar is the session's initial window, and none of the server
#  placeholder bookkeeping is created.
#
#  Every pane gets a UTF-8 locale, whatever the caller's is: the server
#  console is UTF-8 and the server transcodes it to the locale it starts
#  with. The script's own LC_ALL=C stays, for deterministic globbing and
#  case matching, and every tmux call it makes runs in the pane locale,
#  which is also what decides how tmux renders and captures multibyte
#  text. FRPC_PANEL_LOCALE overrides the choice.
#
#  Requires: POSIX sh, tmux, frpc. --dry-run does not need tmux.
# ============================================================
set -eu

SERVER_WINDOW=server
STOP_TIMEOUT=${FRPC_STOP_TIMEOUT:-180}
READY_TIMEOUT=${FRPC_READY_TIMEOUT:-5}
FRPC=${FRPC:-frpc}
# A carriage return, so a scene manifest that was last saved by an editor on
# another platform is read as the operator meant it and not with a stray
# character appended to every value.
CR=$(printf '\r')

# Captured before the C locale below, which belongs to this script alone.
_caller_locale=${LC_ALL-}

LC_ALL=C
export LC_ALL

# The panes must not inherit that C locale. The server console is UTF-8 and
# the server transcodes it to the locale it starts with, so a C pane puts
# question marks or mojibake where the console had Chinese. The caller's own
# UTF-8 locale is preferred, then C.UTF-8, which glibc carries itself;
# FRPC_PANEL_LOCALE overrides both.
PANEL_LOCALE=${FRPC_PANEL_LOCALE:-}
if [ -z "$PANEL_LOCALE" ]; then
    for _panel_candidate in "$_caller_locale" "${LANG:-}" C.UTF-8; do
        case "$_panel_candidate" in
            *[Uu][Tt][Ff]-8|*[Uu][Tt][Ff]8)
                PANEL_LOCALE=$_panel_candidate
                break
                ;;
        esac
    done
fi

# The tmux binary, resolved before the wrapper below hides the name from
# `command -v`.
TMUX_BIN=$(command -v tmux 2>/dev/null || true)

# Every tmux call runs in the panel locale: the client's own locale is what
# decides how tmux renders and captures multibyte text, and what a pane it
# starts inherits.
tmux() {
    LC_ALL=$PANEL_LOCALE "$TMUX_BIN" "$@"
}

SESSION=${FRPC_SESSION:-asp-frpc}
case "$SESSION" in
    ''|*[!A-Za-z0-9_-]*)
        echo "[frpc] ERROR: FRPC_SESSION must use only letters, digits, '_' and '-'" >&2
        exit 2
        ;;
esac

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
        '  scripts/scenes/frpc.sh up --config <dir|file> [--config <dir|file>]... [--world NAME] [--no-attach] [--defer-server] [--dry-run]' \
        '  scripts/scenes/frpc.sh up --scene <file> [--world NAME] [--no-attach] [--defer-server] [--dry-run]' \
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

# frpc reads .ini (frp 0.51 and older) and .toml, .yaml/.yml or .json
# (0.52 and newer). Only the file-name extensions a directory input may
# select are listed here: a name is matched portably, without tr.
is_config_name() {
    case "$1" in
        *.[Ii][Nn][Ii]|*.[Tt][Oo][Mm][Ll]|*.[Yy][Aa][Mm][Ll]|*.[Yy][Mm][Ll])
            return 0
            ;;
    esac
    return 1
}

# Set _sidecar to the command for one configuration: the selected frpc runs
# with the configuration's own directory as its working directory, because
# frpc resolves the relative paths inside a configuration (certificates,
# logs, plugin files) against the working directory. exec leaves frpc as the
# process of the pane, so its exit is what remain-on-exit shows.
sidecar_command() {
    _sc_binary=$1
    _sc_path=$2
    _sc_dir=${_sc_path%/*}
    [ -n "$_sc_dir" ] || _sc_dir=/
    quote_sh "$_sc_binary"
    _sc_binary_quoted=$_q_result
    quote_sh "$_sc_path"
    _sc_path_quoted=$_q_result
    quote_sh "$_sc_dir"
    _sc_dir_quoted=$_q_result
    _sidecar="cd $_sc_dir_quoted && exec $_sc_binary_quoted -c $_sc_path_quoted"
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
                if ! is_config_name "${_cfg_path##*/}"; then
                    echo "[frpc] note: ignoring $_cfg_path (not .ini/.toml/.yaml/.yml)" >&2
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

# ---------------------------------------------------------------
#  Scene manifests (--scene)
# ---------------------------------------------------------------

# Set _trim_result to $1 without leading or trailing whitespace.
trim() {
    _trim_result=$1
    _trim_result=${_trim_result#"${_trim_result%%[![:space:]]*}"}
    _trim_result=${_trim_result%"${_trim_result##*[![:space:]]}"}
}

# Return 0 when $1 contains a control character. The record parser below is
# line- and tab-delimited, so a value that can introduce another delimiter is
# a malformed manifest entry, not a path this script can represent safely.
has_control_chars() {
    case "$1" in
        *[[:cntrl:]]*)
            return 0
            ;;
    esac
    return 1
}

# Set _q_result to a scene path. A binary that is a bare word stays a command
# name for PATH to resolve at start; a config that is a bare word is a file
# next to the scene, because a config is data and not an executable. A value
# with a slash, and an absolute value, are both filesystem paths.
scene_path() {
    _sp_value=$1
    _sp_kind=$2
    case "$_sp_value" in
        /*)
            _q_result=$_sp_value
            return 0
            ;;
        */*)
            # A leading "./" is how an operator writes "next to the scene";
            # drop it so the joined path stays readable. The slash is what
            # makes this a path, so it is classified before the drop.
            _sp_rel=${_sp_value#./}
            _q_result=${_scene_dir%/}/$_sp_rel
            return 0
            ;;
    esac
    if [ "$_sp_kind" = binary ]; then
        _q_result=$_sp_value
        return 0
    fi
    _q_result=${_scene_dir%/}/$_sp_value
    return 0
}

# Set _q_result to an executable path for a scene binary value, and fail when
# it names nothing this host can run. A bare word is looked up on PATH here,
# not at parse time: --dry-run must still work without the binary installed.
resolve_binary_command() {
    _rb_value=$1
    case "$_rb_value" in
        /*|*/*)
            if [ ! -f "$_rb_value" ]; then
                echo "[frpc] ERROR: no such frpc binary: $_rb_value" >&2
                return 2
            fi
            if [ ! -x "$_rb_value" ]; then
                echo "[frpc] ERROR: frpc binary is not executable: $_rb_value" >&2
                return 2
            fi
            _q_result=$_rb_value
            return 0
            ;;
    esac
    if ! _rb_path=$(command -v "$_rb_value" 2>/dev/null); then
        echo "[frpc] ERROR: frpc binary not found (give a path or put it on PATH): $_rb_value" >&2
        return 2
    fi
    _q_result=$_rb_path
    return 0
}

# Append the section being read to _resolved once it is complete.
flush_scene_section() {
    if [ -z "$_cur_name" ]; then
        return 0
    fi
    if [ "$_cur_has_binary" -ne 1 ]; then
        echo "[frpc] ERROR: section [$_cur_name] needs a binary" >&2
        return 2
    fi
    if [ "$_cur_has_config" -ne 1 ]; then
        echo "[frpc] ERROR: section [$_cur_name] needs a config" >&2
        return 2
    fi
    _resolved=$_resolved$_cur_name'	'$_cur_binary'	'$_cur_config'
'
    return 0
}

# Set _scene_session, _scene_server and _resolved from a scene manifest. The
# manifest is read, never sourced: no substitution, no command, no inline
# comment. Records are "<section>\t<binary>\t<config>" lines; a binary that
# is a bare command name is kept as written and resolved on PATH at start.
parse_scene() {
    _ps_input=$1
    case "$_ps_input" in
        */*)
            _ps_dir=${_ps_input%/*}
            [ -n "$_ps_dir" ] || _ps_dir=/
            ;;
        *)
            _ps_dir=.
            ;;
    esac
    if ! _ps_dir=$(CDPATH= cd -- "$_ps_dir" 2>/dev/null && pwd -P); then
        echo "[frpc] ERROR: cannot resolve the scene directory: $_ps_input" >&2
        return 2
    fi
    _ps_path=${_ps_dir%/}/${_ps_input##*/}
    if [ ! -f "$_ps_path" ]; then
        echo "[frpc] ERROR: no such scene file: $_ps_path" >&2
        return 2
    fi
    if [ ! -r "$_ps_path" ]; then
        echo "[frpc] ERROR: cannot read the scene file: $_ps_path" >&2
        return 2
    fi
    _scene_dir=$_ps_dir

    _scene_session=
    _scene_server=
    _have_session=0
    _have_server=0
    _resolved=
    _scene_names='
'
    _cur_name=
    _cur_binary=
    _cur_config=
    _cur_has_binary=0
    _cur_has_config=0
    _ps_sections=0

    while IFS= read -r _ps_line || [ -n "$_ps_line" ]; do
        _ps_line=${_ps_line%"$CR"}
        trim "$_ps_line"
        _ps_line=$_trim_result

        if [ -z "$_ps_line" ]; then
            continue
        fi
        case "$_ps_line" in
            \#*)
                continue
                ;;
            \[*\])
                _ps_name=${_ps_line#\[}
                _ps_name=${_ps_name%\]}
                case "$_ps_name" in
                    ''|*[!A-Za-z0-9_-]*)
                        echo "[frpc] ERROR: section names use only letters, digits, '_' and '-': $_ps_name" >&2
                        return 2
                        ;;
                esac
                if ! flush_scene_section; then
                    return 2
                fi
                case "
$_scene_names
" in
                    *"
$_ps_name
"*)
                        echo "[frpc] ERROR: duplicate section [$_ps_name]" >&2
                        return 2
                        ;;
                esac
                _scene_names=$_scene_names$_ps_name'
'
                _cur_name=$_ps_name
                _cur_binary=
                _cur_config=
                _cur_has_binary=0
                _cur_has_config=0
                _ps_sections=$((_ps_sections + 1))
                continue
                ;;
        esac

        case "$_ps_line" in
            *=*)
                ;;
            *)
                echo "[frpc] ERROR: expecting 'key = value' or a [section] line: $_ps_line" >&2
                return 2
                ;;
        esac
        _ps_key=${_ps_line%%=*}
        _ps_value=${_ps_line#*=}
        trim "$_ps_key"
        _ps_key=$_trim_result
        trim "$_ps_value"
        _ps_value=$_trim_result
        if [ -z "$_ps_key" ]; then
            echo "[frpc] ERROR: empty key: $_ps_line" >&2
            return 2
        fi
        if [ -z "$_ps_value" ]; then
            echo "[frpc] ERROR: empty value for '$_ps_key'" >&2
            return 2
        fi
        if has_control_chars "$_ps_value"; then
            echo "[frpc] ERROR: control characters are not allowed in '$_ps_key' values" >&2
            return 2
        fi

        if [ -z "$_cur_name" ]; then
            # Top-level keys live before the first section. Once a section has
            # started there is no way back to them, which is what keeps a
            # mistyped "session" from silently becoming a section key.
            case "$_ps_key" in
                session)
                    if [ "$_have_session" -eq 1 ]; then
                        echo "[frpc] ERROR: duplicate top-level key 'session'" >&2
                        return 2
                    fi
                    case "$_ps_value" in
                        ''|*[!A-Za-z0-9_-]*)
                            echo "[frpc] ERROR: session uses only letters, digits, '_' and '-': $_ps_value" >&2
                            return 2
                            ;;
                    esac
                    _scene_session=$_ps_value
                    _have_session=1
                    ;;
                server)
                    if [ "$_have_server" -eq 1 ]; then
                        echo "[frpc] ERROR: duplicate top-level key 'server'" >&2
                        return 2
                    fi
                    case "$_ps_value" in
                        true|false)
                            ;;
                        *)
                            echo "[frpc] ERROR: server must be 'true' or 'false': $_ps_value" >&2
                            return 2
                            ;;
                    esac
                    _scene_server=$_ps_value
                    _have_server=1
                    ;;
                *)
                    echo "[frpc] ERROR: unknown top-level key '$_ps_key'; top-level keys precede the first section" >&2
                    return 2
                    ;;
            esac
            continue
        fi

        case "$_ps_key" in
            binary)
                if [ "$_cur_has_binary" -eq 1 ]; then
                    echo "[frpc] ERROR: duplicate key 'binary' in section [$_cur_name]" >&2
                    return 2
                fi
                scene_path "$_ps_value" binary
                _cur_binary=$_q_result
                _cur_has_binary=1
                ;;
            config)
                if [ "$_cur_has_config" -eq 1 ]; then
                    echo "[frpc] ERROR: duplicate key 'config' in section [$_cur_name]" >&2
                    return 2
                fi
                scene_path "$_ps_value" config
                _cur_config=$_q_result
                if [ ! -f "$_cur_config" ]; then
                    echo "[frpc] ERROR: no such config in section [$_cur_name]: $_cur_config" >&2
                    return 2
                fi
                if [ ! -r "$_cur_config" ]; then
                    echo "[frpc] ERROR: cannot read config in section [$_cur_name]: $_cur_config" >&2
                    return 2
                fi
                _cur_has_config=1
                ;;
            *)
                echo "[frpc] ERROR: unknown key '$_ps_key' in section [$_cur_name]" >&2
                return 2
                ;;
        esac
    done < "$_ps_path"

    if ! flush_scene_section; then
        return 2
    fi
    if [ "$_ps_sections" -eq 0 ]; then
        echo "[frpc] ERROR: the scene declares no sections: $_ps_path" >&2
        return 2
    fi
    if [ "$_have_session" -ne 1 ]; then
        echo "[frpc] ERROR: the scene needs a top-level session: $_ps_path" >&2
        return 2
    fi
    if [ "$_have_server" -ne 1 ]; then
        echo "[frpc] ERROR: the scene needs a top-level server: $_ps_path" >&2
        return 2
    fi
    return 0
}

# Decode one resolved record. Legacy --config records are "<name>\t<config>";
# scene records are "<name>\t<binary>\t<config>". Both decoders live here so
# the dry run and the start path cannot drift apart. The mode is explicit:
# inferring it from a tab in the path would turn a legal legacy config name
# into a field separator.
decode_record() {
    _dr_line=$1
    _line_bare=${_dr_line%%'	'*}
    _dr_rest=${_dr_line#*'	'}
    if [ "${_records_have_binary:-0}" -eq 1 ]; then
        _line_binary=${_dr_rest%%'	'*}
        _line_config=${_dr_rest#*'	'}
    else
        _line_binary=
        _line_config=$_dr_rest
    fi
}

# Apply the window options every scene window needs. Applied while the window
# holds a placeholder process, so a command that exits immediately cannot
# destroy the window before the options land.
configure_window() {
    _cw_id=$1
    if ! tmux set-window-option -t "$_cw_id" remain-on-exit on; then
        return 1
    fi
    tmux set-window-option -t "$_cw_id" monitor-activity on
}

# Create a window with a placeholder process, apply its window options, then
# run the real command.
spawn_window() {
    _sw_session=$1
    _sw_name=$2
    _sw_command=$3

    if ! _sw_id=$(tmux new-window -P -F '#{window_id}' -t "$_sw_session" -n "$_sw_name" -c "$ROOT" -- cat); then
        return 1
    fi
    if ! configure_window "$_sw_id"; then
        return 1
    fi
    tmux respawn-window -k -t "$_sw_id" "$_sw_command"
}

# Return 0 only when every frpc window is still alive after the grace
# period. remain-on-exit keeps a failed sidecar visible for inspection.
wait_for_sidecars() {
    _ws_elapsed=0
    while :; do
        while IFS= read -r _ws_line; do
            [ -n "$_ws_line" ] || continue
            _ws_bare=${_ws_line%%'	'*}
            if ! _ws_dead=$(tmux list-panes -t "=$SESSION:frpc-$_ws_bare" -F '#{pane_dead}' 2>/dev/null); then
                _ws_dead=1
            fi
            if [ "$_ws_dead" != 0 ]; then
                echo "[frpc] ERROR: sidecar frpc-$_ws_bare is not running; server not started" >&2
                if _ws_capture=$(tmux capture-pane -p -J -t "=$SESSION:frpc-$_ws_bare" 2>/dev/null); then
                    printf '%s\n' "$_ws_capture" | tail -n 20 >&2
                fi
                return 1
            fi
        done <<EOF
$_resolved
EOF
        if [ "$_ws_elapsed" -ge "$READY_TIMEOUT" ]; then
            return 0
        fi
        sleep 1
        _ws_elapsed=$((_ws_elapsed + 1))
    done
}

cmd_up() {
    _config_inputs=
    _have_config=0
    _scene_file=
    _have_scene=0
    _no_attach=0
    _defer_server=0
    _dry_run=0
    _records_have_binary=0
    _world_name=

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
            --scene)
                if [ "$#" -lt 2 ]; then
                    echo "[frpc] ERROR: --scene needs one file" >&2
                    exit 2
                fi
                if [ "$_have_scene" -eq 1 ]; then
                    echo "[frpc] ERROR: --scene may be given only once" >&2
                    exit 2
                fi
                _scene_file=$2
                _have_scene=1
                shift 2
                ;;
            --world)
                if [ "$#" -lt 2 ] || [ -n "$_world_name" ]; then
                    echo "[frpc] ERROR: --world requires one native save name, once" >&2
                    exit 2
                fi
                case "$2" in
                    ''|*[!A-Za-z0-9_-]*)
                        echo "[frpc] ERROR: --world requires ASCII letters, digits, _ or -" >&2
                        exit 2
                        ;;
                esac
                _world_name=$2
                shift 2
                ;;
            --no-attach)
                _no_attach=1
                shift
                ;;
            --defer-server)
                _defer_server=1
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

    if [ "$_have_scene" -eq 1 ] && [ "$_have_config" -eq 1 ]; then
        echo "[frpc] ERROR: --scene and --config are mutually exclusive" >&2
        exit 2
    fi
    if [ "$_have_scene" -eq 0 ] && [ "$_have_config" -eq 0 ]; then
        echo "[frpc] ERROR: up needs --config <dir|file> or --scene <file>" >&2
        exit 2
    fi
    case "$READY_TIMEOUT" in
        ''|*[!0-9]*)
            echo "[frpc] ERROR: FRPC_READY_TIMEOUT must be a whole number of seconds" >&2
            exit 2
            ;;
    esac

    _want_server=1
    if [ "$_have_scene" -eq 1 ]; then
        if ! parse_scene "$_scene_file"; then
            exit 2
        fi
        _records_have_binary=1
        # FRPC_SESSION stays the composition and test hook: the shared-TCP
        # wrapper sets it so the session it adds the mux to is the one the
        # sidecars landed in. Without it the manifest names the session.
        if [ -z "${FRPC_SESSION:-}" ]; then
            SESSION=$_scene_session
            if [ "$SESSION" != asp-frpc ]; then
                printf '[frpc] scene names session %s; set FRPC_SESSION=%s to reach it with down/status/attach\n' \
                    "$SESSION" "$SESSION" >&2
            fi
        fi
        if [ "$_scene_server" = false ]; then
            _want_server=0
        fi
        if [ "$_defer_server" -eq 1 ]; then
            # A composing scene needs the placeholder even when the manifest
            # says server = false: the wrapper owns the eventual start.
            _want_server=1
        fi
    else
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
    fi

    quote_sh "$ROOT"
    _root_quoted=$_q_result
    _server_command='bash scripts/start.sh'
    if [ -n "$_world_name" ]; then
        if [ "$_want_server" -eq 0 ]; then
            echo "[frpc] ERROR: --world requires a scene that starts a server" >&2
            exit 2
        fi
        if [ ! -f "$ROOT/server/$_world_name/level.dat" ] ||
           [ -L "$ROOT/server/$_world_name" ] || [ -L "$ROOT/server/$_world_name/level.dat" ]; then
            echo "[frpc] ERROR: --world requires an existing native save at server/$_world_name/level.dat (no links)" >&2
            exit 2
        fi
        quote_sh "$_world_name"
        _server_command="$_server_command --world $_q_result"
    fi

    if [ "$_dry_run" -eq 1 ]; then
        # 1 means the next record creates the session as its initial window.
        _dry_initial=$((1 - _want_server))
        if [ "$_want_server" -eq 1 ]; then
            printf 'tmux new-session -d -P -F %s -s %s -n %s -c %s -- cat\n' \
                "'#{window_id}'" "$SESSION" "$SERVER_WINDOW" "$_root_quoted"
            printf 'tmux set-environment -t %s LC_ALL %s\n' "=$SESSION" "$PANEL_LOCALE"
            printf 'tmux set-option -s history-limit 50000\n'
            printf 'tmux set-window-option -t <server-window-id> remain-on-exit on\n'
            printf 'tmux set-window-option -t <server-window-id> monitor-activity on\n'
            printf 'tmux set-window-option -t <server-window-id> @asp-server-deferred %s\n' "$_defer_server"
        fi
        while IFS= read -r _line; do
            [ -n "$_line" ] || continue
            decode_record "$_line"
            sidecar_command "${_line_binary:-$FRPC}" "$_line_config"
            _sidecar_command=$_sidecar
            if [ "$_dry_initial" -eq 1 ]; then
                _dry_initial=0
                printf 'tmux new-session -d -P -F %s -s %s -n %s -c %s -- cat\n' \
                    "'#{window_id}'" "$SESSION" "frpc-$_line_bare" "$_root_quoted"
                printf 'tmux set-environment -t %s LC_ALL %s\n' "=$SESSION" "$PANEL_LOCALE"
                printf 'tmux set-option -s history-limit 50000\n'
            else
                printf 'tmux new-window -P -F %s -t %s -n %s -c %s -- cat\n' \
                    "'#{window_id}'" "=$SESSION" "frpc-$_line_bare" "$_root_quoted"
            fi
            printf 'tmux set-window-option -t <window-id> remain-on-exit on\n'
            printf 'tmux set-window-option -t <window-id> monitor-activity on\n'
            printf 'tmux respawn-window -k -t <window-id> %s\n' "$_sidecar_command"
        done <<EOF
$_resolved
EOF
        if [ "$_want_server" -eq 0 ]; then
            printf '# server not started: the scene says server = false\n'
        elif [ "$_defer_server" -eq 1 ]; then
            printf '# server deferred; start it after the other prerequisites are ready\n'
        else
            printf 'tmux set-window-option -t <server-window-id> @asp-server-deferred 0\n'
            printf 'tmux respawn-window -k -t <server-window-id> %s\n' "$_server_command"
        fi
        return 0
    fi

    if [ -z "$TMUX_BIN" ]; then
        echo "[frpc] ERROR: tmux not found (install it or add it to PATH)" >&2
        exit 2
    fi

    # Resolve every binary to an absolute path before tmux is touched: the tmux
    # server may not share this shell's PATH, and a bad section must not leave
    # half a session behind. A manifest names one binary per section; the
    # legacy path still has the single FRPC.
    _frpc_bin=
    if [ "$_have_scene" -eq 1 ]; then
        _spawn_records=
        while IFS= read -r _line; do
            [ -n "$_line" ] || continue
            decode_record "$_line"
            if ! resolve_binary_command "$_line_binary"; then
                exit 2
            fi
            _spawn_records=$_spawn_records$_line_bare'	'$_q_result'	'$_line_config'
'
        done <<EOF
$_resolved
EOF
        _resolved=$_spawn_records
    else
        if ! command -v "$FRPC" >/dev/null 2>&1; then
            echo "[frpc] ERROR: frpc not found (set FRPC=/path/to/frpc or put it on PATH)" >&2
            exit 2
        fi
        if ! _frpc_bin=$(command -v "$FRPC"); then
            echo "[frpc] ERROR: cannot resolve the frpc binary: $FRPC" >&2
            exit 2
        fi
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

    # A scene without a server has nothing to put in front of its sidecars, so
    # the first one becomes the session's initial window and the rest are added
    # to it. With a server window the session exists before any sidecar starts.
    _session_ready=$_want_server
    if [ "$_want_server" -eq 1 ]; then
        if ! _server_window_id=$(tmux new-session -d -P -F '#{window_id}' -s "$SESSION" -n "$SERVER_WINDOW" -c "$ROOT" -- cat); then
            echo "[frpc] ERROR: could not create tmux session $SESSION" >&2
            exit 1
        fi
        if ! tmux set-environment -t "=$SESSION" LC_ALL "$PANEL_LOCALE"; then
            echo "[frpc] ERROR: could not give session $SESSION a UTF-8 locale" >&2
            exit 1
        fi
        if ! tmux set-option -s history-limit 50000; then
            echo "[frpc] ERROR: could not configure the tmux server" >&2
            exit 1
        fi
        if ! configure_window "$_server_window_id"; then
            echo "[frpc] ERROR: could not configure the server window" >&2
            exit 1
        fi
        if ! tmux set-window-option -t "$_server_window_id" @asp-server-deferred "$_defer_server"; then
            echo "[frpc] ERROR: could not mark the server window state" >&2
            exit 1
        fi
    fi

    while IFS= read -r _line; do
        [ -n "$_line" ] || continue
        decode_record "$_line"
        sidecar_command "${_line_binary:-$_frpc_bin}" "$_line_config"
        _sidecar_command=$_sidecar
        if [ "$_session_ready" -eq 0 ]; then
            _session_ready=1
            if ! _initial_window_id=$(tmux new-session -d -P -F '#{window_id}' -s "$SESSION" -n "frpc-$_line_bare" -c "$ROOT" -- cat); then
                echo "[frpc] ERROR: could not create tmux session $SESSION" >&2
                exit 1
            fi
            if ! tmux set-environment -t "=$SESSION" LC_ALL "$PANEL_LOCALE"; then
                echo "[frpc] ERROR: could not give session $SESSION a UTF-8 locale" >&2
                exit 1
            fi
            if ! tmux set-option -s history-limit 50000; then
                echo "[frpc] ERROR: could not configure the tmux server" >&2
                exit 1
            fi
            if ! configure_window "$_initial_window_id"; then
                echo "[frpc] ERROR: could not configure window frpc-$_line_bare" >&2
                exit 1
            fi
            if ! tmux respawn-window -k -t "$_initial_window_id" "$_sidecar_command"; then
                echo "[frpc] ERROR: could not start window frpc-$_line_bare" >&2
                exit 1
            fi
            continue
        fi
        if ! spawn_window "=$SESSION" "frpc-$_line_bare" "$_sidecar_command"; then
            echo "[frpc] ERROR: could not create window frpc-$_line_bare; server not started" >&2
            return 1
        fi
    done <<EOF
$_resolved
EOF

    if ! wait_for_sidecars; then
        printf '[frpc] sidecars are not healthy; server not started (session %s left running)\n' "$SESSION" >&2
        return 1
    fi

    if [ "$_want_server" -eq 0 ]; then
        printf '[frpc] sidecars ready; no server window in session %s (the scene says server = false)\n' "$SESSION"
        if [ "$_no_attach" -eq 1 ]; then
            return 0
        fi
        if [ ! -t 0 ]; then
            printf '[frpc] stdin is not a terminal; session %s left running\n' "$SESSION"
            return 0
        fi
        tmux attach-session -t "=$SESSION"
        return 0
    fi

    if [ "$_defer_server" -eq 1 ]; then
        printf '[frpc] sidecars ready; server deferred in session %s\n' "$SESSION"
        if [ "$_no_attach" -eq 1 ]; then
            return 0
        fi
        if [ ! -t 0 ]; then
            printf '[frpc] stdin is not a terminal; session %s left running\n' "$SESSION"
            return 0
        fi
        tmux attach-session -t "=$SESSION"
        return 0
    fi

    if ! tmux set-window-option -t "$_server_window_id" @asp-server-deferred 0; then
        echo "[frpc] ERROR: could not clear the deferred server state" >&2
        exit 1
    fi
    if ! tmux respawn-window -k -t "$_server_window_id" "$_server_command"; then
        echo "[frpc] ERROR: could not start the server window" >&2
        exit 1
    fi

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
    if [ -z "$TMUX_BIN" ]; then
        echo "[frpc] ERROR: tmux not found (install it or add it to PATH)" >&2
        exit 2
    fi
    if ! tmux has-session -t "=$SESSION" 2>/dev/null; then
        printf '[frpc] no session %s\n' "$SESSION"
        return 0
    fi

    # A scene that said server = false has no server window to send `stop` to;
    # killing the session is the whole teardown. A composer's deferred window
    # still exists, so it takes the branch below instead.
    if ! tmux list-panes -t "=$SESSION:$SERVER_WINDOW" -F '#{pane_dead}' >/dev/null 2>&1; then
        printf '[frpc] no server window in session %s; killing session\n' "$SESSION"
        tmux kill-session -t "=$SESSION"
        return 0
    fi

    if ! _deferred=$(tmux show-options -w -q -v -t "=$SESSION:$SERVER_WINDOW" @asp-server-deferred 2>/dev/null); then
        _deferred=
    fi
    if [ "$_deferred" = 1 ]; then
        printf '[frpc] server is still deferred; killing session %s\n' "$SESSION"
        tmux kill-session -t "=$SESSION"
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
    if [ -z "$TMUX_BIN" ]; then
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
    if [ -z "$TMUX_BIN" ]; then
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
