#!/bin/sh
# ============================================================
#  ASP frpc shared-TCP scene (POSIX sh, Linux only; not core)
#
#  Runs the server, an HAProxy L4 demultiplexer and one frpc
#  process per configuration (or scene section) in one tmux
#  session. Java Minecraft TCP and Bedrock NetherNet built-in
#  signalling share one public TCP port; the Bedrock WebRTC media
#  plane still needs its own UDP tunnel, which the official frpc
#  client is the verified carrier for.
#
#  Start order: frpc sidecars first, HAProxy second (it must bind the
#  listen port), the Java server last. MUX_READY_TIMEOUT (default 10)
#  bounds the HAProxy wait.
#
#  Usage:
#    scripts/scenes/frpc-shared-tcp.sh up --config <dir|file> \
#        [--config <dir|file>]... [--listen HOST:PORT] \
#        [--java HOST:PORT] [--bedrock HOST:PORT] \
#        [--tls-cert FILE]... [--tls-listen HOST:PORT] [--strict-sni] \
#        [--proxy-protocol] [--packs HOST:PORT] [--haproxy-config FILE] \
#        [--no-attach] [--dry-run]
#    scripts/scenes/frpc-shared-tcp.sh up --scene <file> \
#        [--listen HOST:PORT] [--java HOST:PORT] [--bedrock HOST:PORT] \
#        [--tls-cert FILE]... [--tls-listen HOST:PORT] [--strict-sni] \
#        [--proxy-protocol] [--packs HOST:PORT] [--haproxy-config FILE] \
#        [--no-attach] [--dry-run]
#    scripts/scenes/frpc-shared-tcp.sh reload
#    scripts/scenes/frpc-shared-tcp.sh down
#    scripts/scenes/frpc-shared-tcp.sh status
#    scripts/scenes/frpc-shared-tcp.sh attach
#    scripts/scenes/frpc-shared-tcp.sh help
#
#  --scene hands the sidecar set to frpc.sh as a scene manifest instead of a
#  --config list, and is mutually exclusive with --config. The manifest is
#  where several TCP entries point at this one mux and where the UDP media
#  tunnel names the official frpc binary; the server window is still deferred
#  here and started by this script, last, so a manifest that says
#  server = false still composes with it.
#
#  Defaults:
#    --listen     127.0.0.1:25566
#    --java       127.0.0.1:25565
#    --bedrock    127.0.0.1:19132
#    --tls-listen 127.0.0.1:25567 (only with --tls-cert)
#    LAN Java     0.0.0.0:25564  (automatic with --proxy-protocol)
#
#  Without --haproxy-config the scene writes a generated HAProxy
#  config to .tmp/frpc-shared-tcp/haproxy.cfg (gitignored). The frpc
#  TCP proxy must point localPort at the mux listen port.
#
#  The demux sends a TLS ClientHello or an HTTP method prefix to
#  Geyser built-in signalling and everything else to Java. By default
#  it does not parse PROXY protocol: leave frpc's
#  transport.proxyProtocolVersion unset.
#
#  --proxy-protocol makes the demux speak PROXY protocol v2 instead:
#  the shared port then only accepts a connection whose first bytes are
#  a v2 header, and HAProxy hands the Java backend a header of its own,
#  so Paper sees each player's real public address rather than
#  127.0.0.1. Everything that reaches the port has to send the header,
#  the frpc TCP proxy included (transport.proxyProtocolVersion = "v2"),
#  and the backend has to be told to expect it
#  (Paper proxies.proxy-protocol; Geyser advanced.java.use-haproxy-protocol).
#  scripts/probe_public_entry.py --proxy-protocol speaks it for the
#  local-mux checks. Nothing else about the configuration moves.
#
#  --proxy-protocol also adds a plain frontend for LAN Java clients. It
#  accepts the client's ordinary Minecraft connection and sends it to
#  the same Java backend, which carries the send-proxy-v2 directive, so
#  Paper still receives a header and keeps the real LAN address.
#  MUX_LAN_JAVA overrides its bind; the default is 0.0.0.0:25564, so an
#  operator who does not want that exposure should choose a specific LAN
#  address or supply a hand-written HAProxy configuration.
#
#  --packs HOST:PORT serves plaintext resource-pack downloads from the
#  same shared port: a connection whose first bytes are "GET <prefix>"
#  goes to that backend instead of Geyser, so
#  http://<public-ip>:<port>/packs/<file> works without TLS or a name.
#  The match reads offset 0 of a fresh connection, so a request that
#  reuses a kept-alive connection, and an h2c preface, do not match and
#  fall through to Geyser. MUX_PACKS_PREFIX sets the prefix (default
#  /packs/; it must start and end with "/"). The TLS branches, the
#  plaintext Geyser branch and Java are untouched. The backend is
#  somebody else's process: this scene forwards to it and reports
#  whether it is reachable, nothing more.
#
#  --serve-packs is the same route with the backend declared as this
#  entry's own: it starts scripts/serve-packs.sh in a 'packs' window,
#  'down' stops it with the session, and 'status' says whether that
#  window is up. The endpoint comes from --packs-port (default 8000),
#  so the ACL and the pack server take their port and prefix from this
#  command line and nowhere else - not from an environment variable
#  each, which is how they could disagree while both looked correct. It
#  cannot be combined with --packs: one route, one owner.
#
#  With --tls-cert the scene terminates TLS itself: the shared port
#  keeps the ClientHello on a second loopback bind (--tls-listen)
#  where HAProxy decrypts it and hands the plain bytes to Geyser. The
#  certificate is a combined PEM (chain plus private key) that lives
#  outside the repository; Geyser keeps its plain HTTP listener.
#
#  --tls-cert may be given more than once: every file becomes one `crt`
#  on that bind and HAProxy picks between them by SNI, which is what
#  serving several names - several accounts, each with its own
#  provider-issued certificate - on one port needs. A name no
#  certificate covers falls back to the first one, unless
#  --strict-sni makes such a handshake fail. Java carries no SNI, so
#  none of this changes how Java traffic is routed.
#
#  Every certificate is also inspected at 'up' and through 'status':
#  subject, SANs and notAfter. One that expires inside
#  MUX_CERT_WARN_DAYS (default 7) is reported as a warning, not a
#  refusal to start. Downloading or renewing it is outside this scene;
#  that belongs to the provider/token pipeline and its schedule.
#
#  The mux runs in HAProxy master-worker mode with a pidfile
#  (.tmp/frpc-shared-tcp/haproxy.pid, MUX_PIDFILE overrides it), so
#  'reload' can swap that certificate under a running server: it sends
#  SIGUSR2 to the master, which re-reads the configuration and hands
#  the listening socket to a new worker. Players on the port keep
#  playing. The old command, respawning the mux window, drops them.
#  That master is also why 'down' does not rely on the session: it
#  ignores the SIGHUP a teardown sends it, so 'down' stops it by its
#  pidfile (SIGTERM, then SIGKILL after MUX_STOP_TIMEOUT seconds), and
#  'up' refuses to start a second master over a live one or over an
#  occupied listen port. 'status' reads the same pidfile, which is what
#  makes a master left behind visible instead of orphaned.
#
#  'status' also prints the TLS binds of the configuration the mux reads
#  (MUX_HAPROXY_CONFIG, default the generated config), because that line
#  is where "which certificate is being served" is actually answered: a
#  reload aimed at a file the configuration does not mention changes
#  nothing, and says nothing. It then reports the certificate inventory
#  'up' wrote, so a stale or nearly expired PEM is visible without
#  re-parsing HAProxy's quoting.
#
#  The session, and the UTF-8 locale its panes get, belong to frpc.sh:
#  this script creates no session of its own - it adds a mux window to
#  the one frpc.sh made and starts the server window last.
#
#  Requires: POSIX sh, tmux, frpc, haproxy.
# ============================================================
set -eu

