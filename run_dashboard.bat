@echo off
REM ============================================================
REM  Project FORESIGHT - launch the Streamlit planning dashboard
REM  Double-click this file. It installs what's needed (first
REM  time only) and opens the dashboard in your browser.
REM ============================================================

cd /d "%~dp0"

echo.
echo  Project FORESIGHT - starting dashboard...
echo  Folder: %cd%
echo.

REM Install dependencies (quiet). Requires Python 3.9+ on PATH.
python -m pip install --quiet -r requirements.txt

REM If model outputs are missing, build them once from the raw data.
if not exist "data\processed\forecast.csv" (
    echo  First run - building model outputs, please wait...
    python src\run_all.py
)

echo.
echo  Opening http://localhost:8501  (press Ctrl+C in this window to stop)
echo.

python -m streamlit run app\streamlit_app.py

pause
