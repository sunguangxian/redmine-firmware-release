@echo off
cd /d "%~dp0"

if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -r requirements.txt -q

where npm >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  if exist frontend\package.json (
    echo Installing and building Vue frontend...
    cd frontend
    if not exist node_modules npm install
    npm run build
    cd ..
  )
) else (
  echo npm not found. Backend will start, but Vue frontend must be built manually for production mode.
)

echo Starting Redmine Release Tool API...
python main.py
