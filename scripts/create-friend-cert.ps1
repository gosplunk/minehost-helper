param(
  [string]$PublisherName = "MineHost Helper Friend Build",
  [string]$OutputDirectory = "friend-signing",
  [int]$YearsValid = 3
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Output = Join-Path $Root $OutputDirectory
New-Item -ItemType Directory -Path $Output -Force | Out-Null

$subject = "CN=$PublisherName"
$existing = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
  Where-Object { $_.Subject -eq $subject } |
  Sort-Object NotAfter -Descending |
  Select-Object -First 1

if ($existing) {
  $cert = $existing
  Write-Host "Using existing Friend Mode certificate: $($cert.Thumbprint)" -ForegroundColor Yellow
} else {
  $cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $subject `
    -FriendlyName "$PublisherName Code Signing" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -KeyExportPolicy Exportable `
    -KeyUsage DigitalSignature `
    -NotAfter (Get-Date).AddYears($YearsValid)
  Write-Host "Created Friend Mode certificate: $($cert.Thumbprint)" -ForegroundColor Green
}

$cerPath = Join-Path $Output "MineHostHelper-FriendPublisher.cer"
Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null

$envFile = Join-Path $Output "use-friend-cert.ps1"
@"
`$env:WINDOWS_SIGN_CERT_SHA1 = "$($cert.Thumbprint)"
Write-Host "MineHost Helper Friend Mode signing enabled for this PowerShell session." -ForegroundColor Green
Write-Host "Certificate thumbprint: $($cert.Thumbprint)"
"@ | Set-Content -Path $envFile -Encoding UTF8

$installScript = Join-Path $Output "InstallFriendPublisherCertificate.ps1"
@"
`$ErrorActionPreference = "Stop"
`$certPath = Join-Path `$PSScriptRoot "MineHostHelper-FriendPublisher.cer"

Write-Host ""
Write-Host "Installing MineHost Helper Friend Publisher certificate..." -ForegroundColor Cyan
Write-Host "Publisher: $PublisherName"
Write-Host ""

Import-Certificate -FilePath `$certPath -CertStoreLocation Cert:\LocalMachine\TrustedPeople | Out-Null

Write-Host ""
Write-Host "Certificate installed. You can now run MineHostHelperSetup-FriendSigned.exe." -ForegroundColor Green
Read-Host "Press Enter to close"
"@ | Set-Content -Path $installScript -Encoding UTF8

$installHelper = Join-Path $Output "Install MineHost Helper Friend Publisher Certificate.bat"
@"
@echo off
setlocal
cd /d "%~dp0"
echo.
echo MineHost Helper Friend Publisher Certificate
echo.
echo Only continue if you personally received this file from someone you trust.
echo This trusts MineHost Helper friend builds signed by:
echo   $PublisherName
echo.
pause
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "`$p = Join-Path (Get-Location) 'InstallFriendPublisherCertificate.ps1'; Start-Process powershell.exe -Verb RunAs -ArgumentList ('-NoLogo -NoProfile -ExecutionPolicy Bypass -File ""' + `$p + '""')"
"@ | Set-Content -Path $installHelper -Encoding ASCII

Write-Host ""
Write-Host "Friend Mode certificate files written to: $Output" -ForegroundColor Green
Write-Host "Public cert for friends: $cerPath"
Write-Host "Signing setup script: $envFile"
Write-Host "Friend certificate install script: $installScript"
Write-Host ""
Write-Host "Next build with this cert:"
Write-Host "  . '$envFile'"
Write-Host "  .\scripts\build-exe.ps1"
Write-Host "  .\scripts\build-installer.ps1"
