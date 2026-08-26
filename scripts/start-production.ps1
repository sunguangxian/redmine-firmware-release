param(
    [string]$EnvFile = "",
    [switch]$NoBuildCheck,
    [switch]$AllowInsecureHttp
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

if ($AllowInsecureHttp) {
    $env:RELEASE_TOOL_ALLOW_INSECURE_HTTP = "1"
    # Secure cookies are not sent over plain HTTP. LAN HTTP mode must disable it
    # so login sessions continue to work from other machines on the intranet.
    $env:RELEASE_TOOL_SESSION_COOKIE_SECURE = "0"
}

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
$certValue = if ($env:RELEASE_TOOL_TLS_CERTFILE) { $env:RELEASE_TOOL_TLS_CERTFILE.Trim() } else { "" }
$allowInsecureValue = if ($env:RELEASE_TOOL_ALLOW_INSECURE_HTTP) { $env:RELEASE_TOOL_ALLOW_INSECURE_HTTP.Trim().ToLowerInvariant() } else { "" }
$isLoopback = $hostValue.Trim().ToLowerInvariant() -in @("127.0.0.1", "localhost", "::1")
$isInsecureAllowed = $allowInsecureValue -in @("1", "true", "yes", "on")

if (-not $isLoopback -and -not $certValue -and -not $isInsecureAllowed) {
    throw "Listening on ${hostValue}:${portValue} without HTTPS is blocked. For an isolated LAN only, restart with -AllowInsecureHttp; otherwise configure RELEASE_TOOL_TLS_CERTFILE and RELEASE_TOOL_TLS_KEYFILE."
}

$logFile = Join-Path $LogDir ("release-tool-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")

Write-Host "Starting Redmine Release Tool on ${hostValue}:${portValue}"
if (-not $isLoopback -and -not $certValue -and $isInsecureAllowed) {
    Write-Warning "Insecure HTTP is enabled for a non-loopback address. Use this only on a trusted isolated LAN."
}
Write-Host "Log file: $logFile"

# uvicorn writes normal INFO logs to stderr. In Windows PowerShell 5.1, piping
# native stderr directly can be surfaced as NativeCommandError when
# $ErrorActionPreference is Stop. Let cmd.exe merge stderr into stdout first.
$runCommand = "`"$VenvPython`" main.py 2>&1"
cmd.exe /d /c $runCommand | Tee-Object -FilePath $logFile -Append
