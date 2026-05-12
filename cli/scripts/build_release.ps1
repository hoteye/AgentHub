param(
    [ValidateSet("onedir", "onefile")]
    [string]$Mode = "onedir"
)

$ErrorActionPreference = "Stop"

$CliRoot = Split-Path -Parent $PSScriptRoot
Set-Location $CliRoot

python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt
python scripts/build_release.py --clean --mode $Mode
