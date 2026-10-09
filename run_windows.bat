@echo off
REM Run noScribeEdit from source on Windows (no build).
REM   run_windows.bat            -> start the editor
REM   run_windows.bat FILE.html  -> start the editor and open FILE.html
REM The first run creates .venv and installs the requirements; later runs start right away.
setlocal
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "REQ_FILE=environments\requirements.txt"

if exist "%VENV_DIR%\Scripts\python.exe" goto :run

REM --- First run: pick a Python the pinned dependencies support (av<13 has no wheels for 3.13)
set "PY_CMD="
for %%v in (3.12 3.11 3.10) do (
    if not defined PY_CMD (
        py -%%v -c "import sys" >nul 2>&1 && set "PY_CMD=py -%%v"
    )
)
if not defined PY_CMD (
    python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)" >nul 2>&1 && set "PY_CMD=python"
)
if not defined PY_CMD (
    echo.
    echo ERROR: Python 3.10, 3.11 or 3.12 was not found.
    echo Install Python 3.12 from https://www.python.org/downloads/windows/ and tick "py launcher".
    pause
    exit /b 1
)
echo Using interpreter: %PY_CMD%
echo Creating virtual environment in %VENV_DIR% ...
%PY_CMD% -m venv "%VENV_DIR%" || (pause & exit /b 1)
call "%VENV_DIR%\Scripts\activate.bat" || (pause & exit /b 1)
echo Installing requirements (first run only) ...
python -m pip install --upgrade pip --quiet
python -m pip install -r "%REQ_FILE%" || (
    echo.
    echo ERROR: pip install failed. See messages above.
    pause
    exit /b 1
)
goto :start

:run
call "%VENV_DIR%\Scripts\activate.bat" || (pause & exit /b 1)

:start
if "%~1"=="" (
    python noScribeEdit.py
) else (
    python noScribeEdit.py "%~1"
)
if errorlevel 1 (
    echo.
    echo noScribeEdit ended with an error. See messages above.
    pause
)
endlocal
