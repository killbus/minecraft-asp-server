#!/bin/sh
# Serve server/packs at /packs/ for PackManagerPro (default port 8000).
# The mux forwards the path unchanged, so the URL prefix is stripped here;
# see scripts/serve_packs.py.
#
# Arguments are passed through: the shared-TCP scene starts this with an
# explicit --port and --prefix, so neither the port nor the URL prefix has
# a second, independently-read source. Without arguments the defaults of
# scripts/serve_packs.py apply (8000, /packs/), which is what a manual
# one-off run wants.
set -eu
cd "$(dirname "$0")/.."
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    PYTHON=python
fi
exec "$PYTHON" scripts/serve_packs.py "$@"
