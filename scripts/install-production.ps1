param(
    [string]$EnvFile = "",
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$ExampleEnv = Join-Path $PSScriptRoot "production.env.example"
$DefaultEnv = Join-Path $PSScriptRoot "production.env"

Set-Location $Root

if (-not $EnvFile) {
    $EnvFile = $DefaultEnv
}

if (-not (Test-Path $EnvFile) -and (Test-Path $ExampleEnv)) {
    Copy-Item -Path $ExampleEnv -Destination $EnvFile
    Write-Host "Created $EnvFile. Edit it before starting the service."
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating Python virtual environment..."
    python -m venv .venv
}

Write-Host "Installing Python dependencies..."
& $VenvPython -m pip install -r requirements.txt

if (-not $SkipFrontendBuild) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        throw "npm was not found. Install Node.js 18+ or rerun with -SkipFrontendBuild after copying a built frontend/dist."
    }

    Write-Host "Installing and building Vue frontend..."
    Push-Location (Join-Path $Root "frontend")
    try {
        if (Test-Path "package-lock.json") {
            npm ci
        } else {
            npm install
        }
        npm run build
    } finally {
        Pop-Location
    }
}

Write-Host "Production install completed."
Write-Host "Start with: powershell -ExecutionPolicy Bypass -File scripts\start-production.ps1"
