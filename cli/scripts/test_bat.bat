@echo off
chcp 65001 >/dev/null 2>/dev/null
set "SCRIPT_DIR=%~dp0"
echo [1] SCRIPT_DIR=%SCRIPT_DIR%
set "CLI_DIR=%SCRIPT_DIR:~0,-1%"
echo [2] CLI_DIR=%CLI_DIR%
for %%I in ("%CLI_DIR%") do set "PROJECT_PARENT=%%~dpI"
echo [3] PROJECT_PARENT=%PROJECT_PARENT%
set "PROJECT_ROOT=%PROJECT_PARENT:~0,-1%"
echo [4] PROJECT_ROOT=%PROJECT_ROOT%
for %%I in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~dpI"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
echo [5] FINAL PROJECT_ROOT=%PROJECT_ROOT%
pushd "%PROJECT_ROOT%"
echo [6] pushd ERR=%ERRORLEVEL%
echo [7] CD=%CD%
python -c "import cli.agent_cli; print('MODULE OK')" 2>&1
popd
