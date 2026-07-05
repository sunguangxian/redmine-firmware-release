param(
    [string]$ServiceName = "RedmineReleaseTool",
    [string]$EnvFile = "",
    [string]$NssmPath = "nssm.exe"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$StartScript = Join-Path $PSScriptRoot "start-production.ps1"
$DefaultEnv = Join-Path $PSScriptRoot "production.env"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not $EnvFile) {
    $EnvFile = $DefaultEnv
}

$nssm = Get-Command $NssmPath -ErrorAction SilentlyContinue
if (-not $nssm) {
    throw "nssm.exe was not found. Download NSSM and either add it to PATH or pass -NssmPath C:\path\to\nssm.exe."
}

if (-not (Test-Path $StartScript)) {
    throw "Start script not found: $StartScript"
}

if (-not (Test-Path (Join-Path $Root "logs"))) {
    New-Item -ItemType Directory -Path (Join-Path $Root "logs") | Out-Null
}

& $nssm.Source install $ServiceName $PowerShellExe "-ExecutionPolicy Bypass -NoProfile -File `"$StartScript`" -EnvFile `"$EnvFile`""
& $nssm.Source set $ServiceName AppDirectory $Root
& $nssm.Source set $ServiceName AppStdout (Join-Path $Root "logs\service-stdout.log")
& $nssm.Source set $ServiceName AppStderr (Join-Path $Root "logs\service-stderr.log")
& $nssm.Source set $ServiceName AppRotateFiles 1
& $nssm.Source set $ServiceName AppRotateOnline 1
& $nssm.Source set $ServiceName AppRotateBytes 10485760
& $nssm.Source set $ServiceName AppExit Default Restart
& $nssm.Source set $ServiceName AppRestartDelay 5000
& $nssm.Source set $ServiceName AppThrottle 1500
& $nssm.Source set $ServiceName Start SERVICE_AUTO_START

Write-Host "Service installed: $ServiceName"
Write-Host "Start it with: nssm start $ServiceName"
