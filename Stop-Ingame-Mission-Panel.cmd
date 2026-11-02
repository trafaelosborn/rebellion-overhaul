@echo off
cd /d "%~dp0"
python "%~dp0mission_inline.py" --stop
if errorlevel 1 pause
