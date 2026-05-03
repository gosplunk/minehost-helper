$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$OutputDir = Join-Path $Root "dist-portable"
$Stage = Join-Path $env:TEMP "MineHostHelper-portable-stage"
$PackageRoot = Join-Path $Stage "MineHostHelper"
$ZipPath = Join-Path $OutputDir "MineHostHelper-Portable.zip"

if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
if (Test-Path $OutputDir) { Remove-Item $OutputDir -Recurse -Force }
New-Item -ItemType Directory -Path $PackageRoot -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$Items = @(
  ".github",
  "backend",
  "docs",
  "frontend",
  "scripts",
  "tests",
  "CONTRIBUTING.md",
  "LICENSE.md",
  "README.md",
  "requirements.txt",
  "SECURITY.md",
  "Start MineHost Helper.bat",
  "Stop MineHost Helper.bat"
)

foreach ($item in $Items) {
  if (Test-Path $item) {
    Copy-Item $item (Join-Path $PackageRoot $item) -Recurse -Force
  }
}

$RemovePatterns = @(
  ".pytest_cache",
  "__pycache__",
  "node_modules",
  "dist",
  "dist-installer",
  "dist-portable",
  ".venv",
  "app_data",
  "servers",
  "backups",
  "runtimes",
  "logs"
)

foreach ($pattern in $RemovePatterns) {
  Get-ChildItem $PackageRoot -Recurse -Force -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq $pattern } |
    Remove-Item -Recurse -Force
}

Get-ChildItem $PackageRoot -Recurse -Force -Include "*.pyc","*.pyo","*.log" -ErrorAction SilentlyContinue |
  Remove-Item -Force

Compress-Archive -Path (Join-Path $PackageRoot "*") -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host ""
Write-Host "Built portable ZIP: $ZipPath" -ForegroundColor Green
Write-Host "This package contains no MineHost Helper EXE. Users start it with Start MineHost Helper.bat." -ForegroundColor Yellow
