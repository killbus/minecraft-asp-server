@echo off
REM ============================================================
REM  AdvancedSlimePaper 26.2 - start script (Windows)
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
setlocal
cd /d "%~dp0..\server"

set "JAVA=D:\Applications\Scoop\apps\temurin25-jdk\current\bin\java.exe"

if not exist "%JAVA%" (
    echo [start] ERROR: Java 25 not found at:
    echo         %JAVA%
    echo         Install a JDK 25+ or fix the JAVA variable above.
    exit /b 1
)

if not exist "asp-server.jar" (
    echo [start] ERROR: asp-server.jar not found in %cd%
    exit /b 1
)

REM --- pre-start backup (backup.cmd changes cwd, so restore it after) ---
if not "%ASP_SKIP_BACKUP%"=="1" (
    if not defined BACKUP_MIN_INTERVAL set "BACKUP_MIN_INTERVAL=60"
    call "%~dp0backup.cmd"
    if errorlevel 1 echo [start] WARN: pre-start backup failed; starting the server anyway.
    cd /d "%~dp0..\server"
)

REM -Xmx / -Xms: tune to your RAM. Bedrock+Java mixed load is heavier
REM than Java-only. 4G heap is a sane default for a small SMP.
"%JAVA%" -Xms2G -Xmx4G -XX:+UseG1GC -jar asp-server.jar
set "EXITCODE=%errorlevel%"
echo.
echo [start] Server exited (code %EXITCODE%).

if /i "%~1"=="-pause" pause
endlocal & exit /b %EXITCODE%
