# Friend Mode Self-Signed Builds

Friend Mode is for a small private group of people who personally trust the person building MineHost Helper.

It does not make MineHost Helper publicly trusted by Windows. It creates a private code-signing certificate, signs the MineHost Helper EXE/installer, and gives friends a helper script to trust that certificate on their PC.

Use this only for friends/family testing. Do not use it for public distribution.

## What Friends Will See

Friends receive a ZIP containing:

- `MineHostHelperSetup-FriendSigned.exe`
- `MineHostHelper-FriendPublisher.cer`
- `Install MineHost Helper Friend Publisher Certificate.bat`
- `InstallFriendPublisherCertificate.ps1`
- This document

They run the certificate helper first, approve the Windows administrator prompt, then run the signed installer.

## Security Warning

Installing the certificate means Windows will trust software signed by that Friend Mode certificate. Only install it if:

- You personally know and trust the person who gave it to you.
- The ZIP came directly from that person or their GitHub release.
- You understand this is not a Microsoft/company-verified publisher.

To remove trust later:

1. Open `Manage computer certificates`.
2. Go to `Trusted People > Certificates`.
3. Delete `MineHost Helper Friend Build` or the publisher name used by the builder.

## Build A Friend-Signed Installer

From the repo root:

```powershell
.\scripts\build-friend-installer.ps1
```

Output:

```text
dist-friend\MineHostHelper-FriendSigned.zip
```

Custom publisher name:

```powershell
.\scripts\build-friend-installer.ps1 -PublisherName "Josep MineHost Helper"
```

## Manual Steps

Create or reuse a Friend Mode cert:

```powershell
.\scripts\create-friend-cert.ps1 -PublisherName "Josep MineHost Helper"
```

Enable signing for the current PowerShell session:

```powershell
. .\friend-signing\use-friend-cert.ps1
```

Build:

```powershell
.\scripts\build-exe.ps1
.\scripts\build-installer.ps1
```

## Limitations

- This may not clear a Microsoft Defender malware/PUP detection. If Defender still blocks it, submit the exact file to Microsoft as a false positive.
- It does not build public SmartScreen reputation.
- It requires friends to approve trusting the certificate.
- It is less appropriate than Microsoft Store, Azure Artifact Signing, or a real code-signing certificate for public releases.
