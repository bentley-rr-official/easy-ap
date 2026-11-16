# easy-ap (C# planned)

This folder is a **planned C# rewrite scaffold** for `easy-ap` to make native builds/editing easier (Windows `.exe`, Linux builds, future packaging).

## Goals (parity with Python GUI)

- Blue/white, user-friendly UI
- Nameserver input **must** be `http://` or `https://`
- Device selection and improved adb flow (detect/retry/reconnect/auth guidance)
- Uninstall confirmation prompt: **"Are you sure you would like to uninstall Rec Room?"** before removing `com.AgainstGravity.RecRoom`
- Clear overall + per-item/per-APK progress bars
- Detailed technical logs in terminal/console pane (implementation choice TBD)
- Automated flow: download patcher/xapk/bundles, write config, build, install APKs, push bundles

## Suggested architecture

- `EasyAp.Gui/` - UI app (WinUI 3 / WPF / Avalonia; Avalonia recommended for Windows+Linux)
- `EasyAp.Core/` (future) - workflow/services:
  - Download/extract service
  - Nameserver/config service
  - Build runner
  - ADB/device/install service
  - Bundle push service

## Build plan (future)

1. Choose cross-platform UI framework (Avalonia recommended) for Windows/Linux parity.
2. Implement core workflow services with cancellation, progress events, and structured logging.
3. Port adb install flow (`push` + `pm install-create/write/commit`) with signature-mismatch uninstall confirmation.
4. Add packaging:
   - Windows: publish single-file/self-contained `.exe` (and installer if desired)
   - Linux: publish self-contained app + package as `.AppImage`
5. Validate against current Python behavior and replace/ship alongside Python app.

## Current status

Scaffold only (no functional implementation yet). Use `../easy_ap_gui.py` for the working flow.
