param(
    [string]$EnvFile = "",
    [switch]$NoBuildCheck
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$DefaultEnv = Join-Path $PSScriptRoot "production.env"
$DistIndex = Join-Path $Root "frontend\dist\index.html"
$LogDir = Join-Path $Root "logs"

function Import-EnvFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        Write-Warning "Environment file not found: $Path. Built-in defaults will be used."
        return
    }

    Get-Content -Path $Path -Encoding utf8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $pair = $line.Split("=", 2)
        if ($pair.Count -ne 2) {
            return
        }
        [Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1].Trim(), "Process")
    }
}

Set-Location $Root

if (-not $EnvFile) {
    $EnvFile = $DefaultEnv
}

Import-EnvFile $EnvFile

if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment not found. Run scripts\install-production.ps1 first."
}

if (-not $NoBuildCheck -and -not (Test-Path $DistIndex)) {
    throw "frontend\dist was not found. Run scripts\install-production.ps1 to build the frontend."
}

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$hostValue = if ($env:RELEASE_TOOL_HOST) { $env:RELEASE_TOOL_HOST } else { "127.0.0.1" }
$portValue = if ($env:RELEASE_TOOL_PORT) { $env:RELEASE_TOOL_PORT } else { "7860" }
$logFile = Join-Path $LogDir ("release-tool-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")

Write-Host "Starting Redmine Release Tool on ${hostValue}:${portValue}"
Write-Host "Log file: $logFile"

& $VenvPython main.py *>&1 | Tee-Object -FilePath $logFile -Append
