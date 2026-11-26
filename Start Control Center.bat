@echo off
rem Double-click to open the AppShare Control Center (it turns the server on/off).
cd /d "%~dp0"
python -m launcher %*
if errorlevel 1 pause
