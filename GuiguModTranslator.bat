@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
if exist "GuiguModTranslator.exe" (
  start "" "GuiguModTranslator.exe" %*
  exit /b 0
)
if not exist ".venv\Scripts\python.exe" (
  py -3.13 -m venv .venv
  if errorlevel 1 goto :failed
)
if not exist ".venv\installed-v1.txt" (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto :failed
  echo ready>.venv\installed-v1.txt
)
.venv\Scripts\python.exe entry.py %*
if errorlevel 1 goto :failed
exit /b 0
:failed
echo.
echo Guigu Mod Translator stopped. See the error above.
pause
exit /b 1
