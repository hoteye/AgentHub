param(
    [string]$PythonExe = "",
    [string]$Host = "127.0.0.1",
    [int]$Port = 8787,
    [string]$BasePath = "/gui",
    [switch]$ShowBanner
)

$ErrorActionPreference = "Stop"

$CliRoot = Split-Path -Parent $PSScriptRoot
$ProjectRoot = Split-Path -Parent $CliRoot

if (-not $PythonExe) {
    $candidates = @(
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
        (Join-Path $CliRoot ".venv\Scripts\python.exe"),
        "python"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -eq "python") {
            $PythonExe = $candidate
            break
        }
        if (Test-Path $candidate) {
            $PythonExe = $candidate
            break
        }
    }
}

if (-not $PythonExe) {
    throw "No usable Python executable found."
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if ($ShowBanner) {
    Write-Host "Starting EasyClaw GUI bridge server"
    Write-Host "  Repo Root: $ProjectRoot"
    Write-Host "  Python: $PythonExe"
    Write-Host "  Listen: $Host`:$Port"
    Write-Host "  Request Path: $BasePath/requests"
    Write-Host "  Events Path: $BasePath/events"
    Write-Host "  Health Path: $BasePath/health"
}

Set-Location $ProjectRoot
& $PythonExe -m cli.agent_cli.gateway_api.gui_http_server --host $Host --port $Port --base-path $BasePath
exit $LASTEXITCODE
