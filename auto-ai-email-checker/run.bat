@echo off
setlocal EnableDelayedExpansion
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

where ngrok >nul 2>&1
if errorlevel 1 (
  echo ngrok was not found on PATH. Install it to receive automatic email updates.
  echo The backend and frontend are still running.
) else (
  set "WEBHOOK_BASE_URL="
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do if /I "%%A"=="WEBHOOK_BASE_URL" set "WEBHOOK_BASE_URL=%%B"
  if defined WEBHOOK_BASE_URL (
    start "email-checker-ngrok" cmd /k "ngrok http http://127.0.0.1:8000 --url !WEBHOOK_BASE_URL!"
  ) else (
    start "email-checker-ngrok" cmd /k "ngrok http http://127.0.0.1:8000"
  )
  echo ngrok started for port 8000. Check http://127.0.0.1:4040 for its public URL.
  echo Configured webhook URL: !WEBHOOK_BASE_URL!
)

echo Close the opened windows to stop the servers and tunnel.
endlocal
