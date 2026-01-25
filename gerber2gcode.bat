@echo off
REM Gerber to G-code converter wrapper for Windows
REM Usage: gerber2gcode.bat input.gtl [options]

python "%~dp0gerber_to_gcode.py" %*
