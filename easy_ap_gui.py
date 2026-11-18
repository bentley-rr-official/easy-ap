#!/usr/bin/env python3
import json
import os
import platform
import queue
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_TITLE = "2025RR - Rec Room Patcher"
APP_SHORT = "2025RR"
PATCH_ZIP_URL = "https://github.com/bentley-rr-official/2025-android-patcher/archive/refs/heads/main.zip"
XAPK_URL = "https://rrcdn-25.recuni.org/dl/base.xapk"
BUNDLES_URL = "https://rrcdn-25.recuni.org/dl/bundles.zip"
DEFAULTS = {
    "app_title": APP_TITLE,
    "package_name": "com.AgainstGravity.RecRoom",
    "remote_bundles_dir": "/sdcard/Android/data/{package}/files/AssetPackStubs/OutfitsAssetPack",
    "workdir": "",
    "bash_command": "",
    "adb_command": "",
    "auto_start": True,
    "clean_workdir": True,
    "default_nameserver_url": "",
    "pairip_keep_startup": "0",
}

# Blue/white theme
C_BG = "#f4f8ff"
C_CARD = "#ffffff"
C_PRIMARY = "#1e88e5"
C_PRIMARY_DARK = "#1565c0"
C_ACCENT = "#42a5f5"
C_TEXT = "#0f2942"
C_MUTED = "#5f738a"
C_BORDER = "#d7e6f7"
C_SUCCESS = "#1b8f5a"
C_WARN = "#b45309"
C_ERROR = "#c62828"


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def tool_cache_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "2025RR" / "tools"
    base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    return base / "2025rr" / "tools"


def download_cache_dir() -> Path:
    d = tool_cache_dir().parent / "downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_workdir() -> Path:
    env = os.environ.get("RR2025_PATCH_WORKDIR") or os.environ.get("EASY_AP_WORKDIR")
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("TEMP") or tempfile.gettempdir())
    else:
        base = Path(tempfile.gettempdir())
    return base / "2025rr"


def load_settings() -> dict:
    return dict(DEFAULTS)


def save_settings(s: dict):
    # Settings are kept in memory for this session only.
    return


