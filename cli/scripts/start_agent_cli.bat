@echo off
chcp 65001 >nul 2>nul
wsl.exe -d Ubuntu --cd /home/lyc/project/AgentHub -e /opt/miniconda3/bin/python -m cli.agent_cli
