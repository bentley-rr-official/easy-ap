#!/usr/bin/env python3
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

PATCH_ZIP_URL = "https://github.com/bentley-rr-official/2025-android-patcher/archive/refs/heads/main.zip"
XAPK_URL = "https://drive.usercontent.google.com/download?id=1k9ASR35hKhZX4QftctMHmuJCWRG2s04p&export=download&authuser=0&confirm=t"
BUNDLES_URL = "https://drive.usercontent.google.com/download?id=1o42Q81c9G_fNceEiXSfHEOFjUPx23z6E&export=download&authuser=0&confirm=t"
DEFAULT_PACKAGE = "com.AgainstGravity.RecRoom"


def default_workdir() -> Path:
    return Path(tempfile.gettempdir()) / "easy-ap"


def fmt_bytes(n: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("easy-ap")
        self.geometry("900x520")
        self.minsize(760, 460)

        self.workdir = default_workdir()
        self.nameserver = ""
        self.package = DEFAULT_PACKAGE
        self.uiq: queue.Queue = queue.Queue()
        self.selected_device = None
        self.device_event = threading.Event()
        self.nameserver_event = threading.Event()
        self.running = False

        self._build_ui()
        self.after(100, self._drain_ui)
        self.after(400, self.start_auto)

    # ---------- UI ----------
    def _build_ui(self):
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        title = ttk.Label(root, text="easy-ap", font=("TkDefaultFont", 18, "bold"))
        title.grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Automatic patch, build, install, and bundle push", foreground="#555").grid(row=1, column=0, sticky="w", pady=(0, 10))

        # Status card
        status_box = ttk.LabelFrame(root, text="Status", padding=10)
        status_box.grid(row=2, column=0, sticky="ew")
        self.status_var = tk.StringVar(value="Starting...")
        self.step_var = tk.StringVar(value="Preparing")
        ttk.Label(status_box, textvariable=self.status_var, font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(status_box, textvariable=self.step_var).grid(row=1, column=0, sticky="w", pady=(2, 8))

        self.overall = ttk.Progressbar(status_box, mode="determinate", maximum=100)
        self.overall.grid(row=2, column=0, sticky="ew")
        self.overall_text = tk.StringVar(value="")
        ttk.Label(status_box, textvariable=self.overall_text).grid(row=3, column=0, sticky="w", pady=(4, 0))

        # Current item/file progress
        item_box = ttk.LabelFrame(root, text="Current item", padding=10)
        item_box.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.item_var = tk.StringVar(value="Waiting...")
        ttk.Label(item_box, textvariable=self.item_var).grid(row=0, column=0, sticky="w")
        self.item_progress = ttk.Progressbar(item_box, mode="determinate", maximum=100)
        self.item_progress.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.item_detail = tk.StringVar(value="")
        ttk.Label(item_box, textvariable=self.item_detail).grid(row=2, column=0, sticky="w", pady=(4, 0))

        # Device
        dev_box = ttk.LabelFrame(root, text="Device", padding=10)
        dev_box.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.device_info_var = tk.StringVar(value="No device action needed yet.")
        ttk.Label(dev_box, textvariable=self.device_info_var).grid(row=0, column=0, sticky="w")
        self.device_buttons_frame = ttk.Frame(dev_box)
        self.device_buttons_frame.grid(row=1, column=0, sticky="w", pady=(6, 0))

        # Details / help
        help_box = ttk.LabelFrame(root, text="Details", padding=10)
        help_box.grid(row=5, column=0, sticky="nsew", pady=(10, 0))
        details = (
            f"Work folder: {self.workdir}\n"
            "• Downloads patcher, base.xapk, and bundles automatically\n"
            "• You will be asked for the nameserver after the patcher downloads\n"
            "• Build tools (NDK, build-tools, adb, keystore, Python deps) are bootstrapped when possible\n"
            "• Detailed logs are printed in the terminal window"
        )
        ttk.Label(help_box, text=details, justify="left").grid(row=0, column=0, sticky="w")

        btns = ttk.Frame(root)
        btns.grid(row=6, column=0, sticky="w", pady=(10, 0))
        self.start_btn = ttk.Button(btns, text="Start / Restart", command=self.start_auto)
        self.start_btn.pack(side="left")

        root.columnconfigure(0, weight=1)
        root.rowconfigure(5, weight=1)
        status_box.columnconfigure(0, weight=1)
        item_box.columnconfigure(0, weight=1)
        dev_box.columnconfigure(0, weight=1)
        help_box.columnconfigure(0, weight=1)

    def log(self, msg: str):
        # Terminal logging (not UI)
        print(msg, flush=True)

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

    # ---------- dialogs / device selection ----------
    def ask_nameserver_ui(self):
        def _do():
            ns = simpledialog.askstring("Nameserver required", "Enter nameserver (RecNet NameServer Host):", parent=self)
            self.nameserver = (ns or "").strip()
            self.nameserver_event.set()
        self.ui(_do)

    def show_devices_ui(self, devices):
        def _do():
            for w in self.device_buttons_frame.winfo_children():
                w.destroy()
            self.selected_device = None
            self.device_event.clear()
            if not devices:
                self.device_info_var.set("No devices found. Connect your phone (USB debugging on), unlock it, then click Retry.")
                ttk.Button(self.device_buttons_frame, text="Retry device check", command=self._retry_devices).pack(side="left")
                return
            self.device_info_var.set("Select a device:")
            for serial, desc in devices:
                label = serial + (f" — {desc}" if desc else "")
                ttk.Button(self.device_buttons_frame, text=label, command=lambda s=serial: self._select_device(s)).pack(side="left", padx=4)
        self.ui(_do)

    def _retry_devices(self):
        self.selected_device = "__retry__"
        self.device_info_var.set("Checking for devices...")
        self.device_event.set()

    def _select_device(self, serial):
        self.selected_device = serial
        self.device_info_var.set(f"Selected device: {serial}")
        self.device_event.set()

    # ---------- command/download helpers ----------
    def human_error(self, title: str, detail: str, hints=None) -> RuntimeError:
        msg = f"{title}\n\nWhat happened:\n{detail}"
        if hints:
            msg += "\n\nHow to fix:\n- " + "\n- ".join(hints)
        return RuntimeError(msg)

    def run_cmd(self, cmd, cwd=None, env=None, check=True, capture=False, timeout=None):
        self.log("$ " + " ".join(cmd))
        try:
            if capture or timeout is not None:
                p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
                out = p.stdout or ""
                if out:
                    for line in out.splitlines():
                        self.log(line)
                if check and p.returncode != 0:
                    raise RuntimeError(f"Command failed (exit {p.returncode}): {' '.join(cmd)}\n{out.strip()}")
                return out
            proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            assert proc.stdout
            for line in proc.stdout:
                self.log(line.rstrip())
            rc = proc.wait()
            if check and rc != 0:
                raise RuntimeError(f"Command failed (exit {rc}): {' '.join(cmd)}")
            return ""
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(cmd)}")

    def download_file(self, url, dest: Path, label: str, overall_base=0, overall_span=0):
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.set_progress(step=label, item=f"Downloading {dest.name}", item_mode="determinate", item_value=0, item_detail="Starting...")

        def hook(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                pct = min(100, int(downloaded * 100 / total_size))
                detail = f"{fmt_bytes(downloaded)} / {fmt_bytes(total_size)} ({pct}%)"
                self.set_progress(item_value=pct, item_mode="determinate", item_detail=detail,
                                  overall=overall_base + int(pct * overall_span / 100) if overall_span else None)
            else:
                self.set_progress(item_mode="indeterminate", item_detail=f"{fmt_bytes(downloaded)} downloaded")

        try:
            urllib.request.urlretrieve(url, dest, reporthook=hook)
        except Exception as e:
            raise self.human_error(
                f"Download failed: {dest.name}",
                str(e),
                ["Check your internet connection", "Try again (downloads can fail temporarily)", "If using a VPN/firewall, allow access to GitHub/Google Drive"]
            )
        self.set_progress(item_value=100, item_mode="determinate", item_detail=f"Downloaded {fmt_bytes(dest.stat().st_size)}",
                          overall=overall_base + overall_span if overall_span else None)

    def extract_zip(self, zip_path: Path, dest_dir: Path, label: str):
        self.set_progress(step=label, item=f"Extracting {zip_path.name}", item_mode="determinate", item_value=0, item_detail="Starting...")
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
            raise self.human_error(f"Failed to extract {zip_path.name}", str(e), ["The download may be corrupted; restart to re-download", "Ensure you have enough disk space in the temp folder"])

    # ---------- adb / devices ----------
    def ensure_adb(self):
        self.set_progress(step="Preparing device tools (adb)", item="Checking adb", item_mode="indeterminate", item_detail="")
        if shutil.which("adb"):
            self.log("adb found: " + shutil.which("adb"))
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
                if shutil.which("adb"):
                    self.log("adb found: " + shutil.which("adb"))
                    return
        self.log("adb not found, downloading platform-tools...")
        self._bootstrap_platform_tools()
        for c in candidates:
            if c.exists():
                os.environ["PATH"] = str(c.parent) + os.pathsep + os.environ.get("PATH", "")
        if not shutil.which("adb"):
            raise self.human_error(
                "ADB (Android platform-tools) is not available",
                "adb could not be found or installed automatically.",
                ["Install Android platform-tools manually from Google", "Reconnect/restart and try again", "On Linux, you can also install your distro's android-tools package"]
            )
        self.log("adb ready: " + shutil.which("adb"))

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
            raise self.human_error("Unsupported OS for automatic adb install", system, ["Install Android platform-tools manually"])
        dest = wd / 'platform-tools'
        adb_name = 'adb.exe' if system == 'windows' else 'adb'
        if (dest / adb_name).exists():
            os.environ['PATH'] = str(dest) + os.pathsep + os.environ.get('PATH', '')
            return
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

    def get_adb_devices(self):
        out = self.run_cmd(["adb", "devices", "-l"], capture=True, check=False)
        devices = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices") or line.startswith("* daemon"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serial = parts[0]
                desc = " ".join(parts[2:])
                devices.append((serial, desc))
        return devices

    def adb(self, args, capture=False, check=True, timeout=None):
        base = ["adb"]
        if self.selected_device and self.selected_device not in ("__retry__", None):
            base += ["-s", self.selected_device]
        return self.run_cmd(base + args, capture=capture, check=check, timeout=timeout)

    def _wait_for_device(self, timeout=180):
        self.log("Waiting for device to reconnect...")
        end = time.time() + timeout
        while time.time() < end:
            devs = self.get_adb_devices()
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
                               ["Check USB cable/connection", "Unlock the phone and allow USB debugging", "Run again once the device is connected"])

    # ---------- build env (reuse previous bootstraps, simplified) ----------
    def find_tool(self, name):
        p = shutil.which(name)
        if p: return Path(p)
        home = Path.home()
        roots = [os.environ.get('ANDROID_HOME'), os.environ.get('ANDROID_SDK_ROOT'), str(home/'Android/Sdk'), str(self.workdir/'android-sdk'), '/usr/lib/android-sdk']
        for root in roots:
            if not root: continue
            r = Path(root)
            for c in list(r.glob(f'build-tools/*/{name}')) + list(r.glob(f'build-tools/*/lib/{name}')):
                if c.exists(): return c
        return None

    def ensure_python_deps_env(self, wd: Path):
        venv = wd / 'venv'
        py = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not py.exists():
            self.log('Creating Python virtual environment for build dependencies...')
            self.run_cmd([sys.executable, '-m', 'venv', str(venv)])
        try:
            self.run_cmd([str(py), '-c', 'import lief'], check=True, capture=True)
        except Exception:
            self.log('Installing lief in venv...')
            self.run_cmd([str(py), '-m', 'pip', 'install', '--upgrade', 'pip'], check=False)
            self.run_cmd([str(py), '-m', 'pip', 'install', 'lief'], check=False)
        bin_dir = str(venv / ('Scripts' if os.name == 'nt' else 'bin'))
        os.environ['PATH'] = bin_dir + os.pathsep + os.environ.get('PATH', '')

    def bootstrap_android_tools(self, patcher: Path, wd: Path):
        tools = patcher / 'tools'
        tools.mkdir(parents=True, exist_ok=True)
        need_za = not ((tools / 'zipalign').exists() or shutil.which('zipalign'))
        need_apk = not ((tools / 'lib' / 'apksigner.jar').exists() or shutil.which('apksigner'))
        if not (need_za or need_apk): return
        if platform.system().lower() != 'linux':
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
                    p.chmod(p.stat().st_mode | 0o111)
            except Exception:
                pass

    def bootstrap_ndk(self, wd: Path):
        ndk_path = Path(os.environ.get('ANDROID_NDK') or (Path.home() / 'x' / 'ndk' / 'android-ndk-r27c'))
        clang = ndk_path / 'toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android29-clang++'
        real_clang = ndk_path / 'toolchains/llvm/prebuilt/linux-x86_64/bin/clang'
        def ok_ndk():
            if not (clang.exists() and os.access(clang, os.X_OK)): return False
            if real_clang.exists() and not real_clang.is_symlink():
                try:
                    if real_clang.stat().st_size < 4096 and b'\x00' not in real_clang.read_bytes(): return False
                except Exception: pass
            return True
        if ndk_path.exists() and not ok_ndk():
            self._fix_ndk_layout(ndk_path)
        if ok_ndk():
            os.environ['ANDROID_NDK'] = str(ndk_path)
            return
        if ndk_path.exists():
            try: shutil.rmtree(ndk_path)
            except Exception: pass
        if platform.system().lower() != 'linux':
            return
        ndk_path.parent.mkdir(parents=True, exist_ok=True)
        url = 'https://dl.google.com/android/repository/android-ndk-r27c-linux.zip'
        z = wd / 'android-ndk-r27c-linux.zip'
        self.download_file(url, z, 'Downloading Android NDK r27c (large download)...')
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
        os.environ['ANDROID_NDK'] = str(ndk_path)

    def prepare_build_env(self, patcher: Path):
        self.set_progress(step='Preparing build environment', item='Setting up tools and dependencies', item_mode='indeterminate', item_detail='')
        wd = self.workdir
        tools = patcher / 'tools'
        tools.mkdir(parents=True, exist_ok=True)
        try: self.ensure_python_deps_env(wd)
        except Exception as e: self.log(f'Python env setup issue: {e}')
        try: self.bootstrap_android_tools(patcher, wd)
        except Exception as e: self.log(f'Build-tools setup issue: {e}')
        try: self.bootstrap_ndk(wd)
        except Exception as e: self.log(f'NDK setup issue: {e}')
        # baksmali/smali
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
        # keystore
        ks = tools / 'debug.keystore'
        if not ks.exists() and shutil.which('keytool'):
            mk = patcher / 'scripts' / 'make-keystore.sh'
            if mk.exists(): self.run_cmd(['bash', str(mk)], cwd=patcher, check=False)

        missing = []
        if not shutil.which('java'): missing.append('Java (JDK/JRE)')
        if not (tools / 'zipalign').exists() and not shutil.which('zipalign'): missing.append('Android build-tools (zipalign)')
        if not (tools / 'lib' / 'apksigner.jar').exists() and not shutil.which('apksigner'): missing.append('Android build-tools (apksigner)')
        if not (tools / 'debug.keystore').exists(): missing.append('Signing keystore (keytool)')
        ndk = Path(os.environ.get('ANDROID_NDK') or (Path.home()/'x'/'ndk'/'android-ndk-r27c'))
        if not (ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android29-clang++').exists():
            missing.append('Android NDK r27c')
        if missing:
            raise self.human_error(
                "Build dependencies are missing",
                "Some required tools could not be installed automatically:\n- " + "\n- ".join(missing),
                [
                    "Install Java and Android SDK build-tools/NDK, then run again",
                    "On Linux, the app tries to auto-download build-tools and NDK (this needs internet and disk space)",
                    "Check the terminal log above for the specific download/setup error",
                ]
            )
        self.log('Build environment ready.')

    # ---------- install/push ----------
    def _infer_package(self, apks):
        for a in apks:
            name = a.stem
            if name.startswith('config.') or name.startswith('Unity'):
                continue
            if '.' in name:
                return name
        return self.package or DEFAULT_PACKAGE

    def install_apks(self, apks):
        self.set_progress(step='Installing APKs on device', overall=80, overall_text='Building complete, installing...',
                          item='Preparing APK install session', item_mode='indeterminate', item_detail='')
        if not apks:
            raise self.human_error("No APKs to install", "The build output does not contain signed APK files.",
                                   ["Check the build log for errors", "Try running again"])
        pkg = self._infer_package(apks)
        remote_tmp = '/data/local/tmp/easy_ap_install'
        total = len(apks)

        # Clean temp and push each APK with per-file progress
        for attempt in range(2):
            try:
                self.adb(['shell', 'rm', '-rf', remote_tmp], check=False, timeout=30)
                self.adb(['shell', 'mkdir', '-p', remote_tmp], check=True, timeout=30)
                break
            except Exception as e:
                self.log(f'Warning: device temp setup issue ({e}); retrying after reconnect...')
                self._wait_for_device()
        else:
            self.adb(['shell', 'mkdir', '-p', remote_tmp], check=True, timeout=30)
        for i, apk in enumerate(apks, 1):
            size = apk.stat().st_size
            self.set_progress(step='Installing APKs on device', item=f'APK {i}/{total}: {apk.name}',
                              item_mode='determinate', item_value=0, item_detail=f'Pushing {fmt_bytes(size)} to device...')
            self.log(f'Pushing APK {i}/{total}: {apk.name} ({fmt_bytes(size)})')
            try:
                self.adb(['push', str(apk), f'{remote_tmp}/{apk.name}'])
            except Exception:
                self._wait_for_device()
                self.adb(['shell', 'mkdir', '-p', remote_tmp], check=False)
                self.adb(['push', str(apk), f'{remote_tmp}/{apk.name}'])
            self.set_progress(item_value=100, item_detail=f'Pushed {apk.name}')

        # Create install session
        def create_session():
            create_args = ['shell', 'pm', 'install-create', '-r', '-S', str(total_size)]
            out = self.adb(create_args, capture=True, check=False)
            m = re.search(r'\[(\d+)\]', out)
            if not m:
                out = self.adb(['shell', 'pm', 'install-create', '-r'], capture=True, check=False)
                m = re.search(r'\[(\d+)\]', out)
            if not m:
                raise self.human_error("Failed to start install session", (out or "").strip() or "pm install-create did not return a session ID.",
                                       ["Make sure the device allows app installs", "Unlock the device and accept any prompts", "Try uninstalling the existing app manually if signature differs"])
            sid = m.group(1)
            self.log(f'Install session: {sid}')
            return sid

        def commit_session(session):
            out = self.adb(['shell', 'pm', 'install-commit', session], capture=True, check=False)
            return out

        self.set_progress(item='Creating install session', item_mode='indeterminate', item_detail='Starting package install...')
        total_size = sum(a.stat().st_size for a in apks)
        session = create_session()

        # Write each APK (per-apk progress)
        try:
            for i, apk in enumerate(apks, 1):
                self.set_progress(step='Installing APKs on device', item=f'APK {i}/{total}: {apk.name}',
                                  item_mode='determinate', item_value=30, item_detail='Adding APK to install session...')
                remote = f'{remote_tmp}/{apk.name}'
                outw = self.adb(['shell', 'pm', 'install-write', '-S', str(apk.stat().st_size), session, apk.name, remote], capture=True, check=False)
                if outw and 'Success' not in outw and 'Failure' in outw:
                    self.log(f'install-write warning/output: {outw.strip()}')
                self.set_progress(item_value=100, item_detail=f'Added {apk.name} to session')

            self.set_progress(item='Committing install', item_mode='indeterminate', item_detail='Finalizing installation on device (this may take a moment)...')
            out = commit_session(session)
            if 'Success' not in out:
                if 'INSTALL_FAILED_UPDATE_INCOMPATIBLE' in out or 'signatures do not match' in (out or '').lower():
                    self.log(f'Signature mismatch. Uninstalling {pkg} and retrying install...')
                    self.set_progress(item='Signature mismatch', item_mode='indeterminate', item_detail=f'Uninstalling existing {pkg} and reinstalling...')
                    self.adb(['uninstall', pkg], check=False)
                    # recreate session and retry
                    self.adb(['shell', 'mkdir', '-p', remote_tmp], check=False, timeout=30)
                    for i, apk in enumerate(apks, 1):
                        self.set_progress(item=f'Re-uploading APK {i}/{total}: {apk.name}', item_mode='determinate', item_value=0, item_detail='Pushing to device...')
                        self.adb(['push', str(apk), f'{remote_tmp}/{apk.name}'])
                        self.set_progress(item_value=100)
                    session = create_session()
                    for i, apk in enumerate(apks, 1):
                        self.set_progress(item=f'Adding APK {i}/{total}: {apk.name}', item_mode='determinate', item_value=30)
                        self.adb(['shell', 'pm', 'install-write', '-S', str(apk.stat().st_size), session, apk.name, f'{remote_tmp}/{apk.name}'], check=False)
                        self.set_progress(item_value=100)
                    self.set_progress(item='Committing install', item_mode='indeterminate', item_detail='Finalizing installation...')
                    out = commit_session(session)
                if 'Success' not in out:
                    raise self.human_error("App install failed", (out or '').strip() or "Install did not complete successfully.",
                                           ["If the app is already installed from another source (e.g. Play Store), uninstall it and try again",
                                            "Check device storage space and that app installs are allowed",
                                            "Keep the device connected/unlocked during installation"])
        finally:
            try:
                self.adb(['shell', 'rm', '-rf', remote_tmp], check=False, timeout=30)
            except Exception:
                pass

        self.set_progress(item='Install complete', item_mode='determinate', item_value=100, item_detail=f'Installed {total} APK(s)')
        self.log(f'Installed {total} APK(s) successfully.')

    def push_bundles(self, bundles_dir: Path):
        self.set_progress(step='Pushing bundles', overall=90, item='Preparing bundles', item_mode='indeterminate', item_detail='')
        files = sorted([p for p in bundles_dir.iterdir() if p.is_file() and p.suffix == '.bundle'])
        if not files:
            files = sorted([p for p in bundles_dir.iterdir() if p.is_file()])
        if not files:
            self.log('No bundle files found to push; skipping.')
            self.set_progress(item='No bundles to push', item_mode='determinate', item_value=100, item_detail='Skipped')
            return
        pkg = self.package or DEFAULT_PACKAGE
        remote = f"/sdcard/Android/data/{pkg}/files/AssetPackStubs/OutfitsAssetPack"
        try:
            self.adb(["shell", "mkdir", "-p", remote], check=False)
        except Exception:
            self._wait_for_device()
            self.adb(["shell", "mkdir", "-p", remote], check=False)

        total = len(files)
        for i, f in enumerate(files, 1):
            size = f.stat().st_size
            self.set_progress(step='Pushing bundles', item=f'Bundle {i}/{total}: {f.name}',
                              item_mode='determinate', item_value=0, item_detail=f'{fmt_bytes(size)}')
            try:
                self.adb(["push", str(f), f"{remote}/{f.name}"])
            except Exception:
                self.log(f'Push failed for {f.name}, reconnecting...')
                self._wait_for_device()
                self.adb(["shell", "mkdir", "-p", remote], check=False)
                self.adb(["push", str(f), f"{remote}/{f.name}"])
            self.set_progress(item_value=100, overall=90 + int(i * 10 / total), item_detail=f'Pushed {i}/{total}')
        self.log(f'Pushed {total} bundle file(s) to {remote}')

    # ---------- workflow ----------
    def start_auto(self):
        if self.running:
            return
        self.running = True
        self.start_btn.configure(state="disabled")
        threading.Thread(target=self.workflow, daemon=True).start()

    def workflow(self):
        try:
            wd = self.workdir
            self.set_progress(status="Preparing...", step="Cleaning work folder", overall=0, overall_mode="determinate",
                              overall_text="0%", item="Work folder", item_mode="indeterminate", item_detail=str(wd))
            if wd.exists():
                shutil.rmtree(wd, ignore_errors=True)
            wd.mkdir(parents=True, exist_ok=True)

            # 1 patcher
            self.set_progress(status="Downloading files", overall_text="Step 1/6")
            patch_zip = wd / "2025-android-patcher.zip"
            self.download_file(PATCH_ZIP_URL, patch_zip, "Downloading patcher", 0, 8)
            extract_root = wd / "patcher_extract"
            if extract_root.exists(): shutil.rmtree(extract_root)
            self.extract_zip(patch_zip, extract_root, "Extracting patcher")
            extracted = extract_root / "2025-android-patcher-main"
            if not extracted.exists():
                dirs = [p for p in extract_root.iterdir() if p.is_dir()]
                extracted = dirs[0] if dirs else extracted
            patcher = wd / "2025-android-patcher"
            if patcher.exists(): shutil.rmtree(patcher)
            shutil.move(str(extracted), str(patcher))
            self.set_progress(overall=10, overall_text="Patcher ready")

            # nameserver prompt
            self.set_progress(status="Input needed", step="Nameserver", item="Waiting for nameserver",
                              item_mode="indeterminate", item_detail="Enter the RecNet nameserver in the dialog")
            self.nameserver = ""
            self.nameserver_event.clear()
            self.ask_nameserver_ui()
            self.nameserver_event.wait()
            if not self.nameserver:
                raise self.human_error("Nameserver required", "No nameserver was entered.",
                                       ["Restart and enter your RecNet nameserver (host) when prompted"])
            self.log(f"Using nameserver: {self.nameserver}")

            # 2 xapk
            self.set_progress(status="Downloading files", overall_text="Step 2/6")
            xapk = wd / "base.xapk"
            self.download_file(XAPK_URL, xapk, "Downloading base.xapk", 10, 20)

            # 3 bundles
            self.set_progress(status="Downloading files", overall_text="Step 3/6")
            bundles_zip = wd / "bundles.zip"
            self.download_file(BUNDLES_URL, bundles_zip, "Downloading bundles.zip", 30, 15)
            self.extract_zip(bundles_zip, patcher / "bundles", "Extracting bundles")
            self.set_progress(overall=48, overall_text="Downloads complete")

            # config
            cfg = f"""[App]\nPackage Name = \n\n[Server]\nRecNet NameServer Host = {self.nameserver}\nOculus App Id =\n\n[Photon]\nApp Id Realtime =\nApp Id Voice =\nApp Id Chat =\nPhoton NameServer =\nPhoton NameServer Port = 0\n\n[Advanced]\nLog HTTP = true\nDebug = false\nLog HTTP Body Max = 10000\nLog Noisy Endpoints = false\n"""
            (patcher / "2025.cfg").write_text(cfg, encoding="utf-8")

            # 4 build
            self.set_progress(status="Building", overall=50, overall_text="Step 4/6: Building (this can take a while)",
                              step="Build", item="Running build script", item_mode="indeterminate",
                              item_detail="Compiling and patching APKs... detailed build output is shown in the terminal window")
            self.prepare_build_env(patcher)
            self.set_progress(status="Building", overall=55, overall_text="Step 4/6: Building (see terminal for live output)",
                              step="Build", item="Running build script", item_mode="indeterminate",
                              item_detail="Build in progress... watch the terminal for live updates")
            env = os.environ.copy()
            env["CONFIG"] = str(patcher / "2025.cfg")
            env.setdefault("PAIRIP_KEEP_STARTUP", "0")
            vbin = self.workdir / 'venv' / ('Scripts' if os.name == 'nt' else 'bin')
            if vbin.exists(): env['PATH'] = str(vbin) + os.pathsep + env.get('PATH','')
            for k in ('ANDROID_NDK','ANDROID_HOME','ANDROID_SDK_ROOT'):
                if os.environ.get(k): env[k] = os.environ[k]
            try:
                self.run_cmd(["bash", str(patcher / "scripts" / "build-phone.sh"), str(xapk)], cwd=patcher, env=env)
            except Exception as e:
                raise self.human_error("Build failed", str(e),
                                       ["Check the terminal output above for the first error", "Make sure required build tools are installed and try again", "Ensure you have enough disk space and a stable internet connection for downloads"])
            self.set_progress(overall=78, overall_text="Build complete")

            # 5 device + install
            self.ensure_adb()
            while True:
                devices = self.get_adb_devices()
                if not devices:
                    self.set_progress(status="Waiting for device", step="Connect device", item="No devices found",
                                      item_mode="indeterminate", item_detail="Connect phone with USB debugging enabled")
                    self.device_event.clear()
                    self.show_devices_ui([])
                    self.device_event.wait()
                    if self.selected_device == "__retry__":
                        self.selected_device = None
                        continue
                    continue
                self.set_progress(status="Select device", step="Choose device", item="Device selection",
                                  item_mode="indeterminate", item_detail="Select which device to install to")
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
                raise self.human_error("No built APKs found", f"Expected signed APKs in {signed}",
                                       ["The build may have failed; check terminal logs", "Try running again"])
            self.install_apks(apks)

            # 6 bundles
            self.push_bundles(patcher / "bundles")

            self.set_progress(status="Done", step="Completed", overall=100, overall_text="100% - Finished",
                              item="All steps completed", item_mode="determinate", item_value=100,
                              item_detail="App installed and bundles pushed successfully")
            self.log("DONE: build, install, and bundle push finished.")
            self.ui(lambda: messagebox.showinfo("easy-ap", "Completed successfully.\n\nThe app was installed and bundles were pushed to your device."))
        except Exception as e:
            err = str(e)
            self.log("\n[ERROR] " + err)
            self.set_progress(status="Error", step="Failed", item="An error occurred", item_mode="determinate", item_value=0,
                              item_detail="See message and terminal log for details")
            self.ui(lambda m=err: messagebox.showerror("easy-ap", m))
        finally:
            self.running = False
            self.ui(lambda: self.start_btn.configure(state="normal"))


if __name__ == "__main__":
    app = App()
    app.mainloop()