def fmt_bytes(n: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def is_valid_nameserver_url(value: str) -> bool:
    try:
        u = urlparse(value.strip())
        return u.scheme in ("http", "https") and bool(u.hostname)
    except Exception:
        return False


def normalize_nameserver_host(url: str) -> str:
    u = urlparse(url.strip())
    host = u.hostname or ""
    if u.port:
        host = f"{host}:{u.port}"
    return host


def split_cmd(value: str):
    if not value:
        return []
    if os.name == "nt":
        try:
            return shlex.split(value, posix=False)
        except Exception:
            return [value]
    return shlex.split(value)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.title(self.settings.get("app_title") or APP_TITLE)
        self.geometry("1020x720")
        self.minsize(900, 620)
        self.configure(bg=C_BG)

        wd = self.settings.get("workdir") or ""
        self.workdir = Path(wd).expanduser() if wd else default_workdir()
        self.nameserver_url = (self.settings.get("default_nameserver_url") or "").strip()
        self.nameserver_host = normalize_nameserver_host(self.nameserver_url) if is_valid_nameserver_url(self.nameserver_url) else ""
        self.package = (self.settings.get("package_name") or DEFAULTS["package_name"]).strip() or DEFAULTS["package_name"]
        self.uiq: queue.Queue = queue.Queue()
        self.selected_device = None
        self.device_event = threading.Event()
        self.nameserver_event = threading.Event()
        self.confirm_event = threading.Event()
        self.confirm_result = False
        self.file_event = threading.Event()
        self.file_result = ""
        self.running = False

        self._setup_style()
        self._build_ui()
        self.after(100, self._drain_ui)
        if self.settings.get("auto_start", True):
            self.after(500, self.start_auto)
        else:
            self.status_var.set("Ready")
            self.step_var.set("Click \"Start / Restart patch process\" when you're ready to begin")
            self.overall_text.set("Waiting to start")
            self.item_var.set("Auto-start is turned off")
            self.item_detail.set("Check Settings if needed, then start when you're ready. 2025RR will guide you through patching Rec Room.")

    # ---------- UI ----------
    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        default_font = ("Segoe UI", 10) if os.name == "nt" else ("Segoe UI", 10)
        self.option_add("*Font", default_font)
        style.configure(".", background=C_BG, foreground=C_TEXT)
        style.configure("TFrame", background=C_BG)
        style.configure("Card.TFrame", background=C_CARD)
        style.configure("TLabel", background=C_BG, foreground=C_TEXT)
        style.configure("Card.TLabel", background=C_CARD, foreground=C_TEXT)
        style.configure("Muted.TLabel", background=C_BG, foreground=C_MUTED)
        style.configure("CardMuted.TLabel", background=C_CARD, foreground=C_MUTED)
        style.configure("Title.TLabel", background=C_BG, foreground=C_PRIMARY_DARK, font=("Segoe UI", 21, "bold"))
        style.configure("Subtitle.TLabel", background=C_BG, foreground=C_MUTED, font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=C_CARD, foreground=C_PRIMARY_DARK, font=("Segoe UI", 11, "bold"))
        style.configure("Status.TLabel", background=C_CARD, foreground=C_TEXT, font=("Segoe UI", 12, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 8), foreground="white", background=C_PRIMARY)
        style.map("Primary.TButton", background=[("active", C_PRIMARY_DARK), ("pressed", C_PRIMARY_DARK), ("disabled", "#9ec7ea")], foreground=[("disabled", "#eef6ff")])
        style.configure("Secondary.TButton", font=("Segoe UI", 10), padding=(12, 7), foreground=C_PRIMARY_DARK, background="#eaf4ff")
        style.map("Secondary.TButton", background=[("active", "#dcebff"), ("pressed", "#dcebff")])
        style.configure("Blue.Horizontal.TProgressbar", troughcolor="#e7f1fb", background=C_PRIMARY, bordercolor="#e7f1fb", lightcolor=C_ACCENT, darkcolor=C_PRIMARY)

    def _card(self, parent, title, row, pady=(0, 10), expand=False):
        outer = tk.Frame(parent, bg=C_BORDER, bd=0, highlightthickness=0)
        outer.grid(row=row, column=0, sticky="nsew" if expand else "ew", pady=pady)
        inner = tk.Frame(outer, bg=C_CARD, bd=0, highlightthickness=0)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        if title:
            ttk.Label(inner, text=title, style="Header.TLabel").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 6))
            body = tk.Frame(inner, bg=C_CARD)
            body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 12))
        else:
            body = inner
            body.grid(row=0, column=0, sticky="nsew", padx=14, pady=12)
        inner.columnconfigure(0, weight=1)
        if expand:
            inner.rowconfigure(1, weight=1)
            body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        return body

    def _build_ui(self):
        root = tk.Frame(self, bg=C_BG)
        root.pack(fill="both", expand=True, padx=18, pady=16)

        header = tk.Frame(root, bg=C_BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(header, text="2025RR Rec Room Patcher", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="A friendly step-by-step app to patch and install Rec Room (2025 Android) on your device", style="Subtitle.TLabel").grid(row=1, column=0, sticky="w")

        status_body = self._card(root, "Status", 1)
        self.status_var = tk.StringVar(value="Starting...")
        self.step_var = tk.StringVar(value="Preparing your 2025RR patch setup")
        ttk.Label(status_body, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(status_body, textvariable=self.step_var, style="CardMuted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 10))
        self.overall = ttk.Progressbar(status_body, mode="determinate", maximum=100, style="Blue.Horizontal.TProgressbar")
        self.overall.grid(row=2, column=0, sticky="ew")
        self.overall_text = tk.StringVar(value="0%")
        ttk.Label(status_body, textvariable=self.overall_text, style="CardMuted.TLabel").grid(row=3, column=0, sticky="w", pady=(6, 0))

        item_body = self._card(root, "Current progress", 2)
        self.item_var = tk.StringVar(value="Waiting...")
        ttk.Label(item_body, textvariable=self.item_var, style="Card.TLabel", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.item_progress = ttk.Progressbar(item_body, mode="determinate", maximum=100, style="Blue.Horizontal.TProgressbar")
        self.item_progress.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.item_detail = tk.StringVar(value="")
        ttk.Label(item_body, textvariable=self.item_detail, style="CardMuted.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 0))

        # Device & prompts card with ADB help
        dev_outer = tk.Frame(root, bg=C_BORDER, bd=0, highlightthickness=0)
        dev_outer.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        dev_inner = tk.Frame(dev_outer, bg=C_CARD, bd=0, highlightthickness=0)
        dev_inner.pack(fill="both", expand=True, padx=1, pady=1)
        dev_header = tk.Frame(dev_inner, bg=C_CARD)
        dev_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        ttk.Label(dev_header, text="Device & prompts", style="Header.TLabel").pack(side="left")
        help_btn = tk.Button(dev_header, text="?", width=2, command=self.show_adb_help,
                             bg="#eaf4ff", fg=C_PRIMARY_DARK, activebackground="#dcebff",
                             relief="flat", bd=0, highlightthickness=0, cursor="hand2", font=("Segoe UI", 10, "bold"))
        help_btn.pack(side="left", padx=(8, 0))
        dev_body = tk.Frame(dev_inner, bg=C_CARD)
        dev_body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 12))
        dev_inner.columnconfigure(0, weight=1)
        dev_body.columnconfigure(0, weight=1)
        dev_outer.columnconfigure(0, weight=1)
        self.device_info_var = tk.StringVar(value="No device action needed yet.")
        ttk.Label(dev_body, textvariable=self.device_info_var, style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.device_buttons_frame = tk.Frame(dev_body, bg=C_CARD)
        self.device_buttons_frame.grid(row=1, column=0, sticky="w", pady=(8, 0))

        # Build log card (shown only while building)
        self.build_log_outer = tk.Frame(root, bg=C_BORDER, bd=0, highlightthickness=0)
        log_inner = tk.Frame(self.build_log_outer, bg=C_CARD, bd=0, highlightthickness=0)
        log_inner.pack(fill="both", expand=True, padx=1, pady=1)
        ttk.Label(log_inner, text="Build log", style="Header.TLabel").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 6))
        log_body = tk.Frame(log_inner, bg=C_CARD)
        log_body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 12))
        self.log_text = tk.Text(log_body, height=12, wrap="word", bg="#f7fbff", fg=C_TEXT, bd=0, highlightthickness=1,
                                highlightbackground=C_BORDER, relief="flat", font=("Consolas", 9) if os.name == "nt" else ("DejaVu Sans Mono", 9))
        log_scroll = ttk.Scrollbar(log_body, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set, state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")
        log_body.columnconfigure(0, weight=1)
        log_body.rowconfigure(0, weight=1)
        log_inner.columnconfigure(0, weight=1)
        log_inner.rowconfigure(1, weight=1)
        self.build_log_outer.columnconfigure(0, weight=1)
        self.build_log_visible = False
        self._keep_log_visible = False

        actions = tk.Frame(root, bg=C_BG)
        actions.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        self.start_btn = ttk.Button(actions, text="Start / Restart patch process", style="Primary.TButton", command=self.start_auto)
        self.start_btn.pack(side="left")
        ttk.Button(actions, text="Settings", style="Secondary.TButton", command=self.open_settings).pack(side="left", padx=8)
        ttk.Button(actions, text="Open work folder", style="Secondary.TButton", command=self.open_workdir).pack(side="left")

        root.columnconfigure(0, weight=1)
        root.rowconfigure(4, weight=1)

    def show_adb_help(self):
        message = (
            "ADB (Android Debug Bridge) lets 2025RR install the patched Rec Room app and push bundles to your Android device over USB.\n\n"
            "To get it working:\n"
            "1. Enable Developer options on your phone (usually tap Build number several times in Settings > About phone).\n"
            "2. Turn on USB debugging in Developer options.\n"
            "3. Connect your phone with a data USB cable, unlock it, and allow USB debugging for this computer when prompted.\n"
            "4. If 2025RR can't find ADB automatically, you can install Android platform-tools or set the ADB path in Settings.\n\n"
            "More help (official Android guide):\n"
            "https://developer.android.com/tools/adb#Enabling"
        )
        win = tk.Toplevel(self)
        win.title("ADB help")
        win.configure(bg=C_BG)
        win.transient(self)
        frm = tk.Frame(win, bg=C_CARD, padx=14, pady=14)
        frm.pack(fill="both", expand=True, padx=12, pady=12)
        lbl = tk.Label(frm, text=message, justify="left", anchor="w", bg=C_CARD, fg=C_TEXT, wraplength=620, font=("Segoe UI", 10))
        lbl.pack(fill="both", expand=True)
        link = tk.Label(frm, text="Open ADB guide in browser", fg=C_PRIMARY_DARK, bg=C_CARD, cursor="hand2", font=("Segoe UI", 10, "underline"))
        link.pack(anchor="w", pady=(8, 0))
        import webbrowser
        link.bind("<Button-1>", lambda e: webbrowser.open("https://developer.android.com/tools/adb#Enabling"))
        ttk.Button(frm, text="Close", style="Secondary.TButton", command=win.destroy).pack(anchor="e", pady=(12, 0))

    def set_build_log_visible(self, visible: bool):
        def _do():
            if visible and not self.build_log_visible:
                self.build_log_outer.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
                self.build_log_visible = True
            elif not visible and self.build_log_visible:
                self.build_log_outer.grid_remove()
                self.build_log_visible = False
        self.ui(_do)

    def clear_build_log(self):
        def _do():
            try:
                self.log_text.configure(state="normal")
                self.log_text.delete("1.0", "end")
                self.log_text.configure(state="disabled")
            except Exception:
                pass
        self.ui(_do)

    def append_build_log(self, msg: str):
        def _do():
            try:
                self.log_text.configure(state="normal")
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
            except Exception:
                pass
        self.ui(_do)

    def open_workdir(self):
        try:
            self.workdir.mkdir(parents=True, exist_ok=True)
            if sys.platform.startswith("win"):
                os.startfile(str(self.workdir))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.workdir)])
            else:
                subprocess.Popen(["xdg-open", str(self.workdir)])
        except Exception as e:
            messagebox.showerror(APP_SHORT, f"Could not open work folder:\n{e}")

    def log(self, msg: str):
        print(msg, flush=True)
        try:
            self.append_build_log(str(msg))
        except Exception:
            pass

    def ui(self, fn, *args):
        self.uiq.put((fn, args))

    def _drain_ui(self):
        try:
            while True:
                fn, args = self.uiq.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.after(100, self._drain_ui)

    def _set_status(self, status=None, step=None, overall=None, overall_mode=None, overall_text=None,
                    item=None, item_value=None, item_mode=None, item_detail=None):
        if status is not None: self.status_var.set(status)
        if step is not None: self.step_var.set(step)
        if overall_mode is not None:
            cur = str(self.overall.cget('mode'))
            if cur == 'indeterminate' and overall_mode != 'indeterminate':
                try: self.overall.stop()
                except Exception: pass
            self.overall.configure(mode=overall_mode)
            if overall_mode == 'indeterminate' and cur != 'indeterminate':
                try: self.overall.start(10)
                except Exception: pass
        if overall is not None and str(self.overall.cget('mode')) == 'determinate':
            self.overall['value'] = max(0, min(100, overall))
        if overall_text is not None: self.overall_text.set(overall_text)

        if item is not None: self.item_var.set(item)
        if item_mode is not None:
            cur = str(self.item_progress.cget('mode'))
            if cur == 'indeterminate' and item_mode != 'indeterminate':
                try: self.item_progress.stop()
                except Exception: pass
            self.item_progress.configure(mode=item_mode)
            if item_mode == 'indeterminate' and cur != 'indeterminate':
                try: self.item_progress.start(10)
                except Exception: pass
        if item_value is not None and str(self.item_progress.cget('mode')) == 'determinate':
            self.item_progress['value'] = max(0, min(100, item_value))
        if item_detail is not None: self.item_detail.set(item_detail)

    def set_progress(self, **kw):
        self.ui(lambda: self._set_status(**kw))

    # ---------- settings/customization ----------
    def open_settings(self):
        if self.running:
            messagebox.showinfo(APP_SHORT, "Please wait for the current Rec Room patch process to finish before changing settings.", parent=self)
            return
        win = tk.Toplevel(self)
        win.title(f"{APP_SHORT} - Settings")
        win.geometry("760x520")
        win.configure(bg=C_BG)
        win.transient(self)

        frm = tk.Frame(win, bg=C_BG)
        frm.pack(fill="both", expand=True, padx=14, pady=14)
        fields = [
            ("App package name", "package_name"),
            ("Bundles device path ({package} allowed)", "remote_bundles_dir"),
            ("Work directory (blank = default)", "workdir"),
            ("Bash command (blank = auto, Windows needs Git Bash/WSL bash)", "bash_command"),
            ("ADB command/path (blank = auto)", "adb_command"),
            ("Default nameserver URL (optional)", "default_nameserver_url"),
        ]
        vars_map = {}
        for i, (label, key) in enumerate(fields):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=4)
            v = tk.StringVar(value=str(self.settings.get(key, "")))
            vars_map[key] = v
            ttk.Entry(frm, textvariable=v, width=72).grid(row=i, column=1, sticky="ew", pady=4, padx=(8, 0))
        bool_row = len(fields)
        auto_var = tk.BooleanVar(value=bool(self.settings.get("auto_start", True)))
        clean_var = tk.BooleanVar(value=bool(self.settings.get("clean_workdir", True)))
        ttk.Checkbutton(frm, text="Start patching automatically when 2025RR opens", variable=auto_var).grid(row=bool_row, column=0, columnspan=2, sticky="w", pady=(10, 2))
        ttk.Checkbutton(frm, text="Clean/recreate work folder before each run", variable=clean_var).grid(row=bool_row+1, column=0, columnspan=2, sticky="w", pady=2)
        frm.columnconfigure(1, weight=1)

        def save():
            for key, v in vars_map.items():
                self.settings[key] = v.get().strip()
            self.settings["auto_start"] = bool(auto_var.get())
            self.settings["clean_workdir"] = bool(clean_var.get())
            save_settings(self.settings)
            self.package = (self.settings.get("package_name") or DEFAULTS["package_name"]).strip() or DEFAULTS["package_name"]
            wd = self.settings.get("workdir") or ""
            self.workdir = Path(wd).expanduser() if wd else default_workdir()
            if not self.nameserver_url and is_valid_nameserver_url(self.settings.get("default_nameserver_url", "")):
                self.nameserver_url = self.settings["default_nameserver_url"].strip()
                self.nameserver_host = normalize_nameserver_host(self.nameserver_url)
            messagebox.showinfo(APP_SHORT, "Settings updated for this session.", parent=win)
            win.destroy()

        btns = tk.Frame(win, bg=C_BG)
        btns.pack(fill="x", padx=14, pady=(0, 14))
        ttk.Button(btns, text="Save settings", style="Primary.TButton", command=save).pack(side="left")
        ttk.Button(btns, text="Cancel", style="Secondary.TButton", command=win.destroy).pack(side="left", padx=8)

    # ---------- dialogs / confirmations ----------
    def ask_nameserver_ui(self):
        def _do():
            initial = self.nameserver_url or (self.settings.get("default_nameserver_url") or "")
            while True:
                ns = simpledialog.askstring(
                    "Nameserver URL needed",
                    "Enter the nameserver URL for your Rec Room setup (must start with http:// or https://):",
                    initialvalue=initial,
                    parent=self,
                )
                if ns is None:
                    self.nameserver_url = ""
                    self.nameserver_host = ""
                    break
                ns = ns.strip()
                if is_valid_nameserver_url(ns):
                    self.nameserver_url = ns
                    self.nameserver_host = normalize_nameserver_host(ns)
                    self.settings["default_nameserver_url"] = ns
                    save_settings(self.settings)
                    break
                messagebox.showerror(
                    "Invalid nameserver URL",
                    "Please enter a valid URL starting with http:// or https://\n\nExample: https://ns.example.com",
                    parent=self,
                )
            self.nameserver_event.set()
        self.ui(_do)

    def ask_confirm_uninstall_ui(self, package: str):
        def _do():
            self.confirm_result = messagebox.askyesno(
                "Uninstall Rec Room?",
                f"To install this patched Rec Room build, the existing app ({package}) needs to be removed first because the app signatures don't match.\n\n"
                "Uninstalling may remove Rec Room app data on your device.\n\n"
                "Are you sure you would like to uninstall Rec Room?",
                parent=self,
                icon=messagebox.WARNING,
            )
            self.confirm_event.set()
        self.ui(_do)

    def confirm_uninstall(self, package: str) -> bool:
        self.confirm_event.clear()
        self.confirm_result = False
        self.ask_confirm_uninstall_ui(package)
        self.confirm_event.wait()
        return bool(self.confirm_result)

    def ask_local_xapk_ui(self):
        def _do():
            self.file_result = ""
            path = filedialog.askopenfilename(
                title="Select base.xapk",
                filetypes=[("Rec Room base package", "*.xapk *.apk *.zip"), ("All files", "*.*")],
                parent=self,
            )
            self.file_result = path or ""
            self.file_event.set()
        self.ui(_do)

    def pick_local_xapk(self) -> str:
        self.file_event.clear()
        self.file_result = ""
        self.ask_local_xapk_ui()
        self.file_event.wait()
        return self.file_result

    def show_devices_ui(self, devices):
        def _do():
            for w in self.device_buttons_frame.winfo_children():
                w.destroy()
            self.selected_device = None
            self.device_event.clear()
            if not devices:
                self.device_info_var.set("No devices found. Connect your phone, enable USB debugging, unlock it, and allow this computer if prompted.")
                ttk.Button(self.device_buttons_frame, text="Retry device check", style="Secondary.TButton", command=self._retry_devices).pack(side="left")
                return
            self.device_info_var.set("Choose the Android device you want to patch/install Rec Room on:")
            for serial, desc in devices:
                label = serial + (f" — {desc}" if desc else "")
                ttk.Button(self.device_buttons_frame, text=label, style="Secondary.TButton", command=lambda s=serial: self._select_device(s)).pack(side="left", padx=(0, 8), pady=2)
        self.ui(_do)

    def _retry_devices(self):
        self.selected_device = "__retry__"
        self.device_info_var.set("Checking for devices...")
        self.device_event.set()

    def _select_device(self, serial):
        self.selected_device = serial
        self.device_info_var.set(f"Selected device: {serial}")
        self.device_event.set()

    # ---------- helpers ----------
    def human_error(self, title: str, detail: str, hints=None) -> RuntimeError:
        msg = f"{title}\n\nWhat happened:\n{detail}"
        if hints:
            msg += "\n\nHow to fix:\n- " + "\n- ".join(hints)
        return RuntimeError(msg)

    def _subprocess_hidden_kwargs(self):
        if os.name != "nt":
            return {}
        kwargs = {}
        try:
            cf = 0
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                cf |= subprocess.CREATE_NO_WINDOW
            if cf:
                kwargs["creationflags"] = cf
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            kwargs["startupinfo"] = si
        except Exception:
            pass
        return kwargs

    def run_cmd(self, cmd, cwd=None, env=None, check=True, capture=False, timeout=None):
        self.log("$ " + " ".join(str(c) for c in cmd))
        hidden = self._subprocess_hidden_kwargs()
        try:
            if capture or timeout is not None:
                p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, **hidden)
                out = p.stdout or ""
                if out:
                    for line in out.splitlines():
                        self.log(line)
                if check and p.returncode != 0:
                    raise RuntimeError(f"Command failed (exit {p.returncode}): {' '.join(str(c) for c in cmd)}\n{out.strip()}")
                return out
            proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, **hidden)
            assert proc.stdout
            for line in proc.stdout:
                self.log(line.rstrip())
            rc = proc.wait()
            if check and rc != 0:
                raise RuntimeError(f"Command failed (exit {rc}): {' '.join(str(c) for c in cmd)}")
            return ""
        except FileNotFoundError as e:
            raise RuntimeError(f"Command not found: {cmd[0]} ({e})")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(str(c) for c in cmd)}")

    def _is_google_drive_url(self, url: str) -> bool:
        return "drive.google.com" in url or "drive.usercontent.google.com" in url

    def _drive_file_id(self, url: str):
        try:
            import urllib.parse as up
            q = {k: v[0] for k, v in up.parse_qs(urlparse(url).query).items()}
            return q.get("id")
        except Exception:
            return None

    def _stream_response(self, opener, req, dest: Path, overall_base=0, overall_span=0):
        with opener.open(req, timeout=120) as resp, open(dest, "wb") as f:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            total = resp.headers.get("Content-Length")
            total_size = int(total) if total and total.isdigit() else 0
            downloaded = 0
            # progress hook by bytes
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    pct = min(100, int(downloaded * 100 / total_size))
                    detail = f"{fmt_bytes(downloaded)} / {fmt_bytes(total_size)} ({pct}%)"
                    self.set_progress(item_value=pct, item_mode="determinate", item_detail=detail,
                                      overall=overall_base + int(pct * overall_span / 100) if overall_span else None)
                else:
                    self.set_progress(item_mode="indeterminate", item_detail=f"{fmt_bytes(downloaded)} downloaded")
            return ctype, downloaded

    def download_file(self, url, dest: Path, label: str, overall_base=0, overall_span=0, min_size=0):
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.set_progress(step=label, item=f"Downloading {dest.name}", item_mode="determinate", item_value=0, item_detail="Starting download...")

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
        last_err = None
        for attempt in range(4):
            try:
                if attempt > 0:
                    self.log(f"Retrying download ({attempt+1}/4): {dest.name}")
                    self.set_progress(item_mode="determinate", item_value=0, item_detail=f"Retrying download ({attempt+1}/4)...")
                try:
                    if dest.exists(): dest.unlink()
                except Exception:
                    pass

                opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())

                if self._is_google_drive_url(url):
                    import urllib.parse as up
                    file_id = self._drive_file_id(url)
                    candidates = []
                    if file_id:
                        # Prefer no-confirm first (virus-scan warning form flow), then fallbacks
                        candidates = [
                            f"https://drive.usercontent.google.com/download?export=download&id={file_id}&authuser=0",
                            f"https://drive.google.com/uc?export=download&id={file_id}",
                            f"https://drive.usercontent.google.com/download?export=download&id={file_id}&confirm=t",
                            url,
                        ]
                    else:
                        candidates = [url]

                    ok = False
                    last_reason = None
                    for dl_url in candidates:
                        try:
                            if dest.exists(): dest.unlink()
                        except Exception:
                            pass
                        req = urllib.request.Request(dl_url, headers=headers)
                        ctype, _ = self._stream_response(opener, req, dest, overall_base, overall_span)
                        size = dest.stat().st_size if dest.exists() else 0
                        is_html = "text/html" in (ctype or "").lower() or (size < 5 * 1024 * 1024 and size > 0)
                        if min_size and size < min_size and is_html:
                            try:
                                html = dest.read_text(errors="ignore")
                            except Exception:
                                html = ""
                            low = html.lower()
                            if "quota exceeded" in low or "download quota" in low or "too many users have viewed" in low:
                                # do not keep trying confirm=t variants that trigger quota page; report clearly
                                raise RuntimeError("Google Drive download quota exceeded for this file (Google returned a quota/error page instead of the file).")

                            # Try to follow download form (virus scan warning / confirm page)
                            action_m = re.search(r'<form[^>]*id="download-form"[^>]*action="([^"]+)"', html, re.I)
                            if not action_m:
                                action_m = re.search(r'<form[^>]*action="([^"]+)"[^>]*>', html, re.I)
                            if action_m:
                                action = action_m.group(1).replace("&amp;", "&")
                                inputs = dict(re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', html, re.I))
                                if inputs:
                                    q = up.urlencode(inputs)
                                    form_url = action + ("&" if "?" in action else "?") + q
                                    try:
                                        if dest.exists(): dest.unlink()
                                    except Exception:
                                        pass
                                    req2 = urllib.request.Request(form_url, headers=headers)
                                    self._stream_response(opener, req2, dest, overall_base, overall_span)
                                    size = dest.stat().st_size if dest.exists() else 0
                                    if not (min_size and size < min_size):
                                        ok = True
                                        break
                                    # if still HTML, continue to other strategies
                                    try:
                                        html2 = dest.read_text(errors="ignore").lower()
                                    except Exception:
                                        html2 = ""
                                    if "quota exceeded" in html2:
                                        raise RuntimeError("Google Drive download quota exceeded for this file (Google returned a quota/error page instead of the file).")
                                    last_reason = f"small file after form submit ({fmt_bytes(size)})"
                                    continue

                            # Fallback: build confirm URL from known fields
                            token = None
                            m = re.search(r'name="confirm"\s+value="([^"]+)"', html, re.I)
                            if m: token = m.group(1)
                            if not token:
                                m = re.search(r'[?&]confirm=([0-9A-Za-z_\-]+)', html)
                                if m: token = m.group(1)
                            uuid = None
                            m = re.search(r'name="uuid"\s+value="([^"]+)"', html, re.I)
                            if m: uuid = m.group(1)
                            if file_id and (token or uuid):
                                params = {"id": file_id, "export": "download"}
                                if token: params["confirm"] = token
                                if uuid: params["uuid"] = uuid
                                confirm_url = "https://drive.usercontent.google.com/download?" + up.urlencode(params)
                                try:
                                    if dest.exists(): dest.unlink()
                                except Exception:
                                    pass
                                req2 = urllib.request.Request(confirm_url, headers=headers)
                                self._stream_response(opener, req2, dest, overall_base, overall_span)
                                size = dest.stat().st_size if dest.exists() else 0
                                if not (min_size and size < min_size):
                                    ok = True
                                    break
                            last_reason = f"received HTML page instead of file ({fmt_bytes(size)})"
                            continue

                        if min_size and size < min_size:
                            last_reason = f"file too small ({fmt_bytes(size)})"
                            continue
                        ok = True
                        break

                    if not ok:
                        size = dest.stat().st_size if dest.exists() else 0
                        snippet = ""
                        try:
                            snippet = dest.read_text(errors="ignore")[:2000].lower()
                        except Exception:
                            pass
                        if "quota exceeded" in snippet or "download quota" in snippet or "too many users have viewed" in snippet:
                            raise RuntimeError("Google Drive download quota exceeded for this file (Google returned a quota/error page instead of the file).")
                        raise RuntimeError(last_reason or f"Downloaded file is too small ({fmt_bytes(size)}). Google Drive may have returned a warning/confirmation page instead of the file.")
                else:
                    req = urllib.request.Request(url, headers=headers)
                    self._stream_response(opener, req, dest, overall_base, overall_span)
                    size = dest.stat().st_size if dest.exists() else 0
                    if min_size and size < min_size:
                        snippet = ""
                        try:
                            snippet = dest.read_text(errors="ignore")[:2000].lower()
                        except Exception:
                            pass
                        if "quota exceeded" in snippet or "download quota" in snippet or "too many users have viewed" in snippet:
                            raise RuntimeError("Google Drive download quota exceeded for this file (Google returned a quota/error page instead of the file).")
                        raise RuntimeError(f"Downloaded file is too small ({fmt_bytes(size)}). The download may have been blocked or returned an error page.")

                last_err = None
                break
            except Exception as e:
                last_err = e
                try:
                    if dest.exists(): dest.unlink()
                except Exception:
                    pass
                if attempt < 3:
                    time.sleep(2 + attempt)
        if last_err is not None:
            raise self.human_error(
                f"Download failed: {dest.name}",
                str(last_err),
                ["Check your internet connection and try again", "Google Drive may block automated downloads temporarily; try again later or from a different network", "If a firewall/VPN blocks downloads, allow GitHub and Google Drive", "Large downloads may take time; keep the app open while retrying"]
            )
        self.set_progress(item_value=100, item_mode="determinate", item_detail=f"Downloaded {fmt_bytes(dest.stat().st_size)}",
                          overall=overall_base + overall_span if overall_span else None)

    def extract_zip(self, zip_path: Path, dest_dir: Path, label: str):
        self.set_progress(step=label, item=f"Extracting {zip_path.name}", item_mode="determinate", item_value=0, item_detail="Preparing files...")
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                infos = [i for i in zf.infolist() if not i.is_dir()]
                total = max(1, len(infos))
                for idx, info in enumerate(infos, 1):
                    zf.extract(info, dest_dir)
                    pct = int(idx * 100 / total)
                    self.set_progress(item_value=pct, item_mode="determinate", item_detail=f"{idx}/{total}: {Path(info.filename).name}")
        except Exception as e:
            raise self.human_error(f"Could not extract {zip_path.name}", str(e),
                                   ["The downloaded file may be incomplete; restart to re-download", "Make sure there is enough free disk space"])

    # ---------- adb / device ----------
    def _resolve_adb_base(self):
        custom = (self.settings.get("adb_command") or "").strip()
        if custom:
            parts = split_cmd(custom)
            if parts and (Path(parts[0]).exists() or shutil.which(parts[0])):
                return parts
        exe = "adb.exe" if os.name == "nt" else "adb"
        found = shutil.which("adb") or shutil.which(exe)
        if found:
            return [found]
        return [exe]

    def _bootstrap_platform_tools(self):
        system = platform.system().lower()
        wd = self.workdir
        if system == 'linux':
            url = 'https://dl.google.com/android/repository/platform-tools-latest-linux.zip'
        elif system == 'darwin':
            url = 'https://dl.google.com/android/repository/platform-tools-latest-darwin.zip'
        elif system == 'windows':
            url = 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip'
        else:
            return False
        dest = wd / 'platform-tools'
        adb_name = 'adb.exe' if system == 'windows' else 'adb'
        if (dest / adb_name).exists():
            os.environ['PATH'] = str(dest) + os.pathsep + os.environ.get('PATH', '')
            return True
        try:
            z = wd / 'platform-tools.zip'
            self.download_file(url, z, 'Downloading Android platform-tools (adb)...')
            tmp = wd / 'pt_extract'
            if tmp.exists(): shutil.rmtree(tmp)
            self.extract_zip(z, tmp, 'Extracting platform-tools...')
            src = tmp / 'platform-tools'
            if not src.exists():
                dirs = [d for d in tmp.iterdir() if d.is_dir()]
                src = dirs[0] if dirs else src
            if dest.exists(): shutil.rmtree(dest)
            shutil.move(str(src), str(dest))
            shutil.rmtree(tmp, ignore_errors=True)
            try: z.unlink()
            except Exception: pass
            adb_path = dest / adb_name
            if adb_path.exists() and system != 'windows':
                try: os.chmod(adb_path, adb_path.stat().st_mode | 0o111)
                except Exception: pass
            os.environ['PATH'] = str(dest) + os.pathsep + os.environ.get('PATH', '')
            return (dest / adb_name).exists() or shutil.which('adb') is not None
        except Exception as e:
            self.log(f'Platform-tools download failed: {e}')
            return False

    def ensure_adb(self):
        self.set_progress(step="Preparing device tools", item="Checking for ADB (Android tools)", item_mode="indeterminate", item_detail="ADB is needed to install patched Rec Room APKs and push bundles to your device")
        base = self._resolve_adb_base()
        if Path(base[0]).exists() or shutil.which(base[0]):
            try:
                self.run_cmd(base + ["version"], capture=True, check=False, timeout=15)
            except Exception:
                pass
            self.log("adb ready: " + " ".join(base))
            self._adb_base = base
            return
        candidates = []
        home = Path.home()
        candidates += [self.workdir / 'platform-tools' / ('adb.exe' if os.name=='nt' else 'adb'),
                       home / "platform-tools" / "adb", home / "Android" / "platform-tools" / "adb",
                       home / "Android" / "Sdk" / "platform-tools" / "adb"]
        if os.name == "nt":
            candidates += [Path("C:/platform-tools/adb.exe"), home / "AppData/Local/Android/Sdk/platform-tools/adb.exe"]
        for c in candidates:
            if c.exists():
                os.environ["PATH"] = str(c.parent) + os.pathsep + os.environ.get("PATH", "")
        self.log("adb not found, attempting automatic setup...")
        self._bootstrap_platform_tools()
        base = self._resolve_adb_base()
        if not (Path(base[0]).exists() or shutil.which(base[0])):
            raise self.human_error(
                "ADB (Android platform-tools) is not available",
                "2025RR could not find or install ADB automatically.",
                ["Install Android platform-tools manually and add adb to PATH", "Or set the adb command/path in Settings", "Connect your device with a data-capable USB cable and enable USB debugging"]
            )
        self._adb_base = base
        self.log("adb ready: " + " ".join(base))

    def get_adb_devices(self):
        out = self.run_cmd(self._adb_base + ["devices", "-l"], capture=True, check=False, timeout=20)
        devices = []
        states = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices") or line.startswith("* daemon"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                serial, state = parts[0], parts[1]
                desc = " ".join(parts[2:])
                if state == "device":
                    devices.append((serial, desc))
                else:
                    states.append((serial, state, desc))
        self._last_adb_device_states = states
        return devices

    def _device_wait_message(self):
        states = getattr(self, "_last_adb_device_states", []) or []
        if not states:
            return "Connect a phone with USB debugging enabled, unlock it, and click Retry."
        parts = [f"{s} ({st})" for s, st, _ in states[:3]]
        extra = " Check the USB debugging prompt on your phone and allow this computer." if any(st == "unauthorized" for _, st, _ in states) else ""
        return "Detected device(s) not ready: " + ", ".join(parts) + "." + extra + " Click Retry when ready."

    def adb(self, args, capture=False, check=True, timeout=None):
        base = list(getattr(self, "_adb_base", self._resolve_adb_base()))
        if self.selected_device and self.selected_device not in ("__retry__", None):
            base += ["-s", self.selected_device]
        return self.run_cmd(base + args, capture=capture, check=check, timeout=timeout)

    def _wait_for_device(self, timeout=180):
        self.log("Waiting for your device to reconnect...")
        end = time.time() + timeout
        while time.time() < end:
            try:
                devs = self.get_adb_devices()
            except Exception:
                devs = []
            if devs:
                serials = [d[0] for d in devs]
                if self.selected_device in serials:
                    return
                if len(devs) == 1:
                    self.selected_device = devs[0][0]
                    self.ui(lambda s=self.selected_device: self.device_info_var.set(f"Selected device: {s}"))
                    return
                return
            time.sleep(2)
        raise self.human_error("Device disconnected", "The selected device did not reconnect in time.",
                               ["Check the USB cable and connection", "Unlock the device and allow USB debugging if prompted", "Click Start / Restart once the device is ready"])

    # ---------- build ----------
    def _is_wsl_system_bash(self, path_str: str) -> bool:
        try:
            p = Path(path_str)
            s = str(p).lower().replace('/', '\\')
            windir = os.environ.get('WINDIR', r'C:\Windows').lower().replace('/', '\\')
            localapp = os.environ.get('LOCALAPPDATA', '').lower().replace('/', '\\')
            if s.endswith('\\system32\\bash.exe') and s.startswith(windir):
                return True
            # Windows App Execution Alias for WSL bash (e.g. %LOCALAPPDATA%\Microsoft\WindowsApps\bash.exe)
            if s.endswith('\\windowsapps\\bash.exe') and (not localapp or localapp in s or '\\microsoft\\windowsapps\\' in s):
                return True
            return False
        except Exception:
            return False

    def _find_git_bash_windows(self):
        candidates = [
            tool_cache_dir() / "portable-git" / "bin" / "bash.exe",
            tool_cache_dir() / "portable-git" / "usr" / "bin" / "bash.exe",
            Path(r"C:\Program Files\Git\bin\bash.exe"),
            Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
            Path(r"C:\Program Files (x86)\Git\bin\bash.exe"),
            Path.home() / "scoop/apps/git/current/bin/bash.exe",
        ]
        for c in candidates:
            try:
                if c.exists():
                    return str(c)
            except Exception:
                pass
        return None

    def ensure_git_bash_windows(self):
        if os.name != "nt":
            return None
        found = self._find_git_bash_windows()
        if found:
            return found

        self.log("Git Bash not found. Downloading Portable Git for Windows...")
        self.set_progress(status="Preparing tools", step="Setting up Git Bash", item="Downloading Portable Git",
                          item_mode="indeterminate", item_detail="Git Bash is needed to run the patch build on Windows")
        cache = tool_cache_dir()
        cache.mkdir(parents=True, exist_ok=True)
        git_dir = cache / "portable-git"
        if git_dir.exists():
            try:
                shutil.rmtree(git_dir)
            except Exception:
                pass
        git_dir.mkdir(parents=True, exist_ok=True)

        # Try to discover latest PortableGit asset, then fall back to known versions
        urls = []
        try:
            req = urllib.request.Request(
                "https://api.github.com/repos/git-for-windows/git/releases/latest",
                headers={"User-Agent": "2025RR", "Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
            for asset in (data.get("assets") or []):
                name = (asset.get("name") or "")
                if name.startswith("PortableGit-") and name.endswith("-64-bit.7z.exe"):
                    u = asset.get("browser_download_url")
                    if u:
                        urls.append(u)
                        break
        except Exception as e:
            self.log(f"Could not query latest PortableGit release: {e}")

        urls += [
            "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.2/PortableGit-2.47.1.2-64-bit.7z.exe",
            "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/PortableGit-2.47.1-64-bit.7z.exe",
            "https://github.com/git-for-windows/git/releases/download/v2.46.2.windows.1/PortableGit-2.46.2-64-bit.7z.exe",
        ]

        exe_path = cache / "PortableGit-64-bit.7z.exe"
        last_err = None
        for url in urls:
            try:
                self.log(f"Downloading Portable Git: {url}")
                self.download_file(url, exe_path, "Downloading Portable Git (Git Bash)", min_size=20 * 1024 * 1024)
                self.set_progress(item="Installing Portable Git", item_mode="indeterminate", item_detail="Extracting Git Bash...")
                cmd = [str(exe_path), "-y", f"-o{git_dir}"]
                self.run_cmd(cmd, check=True)
                found = self._find_git_bash_windows()
                if found:
                    try:
                        exe_path.unlink()
                    except Exception:
                        pass
                    self.log(f"Portable Git ready: {found}")
                    return found
                last_err = RuntimeError("Portable Git extracted but bash.exe was not found.")
            except Exception as e:
                last_err = e
                self.log(f"Portable Git setup attempt failed: {e}")
                try:
                    if exe_path.exists():
                        exe_path.unlink()
                except Exception:
                    pass
                try:
                    if git_dir.exists():
                        shutil.rmtree(git_dir)
                    git_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
        raise self.human_error(
            "Git Bash could not be set up automatically",
            str(last_err) if last_err else "Portable Git download/extraction failed.",
            [
                "Install Git for Windows manually from https://git-scm.com/download/win",
                "Then set the Bash command in Settings to your Git Bash path (e.g. C:\\Program Files\\Git\\bin\\bash.exe)",
                "Or ensure your internet connection allows downloading Git for Windows",
            ],
        )

    def resolve_bash(self):
        custom = (self.settings.get("bash_command") or "").strip()
        if custom:
            parts = split_cmd(custom)
            if parts and (Path(parts[0]).exists() or shutil.which(parts[0])):
                if os.name == "nt" and len(parts) == 1 and self._is_wsl_system_bash(parts[0]):
                    git_bash = self._find_git_bash_windows()
                    if git_bash:
                        return [git_bash]
                    if shutil.which("wsl") or shutil.which("wsl.exe"):
                        return ["wsl", "bash"]
                return parts
        if os.name == "nt":
            # Prefer Git Bash (installed or auto-downloaded portable) over WSL app-alias/system bash
            git_bash = self._find_git_bash_windows()
            for cand in ["bash", "bash.exe"]:
                p = shutil.which(cand)
                if p:
                    if self._is_wsl_system_bash(p):
                        if git_bash:
                            return [git_bash]
                        if shutil.which("wsl") or shutil.which("wsl.exe"):
                            return ["wsl", "bash"]
                        continue
                    return [p]
            if git_bash:
                return [git_bash]
            if shutil.which("wsl") or shutil.which("wsl.exe"):
                return ["wsl", "bash"]
            return ["bash"]
        for cand in ["bash", "bash.exe"]:
            p = shutil.which(cand)
            if p:
                return [p]
        return ["bash"]

    def run_bash_script(self, script: Path, cwd: Path, env=None, args=None):
        args = args or []
        bash = self.resolve_bash()
        use_wsl = False
        if os.name == "nt":
            if bash[:2] == ["wsl", "bash"] or (bash[:1] == ["wsl.exe"]):
                # Try to get Git Bash automatically before falling back to WSL
                try:
                    git_bash = self.ensure_git_bash_windows()
                    if git_bash:
                        bash = [git_bash]
                    else:
                        use_wsl = True
                except Exception as e:
                    self.log(f"Automatic Git Bash setup failed, falling back to WSL if available: {e}")
                    use_wsl = True
            elif len(bash) == 1 and self._is_wsl_system_bash(bash[0]):
                try:
                    git_bash = self.ensure_git_bash_windows()
                    if git_bash:
                        bash = [git_bash]
                    else:
                        use_wsl = True
                except Exception as e:
                    self.log(f"Automatic Git Bash setup failed, falling back to WSL if available: {e}")
                    use_wsl = True
        if use_wsl:
            def wsl_path(p):
                s = os.path.abspath(str(p))
                m = re.match(r"^([A-Za-z]):[\\/](.*)$", s)
                if m:
                    drive = m.group(1).lower()
                    rest = m.group(2).replace("\\", "/")
                    return f"/mnt/{drive}/{rest}"
                return s.replace("\\", "/")
            script_w = wsl_path(script)
            cwd_w = wsl_path(cwd)
            args_w = []
            for a in args:
                sa = str(a)
                if re.match(r"^[A-Za-z]:[\\/]", sa) or ("\\" in sa and Path(sa).drive):
                    args_w.append(wsl_path(sa))
                else:
                    args_w.append(sa)
            quoted = " ".join(shlex.quote(x) for x in [script_w] + args_w)
            wsl_exe = shutil.which("wsl.exe") or shutil.which("wsl") or "wsl.exe"
            cmd = [wsl_exe, "bash", "-lc", f"cd {shlex.quote(cwd_w)} && {quoted}"]
            self.run_cmd(cmd, env=env)
            return
        # If on Windows and resolved bash is missing/unusable, try bootstrapping Git Bash
        if os.name == "nt" and (not bash or not (Path(bash[0]).exists() or shutil.which(bash[0])) or bash == ["bash"]):
            try:
                git_bash = self.ensure_git_bash_windows()
                if git_bash:
                    bash = [git_bash]
            except Exception as e:
                self.log(f"Automatic Git Bash setup failed: {e}")
        # Convert Windows paths for Git Bash/MSYS when needed
        if os.name == "nt" and bash and len(bash) == 1:
            bash_exe = str(bash[0]).lower().replace('/', '\\')
            if 'git' in bash_exe and bash_exe.endswith('bash.exe'):
                # Git Bash can generally handle Windows paths, but normalize to forward slashes
                script_arg = str(script).replace('\\', '/')
                cwd_run = cwd
                args_run = [str(a).replace('\\', '/') if (isinstance(a, (str, Path)) and re.match(r'^[A-Za-z]:[\\/]', str(a))) else str(a) for a in args]
                self.run_cmd(bash + [script_arg] + args_run, cwd=cwd_run, env=env)
                return

        self.run_cmd(bash + [str(script)] + [str(a) for a in args], cwd=cwd, env=env)

    # ---------- build env (bootstraps) ----------
    def find_tool(self, name):
        candidates_names = [name]
        if os.name == 'nt' and not name.lower().endswith('.exe'):
            candidates_names.append(name + '.exe')
        for n in candidates_names:
            p = shutil.which(n)
            if p: return Path(p)
        home = Path.home()
        roots = [
            os.environ.get('ANDROID_HOME'),
            os.environ.get('ANDROID_SDK_ROOT'),
            str(home / 'Android' / 'Sdk'),
            str(home / 'AppData' / 'Local' / 'Android' / 'Sdk'),
            str(self.workdir / 'android-sdk'),
            '/usr/lib/android-sdk',
        ]
        for root in roots:
            if not root: continue
            r = Path(root)
            patterns = [f'build-tools/*/{name}', f'build-tools/*/lib/{name}']
            if os.name == 'nt' and not name.lower().endswith('.exe'):
                patterns += [f'build-tools/*/{name}.exe']
            for pat in patterns:
                for c in r.glob(pat):
                    if c.exists(): return c
        # Java keytool common locations
        if name == 'keytool':
            java_home = os.environ.get('JAVA_HOME')
            if java_home:
                for cand in [Path(java_home)/'bin'/'keytool.exe', Path(java_home)/'bin'/'keytool']:
                    if cand.exists(): return cand
            if os.name == 'nt':
                common = [
                    Path(r'C:\Program Files\Java'),
                    Path(r'C:\Program Files\Eclipse Adoptium'),
                    Path(r'C:\Program Files\Microsoft\jdk'),
                ]
                for base in common:
                    if base.exists():
                        for cand in sorted(base.glob('*/bin/keytool.exe'), reverse=True):
                            if cand.exists(): return cand
        return None

    def _host_python_for_venv(self):
        if not getattr(sys, "frozen", False):
            return sys.executable
        candidates = ["python3", "python"]
        if os.name == "nt":
            candidates = ["py", "python", "python3"] + candidates
        for name in candidates:
            p = shutil.which(name)
            if p:
                return p
        return None


    def patch_patcher_for_host(self, patcher: Path):
        """Apply small host-compatibility patches to the downloaded patcher scripts."""
        try:
            build_phone = patcher / "scripts" / "build-phone.sh"
            if build_phone.exists():
                s = build_phone.read_text(encoding="utf-8", errors="ignore")
                changed = False

                # Define PYTHON_BIN preferring venv, and use it for script/tool invocations
                if 'PYTHON_BIN="${PYTHON_BIN:-python3}"' not in s and 'python3 -c "import lief"' in s:
                    py_def = 'PYTHON_BIN="${PYTHON_BIN:-python3}"\nif [ -n "${VIRTUAL_ENV:-}" ]; then\n  if [ -x "$VIRTUAL_ENV/bin/python" ]; then PYTHON_BIN="$VIRTUAL_ENV/bin/python"; elif [ -x "$VIRTUAL_ENV/bin/python3" ]; then PYTHON_BIN="$VIRTUAL_ENV/bin/python3"; elif [ -x "$VIRTUAL_ENV/Scripts/python.exe" ]; then PYTHON_BIN="$VIRTUAL_ENV/Scripts/python.exe"; elif [ -x "$VIRTUAL_ENV/Scripts/python" ]; then PYTHON_BIN="$VIRTUAL_ENV/Scripts/python"; fi\nfi\n'
                    anchor = 'set -euo pipefail\n'
                    if anchor in s:
                        s = s.replace(anchor, anchor + py_def, 1)
                    else:
                        s = s.replace('command -v java >/dev/null || die "java not found"\n\n', 'command -v java >/dev/null || die "java not found"\n\n' + py_def)
                    changed = True

                old_lief = 'python3 -c "import lief" 2>/dev/null || die "python \'lief\' missing: pip install lief"'
                if old_lief in s:
                    new_lief = '"$PYTHON_BIN" -c "import lief" 2>/dev/null || die "python \'lief\' missing: pip install lief (tried $PYTHON_BIN)"'
                    s = s.replace(old_lief, new_lief)
                    changed = True

                # Replace common python3 script invocations with "$PYTHON_BIN"
                replacements = [
                    ('  VC="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))[\'version_code\'])" "$OUT/in/manifest.json")',
                     '  VC="$("$PYTHON_BIN" -c "import json,sys;print(json.load(open(sys.argv[1]))[\'version_code\'])" "$OUT/in/manifest.json")'),
                    ('    BASE_APK="$(python3 -c \'import json,sys;print(next(s["file"] for s in json.load(open(sys.argv[1]))["split_apks"] if s["id"]=="base"))\' "$OUT/in/manifest.json")',
                     '    BASE_APK="$("$PYTHON_BIN" -c \'import json,sys;print(next(s["file"] for s in json.load(open(sys.argv[1]))["split_apks"] if s["id"]=="base"))\' "$OUT/in/manifest.json")'),
                    ('    BASE_APK="$(python3 - "$OUT/in" <<\'PY\'',
                     '    BASE_APK="$("$PYTHON_BIN" - "$OUT/in" <<\'PY\''),
                    ('  python3 "$HERE/pairip_strip.py" "$OUT/in/$BASE_APK" "$OUT/tmp/base.stripped.apk" || die "pairip_strip failed (see messages above)"',
                     '  "$PYTHON_BIN" "$HERE/pairip_strip.py" "$OUT/in/$BASE_APK" "$OUT/tmp/base.stripped.apk" || die "pairip_strip failed (see messages above)"'),
                    ('    python3 "$HERE/gen-config.py" "$CONFIG" "$GEN/config_generated.h"',
                     '    "$PYTHON_BIN" "$HERE/gen-config.py" "$CONFIG" "$GEN/config_generated.h"'),
                    ('python3 "$HERE/inject.py" "$OUT/tmp/libmain.so" "$OUT/tmp/libmain.injected.so" 2>&1',
                     '"$PYTHON_BIN" "$HERE/inject.py" "$OUT/tmp/libmain.so" "$OUT/tmp/libmain.injected.so" 2>&1'),
                    ('python3 - "$OUT/tmp/libmain.injected.so" <<\'PY\'',
                     '"$PYTHON_BIN" - "$OUT/tmp/libmain.injected.so" <<\'PY\''),
                    ('    python3 "$HERE/gotfix_inject.py" "$OUT/tmp/$TGT" "$OUT/tmp/$TGT.gf" "$GNAME"',
                     '    "$PYTHON_BIN" "$HERE/gotfix_inject.py" "$OUT/tmp/$TGT" "$OUT/tmp/$TGT.gf" "$GNAME"'),
                    ('  python3 "$HERE/neuter_pairipcore.py" "$OUT/tmp/libpairipcore.so" "$OUT/tmp/libpairipcore.stub.so" || die "neuter_pairipcore failed"',
                     '  "$PYTHON_BIN" "$HERE/neuter_pairipcore.py" "$OUT/tmp/libpairipcore.so" "$OUT/tmp/libpairipcore.stub.so" || die "neuter_pairipcore failed"'),
                    ('python3 "$HERE/phone_patch.py" "$SPLIT" "$OUT/tmp/libmain.injected.so" "$OUT/libvrsupport.so" "$OUT/tmp/config.arm64_v8a.apk" ${GOTFIX_PUT[@]+"${GOTFIX_PUT[@]}"}',
                     '"$PYTHON_BIN" "$HERE/phone_patch.py" "$SPLIT" "$OUT/tmp/libmain.injected.so" "$OUT/libvrsupport.so" "$OUT/tmp/config.arm64_v8a.apk" ${GOTFIX_PUT[@]+"${GOTFIX_PUT[@]}"}'),
                    ('if [ "$NOHOOK" = 1 ]; then echo "   (NOHOOK: skipping verify-phone)"; else python3 "$HERE/verify-phone.py" "$OUT/signed" "${VERIFY_IL2CPP_MD5:-$EXPECT_IL2CPP_MD5}" "$EXPECT_IL2CPP_MD5"; fi',
                     'if [ "$NOHOOK" = 1 ]; then echo "   (NOHOOK: skipping verify-phone)"; else "$PYTHON_BIN" "$HERE/verify-phone.py" "$OUT/signed" "${VERIFY_IL2CPP_MD5:-$EXPECT_IL2CPP_MD5}" "$EXPECT_IL2CPP_MD5"; fi'),
                ]
                for o, n in replacements:
                    if o in s and n not in s:
                        s = s.replace(o, n)
                        changed = True

                if os.name == "nt":
                    old_clang = 'CLANG="$ANDROID_NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android29-clang++"\nif [ -z "$HOOK_SO" ] && [ ! -x "$CLANG" ]; then die "NDK clang not found: $CLANG (set ANDROID_NDK, or HOOK_SO=<prebuilt libvrsupport.so>)"; fi'
                    if old_clang in s:
                        new_clang = (
                            'CLANG=""\n'
                            'if [ -z "$HOOK_SO" ]; then\n'
                            '  for cand in \\\n'
                            '    "$ANDROID_NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android29-clang++" \\\n'
                            '    "$ANDROID_NDK/toolchains/llvm/prebuilt/windows-x86_64/bin/aarch64-linux-android29-clang++.cmd" \\\n'
                            '    "$ANDROID_NDK/toolchains/llvm/prebuilt/windows-x86_64/bin/aarch64-linux-android29-clang++.exe" \\\n'
                            '    "$ANDROID_NDK/toolchains/llvm/prebuilt/windows-x86_64/bin/aarch64-linux-android29-clang++"; do\n'
                            '    if [ -f "$cand" ]; then CLANG="$cand"; break; fi\n'
                            '  done\n'
                            '  [ -n "$CLANG" ] || die "NDK clang not found in $ANDROID_NDK (checked linux-x86_64 and windows-x86_64 prebuilt toolchains; set ANDROID_NDK or HOOK_SO=<prebuilt libvrsupport.so>)"\n'
                            'fi'
                        )
                        s = s.replace(old_clang, new_clang)
                        changed = True

                    old_za = 'ZIPALIGN="$TOOLS/zipalign"; [ -x "$ZIPALIGN" ] || ZIPALIGN="$(command -v zipalign || true)"'
                    if old_za in s:
                        new_za = 'ZIPALIGN="$TOOLS/zipalign"; [ -x "$ZIPALIGN" ] || ZIPALIGN="$TOOLS/zipalign.exe"; [ -x "$ZIPALIGN" ] || [ -f "$ZIPALIGN" ] || ZIPALIGN="$(command -v zipalign || command -v zipalign.exe || true)"'
                        s = s.replace(old_za, new_za)
                        changed = True

                    old_gotfix = '  [ -x "$CLANG" ] || die "gotfix needs the NDK (set ANDROID_NDK) -- or NOGOTFIX=1"'
                    if old_gotfix in s:
                        s = s.replace(old_gotfix, '  [ -f "$CLANG" ] || [ -x "$CLANG" ] || die "gotfix needs the NDK (set ANDROID_NDK) -- or NOGOTFIX=1"')
                        changed = True

                if changed:
                    build_phone.write_text(s, encoding="utf-8", newline="\n")
                    self.log("Patched build-phone.sh for host/build environment compatibility.")
        except Exception as e:
            self.log(f"Patcher compatibility patch issue: {e}")

    def ensure_python_deps_env(self, wd: Path):
        venv = wd / 'venv'
        py = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not py.exists():
            host_py = self._host_python_for_venv()
            if not host_py:
                raise self.human_error(
                    "Python is required to prepare the patch build environment",
                    "2025RR needs Python to create a build environment for patch dependencies, but a Python installation was not found on this system.",
                    [
                        "Install Python 3 and make sure it is available in PATH (python3/python/py)",
                        "Then start the patch process again",
                    ],
                )
            self.log('Creating a Python environment for patch build dependencies...')
            self.run_cmd([host_py, '-m', 'venv', str(venv)])
        try:
            self.run_cmd([str(py), '-c', 'import lief'], check=True, capture=True)
        except Exception:
            self.log('Installing lief in venv...')
            self.run_cmd([str(py), '-m', 'pip', 'install', '--upgrade', 'pip'], check=False)
            self.run_cmd([str(py), '-m', 'pip', 'install', 'lief'], check=False)

        # Ensure patch scripts can find python3/lief in bash environments
        try:
            vbin = venv / ('Scripts' if os.name == 'nt' else 'bin')
            if os.name == 'nt':
                py3_exe = vbin / 'python3.exe'
                if py.exists() and not py3_exe.exists():
                    try:
                        shutil.copy2(py, py3_exe)
                    except Exception:
                        pass
                py3_sh = vbin / 'python3'
                if py.exists() and not py3_sh.exists():
                    try:
                        py3_sh.write_text(f'#!/usr/bin/env bash\nexec "{py}" "$@"\n', encoding='utf-8')
                    except Exception:
                        pass
            else:
                # Ensure python3 name exists in venv bin
                py3 = vbin / 'python3'
                if py.exists() and not py3.exists():
                    try:
                        py3.symlink_to(py.name)
                    except Exception:
                        try:
                            shutil.copy2(py, py3)
                        except Exception:
                            pass
        except Exception as e:
            self.log(f'Python alias setup issue: {e}')

        bin_dir = str(venv / ('Scripts' if os.name == 'nt' else 'bin'))
        os.environ['PATH'] = bin_dir + os.pathsep + os.environ.get('PATH', '')
        os.environ['VIRTUAL_ENV'] = str(venv)

    def bootstrap_android_tools(self, patcher: Path, wd: Path):
        tools = patcher / 'tools'
        tools.mkdir(parents=True, exist_ok=True)
        system = platform.system().lower()
        need_za = not ((tools / 'zipalign').exists() or (tools / 'zipalign.exe').exists() or shutil.which('zipalign'))
        need_apk = not ((tools / 'lib' / 'apksigner.jar').exists() or shutil.which('apksigner'))
        if not (need_za or need_apk):
            return

        if system == 'windows':
            bt_root = wd / 'android-build-tools'
            urls = [
                'https://dl.google.com/android/repository/build-tools_r34-windows.zip',
                'https://dl.google.com/android/repository/build-tools_r34.0.0-windows.zip',
            ]
            z = wd / 'build-tools-windows.zip'
            if not bt_root.exists():
                last_err = None
                for url in urls:
                    try:
                        self.download_file(url, z, 'Downloading Android build-tools (Windows)...')
                        tmp = wd / 'bt_extract'
                        if tmp.exists(): shutil.rmtree(tmp)
                        self.extract_zip(z, tmp, 'Extracting Android build-tools...')
                        candidates = list(tmp.glob('android-*')) + [d for d in tmp.iterdir() if d.is_dir()]
                        src = candidates[0] if candidates else None
                        if not src: raise RuntimeError('Could not locate extracted build-tools directory')
                        if bt_root.exists(): shutil.rmtree(bt_root)
                        shutil.move(str(src), str(bt_root))
                        shutil.rmtree(tmp, ignore_errors=True)
                        try: z.unlink()
                        except Exception: pass
                        last_err = None
                        break
                    except Exception as e:
                        last_err = e
                if last_err:
                    self.log(f'Automatic Windows build-tools bootstrap failed: {last_err}')
                    return
            za = bt_root / 'zipalign.exe'
            if not za.exists():
                za = bt_root / 'zipalign'
            if za.exists() and need_za and not (tools / za.name).exists() and not (tools / 'zipalign').exists() and not (tools / 'zipalign.exe').exists():
                try:
                    shutil.copy2(za, tools / za.name)
                except Exception as e:
                    self.log(f'Could not copy zipalign: {e}')
            aj = bt_root / 'lib' / 'apksigner.jar'
            if aj.exists() and need_apk and not (tools / 'lib' / 'apksigner.jar').exists():
                (tools / 'lib').mkdir(parents=True, exist_ok=True)
                shutil.copy2(aj, tools / 'lib' / 'apksigner.jar')
            return

        if system != 'linux':
            self.log('Automatic Android build-tools bootstrap is currently supported on Linux and Windows; ensure zipalign/apksigner are installed and available.')
            return

        bt_root = wd / 'android-build-tools'
        urls = [
            'https://dl.google.com/android/repository/build-tools_r34-linux.zip',
            'https://dl.google.com/android/repository/build-tools_r34.0.0-linux.zip',
        ]
        z = wd / 'build-tools-linux.zip'
        if not bt_root.exists():
            last_err = None
            for url in urls:
                try:
                    self.download_file(url, z, 'Downloading Android build-tools...')
                    tmp = wd / 'bt_extract'
                    if tmp.exists(): shutil.rmtree(tmp)
                    self.extract_zip(z, tmp, 'Extracting Android build-tools...')
                    candidates = list(tmp.glob('android-*')) + [d for d in tmp.iterdir() if d.is_dir()]
                    src = candidates[0] if candidates else None
                    if not src: raise RuntimeError('Could not locate extracted build-tools directory')
                    if bt_root.exists(): shutil.rmtree(bt_root)
                    shutil.move(str(src), str(bt_root))
                    shutil.rmtree(tmp, ignore_errors=True)
                    try: z.unlink()
                    except Exception: pass
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
            if last_err: raise last_err
        za = bt_root / 'zipalign'
        if za.exists() and need_za and not (tools / 'zipalign').exists():
            try: os.chmod(za, 0o755)
            except Exception: pass
            wrapper = tools / 'zipalign'
            wrapper.write_text(f'#!/usr/bin/env bash\nexec "{za}" "$@"\n', encoding='utf-8')
            os.chmod(wrapper, 0o755)
        aj = bt_root / 'lib' / 'apksigner.jar'
        if aj.exists() and need_apk and not (tools / 'lib' / 'apksigner.jar').exists():
            (tools / 'lib').mkdir(parents=True, exist_ok=True)
            shutil.copy2(aj, tools / 'lib' / 'apksigner.jar')

    def _fix_ndk_layout(self, root: Path):
        for p in root.rglob('*'):
            try:
                if p.is_symlink() or not p.is_file():
                    continue
                sp = str(p)
                if ('/bin/' in sp or '/prebuilt/' in sp or '/lib' in sp) and p.stat().st_size <= 4096:
                    try:
                        data = p.read_bytes()
                        if b'\x00' not in data:
                            s = data.decode('utf-8', 'ignore').strip()
                            if s and '\n' not in s and ' ' not in s and len(s) < 255:
                                target = p.parent / s
                                if target.exists() or (p.parent / Path(s).name).exists():
                                    try:
                                        p.unlink(); os.symlink(s, p); continue
                                    except Exception:
                                        pass
                    except Exception:
                        pass
                if '/bin/' in sp or '/prebuilt/' in sp:
                    try: p.chmod(p.stat().st_mode | 0o111)
                    except Exception: pass
            except Exception:
                pass

    def _ndk_candidates(self, base: Path):
        # Return possible clang executables for host platform
        if platform.system().lower() == 'windows':
            pre = base / 'toolchains/llvm/prebuilt/windows-x86_64/bin'
            return [pre / 'aarch64-linux-android29-clang++.cmd', pre / 'aarch64-linux-android29-clang++.bat', pre / 'aarch64-linux-android29-clang++']
        pre = base / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
        return [pre / 'aarch64-linux-android29-clang++']

    def _is_valid_ndk(self, base: Path):
        for c in self._ndk_candidates(base):
            if c.exists():
                return True
        return False

    def bootstrap_ndk(self, wd: Path):
        system = platform.system().lower()
        env_ndk = os.environ.get('ANDROID_NDK')
        candidates = []
        if env_ndk:
            candidates.append(Path(env_ndk))
        if system == 'windows':
            local = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
            candidates += [
                local / 'Android' / 'Sdk' / 'ndk' / '27.2.12479018',
                local / 'Android' / 'Sdk' / 'ndk' / 'android-ndk-r27c',
                Path.home() / 'Android' / 'Sdk' / 'ndk' / '27.2.12479018',
                wd / 'android-ndk-r27c',
            ]
        else:
            candidates += [
                Path.home() / 'x' / 'ndk' / 'android-ndk-r27c',
                Path.home() / 'Android' / 'Sdk' / 'ndk' / '27.2.12479018',
                wd / 'android-ndk-r27c',
            ]
        for cand in candidates:
            if cand.exists() and self._is_valid_ndk(cand):
                os.environ['ANDROID_NDK'] = str(cand)
                self.log(f'Using Android NDK: {cand}')
                return
            if cand.exists() and system == 'linux':
                self._fix_ndk_layout(cand)
                if self._is_valid_ndk(cand):
                    os.environ['ANDROID_NDK'] = str(cand)
                    self.log(f'Using Android NDK: {cand}')
                    return

        # Auto-download
        if system == 'windows':
            ndk_path = wd / 'android-ndk-r27c'
            if ndk_path.exists() and self._is_valid_ndk(ndk_path):
                os.environ['ANDROID_NDK'] = str(ndk_path)
                return
            url = 'https://dl.google.com/android/repository/android-ndk-r27c-windows.zip'
            z = wd / 'android-ndk-r27c-windows.zip'
            try:
                self.download_file(url, z, 'Downloading Android NDK r27c for Windows (large download)...', min_size=100 * 1024 * 1024)
                tmp = wd / 'ndk_extract'
                if tmp.exists(): shutil.rmtree(tmp)
                self.extract_zip(z, tmp, 'Extracting Android NDK r27c...')
                extracted = tmp / 'android-ndk-r27c'
                if not extracted.exists():
                    dirs = [d for d in tmp.iterdir() if d.is_dir()]
                    extracted = dirs[0] if dirs else extracted
                if ndk_path.exists(): shutil.rmtree(ndk_path)
                shutil.move(str(extracted), str(ndk_path))
                shutil.rmtree(tmp, ignore_errors=True)
                try: z.unlink()
                except Exception: pass
                if self._is_valid_ndk(ndk_path):
                    os.environ['ANDROID_NDK'] = str(ndk_path)
                    self.log(f'Installed Android NDK: {ndk_path}')
                    return
            except Exception as e:
                self.log(f'Automatic Windows NDK bootstrap failed: {e}')
            self.log('Automatic Android NDK setup on Windows could not be completed; ensure ANDROID_NDK points to NDK r27c.')
            return

        if system != 'linux':
            self.log('Automatic Android NDK bootstrap is currently supported on Linux and Windows; ensure ANDROID_NDK is configured.')
            return

        ndk_path = Path.home() / 'x' / 'ndk' / 'android-ndk-r27c'
        if ndk_path.exists():
            try: shutil.rmtree(ndk_path)
            except Exception: pass
        ndk_path.parent.mkdir(parents=True, exist_ok=True)
        url = 'https://dl.google.com/android/repository/android-ndk-r27c-linux.zip'
        z = wd / 'android-ndk-r27c-linux.zip'
        self.download_file(url, z, 'Downloading Android NDK r27c (large download)...', min_size=100 * 1024 * 1024)
        tmp = wd / 'ndk_extract'
        if tmp.exists(): shutil.rmtree(tmp)
        self.extract_zip(z, tmp, 'Extracting Android NDK r27c...')
        extracted = tmp / 'android-ndk-r27c'
        if not extracted.exists():
            dirs = [d for d in tmp.iterdir() if d.is_dir()]
            extracted = dirs[0] if dirs else extracted
        if ndk_path.exists(): shutil.rmtree(ndk_path)
        shutil.move(str(extracted), str(ndk_path))
        shutil.rmtree(tmp, ignore_errors=True)
        try: z.unlink()
        except Exception: pass
        self._fix_ndk_layout(ndk_path)
        if self._is_valid_ndk(ndk_path):
            os.environ['ANDROID_NDK'] = str(ndk_path)
            self.log(f'Installed Android NDK: {ndk_path}')

    def prepare_build_env(self, patcher: Path):
        self.set_progress(step='Preparing the patch build environment', item='Setting up tools and dependencies', item_mode='indeterminate', item_detail='This may take a while on first run')
        wd = self.workdir
        tools = patcher / 'tools'
        tools.mkdir(parents=True, exist_ok=True)
        try: self.ensure_python_deps_env(wd)
        except Exception as e: self.log(f'Python env setup issue: {e}')
        try: self.bootstrap_android_tools(patcher, wd)
        except Exception as e: self.log(f'Build-tools setup issue: {e}')
        try: self.bootstrap_ndk(wd)
        except Exception as e: self.log(f'NDK setup issue: {e}')
        def ensure_jar(name, urls):
            dest = tools / f'{name}.jar'
            if dest.exists() and dest.stat().st_size > 0: return
            for url in urls:
                try:
                    self.download_file(url, dest, f'Downloading {name}.jar...')
                    if dest.exists() and dest.stat().st_size > 10000: return
                except Exception as e:
                    self.log(f'Failed {name} from {url}: {e}')
                    try: dest.unlink()
                    except Exception: pass
        if not shutil.which('baksmali') and not (tools/'baksmali.jar').exists():
            ensure_jar('baksmali', ['https://bitbucket.org/JesusFreke/smali/downloads/baksmali-2.5.2.jar'])
        if not shutil.which('smali') and not (tools/'smali.jar').exists():
            ensure_jar('smali', ['https://bitbucket.org/JesusFreke/smali/downloads/smali-2.5.2.jar'])
        keytool = self.find_tool('keytool') or shutil.which('keytool') or shutil.which('keytool.exe')
        ks = tools / 'debug.keystore'
        if not ks.exists() and keytool:
            mk = patcher / 'scripts' / 'make-keystore.sh'
            if mk.exists():
                try:
                    self.run_bash_script(mk, cwd=patcher)
                except Exception as e:
                    self.log(f'Keystore generation script issue: {e}')
            # fallback: try keytool directly if bash/script failed (use alias expected by patcher)
            if not ks.exists():
                try:
                    self.run_cmd([str(keytool), '-genkeypair', '-v', '-keystore', str(ks), '-alias', '2025',
                                  '-storepass', 'android', '-keypass', 'android', '-keyalg', 'RSA', '-keysize', '2048',
                                  '-validity', '36500', '-dname', 'CN=Rec-Uni, O=Rec-Uni'], check=False)
                except Exception as e:
                    self.log(f'Direct keytool keystore generation issue: {e}')

        missing = []
        java_ok = bool(shutil.which('java') or os.environ.get('JAVA_HOME'))
        if not java_ok: missing.append('Java (JDK/JRE)')
        za_ok = (tools / 'zipalign').exists() or (tools / 'zipalign.exe').exists() or bool(shutil.which('zipalign'))
        if not za_ok: missing.append('Android build-tools (zipalign)')
        apk_ok = (tools / 'lib' / 'apksigner.jar').exists() or bool(shutil.which('apksigner'))
        if not apk_ok: missing.append('Android build-tools (apksigner)')
        kt_ok = bool(keytool or (tools / 'debug.keystore').exists())
        if not (tools / 'debug.keystore').exists() and not kt_ok:
            missing.append('Signing keystore (keytool)')
        elif not (tools / 'debug.keystore').exists():
            missing.append('Signing keystore (keytool/JDK)')

        ndk_env = os.environ.get('ANDROID_NDK')
        ndk_ok = False
        ndk_candidates = [Path(ndk_env)] if ndk_env else []
        if platform.system().lower() == 'windows':
            local = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
            ndk_candidates += [self.workdir / 'android-ndk-r27c', local / 'Android' / 'Sdk' / 'ndk' / '27.2.12479018']
        else:
            ndk_candidates += [Path.home()/'x'/'ndk'/'android-ndk-r27c', self.workdir / 'android-ndk-r27c']
        for c in ndk_candidates:
            try:
                if c.exists() and self._is_valid_ndk(c):
                    ndk_ok = True
                    os.environ['ANDROID_NDK'] = str(c)
                    break
            except Exception:
                pass
        if not ndk_ok:
            missing.append('Android NDK r27c')

        if missing:
            hints = ["Try running again, and review the error details shown in the app"]
            if platform.system().lower() == 'linux':
                hints = ["Install Java and Android build-tools/NDK, then try again", "On Linux, first-run setup can download large tools (NDK/build-tools)"] + hints
            elif platform.system().lower() == 'windows':
                hints = [
                    "Install JDK (Java) and ensure java/keytool are in PATH (or set JAVA_HOME)",
                    "Install Android SDK Build-Tools and NDK r27c (Android Studio SDK Manager) and set ANDROID_HOME/ANDROID_NDK if needed",
                    "2025RR can try to download some Windows build tools automatically, but your setup may still need manual steps",
                    "Use Git Bash or WSL for the patch build and set the Bash command in Settings if needed",
                ] + hints
            else:
                hints = ["Install Java and Android build-tools/NDK, then try again"] + hints
            raise self.human_error(
                "Some patch build tools are missing",
                "Some required tools could not be installed automatically:\n- " + "\n- ".join(missing),
                hints
            )
        self.log('2025RR patch build environment ready.')

    # ---------- install / push ----------
    def _infer_package(self, apks):
        for a in apks:
            name = a.stem
            if name.startswith('config.') or name.startswith('Unity'):
                continue
            if '.' in name:
                return name
        return self.package or DEFAULTS["package_name"]

    def install_apks(self, apks):
        self.set_progress(status="Installing", step="Install 2025RR patch APKs to device", overall=80, overall_text="Step 5/6: Installing APKs",
                          item="Preparing APK install", item_mode="indeterminate", item_detail="Setting up device install session")
        if not apks:
            raise self.human_error("No APKs to install", "The 2025RR patch build output does not contain signed APK files.",
                                   ["The build may have failed — try starting the patch process again", "If it keeps failing, check that your build tools are set up correctly"])
        pkg = self._infer_package(apks)
        remote_tmp = '/data/local/tmp/2025rr_install'
        total = len(apks)

        def ensure_remote_tmp():
            for attempt in range(2):
                try:
                    self.adb(['shell', 'rm', '-rf', remote_tmp], check=False, timeout=30)
                    self.adb(['shell', 'mkdir', '-p', remote_tmp], check=True, timeout=30)
                    return
                except Exception as e:
                    self.log(f'Device temp setup issue ({e}); retrying...')
                    self._wait_for_device()
            self.adb(['shell', 'mkdir', '-p', remote_tmp], check=True, timeout=30)

        def push_all_apks():
            for i, apk in enumerate(apks, 1):
                size = apk.stat().st_size
                self.set_progress(item=f'APK {i}/{total}: {apk.name}', item_mode='determinate', item_value=0,
                                  item_detail=f'Copying to device ({fmt_bytes(size)})')
                self.log(f'Pushing APK {i}/{total}: {apk.name} ({fmt_bytes(size)})')
                try:
                    self.adb(['push', str(apk), f'{remote_tmp}/{apk.name}'])
                except Exception:
                    self._wait_for_device()
                    self.adb(['shell', 'mkdir', '-p', remote_tmp], check=False, timeout=30)
                    self.adb(['push', str(apk), f'{remote_tmp}/{apk.name}'])
                self.set_progress(item_value=100, item_detail=f'Copied {apk.name}')

        def create_session():
            total_size = sum(a.stat().st_size for a in apks)
            out = self.adb(['shell', 'pm', 'install-create', '-r', '-S', str(total_size)], capture=True, check=False)
            m = re.search(r'\[(\d+)\]', out)
            if not m:
                out = self.adb(['shell', 'pm', 'install-create', '-r'], capture=True, check=False)
                m = re.search(r'\[(\d+)\]', out)
            if not m:
                raise self.human_error("Failed to start install session", (out or '').strip() or "pm install-create did not return a session ID.",
                                       ["Unlock the device and allow USB installs if prompted", "Check that enough storage space is available", "If needed, uninstall the existing Rec Room app and try again"])
            sid = m.group(1)
            self.log(f'Install session: {sid}')
            return sid

        def commit_session(session):
            return self.adb(['shell', 'pm', 'install-commit', session], capture=True, check=False)

        def install_attempt():
            ensure_remote_tmp()
            push_all_apks()
            self.set_progress(item='Creating install session', item_mode='indeterminate', item_detail='Preparing package manager session...')
            session = create_session()
            for i, apk in enumerate(apks, 1):
                self.set_progress(item=f'APK {i}/{total}: {apk.name}', item_mode='determinate', item_value=30, item_detail='Adding APK to install session...')
                remote = f'{remote_tmp}/{apk.name}'
                self.adb(['shell', 'pm', 'install-write', '-S', str(apk.stat().st_size), session, apk.name, remote], check=False)
                self.set_progress(item_value=100, item_detail=f'Added {apk.name}')
            self.set_progress(item='Finalizing 2025RR patch installation', item_mode='indeterminate', item_detail='Committing install on device (large apps can take a while)...')
            return commit_session(session)

        def uninstall_existing():
            self.set_progress(item='Uninstalling existing Rec Room app', item_mode='indeterminate', item_detail=f'Removing {pkg} from device...')
            self.adb(['uninstall', pkg], check=False, timeout=120)

        try:
            out = install_attempt()
            if 'Success' not in out:
                # Retry by uninstalling existing app when possible (helps signature/storage/update conflicts)
                if 'INSTALL_FAILED_UPDATE_INCOMPATIBLE' in out or 'signatures do not match' in (out or '').lower():
                    if not self.confirm_uninstall(pkg):
                        raise self.human_error("Installation cancelled", f"{pkg} is already installed with a different signature and must be removed to continue.",
                                               ["Uninstall the existing Rec Room app from your device, then run again", "Or allow 2025RR to uninstall it when prompted"])
                    self.log(f'User confirmed uninstall of {pkg}')
                else:
                    self.log(f'Install failed, attempting uninstall+retry: {(out or "").strip()}')
                uninstall_existing()
                out = install_attempt()
                if 'Success' not in out:
                    raise self.human_error("2025RR patch install failed", (out or '').strip() or "Install did not complete successfully.",
                                           ["Keep the device connected and unlocked during installation", "Ensure there is enough free storage on the device", "If needed, uninstall the existing Rec Room app from your device and try again", "Free up device storage and retry"])
        finally:
            try:
                self.adb(['shell', 'rm', '-rf', remote_tmp], check=False, timeout=30)
            except Exception:
                pass

        self.set_progress(item='2025RR patch APKs installed', item_mode='determinate', item_value=100, item_detail=f'Successfully installed {total} APK(s)')
        self.log(f'Installed {total} Rec Room 2025 patch APK(s) successfully.')

    def push_bundles(self, bundles_dir: Path):
        self.set_progress(status="Pushing bundles", step="Push 2025RR bundles to device", overall=90, overall_text="Step 6/6: Pushing bundles",
                          item="Preparing bundle upload", item_mode="indeterminate", item_detail="")
        files = sorted([p for p in bundles_dir.iterdir() if p.is_file() and p.suffix == '.bundle']) if bundles_dir.exists() else []
        if not files and bundles_dir.exists():
            files = sorted([p for p in bundles_dir.iterdir() if p.is_file()])
        if not files:
            self.log('No bundle files found to push; skipping.')
            self.set_progress(item='No bundles to push', item_mode='determinate', item_value=100, item_detail='Skipped')
            return
        pkg = self.package or DEFAULTS["package_name"]
        remote_tpl = (self.settings.get("remote_bundles_dir") or DEFAULTS["remote_bundles_dir"])
        remote = remote_tpl.format(package=pkg)
        try:
            self.adb(["shell", "mkdir", "-p", remote], check=False, timeout=30)
        except Exception:
            self._wait_for_device()
            self.adb(["shell", "mkdir", "-p", remote], check=False, timeout=30)

        total = len(files)
        for i, f in enumerate(files, 1):
            size = f.stat().st_size
            self.set_progress(item=f'Bundle {i}/{total}: {f.name}', item_mode='determinate', item_value=0, item_detail=f'Uploading {fmt_bytes(size)}')
            try:
                self.adb(["push", str(f), f"{remote}/{f.name}"])
            except Exception:
                self.log(f'Push failed for {f.name}, reconnecting...')
                self._wait_for_device()
                self.adb(["shell", "mkdir", "-p", remote], check=False, timeout=30)
                self.adb(["push", str(f), f"{remote}/{f.name}"])
            self.set_progress(item_value=100, overall=90 + int(i * 10 / total), item_detail=f'Uploaded {i}/{total}')
        self.log(f'Pushed {total} Rec Room 2025 bundle file(s) to {remote}')

    # ---------- workflow ----------
    def start_auto(self):
        if self.running:
            return
        self.running = True
        self.start_btn.configure(state="disabled")
        self.device_info_var.set("Starting the Rec Room patch process...")
        threading.Thread(target=self.workflow, daemon=True).start()

    def workflow(self):
        try:
            self._keep_log_visible = False
            self.set_build_log_visible(False)
            wd = self.workdir
            self.set_progress(status="Preparing", step="Setting up work folder", overall=0, overall_mode="determinate", overall_text="0%",
                              item="Work folder", item_mode="indeterminate", item_detail=str(wd))
            if wd.exists() and self.settings.get("clean_workdir", True):
                shutil.rmtree(wd, ignore_errors=True)
            wd.mkdir(parents=True, exist_ok=True)
            self.package = (self.settings.get("package_name") or DEFAULTS["package_name"]).strip() or DEFAULTS["package_name"]

            self.set_progress(status="Downloading", step="Step 1/6: Downloading the 2025RR patcher", overall_text="Step 1/6")
            patch_zip = wd / "2025-android-patcher.zip"
            self.download_file(PATCH_ZIP_URL, patch_zip, "Downloading the 2025RR patcher", 0, 8, min_size=50 * 1024)
            extract_root = wd / "patcher_extract"
            if extract_root.exists(): shutil.rmtree(extract_root)
            self.extract_zip(patch_zip, extract_root, "Extracting the 2025RR patcher")
            extracted = extract_root / "2025-android-patcher-main"
            if not extracted.exists():
                dirs = [p for p in extract_root.iterdir() if p.is_dir()]
                extracted = dirs[0] if dirs else extracted
            patcher = wd / "2025-android-patcher"
            if patcher.exists(): shutil.rmtree(patcher)
            shutil.move(str(extracted), str(patcher))
            self.patch_patcher_for_host(patcher)
            self.set_progress(overall=10, overall_text="Patcher ready")

            self.set_progress(status="Input needed", step="Nameserver setup", item="Waiting for your nameserver URL", item_mode="indeterminate",
                              item_detail="Enter the nameserver URL for Rec Room (must start with http:// or https://)")
            if not self.nameserver_host and is_valid_nameserver_url(self.settings.get("default_nameserver_url", "")):
                self.nameserver_url = self.settings["default_nameserver_url"].strip()
                self.nameserver_host = normalize_nameserver_host(self.nameserver_url)
            self.nameserver_event.clear()
            self.ask_nameserver_ui()
            self.nameserver_event.wait()
            if not self.nameserver_host:
                raise self.human_error("Nameserver URL required", "No valid nameserver URL was provided.",
                                       ["Click Start / Restart and enter a nameserver URL starting with http:// or https://", "You can also save a default nameserver URL in Settings"])
            self.log(f"Using nameserver URL: {self.nameserver_url} (configured host: {self.nameserver_host})")

            self.set_progress(status="Downloading", step="Step 2/6: Downloading Rec Room base package (base.xapk)", overall_text="Step 2/6")
            cache_dir = download_cache_dir()
            xapk_cache = cache_dir / "base.xapk"
            xapk = wd / "base.xapk"
            local_candidates = [
                xapk_cache,
                app_base_dir() / "base.xapk",
                Path.cwd() / "base.xapk",
                Path.home() / "Downloads" / "base.xapk",
            ]
            used_local = None
            for cand in local_candidates:
                try:
                    if cand.exists() and cand.stat().st_size >= 50 * 1024 * 1024:
                        if cand.resolve() != xapk.resolve():
                            shutil.copy2(cand, xapk)
                        used_local = cand
                        break
                except Exception:
                    continue
            if used_local:
                self.log(f"Using local/cached base.xapk: {used_local}")
                self.set_progress(item="Using local/cached base.xapk", item_mode="determinate", item_value=100, item_detail=f"Found file ({fmt_bytes(xapk.stat().st_size)})", overall=30)
            else:
                try:
                    self.download_file(XAPK_URL, xapk, "Downloading Rec Room base package (base.xapk)", 10, 20, min_size=50 * 1024 * 1024)
                    try:
                        shutil.copy2(xapk, xapk_cache)
                        self.log(f"Cached base.xapk for future runs: {xapk_cache}")
                    except Exception as ce:
                        self.log(f"Could not cache base.xapk: {ce}")
                except Exception as e:
                    msg = str(e)
                    self.log(f"Automatic base.xapk download failed: {msg}")
                    # Offer local file picker fallback (common when Google Drive blocks automated downloads)
                    self.set_progress(status="Action needed", step="base.xapk needed", item="Couldn't download base.xapk automatically",
                                      item_mode="determinate", item_value=0, item_detail="Please choose a local base.xapk file to continue...")
                    self.ui(lambda: self.device_info_var.set("base.xapk couldn't be downloaded automatically. Please choose a local base.xapk file when prompted."))
                    picked = self.pick_local_xapk()
                    if picked:
                        try:
                            p = Path(picked)
                            if not p.exists() or p.stat().st_size < 50 * 1024 * 1024:
                                raise RuntimeError("Selected file is missing or too small to be a valid base.xapk.")
                            shutil.copy2(p, xapk)
                            try:
                                shutil.copy2(xapk, xapk_cache)
                            except Exception:
                                pass
                            self.log(f"Using selected base.xapk: {p}")
                            self.set_progress(status="Downloading", step="Step 2/6: Rec Room base package ready", overall=30, overall_text="Using local base.xapk",
                                              item="Using selected base.xapk", item_mode="determinate", item_value=100, item_detail=f"Loaded {fmt_bytes(xapk.stat().st_size)}")
                        except Exception as pe:
                            raise self.human_error("Selected base.xapk couldn't be used", str(pe),
                                                   ["Choose a valid base.xapk file (at least 50 MB)", "Or place base.xapk next to 2025RR and run again"])
                    else:
                        if "quota exceeded" in msg.lower():
                            raise self.human_error(
                                "base.xapk download unavailable (Google Drive blocked/quota)",
                                "The hardcoded base.xapk link could not be downloaded automatically (Google Drive returned a block/quota/warning page).",
                                [
                                    "Download base.xapk in your browser, then place it next to 2025RR or in your Downloads folder and run again",
                                    "Or click Start / Restart and select the local base.xapk when prompted",
                                    "If you have a working direct download link for base.xapk, the hardcoded link in 2025RR can be updated",
                                ]
                            )
                        raise

            self.set_progress(status="Downloading", step="Step 3/6: Downloading Rec Room bundles", overall_text="Step 3/6")
            bundles_cache = cache_dir / "bundles.zip"
            bundles_zip = wd / "bundles.zip"
            if bundles_cache.exists() and bundles_cache.stat().st_size >= 1024 * 1024:
                try:
                    shutil.copy2(bundles_cache, bundles_zip)
                    self.log(f"Using cached bundles.zip: {bundles_cache}")
                    self.set_progress(item="Using cached bundles.zip", item_mode="determinate", item_value=100,
                                      item_detail=f"Found cached file ({fmt_bytes(bundles_zip.stat().st_size)})", overall=45)
                except Exception:
                    self.download_file(BUNDLES_URL, bundles_zip, "Downloading Rec Room bundles", 30, 15, min_size=1024 * 1024)
                    try:
                        shutil.copy2(bundles_zip, bundles_cache)
                    except Exception:
                        pass
            else:
                self.download_file(BUNDLES_URL, bundles_zip, "Downloading Rec Room bundles", 30, 15, min_size=1024 * 1024)
                try:
                    shutil.copy2(bundles_zip, bundles_cache)
                    self.log(f"Cached bundles.zip for future runs: {bundles_cache}")
                except Exception as ce:
                    self.log(f"Could not cache bundles.zip: {ce}")
            self.extract_zip(bundles_zip, patcher / "bundles", "Extracting Rec Room bundles")
            self.set_progress(overall=48, overall_text="Downloads complete")

            cfg = f"""[App]
Package Name = 

[Server]
RecNet NameServer Host = {self.nameserver_host}
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
Asset Pack Stub = true
"""
            (patcher / "2025.cfg").write_text(cfg, encoding="utf-8")

            self.ui(self.clear_build_log)
            self.set_build_log_visible(True)
            self.set_progress(status="Building", step="Step 4/6: Building patched Rec Room APKs", overall=50, overall_text="Step 4/6: Building",
                              item="Preparing the patch build", item_mode="indeterminate", item_detail="Setting up tools and building patched Rec Room APKs — this can take a while")
            self.prepare_build_env(patcher)
            env = os.environ.copy()
            env["CONFIG"] = str(patcher / "2025.cfg")
            env.setdefault("PAIRIP_KEEP_STARTUP", str(self.settings.get("pairip_keep_startup", "0")))
            vbin = self.workdir / 'venv' / ('Scripts' if os.name == 'nt' else 'bin')
            if vbin.exists():
                env['VIRTUAL_ENV'] = str(self.workdir / 'venv')
                env['PATH'] = str(vbin) + os.pathsep + env.get('PATH', '')
            # Help bash scripts find Java/keytool on Windows
            try:
                java_home = os.environ.get('JAVA_HOME')
                if java_home:
                    jb = Path(java_home) / 'bin'
                    if jb.exists():
                        env['PATH'] = str(jb) + os.pathsep + env.get('PATH', '')
                kt = self.find_tool('keytool')
                if kt:
                    env['PATH'] = str(Path(kt).parent) + os.pathsep + env.get('PATH', '')
                jav = shutil.which('java') or shutil.which('java.exe')
                if jav:
                    env['PATH'] = str(Path(jav).parent) + os.pathsep + env.get('PATH', '')
            except Exception:
                pass
            for k in ('ANDROID_NDK','ANDROID_HOME','ANDROID_SDK_ROOT','JAVA_HOME'):
                if os.environ.get(k): env[k] = os.environ[k]
            build_script = patcher / "scripts" / "build-phone.sh"
            if not build_script.exists():
                raise self.human_error("Build script not found", f"Expected {build_script} in the downloaded patcher.",
                                       ["Check that the patcher ZIP URL in Settings points to a valid 2025-android-patcher source"])
            self.set_progress(item="Building patched Rec Room APKs", item_mode="indeterminate", item_detail="Build in progress... live build log is shown below.")
            try:
                self.run_bash_script(build_script, cwd=patcher, env=env, args=[xapk])
            except Exception as e:
                raise self.human_error("Patch build failed", str(e),
                                       ["Review the build log shown above for the specific build error", "On Windows, make sure Git Bash or WSL is installed and set the Bash command in Settings if needed", "Check that required build tools are installed/configured (Java, Android build-tools/NDK, bash)", "Make sure you have enough free disk space, then try again"])
            self.set_progress(overall=78, overall_text="Patch build complete")
            self.set_build_log_visible(False)

            self.ensure_adb()
            self.ui(lambda: self.device_info_var.set("Looking for connected Android devices..."))
            while True:
                try:
                    devices = self.get_adb_devices()
                except Exception:
                    devices = []
                if not devices:
                    detail = self._device_wait_message()
                    self.set_progress(status="Waiting for device", step="Connect your Android device", item="No ready devices detected",
                                      item_mode="indeterminate", item_detail=detail)
                    self.device_event.clear()
                    self.show_devices_ui([])
                    self.device_event.wait()
                    if self.selected_device == "__retry__":
                        self.selected_device = None
                        continue
                    continue
                self.set_progress(status="Select device", step="Choose your Android device", item="Device selection",
                                  item_mode="indeterminate", item_detail="Select which connected device should receive the patched Rec Room install")
                self.device_event.clear()
                self.show_devices_ui(devices)
                self.device_event.wait()
                if self.selected_device == "__retry__":
                    self.selected_device = None
                    continue
                if self.selected_device:
                    break

            signed = patcher / "build" / "phone" / "signed"
            apks = sorted(signed.glob("*.apk"))
            if not apks:
                raise self.human_error("No patched APKs found", f"Expected signed patched APKs in {signed}",
                                       ["The patch build may have failed — try running the patch process again to see build details", "Click Start / Restart to try again"])
            self.install_apks(apks)
            self.push_bundles(patcher / "bundles")

            self.set_progress(status="All done!", step="Rec Room patch completed", overall=100, overall_text="100% complete",
                              item="All steps finished", item_mode="determinate", item_value=100,
                              item_detail="Patched Rec Room APKs were installed and bundles were pushed to your device. You can disconnect your device when ready.")
            self.log("DONE: 2025RR Rec Room patch build, install, and bundle push finished.")
            self.ui(lambda: messagebox.showinfo(APP_SHORT, "Rec Room patch completed!\n\n2025RR installed the patched Rec Room APKs and pushed the bundles to your device.", parent=self))
        except Exception as e:
            err = str(e)
            self.log("\n[ERROR] " + err)
            self._keep_log_visible = True
            self.set_build_log_visible(True)
            self.set_progress(status="Something went wrong", step="Action needed", item="Rec Room patch process stopped",
                              item_mode="determinate", item_value=0, item_detail="Check the build log (if shown) and error message for details, then fix the issue and try again.")
            self.ui(lambda m=err: messagebox.showerror(APP_SHORT, m, parent=self))
        finally:
            try:
                if not self._keep_log_visible:
                    self.set_build_log_visible(False)
            except Exception:
                pass
            self.running = False
            self.ui(lambda: self.start_btn.configure(state="normal"))


if __name__ == "__main__":
    app = App()
    app.mainloop()
