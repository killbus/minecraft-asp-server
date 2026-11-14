#!/bin/sh
# ============================================================
#  ASP frpc shared-TCP scene (POSIX sh, Linux only; not core)
#
#  Runs the server, an HAProxy L4 demultiplexer and one frpc
#  process per configuration in one tmux session. Java Minecraft
#  TCP and Bedrock NetherNet built-in signalling share one public
#  TCP port; the Bedrock WebRTC media plane still needs its own
#  frpc UDP proxy.
#
#  Start order: frpc sidecars first, HAProxy second (it must bind the
#  listen port), the Java server last. MUX_READY_TIMEOUT (default 10)
#  bounds the HAProxy wait.
#
#  Usage:
#    scripts/scenes/frpc-shared-tcp.sh up --config <dir|file> \
#        [--config <dir|file>]... [--listen HOST:PORT] \
#        [--java HOST:PORT] [--bedrock HOST:PORT] \
#        [--tls-cert FILE] [--tls-listen HOST:PORT] \
#        [--haproxy-config FILE] [--no-attach] [--dry-run]
#    scripts/scenes/frpc-shared-tcp.sh down
#    scripts/scenes/frpc-shared-tcp.sh status
#    scripts/scenes/frpc-shared-tcp.sh attach
#    scripts/scenes/frpc-shared-tcp.sh help
#
#  Defaults:
#    --listen     127.0.0.1:25566
#    --java       127.0.0.1:25565
#    --bedrock    127.0.0.1:19132
#    --tls-listen 127.0.0.1:25567 (only with --tls-cert)
#
#  Without --haproxy-config the scene writes a generated HAProxy
#  config to .tmp/frpc-shared-tcp/haproxy.cfg (gitignored). The frpc
#  TCP proxy must point localPort at the mux listen port.
#
#  The demux sends a TLS ClientHello or an HTTP method prefix to
#  Geyser built-in signalling and everything else to Java. It does
#  not parse PROXY protocol: leave frpc's
#  transport.proxyProtocolVersion unset.
#
#  With --tls-cert the scene terminates TLS itself: the shared port
#  keeps the ClientHello on a second loopback bind (--tls-listen)
#  where HAProxy decrypts it and hands the plain bytes to Geyser. The
#  certificate is a combined PEM (chain plus private key) that lives
#  outside the repository; Geyser keeps its plain HTTP listener.
#
#  Requires: POSIX sh, tmux, frpc, haproxy.
# ============================================================
set -eu

SERVER_WINDOW=server
MUX_WINDOW=mux
SESSION=asp-frpc-shared
HAPROXY=${HAPROXY:-haproxy}
MUX_READY_TIMEOUT=${MUX_READY_TIMEOUT:-10}
MUX_LISTEN=${MUX_LISTEN:-127.0.0.1:25566}
MUX_JAVA=${MUX_JAVA:-127.0.0.1:25565}
MUX_BEDROCK=${MUX_BEDROCK:-127.0.0.1:19132}
MUX_TLS_LISTEN=${MUX_TLS_LISTEN:-127.0.0.1:25567}

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
    echo "[frpc-shared] ERROR: cannot resolve the script directory" >&2
    exit 1
fi
if ! ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." 2>/dev/null && pwd -P); then
    echo "[frpc-shared] ERROR: cannot resolve the repository root" >&2
    exit 1
fi

FRPC_SH=$SCRIPT_DIR/frpc.sh
DEFAULT_HAPROXY_CONFIG=$ROOT/.tmp/frpc-shared-tcp/haproxy.cfg

