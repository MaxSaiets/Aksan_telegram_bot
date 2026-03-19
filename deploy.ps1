Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = "C:\bots\telegram_aksan_bot"
$pythonExe = Join-Path $projectRoot "venv\\Scripts\\python.exe"

Set-Location $projectRoot

git fetch origin
git reset --hard origin/main

& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r requirements.txt
& $pythonExe -m pip install telethon cryptg

Restart-Service aksan_bot_polling
Restart-Service aksan_bot_worker

Write-Host "Deploy completed successfully."