SERVER_WINDOW=server
MUX_WINDOW=mux
PACKS_WINDOW=packs
SESSION=asp-frpc-shared
HAPROXY=${HAPROXY:-haproxy}
MUX_READY_TIMEOUT=${MUX_READY_TIMEOUT:-10}
MUX_LISTEN=${MUX_LISTEN:-127.0.0.1:25566}
MUX_JAVA=${MUX_JAVA:-127.0.0.1:25565}
MUX_BEDROCK=${MUX_BEDROCK:-127.0.0.1:19132}
MUX_TLS_LISTEN=${MUX_TLS_LISTEN:-127.0.0.1:25567}
MUX_LAN_JAVA=${MUX_LAN_JAVA:-0.0.0.0:25564}
MUX_STOP_TIMEOUT=${MUX_STOP_TIMEOUT:-10}
# The pack route's prefix is not an operator input: it is the name the
# served directory has in the URL. Deriving it here keeps the ACL and the
# pack server on one value; MUX_PACKS_PREFIX stays as the override for a
# foreign backend whose URL shape this repository does not own.
PACKS_PREFIX=${MUX_PACKS_PREFIX:-/packs/}
MUX_PACKS_PORT=${MUX_PACKS_PORT:-8000}
# The directory the pack server serves. Its basename is the URL path, so it
# lives here, next to the prefix it produces, rather than being repeated as
# a literal in the window command.
PACKS_DIR=${MUX_PACKS_DIR:-server/packs}

# Captured before the C locale below, which belongs to this script alone.
_caller_locale=${LC_ALL-}

LC_ALL=C
export LC_ALL

# Every tmux call this script makes runs in a UTF-8 locale, and so does the
# mux window it adds: the frpc scene below owns the session environment, and
# this keeps the calls made here consistent with it. The caller's UTF-8
# locale is preferred, then C.UTF-8, which glibc carries itself; the same
# FRPC_PANEL_LOCALE override applies.
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
# The pack directory is named the way the repository names it ("server/packs")
# and resolved against the repository root, not the operator's cwd, because
# the window that serves it starts in that root.
case "$PACKS_DIR" in
    /*)
        ;;
    *)
        PACKS_DIR=$ROOT/$PACKS_DIR
        ;;
esac
DEFAULT_HAPROXY_CONFIG=$ROOT/.tmp/frpc-shared-tcp/haproxy.cfg
DEFAULT_HAPROXY_PID=$ROOT/.tmp/frpc-shared-tcp/haproxy.pid
DEFAULT_CERT_STATE=$ROOT/.tmp/frpc-shared-tcp/certs
DEFAULT_PACKS_STATE=$ROOT/.tmp/frpc-shared-tcp/packs
# What 'status' reads. 'up --haproxy-config' says it for one run, so the
# variable is how a status call sees the same file.
MUX_HAPROXY_CONFIG=${MUX_HAPROXY_CONFIG:-$DEFAULT_HAPROXY_CONFIG}
# The master holds the port, so its pidfile is what 'reload' signals.
MUX_PIDFILE=${MUX_PIDFILE:-$DEFAULT_HAPROXY_PID}
# The certificate inventory 'up' writes and 'status' reads. It is evidence
# of what this scene validated, not another source of HAProxy configuration.
MUX_CERT_STATE=${MUX_CERT_STATE:-$DEFAULT_CERT_STATE}
# What 'status' needs to describe the pack route: which mode it was started
# in, and the two values the ACL was written from. It is evidence, not a
# second source of configuration - nothing reads it to build the mux.
MUX_PACKS_STATE=${MUX_PACKS_STATE:-$DEFAULT_PACKS_STATE}
MUX_CERT_WARN_DAYS=${MUX_CERT_WARN_DAYS:-7}
# The command that sends the reload signal; a variable so a test can stand in
# for it, the same way HAPROXY can point at another binary.
MUX_SIGNAL=${MUX_SIGNAL:-kill}
# A relative pidfile means "relative to where this was run", not to the
# repository: the tmux windows start in the repository root, the operator
# does not.
case "$MUX_PIDFILE" in
    /*)
        ;;
    *)
        if ! _scene_cwd=$(CDPATH= cd -- . 2>/dev/null && pwd -P); then
            echo "[frpc-shared] ERROR: cannot resolve the current directory" >&2
            exit 1
        fi
        MUX_PIDFILE=$_scene_cwd/$MUX_PIDFILE
        ;;
esac
case "$MUX_CERT_STATE" in
    /*)
        ;;
    *)
        if ! _cert_cwd=$(CDPATH= cd -- . 2>/dev/null && pwd -P); then
            echo "[frpc-shared] ERROR: cannot resolve the current directory" >&2
            exit 1
        fi
        MUX_CERT_STATE=$_cert_cwd/$MUX_CERT_STATE
        ;;
esac
case "$MUX_PACKS_STATE" in
    /*)
        ;;
    *)
        if ! _packs_cwd=$(CDPATH= cd -- . 2>/dev/null && pwd -P); then
            echo "[frpc-shared] ERROR: cannot resolve the current directory" >&2
            exit 1
        fi
        MUX_PACKS_STATE=$_packs_cwd/$MUX_PACKS_STATE
        ;;
esac

usage() {
    printf '%s\n' \
        'Usage:' \
        '  scripts/scenes/frpc-shared-tcp.sh up --config <dir|file> [--config <dir|file>]... [--listen HOST:PORT] [--java HOST:PORT] [--bedrock HOST:PORT] [--tls-cert FILE]... [--tls-listen HOST:PORT] [--strict-sni] [--proxy-protocol] [--packs HOST:PORT | --serve-packs [--packs-port PORT]] [--haproxy-config FILE] [--no-attach] [--dry-run]' \
        '  scripts/scenes/frpc-shared-tcp.sh up --scene <file> [--listen HOST:PORT] [--java HOST:PORT] [--bedrock HOST:PORT] [--tls-cert FILE]... [--tls-listen HOST:PORT] [--strict-sni] [--proxy-protocol] [--packs HOST:PORT | --serve-packs [--packs-port PORT]] [--haproxy-config FILE] [--no-attach] [--dry-run]' \
        '  scripts/scenes/frpc-shared-tcp.sh reload' \
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

# A prefix that can go into a payload match as literal text: one leading
# and one trailing slash, no character HAProxy would split or quote, and
# no empty or parent segment. "/" itself is refused because it would
# swallow every plaintext HTTP request instead of only pack downloads.
is_packs_prefix() {
    _pp_prefix=$1
    case "$_pp_prefix" in
        /|'')
            return 1
            ;;
        /*/)
            ;;
        *)
            return 1
            ;;
    esac
    case "$_pp_prefix" in
        *[!A-Za-z0-9._~/-]*|*//*|*..*)
            return 1
            ;;
    esac
    return 0
}

