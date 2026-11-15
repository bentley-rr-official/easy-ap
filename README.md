# easy-ap

Simple GUI helper for downloading, building, installing, and pushing bundles for the **2025 Android Patcher**.

## What it does

The GUI asks for:
- **Work directory** (where files are downloaded/built)
- **Nameserver** (only this value is configured; written as `RecNet NameServer Host` in `2025.cfg`)
- **Device package** (used for bundle push target, default `com.AgainstGravity.RecRoom`)

Actions:

1. **Download patcher (zip)**  
   Downloads and extracts:  
   `https://github.com/bentley-rr-official/2025-android-patcher/archive/refs/heads/main.zip`  
   into `<workdir>/2025-android-patcher`.

2. **Download `base.xapk`**  
   Downloads to `<workdir>/base.xapk` using:
   ```bash
   curl -L "https://drive.usercontent.google.com/download?id=1k9ASR35hKhZX4QftctMHmuJCWRG2s04p&export=download&authuser=0&confirm=t" -o base.xapk
   ```

3. **Download & extract bundles**  
   Downloads `bundles.zip` to `<workdir>/bundles.zip` using:
   ```bash
   curl -L "https://drive.usercontent.google.com/download?id=1o42Q81c9G_fNceEiXSfHEOFjUPx23z6E&export=download&authuser=0" -o bundles.zip
   ```
   Then extracts files into `<workdir>/2025-android-patcher/bundles/`.

4. **Build**  
   Writes `<workdir>/2025-android-patcher/2025.cfg` with the provided nameserver and runs:
   ```bash
   bash scripts/build-phone.sh <workdir>/base.xapk
   ```

5. **Install to phone**  
   Runs `build/phone/signed/install.sh` if present (otherwise falls back to `adb install-multiple`).

6. **Push bundles to phone**  
   Pushes `*.bundle` files from `<workdir>/2025-android-patcher/bundles/` to:
   ```text
   /sdcard/Android/data/<package>/files/AssetPackStubs/OutfitsAssetPack/
   ```

You can run steps individually or use **Run all (1 → 6)**.

## Requirements

- Python 3 + Tkinter (`python3-tk` on some Linux distros)
- `curl`
- `bash`, `unzip`, `adb` (for install/push)
- Build dependencies required by the patcher (e.g. `java`, `python3` + `lief`, `zipalign`/`apksigner`, `tools/debug.keystore`, Android NDK r27c, etc. as described in the patcher repo)

## Run

```bash
python3 easy_ap_gui.py
```

## Notes

- Enter the **nameserver** before building (step 4 requires it).
- Build/install steps depend on your local toolchain and a connected ADB device; check the log panel for errors from underlying commands.
- This tool downloads and runs external code/files; review sources and use at your own risk.
