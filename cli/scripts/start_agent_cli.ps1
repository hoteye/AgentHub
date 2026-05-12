param(
    [string]$PythonExe = "python",
    [int]$Width = 140,
    [int]$Height = 42,
    [switch]$ResizeWindow,
    [switch]$ShowBanner,
    [switch]$SplitPane
)

$ErrorActionPreference = "Stop"

$StartupCwd = (Get-Location).ProviderPath
if (-not $StartupCwd) {
    $StartupCwd = (Get-Location).Path
}

$CliRoot = Split-Path -Parent $PSScriptRoot
$ProjectRoot = Split-Path -Parent $CliRoot

$env:AGENTHUB_STARTUP_CWD = $StartupCwd
$env:AGENTHUB_STARTUP_CWD_LAUNCHER_ACTIVE = "1"
$env:AGENTHUB_STARTUP_CWD_SOURCE = "launcher"
if (-not $env:AGENTHUB_PREVIEW_WORKSPACE) {
    $env:AGENTHUB_PREVIEW_WORKSPACE = $env:AGENTHUB_STARTUP_CWD
}

Set-Location $ProjectRoot

try {
    chcp 65001 > $null
}
catch {
}

try {
    [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
}
catch {
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

try {
    $Host.UI.RawUI.WindowTitle = "AgentHub CLI"
}
catch {
}

if ($ResizeWindow) {
    try {
        $raw = $Host.UI.RawUI
        $maxSize = $raw.MaxPhysicalWindowSize

        $bufferSize = $raw.BufferSize
        if ($bufferSize.Width -lt $Width) {
            $bufferSize.Width = $Width
        }
        if ($bufferSize.Height -lt 4000) {
            $bufferSize.Height = 4000
        }
        $raw.BufferSize = $bufferSize

        $windowSize = $raw.WindowSize
        $windowSize.Width = [Math]::Min($Width, $maxSize.Width)
        $windowSize.Height = [Math]::Min($Height, $maxSize.Height)
        $raw.WindowSize = $windowSize
    }
    catch {
        if ($ShowBanner) {
            Write-Host "Window sizing skipped: $($_.Exception.Message)"
        }
    }
}

if ($ShowBanner) {
    Write-Host "Starting AgentHub CLI"
    if ($ResizeWindow) {
        Write-Host "  Size: ${Width}x${Height}"
    }
    Write-Host "  Keys: Enter=Send Ctrl+J=Newline F5=Provider F6=Tools F8=Paste F9=Send Ctrl+L=Clear Ctrl+C=Quit"
    Write-Host "  Recommended first commands: /provider, /plugins, /tools"
}

if ($SplitPane) {
    try {
        $wtSession = $env:WT_SESSION
        if (-not $wtSession) {
            if ($ShowBanner) {
                Write-Host "SplitPane: WT_SESSION not set, not running inside Windows Terminal. Skipping split."
            }
        }
        else {
            $wtExe = $null
            $localAppData = $env:LOCALAPPDATA
            if ($localAppData) {
                $candidate = Join-Path $localAppData "Microsoft\WindowsApps\wt.exe"
                if (Test-Path $candidate) {
                    $wtExe = $candidate
                }
            }
            if (-not $wtExe) {
                $found = Get-Command wt.exe -ErrorAction SilentlyContinue
                if ($found) { $wtExe = $found.Source }
            }
            if (-not $wtExe) {
                if ($ShowBanner) {
                    Write-Host "SplitPane: wt.exe not found. Install Windows Terminal for split-pane support."
                }
            }
            else {
                $previewTitle = "AgentHub Preview"
                Start-Process -FilePath $wtExe -ArgumentList "split-pane","-V","-s","0.5","cmd","/k","title $previewTitle" -NoNewWindow
                if ($ShowBanner) {
                    Write-Host "SplitPane: opened right-side preview pane in Windows Terminal."
                }
            }
        }
    }
    catch {
        if ($ShowBanner) {
            Write-Host "SplitPane: skipped due to error: $($_.Exception.Message)"
        }
    }
}

& $PythonExe -m cli.agent_cli
exit $LASTEXITCODE
