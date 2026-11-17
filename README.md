# 2025RR Rec Room Patcher

**2025RR** is a friendly, all-in-one patcher app for **Rec Room (2025 Android build)**. It helps you download what you need, set up your nameserver, build the patched Rec Room APKs, install them on your Android device, and push the required bundles — with clear progress and helpful prompts along the way.

> This tool is for patching/installing Rec Room on Android devices you own/control. Make sure you follow Rec Room's terms and any applicable rules for your use case.

## Features

- **Easy-to-use blue/white app** with step-by-step progress, device prompts, and per-file/per-APK progress bars
- **Made for Rec Room patching**: downloads the 2025RR patcher and required files, builds the patch, installs APKs, and pushes bundles
- **Nameserver setup made simple**: asks for your nameserver URL (`http://` or `https://`) and configures it for the patch
- **Safer installs**: if an existing Rec Room install must be replaced because signatures differ, it asks first:  
  **"Are you sure you would like to uninstall Rec Room?"**
- **Helpful status and logs**: clear in-app progress, with a build log shown in the app while Rec Room is being patched
- **Easy customization** via the in-app **Settings** screen for this session (work folder, adb/bash paths, package/bundle destination, default nameserver URL, etc.)
- **Works on Windows & Linux**: run from Python source, or use GitHub Actions builds for a Windows `.exe` and Linux `.AppImage`

## How it works (what 2025RR does for you)

When you start (or click **Start / Restart patch process**), 2025RR will:

1. **Prepare a work folder** (where downloads and build files are stored)
2. **Download the 2025RR patcher**
3. **Ask for your nameserver URL** (must start with `http://` or `https://`) and configure the patch settings for you
4. **Download the Rec Room base package (`base.xapk`) and bundles**
5. **Build the patched Rec Room APKs** (this can take a while the first time)
6. **Find your Android device** over USB (ADB/USB debugging) and let you choose the right one if needed
7. **Install the patched APKs** to your device, showing progress for each file and asking before uninstalling Rec Room if signatures don't match
8. **Push the required bundles** to your device (default):  
   `/sdcard/Android/data/com.AgainstGravity.RecRoom/files/AssetPackStubs/OutfitsAssetPack/`

## Before you start

To use 2025RR as smoothly as possible, make sure you have:

- **An Android device** with **USB debugging enabled** and a data-capable USB cable
- **Internet access** (for downloads and first-time build/setup steps)
- **Time for the first run** — building Rec Room patches can take a while, especially the first time when tools/dependencies are downloaded

### Running from source (Python)
- **Python 3** with **Tkinter**

### Building the patched APKs
The patch build needs a few development tools:
- **Java (JDK/JRE)** and signing tools
- **Android build tools / NDK** (2025RR can try to download some tools automatically, but your setup may still need manual configuration)
- **`bash`** to run the patch build script
  - **Linux:** usually already available
  - **Windows:** install **Git Bash** or **WSL** and set the Bash command in **Settings** if auto-detection doesn't work
- **ADB (Android platform-tools)** (2025RR can try to download it automatically)

> Tip: During the build step, 2025RR shows the live build log in the app so you can follow progress and spot issues.

## Run from source

```bash
python3 easy_ap_gui.py
```

## Settings & customization

Click **Settings** in the app to adjust things like:
- Work folder location
- ADB command/path and Bash command/path
- Package name and bundle destination on device
- Default nameserver URL
- Auto-start and clean-workdir behavior

- Download links for the 2025RR patcher, `base.xapk`, and bundles are **hardcoded** in the app.
- Settings are applied for the current app session (no settings file required).

## Windows & Linux app builds

GitHub Actions workflows can build ready-to-use app artifacts:

- **Windows:** `.github/workflows/build-windows-exe.yml` → `2025RR-windows-x64.exe`
- **Linux:** `.github/workflows/build-linux-appimage.yml` → `2025RR-linux-amd64.AppImage`

These workflows run on pushes and can also be triggered manually (`workflow_dispatch`) or by version tags (`v*`).

## Notes

- 2025RR can clean/recreate its work folder each run (configurable in Settings).
- This project is fully **Python** (Tkinter GUI). Check downloaded files/code and use at your own risk.