usage() {
    printf '%s\n' \
        'Usage:' \
        '  scripts/scenes/frpc-shared-tcp.sh up --config <dir|file> [--config <dir|file>]... [--listen HOST:PORT] [--java HOST:PORT] [--bedrock HOST:PORT] [--tls-cert FILE] [--tls-listen HOST:PORT] [--haproxy-config FILE] [--no-attach] [--dry-run]' \
        '  scripts/scenes/frpc-shared-tcp.sh down' \
        '  scripts/scenes/frpc-shared-tcp.sh status' \
        '  scripts/scenes/frpc-shared-tcp.sh attach' \
        '  scripts/scenes/frpc-shared-tcp.sh help'
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

# Set _q_result to a HAProxy configuration value for $1. HAProxy splits
# values on spaces unless they are double quoted, and bare paths are kept
# bare so the generated file stays readable.
haproxy_quote() {
    _hq_text=$1
    case "$_hq_text" in
        *[!A-Za-z0-9._/+-]*)
            _hq_escaped=
            while [ -n "$_hq_text" ]; do
                _hq_char=${_hq_text%"${_hq_text#?}"}
                _hq_text=${_hq_text#?}
                case "$_hq_char" in
                    '\\'|'"')
                        _hq_escaped=$_hq_escaped\\$_hq_char
                        ;;
                    *)
                        _hq_escaped=$_hq_escaped$_hq_char
                        ;;
                esac
            done
            _q_result="\"$_hq_escaped\""
            ;;
        *)
            _q_result=$_hq_text
            ;;
    esac
}

is_endpoint() {
    _ep=$1
    case "$_ep" in
        ''|*[!A-Za-z0-9.:\[\]-]*)
            return 1
            ;;
    esac
    case "$_ep" in
        *:*)
            ;;
        *)
            return 1
            ;;
    esac
    _ep_host=${_ep%:*}
    _ep_port=${_ep##*:}
    [ -n "$_ep_host" ] || return 1
    case "$_ep_host" in
        *:*)
            case "$_ep_host" in
                \[*\])
                    ;;
                *)
                    return 1
                    ;;
            esac
            ;;
    esac
    case "$_ep_port" in
        [1-9]|[1-9][0-9]|[1-9][0-9][0-9]|[1-9][0-9][0-9][0-9]|\
        [1-5][0-9][0-9][0-9][0-9]|6[0-4][0-9][0-9][0-9]|\
        65[0-4][0-9][0-9]|655[0-2][0-9]|6553[0-5])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# Print the generated HAProxy config for one listen/java/bedrock set.
# A non-empty $4 turns on TLS termination: the ClientHello is handed to a
# second loopback bind ($5) that HAProxy decrypts with the PEM in $4, so
# Geyser receives plain HTTP and needs no certificate of its own.
print_haproxy_config() {
    _ph_listen=$1
    _ph_java=$2
    _ph_bedrock=$3
    _ph_tls_cert=$4
    _ph_tls_listen=$5
    _ph_tls_cert_q=
    if [ -n "$_ph_tls_cert" ]; then
        haproxy_quote "$_ph_tls_cert"
        _ph_tls_cert_q=$_q_result
    fi
    cat <<EOF
# Generated by scripts/scenes/frpc-shared-tcp.sh; edits are overwritten.
# Java and Bedrock built-in signalling share this local TCP port.
global
    maxconn 4096

defaults
    mode tcp
    timeout connect 5s
    timeout client 1h
    timeout server 1h

frontend mc_shared
    bind $_ph_listen
    acl is_tls req.ssl_hello_type 1
    acl is_http payload(0,4) -m beg "GET " "POST" "HEAD" "PUT " "OPTI" "PATC" "DELE" "CONN" "TRAC" "PRI "
    acl is_java payload(0,1) -m bin fe
    acl is_java payload(1,1) -m bin 00
    tcp-request inspect-delay 3s
    tcp-request content accept if is_tls or is_http or is_java
EOF
    if [ -n "$_ph_tls_cert" ]; then
        cat <<EOF
    use_backend geyser_tls if is_tls
    use_backend geyser_signaling if is_http
EOF
    else
        cat <<EOF
    use_backend geyser_signaling if is_tls or is_http
EOF
    fi
    cat <<EOF
    default_backend java

backend geyser_signaling
    server geyser $_ph_bedrock

backend java
    server paper $_ph_java
EOF
    if [ -n "$_ph_tls_cert" ]; then
        cat <<EOF

# TLS is terminated here, not in Geyser: the decrypted stream reaches the
# same signalling backend byte for byte.
backend geyser_tls
    server termination $_ph_tls_listen

frontend geyser_tls_termination
    bind $_ph_tls_listen ssl crt $_ph_tls_cert_q
    default_backend geyser_signaling
EOF
    fi
}

