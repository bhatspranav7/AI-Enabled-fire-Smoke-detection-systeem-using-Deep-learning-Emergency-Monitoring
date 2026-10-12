@echo off
REM Starts the full demo in three windows: backend+dashboard, sensor simulator, live inference.
REM Usage:  run_demo.bat              -> webcam
REM         run_demo.bat demo_media\images   -> cycle through sample images (no real fire needed)
REM         run_demo.bat path\to\video.mp4   -> video file
cd /d "%~dp0"
if not exist .venv (echo Run setup.bat first. & pause & exit /b 1)
set SRC=%~1
set SRCARG=
if not "%SRC%"=="" set SRCARG=--source "%SRC%"

start "Backend + Dashboard" cmd /k ".venv\Scripts\activate.bat && python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000"
timeout /t 4 /nobreak >nul
start "ESP32 Sensor Simulator" cmd /k ".venv\Scripts\activate.bat && python iot\sensor_simulator.py"
start "Live Inference" cmd /k ".venv\Scripts\activate.bat && python inference\run_live.py %SRCARG%"
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8000/
echo Demo started. Close the three windows to stop.
