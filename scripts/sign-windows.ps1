param(
  [Parameter(Mandatory = $true)]
  [string[]]$Path
)

$ErrorActionPreference = "Stop"

$TimestampUrl = $env:WINDOWS_SIGN_TIMESTAMP_URL
if (-not $TimestampUrl) {
  $TimestampUrl = "http://timestamp.digicert.com"
}

function Find-SignTool {
  $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }

  $kits = @(
    "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
    "$env:ProgramFiles\Windows Kits\10\bin"
  )
  foreach ($kit in $kits) {
    if (-not (Test-Path $kit)) { continue }
    $candidate = Get-ChildItem $kit -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
      Sort-Object FullName -Descending |
      Select-Object -First 1
    if ($candidate) { return $candidate.FullName }
  }
  return $null
}

$certSha1 = $env:WINDOWS_SIGN_CERT_SHA1
$pfxPath = $env:WINDOWS_SIGN_PFX
$pfxPassword = $env:WINDOWS_SIGN_PFX_PASSWORD

if (-not $certSha1 -and -not $pfxPath) {
  Write-Host "Skipping code signing: set WINDOWS_SIGN_CERT_SHA1 or WINDOWS_SIGN_PFX to sign release binaries." -ForegroundColor Yellow
  exit 0
}

$signTool = Find-SignTool
if (-not $signTool) {
  throw "signtool.exe was not found. Install the Windows SDK or add signtool.exe to PATH."
}

foreach ($target in $Path) {
  if (-not (Test-Path $target)) {
    throw "File not found for signing: $target"
  }
  if ($pfxPath) {
    $args = @("sign", "/fd", "SHA256", "/td", "SHA256", "/tr", $TimestampUrl, "/f", $pfxPath)
    if ($pfxPassword) {
      $args += @("/p", $pfxPassword)
    }
    $args += $target
  } else {
    $args = @("sign", "/fd", "SHA256", "/td", "SHA256", "/tr", $TimestampUrl, "/sha1", $certSha1, $target)
  }
  & $signTool @args
  if ($LASTEXITCODE -ne 0) {
    throw "signtool failed for $target"
  }
}
