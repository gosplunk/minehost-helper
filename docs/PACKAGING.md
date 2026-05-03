# Packaging MineHost Helper

MineHost Helper currently has three distribution paths:

- Source/portable folder for development.
- Standalone PyInstaller EXE for direct testing.
- Bootstrap setup EXE for friends and non-technical users.

For friends, use the setup EXE:

```text
dist-installer\MineHostHelperSetup.exe
```

## Bootstrap Installer

Build:

```powershell
.\scripts\build-installer.ps1
```

The script builds `dist\MineHostHelper.exe`, builds `Uninstall MineHost Helper.exe`, embeds both into a small setup EXE, and writes:

```text
dist-installer\MineHostHelperSetup.exe
```

PyInstaller UPX compression is disabled in all specs. Do not re-enable it for public releases; compressed self-extracting binaries are more likely to trigger antivirus false positives.

Installer behavior:

- Lets the user choose the install folder.
- Detects an existing install before copying files.
- Offers Update / Repair to keep servers, backups, Java runtimes, logs, and app settings.
- Offers Clean Install to remove the selected MineHost Helper install folder and start over after explicit confirmation.
- Clean Install stops MineHost Helper first, moves the old install folder aside, then deletes it in the background so locked files do not block reinstall.
- Checks for Java 25+ when setup opens and skips Java preparation when compatible bundled or system Java already exists.
- Prepares the bundled Eclipse Temurin Java runtime during install only when Java 25+ is missing.
- Installs for the current Windows user without requiring Administrator permission.
- Creates Start Menu and optional Desktop shortcuts.
- Registers MineHost Helper in Windows Apps & Features under HKCU.
- Installs `Uninstall MineHost Helper.exe` in the install folder.
- Preserves user data during app updates.

Uninstaller behavior:

- Removes shortcuts.
- Removes the Apps & Features uninstall entry.
- Removes the start-on-boot registry entry.
- Offers to remove user data such as `servers/`, `backups/`, `app_data/`, `runtimes/`, and `logs/`.

## Standalone EXE

Build:

```powershell
.\scripts\build-exe.ps1
```

Output:

```text
dist\MineHostHelper.exe
```

The EXE starts the local FastAPI backend, opens the browser, and can sit in the Windows system tray. Runtime data is stored next to the EXE:

- `app_data/`
- `servers/`
- `backups/`
- `runtimes/`
- `logs/`

The tray agent supports close-to-tray, start-on-boot, and optional Minecraft server auto-start.

## Portable Source Folder

Portable source mode is useful for development and early debugging:

1. Copy the repo to a writable location such as `C:\MineHostHelper`.
2. Do not include generated folders such as `.venv/`, `servers/`, `backups/`, `runtimes/`, `app_data/`, `logs/`, `build/`, `dist/`, or `dist-installer/` in source archives.
3. Double click `Start MineHost Helper.bat`.

This mode requires Python on the target PC or lets the launcher ask to install Python with `winget`.

## Inno Setup Path

Inno Setup remains a good option for a more conventional installer:

```powershell
iscc .\installer\MineHostHelper.iss
```

Output:

```text
dist-installer\MineHostHelperSetup.exe
```

Use Inno Setup if you want a more standard installer experience, richer wizard pages, or easier future code-signing integration. The current bootstrap installer is simpler and good enough for friend testing.

## MSI/MSIX Alternatives

- MSI is familiar for enterprise deployment but adds authoring complexity.
- WiX can produce robust MSI installers but has a higher maintenance cost.
- MSIX has cleaner update and sandbox semantics, but it can be restrictive for local server management and firewall workflows.
- For this app, the PyInstaller bootstrap installer or Inno Setup are the most pragmatic near-term choices.

## Unsigned Installer And SmartScreen

Unsigned installers or launchers may trigger Windows SmartScreen or Defender false positives, especially for new apps with low reputation.

Users may see:

- `Windows protected your PC`
- `Unknown publisher`
- `WinError 225`
- `Operation did not complete successfully because the file contains a virus or potentially unwanted software`

For trusted private testing, SmartScreen may allow `More info`, then `Run anyway`. Defender malware detections are different: do not ask non-technical users to bypass or disable Defender. Submit the exact flagged file to Microsoft for review and wait for the verdict.

See [WINDOWS_DEFENDER.md](WINDOWS_DEFENDER.md).

## Code Signing

Code signing improves trust and reduces SmartScreen friction over time. It is strongly recommended before public distribution to non-technical users.

Options:

- Standard code signing certificate.
- Extended Validation certificate for stronger initial reputation, usually more expensive.
- Azure Trusted Signing for non-Store distribution.
- Sign final `.exe` launchers and installers during release builds.

The build scripts call `scripts/sign-windows.ps1` automatically. Signing is skipped unless a certificate is configured through `WINDOWS_SIGN_CERT_SHA1` or `WINDOWS_SIGN_PFX`.

## Release Checklist

Before publishing a GitHub release:

- Run tests.
- Build `dist\MineHostHelper.exe`.
- Build `dist-installer\MineHostHelperSetup.exe`.
- Install into a clean writable folder.
- Verify first launch opens the browser.
- Verify create/start/stop server flow.
- Verify Find Existing Servers can adopt a test server folder without moving it.
- Verify Players buttons send commands only when the server is running.
- Verify Files page can edit `server.properties` and creates a backup copy.
- Verify automatic backup schedule can be saved.
- Verify Help page update check and problem explainer load.
- Verify uninstaller appears in Apps & Features.
- Verify uninstall removes shortcuts and startup entry.
- Submit any Defender false positive to Microsoft before sharing with non-technical users.
- Sign release artifacts if a certificate is available.
- Document SmartScreen expectations in release notes.

## Future Packaging Improvements

- Add GitHub Actions release builds.
- Add optional code signing.
- Add an auto-update flow with explicit user approval.
- Java is detected when setup opens and prepared during setup only when Java 25+ is missing, but it still downloads from Eclipse Adoptium instead of being bundled in the installer. Consider bundling a known-good Java runtime later if you want fully offline installs or fewer first-install network failures.
- Add release artifact checksums.
