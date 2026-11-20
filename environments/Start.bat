@echo off
setlocal
cd /d "%~dp0.."
if defined SPASHINY_PYTHON (
  "%SPASHINY_PYTHON%" backend\runtime.py local %*
) else (
  python backend\runtime.py local %*
)
if errorlevel 1 (
  echo.
  echo SpaShiny did not start. Read the message above and the logs in your local SpaShiny data folder.
  echo Activate your SpaShiny Python environment, or set SPASHINY_PYTHON to its python.exe.
  pause
)
endlocal
