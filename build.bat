@echo off
rem MomongaPet.exe build (output: dist\MomongaPet.exe)
chcp 65001 >nul
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -m pip install --quiet pyinstaller pyside6 pillow || exit /b 1
"%PY%" tools\make_icon.py || exit /b 1
set "ICON="
if exist build\icon.ico set "ICON=--icon build\icon.ico"
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name MomongaPet %ICON% --add-data "sprites;sprites" momongapet.py || exit /b 1
echo.
echo Done: dist\MomongaPet.exe
