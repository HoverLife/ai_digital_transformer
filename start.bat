@echo off
REM One-command launcher for Windows: starts containers, waits, opens the site.
setlocal
set URL=http://localhost:8000

echo [*] Starting services (docker compose up)...
docker compose up -d --build
if errorlevel 1 (
  echo [!] docker compose failed. Make sure Docker Desktop is running.
  pause
  exit /b 1
)

echo [*] Waiting for %URL% ...
set /a tries=0
:wait
curl -fs %URL%/api/health >nul 2>&1
if not errorlevel 1 goto ready
set /a tries+=1
if %tries% GEQ 60 goto ready
timeout /t 2 >nul
goto wait

:ready
echo [*] Opening %URL% in browser...
start "" %URL%
echo [*] Done. URL: %URL%   ^|  Stop: docker compose down
docker compose logs -f app
