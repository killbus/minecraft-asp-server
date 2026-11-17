@echo off
REM Serve server\packs for PackManagerPro (default port 8000).
REM PackManagerPro sends this URL to the client, so 127.0.0.1 only works
REM for clients on this machine or through a proxy; see the SOP.
setlocal
cd /d "%~dp0.."
if not defined PACK_PORT set "PACK_PORT=8000"
python -m http.server %PACK_PORT% --directory server\packs
