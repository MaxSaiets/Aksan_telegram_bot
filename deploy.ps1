Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = if ($env:DEPLOY_PROJECT_ROOT) {
    $env:DEPLOY_PROJECT_ROOT
} else {
    $PSScriptRoot
}

if (-not (Test-Path $projectRoot)) {
    throw "Project root not found: $projectRoot"
}

$pythonExe = Join-Path $projectRoot 'venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    throw "Python venv executable not found: $pythonExe"
}

Set-Location $projectRoot

git config --global --add safe.directory $projectRoot
$resolvedRoot = (Get-Item $projectRoot).Target
if (-not $resolvedRoot) { $resolvedRoot = (Get-Item $projectRoot).FullName }
git config --global --add safe.directory $resolvedRoot

git fetch origin
if ($LASTEXITCODE -ne 0) {
    throw 'git fetch failed'
}

git reset --hard origin/main
if ($LASTEXITCODE -ne 0) {
    throw 'git reset failed'
}

& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r requirements.txt
& $pythonExe -m pip install telethon cryptg

Restart-Service aksan_bot_polling
Restart-Service aksan_bot_worker

Write-Host "Deploy completed successfully for $projectRoot."

