#!/usr/bin/env python3
import os
import queue
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

PATCH_REPO = "https://github.com/bentley-rr-official/2025-android-patcher.git"
PATCH_ZIP_URL = "https://github.com/bentley-rr-official/2025-android-patcher/archive/refs/heads/main.zip"
XAPK_URL = "https://drive.usercontent.google.com/download?id=1k9ASR35hKhZX4QftctMHmuJCWRG2s04p&export=download&authuser=0&confirm=t"
BUNDLES_URL = "https://drive.usercontent.google.com/download?id=1o42Q81c9G_fNceEiXSfHEOFjUPx23z6E&export=download&authuser=0"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("easy-ap")
        self.geometry("860x620")
        self.minsize(760, 520)

        self.workdir_var = tk.StringVar(value=str(Path.home() / "easy-ap-work"))
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.busy = False

        self._build_ui()
        self.after(100, self._drain_log)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        frm = ttk.Frame(self)
        frm.pack(fill="x", **pad)

        ttk.Label(frm, text="Work directory:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.workdir_var, width=70).grid(row=0, column=1, sticky="we", padx=6)
        ttk.Button(frm, text="Browse...", command=self.browse_dir).grid(row=0, column=2)
        frm.columnconfigure(1, weight=1)

        actions = ttk.LabelFrame(self, text="Actions")
        actions.pack(fill="x", **pad)

        self.btn_patches = ttk.Button(actions, text="1) Download patches (GitHub)", command=self.download_patches)
        self.btn_xapk = ttk.Button(actions, text="2) Download base.xapk", command=self.download_xapk)
        self.btn_bundles = ttk.Button(actions, text="3) Download & extract bundles.zip", command=self.download_bundles)
        self.btn_all = ttk.Button(actions, text="Run all (1 → 2 → 3)", command=self.run_all)
        self.btn_open = ttk.Button(actions, text="Open work folder", command=self.open_folder)

        self.btn_patches.grid(row=0, column=0, sticky="we", padx=6, pady=6)
        self.btn_xapk.grid(row=0, column=1, sticky="we", padx=6, pady=6)
        self.btn_bundles.grid(row=0, column=2, sticky="we", padx=6, pady=6)
        self.btn_all.grid(row=1, column=0, sticky="we", padx=6, pady=6)
        self.btn_open.grid(row=1, column=1, sticky="we", padx=6, pady=6)
        for i in range(3):
            actions.columnconfigure(i, weight=1)

        info = ttk.LabelFrame(self, text="Info")
        info.pack(fill="x", **pad)
        msg = (
            "• Patches are cloned/downloaded into: <workdir>/2025-android-patcher\n"
            "• base.xapk is downloaded to: <workdir>/base.xapk\n"
            "• bundles.zip is downloaded to: <workdir>/bundles.zip and extracted so *.bundle files end up in: <workdir>/2025-android-patcher/bundles/\n"
            "• Requires: git, curl, unzip (or Python zip extraction fallback), and internet access."
        )
        ttk.Label(info, text=msg, justify="left").pack(anchor="w", padx=8, pady=6)

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
        for b in (self.btn_patches, self.btn_xapk, self.btn_bundles, self.btn_all):
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

    def run_cmd(self, cmd, cwd=None):
        self.log_msg("$ " + " ".join(cmd))
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
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

    def download_patches(self):
        self.run_task("Download patches", self._download_patches)

    def _download_patches(self):
        wd = self.workdir()
        dest = wd / "2025-android-patcher"
        if (dest / ".git").exists():
            self.log_msg(f"Repo exists, pulling latest in {dest}")
            self.run_cmd(["git", "-C", str(dest), "pull", "--ff-only"])
            return
        if dest.exists() and any(dest.iterdir()):
            raise RuntimeError(f"{dest} exists and is not a git repo. Move/rename it or choose another work directory.")
        if shutil.which("git"):
            self.run_cmd(["git", "clone", PATCH_REPO, str(dest)], cwd=wd)
        else:
            self.log_msg("git not found, downloading zip archive...")
            zip_path = wd / "2025-android-patcher.zip"
            self.run_cmd(["curl", "-L", PATCH_ZIP_URL, "-o", str(zip_path)], cwd=wd)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(wd)
            extracted = wd / "2025-android-patcher-main"
            if not extracted.exists():
                raise RuntimeError("Unexpected archive layout; expected 2025-android-patcher-main folder")
            extracted.rename(dest)
            zip_path.unlink(missing_ok=True)

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
        zip_path = wd / "bundles.zip"
        self.run_cmd(["curl", "-L", BUNDLES_URL, "-o", str(zip_path)], cwd=wd)
        if not zip_path.exists() or zip_path.stat().st_size == 0:
            raise RuntimeError("bundles.zip download failed or file is empty")

        patcher = wd / "2025-android-patcher"
        bundles_dir = patcher / "bundles"
        bundles_dir.mkdir(parents=True, exist_ok=True)

        self.log_msg(f"Extracting bundles to {bundles_dir} ...")
        count = 0
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = Path(info.filename).name
                target = bundles_dir / name
                # Prefer *.bundle files; also extract everything else into bundles dir as-is by name
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                if name.endswith(".bundle"):
                    count += 1
        self.log_msg(f"Extracted {count} *.bundle files (and any other files) into {bundles_dir}")
        self.log_msg(f"Zip saved at: {zip_path}")

    def run_all(self):
        self.run_task("Run all", self._run_all)

    def _run_all(self):
        self._download_patches()
        self._download_xapk()
        self._download_bundles()

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
