@echo on
REM ============================================================
REM  ASP server backup (Windows)
REM
REM  Usage:  scripts\backup.cmd [SERVER_DIR]
REM  Default SERVER_DIR: ..\server (relative to this script)
REM
REM  Scope (see docs/ASP-SOP.md section 1 - not regenerable):
REM    world/ + whitelist/ban/usercache/ops json + server config
REM    + config/ (Paper) + per-plugin config dirs (jars excluded)
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
REM    BACKUP_TARGETS        replaces the target list below
REM    BACKUP_ROOT           same, kept for older callers (single target)
REM    KEEP                  complete backups kept per target (default 5)
REM    BACKUP_MIN_INTERVAL   skip when every target already has a complete
REM                          backup younger than this many minutes
REM                          (default 0 = never skip)
REM    BACKUP_REQUIRE_ALL=1  a failed mirror fails the run (default 0)
REM    ALLOW_ONLINE=1        proceed even though the server is running
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

REM ============================================================
REM  BACKUP TARGETS  (edit this block)
REM ============================================================
REM  Semicolon-separated list, e.g.
REM      ..\backups;E:\MC-Backups
REM  A relative path resolves against this script's directory; an
REM  absolute path (D:\..., \\server\share) is used as-is. Paths may
REM  contain spaces, but not semicolons.
REM
REM  The FIRST entry is the primary target: if it fails, the whole run
REM  fails. Every later entry is a mirror: a mirror failure prints a
REM  warning but the run still succeeds, because an unplugged USB disk
REM  must not stop the local backup from being taken. Set
REM  BACKUP_REQUIRE_ALL=1 to make any mirror failure fatal.
if not defined BACKUP_TARGETS set "BACKUP_TARGETS=..\backups"
if defined BACKUP_ROOT set "BACKUP_TARGETS=%BACKUP_ROOT%"

if not defined KEEP set "KEEP=5"
if not defined BACKUP_MIN_INTERVAL set "BACKUP_MIN_INTERVAL=0"
if not defined BACKUP_REQUIRE_ALL set "BACKUP_REQUIRE_ALL=0"
if "%~1"=="" (set "SERVER_DIR=%~dp0..\server") else (set "SERVER_DIR=%~1")
set "ERRMSG="

for /f %%i in ('powershell -NoProfile -Command "[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')"') do set "TS=%%i"

REM Fail unless a path below explicitly succeeds. `exit /b` cannot be used
REM inside a parenthesised block here: when the enclosing block has more
REM commands after it, cmd loses the exit code (verified on this build), so
REM every early exit is `goto :finish` and the code travels in RESULT.
set "RESULT=1"

REM --- preflight ---
if not exist "%SERVER_DIR%\asp-server.jar" (
    echo [backup] ERROR: not a server dir: %SERVER_DIR% ^(asp-server.jar missing^)
    goto :finish
)

REM --- resolve the target list into TGT_1 .. TGT_N ---
REM `for /f` with delims=; keeps spaces inside a path; the second loop
REM only trims the leading space people habitually put after the ';'.
set "TGT_N=0"
set "REST=%BACKUP_TARGETS%"
:parse_next
if not defined REST goto :parse_done
set "T="
set "NEXT="
for /f "tokens=1* delims=;" %%a in ("%REST%") do (
    set "T=%%a"
    set "NEXT=%%b"
)
set "REST=%NEXT%"
if not defined T goto :parse_next
for /f "tokens=* delims= " %%p in ("%T%") do set "T=%%p"
if not defined T goto :parse_next
if "%T:~0,2%"=="\\" goto :parse_abs
if "%T:~1,1%"==":" goto :parse_abs
set "T=%~dp0%T%"
:parse_abs
set /a TGT_N+=1
set "TGT_!TGT_N!=%T%"
goto :parse_next
:parse_done

if %TGT_N% equ 0 (
    echo [backup] ERROR: no backup targets configured ^(BACKUP_TARGETS is empty^)
    goto :finish
)

REM Refuse a torn snapshot: the ASP server must be stopped while we copy.
REM Match the real launch shape (`java ... -jar ...\asp-server.jar`) so an
REM unrelated process that merely mentions the file name is not a false hit.
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process -Filter 'Name=''java.exe''' | Where-Object { $_.CommandLine -match '-jar\s+.*asp-server\.jar' }) { exit 2 } else { exit 0 }"
if errorlevel 2 if not "%ALLOW_ONLINE%"=="1" (
    echo [backup] ERROR: the ASP server is running; stop it first ^(or set ALLOW_ONLINE=1^)
    goto :finish
)
if errorlevel 2 echo [backup] WARN: ALLOW_ONLINE=1 - snapshot may be inconsistent

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
        if exist "!TGT_%%i!\%TS%" rmdir /s /q "!TGT_%%i!\%TS%"
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

