@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0bootstrap.py" %*
    goto finished
)
where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0bootstrap.py" %*
    goto finished
)
echo Python was not found. Install desktop Python 3.10 or newer with Tcl/Tk.
echo See README.md for Windows download and installation steps.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1
:finished
if errorlevel 1 (
    echo See the error above and README.md. Keep this window open to read the details.
    pause
    exit /b 1
)
exit /b 0
