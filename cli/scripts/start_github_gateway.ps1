param(
    [string]$PythonExe = "",
    [string]$Host = "127.0.0.1",
    [int]$Port = 8787,
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
    Write-Host "Starting GitHub Phase 1 gateway server"
    Write-Host "  Repo Root: $ProjectRoot"
    Write-Host "  Python: $PythonExe"
    Write-Host "  Listen: $Host`:$Port"
    Write-Host "  Webhook Path: /webhooks/github"
    if ($env:GITHUB_WEBHOOK_SECRET) {
        Write-Host "  Signature Verification: enabled"
    }
    else {
        Write-Host "  Signature Verification: disabled"
    }
}

Set-Location $ProjectRoot
& $PythonExe -m cli.agent_cli.gateway_api.github_http_server --host $Host --port $Port
exit $LASTEXITCODE
