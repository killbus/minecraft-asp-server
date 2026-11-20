@echo on
@setlocal
@set "BACKUP_DEBUG=1"
@call "%~dp0backup.cmd" %*
@endlocal & exit /b %errorlevel%
