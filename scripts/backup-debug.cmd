@echo on
REM ============================================================
REM  ASP server backup (Windows)
REM
REM  Usage:  scripts\backup.cmd [SERVER_DIR]
REM  Default SERVER_DIR: ..\server (relative to this script)
REM
REM  Scope (see docs/ASP-SOP.md section 1 - not regenerable):
REM    world/ + whitelist/ban/usercache/ops json + server config
REM    + config/ (Paper) + per-plugin config dirs (jars excluded - re-downloadable)
REM  Output: ..\backups\<UTC timestamp>\ with MANIFEST.txt
REM  Retention: newest %KEEP% backups, older ones pruned.
REM  Run while the server is stopped for a consistent snapshot.
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "KEEP=5"
if "%~1"=="" (set "SERVER_DIR=%~dp0..\server") else (set "SERVER_DIR=%~1")
set "BACKUP_ROOT=%~dp0..\backups"

for /f %%i in ('powershell -NoProfile -Command "[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')"') do set "TS=%%i"
set "DEST=%BACKUP_ROOT%\%TS%"

REM --- preflight ---
if not exist "%SERVER_DIR%\asp-server.jar" (
    echo [backup] ERROR: not a server dir: %SERVER_DIR% ^(asp-server.jar missing^)
    exit /b 1
)
tasklist /FI "IMAGENAME eq java.exe" 2>nul | find /I "java.exe" >nul && echo [backup] WARN: a java process is running; stop the server for a consistent backup

mkdir "%DEST%"

REM --- world: mirror, runtime artifacts excluded ---
robocopy "%SERVER_DIR%\world" "%DEST%\world" /MIR /XF session.lock level.dat_old /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo [backup] ERROR: world copy failed ^(robocopy exit %errorlevel%^)
    exit /b 1
)

REM --- player files + server-level config ---
for %%f in (whitelist.json ops.json banned-ips.json banned-players.json usercache.json server.properties eula.txt bukkit.yml spigot.yml commands.yml server-icon.png) do copy /Y "%SERVER_DIR%\%%f" "%DEST%\" >nul 2>nul

REM --- Paper config dir (paper-global.yml, paper-world-defaults.yml) ---
if exist "%SERVER_DIR%\config" robocopy "%SERVER_DIR%\config" "%DEST%\config" /MIR /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo [backup] ERROR: config copy failed ^(robocopy exit %errorlevel%^)
    exit /b 1
)

REM --- plugin dirs: config + data, jars excluded ---
for /d %%d in ("%SERVER_DIR%\plugins\*") do robocopy "%%~d" "%DEST%\plugins\%%~nxd" /MIR /XF *.jar /NFL /NDL /NJH /NJS /NP >nul
copy /Y "%SERVER_DIR%\plugins\*.yml" "%DEST%\plugins\" >nul 2>nul

REM --- manifest: hash every backed-up file (world included) ---
powershell -NoProfile -Command "$d=(Resolve-Path -LiteralPath $env:DEST).Path; $o=@('# ASP backup ' + $env:TS); $sha=[System.Security.Cryptography.SHA256]::Create(); $fs=[System.IO.Directory]::GetFiles($d,'*',[System.IO.SearchOption]::AllDirectories); [Array]::Sort($fs,[System.StringComparer]::Ordinal); foreach ($f in $fs) { if ([System.IO.Path]::GetFileName($f) -ne 'MANIFEST.txt') { $s=[System.IO.File]::OpenRead($f); $h=([System.BitConverter]::ToString($sha.ComputeHash($s)) -replace '-','').ToLower(); $s.Dispose(); $rel=$f.Substring($d.Length+1).Replace([char]92,'/'); $o += ('{0}  ./{1}' -f $h, $rel) } }; [System.IO.File]::WriteAllText((Join-Path $d 'MANIFEST.txt'), (($o -join [char]10) + [char]10), [System.Text.Encoding]::ASCII)"
if errorlevel 1 (
    echo [backup] ERROR: manifest generation failed
    exit /b 1
)

REM --- prune: keep newest %KEEP% (dir names are timestamps) ---
set /a n=0
for /f "delims=" %%d in ('dir /b /ad /o-n "%BACKUP_ROOT%" 2^>nul') do (
    set /a n+=1
    if !n! gtr %KEEP% rmdir /s /q "%BACKUP_ROOT%\%%d"
)

echo [backup] OK: %DEST%
endlocal
