# Rec Room 2025 Android Patch Tool

A customizable, user-friendly tool for applying the **Rec Room 2025 Android patch**: it downloads the required patcher/files, asks for your Rec Room nameserver, builds the patched Rec Room 2025 Android APKs, installs them to a selected Android device, and pushes the required bundles.

> This project is specifically for the **Rec Room 2025 Android patch** workflow (not a generic app patcher).

## Features

- **Blue/white GUI** with clear progress, device prompts, and per-file/per-APK progress bars
- **Terminal/console logging** for detailed live output (downloads, build, adb, install)
- **Rec Room-specific flow**: patcher download/build, nameserver setup, APK install, and bundle push for Rec Room 2025
- **Nameserver URL required**: must start with `http://` or `https://` (the tool extracts and configures the host for the Rec Room 2025 patcher)
- **Safer uninstall confirmation**: if an existing install must be replaced due to signature mismatch, it asks:  
  **"Are you sure you would like to uninstall Rec Room?"**
- **Customizable settings** via UI and `recroom-2025-patch-settings.json` (URLs, package, work folder, adb/bash commands, bundle destination, auto-start, etc.)
- **Cross-platform app support**: Python/Tkinter source runs on Linux and Windows; build packaging workflows are provided for Windows `.exe` and Linux `.AppImage`

## What it does

On start (or **Start / Restart patch process**), the tool:

1. Prepares a work folder (default: OS temp folder, configurable)
2. Downloads the **Rec Room 2025 Android patcher** (`2025-android-patcher`) from the configured URL
3. Prompts for your **Rec Room 2025 nameserver URL** (`http://`/`https://`) and writes `RecNet NameServer Host` + `Asset Pack Stub = true` to `2025.cfg`
4. Downloads the Rec Room `base.xapk` and bundles archive
5. Extracts bundles into the patcher workspace and runs the Rec Room 2025 patch build (`scripts/build-phone.sh`)
6. Ensures `adb` is available, detects/selects your Android device, and handles reconnect/retry cases
7. Installs patched APKs with per-APK progress (with confirmation before uninstalling existing Rec Room if signatures differ)
8. Pushes Rec Room 2025 bundles to the device (default):  
   `/sdcard/Android/data/com.AgainstGravity.RecRoom/files/AssetPackStubs/OutfitsAssetPack/`

## Customization

- Click **Settings** in the app to customize:
  - Patcher/XAPK/bundles download URLs
  - Package name and bundle destination path on device
  - Work directory
  - ADB command/path
  - Bash command/path (important on Windows)
  - Default nameserver URL, auto-start, clean-workdir behavior
- Settings are saved to `recroom-2025-patch-settings.json` next to the app/script.
- See `recroom-2025-patch-settings.example.json` for all available options.

## Requirements

### To run from source
- **Python 3 + Tkinter**
- Internet access for downloads
- Android device with **USB debugging** enabled

### To build the Rec Room 2025 Android patch
- The Rec Room 2025 patcher build requirements (Java, Android build-tools/NDK, signing tools, etc.)
- A `bash` environment to run `scripts/build-phone.sh`
  - **Linux:** usually available by default
  - **Windows:** install **Git Bash** or **WSL** and set the Bash command in **Settings** if auto-detection is not sufficient
- `adb` / Android platform-tools (the tool can attempt to download platform-tools automatically)

> Building the Rec Room 2025 Android patch can take a long time (especially first-run dependency downloads). Keep the terminal/console open for live build logs.

## Run (source)

```bash
python3 easy_ap_gui.py
```

## Windows / Linux builds (`.exe` / `.AppImage`)

GitHub Actions workflows are included to build distributables:

- `.github/workflows/build-windows-exe.yml` → **Windows `.exe`** (PyInstaller, artifact zip)
- `.github/workflows/build-linux-appimage.yml` → **Linux `.AppImage`** (PyInstaller + appimagetool)

You can trigger them via **workflow_dispatch** or by pushing a version tag (`v*`). Build artifacts are uploaded from the workflow runs.

## Notes

- The tool can clean/recreate its work folder each run (configurable).
- Download URLs and paths are customizable for your Rec Room 2025 patch setup/mirrors.
- Review downloaded code/files and use at your own risk.
- **C# rewrite:** planned for later (scaffold/docs remain in `csharp/`), but not part of this update.