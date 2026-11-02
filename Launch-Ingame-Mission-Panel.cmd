@echo off
cd /d "%~dp0"
where pythonw.exe >nul 2>nul
if errorlevel 1 goto console
start "" pythonw.exe "%~dp0mission_inline.py"
exit /b
:console
python "%~dp0mission_inline.py"
if errorlevel 1 pause
