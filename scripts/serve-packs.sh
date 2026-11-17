#!/bin/sh
# Serve server/packs for PackManagerPro (default port 8000).
# PackManagerPro sends this URL to the client, so 127.0.0.1 only works
# for clients on this machine or through a proxy; see the SOP.
set -eu
cd "$(dirname "$0")/.."
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    PYTHON=python
fi
exec "$PYTHON" -m http.server "${PACK_PORT:-8000}" --directory server/packs
