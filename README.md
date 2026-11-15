# easy-ap

Automated GUI helper for the **2025 Android Patcher**: downloads files, builds, installs APKs to a selected device, and pushes bundles.

## What it does

On start (and via **Start / Restart**), the app runs automatically:

1. **Prepares work directory** in the OS temp folder (`/tmp/easy-ap` on Linux/macOS, `%TEMP%\easy-ap` on Windows)
2. **Downloads patcher (with progress)** from:  
   `https://github.com/bentley-rr-official/2025-android-patcher/archive/refs/heads/main.zip`
3. **Asks for nameserver** (after patcher download). Only this value is configured (`RecNet NameServer Host` in `2025.cfg`).
4. **Downloads `base.xapk` (with progress)**:  
   `curl` source: `https://drive.usercontent.google.com/download?id=1k9ASR35hKhZX4QftctMHmuJCWRG2s04p&export=download&authuser=0&confirm=t`
5. **Downloads & extracts `bundles.zip` (with progress)**:  
   `curl` source: `https://drive.usercontent.google.com/download?id=1o42Q81c9G_fNceEiXSfHEOFjUPx23z6E&export=download&authuser=0&confirm=t`  
   Bundles are extracted into `<workdir>/2025-android-patcher/bundles/`.
6. **Builds** by writing `2025.cfg` (nameserver only) and running `scripts/build-phone.sh` on `base.xapk`.
7. **Ensures `adb` is available** (attempts automatic installation if missing).
8. **Device selection**: checks `adb devices`.
   - If no devices are found: shows **"No devices found"** with a retry button.
   - If one or more devices are found: shows buttons to **select a device**.
9. **Installs APKs** to the selected device with per-APK progress.
10. **Pushes bundles** to the selected device with per-file progress:  
    `/sdcard/Android/data/com.AgainstGravity.RecRoom/files/AssetPackStubs/OutfitsAssetPack/`

Progress bars and logs are shown in the GUI throughout.

## Requirements

- Python 3 + Tkinter
- `bash`, `curl`/network access (downloads use Python), `unzip` support (built-in Python `zipfile`)
- **Build toolchain required by the patcher** on this machine (e.g. `java`, `python3` + `lief`, `zipalign`/`apksigner`, `tools/debug.keystore`, Android NDK r27c, etc.) — the build step will fail if dependencies are missing
- USB debugging enabled and device connected for install/push steps
- `adb` (auto-install is attempted if missing, but may require admin rights/package manager support)

## Run

```bash
python3 easy_ap_gui.py
```

## Notes

- The app cleans/recreates its temp work directory on each run.
- Large downloads and builds can take a long time; watch the progress and log panels.
- Automatic `adb` installation is best-effort and platform-dependent; install Android platform-tools manually if needed.
- Review downloaded code/files and use at your own risk.