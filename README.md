# easy-ap

Simple GUI helper for downloading the **2025 Android Patcher** and required files.

## What it does

The GUI can:

1. **Download patches from GitHub**  
   Clones/updates [`bentley-rr-official/2025-android-patcher`](https://github.com/bentley-rr-official/2025-android-patcher) into `<workdir>/2025-android-patcher` (falls back to downloading the repo zip if `git` is unavailable).

2. **Download `base.xapk`**  
   Downloads to `<workdir>/base.xapk` using:
   ```bash
   curl -L "https://drive.usercontent.google.com/download?id=1k9ASR35hKhZX4QftctMHmuJCWRG2s04p&export=download&authuser=0&confirm=t" -o base.xapk
   ```

3. **Download and extract `bundles.zip`**  
   Downloads to `<workdir>/bundles.zip` using:
   ```bash
   curl -L "https://drive.usercontent.google.com/download?id=1o42Q81c9G_fNceEiXSfHEOFjUPx23z6E&export=download&authuser=0" -o bundles.zip
   ```
   Then extracts files into `<workdir>/2025-android-patcher/bundles/` (so bundle files are in the patcher repo’s `bundles/` folder).

## Requirements

- Python 3
- Tkinter (`python3-tk` on some Linux distros)
- `curl`
- `git` (recommended; zip fallback is used if missing)
- Internet access

## Run

```bash
python3 easy_ap_gui.py
```

Choose a work directory in the app, then run the actions individually or click **Run all (1 → 2 → 3)**.

## Notes

- Download the patches first if you want `bundles.zip` extracted directly into the patcher’s `bundles/` directory.
- Large downloads may take time; progress/output is shown in the log panel.
- Files are saved locally in your selected work directory. Review and trust download sources before use.