generate_haproxy_config() {
    _gh_cfg=$1
    case "$_gh_cfg" in
        */*) _gh_dir=${_gh_cfg%/*} ;;
        *) _gh_dir=. ;;
    esac
    mkdir -p "$_gh_dir" || return 1
    _gh_tmp=${_gh_cfg}.tmp.$$
    if ! print_haproxy_config "$2" "$3" "$4" "$5" "$6" > "$_gh_tmp"; then
        rm -f "$_gh_tmp"
        return 1
    fi
    if ! mv -f "$_gh_tmp" "$_gh_cfg"; then
        rm -f "$_gh_tmp"
        return 1
    fi
}

haproxy_check() {
    if ! _hc_output=$("$HAPROXY" -c -f "$1" 2>&1); then
        printf '%s\n' "$_hc_output" >&2
        return 1
    fi
}

require_frpc() {
    if [ ! -f "$FRPC_SH" ]; then
        echo "[frpc-shared] ERROR: frpc scene not found: $FRPC_SH" >&2
        return 1
    fi
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

# Return 0 when LISTEN is accepting TCP, 1 when it is not, 2 when no
# listening-socket tool is available (caller may then trust the window).
mux_listen_check() {
    _ml_port=${LISTEN##*:}
    for _ml_tool in 'ss -ltn' 'netstat -ltn'; do
        _ml_bin=${_ml_tool%% *}
        command -v "$_ml_bin" >/dev/null 2>&1 || continue
        if _ml_out=$($_ml_tool 2>/dev/null); then
            if printf '%s\n' "$_ml_out" | awk '{print $4}' | grep -F ":$_ml_port" >/dev/null 2>&1; then
                return 0
            fi
            return 1
        fi
    done
    return 2
}

# Wait for the HAProxy window to stay alive and bind the listen port.
wait_mux_ready() {
    _wm_elapsed=0
    while [ "$_wm_elapsed" -lt "$MUX_READY_TIMEOUT" ]; do
        if ! _wm_dead=$(tmux list-panes -t "=$SESSION:$MUX_WINDOW" -F '#{pane_dead}' 2>/dev/null); then
            _wm_dead=1
        fi
        if [ "$_wm_dead" != 0 ]; then
            echo "[frpc-shared] ERROR: $MUX_WINDOW window is not running" >&2
            if _wm_capture=$(tmux capture-pane -p -J -t "=$SESSION:$MUX_WINDOW" 2>/dev/null); then
                printf '%s\n' "$_wm_capture" | tail -n 20 >&2
            fi
            return 1
        fi
        if [ "$_wm_elapsed" -ge 2 ]; then
            _wm_rc=0
            mux_listen_check || _wm_rc=$?
            if [ "$_wm_rc" -eq 0 ]; then
                return 0
            fi
            if [ "$_wm_rc" -eq 2 ]; then
                return 0
            fi
        fi
        sleep 1
        _wm_elapsed=$((_wm_elapsed + 1))
    done
    echo "[frpc-shared] ERROR: $MUX_WINDOW did not bind $LISTEN within ${MUX_READY_TIMEOUT}s" >&2
    if _wm_capture=$(tmux capture-pane -p -J -t "=$SESSION:$MUX_WINDOW" 2>/dev/null); then
        printf '%s\n' "$_wm_capture" | tail -n 20 >&2
    fi
    return 1
}

resolve_absolute_file() {
    _ra_file=$1
    case "$_ra_file" in
        */*) _ra_dir=${_ra_file%/*} ;;
        *) _ra_dir=. ;;
    esac
    if ! _ra_dir=$(CDPATH= cd -- "$_ra_dir" 2>/dev/null && pwd -P); then
        return 1
    fi
    _q_result=${_ra_dir%/}/${_ra_file##*/}
}

