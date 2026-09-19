@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"

rem ---------------------------------------------------------------------------
rem PERSONAL EDITION launcher.
rem This starts YOUR copy from the source in this folder. A source run is the
rem Personal edition: it has every Friends feature, and it has no 5p shared-key
rem limit. The API key choice is unchanged - the bundled shared key, or your own
rem OpenRouter key. The Friends ZIP keeps its 5p limit; only this folder is
rem personal. Startup failures keep the error visible; an older EXE may lack
rem these features and must not silently replace the Personal edition.
rem ---------------------------------------------------------------------------

if not exist ".venv\Scripts\python.exe" (
  py -3.13 -m venv .venv
  if errorlevel 1 goto :python_missing
)
if not exist ".venv\Scripts\python.exe" goto :python_missing
if not exist ".venv\installed-v1.txt" (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto :failed
  echo ready>.venv\installed-v1.txt
)
.venv\Scripts\python.exe entry.py %*
if errorlevel 1 goto :failed
exit /b 0

:python_missing
echo Python 3.13 is required to run this Personal edition from source.
echo Install Python 3.13 with the Windows Python launcher, then reopen this BAT.
pause
exit /b 1

:failed
echo.
echo Guigu Mod Translator stopped. See the error above.
pause
exit /b 1
