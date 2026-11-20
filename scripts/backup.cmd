@if not defined BACKUP_DEBUG echo off
REM ============================================================
REM  Paper server backup (Windows)
REM
REM  Usage:  scripts\backup.cmd [SERVER_DIR]
REM  Default SERVER_DIR: ..\server (relative to this script)
REM
REM  Scope (see docs/SINGLE-WORLD-SOP.md):
REM    native saves + whitelist/ban/usercache/ops json + server config
REM    + config/ (Paper) + per-plugin config dirs (jars excluded)
REM    + settings/*.json (per-host coordinates; *.example.json excluded)
REM    Known-regenerable plugin caches are excluded (see below).
REM  Output: <target>\<UTC timestamp>\ with MANIFEST.txt
REM
REM  Every configured target gets its own full copy and its own manifest,
REM  so the copies are independent: one bad disk cannot corrupt the other.
REM
REM  A backup counts as complete only when COMPLETE exists. Prune keeps
REM  the newest %KEEP% complete backups per target and deletes partial
REM  leftovers, so a failed run can never push a good backup out of the
REM  window. Run while the server is stopped for a consistent snapshot.
REM
REM  Env overrides:
REM    KEEP                  complete backups kept per target (default 5)
REM    BACKUP_MIN_INTERVAL   skip when every target already has a complete
REM                          backup younger than this many minutes
REM                          (default 0 = never skip)
REM    SETTINGS_DIR          per-host settings source (default ..\settings)
REM    BACKUP_REQUIRE_ALL=1  a failed mirror fails the run (default 0)
REM    ALLOW_ONLINE=1        proceed even though the server is running
REM ============================================================
setlocal EnableExtensions DisableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
cd /d "%~dp0"

if not defined KEEP set "KEEP=5"
if not defined BACKUP_MIN_INTERVAL set "BACKUP_MIN_INTERVAL=0"
if not defined BACKUP_REQUIRE_ALL set "BACKUP_REQUIRE_ALL=0"
if not defined SETTINGS_DIR set "SETTINGS_DIR=%~dp0..\settings"
if "%~1"=="" (set "SERVER_DIR=%~dp0..\server") else (set "SERVER_DIR=%~1")
set "ERRMSG="

for /f %%i in ('powershell -NoProfile -Command "[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')"') do set "TS=%%i"

REM Fail unless a path below explicitly succeeds. `exit /b` cannot be used
REM inside a parenthesised block here: when the enclosing block has more
REM commands after it, cmd loses the exit code (verified on this build), so
REM every early exit is `goto :finish` and the code travels in RESULT.
set "RESULT=1"

REM --- preflight ---
if not exist "%SERVER_DIR%\paper-server.jar" (
    echo [backup] ERROR: not a server dir: %SERVER_DIR% ^(paper-server.jar missing^)
    goto :finish
)

for %%d in (config plugins settings) do if exist "%SERVER_DIR%\%%d\level.dat" (
    echo [backup] ERROR: native save collides with snapshot directory: %%d
    goto :finish
)

where python >nul 2>nul
if errorlevel 1 (
    echo [backup] ERROR: python is required for settings\minecraft-server.json
    goto :finish
)
python -B "%SCRIPT_DIR%backup_settings.py" --format cmd --server-dir "%SERVER_DIR%" --settings-dir "%SETTINGS_DIR%" >nul
if errorlevel 1 goto :finish
setlocal EnableDelayedExpansion
set "TGT_N=0"
for /f "usebackq delims=" %%a in (`python -B "%SCRIPT_DIR%backup_settings.py" --format cmd --server-dir "%SERVER_DIR%" --settings-dir "%SETTINGS_DIR%"`) do (
    set /a TGT_N+=1
    set "TGT_!TGT_N!=%%a"
)

if %TGT_N% equ 0 (
    echo [backup] ERROR: no validated backup.targets were returned
    goto :finish
)

REM Refuse a torn snapshot: the Paper server must be stopped while we copy.
REM Match the real launch shape (`java ... -jar ...\paper-server.jar`) so an
REM unrelated process that merely mentions the file name is not a false hit.
powershell -NoProfile -Command "try { $p = Get-CimInstance Win32_Process -Filter 'Name=''java.exe''' -ErrorAction Stop | Where-Object { $_.CommandLine -match '-jar\s+.*paper-server\.jar' }; if ($p) { exit 2 } } catch { exit 3 }; exit 0"
if %errorlevel% equ 3 (
    echo [backup] ERROR: cannot determine whether the Paper server is running
    if not "%ALLOW_ONLINE%"=="1" goto :finish
    echo [backup] WARN: ALLOW_ONLINE=1 - running check skipped
    goto :running_check_done
)
if errorlevel 2 if not "%ALLOW_ONLINE%"=="1" (
    echo [backup] ERROR: the Paper server is running; stop it first ^(or set ALLOW_ONLINE=1^)
    goto :finish
)
if errorlevel 2 echo [backup] WARN: ALLOW_ONLINE=1 - snapshot may be inconsistent
:running_check_done

REM --- optional: skip only when EVERY target is already up to date ---
REM A target that fell behind (unplugged disk, new target added) forces a
REM run even if the primary is fresh, so the mirror can catch up.
if not "%BACKUP_MIN_INTERVAL%"=="0" (
    set "ALL_RECENT=1"
    for /l %%i in (1,1,%TGT_N%) do (
        call :is_recent "!TGT_%%i!"
        if !errorlevel! neq 0 set "ALL_RECENT=0"
    )
    if "!ALL_RECENT!"=="1" (
        echo [backup] SKIP: every target has a complete backup younger than %BACKUP_MIN_INTERVAL% min
        set "RESULT=0"
        goto :finish
    )
)

REM --- run every target; a mirror failure is not fatal by default ---
set /a ok=0
set /a bad=0
set /a primary_failed=0
for /l %%i in (1,1,%TGT_N%) do (
    call :do_target "!TGT_%%i!"
    if !errorlevel! equ 0 (
        set /a ok+=1
        echo [backup] OK: !TGT_%%i!\%TS%
    ) else (
        set /a bad+=1
        if %%i equ 1 set /a primary_failed=1
        echo [backup] ERROR: target failed: !TGT_%%i!
    )
)

if %ok% equ 0 (
    echo [backup] ERROR: every target failed
    goto :finish
)
if %primary_failed% equ 1 (
    echo [backup] ERROR: the primary target failed
    goto :finish
)
if %bad% gtr 0 (
    if "%BACKUP_REQUIRE_ALL%"=="1" (
        echo [backup] ERROR: mirror failed and BACKUP_REQUIRE_ALL=1
        goto :finish
    )
    echo [backup] WARN: %bad% of %TGT_N% targets failed; the rest are complete
)
set "RESULT=0"

:finish
endlocal & exit /b %RESULT%


REM ============================================================
REM  :is_recent <target dir>
REM  Exit 0 when that target holds a complete backup younger than
REM  BACKUP_MIN_INTERVAL minutes, exit 1 otherwise.
REM ============================================================
:is_recent
set "TGT=%~1"
powershell -NoProfile -Command "$m=[double]$env:BACKUP_MIN_INTERVAL; $n=Get-ChildItem -LiteralPath $env:TGT -Directory -EA 0 | Where-Object { Test-Path (Join-Path $_.FullName 'COMPLETE') } | Sort-Object Name -Descending | Select-Object -First 1; if ($n) { $c=Get-Item (Join-Path $n.FullName 'COMPLETE'); if (((Get-Date)-$c.LastWriteTime).TotalMinutes -lt $m) { exit 0 } }; exit 1"
exit /b %errorlevel%


REM ============================================================
REM  :do_target <target dir>
REM  Writes one complete backup into that target. Exit 0 on success,
REM  1 on any failure (the partial directory is removed either way).
REM ============================================================
:do_target
setlocal EnableDelayedExpansion
set "TDIR=%~1"
set "DEST=%TDIR%\%TS%"
set "ERRMSG="
set "CREATED_DEST="

python -B "%SCRIPT_DIR%backup_settings.py" --snapshot "%TDIR%" "%TS%" --new
if errorlevel 1 set "ERRMSG=unsafe or existing snapshot destination"
if defined ERRMSG goto :dt_fail

mkdir "%DEST%" 2>nul
if errorlevel 1 set "ERRMSG=cannot create a new snapshot directory"
if not exist "%DEST%" set "ERRMSG=cannot create %DEST%"
if defined ERRMSG goto :dt_fail
set "CREATED_DEST=1"

for /d %%w in ("%SERVER_DIR%\*") do if exist "%%w\level.dat" if not exist "%%w\level.dat\" (
    robocopy "%%w" "%DEST%\%%~nxw" /MIR /XF session.lock level.dat_old /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 if not defined ERRMSG set "ERRMSG=world copy failed: %%~nxw"
)
if defined ERRMSG goto :dt_fail

REM --- player files + server-level config ---
for %%f in (whitelist.json ops.json banned-ips.json banned-players.json usercache.json server.properties eula.txt bukkit.yml spigot.yml commands.yml permissions.yml server-icon.png) do copy /Y "%SERVER_DIR%\%%f" "%DEST%\" >nul 2>nul

REM --- Paper config dir (paper-global.yml, paper-world-defaults.yml) ---
if exist "%SERVER_DIR%\config" (
    robocopy "%SERVER_DIR%\config" "%DEST%\config" /MIR /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 set "ERRMSG=config copy failed (robocopy exit !errorlevel!)"
)
if defined ERRMSG goto :dt_fail

REM --- plugin dirs: config + data, jars excluded ---
REM Only caches proven regenerable in docs/SINGLE-WORLD-SOP.md are
REM excluded. Do not widen this to every */cache/: a plugin may keep
REM real state in a directory with that name.
for /d %%d in ("%SERVER_DIR%\plugins\*") do (
    set "EXCLUDE_CACHE="
    if /i "%%~nxd"=="Geyser-Spigot" set "EXCLUDE_CACHE=/XD "%%~fd\cache""
    if /i "%%~nxd"=="SkinsRestorer" set "EXCLUDE_CACHE=/XD "%%~fd\cache""
    robocopy "%%~d" "%DEST%\plugins\%%~nxd" /MIR /XF *.jar !EXCLUDE_CACHE! /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 if not defined ERRMSG set "ERRMSG=plugin copy failed: %%~nxd"
)
if defined ERRMSG goto :dt_fail
copy /Y "%SERVER_DIR%\plugins\*.yml" "%DEST%\plugins\" >nul 2>nul