cmd_up() {
    _config_inputs=
    _have_config=0
    _no_attach=0
    _dry_run=0
    _haproxy_config=
    _tls_listen_set=0
    TLS_CERT=
    TLS_LISTEN=$MUX_TLS_LISTEN
    LISTEN=$MUX_LISTEN
    JAVA=$MUX_JAVA
    BEDROCK=$MUX_BEDROCK

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --config)
                if [ "$#" -lt 2 ]; then
                    echo "[frpc-shared] ERROR: --config needs one path" >&2
                    exit 2
                fi
                _config_inputs=$_config_inputs$2'
'
                _have_config=1
                shift 2
                ;;
            --listen)
                if [ "$#" -lt 2 ]; then
                    echo "[frpc-shared] ERROR: --listen needs HOST:PORT" >&2
                    exit 2
                fi
                LISTEN=$2
                shift 2
                ;;
            --java)
                if [ "$#" -lt 2 ]; then
                    echo "[frpc-shared] ERROR: --java needs HOST:PORT" >&2
                    exit 2
                fi
                JAVA=$2
                shift 2
                ;;
            --bedrock)
                if [ "$#" -lt 2 ]; then
                    echo "[frpc-shared] ERROR: --bedrock needs HOST:PORT" >&2
                    exit 2
                fi
                BEDROCK=$2
                shift 2
                ;;
            --haproxy-config)
                if [ "$#" -lt 2 ]; then
                    echo "[frpc-shared] ERROR: --haproxy-config needs a file" >&2
                    exit 2
                fi
                _haproxy_config=$2
                shift 2
                ;;
            --tls-cert)
                if [ "$#" -lt 2 ]; then
                    echo "[frpc-shared] ERROR: --tls-cert needs a file" >&2
                    exit 2
                fi
                TLS_CERT=$2
                shift 2
                ;;
            --tls-listen)
                if [ "$#" -lt 2 ]; then
                    echo "[frpc-shared] ERROR: --tls-listen needs HOST:PORT" >&2
                    exit 2
                fi
                TLS_LISTEN=$2
                _tls_listen_set=1
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
                echo "[frpc-shared] ERROR: unknown up option: $1" >&2
                usage >&2
                exit 2
                ;;
        esac
    done

    if [ "$_have_config" -eq 0 ]; then
        echo "[frpc-shared] ERROR: up needs at least one --config <dir|file>" >&2
        exit 2
    fi
    for _endpoint in "$LISTEN" "$JAVA" "$BEDROCK"; do
        if ! is_endpoint "$_endpoint"; then
            echo "[frpc-shared] ERROR: not HOST:PORT (IPv6 needs brackets): $_endpoint" >&2
            exit 2
        fi
    done
    if [ -z "$TLS_CERT" ]; then
        if [ "$_tls_listen_set" -eq 1 ]; then
            echo "[frpc-shared] ERROR: --tls-listen needs --tls-cert" >&2
            exit 2
        fi
    else
        if [ -n "$_haproxy_config" ]; then
            echo "[frpc-shared] ERROR: --tls-cert cannot be combined with --haproxy-config" >&2
            exit 2
        fi
        if ! is_endpoint "$TLS_LISTEN"; then
            echo "[frpc-shared] ERROR: not HOST:PORT (IPv6 needs brackets): $TLS_LISTEN" >&2
            exit 2
        fi
        case "$TLS_LISTEN" in
            "$LISTEN"|"$JAVA"|"$BEDROCK")
                echo "[frpc-shared] ERROR: --tls-listen must differ from --listen/--java/--bedrock: $TLS_LISTEN" >&2
                exit 2
                ;;
        esac
        if [ ! -f "$TLS_CERT" ]; then
            echo "[frpc-shared] ERROR: no such TLS certificate: $TLS_CERT" >&2
            exit 2
        fi
        if [ ! -r "$TLS_CERT" ]; then
            echo "[frpc-shared] ERROR: cannot read TLS certificate: $TLS_CERT" >&2
            exit 2
        fi
        if ! resolve_absolute_file "$TLS_CERT"; then
            echo "[frpc-shared] ERROR: cannot resolve TLS certificate: $TLS_CERT" >&2
            exit 2
        fi
        TLS_CERT=$_q_result
        # HAProxy reads the certificate and its private key from one file.
        if ! grep -q 'BEGIN CERTIFICATE' "$TLS_CERT" 2>/dev/null; then
            echo "[frpc-shared] ERROR: TLS certificate holds no PEM certificate: $TLS_CERT" >&2
            exit 2
        fi
        if ! grep -q 'PRIVATE KEY' "$TLS_CERT" 2>/dev/null; then
            echo "[frpc-shared] ERROR: TLS certificate holds no private key; HAProxy needs one file:" >&2
            echo "[frpc-shared]        cat fullchain.pem privkey.pem > <name>.pem" >&2
            exit 2
        fi
    fi
    case "$MUX_READY_TIMEOUT" in
        ''|*[!0-9]*)
            echo "[frpc-shared] ERROR: MUX_READY_TIMEOUT must be a whole number of seconds" >&2
            exit 2
            ;;
    esac

    # Rebuild the positional list as frpc arguments. Quote_sh cannot be used
    # here: an unquoted expansion of a quoted fragment would pass the literal
    # quotes to frpc instead of removing them.
    set --
    _old_ifs=$IFS
    IFS='
