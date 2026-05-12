@echo off
setlocal

cd /d "%~dp0\.."

set BUILD_MODE=%~1
if /I "%BUILD_MODE%"=="" set BUILD_MODE=onedir

echo [1/3] Installing runtime dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo [2/3] Installing packaging dependencies...
python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1

echo [3/3] Building portable Windows release...
python scripts\build_release.py --clean --mode %BUILD_MODE%
if errorlevel 1 exit /b 1

echo Build finished.