REM --- per-host settings: untracked, so the snapshot is their only copy ---
REM git tracks settings\*.example.json only. The file that fills the
REM placeholders is host state, not source: it cannot be reconstructed from
REM the repository, and it is what explains the rendered server.properties
REM and plugin yml beside it. See docs\SINGLE-WORLD-SOP.md.
if exist "%SETTINGS_DIR%" (
    robocopy "%SETTINGS_DIR%" "%DEST%\settings" /MIR /XF *.example.json /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 set "ERRMSG=settings copy failed (robocopy exit !errorlevel!)"
)
if defined ERRMSG goto :dt_fail

REM Resource packs under packs/ are externally sourced and regenerable; they
REM stay out of the snapshot. Preserve their external source and hash.

REM --- manifest: hash every backed-up file (world included) ---
powershell -NoProfile -Command "$d=(Resolve-Path -LiteralPath $env:DEST).Path; $o=@('# Paper backup ' + $env:TS); $sha=[System.Security.Cryptography.SHA256]::Create(); $fs=[System.IO.Directory]::GetFiles($d,'*',[System.IO.SearchOption]::AllDirectories); [Array]::Sort($fs,[System.StringComparer]::Ordinal); foreach ($f in $fs) { if ([System.IO.Path]::GetFileName($f) -ne 'MANIFEST.txt') { $s=[System.IO.File]::OpenRead($f); $h=([System.BitConverter]::ToString($sha.ComputeHash($s)) -replace '-','').ToLower(); $s.Dispose(); $rel=$f.Substring($d.Length+1).Replace([char]92,'/'); $o += ('{0}  ./{1}' -f $h, $rel) } }; [System.IO.File]::WriteAllText((Join-Path $d 'MANIFEST.txt'), (($o -join [char]10) + [char]10), [System.Text.Encoding]::ASCII)"
if errorlevel 1 set "ERRMSG=manifest generation failed"
if defined ERRMSG goto :dt_fail
if not exist "%DEST%\MANIFEST.txt" set "ERRMSG=manifest file missing after generation"
if defined ERRMSG goto :dt_fail

REM --- completion marker: written last, only for a fully written backup ---
> "%DEST%\COMPLETE" echo %TS%
if not exist "%DEST%\COMPLETE" set "ERRMSG=cannot write COMPLETE marker"
if defined ERRMSG goto :dt_fail
set "CREATED_DEST="

REM --- prune THIS target: keep its newest %KEEP% complete backups ---
REM Only directories named like our own timestamps are touched, so a
REM target may point at a shared folder without us deleting its contents.
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%backup_cleanup.ps1" -Action prune
if errorlevel 1 set "ERRMSG=backup pruning failed"
if defined ERRMSG goto :dt_fail

endlocal & exit /b 0

:dt_fail
echo [backup] ERROR: %ERRMSG%
if defined CREATED_DEST powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%backup_cleanup.ps1" -Action remove
endlocal & exit /b 1