'
    set -f
    for _config_path in $_config_inputs; do
        set -- "$@" --config "$_config_path"
    done
    set +f
    IFS=$_old_ifs

    if [ -n "$_haproxy_config" ]; then
        if [ ! -f "$_haproxy_config" ]; then
            echo "[frpc-shared] ERROR: no such HAProxy config: $_haproxy_config" >&2
            exit 2
        fi
        if ! resolve_absolute_file "$_haproxy_config"; then
            echo "[frpc-shared] ERROR: cannot resolve HAProxy config: $_haproxy_config" >&2
            exit 2
        fi
        _haproxy_config=$_q_result
    else
        _haproxy_config=$DEFAULT_HAPROXY_CONFIG
    fi

    quote_sh "$HAPROXY"
    _haproxy_quoted=$_q_result
    quote_sh "$_haproxy_config"
    _haproxy_config_quoted=$_q_result
    _haproxy_command="$_haproxy_quoted -db -f $_haproxy_config_quoted"
    quote_sh "$ROOT"
    _root_quoted=$_q_result
    _server_command='bash scripts/start.sh'

    if [ "$_dry_run" -eq 1 ]; then
        if [ "$_haproxy_config" = "$DEFAULT_HAPROXY_CONFIG" ]; then
            printf '# frpc-shared: would generate HAProxy config %s\n' "$_haproxy_config"
            print_haproxy_config "$LISTEN" "$JAVA" "$BEDROCK" "$TLS_CERT" "$TLS_LISTEN"
        else
            printf '# frpc-shared: would use HAProxy config %s\n' "$_haproxy_config"
        fi
        FRPC_SESSION=$SESSION "$FRPC_SH" up --defer-server --dry-run "$@"
        printf 'tmux new-window -P -F %s -t %s -n %s -c %s -- cat\n' \
            "'#{window_id}'" "=$SESSION" "$MUX_WINDOW" "$_root_quoted"
        printf 'tmux set-window-option -t <window-id> remain-on-exit on\n'
        printf 'tmux set-window-option -t <window-id> monitor-activity on\n'
        printf 'tmux respawn-window -k -t <window-id> %s\n' "$_haproxy_command"
        printf 'tmux set-window-option -t <server-window-id> @asp-server-deferred 0\n'
        printf 'tmux respawn-window -k -t <server-window-id> %s\n' "$_server_command"
        return 0
    fi

    require_frpc || exit 1
    if ! command -v tmux >/dev/null 2>&1; then
        echo "[frpc-shared] ERROR: tmux not found (install it or add it to PATH)" >&2
        exit 2
    fi
    if ! command -v "$HAPROXY" >/dev/null 2>&1; then
        echo "[frpc-shared] ERROR: haproxy not found (set HAPROXY=/path/to/haproxy)" >&2
        exit 2
    fi
    # Use an absolute path: the tmux server may not share this shell's PATH.
    if ! HAPROXY=$(command -v "$HAPROXY"); then
        echo "[frpc-shared] ERROR: cannot resolve the haproxy binary" >&2
        exit 2
    fi
    quote_sh "$HAPROXY"
    _haproxy_quoted=$_q_result
    _haproxy_command="$_haproxy_quoted -db -f $_haproxy_config_quoted"

    if tmux has-session -t "=$SESSION" 2>/dev/null; then
        printf '[frpc-shared] ERROR: session %s already exists; run down first\n' "$SESSION" >&2
        exit 3
    fi

    if [ -z "$_haproxy_config" ] || [ "$_haproxy_config" = "$DEFAULT_HAPROXY_CONFIG" ]; then
        if ! generate_haproxy_config "$_haproxy_config" "$LISTEN" "$JAVA" "$BEDROCK" \
            "$TLS_CERT" "$TLS_LISTEN"; then
            echo "[frpc-shared] ERROR: cannot write HAProxy config: $_haproxy_config" >&2
            exit 1
        fi
    fi
    if ! haproxy_check "$_haproxy_config"; then
        echo "[frpc-shared] ERROR: HAProxy rejected $_haproxy_config" >&2
        exit 1
    fi

    # 1. Sidecars first. frpc.sh leaves the server window as a placeholder.
    if ! FRPC_SESSION=$SESSION "$FRPC_SH" up --defer-server --no-attach "$@"; then
        echo "[frpc-shared] ERROR: frpc scene failed to start" >&2
        exit 1
    fi

    # 2. The demultiplexer must be listening before the Java server starts.
    if ! spawn_window "=$SESSION" "$MUX_WINDOW" "$_haproxy_command"; then
        echo "[frpc-shared] ERROR: could not create the $MUX_WINDOW window" >&2
        FRPC_SESSION=$SESSION "$FRPC_SH" down >/dev/null 2>&1 || true
        exit 1
    fi
    if ! wait_mux_ready; then
        FRPC_SESSION=$SESSION "$FRPC_SH" down >/dev/null 2>&1 || true
        exit 1
    fi

    # 3. Only now start the server, the last prerequisite.
    if ! tmux set-window-option -t "=$SESSION:$SERVER_WINDOW" @asp-server-deferred 0; then
        echo "[frpc-shared] ERROR: could not clear the deferred server state" >&2
        exit 1
    fi
    if ! tmux respawn-window -k -t "=$SESSION:$SERVER_WINDOW" "$_server_command"; then
        echo "[frpc-shared] ERROR: could not start the server window" >&2
        exit 1
    fi

    if [ "$_no_attach" -eq 1 ]; then
        printf '[frpc-shared] started session %s without attaching\n' "$SESSION"
        return 0
    fi
    if [ ! -t 0 ]; then
        printf '[frpc-shared] started session %s; stdin is not a terminal\n' "$SESSION"
        return 0
    fi
    FRPC_SESSION=$SESSION "$FRPC_SH" attach
}

cmd_down() {
    if [ "$#" -ne 0 ]; then
        usage >&2
        exit 2
    fi
    require_frpc || exit 1
    FRPC_SESSION=$SESSION "$FRPC_SH" down
}

cmd_status() {
    if [ "$#" -ne 0 ]; then
        usage >&2
        exit 2
    fi
    require_frpc || exit 1
    FRPC_SESSION=$SESSION "$FRPC_SH" status
}

cmd_attach() {
    if [ "$#" -ne 0 ]; then
        usage >&2
        exit 2
    fi
    require_frpc || exit 1
    FRPC_SESSION=$SESSION "$FRPC_SH" attach
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
