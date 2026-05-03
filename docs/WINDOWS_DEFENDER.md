# Windows Defender And SmartScreen

MineHost Helper is an unsigned, self-contained Windows app during early testing. Microsoft Defender or SmartScreen may block new builds with messages such as:

- `WinError 225`
- `Operation did not complete successfully because the file contains a virus or potentially unwanted software`
- `Windows protected your PC`
- `Unknown publisher`

Do not tell non-technical users to disable Defender. Treat this as a release trust problem that must be fixed by packaging, signing, and Microsoft review.

## Recommended Temporary Path

Use `MineHostHelper-Portable.zip` instead of the installer. The portable ZIP contains source files and batch/PowerShell launchers, not a custom MineHost Helper executable. This avoids the PyInstaller bootloader that Defender is flagging.

Steps:

1. Download `MineHostHelper-Portable.zip` from the latest GitHub release.
2. Unzip it into a normal writable folder, such as `C:\MineHostHelper`.
3. Double click `Start MineHost Helper.bat`.
4. If Python is missing, the launcher can ask to install Python with `winget`.

This is not as polished as an installer, but it is safer than asking users to bypass antivirus.

## Why It Happens

Early MineHost Helper builds are produced with PyInstaller. PyInstaller creates self-extracting executables that bundle Python, app code, and assets. Unsigned self-extracting binaries with low download reputation are common false-positive targets.

Starting with `v0.1.21`, MineHost Helper disables UPX compression in PyInstaller specs because compressed executables are more likely to look suspicious to antivirus engines. Starting with `v0.1.22`, the primary release asset is a portable ZIP to avoid the PyInstaller installer path entirely.

## Immediate Response For A Flagged Release

1. Do not publish instructions asking users to turn off Defender.
2. Submit the exact flagged installer to Microsoft as a software developer:
   `https://www.microsoft.com/en-us/wdsi/filesubmission`
3. Choose that the file was incorrectly detected.
4. Include the GitHub release URL and SHA256 hash.
5. Wait for Microsoft’s verdict before sending the file to non-technical users.
6. Rebuild and re-release only after the detection is cleared or after the package is signed.

Microsoft documentation:

- Submit files for analysis: `https://learn.microsoft.com/en-us/defender-xdr/submission-guide/`
- SmartScreen reputation for app developers: `https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation`

## Required Long-Term Fix

Use Authenticode code signing for every release. Microsoft recommends signing release binaries for non-Store distribution. Signing does not guarantee zero SmartScreen warnings on day one, but it:

- Replaces `Unknown publisher` with a real publisher name.
- Lets reputation accumulate on the signing certificate.
- Reduces enterprise and consumer trust friction.
- Is expected for software given to non-technical users.

Supported signing environment variables:

- `WINDOWS_SIGN_CERT_SHA1`: SHA1 thumbprint of a code-signing cert in the Windows certificate store.
- `WINDOWS_SIGN_PFX`: Path to a `.pfx` code-signing certificate.
- `WINDOWS_SIGN_PFX_PASSWORD`: Password for the `.pfx`, if needed.
- `WINDOWS_SIGN_TIMESTAMP_URL`: Optional timestamp server. Defaults to `http://timestamp.digicert.com`.

The build scripts call `scripts/sign-windows.ps1` automatically. If no signing certificate is configured, signing is skipped.

Example:

```powershell
$env:WINDOWS_SIGN_PFX = "C:\certs\MineHostHelper.pfx"
$env:WINDOWS_SIGN_PFX_PASSWORD = "use-a-secret-manager-in-real-builds"
.\scripts\build-exe.ps1
.\scripts\build-installer.ps1
```

## Packaging Direction

The current PyInstaller bootstrap installer is acceptable for internal testing, but a public-friendly Windows release should move to one of these:

- Signed Inno Setup installer wrapping the built app.
- Signed MSI/MSIX package.
- Azure Trusted Signing or a normal code-signing certificate.

Avoid nested unsigned self-extracting executables for public releases.
