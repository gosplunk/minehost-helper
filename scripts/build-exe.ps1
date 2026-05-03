$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
  py -3 -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pyinstaller==6.11.1

if (Test-Path ".\build") { Remove-Item ".\build" -Recurse -Force }
if (Test-Path ".\dist") { Remove-Item ".\dist" -Recurse -Force }

$Stage = Join-Path $env:TEMP "MineHostHelper-pyinstaller-stage"
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage | Out-Null

Copy-Item ".\backend" (Join-Path $Stage "backend") -Recurse
Copy-Item ".\frontend" (Join-Path $Stage "frontend") -Recurse
Copy-Item ".\MineHostHelper.spec" (Join-Path $Stage "MineHostHelper.spec")

Push-Location $Stage
try {
  & "$Root\.venv\Scripts\python.exe" -m PyInstaller ".\MineHostHelper.spec" --clean --noconfirm
} finally {
  Pop-Location
}

New-Item -ItemType Directory -Path ".\dist" -Force | Out-Null
Copy-Item (Join-Path $Stage "dist\MineHostHelper.exe") ".\dist\MineHostHelper.exe" -Force

Write-Host ""
Write-Host "Built: $Root\dist\MineHostHelper.exe" -ForegroundColor Green
Write-Host "Give this EXE to a friend for a standalone test, or wrap it with Inno Setup for an installer." -ForegroundColor Yellow
