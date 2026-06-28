@echo off
REM ============================================================
REM  Reinicia el servidor Apolo CAD (doble clic para ejecutar).
REM  1) Detiene cualquier uvicorn de apolo que este corriendo.
REM  2) Arranca uno nuevo con --reload en http://127.0.0.1:8000
REM     (la ventana queda abierta mostrando el log; Ctrl+C detiene).
REM ============================================================
echo.
echo == Reiniciando Genix Apolo CAD ==
echo Deteniendo instancia previa...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | Where-Object { $_.CommandLine -like '*uvicorn*apolo.api.main*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 2 >nul
echo Arrancando en http://127.0.0.1:8000  (Ctrl+C para detener)
echo.
cd /d "%~dp0core"
"%~dp0.venv\Scripts\python.exe" -m uvicorn apolo.api.main:app --host 127.0.0.1 --port 8000 --reload
pause
