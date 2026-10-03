@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  start "Nexora Local Server" cmd /k py -3 server.py
) else (
  start "Nexora Local Server" cmd /k python server.py
)
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765
endlocal
