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

Installer behavior:

- Lets the user choose the install folder.
- Detects an existing install before copying files.
- Offers Update / Repair to keep servers, backups, Java runtimes, logs, and app settings.
- Offers Clean Install to remove the selected MineHost Helper install folder and start over after explicit confirmation.
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

Unsigned installers or launchers may trigger Windows SmartScreen, especially for new apps with low reputation.

Users may see:

- `Windows protected your PC`
- `Unknown publisher`

For trusted private testing, users can click `More info`, then `Run anyway`. Do not ask strangers to bypass SmartScreen for public distribution.

## Code Signing

Code signing improves trust and reduces SmartScreen friction over time, but it is not required for friends/testing.

Options:

- Standard code signing certificate.
- Extended Validation certificate for stronger initial reputation, usually more expensive.
- Sign final `.exe` launchers and installers during release builds.

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
- Document SmartScreen expectations in release notes.

## Future Packaging Improvements

- Add GitHub Actions release builds.
- Add optional code signing.
- Add an auto-update flow with explicit user approval.
- Consider bundling a known-good Java runtime to reduce first-run download issues.
- Add release artifact checksums.
