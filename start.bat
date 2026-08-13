@echo off
cd /d %~dp0
if not exist .venv (
  echo Elso inditas: virtualis kornyezet letrehozasa...
  py -3 -m venv .venv || goto :error
  .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt || goto :error
)
.venv\Scripts\python.exe main.py %*
goto :eof

:error
echo.
echo Hiba tortent a telepites soran. Ellenorizd, hogy a Python telepitve van-e (py -3).
pause
