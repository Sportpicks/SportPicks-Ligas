@echo off
cd /d "%~dp0"
start "" cmd /k "cd /d %~dp0 && echo Listo, ya estas en SportPicks-Ligas && git status"