mkdir "%DEST%" 2>nul
if not exist "%DEST%" set "ERRMSG=cannot create %DEST%"
if defined ERRMSG goto :dt_fail

REM --- world: mirror, runtime artifacts excluded ---
REM world/ is a tree, not just level.dat: on this build level.dat is a
REM slim header and the real state lives in data/ and dimensions/*/data/.
robocopy "%SERVER_DIR%\world" "%DEST%\world" /MIR /XF session.lock level.dat_old /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 set "ERRMSG=world copy failed (robocopy exit !errorlevel!)"
if defined ERRMSG goto :dt_fail

REM --- player files + server-level config ---
for %%f in (whitelist.json ops.json banned-ips.json banned-players.json usercache.json server.properties eula.txt bukkit.yml spigot.yml commands.yml server-icon.png) do copy /Y "%SERVER_DIR%\%%f" "%DEST%\" >nul 2>nul

REM --- Paper config dir (paper-global.yml, paper-world-defaults.yml) ---
if exist "%SERVER_DIR%\config" (
    robocopy "%SERVER_DIR%\config" "%DEST%\config" /MIR /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 set "ERRMSG=config copy failed (robocopy exit !errorlevel!)"
)
if defined ERRMSG goto :dt_fail

REM --- plugin dirs: config + data, jars excluded ---
for /d %%d in ("%SERVER_DIR%\plugins\*") do (
    robocopy "%%~d" "%DEST%\plugins\%%~nxd" /MIR /XF *.jar /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 if not defined ERRMSG set "ERRMSG=plugin copy failed: %%~nxd"
)
if defined ERRMSG goto :dt_fail
copy /Y "%SERVER_DIR%\plugins\*.yml" "%DEST%\plugins\" >nul 2>nul

REM --- manifest: hash every backed-up file (world included) ---
powershell -NoProfile -Command "$d=(Resolve-Path -LiteralPath $env:DEST).Path; $o=@('# ASP backup ' + $env:TS); $sha=[System.Security.Cryptography.SHA256]::Create(); $fs=[System.IO.Directory]::GetFiles($d,'*',[System.IO.SearchOption]::AllDirectories); [Array]::Sort($fs,[System.StringComparer]::Ordinal); foreach ($f in $fs) { if ([System.IO.Path]::GetFileName($f) -ne 'MANIFEST.txt') { $s=[System.IO.File]::OpenRead($f); $h=([System.BitConverter]::ToString($sha.ComputeHash($s)) -replace '-','').ToLower(); $s.Dispose(); $rel=$f.Substring($d.Length+1).Replace([char]92,'/'); $o += ('{0}  ./{1}' -f $h, $rel) } }; [System.IO.File]::WriteAllText((Join-Path $d 'MANIFEST.txt'), (($o -join [char]10) + [char]10), [System.Text.Encoding]::ASCII)"
if errorlevel 1 set "ERRMSG=manifest generation failed"
if defined ERRMSG goto :dt_fail
if not exist "%DEST%\MANIFEST.txt" set "ERRMSG=manifest file missing after generation"
if defined ERRMSG goto :dt_fail

REM --- completion marker: written last, only for a fully written backup ---
> "%DEST%\COMPLETE" echo %TS%
if not exist "%DEST%\COMPLETE" set "ERRMSG=cannot write COMPLETE marker"
if defined ERRMSG goto :dt_fail

REM --- prune THIS target: keep its newest %KEEP% complete backups ---
REM Only directories named like our own timestamps are touched, so a
REM target may point at a shared folder without us deleting its contents.
set /a n=0
for /f "delims=" %%d in ('dir /b /ad /o-n "%TDIR%" 2^>nul') do (
    set "OURS="
    echo %%d| findstr /r /c:"^[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]$" >nul && set "OURS=1"
    if defined OURS (
        if exist "%TDIR%\%%d\COMPLETE" (
            set /a n+=1
            if !n! gtr %KEEP% rmdir /s /q "%TDIR%\%%d"
        ) else (
            rmdir /s /q "%TDIR%\%%d"
        )
    )
)

endlocal & exit /b 0

:dt_fail
echo [backup] ERROR: %ERRMSG%
rmdir /s /q "%DEST%" 2>nul
endlocal & exit /b 1
