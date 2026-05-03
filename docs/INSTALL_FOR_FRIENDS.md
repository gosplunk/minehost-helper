# MineHost Helper Friend Install Guide

This guide is for friends installing MineHost Helper on Windows 10 or Windows 11.

You do not need Git, Python, Node, Docker, or command-line knowledge when using the Friend Mode installer.

## The Short Version

1. Download `MineHostHelper-FriendSigned.zip`.
2. Right click the ZIP and choose `Extract All`.
3. Open the extracted folder.
4. Double click `Install MineHost Helper Friend Publisher Certificate.bat`.
5. Approve the Windows administrator prompt.
6. Double click `MineHostHelperSetup-FriendSigned.exe`.
7. Follow the installer.
8. When the browser opens, create your MineHost Helper login.
9. Choose `Setup new server, guided`.

## Download The Right File

Use this download:

[Download MineHostHelper-FriendSigned.zip](https://github.com/gosplunk/minehost-helper/releases/latest/download/MineHostHelper-FriendSigned.zip)

Do not download these unless someone specifically tells you to:

- `Source code (zip)`
- `Source code (tar.gz)`
- Random files from the repository file list

Those are for development, not normal install.

## What Should Be In The ZIP

After extracting the ZIP, you should see these files:

| File | What it does |
| --- | --- |
| `START HERE - Install Guide.html` | Double click this if you want the visual install guide. |
| `Install MineHost Helper Friend Publisher Certificate.bat` | Run this first. It tells Windows to trust this private friend build. |
| `MineHostHelperSetup-FriendSigned.exe` | Run this second. This installs MineHost Helper. |
| `MineHostHelper-FriendPublisher.cer` | The public trust certificate used by the helper. |
| `InstallFriendPublisherCertificate.ps1` | Used by the BAT file. You usually do not click this directly. |
| `FRIEND_MODE_SIGNING.md` | Technical details for the self-signed friend build. |

## Step 1: Extract The ZIP

Do not run the installer directly from inside the ZIP preview.

Right click `MineHostHelper-FriendSigned.zip`, choose `Extract All`, then open the extracted folder.

If you see a folder inside a folder, open it until you can see `MineHostHelperSetup-FriendSigned.exe`.

For a visual copy of this guide, double click:

```text
START HERE - Install Guide.html
```

## Step 2: Trust The Friend Publisher Certificate

Double click:

```text
Install MineHost Helper Friend Publisher Certificate.bat
```

Windows will ask for administrator permission because it is installing a certificate into `Trusted People`.

Approve the prompt only if you personally trust the person who gave you this download.

When it says the certificate installed, close that window.

## Step 3: Run The Installer

Double click:

```text
MineHostHelperSetup-FriendSigned.exe
```

The installer lets you:

- Choose where MineHost Helper should be installed.
- Create your local web username and password.
- Install shortcuts.
- Install the uninstaller.
- Keep or update an existing install if MineHost Helper is already installed.

Recommended install location:

```text
C:\Users\<your name>\AppData\Local\MineHost Helper
```

The installer can also use another normal writable folder if you prefer.

## Step 4: First Launch

After install, MineHost Helper starts a local web page in your browser.

The first page should look like this:

![MineHost Helper login](screenshots/01-login.png)

Create or enter your MineHost Helper username and password. This is only for the web manager on your PC.

## Step 5: Choose Guided Setup

On the Get Started page, choose:

```text
Setup new server, guided
```

![MineHost Helper get started](screenshots/02-get-started.png)

Use `Import existing Minecraft server` only if you already have a Minecraft Java server folder on this PC.

## Step 6: Start The Server

After setup, use the Dashboard:

![MineHost Helper dashboard](screenshots/03-dashboard.png)

The main buttons are:

- `Start Server`
- `Stop`
- `Restart`
- `Copy Friend Address`

If friends are outside your house, they usually need the public address shown on the dashboard. Router port forwarding may still be required.

## If Windows Blocks It

If Microsoft Defender says the file is a virus or blocks it with `WinError 225`, stop and ask the person who gave you the download. Do not disable Defender.

Use the portable fallback if needed:

[Download MineHostHelper-Portable.zip](https://github.com/gosplunk/minehost-helper/releases/latest/download/MineHostHelper-Portable.zip)

Portable fallback steps:

1. Extract `MineHostHelper-Portable.zip`.
2. Double click `Start MineHost Helper.bat`.
3. Follow the browser setup.

## If Java Says SSL Certificate Verify Failed

If you see:

```text
could not download Eclipse Temurin Java
SSL Certificate verify failed
unable to get local issuer certificate
```

Update to the newest MineHost Helper release and try again. MineHost Helper now retries Java downloads using Windows-native certificate handling when Python cannot verify the certificate chain.

If it still fails:

1. Make sure Windows date and time are correct.
2. Try a normal home network instead of a school, work, hotel, or filtered network.
3. Open Windows Update and install pending root certificate/security updates.
4. Ask the person who gave you MineHost Helper for help before changing antivirus or certificate settings.

## Common Questions

**Which file do I run first?**

Run `Install MineHost Helper Friend Publisher Certificate.bat` first, then `MineHostHelperSetup-FriendSigned.exe`.

**Do I need Java?**

MineHost Helper checks for Java and can prepare the bundled Java runtime it needs.

**Do I need to open a command prompt?**

No. The BAT file opens briefly only to install the friend certificate.

**Where is the uninstaller?**

Open Windows `Installed apps` and uninstall `MineHost Helper`, or run `Uninstall MineHost Helper.exe` from the install folder.

**Can friends join immediately?**

People on your Wi-Fi can usually use the local address. People outside your house usually need router port forwarding. Use the Networking page inside MineHost Helper.

**Should I expose the MineHost Helper web page to the internet?**

No. The manager web page is for your PC only.
