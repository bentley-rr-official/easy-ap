# Packaging (Rec Room 2025 Android Patch Tool)

This repository includes a working Python/Tkinter **Rec Room 2025 Android Patch Tool** (`easy_ap_gui.py`) and GitHub Actions workflows to build distributables:

- **Windows `.exe`**: `.github/workflows/build-windows-exe.yml`
- **Linux `.AppImage`**: `.github/workflows/build-linux-appimage.yml`

Artifacts are named for the **Rec Room 2025 Android Patch Tool** (not a generic patcher).

## Automated builds (GitHub Actions)
- Trigger via **Actions > workflow_dispatch**, or push a tag like `v1.0.0`.
- Outputs:
  - `RecRoom2025AndroidPatchTool-windows-x64.zip` (contains `.exe`, README, example settings)
  - `RecRoom2025AndroidPatchTool-linux-x86_64.AppImage`

## Local build notes

### Windows `.exe` (PyInstaller)
```powershell
python -m pip install --upgrade pip pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name RecRoom2025AndroidPatchTool easy_ap_gui.py
```

### Linux `.AppImage` (PyInstaller + appimagetool)
Build the binary with PyInstaller, create an AppDir (`AppRun`, `.desktop`, icon), then package with `appimagetool` (see `.github/workflows/build-linux-appimage.yml` for the exact CI steps).

## Runtime/build dependencies (important)
Packaging the GUI does **not** bundle the full Rec Room 2025 Android patch build environment. Users still need:
- Internet access and Android USB debugging/ADB device access
- Rec Room 2025 patcher build dependencies (Java, Android build-tools/NDK, etc.) as required by the patcher
- A `bash` environment for `scripts/build-phone.sh`
  - Linux: usually available
  - Windows: Git Bash or WSL (configure in app **Settings** if needed)

## Customization
The packaged tool supports customization via `recroom-2025-patch-settings.json` (URLs, package, bundle destination, workdir, adb/bash paths, etc.). See `../recroom-2025-patch-settings.example.json`.

## Future C# packaging
C# rewrite/packaging is planned for later. See `../csharp/README.md`.
