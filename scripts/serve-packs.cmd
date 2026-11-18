@echo off
REM Serve server\packs at /packs/ for PackManagerPro (default port 8000).
REM The mux forwards the path unchanged, so the URL prefix is stripped here;
REM see scripts\serve_packs.py.
setlocal
cd /d "%~dp0.."
if not defined PACK_PORT set "PACK_PORT=8000"
python scripts\serve_packs.py --port %PACK_PORT%
