@echo off
chcp 65001 >/dev/null 2>/dev/null
echo [1] DP0=%~dp0
echo [2] Trying pushd to DP0...
pushd "%~dp0"
echo [3] pushd ERR=%ERRORLEVEL%
echo [4] CD=%CD%
echo [5] Trying cd ..\..
cd ..\..
echo [6] CD=%CD%
echo [7] Checking module...
python -c "import cli.agent_cli; print('MODULE OK')" 2>&1
echo [8] Done
popd
