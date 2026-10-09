@echo off
REM Build or run noScribeEdit on Windows.
REM   build_windows.bat          -> create venv, install requirements, build dist\noScribeEdit\noScribeEdit.exe
REM   build_windows.bat run      -> run the editor from source inside the venv (no build)
REM   build_windows.bat run FILE -> run the editor and open FILE
REM   build_windows.bat clean    -> remove build\ and dist\
setlocal
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "SPEC_FILE=noScribeEdit_win.spec"
set "REQ_FILE=environments\requirements.txt"

if /i "%~1"=="clean" (
    echo Removing build\ and dist\ ...
    if exist build rmdir /s /q build
    if exist dist rmdir /s /q dist
    echo Done.
    goto :eof
)

REM --- Pick a Python the pinned dependencies support (av<13 has no wheels for 3.13)
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
    exit /b 1
)
echo Using interpreter: %PY_CMD%

REM --- Virtual environment
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating virtual environment in %VENV_DIR% ...
    %PY_CMD% -m venv "%VENV_DIR%" || exit /b 1
)
call "%VENV_DIR%\Scripts\activate.bat" || exit /b 1

echo Installing requirements ...
python -m pip install --upgrade pip --quiet
python -m pip install -r "%REQ_FILE%" || (
    echo.
    echo ERROR: pip install failed. See messages above.
    exit /b 1
)

if /i "%~1"=="run" (
    echo Starting noScribeEdit from source ...
    if "%~2"=="" (
        python noScribeEdit.py
    ) else (
        python noScribeEdit.py "%~2"
    )
    goto :eof
)

REM --- Build with PyInstaller
echo Building with PyInstaller ...
python -m PyInstaller --noconfirm --clean "%SPEC_FILE%" || (
    echo.
    echo ERROR: PyInstaller failed. See messages above.
    exit /b 1
)

echo.
if exist "dist\noScribeEdit\noScribeEdit.exe" (
    echo Build finished: %CD%\dist\noScribeEdit\noScribeEdit.exe
) else (
    echo Build finished but the executable was not found in dist\noScribeEdit\.
)
endlocal
