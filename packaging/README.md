# Packaging (planned/in-progress)

This repository currently ships a working Python/Tkinter app (`easy_ap_gui.py`). Native-style distribution targets requested:

- Windows: `.exe`
- Linux: `.AppImage`

## Suggested approach (Python app)

### Windows `.exe` (PyInstaller)
1. Install PyInstaller in a clean environment:
   - `python -m pip install pyinstaller`
2. Build:
   - `pyinstaller --noconfirm --onefile --windowed --name easy-ap easy_ap_gui.py`
3. Test on Windows with USB/adb/build prerequisites available.

Notes: Tkinter and bundled runtime behavior should be validated on target Windows versions.

### Linux `.AppImage`
1. Build a Linux binary or bundle with PyInstaller:
   - `pyinstaller --noconfirm --onefile --name easy-ap easy_ap_gui.py`
2. Create an AppDir with desktop entry/icon and AppRun wrapper.
3. Package with `appimagetool` to produce `easy-ap*.AppImage`.

Notes: the app shells out to `bash` and patcher build tooling; packaged runtime must still have required host dependencies (Java, Android tools/NDK as needed).

## Future C# packaging
When the C# implementation matures, prefer framework-native publishing:
- Windows: `dotnet publish -c Release -r win-x64 --self-contained true`
- Linux: `dotnet publish -c Release -r linux-x64 --self-contained true` then AppImage packaging

See `../csharp/README.md`.