# Print the generated HAProxy config for one listen/java/bedrock set.
# A non-empty $4 turns on TLS termination: the ClientHello is handed to a
# second bind ($5) that HAProxy decrypts with the PEMs in $4 (one per line,
# one `crt` each, so SNI chooses between several names), so Geyser receives
# plain HTTP and needs no certificate of its own. $6 is 1 to add `strict-sni`,
# which refuses a ClientHello no certificate covers. $7 is 1 to speak PROXY
# protocol v2 on the shared port: `accept-proxy` on its bind and
# `send-proxy-v2` to the Java backend, so Paper sees the real client address
# instead of 127.0.0.1. $8, when non-empty, is a plain LAN Java bind that
# reaches that same Java backend, which supplies the header for it. $9,
# when non-empty, is a resource-pack server endpoint and $10 the path
# prefix to accept for it: one payload ACL on the shared port routes those
# plaintext requests there, and nothing else in the file moves.
print_haproxy_config() {
    _ph_listen=$1
    _ph_java=$2
    _ph_bedrock=$3
    _ph_tls_certs=$4
    _ph_tls_listen=$5
    _ph_strict_sni=$6
    _ph_lan_java=$8
    _ph_packs_endpoint=${9:-}
    _ph_packs_prefix=${10:-}
    if [ -n "$_ph_packs_endpoint" ]; then
        _ph_packs_match="GET $_ph_packs_prefix"
        _ph_packs_len=${#_ph_packs_match}
    fi
    _ph_accept_proxy=
    _ph_send_proxy=
    if [ "${7:-0}" -eq 1 ]; then
        _ph_accept_proxy=' accept-proxy'
        _ph_send_proxy=' send-proxy-v2'
    fi
    _ph_crt_args=
    _ph_cert_names=0
    if [ -n "$_ph_tls_certs" ]; then
        _ph_old_ifs=$IFS
        IFS='
'
        set -f
        for _ph_cert in $_ph_tls_certs; do
            haproxy_quote "$_ph_cert"
            _ph_crt_args="$_ph_crt_args crt $_q_result"
            _ph_cert_names=$((_ph_cert_names + 1))
        done
        set +f
        IFS=$_ph_old_ifs
    fi
    _ph_sni_arg=
    if [ "$_ph_strict_sni" -eq 1 ]; then
        _ph_sni_arg=' strict-sni'
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
    bind $_ph_listen$_ph_accept_proxy
    acl is_tls req.ssl_hello_type 1
    acl is_http payload(0,4) -m beg "GET " "POST" "HEAD" "PUT " "OPTI" "PATC" "DELE" "CONN" "TRAC" "PRI "
    acl is_java payload(0,1) -m bin fe
    acl is_java payload(1,1) -m bin 00
EOF
    if [ -n "$_ph_packs_endpoint" ]; then
        cat <<EOF
    acl is_packs payload(0,$_ph_packs_len) -m beg "$_ph_packs_match"
EOF
    fi
    cat <<EOF
    tcp-request inspect-delay 3s
    tcp-request content accept if is_tls or is_http or is_java
EOF
    if [ -n "$_ph_packs_endpoint" ]; then
        cat <<EOF
    use_backend packs if is_packs
EOF
    fi
    if [ -n "$_ph_tls_certs" ]; then
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
    server paper $_ph_java$_ph_send_proxy
EOF
    if [ -n "$_ph_lan_java" ]; then
        cat <<EOF

# LAN Java clients use an ordinary connection; this frontend adds the
# PROXY v2 header that Paper expects through the shared java backend.
frontend lan_java
    bind $_ph_lan_java
    default_backend java
EOF
    fi
    if [ -n "$_ph_tls_certs" ]; then
        cat <<EOF

# TLS is terminated here, not in Geyser: the decrypted stream reaches the
# same signalling backend byte for byte.
backend geyser_tls
    server termination $_ph_tls_listen

frontend geyser_tls_termination
EOF
        if [ "$_ph_cert_names" -gt 1 ]; then
            cat <<EOF
    # $_ph_cert_names names on one bind: HAProxy chooses the certificate by
    # SNI. A ClientHello no certificate covers is served the first one,
    # unless strict-sni is set.
EOF
        fi
        cat <<EOF
    bind $_ph_tls_listen ssl$_ph_crt_args$_ph_sni_arg
    default_backend geyser_signaling
EOF
    fi
    if [ -n "$_ph_packs_endpoint" ]; then
        cat <<EOF

backend packs
    server packs $_ph_packs_endpoint
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
    if ! print_haproxy_config "$2" "$3" "$4" "$5" "$6" "${7:-0}" "${8:-0}" "${9:-}" \
        "${10:-}" "${11:-}" > "$_gh_tmp"; then
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

# Return 0 when endpoint $1 is accepting TCP, 1 when it is not, 2 when no
# listening-socket tool is available (caller may then trust the window).
endpoint_listen_check() {
    _el_port=${1##*:}
    for _ml_tool in 'ss -ltn' 'netstat -ltn'; do
        _ml_bin=${_ml_tool%% *}
        command -v "$_ml_bin" >/dev/null 2>&1 || continue
        if _ml_out=$($_ml_tool 2>/dev/null); then
            if printf '%s\n' "$_ml_out" | awk '{print $4}' | grep -F ":$_el_port" >/dev/null 2>&1; then
                return 0
            fi
            return 1
        fi
    done
    return 2
}

mux_listen_check() {
    endpoint_listen_check "$LISTEN"
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

# The name a process reports for itself: the executable's basename, cut by
# the kernel to 15 characters. It is what makes a pidfile entry checkable
# without trusting the file itself.
process_name() {
    if [ -r "/proc/$1/comm" ]; then
        _pname=$(cat "/proc/$1/comm" 2>/dev/null || true)
    else
        _pname=$(ps -o comm= -p "$1" 2>/dev/null || true)
    fi
    printf '%s' "$_pname"
}

kernel_comm() {
    # printf cuts to 15 bytes, which is what the kernel keeps in comm.
    printf '%.15s' "$1"
}

# Read the pidfile and decide what it names. Sets MUX_STATUS_STATE to one
# of none, invalid, stale, other or live, plus MUX_STATUS_PID and
# MUX_STATUS_NAME (empty when there is no process to read). It returns the
# verdict in variables rather than on stdout because a command
# substitution would run this in a subshell and lose them, and a caller
# that only wants the state would then have to re-read the pidfile.
mux_pid_status() {
    MUX_STATUS_STATE=none
    MUX_STATUS_PID=
    MUX_STATUS_NAME=
    if [ ! -f "$MUX_PIDFILE" ]; then
        return 0
    fi
    if [ ! -r "$MUX_PIDFILE" ]; then
        MUX_STATUS_STATE=invalid
        return 0
    fi
    _ms_pid=$(head -n 1 "$MUX_PIDFILE" 2>/dev/null | tr -d '[:space:]' || true)
    case "$_ms_pid" in
        ''|*[!0-9]*)
            MUX_STATUS_STATE=invalid
            return 0
            ;;
    esac
    MUX_STATUS_PID=$_ms_pid
    MUX_STATUS_NAME=$(process_name "$_ms_pid")
    if [ -z "$MUX_STATUS_NAME" ]; then
        # Gone, or owned by someone this user cannot read: either way it is
        # not something this scene may signal.
        MUX_STATUS_STATE=stale
        return 0
    fi
    if [ "$(kernel_comm "$MUX_STATUS_NAME")" = "$(kernel_comm "${HAPROXY##*/}")" ]; then
        MUX_STATUS_STATE=live
    else
        MUX_STATUS_STATE=other
    fi
    return 0
}

# Say what the pidfile names. 'status' reports the mux from here, not from
# the session: a master that outlived its session is exactly the case an
# operator needs to see, and it has no window left to appear in.
report_mux_status() {
    mux_pid_status
    case "$MUX_STATUS_STATE" in
        live)
            printf '[frpc-shared] mux: %s %s is up (pidfile %s)\n' \
                "${HAPROXY##*/}" "$MUX_STATUS_PID" "$MUX_PIDFILE"
            ;;
        other)
            printf '[frpc-shared] mux: WARNING pidfile %s names pid %s (%s), which is not %s\n' \
                "$MUX_PIDFILE" "$MUX_STATUS_PID" "$MUX_STATUS_NAME" "${HAPROXY##*/}"
            ;;
        stale)
            printf '[frpc-shared] mux: WARNING pid %s is gone; the pidfile is stale\n' \
                "$MUX_STATUS_PID"
            ;;
        invalid)
            printf '[frpc-shared] mux: WARNING pidfile %s holds no process id\n' \
                "$MUX_PIDFILE"
            ;;
        *)
            printf '[frpc-shared] mux: not running (no pidfile at %s)\n' \
                "$MUX_PIDFILE"
            ;;
    esac
}

