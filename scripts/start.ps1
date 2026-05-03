$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Find-Python {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return @{ Exe = $py.Source; Args = @("-3") }
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return @{ Exe = $python.Source; Args = @() }
  }
  return $null
}

function Invoke-SelectedPython($Python, [string[]]$Arguments) {
  & $Python.Exe @($Python.Args + $Arguments)
}

function Find-FreePort([int]$StartPort) {
  for ($port = $StartPort; $port -lt ($StartPort + 100); $port++) {
    $listener = $null
    try {
      $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), $port)
      $listener.Start()
      return $port
    } catch {
    } finally {
      if ($listener) { $listener.Stop() }
    }
  }
  throw "No free manager port found from $StartPort to $($StartPort + 99)."
}

Write-Host "Starting MineHost Helper..." -ForegroundColor Green
$Python = Find-Python
if (-not $Python) {
  Write-Host "Python 3 was not found." -ForegroundColor Yellow
  $answer = Read-Host "Install Python 3 with winget now? Type Y to install"
  if ($answer -match "^[Yy]") {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
      Write-Host "winget is not available. Install Python 3 from https://www.python.org/downloads/windows/ and run this again." -ForegroundColor Red
      exit 1
    }
    winget install -e --id Python.Python.3.12
    $Python = Find-Python
  }
}

if (-not $Python) {
  Write-Host "Python 3 is required. Install it, check 'Add python.exe to PATH', then double click this launcher again." -ForegroundColor Red
  exit 1
}

$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  Write-Host "Creating local Python environment..." -ForegroundColor Cyan
  Invoke-SelectedPython $Python @("-m", "venv", $VenvDir)
}

Write-Host "Installing or updating MineHost Helper backend dependencies..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")

$Port = Find-FreePort 8787
$env:MINEHOST_HOST = "127.0.0.1"
$env:MINEHOST_PORT = "$Port"
$Url = "http://127.0.0.1:$Port"

Write-Host ""
Write-Host "MineHost Helper is opening at $Url" -ForegroundColor Green
Write-Host "Keep this window open while using the app. Press Ctrl+C here to stop the manager." -ForegroundColor Yellow
Start-Process $Url

& $VenvPython -m uvicorn backend.main:app --host 127.0.0.1 --port $Port
