@echo off
REM ============================================================
REM  Paper 26.2 - start script (Windows)
REM  Starts the server in the sibling server/ directory.
REM
REM  Before launching, backs up the previous session's world. The
REM  server is stopped at this point by definition, so the snapshot
REM  is consistent - this is the natural backup point for a server
REM  that is not running 24/7.
REM  The backup is skipped when a complete one is younger than
REM  BACKUP_MIN_INTERVAL (60 min) so restart loops do not push older
REM  backups out of the retention window. Set ASP_SKIP_BACKUP=1 to
REM  start without backing up at all.
REM
REM  Usage:
REM    scripts\start.cmd               foreground, in the current terminal
REM    scripts\start.cmd -pause        extra: pause on exit (double-click use)
REM  Requires: Java 25 (MC 26.1+ refuses older JDKs).
REM ============================================================
setlocal EnableExtensions DisableDelayedExpansion
set "SCRIPT_DIR=%~dp0"
set "WORLD_NAME="
set "PAUSE_ON_EXIT="
:parse_args
set "ARGUMENT=%~1"
if defined ARGUMENT goto :parse_argument
if "%1"=="" goto :args_done
goto :usage
:parse_argument
if /i "%~1"=="-pause" (
    set "PAUSE_ON_EXIT=1"
    shift
    goto :parse_args
)
if not "%~1"=="--world" goto :usage
if defined WORLD_NAME goto :usage
set "WORLD_NAME=%~2"
powershell -NoProfile -Command "if ($env:WORLD_NAME -cmatch '\A[A-Za-z0-9_-]+\z') { exit 0 } else { exit 2 }"
if errorlevel 1 goto :usage
shift
shift
goto :parse_args

:usage
echo [start] ERROR: usage: scripts\start.cmd [--world NAME] [-pause] 1>&2
echo [start] NAME must use ASCII letters, digits, _ or -. 1>&2
exit /b 2

:args_done
cd /d "%SCRIPT_DIR%..\server" || exit /b 1
set "WORLD_ARGS="
if not defined WORLD_NAME goto :pack_setup
powershell -NoProfile -Command "$world=Join-Path (Get-Location) $env:WORLD_NAME; $level=Join-Path $world 'level.dat'; if (!(Test-Path -LiteralPath $level -PathType Leaf)) { exit 2 }; foreach ($path in @($world,$level)) { if ((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { exit 2 } }"
if errorlevel 1 goto :invalid_world
set "WORLD_ARGS=--world %WORLD_NAME%"

:pack_setup
set "CONFIG_ARGS="
powershell -NoProfile -Command "try { $settings=Get-Item -LiteralPath '..\settings' -Force -ErrorAction Stop; if ($settings.Attributes -band [IO.FileAttributes]::ReparsePoint) { exit 0 }; if (!$settings.PSIsContainer) { throw 'settings must be a directory' }; foreach ($name in @('minecraft-server.json','resource-packs.json')) { try { $null=Get-Item -LiteralPath (Join-Path $settings.FullName $name) -Force -ErrorAction Stop; exit 0 } catch [System.Management.Automation.ItemNotFoundException] {} }; exit 1 } catch [System.Management.Automation.ItemNotFoundException] { exit 1 } catch { Write-Error $_; exit 2 }"
if errorlevel 2 goto :invalid_pack_policy
if errorlevel 1 goto :java_setup
where python >nul 2>nul
if errorlevel 1 (
    echo [start] ERROR: python is required to validate settings\minecraft-server.json and legacy pack settings 1>&2
    exit /b 2
)
set "PACK_ARGS="
if defined WORLD_NAME set "PACK_ARGS=--world=%WORLD_NAME%"
python -B "%SCRIPT_DIR%select_resource_pack.py" %PACK_ARGS%
set "PACK_STATUS=%errorlevel%"
if "%PACK_STATUS%"=="3" goto :java_setup
if not "%PACK_STATUS%"=="0" goto :invalid_pack_policy
set "CONFIG_ARGS=--config ..\.tmp\startup\server.properties"

:java_setup
if not defined JAVA set "JAVA=D:\Applications\Scoop\apps\temurin25-jdk\current\bin\java.exe"

if not exist "%JAVA%" (
    echo [start] ERROR: Java 25 not found at:
    echo         %JAVA%
    echo         Install a JDK 25+ or fix the JAVA variable above.
    exit /b 1
)

if not exist "paper-server.jar" (
    echo [start] ERROR: paper-server.jar not found in %cd%
    exit /b 1
)

REM --- pre-start backup (backup.cmd changes cwd, so restore it after) ---
if not "%ASP_SKIP_BACKUP%"=="1" (
    if not defined BACKUP_MIN_INTERVAL set "BACKUP_MIN_INTERVAL=60"
    call "%SCRIPT_DIR%backup.cmd"
    if errorlevel 1 echo [start] WARN: pre-start backup failed; starting the server anyway.
    cd /d "%SCRIPT_DIR%..\server"
)

REM -Xmx / -Xms: tune to your RAM. Bedrock+Java mixed load is heavier
REM than Java-only. 4G heap is a sane default for a small SMP.
"%JAVA%" -Xms2G -Xmx4G -XX:+UseG1GC -Dpaper.disableStartupVersionCheck=true -jar paper-server.jar %WORLD_ARGS% %CONFIG_ARGS%
set "EXITCODE=%errorlevel%"
echo.
echo [start] Server exited (code %EXITCODE%).

if defined PAUSE_ON_EXIT pause
endlocal & exit /b %EXITCODE%

:invalid_world
echo [start] ERROR: --world requires an existing native save at server\%WORLD_NAME%\level.dat ^(no links^) 1>&2
exit /b 2

:invalid_pack_policy
echo [start] ERROR: cannot select resource pack; check settings\minecraft-server.json and the preceding error. 1>&2
exit /b 2