# Print one certificate's identity and validity. This is observation, not
# lifecycle management: renewal and download stay outside this scene, and a
# certificate openssl cannot parse is reported rather than rejected because
# HAProxy is the component that decides whether it can load the file.
report_certificate() {
    _rc_cert=$1
    _rc_line="[frpc-shared] tls: $_rc_cert"
    _rc_warn=

    if ! command -v openssl >/dev/null 2>&1; then
        printf '%s: expiry unknown (openssl not found)\n' "$_rc_line"
        return 0
    fi

    _rc_subject=$(openssl x509 -in "$_rc_cert" -noout -subject -nameopt RFC2253 2>/dev/null || true)
    _rc_subject=${_rc_subject#subject=}
    if [ -n "$_rc_subject" ]; then
        _rc_line="$_rc_line: $_rc_subject"
    fi
    _rc_san=$(openssl x509 -in "$_rc_cert" -noout -ext subjectAltName 2>/dev/null || true)
    if [ -n "$_rc_san" ]; then
        _rc_san=$(printf '%s\n' "$_rc_san" | sed -n '2,$p' | tr -d '[:space:]')
        if [ -n "$_rc_san" ]; then
            _rc_line="$_rc_line; $_rc_san"
        fi
    fi

    if ! _rc_end=$(openssl x509 -in "$_rc_cert" -noout -enddate 2>/dev/null); then
        printf '%s: validity unknown (openssl cannot parse it)\n' "$_rc_line"
        return 0
    fi
    _rc_end=${_rc_end#notAfter=}
    _rc_now=$(date +%s 2>/dev/null || true)
    _rc_end_epoch=$(date -d "$_rc_end" +%s 2>/dev/null || true)
    _rc_line="$_rc_line; expires $_rc_end"
    if [ -n "$_rc_now" ] && [ -n "$_rc_end_epoch" ] && [ "$_rc_end_epoch" -ge "$_rc_now" ]; then
        _rc_days=$(((_rc_end_epoch - _rc_now) / 86400))
        _rc_line="$_rc_line ($_rc_days days left)"
    fi

    if ! openssl x509 -in "$_rc_cert" -noout -checkend 0 >/dev/null 2>&1; then
        _rc_warn="WARNING certificate has expired"
    else
        _rc_warn_seconds=$((MUX_CERT_WARN_DAYS * 86400))
        if ! openssl x509 -in "$_rc_cert" -noout -checkend "$_rc_warn_seconds" >/dev/null 2>&1; then
            _rc_warn="WARNING certificate expires within $MUX_CERT_WARN_DAYS days"
        fi
    fi

    _rc_start=$(openssl x509 -in "$_rc_cert" -noout -startdate 2>/dev/null || true)
    _rc_start=${_rc_start#notBefore=}
    if [ -n "$_rc_now" ] && [ -n "$_rc_start" ]; then
        _rc_start_epoch=$(date -d "$_rc_start" +%s 2>/dev/null || true)
        if [ -n "$_rc_start_epoch" ] && [ "$_rc_start_epoch" -gt "$_rc_now" ]; then
            _rc_warn="${_rc_warn:+$_rc_warn; }WARNING certificate is not valid until $_rc_start"
        fi
    fi

    if [ -n "$_rc_warn" ]; then
        printf '%s; %s\n' "$_rc_line" "$_rc_warn"
    else
        printf '%s\n' "$_rc_line"
    fi
}

# Record the exact certificate files this invocation validated. 'status'
# reads it to keep expiry visible without re-parsing HAProxy configuration.
write_cert_inventory() {
    if [ -z "$TLS_CERTS" ]; then
        rm -f "$MUX_CERT_STATE"
        return 0
    fi
    case "$MUX_CERT_STATE" in
        */*)
            _wci_dir=${MUX_CERT_STATE%/*}
            if [ -z "$_wci_dir" ]; then
                _wci_dir=/
            fi
            ;;
        *)
            _wci_dir=.
            ;;
    esac
    if ! mkdir -p "$_wci_dir"; then
        return 1
    fi
    _wci_tmp=${MUX_CERT_STATE}.tmp.$$
    if ! printf '%s' "$TLS_CERTS" > "$_wci_tmp"; then
        rm -f "$_wci_tmp"
        return 1
    fi
    if ! mv -f "$_wci_tmp" "$MUX_CERT_STATE"; then
        rm -f "$_wci_tmp"
        return 1
    fi
}

report_cert_inventory() {
    if [ ! -f "$MUX_CERT_STATE" ]; then
        return 0
    fi
    if [ ! -r "$MUX_CERT_STATE" ]; then
        printf '[frpc-shared] tls: WARNING cannot read certificate inventory %s\n' \
            "$MUX_CERT_STATE"
        return 0
    fi
    while IFS= read -r _rci_cert; do
        _rci_cert=$(printf '%s' "$_rci_cert" | tr -d '\r')
        if [ -n "$_rci_cert" ]; then
            report_certificate "$_rci_cert"
        fi
    done < "$MUX_CERT_STATE"
}

# Record how the pack route was started: one line, "owned|foreign endpoint
# prefix". 'status' reads it to say which mode is live and, for an owned
# backend, which window to look at; nothing builds configuration from it.
write_packs_state() {
    if [ -z "$PACKS_ENDPOINT" ]; then
        rm -f "$MUX_PACKS_STATE"
        return 0
    fi
    case "$MUX_PACKS_STATE" in
        */*)
            _wps_dir=${MUX_PACKS_STATE%/*}
            if [ -z "$_wps_dir" ]; then
                _wps_dir=/
            fi
            ;;
        *)
            _wps_dir=.
            ;;
    esac
    if ! mkdir -p "$_wps_dir"; then
        return 1
    fi
    if [ "$PACKS_OWNED" -eq 1 ]; then
        _wps_mode=owned
    else
        _wps_mode=foreign
    fi
    _wps_tmp=${MUX_PACKS_STATE}.tmp.$$
    if ! printf '%s %s %s\n' "$_wps_mode" "$PACKS_ENDPOINT" "$PACKS_PREFIX" > "$_wps_tmp"; then
        rm -f "$_wps_tmp"
        return 1
    fi
    if ! mv -f "$_wps_tmp" "$MUX_PACKS_STATE"; then
        rm -f "$_wps_tmp"
        return 1
    fi
}

# Say what the pack route is: who owns the backend, where it is, and whether
# that is true right now. For an owned backend the window is the evidence -
# it is the process this entry started; for a foreign one the listening
# socket is all there is to see, since the process is not this entry's.
report_packs_status() {
    if [ ! -f "$MUX_PACKS_STATE" ]; then
        # No state means 'up' with this version did not declare a route. The
        # mux configuration can still have one, so report that rather than
        # claiming there is none.
        if [ -f "$MUX_HAPROXY_CONFIG" ]; then
            _rp_config_line=$(grep -F '    server packs ' "$MUX_HAPROXY_CONFIG" 2>/dev/null || true)
        else
            _rp_config_line=
        fi
        if [ -n "$_rp_config_line" ]; then
            printf '[frpc-shared] packs: %s (no state at %s; owner unknown)\n' \
                "${_rp_config_line#"${_rp_config_line%%[![:space:]]*}"}" "$MUX_PACKS_STATE"
        else
            printf '[frpc-shared] packs: no route (no state at %s)\n' "$MUX_PACKS_STATE"
        fi
        return 0
    fi
    if ! _rp_line=$(head -n 1 "$MUX_PACKS_STATE" 2>/dev/null); then
        printf '[frpc-shared] packs: WARNING cannot read %s\n' "$MUX_PACKS_STATE"
        return 0
    fi
    _rp_mode=${_rp_line%% *}
    _rp_rest=${_rp_line#* }
    _rp_endpoint=${_rp_rest%% *}
    _rp_prefix=${_rp_rest#* }
    if [ "$_rp_mode" = owned ]; then
        if [ -z "$TMUX_BIN" ]; then
            printf '[frpc-shared] packs: owned %s under %s, window state unknown (tmux not found)\n' \
                "$_rp_endpoint" "$_rp_prefix"
            return 0
        fi
        _rp_dead=1
        if _rp_dead=$(tmux list-panes -t "=$SESSION:$PACKS_WINDOW" -F '#{pane_dead}' 2>/dev/null); then
            :
        else
            _rp_dead=1
        fi
        if [ "$_rp_dead" = 0 ]; then
            printf '[frpc-shared] packs: owned %s under %s, window %s up\n' \
                "$_rp_endpoint" "$_rp_prefix" "$PACKS_WINDOW"
        else
            printf '[frpc-shared] packs: owned %s under %s, window %s DEAD\n' \
                "$_rp_endpoint" "$_rp_prefix" "$PACKS_WINDOW"
        fi
        return 0
    fi
    _rp_rc=0
    endpoint_listen_check "$_rp_endpoint" || _rp_rc=$?
    case "$_rp_rc" in
        0)
            printf '[frpc-shared] packs: foreign %s under %s, reachable\n' \
                "$_rp_endpoint" "$_rp_prefix"
            ;;
        2)
            printf '[frpc-shared] packs: foreign %s under %s, reachability unknown (no ss/netstat)\n' \
                "$_rp_endpoint" "$_rp_prefix"
            ;;
        *)
            printf '[frpc-shared] packs: foreign %s under %s, UNREACHABLE\n' \
                "$_rp_endpoint" "$_rp_prefix"
            ;;
    esac
}

# Print the TLS binds of the configuration the mux reads. That line is where
# "which certificate is being served" is actually answered, and its silence
# is the failure mode worth breaking: reloading after writing a PEM the
# configuration does not mention re-reads the old one and reports success.
report_mux_tls() {
    if [ ! -f "$MUX_HAPROXY_CONFIG" ]; then
        printf '[frpc-shared] tls: no configuration at %s\n' "$MUX_HAPROXY_CONFIG"
        return 0
    fi
    if [ ! -r "$MUX_HAPROXY_CONFIG" ]; then
        printf '[frpc-shared] tls: WARNING cannot read %s\n' "$MUX_HAPROXY_CONFIG"
        return 0
    fi
    _rt_found=0
    _rt_binds=$(grep -F 'ssl crt ' "$MUX_HAPROXY_CONFIG" 2>/dev/null || true)
    while IFS= read -r _rt_line; do
        if [ -z "$_rt_line" ]; then
            continue
        fi
        _rt_found=1
        # Printed as the configuration writes it: a status line is not the
        # place to re-parse HAProxy's own quoting.
        printf '[frpc-shared] tls: %s\n' "${_rt_line#"${_rt_line%%[![:space:]]*}"}"
    done <<EOF
$_rt_binds
EOF
    if [ "$_rt_found" -eq 0 ]; then
        printf '[frpc-shared] tls: %s binds no certificate; Geyser terminates TLS itself\n' \
            "$MUX_HAPROXY_CONFIG"
    elif [ ! -f "$MUX_CERT_STATE" ]; then
        printf '[frpc-shared] tls: certificate expiry is not tracked (no --tls-cert inventory at %s)\n' \
            "$MUX_CERT_STATE"
    fi
}

# Stop the master the pidfile names. Tearing down the tmux session is not
# enough: the master ignores the SIGHUP that sends, which is what would
# otherwise leave it on the listen port with no window left to show it.
stop_mux() {
    mux_pid_status
    case "$MUX_STATUS_STATE" in
        none)
            return 0
            ;;
        invalid)
            printf '[frpc-shared] WARNING: pidfile %s holds no process id; nothing to stop\n' \
                "$MUX_PIDFILE" >&2
            return 0
            ;;
        stale)
            printf '[frpc-shared] mux: pid %s is gone; nothing to stop\n' \
                "$MUX_STATUS_PID"
            return 0
            ;;
        other)
            printf '[frpc-shared] ERROR: pidfile %s names pid %s (%s), which is not %s: refusing to signal it\n' \
                "$MUX_PIDFILE" "$MUX_STATUS_PID" "$MUX_STATUS_NAME" "${HAPROXY##*/}" >&2
            return 1
            ;;
    esac
    _sm_want=$(kernel_comm "${HAPROXY##*/}")
    if ! "$MUX_SIGNAL" -TERM "$MUX_STATUS_PID"; then
        printf '[frpc-shared] ERROR: cannot send SIGTERM to %s\n' "$MUX_STATUS_PID" >&2
        return 1
    fi
    _sm_elapsed=0
    while [ "$_sm_elapsed" -lt "$MUX_STOP_TIMEOUT" ]; do
        _sm_name=$(process_name "$MUX_STATUS_PID")
        if [ -z "$_sm_name" ]; then
            printf '[frpc-shared] mux: %s %s stopped\n' "${HAPROXY##*/}" "$MUX_STATUS_PID"
            return 0
        fi
        if [ "$(kernel_comm "$_sm_name")" != "$_sm_want" ]; then
            # The pid was recycled while the master was going down, so the
            # process it names now is somebody else's.
            printf '[frpc-shared] mux: pid %s is %s now, so the master is gone\n' \
                "$MUX_STATUS_PID" "'$_sm_name'"
            return 0
        fi
        sleep 1
        _sm_elapsed=$((_sm_elapsed + 1))
    done
    # Same check once more before escalating: SIGKILL is not something to
    # aim at a pid that stopped being the master a second ago.
    _sm_name=$(process_name "$MUX_STATUS_PID")
    if [ -z "$_sm_name" ]; then
        printf '[frpc-shared] mux: %s %s stopped\n' "${HAPROXY##*/}" "$MUX_STATUS_PID"
        return 0
    fi
    if [ "$(kernel_comm "$_sm_name")" != "$_sm_want" ]; then
        printf '[frpc-shared] mux: pid %s is %s now, so the master is gone\n' \
            "$MUX_STATUS_PID" "'$_sm_name'"
        return 0
    fi
    printf '[frpc-shared] WARNING: %s %s did not stop within %ss; sending SIGKILL\n' \
        "${HAPROXY##*/}" "$MUX_STATUS_PID" "$MUX_STOP_TIMEOUT" >&2
    if ! "$MUX_SIGNAL" -KILL "$MUX_STATUS_PID"; then
        printf '[frpc-shared] ERROR: cannot send SIGKILL to %s\n' "$MUX_STATUS_PID" >&2
        return 1
    fi
    return 0
}

cmd_up() {
    _config_inputs=
    _have_config=0
    _scene_file=
    _have_scene=0
    _no_attach=0
    _dry_run=0
    _haproxy_config=
    _tls_listen_set=0
    TLS_CERTS=
    STRICT_SNI=0
    PROXY_PROTOCOL=0
    TLS_LISTEN=$MUX_TLS_LISTEN
    LISTEN=$MUX_LISTEN
    JAVA=$MUX_JAVA
    BEDROCK=$MUX_BEDROCK
    LAN_JAVA=$MUX_LAN_JAVA
    PACKS_ENDPOINT=
    PACKS_OWNED=0
    _packs_port_set=0
    case "$MUX_CERT_WARN_DAYS" in
        ''|*[!0-9]*)
            echo "[frpc-shared] ERROR: MUX_CERT_WARN_DAYS must be a whole number of days" >&2
            exit 2
            ;;
    esac

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
            --scene)
                if [ "$#" -lt 2 ]; then
                    echo "[frpc-shared] ERROR: --scene needs one file" >&2
                    exit 2
                fi
                if [ "$_have_scene" -eq 1 ]; then
                    echo "[frpc-shared] ERROR: --scene may be given only once" >&2
                    exit 2
                fi
                _scene_file=$2
                _have_scene=1
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
            --packs)
                if [ "$#" -lt 2 ]; then
                    echo "[frpc-shared] ERROR: --packs needs HOST:PORT" >&2
                    exit 2
                fi
                if [ "$PACKS_OWNED" -eq 1 ]; then
                    echo "[frpc-shared] ERROR: --packs and --serve-packs are mutually exclusive" >&2
                    exit 2
                fi
                PACKS_ENDPOINT=$2
                shift 2
                ;;
            --serve-packs)
                if [ -n "$PACKS_ENDPOINT" ]; then
                    echo "[frpc-shared] ERROR: --packs and --serve-packs are mutually exclusive" >&2
                    exit 2
                fi
                PACKS_OWNED=1
                shift
                ;;
            --packs-port)
                if [ "$#" -lt 2 ]; then
                    echo "[frpc-shared] ERROR: --packs-port needs a port" >&2
                    exit 2
                fi
                MUX_PACKS_PORT=$2
                _packs_port_set=1
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
                TLS_CERTS=$TLS_CERTS$2'
