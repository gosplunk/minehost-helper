$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Test-Path ".\dist\MineHostHelper.exe")) {
  & ".\scripts\build-exe.ps1"
}

.\.venv\Scripts\python.exe -m pip install pyinstaller==6.11.1

$Stage = Join-Path $env:TEMP "MineHostHelper-installer-stage"
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage | Out-Null

Copy-Item ".\installer" (Join-Path $Stage "installer") -Recurse
Copy-Item ".\MineHostHelperSetup.spec" (Join-Path $Stage "MineHostHelperSetup.spec")
Copy-Item ".\MineHostHelperUninstall.spec" (Join-Path $Stage "MineHostHelperUninstall.spec")
New-Item -ItemType Directory -Path (Join-Path $Stage "dist") | Out-Null
Copy-Item ".\dist\MineHostHelper.exe" (Join-Path $Stage "dist\MineHostHelper.exe")

Push-Location $Stage
try {
  & "$Root\.venv\Scripts\python.exe" -m PyInstaller ".\MineHostHelperUninstall.spec" --clean --noconfirm
  & "$Root\.venv\Scripts\python.exe" -m PyInstaller ".\MineHostHelperSetup.spec" --clean --noconfirm
} finally {
  Pop-Location
}

New-Item -ItemType Directory -Path ".\dist-installer" -Force | Out-Null
Copy-Item (Join-Path $Stage "dist\MineHostHelperSetup.exe") ".\dist-installer\MineHostHelperSetup.exe" -Force
& ".\scripts\sign-windows.ps1" -Path ".\dist-installer\MineHostHelperSetup.exe"

Write-Host ""
Write-Host "Built installer: $Root\dist-installer\MineHostHelperSetup.exe" -ForegroundColor Green
