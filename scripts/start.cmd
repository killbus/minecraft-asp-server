@echo off
REM ============================================================
REM  AdvancedSlimePaper 26.2 - start script (Windows)
REM  Starts the server in the sibling server/ directory.
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

REM -Xmx / -Xms: tune to your RAM. Bedrock+Java mixed load is heavier
REM than Java-only. 4G heap is a sane default for a small SMP.
"%JAVA%" -Xms2G -Xmx4G -XX:+UseG1GC -jar asp-server.jar
set "EXITCODE=%errorlevel%"
echo.
echo [start] Server exited (code %EXITCODE%).

if /i "%~1"=="-pause" pause
endlocal & exit /b %EXITCODE%