'
                shift 2
                ;;
            --strict-sni)
                STRICT_SNI=1
                shift
                ;;
            --proxy-protocol)
                # A boolean, like --strict-sni: it takes no value, so
                # `--proxy-protocol=x` is not this option and falls through to
                # the unknown-option branch below.
                PROXY_PROTOCOL=1
                shift
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

    if [ "$_have_scene" -eq 1 ] && [ "$_have_config" -eq 1 ]; then
        echo "[frpc-shared] ERROR: --scene and --config are mutually exclusive" >&2
        exit 2
    fi
    if [ "$_have_scene" -eq 0 ] && [ "$_have_config" -eq 0 ]; then
        echo "[frpc-shared] ERROR: up needs --config <dir|file> or --scene <file>" >&2
        exit 2
    fi
    for _endpoint in "$LISTEN" "$JAVA" "$BEDROCK"; do
        if ! is_endpoint "$_endpoint"; then
            echo "[frpc-shared] ERROR: not HOST:PORT (IPv6 needs brackets): $_endpoint" >&2
            exit 2
        fi
    done
    if [ "$PROXY_PROTOCOL" -eq 1 ] && [ -z "$_haproxy_config" ]; then
        if ! is_endpoint "$LAN_JAVA"; then
            echo "[frpc-shared] ERROR: not HOST:PORT (IPv6 needs brackets): $LAN_JAVA" >&2
            exit 2
        fi
        _lan_java_port=${LAN_JAVA##*:}
        for _endpoint in "$LISTEN" "$JAVA" "$BEDROCK"; do
            if [ "${_endpoint##*:}" = "$_lan_java_port" ]; then
                echo "[frpc-shared] ERROR: MUX_LAN_JAVA must differ from --listen/--java/--bedrock: $LAN_JAVA" >&2
                exit 2
            fi
        done
    fi
    if [ -z "$TLS_CERTS" ]; then
        if [ "$_tls_listen_set" -eq 1 ]; then
            echo "[frpc-shared] ERROR: --tls-listen needs --tls-cert" >&2
            exit 2
        fi
        if [ "$STRICT_SNI" -eq 1 ]; then
            echo "[frpc-shared] ERROR: --strict-sni needs --tls-cert" >&2
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
        if [ "$PROXY_PROTOCOL" -eq 1 ] && [ -z "$_haproxy_config" ] && \
            [ "${TLS_LISTEN##*:}" = "${LAN_JAVA##*:}" ]; then
            echo "[frpc-shared] ERROR: --tls-listen must differ from MUX_LAN_JAVA: $TLS_LISTEN" >&2
            exit 2
        fi
        # Every certificate is checked on its own, and kept as an absolute
        # path: HAProxy reads one `crt` per name and chooses between them by
        # SNI, so a name with a broken PEM must not get as far as the bind.
        _tls_certs_resolved=
        _old_ifs=$IFS
        IFS='
'
        set -f
        for _cert in $TLS_CERTS; do
            if [ ! -f "$_cert" ]; then
                echo "[frpc-shared] ERROR: no such TLS certificate: $_cert" >&2
                exit 2
            fi
            if [ ! -r "$_cert" ]; then
                echo "[frpc-shared] ERROR: cannot read TLS certificate: $_cert" >&2
                exit 2
            fi
            if ! resolve_absolute_file "$_cert"; then
                echo "[frpc-shared] ERROR: cannot resolve TLS certificate: $_cert" >&2
                exit 2
            fi
            _cert_resolved=$_q_result
            if printf '%s\n' "$_tls_certs_resolved" | grep -Fxq "$_cert_resolved"; then
                echo "[frpc-shared] ERROR: the same TLS certificate twice: $_cert_resolved" >&2
                exit 2
            fi
            # HAProxy reads the certificate and its private key from one file.
            if ! grep -q 'BEGIN CERTIFICATE' "$_cert_resolved" 2>/dev/null; then
                echo "[frpc-shared] ERROR: TLS certificate holds no PEM certificate: $_cert_resolved" >&2
                exit 2
            fi
            if ! grep -q 'PRIVATE KEY' "$_cert_resolved" 2>/dev/null; then
                echo "[frpc-shared] ERROR: TLS certificate holds no private key; HAProxy needs one file:" >&2
                echo "[frpc-shared]        cat fullchain.pem privkey.pem > <name>.pem" >&2
                exit 2
            fi
            report_certificate "$_cert_resolved"
            _tls_certs_resolved=$_tls_certs_resolved$_cert_resolved'
'
        done
        set +f
        IFS=$_old_ifs
        TLS_CERTS=$_tls_certs_resolved
    fi
    if [ "$PACKS_OWNED" -eq 0 ] && [ "$_packs_port_set" -eq 1 ]; then
        echo "[frpc-shared] ERROR: --packs-port needs --serve-packs" >&2
        exit 2
    fi
    if [ "$PACKS_OWNED" -eq 1 ]; then
        # The backend is this entry's own process, so its address is not an
        # operator input: the loopback address and the one port this command
        # line names are what the pack server is started with below.
        case "$MUX_PACKS_PORT" in
            ''|*[!0-9]*)
                echo "[frpc-shared] ERROR: --packs-port must be a whole number" >&2
                exit 2
                ;;
        esac
        if [ "$MUX_PACKS_PORT" -lt 1 ] || [ "$MUX_PACKS_PORT" -gt 65535 ]; then
            echo "[frpc-shared] ERROR: --packs-port must be 1-65535: $MUX_PACKS_PORT" >&2
            exit 2
        fi
        PACKS_ENDPOINT=127.0.0.1:$MUX_PACKS_PORT
        PACKS_PREFIX=/${PACKS_DIR##*/}/
        if [ -n "${MUX_PACKS_PREFIX-}" ] && [ "$MUX_PACKS_PREFIX" != "$PACKS_PREFIX" ]; then
            echo "[frpc-shared] ERROR: MUX_PACKS_PREFIX cannot be set with --serve-packs; the prefix is the served directory's name" >&2
            exit 2
        fi
        if [ ! -d "$PACKS_DIR" ]; then
            echo "[frpc-shared] ERROR: no such pack directory: $PACKS_DIR" >&2
            exit 2
        fi
    fi
    if [ -n "$PACKS_ENDPOINT" ]; then
        # The scene owns the generated file; a hand-written one is not
        # something it can add this route to.
        if [ -n "$_haproxy_config" ]; then
            echo "[frpc-shared] ERROR: --packs/--serve-packs cannot be combined with --haproxy-config" >&2
            exit 2
        fi
        if ! is_endpoint "$PACKS_ENDPOINT"; then
            echo "[frpc-shared] ERROR: not HOST:PORT (IPv6 needs brackets): $PACKS_ENDPOINT" >&2
            exit 2
        fi
        # Ports, not host strings: a backend bound to another address on
        # the same port is just as much a collision.
        _packs_port=${PACKS_ENDPOINT##*:}
        for _endpoint in "$LISTEN" "$JAVA" "$BEDROCK" "$TLS_LISTEN" "$LAN_JAVA"; do
            if [ "${_endpoint##*:}" = "$_packs_port" ]; then
                echo "[frpc-shared] ERROR: the packs backend must differ from --listen/--java/--bedrock/--tls-listen/MUX_LAN_JAVA: $PACKS_ENDPOINT" >&2
                exit 2
            fi
        done
        if ! is_packs_prefix "$PACKS_PREFIX"; then
            if [ "$PACKS_OWNED" -eq 1 ]; then
                echo "[frpc-shared] ERROR: the pack directory's name is not a literal URL segment: $PACKS_DIR" >&2
            else
                echo "[frpc-shared] ERROR: MUX_PACKS_PREFIX must be a literal /path/ of A-Za-z0-9._~/- without '//' or '..': $PACKS_PREFIX" >&2
            fi
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
    if [ "$_have_scene" -eq 1 ]; then
        set -- --scene "$_scene_file"
    else
        _old_ifs=$IFS
        IFS='
'
        set -f
        for _config_path in $_config_inputs; do
            set -- "$@" --config "$_config_path"
        done
        set +f
        IFS=$_old_ifs
    fi

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
    quote_sh "$MUX_PIDFILE"
    _haproxy_pid_quoted=$_q_result
    # -W: master-worker mode, so the master can hand the listening socket to a
    # new worker on SIGUSR2 without the port dropping. -db keeps the master in
    # the foreground of its tmux window, which is what supervises it. -p is
    # what 'reload' reads.
    _haproxy_command="$_haproxy_quoted -W -db -p $_haproxy_pid_quoted -f $_haproxy_config_quoted"
    quote_sh "$ROOT"
    _root_quoted=$_q_result
    _server_command='bash scripts/start.sh'
    _packs_command=
    if [ "$PACKS_OWNED" -eq 1 ]; then
        # Both values the pack server needs are passed as arguments, so the
        # process has no second, independently-read source for either: the
        # same $PACKS_ENDPOINT and $PACKS_PREFIX this script writes into the
        # ACL above are what start it.
        quote_sh "$ROOT/scripts/serve-packs.sh"
        _packs_script_quoted=$_q_result
        # The bind address is the endpoint the ACL already forwards to, taken
        # apart rather than written a second time.
        quote_sh "${PACKS_ENDPOINT%:*}"
        _packs_bind_quoted=$_q_result
        quote_sh "$PACKS_DIR"
        _packs_dir_quoted=$_q_result
        _packs_command="$_packs_script_quoted --bind $_packs_bind_quoted --port $MUX_PACKS_PORT --directory $_packs_dir_quoted --prefix $PACKS_PREFIX"
    fi
    _lan_java_config=
    if [ "$PROXY_PROTOCOL" -eq 1 ] && [ "$_haproxy_config" = "$DEFAULT_HAPROXY_CONFIG" ]; then
        _lan_java_config=$LAN_JAVA
    fi

    if [ "$_dry_run" -eq 1 ]; then
        if [ "$_haproxy_config" = "$DEFAULT_HAPROXY_CONFIG" ]; then
            printf '# frpc-shared: would generate HAProxy config %s\n' "$_haproxy_config"
            print_haproxy_config "$LISTEN" "$JAVA" "$BEDROCK" "$TLS_CERTS" "$TLS_LISTEN" \
                "$STRICT_SNI" "$PROXY_PROTOCOL" "$_lan_java_config" \
                "$PACKS_ENDPOINT" "$PACKS_PREFIX"
        else
            printf '# frpc-shared: would use HAProxy config %s\n' "$_haproxy_config"
        fi
        FRPC_SESSION=$SESSION "$FRPC_SH" up --defer-server --dry-run "$@"
        printf 'tmux new-window -P -F %s -t %s -n %s -c %s -- cat\n' \
            "'#{window_id}'" "=$SESSION" "$MUX_WINDOW" "$_root_quoted"
        printf 'tmux set-window-option -t <window-id> remain-on-exit on\n'
        printf 'tmux set-window-option -t <window-id> monitor-activity on\n'
        printf 'tmux respawn-window -k -t <window-id> %s\n' "$_haproxy_command"
        if [ "$PACKS_OWNED" -eq 1 ]; then
            printf 'tmux new-window -P -F %s -t %s -n %s -c %s -- cat\n' \
                "'#{window_id}'" "=$SESSION" "$PACKS_WINDOW" "$_root_quoted"
            printf 'tmux set-window-option -t <packs-window-id> remain-on-exit on\n'
            printf 'tmux set-window-option -t <packs-window-id> monitor-activity on\n'
            printf 'tmux respawn-window -k -t <packs-window-id> %s\n' "$_packs_command"
        fi
        printf 'tmux set-window-option -t <server-window-id> @asp-server-deferred 0\n'
        printf 'tmux respawn-window -k -t <server-window-id> %s\n' "$_server_command"
        return 0
    fi

    # Refuse before anything is started. A master left behind - by a crash,
    # or by a teardown that only sent the SIGHUP it ignores - holds the
    # listen port, and the mux window would die on "Address already in use"
    # instead, after the frpc sidecars had come up.
    mux_pid_status
    case "$MUX_STATUS_STATE" in
        live)
            printf '[frpc-shared] ERROR: a mux is already running as pid %s (%s); run down first\n' \
                "$MUX_STATUS_PID" "$MUX_PIDFILE" >&2
            exit 3
            ;;
        other)
            printf '[frpc-shared] ERROR: pidfile %s names pid %s (%s), which is not %s; run down to clear it\n' \
                "$MUX_PIDFILE" "$MUX_STATUS_PID" "$MUX_STATUS_NAME" "${HAPROXY##*/}" >&2
            exit 3
            ;;
    esac
    _pre_listen_rc=0
    mux_listen_check || _pre_listen_rc=$?
    if [ "$_pre_listen_rc" -eq 0 ]; then
        printf '[frpc-shared] ERROR: something already listens on %s; run down or stop it first\n' \
            "$LISTEN" >&2
        exit 3
    fi
    if [ -n "$_lan_java_config" ]; then
        _pre_lan_rc=0
        endpoint_listen_check "$LAN_JAVA" || _pre_lan_rc=$?
        if [ "$_pre_lan_rc" -eq 0 ]; then
            printf '[frpc-shared] ERROR: something already listens on LAN Java %s; run down or stop it first\n' \
                "$LAN_JAVA" >&2
            exit 3
        fi
    fi
    if [ "$PACKS_OWNED" -eq 1 ]; then
        # The backend is this entry's to start, so an occupied port is a
        # failure to report now, not a 503 for players to discover later.
        _pre_packs_rc=0
        endpoint_listen_check "$PACKS_ENDPOINT" || _pre_packs_rc=$?
        if [ "$_pre_packs_rc" -eq 0 ]; then
            printf '[frpc-shared] ERROR: something already listens on the packs backend %s; run down or stop it first\n' \
                "$PACKS_ENDPOINT" >&2
            exit 3
        fi
    fi

    require_frpc || exit 1
    if [ -z "$TMUX_BIN" ]; then
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
    _haproxy_command="$_haproxy_quoted -W -db -p $_haproxy_pid_quoted -f $_haproxy_config_quoted"

    # The pidfile is written by HAProxy, so its directory has to exist first.
    _pid_dir=${MUX_PIDFILE%/*}
    if ! mkdir -p "$_pid_dir"; then
        echo "[frpc-shared] ERROR: cannot create the pidfile directory: $_pid_dir" >&2
        exit 1
    fi

    if tmux has-session -t "=$SESSION" 2>/dev/null; then
        printf '[frpc-shared] ERROR: session %s already exists; run down first\n' "$SESSION" >&2
        exit 3
    fi

    if [ -z "$_haproxy_config" ] || [ "$_haproxy_config" = "$DEFAULT_HAPROXY_CONFIG" ]; then
        if ! generate_haproxy_config "$_haproxy_config" "$LISTEN" "$JAVA" "$BEDROCK" \
            "$TLS_CERTS" "$TLS_LISTEN" "$STRICT_SNI" "$PROXY_PROTOCOL" "$_lan_java_config" \
            "$PACKS_ENDPOINT" "$PACKS_PREFIX"; then
            echo "[frpc-shared] ERROR: cannot write HAProxy config: $_haproxy_config" >&2
            exit 1
        fi
    fi
    if ! haproxy_check "$_haproxy_config"; then
        echo "[frpc-shared] ERROR: HAProxy rejected $_haproxy_config" >&2
        exit 1
    fi

    # 1. Sidecars first. frpc.sh leaves the server window as a placeholder.
    if FRPC_SESSION=$SESSION "$FRPC_SH" up --defer-server --no-attach "$@"; then
        :
    else
        _sidecar_status=$?
        echo "[frpc-shared] ERROR: frpc scene failed to start" >&2
        exit "$_sidecar_status"
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
    if [ "$PACKS_OWNED" -eq 1 ]; then
        # 2b. The pack server this entry declared. It is started after the mux
        # and before the server, and its port and prefix are the ones already
        # written into the ACL: one command line, two consumers.
        if ! spawn_window "=$SESSION" "$PACKS_WINDOW" "$_packs_command"; then
            echo "[frpc-shared] ERROR: could not create the $PACKS_WINDOW window" >&2
            FRPC_SESSION=$SESSION "$FRPC_SH" down >/dev/null 2>&1 || true
            exit 1
        fi
        _packs_ready=0
        _packs_elapsed=0
        while [ "$_packs_elapsed" -lt "$MUX_READY_TIMEOUT" ]; do
            _packs_rc=0
            endpoint_listen_check "$PACKS_ENDPOINT" || _packs_rc=$?
            if [ "$_packs_rc" -eq 0 ]; then
                _packs_ready=1
                break
            fi
            if [ "$_packs_rc" -eq 2 ]; then
                _packs_ready=1
                break
            fi
            if ! _packs_dead=$(tmux list-panes -t "=$SESSION:$PACKS_WINDOW" -F '#{pane_dead}' 2>/dev/null); then
                _packs_dead=1
            fi
            if [ "$_packs_dead" != 0 ]; then
                break
            fi
            sleep 1
            _packs_elapsed=$((_packs_elapsed + 1))
        done
        if [ "$_packs_ready" -eq 0 ]; then
            printf '[frpc-shared] ERROR: the %s window did not bind %s within %ss\n' \
                "$PACKS_WINDOW" "$PACKS_ENDPOINT" "$MUX_READY_TIMEOUT" >&2
            if _packs_capture=$(tmux capture-pane -p -J -t "=$SESSION:$PACKS_WINDOW" 2>/dev/null); then
                printf '%s\n' "$_packs_capture" | tail -n 20 >&2
            fi
            FRPC_SESSION=$SESSION "$FRPC_SH" down >/dev/null 2>&1 || true
            exit 1
        fi
    elif [ -n "$PACKS_ENDPOINT" ]; then
        # A foreign backend: the mux routes to it just the same, so a missing
        # one is a warning, not a failed start.
        _packs_backend_rc=0
        endpoint_listen_check "$PACKS_ENDPOINT" || _packs_backend_rc=$?
        if [ "$_packs_backend_rc" -eq 1 ]; then
            printf '[frpc-shared] WARNING: nothing listens on the packs backend %s; requests under %s will get 503\n' \
                "$PACKS_ENDPOINT" "$PACKS_PREFIX" >&2
        fi
    fi
    if ! write_cert_inventory; then
        printf '[frpc-shared] WARNING: cannot write certificate inventory: %s\n' \
            "$MUX_CERT_STATE" >&2
    fi
    if ! write_packs_state; then
        printf '[frpc-shared] WARNING: cannot write the pack route state: %s\n' \
            "$MUX_PACKS_STATE" >&2
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
    case "$MUX_STOP_TIMEOUT" in
        ''|*[!0-9]*)
            echo "[frpc-shared] ERROR: MUX_STOP_TIMEOUT must be a whole number of seconds" >&2
            exit 2
            ;;
    esac
    require_frpc || exit 1
    _down_status=0
    FRPC_SESSION=$SESSION "$FRPC_SH" down || _down_status=$?
    # The sidecars and the server are tmux's to stop; the mux is not, and
    # this is where it gets stopped. Then the pidfile goes with it: one that
    # outlives its master is a trap for the next caller, since the pid may
    # belong to something else by then.
    stop_mux || _down_status=1
    rm -f "$MUX_PIDFILE"
    rm -f "$MUX_CERT_STATE"
    rm -f "$MUX_PACKS_STATE"
    return "$_down_status"
}

# Hand the listening socket to a new HAProxy worker without dropping it or
# the players on it. What is being reloaded is whatever the configuration
# reads, a certificate above all.
cmd_reload() {
    if [ "$#" -ne 0 ]; then
        usage >&2
        exit 2
    fi
    # The master writes itself first; workers may follow on later lines and
    # only the master takes the reload signal. Which pid that is, and whether
    # it may be signalled at all, is the same question 'down' and 'up' ask.
    mux_pid_status
    case "$MUX_STATUS_STATE" in
        none)
            printf '[frpc-shared] ERROR: no pidfile at %s: the mux is not running, start it with up\n' \
                "$MUX_PIDFILE" >&2
            exit 2
            ;;
        invalid)
            printf '[frpc-shared] ERROR: %s does not hold a process id\n' \
                "$MUX_PIDFILE" >&2
            exit 2
            ;;
        stale)
            printf '[frpc-shared] ERROR: cannot read process %s: the pidfile is stale, or the process belongs to another user (start the mux with up)\n' \
                "$MUX_STATUS_PID" >&2
            exit 2
            ;;
        other)
            printf '[frpc-shared] ERROR: process %s is %s, not %s: refusing to signal it\n' \
                "$MUX_STATUS_PID" "'$MUX_STATUS_NAME'" "${HAPROXY##*/}" >&2
            exit 2
            ;;
    esac
    if ! "$MUX_SIGNAL" -USR2 "$MUX_STATUS_PID"; then
        printf '[frpc-shared] ERROR: cannot send SIGUSR2 to %s\n' "$MUX_STATUS_PID" >&2
        exit 1
    fi
    printf '[frpc-shared] reload: SIGUSR2 sent to %s %s, which re-reads its configuration\n' \
        "${HAPROXY##*/}" "$MUX_STATUS_PID"
}

cmd_status() {
    if [ "$#" -ne 0 ]; then
        usage >&2
        exit 2
    fi
    case "$MUX_CERT_WARN_DAYS" in
        ''|*[!0-9]*)
            echo "[frpc-shared] ERROR: MUX_CERT_WARN_DAYS must be a whole number of days" >&2
            exit 2
            ;;
    esac
    report_mux_status
    report_mux_tls
    report_cert_inventory
    report_packs_status
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
    reload)
        cmd_reload "$@"
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
