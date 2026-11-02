@echo off
cd /d "%~dp0"
where pythonw.exe >nul 2>nul
if errorlevel 1 goto console
start "" pythonw.exe "%~dp0mission_planner.py"
exit /b
:console
python "%~dp0mission_planner.py"
if errorlevel 1 pause
