@echo off
chcp 65001 >/dev/null 2>/dev/null
echo DP0=%~dp0
echo TRYING pushd...
pushd "%~dp0"
echo PUSHLEVEL=%ERRORLEVEL%
echo CD=%CD%
cd ..\..
echo CD2=%CD%
dir cli\agent_cli\__main__.py
popd
