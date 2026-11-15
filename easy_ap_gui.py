#!/usr/bin/env python3
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

PATCH_ZIP_URL = "https://github.com/bentley-rr-official/2025-android-patcher/archive/refs/heads/main.zip"
XAPK_URL = "https://drive.usercontent.google.com/download?id=1k9ASR35hKhZX4QftctMHmuJCWRG2s04p&export=download&authuser=0&confirm=t"
BUNDLES_URL = "https://drive.usercontent.google.com/download?id=1o42Q81c9G_fNceEiXSfHEOFjUPx23z6E&export=download&authuser=0"
DEFAULT_PACKAGE = "com.AgainstGravity.RecRoom"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("easy-ap")
        self.geometry("940x760")
        self.minsize(820, 640)

        self.workdir_var = tk.StringVar(value=str(Path.home() / "easy-ap-work"))
        self.nameserver_var = tk.StringVar(value="")
        self.package_var = tk.StringVar(value=DEFAULT_PACKAGE)
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.busy = False

        self._build_ui()
        self.after(100, self._drain_log)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Work directory:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.workdir_var, width=70).grid(row=0, column=1, sticky="we", padx=6)
        ttk.Button(top, text="Browse...", command=self.browse_dir).grid(row=0, column=2)

        ttk.Label(top, text="Nameserver:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(top, textvariable=self.nameserver_var, width=70).grid(row=1, column=1, sticky="we", padx=6, pady=(8, 0))
        ttk.Label(top, text="(only this value is written to 2025.cfg)").grid(row=1, column=2, sticky="w", pady=(8, 0))

        ttk.Label(top, text="Device package (for bundle push):").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(top, textvariable=self.package_var, width=70).grid(row=2, column=1, sticky="we", padx=6, pady=(8, 0))
        top.columnconfigure(1, weight=1)

        actions = ttk.LabelFrame(self, text="Actions")
        actions.pack(fill="x", **pad)

        self.btn_patches = ttk.Button(actions, text="1) Download patcher (zip)", command=self.download_patches)
        self.btn_xapk = ttk.Button(actions, text="2) Download base.xapk", command=self.download_xapk)
        self.btn_bundles = ttk.Button(actions, text="3) Download & extract bundles", command=self.download_bundles)
        self.btn_build = ttk.Button(actions, text="4) Build", command=self.build_project)
        self.btn_install = ttk.Button(actions, text="5) Install to phone", command=self.install_phone)
        self.btn_push = ttk.Button(actions, text="6) Push bundles to phone", command=self.push_bundles)
        self.btn_all = ttk.Button(actions, text="Run all (1 → 6)", command=self.run_all)
        self.btn_open = ttk.Button(actions, text="Open work folder", command=self.open_folder)

        buttons = [
            (self.btn_patches, 0, 0), (self.btn_xapk, 0, 1), (self.btn_bundles, 0, 2),
            (self.btn_build, 1, 0), (self.btn_install, 1, 1), (self.btn_push, 1, 2),
            (self.btn_all, 2, 0), (self.btn_open, 2, 1),
        ]
        for b, r, c in buttons:
            b.grid(row=r, column=c, sticky="we", padx=6, pady=6)
        for i in range(3):
            actions.columnconfigure(i, weight=1)

        info = ttk.LabelFrame(self, text="Info")
        info.pack(fill="x", **pad)
        msg = (
            "• Patcher zip source: https://github.com/bentley-rr-official/2025-android-patcher/archive/refs/heads/main.zip\n"
            "• Extracted to: <workdir>/2025-android-patcher  |  base.xapk: <workdir>/base.xapk  |  bundles.zip: <workdir>/bundles.zip\n"
            "• Build writes 2025.cfg (Nameserver only) in the patcher folder and runs scripts/build-phone.sh on base.xapk\n"
            "• Install runs build/phone/signed/install.sh (requires adb + connected device)\n"
            "• Push bundles copies <workdir>/2025-android-patcher/bundles/*.bundle to /sdcard/Android/data/<package>/files/AssetPackStubs/OutfitsAssetPack/\n"
            "• Build requirements on this machine: bash, python3, java, lief, zipalign/apksigner, tools/debug.keystore, Android NDK r27c (see patcher README)"
        )
        ttk.Label(info, text=msg, justify="left", wraplength=880).pack(anchor="w", padx=8, pady=6)

        logf = ttk.LabelFrame(self, text="Log")
        logf.pack(fill="both", expand=True, **pad)
        self.log = scrolledtext.ScrolledText(logf, height=18, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status_var, anchor="w").pack(fill="x", padx=12, pady=(0, 8))

    def browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.workdir_var.get() or str(Path.home()))
        if d:
            self.workdir_var.set(d)

    def log_msg(self, msg: str):
        self.log_queue.put(msg)

    def _drain_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", msg + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    def set_busy(self, busy: bool, status: str = ""):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_patches, self.btn_xapk, self.btn_bundles, self.btn_build, self.btn_install, self.btn_push, self.btn_all):
            b.configure(state=state)
        if status:
            self.status_var.set(status)
        elif not busy:
            self.status_var.set("Ready")

    def run_task(self, title, func):
        if self.busy:
            return
        self.set_busy(True, f"Running: {title}...")
        self.log_msg(f"\n== {title} ==")

        def worker():
            try:
                func()
                self.log_msg(f"[OK] {title} completed")
                self.after(0, lambda: self.set_busy(False, "Done"))
            except Exception as e:
                self.log_msg(f"[ERROR] {e}")
                self.after(0, lambda: messagebox.showerror("easy-ap", str(e)))
                self.after(0, lambda: self.set_busy(False, "Error"))

        threading.Thread(target=worker, daemon=True).start()

    def workdir(self) -> Path:
        p = Path(self.workdir_var.get()).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def patcher_dir(self) -> Path:
        return self.workdir() / "2025-android-patcher"

    def run_cmd(self, cmd, cwd=None, env=None):
        self.log_msg("$ " + " ".join(cmd))
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            self.log_msg(line.rstrip())
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"Command failed ({rc}): {' '.join(cmd)}")

    def ensure_nameserver(self) -> str:
        ns = self.nameserver_var.get().strip()
        if not ns:
            raise RuntimeError("Nameserver is required (enter it in the Nameserver field).")
        return ns

    def write_config(self, patcher: Path, nameserver: str):
        cfg = f"""[App]
Package Name = 

[Server]
RecNet NameServer Host = {nameserver}
Oculus App Id =

[Photon]
App Id Realtime =
App Id Voice =
App Id Chat =
Photon NameServer =
Photon NameServer Port = 0

[Advanced]
Log HTTP = true
Debug = false
Log HTTP Body Max = 10000
Log Noisy Endpoints = false
"""
        (patcher / "2025.cfg").write_text(cfg, encoding="utf-8")
        self.log_msg(f"Wrote {patcher / '2025.cfg'} with RecNet NameServer Host = {nameserver}")

    # --- actions ---
    def download_patches(self):
        self.run_task("Download patcher", self._download_patches)

    def _download_patches(self):
        wd = self.workdir()
        dest = wd / "2025-android-patcher"
        zip_path = wd / "2025-android-patcher.zip"
        if dest.exists():
            self.log_msg(f"Removing existing {dest} ...")
            shutil.rmtree(dest)
        self.run_cmd(["curl", "-L", PATCH_ZIP_URL, "-o", str(zip_path)], cwd=wd)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(wd)
        extracted = wd / "2025-android-patcher-main"
        if not extracted.exists():
            # fallback: find a single top-level dir
            dirs = [p for p in wd.iterdir() if p.is_dir() and p.name.startswith("2025-android-patcher")]
            if len(dirs) == 1:
                extracted = dirs[0]
            else:
                raise RuntimeError("Could not locate extracted patcher folder after unzip")
        extracted.rename(dest)
        zip_path.unlink(missing_ok=True)
        self.log_msg(f"Patcher ready at {dest}")

    def download_xapk(self):
        self.run_task("Download base.xapk", self._download_xapk)

    def _download_xapk(self):
        wd = self.workdir()
        out = wd / "base.xapk"
        self.run_cmd(["curl", "-L", XAPK_URL, "-o", str(out)], cwd=wd)
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError("base.xapk download failed or file is empty")
        self.log_msg(f"Saved: {out} ({out.stat().st_size} bytes)")

    def download_bundles(self):
        self.run_task("Download and extract bundles", self._download_bundles)

    def _download_bundles(self):
        wd = self.workdir()
        patcher = self.patcher_dir()
        zip_path = wd / "bundles.zip"
        self.run_cmd(["curl", "-L", BUNDLES_URL, "-o", str(zip_path)], cwd=wd)
        if not zip_path.exists() or zip_path.stat().st_size == 0:
            raise RuntimeError("bundles.zip download failed or file is empty")

        bundles_dir = patcher / "bundles"
        bundles_dir.mkdir(parents=True, exist_ok=True)
        self.log_msg(f"Extracting bundles to {bundles_dir} ...")
        count = 0
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = Path(info.filename).name
                if not name:
                    continue
                target = bundles_dir / name
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                if name.endswith(".bundle"):
                    count += 1
        self.log_msg(f"Extracted {count} *.bundle files into {bundles_dir}")

    def build_project(self):
        self.run_task("Build", self._build_project)

    def _build_project(self):
        wd = self.workdir()
        patcher = self.patcher_dir()
        xapk = wd / "base.xapk"
        if not patcher.exists():
            raise RuntimeError(f"Patcher not found: {patcher} (run step 1 first)")
        if not xapk.exists():
            raise RuntimeError(f"base.xapk not found: {xapk} (run step 2 first)")
        nameserver = self.ensure_nameserver()
        self.write_config(patcher, nameserver)

        build_sh = patcher / "scripts" / "build-phone.sh"
        if not build_sh.exists():
            raise RuntimeError(f"Missing build script: {build_sh}")
        env = os.environ.copy()
        # Keep CONFIG explicit to be sure
        env["CONFIG"] = str(patcher / "2025.cfg")
        self.run_cmd(["bash", str(build_sh), str(xapk)], cwd=patcher, env=env)

    def install_phone(self):
        self.run_task("Install to phone", self._install_phone)

    def _install_phone(self):
        patcher = self.patcher_dir()
        signed = patcher / "build" / "phone" / "signed"
        install_sh = signed / "install.sh"
        install_ps1 = signed / "install.ps1"
        if install_sh.exists():
            self.run_cmd(["bash", str(install_sh)], cwd=signed)
            return
        if install_ps1.exists() and shutil.which("pwsh"):
            self.run_cmd(["pwsh", "-File", str(install_ps1)], cwd=signed)
            return
        # fallback: adb install-multiple *.apk
        apks = sorted(signed.glob("*.apk"))
        if not apks:
            raise RuntimeError(f"No install script or APKs found in {signed} (build first)")
        self.run_cmd(["adb", "install-multiple", "-r"] + [str(a) for a in apks], cwd=signed)

    def push_bundles(self):
        self.run_task("Push bundles to phone", self._push_bundles)

    def _push_bundles(self):
        patcher = self.patcher_dir()
        bundles_dir = patcher / "bundles"
        if not bundles_dir.exists():
            raise RuntimeError(f"Bundles folder not found: {bundles_dir} (run step 3 first)")
        bundle_files = sorted([p for p in bundles_dir.iterdir() if p.is_file() and p.suffix == ".bundle"])
        if not bundle_files:
            # push any files present
            bundle_files = sorted([p for p in bundles_dir.iterdir() if p.is_file()])
        if not bundle_files:
            raise RuntimeError(f"No bundle files found in {bundles_dir}")

        pkg = self.package_var.get().strip() or DEFAULT_PACKAGE
        remote = f"/sdcard/Android/data/{pkg}/files/AssetPackStubs/OutfitsAssetPack"
        self.run_cmd(["adb", "shell", "mkdir", "-p", remote])
        # Push files; adb push dir/. copies contents
        # Use a temp staging dir with only selected files to avoid pushing unrelated stuff if desired
        for f in bundle_files:
            self.run_cmd(["adb", "push", str(f), f"{remote}/{f.name}"])
        self.log_msg(f"Pushed {len(bundle_files)} file(s) to {remote}")

    def run_all(self):
        self.run_task("Run all", self._run_all)

    def _run_all(self):
        self._download_patches()
        self._download_xapk()
        self._download_bundles()
        self._build_project()
        self._install_phone()
        self._push_bundles()

    def open_folder(self):
        wd = self.workdir()
        path = str(wd)
        try:
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", path])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            elif os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                messagebox.showinfo("easy-ap", f"Folder: {path}")
        except Exception as e:
            messagebox.showinfo("easy-ap", f"Folder: {path}\n({e})")


if __name__ == "__main__":
    app = App()
    app.mainloop()
