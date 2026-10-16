#!/usr/bin/env bash
# ============================================================
#  AdvancedSlimePaper 26.2 - start script (Linux / macOS shell)
#  Starts the server in the sibling server/ directory.
#  Usage:
#    scripts/start.sh                 foreground (this terminal)
#    nohup scripts/start.sh &         detach from the terminal
#  A service manager (systemd unit) is the production option.
#  Requires: Java 25 (MC 26.1+ refuses older JDKs).
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/../server"

# JAVA may point at a full java binary; otherwise fall back to PATH.
JAVA="${JAVA:-java}"

if ! command -v "$JAVA" >/dev/null 2>&1; then
    echo "[start] ERROR: java not found (set JAVA=/path/to/java or put java 25+ on PATH)" >&2
    exit 1
fi

# MC 26.1+ refuses to boot on older JDKs; fail fast with a clear message.
major="$("$JAVA" -version 2>&1 | head -n1 | sed -n 's/.*version="\([0-9]*\).*/\1/p')"
if [ -z "$major" ] || [ "$major" -lt 25 ]; then
    echo "[start] ERROR: Java 25+ required (found: ${major:-unknown})" >&2
    exit 1
fi

if [ ! -f asp-server.jar ]; then
    echo "[start] ERROR: asp-server.jar not found in $(pwd)" >&2
    exit 1
fi

# -Xms / -Xmx: tune to available RAM. Bedrock+Java mixed load is
# heavier than Java-only. 4G heap is a sane default for a small SMP.
exec "$JAVA" -Xms2G -Xmx4G -XX:+UseG1GC -jar asp-server.jar
