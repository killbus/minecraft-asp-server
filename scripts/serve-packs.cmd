@echo off
REM Serve server\packs at /packs/ for native resource packs (default port 8000).
REM The mux forwards the path unchanged, so the URL prefix is stripped here;
REM see scripts\serve_packs.py.
REM
REM Arguments are passed through: the shared-TCP scene starts this with an
REM explicit --port and --prefix. Without arguments the defaults of
REM scripts\serve_packs.py apply (8000, /packs/).
setlocal
cd /d "%~dp0.."
python scripts\serve_packs.py %*
