@echo off
REM ============================================================
REM  Push updates to the existing GitHub repo (SR005/foresight).
REM  Use this after the first push, whenever files change.
REM  Streamlit Cloud auto-redeploys within ~1 minute.
REM ============================================================

cd /d "%~dp0"

echo.
echo  Committing and pushing changes...
git add -A
git commit -m "Update: fix forecast vs actual chart (show forecast + baseline)"
git push

echo.
echo  Done. Streamlit will redeploy automatically in about a minute.
echo  Refresh your dashboard tab to see the updated chart.
echo.
pause
