@echo off
REM One-time setup on Windows: creates a virtual environment and installs dependencies.
REM Usage: double-click or run  setup.bat  from the project folder.
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.10+ not found. Install from https://www.python.org/downloads/ and tick "Add to PATH". & pause & exit /b 1)
if not exist .venv (
    echo [setup] creating virtual environment...
    python -m venv .venv || (echo venv creation failed & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
echo [setup] upgrading pip...
python -m pip install --upgrade pip >nul
echo [setup] installing CPU-only PyTorch (smaller download than the default)...
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
echo [setup] installing project requirements...
pip install -r requirements.txt
if not exist .env copy .env.example .env >nul
echo.
echo [setup] done. Next: run_demo.bat   (or see README.md)
pause
