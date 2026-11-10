@echo off
rem MomongaPet - run without console window
chcp 65001 >nul
cd /d "%~dp0"
set "PYW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw"
start "" "%PYW%" momongapet.py
