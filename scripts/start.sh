#!/usr/bin/env bash
# ============================================================
#  Paper 26.2 - start script (Linux / macOS shell)
#  Starts the server in the sibling server/ directory.
#
#  Before launching, backs up the previous session's world. The server
#  is stopped at this point by definition, so the snapshot is
#  consistent - this is the natural backup point for a server that is
#  not running 24/7.
#  The backup is skipped when a complete one is younger than
#  BACKUP_MIN_INTERVAL (60 min) so restart loops do not push older
#  backups out of the retention window. Set ASP_SKIP_BACKUP=1 to start
#  without backing up at all.
#
#  Usage:
#    scripts/start.sh                 foreground (this terminal)
#    nohup scripts/start.sh &         detach from the terminal
#  A service manager (systemd unit) is the production option.
#  Requires: Java 25 (MC 26.1+ refuses older JDKs).
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORLD_NAME=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --world)
            if [ "$#" -lt 2 ] || [ -n "$WORLD_NAME" ] || ! [[ "$2" =~ ^[A-Za-z0-9_-]+$ ]]; then
                echo "[start] ERROR: --world requires one directory name using ASCII letters, digits, _ or -" >&2
                exit 2
            fi
            WORLD_NAME="$2"
            shift 2
            ;;
        *)
            echo "[start] ERROR: usage: scripts/start.sh [--world NAME]" >&2
            exit 2
            ;;
    esac
done
cd "$SCRIPT_DIR/../server"

WORLD_ARGS=()
if [ -n "$WORLD_NAME" ]; then
    if [ ! -f "$WORLD_NAME/level.dat" ] || [ -L "$WORLD_NAME" ] || [ -L "$WORLD_NAME/level.dat" ]; then
        echo "[start] ERROR: --world requires an existing native save at server/$WORLD_NAME/level.dat (no links)" >&2
        exit 2
    fi
    WORLD_ARGS=(--world "$WORLD_NAME")
fi

CONFIG_ARGS=()
if [ -e ../settings/minecraft-server.json ] || [ -L ../settings/minecraft-server.json ] ||
   [ -e ../settings/resource-packs.json ] || [ -L ../settings/resource-packs.json ] || [ -L ../settings ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "[start] ERROR: python3 is required to validate settings/minecraft-server.json and legacy pack settings" >&2
        exit 2
    fi
    PACK_ARGS=()
    if [ -n "$WORLD_NAME" ]; then PACK_ARGS=("--world=$WORLD_NAME"); fi
    PACK_STATUS=0
    python3 -B "$SCRIPT_DIR/select_resource_pack.py" "${PACK_ARGS[@]}" || PACK_STATUS=$?
    case "$PACK_STATUS" in
        0) CONFIG_ARGS=(--config ../.tmp/startup/server.properties) ;;
        3) ;;
        *) exit 2 ;;
    esac
elif [ -e ../settings ] && { [ ! -d ../settings ] || [ ! -x ../settings ]; }; then
    echo "[start] ERROR: cannot inspect settings/minecraft-server.json; check settings permissions" >&2
    exit 2
fi

# JAVA may point at a full java binary; otherwise fall back to PATH.
JAVA="${JAVA:-java}"

if ! command -v "$JAVA" >/dev/null 2>&1; then
    echo "[start] ERROR: java not found (set JAVA=/path/to/java or put java 25+ on PATH)" >&2
    exit 1
fi

# MC 26.1+ refuses to boot on older JDKs; fail fast with a clear message.
major="$("$JAVA" -version 2>&1 | head -n1 | awk -F'"' '{print $2}' | cut -d. -f1)"
if [ -z "$major" ] || [ "$major" -lt 25 ]; then
    echo "[start] ERROR: Java 25+ required (found: ${major:-unknown})" >&2
    exit 1
fi

if [ ! -f paper-server.jar ]; then
    echo "[start] ERROR: paper-server.jar not found in $(pwd)" >&2
    exit 1
fi

# --- pre-start backup ---
if [ "${ASP_SKIP_BACKUP:-0}" != "1" ]; then
    BACKUP_MIN_INTERVAL="${BACKUP_MIN_INTERVAL:-60}" "$SCRIPT_DIR/backup.sh" \
        || echo "[start] WARN: pre-start backup failed; starting the server anyway." >&2
fi

# -Xms / -Xmx: tune to available RAM. Bedrock+Java mixed load is
# heavier than Java-only. 4G heap is a sane default for a small SMP.
exec "$JAVA" -Xms2G -Xmx4G -XX:+UseG1GC \
    -Dpaper.disableStartupVersionCheck=true \
    -jar paper-server.jar "${WORLD_ARGS[@]}" "${CONFIG_ARGS[@]}"
