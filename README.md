# easy-ap

Automated, user-friendly helper for the **2025 Android Patcher**: downloads required files, asks for your nameserver, builds the patched app, installs APKs to a selected Android device, and pushes bundles.

## Features

- **Revamped blue/white GUI** focused on clear progress and prompts
- **Terminal logging** for detailed/live technical output (downloads, build, adb, install)
- **Nameserver validation**: must be a URL starting with `http://` or `https://` (easy-ap extracts the host for the patcher config)
- **Improved adb/device flow**: device detection, retry/selection, reconnect handling, and clearer guidance
- **Safer uninstall handling**: if an existing install must be replaced due to signature mismatch, the app asks:  
  **"Are you sure you would like to uninstall Rec Room?"**
- **Per-file progress**: per-APK install progress and per-bundle upload progress

## What it does

On start (or **Start / Restart**), the app:

1. Prepares a clean work directory in the OS temp folder (`/tmp/easy-ap` on Linux/macOS, `%TEMP%\easy-ap` on Windows)
2. Downloads the patcher (with progress):  
   `https://github.com/bentley-rr-official/2025-android-patcher/archive/refs/heads/main.zip`
3. Prompts for a **nameserver URL** (`http://` or `https://`), extracts the host, and writes `RecNet NameServer Host` to `2025.cfg`
4. Downloads `base.xapk` (with progress):  
   `https://drive.usercontent.google.com/download?id=1k9ASR35hKhZX4QftctMHmuJCWRG2s04p&export=download&authuser=0&confirm=t`
5. Downloads and extracts `bundles.zip` (with progress):  
   `https://drive.usercontent.google.com/download?id=1o42Q81c9G_fNceEiXSfHEOFjUPx23z6E&export=download&authuser=0&confirm=t`  
   Bundles are extracted into `<workdir>/2025-android-patcher/bundles/`
6. Prepares/builds using `scripts/build-phone.sh` on `base.xapk` (bootstraps some dependencies/tools when possible)
7. Ensures `adb` is available and lets you choose a device if multiple are connected
8. Installs built APKs to the selected device (with per-APK progress). If a signature mismatch requires uninstall, it asks for confirmation first
9. Pushes bundles to:  
   `/sdcard/Android/data/com.AgainstGravity.RecRoom/files/AssetPackStubs/OutfitsAssetPack/`

## Requirements

- **Python 3 + Tkinter** (current implementation)
- `bash` (required for the patcher build script on Linux/macOS; Windows build support depends on environment/tooling)
- Internet access for downloads
- **Build toolchain required by the patcher** (Java, Android build-tools/NDK, signing tools, etc.). The app attempts to bootstrap some dependencies on first run, but setup can be slow and platform-dependent.
- Android device with **USB debugging** enabled for install/push

## Run (source)

```bash
python3 easy_ap_gui.py
```

## Packaging (`.exe` / `.AppImage`) and future C# rewrite

- **Windows `.exe` / Linux `.AppImage`**: not packaged in-repo yet. The current app is Python/Tkinter and can be packaged with tools like PyInstaller (Windows/Linux) and an AppImage bundling step on Linux (packaging scripts/config to be added).
- **C# (planned)**: a future C# implementation/skeleton is planned for easier editing and native building/packaging. See `csharp/README.md` for the migration/build plan scaffold.

## Notes

- The app cleans/recreates its temp work directory each run.
- Large downloads/builds (NDK, build-tools, patch build) can take a long time; keep the terminal open for live logs.
- Review downloaded code/files and use at your own risk.