@echo off
setlocal
cd /d "%~dp0"

python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :install
)
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    goto :install
)
echo Python 3.11+ is required: https://www.python.org/downloads/
exit /b 1

:install
if not exist ".venv\Scripts\python.exe" (
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 (
    echo The existing .venv requires Python 3.11 or newer.
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install .
if errorlevel 1 exit /b 1

where ffmpeg >nul 2>&1
if errorlevel 1 echo Warning: ffmpeg is missing. Install FFmpeg and add it to PATH.
where ffprobe >nul 2>&1
if errorlevel 1 echo Warning: ffprobe is missing. Install FFmpeg and add it to PATH.
echo.
echo Installed. Run from this directory:
echo   .venv\Scripts\mediadhob.exe
echo For local transcription: .venv\Scripts\python.exe -m pip install ".[captions]"
exit /b 0
