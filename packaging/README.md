# Packaging (2025RR Rec Room Patcher)

This repository contains the **Python/Tkinter** 2025RR Rec Room patcher app (`easy_ap_gui.py`) and GitHub Actions workflows to build distributable apps:

- **Windows `.exe`**: `.github/workflows/build-windows-exe.yml`
- **Linux `.AppImage`**: `.github/workflows/build-linux-appimage.yml`

## Automated builds (GitHub Actions)

- Workflows run on pushes (and can also be triggered via **workflow_dispatch** or version tags like `v1.0.0`).
- Build outputs/artifacts:
  - `2025RR-windows-x64.exe` (Windows)
  - `2025RR-linux-amd64.AppImage` (Linux)

## Local build notes

### Windows `.exe` (PyInstaller)
```powershell
python -m pip install --upgrade pip pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name 2025RR easy_ap_gui.py
```

### Linux `.AppImage` (PyInstaller + appimagetool)
Build the binary with PyInstaller, create an AppDir (`AppRun`, `.desktop`, icon), then package with `appimagetool` (see `.github/workflows/build-linux-appimage.yml` for the exact CI steps).

## Runtime/build dependencies (important)

Packaging the GUI app does **not** bundle the full Rec Room patch build environment. Users still need:
- Internet access and an Android device with USB debugging/ADB access
- Patch/build dependencies required by the 2025RR patcher (Java, Android build-tools/NDK, etc., as needed)
- A `bash` environment for `scripts/build-phone.sh`
  - **Linux:** usually available
  - **Windows:** Git Bash or WSL (can be configured in the app **Settings**)

## Customization

The packaged app includes an in-app **Settings** screen for adjusting options like work folder, package/bundle paths, and adb/bash commands during the current session. No settings file is required.
