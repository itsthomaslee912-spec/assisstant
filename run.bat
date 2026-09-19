@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo Created .env from .env.example — fill in your API keys before connecting mailboxes.
  )
)

echo Starting AI Auto-Email Checker...
echo   Backend:  http://127.0.0.1:8000
echo   Frontend: http://127.0.0.1:5173
echo.

start "email-checker-backend" cmd /k "%~dp0scripts\run-backend.bat"
timeout /t 2 /nobreak >nul
start "email-checker-frontend" cmd /k "%~dp0scripts\run-frontend.bat"

echo Both windows opened. Close those windows to stop the servers.
endlocal
