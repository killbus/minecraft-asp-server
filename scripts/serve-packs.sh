#!/bin/sh
# Serve server/packs at /packs/ for PackManagerPro (default port 8000).
# The mux forwards the path unchanged, so the URL prefix is stripped here;
# see scripts/serve_packs.py.
set -eu
cd "$(dirname "$0")/.."
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    PYTHON=python
fi
exec "$PYTHON" scripts/serve_packs.py --port "${PACK_PORT:-8000}"
