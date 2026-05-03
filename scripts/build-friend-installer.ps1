param(
  [string]$PublisherName = "MineHost Helper Friend Build",
  [string]$OutputDirectory = "friend-signing"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

& ".\scripts\create-friend-cert.ps1" -PublisherName $PublisherName -OutputDirectory $OutputDirectory
. (Join-Path $Root $OutputDirectory "use-friend-cert.ps1")

& ".\scripts\build-exe.ps1"
& ".\scripts\build-installer.ps1"

$FriendDist = Join-Path $Root "dist-friend"
if (Test-Path $FriendDist) { Remove-Item $FriendDist -Recurse -Force }
New-Item -ItemType Directory -Path $FriendDist | Out-Null

Copy-Item ".\dist-installer\MineHostHelperSetup.exe" (Join-Path $FriendDist "MineHostHelperSetup-FriendSigned.exe") -Force
Copy-Item (Join-Path $Root $OutputDirectory "MineHostHelper-FriendPublisher.cer") $FriendDist -Force
Copy-Item (Join-Path $Root $OutputDirectory "InstallFriendPublisherCertificate.ps1") $FriendDist -Force
Copy-Item (Join-Path $Root $OutputDirectory "Install MineHost Helper Friend Publisher Certificate.bat") $FriendDist -Force
Copy-Item ".\docs\FRIEND_MODE_SIGNING.md" $FriendDist -Force

Compress-Archive -Path (Join-Path $FriendDist "*") -DestinationPath ".\dist-friend\MineHostHelper-FriendSigned.zip" -CompressionLevel Optimal -Force

Write-Host ""
Write-Host "Built Friend Mode package: $FriendDist\MineHostHelper-FriendSigned.zip" -ForegroundColor Green
Write-Host "Give the ZIP only to people who personally trust you." -ForegroundColor Yellow
