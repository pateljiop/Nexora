@echo off
setlocal
cd /d "%~dp0"

if not defined NEXORA_PORT set "NEXORA_PORT=8765"
powershell -NoProfile -Command "$p=$env:NEXORA_PORT; if ($p -notmatch '^\d{1,5}$') { exit 1 }; $n=[int]$p; if ($n -lt 1024 -or $n -gt 65535) { exit 1 }" >nul 2>nul
if errorlevel 1 (
  echo NEXORA_PORT must be a number between 1024 and 65535.
  pause
  exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
  start "Nexora Local Server" cmd /k py -3 server.py
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python was not found. Install Python 3.10+ and try again.
    pause
    exit /b 1
  )
  start "Nexora Local Server" cmd /k python server.py
)

echo Waiting for Nexora to become ready on port %NEXORA_PORT%...
for /L %%i in (1,1,30) do (
  powershell -NoProfile -Command "try { $health=Invoke-RestMethod 'http://127.0.0.1:%NEXORA_PORT%/api/health' -TimeoutSec 1; if ($health.status -eq 'ok' -and $health.storage -eq 'sqlite') { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>nul
  if not errorlevel 1 goto ready
  timeout /t 1 /nobreak >nul
)

echo Nexora did not respond within 30 seconds.
echo Check the server terminal for Python errors or a port conflict.
pause
exit /b 1

:ready
start "" http://127.0.0.1:%NEXORA_PORT%
endlocal
