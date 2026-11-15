#!/usr/bin/env python3
import os
import glob
import platform
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk

PATCH_ZIP_URL = "https://github.com/bentley-rr-official/2025-android-patcher/archive/refs/heads/main.zip"
XAPK_URL = "https://drive.usercontent.google.com/download?id=1k9ASR35hKhZX4QftctMHmuJCWRG2s04p&export=download&authuser=0&confirm=t"
BUNDLES_URL = "https://drive.usercontent.google.com/download?id=1o42Q81c9G_fNceEiXSfHEOFjUPx23z6E&export=download&authuser=0&confirm=t"
DEFAULT_PACKAGE = "com.AgainstGravity.RecRoom"


def default_workdir() -> Path:
    base = Path(tempfile.gettempdir())
    return base / "easy-ap"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("easy-ap")
        self.geometry("980x760")
        self.minsize(860, 640)

        self.workdir = default_workdir()
        self.nameserver = ""
        self.package = DEFAULT_PACKAGE
        self.log_queue: queue.Queue = queue.Queue()
        self.ui_queue: queue.Queue = queue.Queue()
        self.selected_device = None
        self.device_event = threading.Event()
        self.nameserver_event = threading.Event()
        self.running = False

        self._build_ui()
        self.after(100, self._drain_queues)
        self.after(300, self.start_auto)

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        header = ttk.Frame(self)
        header.pack(fill="x", **pad)
        ttk.Label(header, text="easy-ap", font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(header, textvariable=self.status_var).pack(anchor="w")
        ttk.Label(header, text=f"Work directory: {self.workdir}").pack(anchor="w")

        progf = ttk.LabelFrame(self, text="Progress")
        progf.pack(fill="x", **pad)
        self.step_var = tk.StringVar(value="Waiting to start...")
        ttk.Label(progf, textvariable=self.step_var).pack(anchor="w", padx=8, pady=(6, 2))
        self.progress = ttk.Progressbar(progf, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=8, pady=(0, 4))
        self.sub_var = tk.StringVar(value="")
        ttk.Label(progf, textvariable=self.sub_var).pack(anchor="w", padx=8, pady=(0, 6))

        devf = ttk.LabelFrame(self, text="Device selection")
        devf.pack(fill="x", **pad)
        self.device_info_var = tk.StringVar(value="No device selection needed yet.")
        ttk.Label(devf, textvariable=self.device_info_var).pack(anchor="w", padx=8, pady=4)
        self.device_buttons_frame = ttk.Frame(devf)
        self.device_buttons_frame.pack(fill="x", padx=8, pady=4)

        actions = ttk.Frame(self)
        actions.pack(fill="x", **pad)
        self.start_btn = ttk.Button(actions, text="Start / Restart", command=self.start_auto)
        self.start_btn.pack(side="left")

        logf = ttk.LabelFrame(self, text="Log")
        logf.pack(fill="both", expand=True, **pad)
        self.log = scrolledtext.ScrolledText(logf, height=20, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    def log_msg(self, msg: str):
        self.log_queue.put(("log", msg))

    def set_status(self, msg: str):
        self.log_queue.put(("status", msg))

    def set_step(self, msg: str):
        self.log_queue.put(("step", msg))

    def set_progress(self, value=None, maximum=None, sub=None, mode=None):
        self.log_queue.put(("progress", value, maximum, sub, mode))

    def ask_nameserver_ui(self):
        self.log_queue.put(("ask_nameserver", None))

    def ask_device_ui(self, devices):
        self.log_queue.put(("ask_device", devices))

    def _drain_queues(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", item[1] + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "status":
                    self.status_var.set(item[1])
                elif kind == "step":
                    self.step_var.set(item[1])
                elif kind == "progress":
                    _, value, maximum, sub, mode = item
                    if mode:
                        cur = str(self.progress.cget("mode"))
                        if cur == "indeterminate" and mode != "indeterminate":
                            try:
                                self.progress.stop()
                            except Exception:
                                pass
                        self.progress.configure(mode=mode)
                        if mode == "indeterminate" and cur != "indeterminate":
                            try:
                                self.progress.start(10)
                            except Exception:
                                pass
                    if maximum is not None:
                        self.progress.configure(maximum=maximum)
                    if value is not None and str(self.progress.cget("mode")) == "determinate":
                        self.progress["value"] = value
                    if sub is not None:
                        self.sub_var.set(sub)
                elif kind == "ask_nameserver":
                    self._prompt_nameserver()
                elif kind == "ask_device":
                    self._show_device_buttons(item[1])
        except queue.Empty:
            pass
        self.after(100, self._drain_queues)

    def _prompt_nameserver(self):
        # Called on UI thread
        ns = simpledialog.askstring("Nameserver", "Enter nameserver (RecNet NameServer Host):", parent=self)
        if ns and ns.strip():
            self.nameserver = ns.strip()
        else:
            self.nameserver = ""
        self.nameserver_event.set()

    def _show_device_buttons(self, devices):
        for w in self.device_buttons_frame.winfo_children():
            w.destroy()
        self.selected_device = None
        self.device_event.clear()
        if not devices:
            self.device_info_var.set("No devices found. Connect your phone with USB debugging enabled and click Retry.")
            ttk.Button(self.device_buttons_frame, text="Retry device check", command=self._retry_devices).pack(side="left", padx=4, pady=4)
            return
        self.device_info_var.set("Select a device to install/push to:")
        for serial, desc in devices:
            txt = f"{serial}" + (f" ({desc})" if desc else "")
            ttk.Button(self.device_buttons_frame, text=txt, command=lambda s=serial: self._select_device(s)).pack(side="left", padx=4, pady=4)

    def _retry_devices(self):
        # trigger recheck by setting event with no selection? handled in worker loop
        self.device_info_var.set("Retrying device detection...")
        self.selected_device = "__retry__"
        self.device_event.set()

    def _select_device(self, serial):
        self.selected_device = serial
        self.device_info_var.set(f"Selected device: {serial}")
        self.device_event.set()

    # ---------- helpers ----------
    def run_cmd(self, cmd, cwd=None, env=None, check=True, capture=False):
        self.log_msg("$ " + " ".join(cmd))
        if capture:
            p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if p.stdout:
                for line in p.stdout.splitlines():
                    self.log_msg(line)
            if check and p.returncode != 0:
                raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(cmd)}")
            return p.stdout or ""
        proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        assert proc.stdout
        for line in proc.stdout:
            self.log_msg(line.rstrip())
        rc = proc.wait()
        if check and rc != 0:
            raise RuntimeError(f"Command failed ({rc}): {' '.join(cmd)}")
        return ""

    def download_file(self, url, dest: Path, label: str):
        dest.parent.mkdir(parents=True, exist_ok=True)
        self.set_step(label)
        self.set_progress(0, 100, f"Starting download: {dest.name}", "determinate")

        def hook(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                pct = min(100, int(downloaded * 100 / total_size))
                mb = downloaded / (1024 * 1024)
                tmb = total_size / (1024 * 1024)
                self.set_progress(pct, 100, f"{dest.name}: {mb:.1f}/{tmb:.1f} MB ({pct}%)", "determinate")
            else:
                mb = downloaded / (1024 * 1024)
                self.set_progress(None, None, f"{dest.name}: {mb:.1f} MB downloaded", "indeterminate")

        urllib.request.urlretrieve(url, dest, reporthook=hook)
        self.set_progress(100, 100, f"Downloaded {dest.name}", "determinate")

    def extract_zip(self, zip_path: Path, dest_dir: Path, label: str):
        self.set_step(label)
        dest_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            total = max(1, len(infos))
            for idx, info in enumerate(infos, 1):
                zf.extract(info, dest_dir)
                pct = int(idx * 100 / total)
                self.set_progress(pct, 100, f"Extracting {idx}/{total}: {Path(info.filename).name}", "determinate")

    # ---------- adb ----------
    def ensure_adb(self):
        self.set_step("Checking adb...")
        self.set_progress(None, None, "Looking for adb", "indeterminate")
        if shutil.which("adb"):
            self.log_msg("adb found: " + shutil.which("adb"))
            return
        self.log_msg("adb not found, attempting to install...")
        self.install_adb()
        if not shutil.which("adb"):
            # also check common platform-tools locations
            candidates = []
            home = Path.home()
            candidates += [home / "platform-tools" / "adb", home / "Android" / "platform-tools" / "adb"]
            if os.name == "nt":
                candidates += [Path("C:/platform-tools/adb.exe"), home / "AppData/Local/Android/Sdk/platform-tools/adb.exe"]
            for c in candidates:
                if c.exists():
                    os.environ["PATH"] = str(c.parent) + os.pathsep + os.environ.get("PATH", "")
                    break
        if not shutil.which("adb"):
            raise RuntimeError("adb is not installed and automatic installation failed. Please install Android platform-tools (adb) and restart.")
        self.log_msg("adb ready: " + shutil.which("adb"))

    def install_adb(self):
        system = platform.system().lower()
        try:
            if system == "linux":
                if shutil.which("apt-get"):
                    self.run_cmd(["sudo", "apt-get", "update"], check=False)
                    self.run_cmd(["sudo", "apt-get", "install", "-y", "adb"], check=False)
                elif shutil.which("dnf"):
                    self.run_cmd(["sudo", "dnf", "install", "-y", "android-tools"], check=False)
                elif shutil.which("pacman"):
                    self.run_cmd(["sudo", "pacman", "-S", "--noconfirm", "android-tools"], check=False)
            elif system == "darwin":
                if shutil.which("brew"):
                    self.run_cmd(["brew", "install", "android-platform-tools"], check=False)
            elif system == "windows":
                if shutil.which("winget"):
                    self.run_cmd(["winget", "install", "-e", "--id", "Google.PlatformTools"], check=False)
        except Exception as e:
            self.log_msg(f"Automatic adb install attempt error: {e}")

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
                desc = " ".join(parts[2:]) if len(parts) > 2 else ""
                devices.append((serial, desc))
        return devices

    def adb(self, args, capture=False, check=True):
        base = ["adb"]
        if self.selected_device and self.selected_device != "__retry__":
            base += ["-s", self.selected_device]
        return self.run_cmd(base + args, capture=capture, check=check)

    # ---------- build env ----------
    def ensure_java(self):
        if shutil.which('java'):
            return True
        self.log_msg('Java not found, attempting to install...')
        system = platform.system().lower()
        try:
            if system == 'linux':
                if shutil.which('apt-get'):
                    self.run_cmd(['sudo','apt-get','update'], check=False)
                    self.run_cmd(['sudo','apt-get','install','-y','openjdk-17-jre-headless'], check=False)
                elif shutil.which('dnf'):
                    self.run_cmd(['sudo','dnf','install','-y','java-17-openjdk-headless'], check=False)
                elif shutil.which('pacman'):
                    self.run_cmd(['sudo','pacman','-S','--noconfirm','jre17-openjdk-headless'], check=False)
            elif system == 'darwin' and shutil.which('brew'):
                self.run_cmd(['brew','install','openjdk@17'], check=False)
            elif system == 'windows' and shutil.which('winget'):
                self.run_cmd(['winget','install','-e','--id','EclipseAdoptium.Temurin.17.JRE'], check=False)
        except Exception as e:
            self.log_msg(f'Java install attempt failed: {e}')
        return bool(shutil.which('java'))

    def ensure_python_deps_env(self, wd: Path):
        """Create/use a venv in workdir so pip installs work on externally-managed systems."""
        venv = wd / 'venv'
        py = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        pip = venv / ('Scripts/pip.exe' if os.name == 'nt' else 'bin/pip')
        if not py.exists():
            self.log_msg('Creating Python virtual environment for build dependencies...')
            self.run_cmd([sys.executable, '-m', 'venv', str(venv)], check=True)
        # install lief
        try:
            self.run_cmd([str(py), '-c', 'import lief'], check=True, capture=True)
            self.log_msg('python lief (venv): OK')
        except Exception:
            self.log_msg('Installing lief in venv...')
            self.run_cmd([str(py), '-m', 'pip', 'install', '--upgrade', 'pip'], check=False)
            self.run_cmd([str(py), '-m', 'pip', 'install', 'lief'], check=False)
        # prepend venv bin to PATH for subsequent commands
        bin_dir = str(venv / ('Scripts' if os.name == 'nt' else 'bin'))
        os.environ['PATH'] = bin_dir + os.pathsep + os.environ.get('PATH', '')
        self.log_msg(f'Using Python env: {bin_dir}')

    def bootstrap_android_tools(self, patcher: Path, wd: Path):
        tools = patcher / 'tools'
        tools.mkdir(parents=True, exist_ok=True)
        need_za = not ((tools / 'zipalign').exists() or shutil.which('zipalign'))
        need_apk = not ((tools / 'lib' / 'apksigner.jar').exists() or shutil.which('apksigner') or (tools / 'apksigner').exists())
        if not (need_za or need_apk):
            return
        system = platform.system().lower()
        if system != 'linux':
            self.log_msg('Automatic Android build-tools bootstrap is currently implemented for Linux; please install Android SDK build-tools manually on this OS.')
            return
        # Download build-tools zip directly (simpler and no sdkmanager/license hassles)
        bt_root = wd / 'android-build-tools'
        urls = [
            'https://dl.google.com/android/repository/build-tools_r34-linux.zip',
            'https://dl.google.com/android/repository/build-tools_r34.0.0-linux.zip',
            'https://dl.google.com/android/repository/34.0.0-linux.zip',
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
                    # zip usually contains android-14/, android-upsidedowncake/, or similar folder
                    candidates = list(tmp.glob('android-*')) + list(tmp.glob('build-tools*')) + [d for d in tmp.iterdir() if d.is_dir()]
                    src = candidates[0] if candidates else None
                    if not src or not src.exists():
                        raise RuntimeError('Could not locate extracted build-tools directory')
                    if bt_root.exists(): shutil.rmtree(bt_root)
                    shutil.move(str(src), str(bt_root))
                    shutil.rmtree(tmp, ignore_errors=True)
                    try: z.unlink()
                    except Exception: pass
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    self.log_msg(f'Build-tools download failed from {url}: {e}')
                    try:
                        if z.exists(): z.unlink()
                    except Exception: pass
            if last_err:
                raise last_err
        za = bt_root / 'zipalign'
        if za.exists():
            try: os.chmod(za, 0o755)
            except Exception: pass
            if need_za and not (tools / 'zipalign').exists():
                shutil.copy2(za, tools / 'zipalign'); os.chmod(tools / 'zipalign', 0o755)
                self.log_msg(f'Installed zipalign to {tools / "zipalign"}')
        aj = bt_root / 'lib' / 'apksigner.jar'
        if aj.exists() and need_apk and not (tools / 'lib' / 'apksigner.jar').exists():
            (tools / 'lib').mkdir(parents=True, exist_ok=True)
            shutil.copy2(aj, tools / 'lib' / 'apksigner.jar')
            self.log_msg(f'Installed apksigner.jar to {tools / "lib" / "apksigner.jar"}')

    def _fix_ndk_layout(self, root: Path):
        # Python zip extraction can drop executable bits and turn symlinks into small text files.
        for p in root.rglob('*'):
            try:
                if p.is_symlink():
                    continue
                if p.is_file():
                    # repair broken symlinks (small text file containing target path/name)
                    if p.stat().st_size <= 4096 and ('/bin/' in str(p) or '/lib' in str(p) or '/prebuilt/' in str(p)):
                        try:
                            data = p.read_bytes()
                            if b'\x00' in data:
                                pass
                            else:
                                s = data.decode('utf-8', 'ignore').strip()
                                if s and '\n' not in s and ' ' not in s and len(s) < 255:
                                    target = (p.parent / s)
                                    # common case: symlink stored as basename or relative path
                                    if target.exists() or (p.parent / Path(s).name).exists():
                                        try:
                                            p.unlink()
                                            os.symlink(s, p)
                                            continue
                                        except Exception:
                                            pass
                        except Exception:
                            pass
                    # make scripts/binaries in bin/prebuilt dirs executable
                    if '/bin/' in str(p) or '/prebuilt/' in str(p):
                        mode = p.stat().st_mode
                        p.chmod(mode | 0o111)
            except Exception:
                pass

    def bootstrap_ndk(self, wd: Path):
        ndk_default = Path.home() / 'x' / 'ndk' / 'android-ndk-r27c'
        env_ndk = os.environ.get('ANDROID_NDK')
        ndk_path = Path(env_ndk) if env_ndk else ndk_default
        clang = ndk_path / 'toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android29-clang++'
        real_clang = ndk_path / 'toolchains/llvm/prebuilt/linux-x86_64/bin/clang'
        ok = clang.exists() and os.access(clang, os.X_OK)
        if ok and real_clang.exists() and not real_clang.is_symlink():
            try:
                # broken extracted symlink becomes tiny text file like "clang\n"
                if real_clang.stat().st_size < 4096:
                    txt = real_clang.read_bytes()
                    if b'\x00' not in txt:
                        ok = False
            except Exception:
                pass
        if ok:
            os.environ['ANDROID_NDK'] = str(ndk_path)
            self.log_msg(f'NDK OK: {ndk_path}')
            return
        if ndk_path.exists():
            self.log_msg(f'Fixing or re-downloading NDK: {ndk_path}')
            self._fix_ndk_layout(ndk_path)
            # recheck after fix
            ok2 = clang.exists() and os.access(clang, os.X_OK)
            if ok2 and real_clang.exists():
                try:
                    if real_clang.is_symlink() or real_clang.stat().st_size > 4096:
                        os.environ['ANDROID_NDK'] = str(ndk_path)
                        self.log_msg(f'NDK OK after repair: {ndk_path}')
                        return
                except Exception:
                    pass
            self.log_msg(f'NDK still incomplete, re-downloading: {ndk_path}')
            try:
                shutil.rmtree(ndk_path)
            except Exception as e:
                self.log_msg(f'Could not remove incomplete NDK: {e}')
        if ndk_path.exists():
            self.log_msg(f'NDK directory exists but is incomplete, re-downloading: {ndk_path}')
            try:
                shutil.rmtree(ndk_path)
            except Exception as e:
                self.log_msg(f'Could not remove incomplete NDK: {e}')
        if platform.system().lower() != 'linux':
            self.log_msg('Automatic NDK bootstrap is currently implemented for Linux; install NDK r27c manually on this OS.')
            return
        # download into expected location
        ndk_path.parent.mkdir(parents=True, exist_ok=True)
        url = 'https://dl.google.com/android/repository/android-ndk-r27c-linux.zip'
        z = wd / 'android-ndk-r27c-linux.zip'
        self.download_file(url, z, 'Downloading Android NDK r27c (large)...')
        tmp = wd / 'ndk_extract'
        if tmp.exists(): shutil.rmtree(tmp)
        self.extract_zip(z, tmp, 'Extracting Android NDK r27c...')
        extracted = tmp / 'android-ndk-r27c'
        if not extracted.exists():
            dirs = [d for d in tmp.iterdir() if d.is_dir()]
            if dirs:
                extracted = dirs[0]
        if not extracted.exists():
            raise RuntimeError('Could not locate extracted NDK directory')
        if ndk_path.exists(): shutil.rmtree(ndk_path)
        shutil.move(str(extracted), str(ndk_path))
        shutil.rmtree(tmp, ignore_errors=True)
        try: z.unlink()
        except Exception: pass
        self._fix_ndk_layout(ndk_path)
        os.environ['ANDROID_NDK'] = str(ndk_path)
        self.log_msg(f'NDK ready: {ndk_path}')

    def find_tool(self, name):
        p = shutil.which(name)
        if p:
            return Path(p)
        candidates = []
        home = Path.home()
        sdk_roots = [os.environ.get('ANDROID_HOME'), os.environ.get('ANDROID_SDK_ROOT'), str(home/'Android/Sdk'), '/usr/lib/android-sdk']
        for root in sdk_roots:
            if not root:
                continue
            r = Path(root)
            candidates += list(r.glob(f'build-tools/*/{name}'))
            candidates += list(r.glob(f'build-tools/*/{name}.exe'))
            candidates += list(r.glob(f'cmdline-tools/latest/bin/{name}'))
        for c in candidates:
            if c.exists():
                return c
        return None

    def ensure_lief(self):
        try:
            import lief  # noqa
            self.log_msg('python lief: OK')
            return True
        except Exception:
            self.log_msg('python lief not found, trying to install (pip --user)...')
            try:
                self.run_cmd([sys.executable, '-m', 'pip', 'install', '--user', 'lief'], check=False)
            except Exception as e:
                self.log_msg(f'lief install attempt failed: {e}')
            try:
                import lief  # noqa
                self.log_msg('python lief: installed')
                return True
            except Exception:
                self.log_msg('python lief still missing (install manually: pip install lief)')
                return False

    def prepare_build_env(self, patcher: Path):
        self.set_step('Preparing build environment...')
        self.set_progress(None, None, 'Checking/installing build dependencies', 'indeterminate')
        wd = self.workdir
        tools = patcher / 'tools'
        tools.mkdir(parents=True, exist_ok=True)

        # python deps in venv (handles externally-managed python)
        try:
            self.ensure_python_deps_env(wd)
        except Exception as e:
            self.log_msg(f'Python env setup issue: {e}')

        # java + android tools + ndk bootstraps
        self.ensure_java()
        try:
            self.bootstrap_android_tools(patcher, wd)
        except Exception as e:
            self.log_msg(f'Android build-tools bootstrap issue: {e}')
        try:
            self.bootstrap_ndk(wd)
        except Exception as e:
            self.log_msg(f'NDK bootstrap issue: {e}')

        # baksmali/smali (needed by pairip_strip)
        def ensure_jar(name, urls):
            dest = tools / f'{name}.jar'
            if dest.exists() and dest.stat().st_size > 0:
                return True
            for url in urls:
                try:
                    self.download_file(url, dest, f'Downloading {name}.jar...')
                    if dest.exists() and dest.stat().st_size > 10000:
                        return True
                except Exception as e:
                    self.log_msg(f'Failed to download {name} from {url}: {e}')
                    try: dest.unlink()
                    except Exception: pass
            return dest.exists()
        if not shutil.which('baksmali') and not (tools / 'baksmali.jar').exists():
            ensure_jar('baksmali', [
                'https://bitbucket.org/JesusFreke/smali/downloads/baksmali-2.5.2.jar',
                'https://repo1.maven.org/maven2/org/smali/baksmali/2.5.2/baksmali-2.5.2.jar',
            ])
        if not shutil.which('smali') and not (tools / 'smali.jar').exists():
            ensure_jar('smali', [
                'https://bitbucket.org/JesusFreke/smali/downloads/smali-2.5.2.jar',
                'https://repo1.maven.org/maven2/org/smali/smali/2.5.2/smali-2.5.2.jar',
            ])

        # keystore
        ks = tools / 'debug.keystore'
        if not ks.exists():
            if shutil.which('keytool'):
                self.log_msg('Creating debug.keystore...')
                mk = patcher / 'scripts' / 'make-keystore.sh'
                if mk.exists():
                    self.run_cmd(['bash', str(mk)], cwd=patcher, check=False)
            else:
                self.log_msg('keytool not found; cannot auto-create debug.keystore')

        # try locate/copy again
        za = self.find_tool('zipalign')
        if za and not (tools / 'zipalign').exists() and za.is_file():
            try:
                shutil.copy2(za, tools / 'zipalign'); os.chmod(tools / 'zipalign', 0o755)
            except Exception: pass
        if not (tools / 'lib' / 'apksigner.jar').exists():
            aj = self.find_tool('apksigner.jar') if hasattr(self, 'find_tool') else None
            for root in [os.environ.get('ANDROID_HOME'), os.environ.get('ANDROID_SDK_ROOT'), str(Path.home()/'Android/Sdk'), str(wd/'android-sdk'), '/usr/lib/android-sdk']:
                if not root: continue
                jars = list(Path(root).glob('build-tools/*/lib/apksigner.jar'))
                if jars:
                    (tools / 'lib').mkdir(parents=True, exist_ok=True)
                    try: shutil.copy2(jars[-1], tools / 'lib' / 'apksigner.jar')
                    except Exception: pass
                    break

        missing = []
        if not shutil.which('java'): missing.append('java')
        if not (tools / 'zipalign').exists() and not shutil.which('zipalign'): missing.append('zipalign (Android build-tools)')
        if not (tools / 'lib' / 'apksigner.jar').exists() and not shutil.which('apksigner'): missing.append('apksigner (Android build-tools)')
        if not (tools / 'debug.keystore').exists(): missing.append('tools/debug.keystore')
        if not shutil.which('baksmali') and not (tools / 'baksmali.jar').exists(): missing.append('baksmali')
        if not shutil.which('smali') and not (tools / 'smali.jar').exists(): missing.append('smali')
        ndk = os.environ.get('ANDROID_NDK') or str(Path.home()/'x'/'ndk'/'android-ndk-r27c')
        if not Path(ndk).exists(): missing.append(f'Android NDK r27c (expected at {ndk})')
        try:
            subprocess.run([sys.executable, '-c', 'import lief'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception:
            # check venv python
            vpy = wd / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            ok = False
            if vpy.exists():
                r = subprocess.run([str(vpy), '-c', 'import lief'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                ok = (r.returncode == 0)
            if not ok:
                missing.append('python lief')
        if missing:
            msg = 'Missing build dependencies:\n- ' + '\n- '.join(missing)
            self.log_msg(msg)
            self.log_msg('Build may fail if required tools are still missing.')
        else:
            self.log_msg('Build environment looks ready.')

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
            if wd.exists():
                self.log_msg(f"Cleaning work directory: {wd}")
                shutil.rmtree(wd, ignore_errors=True)
            wd.mkdir(parents=True, exist_ok=True)
            self.set_status("Working...")

            # 1 patcher
            patch_zip = wd / "2025-android-patcher.zip"
            self.download_file(PATCH_ZIP_URL, patch_zip, "Downloading patcher...")
            extract_root = wd / "patcher_extract"
            if extract_root.exists():
                shutil.rmtree(extract_root)
            self.extract_zip(patch_zip, extract_root, "Extracting patcher...")
            extracted = extract_root / "2025-android-patcher-main"
            if not extracted.exists():
                dirs = [p for p in extract_root.iterdir() if p.is_dir()]
                if len(dirs) == 1:
                    extracted = dirs[0]
                else:
                    raise RuntimeError("Could not find extracted patcher folder")
            patcher = wd / "2025-android-patcher"
            if patcher.exists():
                shutil.rmtree(patcher)
            extracted.rename(patcher)
            self.log_msg(f"Patcher ready: {patcher}")
            self.set_progress(100, 100, "Patcher downloaded and extracted", "determinate")

            # ask nameserver after downloading patcher
            self.set_step("Nameserver required")
            self.set_status("Waiting for nameserver input...")
            self.nameserver = ""
            self.nameserver_event.clear()
            self.ask_nameserver_ui()
            self.nameserver_event.wait()
            if not self.nameserver:
                raise RuntimeError("Nameserver is required to continue.")
            self.log_msg(f"Using nameserver: {self.nameserver}")

            # 2 xapk
            xapk = wd / "base.xapk"
            self.download_file(XAPK_URL, xapk, "Downloading base.xapk...")

            # 3 bundles
            bundles_zip = wd / "bundles.zip"
            self.download_file(BUNDLES_URL, bundles_zip, "Downloading bundles.zip...")
            self.extract_zip(bundles_zip, patcher / "bundles", "Extracting bundles into patcher/bundles...")
            bcount = len(list((patcher / "bundles").glob("*.bundle")))
            self.log_msg(f"Bundle files in patcher/bundles: {bcount}")

            # write config
            self.write_config(patcher, self.nameserver)

            # 4 build
            self.prepare_build_env(patcher)
            self.set_step("Building...")
            self.set_progress(None, None, "Running build-phone.sh (this may take a while)", "indeterminate")
            env = os.environ.copy()
            env["CONFIG"] = str(patcher / "2025.cfg")
            vbin = self.workdir / 'venv' / ('Scripts' if os.name == 'nt' else 'bin')
            if vbin.exists():
                env['PATH'] = str(vbin) + os.pathsep + env.get('PATH','')
            if os.environ.get('ANDROID_NDK'):
                env['ANDROID_NDK'] = os.environ['ANDROID_NDK']
            if os.environ.get('ANDROID_HOME'):
                env['ANDROID_HOME'] = os.environ['ANDROID_HOME']
            if os.environ.get('ANDROID_SDK_ROOT'):
                env['ANDROID_SDK_ROOT'] = os.environ['ANDROID_SDK_ROOT']
            self.run_cmd(["bash", str(patcher / "scripts" / "build-phone.sh"), str(xapk)], cwd=patcher, env=env)
            self.set_progress(100, 100, "Build complete", "determinate")

            # 5 adb + device + install/push
            self.ensure_adb()
            self.selected_device = None
            while True:
                devices = self.get_adb_devices()
                if not devices:
                    self.set_step("No devices found")
                    self.set_status("No devices found")
                    self.device_event.clear()
                    self.ask_device_ui([])
                    self.device_event.wait()
                    if self.selected_device == "__retry__":
                        self.selected_device = None
                        continue
                    # should not happen, but loop
                    continue
                # show selection (even if one, per request to select from buttons)
                self.set_step("Select device")
                self.set_status("Waiting for device selection...")
                self.device_event.clear()
                self.ask_device_ui(devices)
                self.device_event.wait()
                if self.selected_device == "__retry__":
                    self.selected_device = None
                    continue
                if self.selected_device:
                    break

            # install APKs
            signed = patcher / "build" / "phone" / "signed"
            apks = sorted(signed.glob("*.apk"))
            if not apks:
                raise RuntimeError(f"No APKs found in {signed}")
            self.install_apks(apks)

            # push bundles
            self.push_bundles(patcher / "bundles")

            self.set_step("All done")
            self.set_status("Completed successfully")
            self.set_progress(100, 100, "Install and bundle push complete", "determinate")
            self.log_msg("DONE: build, install, and bundle push finished.")
        except Exception as e:
            self.log_msg(f"[ERROR] {e}")
            self.set_step("Error")
            self.set_status("Error")
            self.after(0, lambda: messagebox.showerror("easy-ap", str(e)))
        finally:
            self.running = False
            self.after(0, lambda: self.start_btn.configure(state="normal"))

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
        self.log_msg(f"Wrote {patcher / '2025.cfg'}")

    def install_apks(self, apks):
        self.set_step("Installing APKs...")
        total = len(apks)
        # try install-multiple as a whole? better per-apk progress as requested
        for i, apk in enumerate(apks, 1):
            pct = int((i - 1) * 100 / total)
            self.set_progress(pct, 100, f"Installing APK {i}/{total}: {apk.name}", "determinate")
            self.adb(["install", "-r", str(apk)])
            pct = int(i * 100 / total)
            self.set_progress(pct, 100, f"Installed {i}/{total}: {apk.name}", "determinate")
        self.log_msg(f"Installed {total} APK(s)")

    def push_bundles(self, bundles_dir: Path):
        self.set_step("Pushing bundles/OBB data...")
        files = sorted([p for p in bundles_dir.iterdir() if p.is_file() and p.suffix == ".bundle"])
        if not files:
            files = sorted([p for p in bundles_dir.iterdir() if p.is_file()])
        if not files:
            self.log_msg("No bundle files found to push; skipping.")
            self.set_progress(100, 100, "No bundles to push", "determinate")
            return
        remote = f"/sdcard/Android/data/{self.package}/files/AssetPackStubs/OutfitsAssetPack"
        self.adb(["shell", "mkdir", "-p", remote])
        total = len(files)
        for i, f in enumerate(files, 1):
            pct = int((i - 1) * 100 / total)
            self.set_progress(pct, 100, f"Pushing bundle {i}/{total}: {f.name}", "determinate")
            self.adb(["push", str(f), f"{remote}/{f.name}"])
            pct = int(i * 100 / total)
            self.set_progress(pct, 100, f"Pushed {i}/{total}: {f.name}", "determinate")
        self.log_msg(f"Pushed {total} bundle file(s) to {remote}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
