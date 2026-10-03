@echo off
setlocal
cd /d "%~dp0"

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

echo Waiting for Nexora to become ready...
for /L %%i in (1,1,30) do (
  powershell -NoProfile -Command "try { Invoke-RestMethod 'http://127.0.0.1:8765/api/health' -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
  if not errorlevel 1 goto ready
  timeout /t 1 /nobreak >nul
)

echo Nexora did not respond within 30 seconds.
echo Check the server terminal for Python errors or a port conflict.
pause
exit /b 1

:ready
start "" http://127.0.0.1:8765
endlocal
