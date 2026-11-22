import ctypes
from ctypes import wintypes
import datetime
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback

APP_NAME = "Rover"
APP_VERSION = "2.1.0"
UNINSTALL_REG_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Rover"

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
ERROR_LOG_PATH = os.path.join(CONFIG_DIR, "error.log")
PID_FILE = os.path.join(tempfile.gettempdir(), "rover.pid")

ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
EVENT_SHOW_NAME = "Local\\RoverShowUI"
EVENT_QUIT_NAME = "Local\\RoverQuit"
MUTEX_NAME = "Local\\RoverSingleInstance"

DEFAULT_BUTTON_MAP = {
    "A": "left_click",
    "B": "escape",
    "X": "show_keyboard",
    "Y": "right_click",
    "LB": "none",
    "RB": "left_click",
    "LT": "precision",
    "RT": "browser_back",
    "L3": "play_pause",
    "R3": "none",
    "START": "enter",
    "D_UP": "scroll_up",
    "D_DOWN": "scroll_down",
    "D_LEFT": "scroll_left",
    "D_RIGHT": "scroll_right",
}

DEFAULT_CONFIG = {
    "schema_version": 2,
    "theme": "dark",
    "deadzone": 4500,
    "base_speed": 20.0,
    "precision_factor": 0.32,
    "accel_exp": 1.7,
    "scroll_step": 90,
    "keyboard_at_top": False,
    "auto_keyboard_ibeam": True,
    "show_toasts": True,
    "tactile_sound": True,
    "minimize_to_tray": True,
    "button_map": dict(DEFAULT_BUTTON_MAP),
}

# 64-bit safe Win32 kernel32 & shell32 prototypes
kernel32 = ctypes.windll.kernel32
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenEventW.restype = wintypes.HANDLE
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.SetEvent.restype = wintypes.BOOL
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.GetLastError.argtypes = []
kernel32.GetLastError.restype = wintypes.DWORD

shell32 = ctypes.windll.shell32
shell32.SHGetFolderPathW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR]
shell32.SHGetFolderPathW.restype = ctypes.c_long


def log_error(context, exc=None):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {context}\n")
            if exc is not None:
                traceback.print_exception(type(exc), exc, exc.__traceback__, file=f)
            else:
                traceback.print_exc(file=f)
    except Exception:
        pass


def get_app_executable(entry_script=None):
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    if entry_script:
        return os.path.abspath(entry_script)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "Rover.py")


def get_desktop_dir():
    try:
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        if shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0 and buf.value:
            return buf.value
    except Exception as exc:
        log_error("get_desktop_dir", exc)
    return os.path.join(os.path.expanduser("~"), "Desktop")


def get_startup_dir():
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def get_startup_shortcut_path():
    return os.path.join(get_startup_dir(), f"{APP_NAME}.lnk")


def remove_legacy_startup_shortcuts(startup_dir=None):
    sdir = startup_dir or get_startup_dir()
    for legacy_name in ("BedAssistant.lnk", "GameSir Assistant.lnk"):
        legacy = os.path.join(sdir, legacy_name)
        if os.path.exists(legacy):
            try:
                os.remove(legacy)
            except Exception as exc:
                log_error(f"remove_legacy_startup_shortcuts({legacy_name})", exc)


def create_shortcut(lnk_path, target, args="", workdir="", icon_path=""):
    """Create a Windows .lnk shortcut passing paths via environment variables to avoid command injection."""
    os.makedirs(os.path.dirname(os.path.abspath(lnk_path)), exist_ok=True)
    env = os.environ.copy()
    env["ROVER_LNK"] = os.path.abspath(lnk_path)
    env["ROVER_TARGET"] = os.path.abspath(target)
    env["ROVER_ARGS"] = str(args or "")
    env["ROVER_WORKDIR"] = os.path.abspath(workdir) if workdir else os.path.dirname(os.path.abspath(target))
    env["ROVER_ICON"] = os.path.abspath(icon_path) if (icon_path and os.path.exists(icon_path)) else ""

    ps_script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        "$s = $ws.CreateShortcut($env:ROVER_LNK); "
        "$s.TargetPath = $env:ROVER_TARGET; "
        "$s.Arguments = $env:ROVER_ARGS; "
        "$s.WorkingDirectory = $env:ROVER_WORKDIR; "
        "if ($env:ROVER_ICON) { $s.IconLocation = $env:ROVER_ICON }; "
        "$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_script],
        env=env,
        creationflags=0x08000000,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def is_startup_enabled():
    return os.path.exists(get_startup_shortcut_path())


def set_startup_enabled(enabled, icon_path="", entry_script=None):
    lnk_path = get_startup_shortcut_path()
    if not enabled:
        try:
            if os.path.exists(lnk_path):
                os.remove(lnk_path)
            remove_legacy_startup_shortcuts()
            return True
        except Exception as exc:
            log_error("set_startup_enabled(False)", exc)
            return False

    try:
        exe = get_app_executable(entry_script)
        workdir = os.path.dirname(exe)
        if getattr(sys, "frozen", False):
            target = exe
            args = "--minimized"
        else:
            py_dir = os.path.dirname(sys.executable)
            pythonw = os.path.join(py_dir, "pythonw.exe")
            target = pythonw if os.path.exists(pythonw) else sys.executable
            args = f'"{exe}" --minimized'
        create_shortcut(lnk_path, target, args=args, workdir=workdir, icon_path=icon_path)
        remove_legacy_startup_shortcuts()
        return True
    except Exception as exc:
        log_error("set_startup_enabled(True)", exc)
        return False


def signal_quit_and_wait(timeout_sec=0.6):
    """Signal a running Rover instance via Local\\RoverQuit and wait for its mutex/event to close."""
    h_quit = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, EVENT_QUIT_NAME)
    if not h_quit:
        return False
    try:
        kernel32.SetEvent(h_quit)
    finally:
        kernel32.CloseHandle(h_quit)

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        probe = kernel32.OpenEventW(SYNCHRONIZE, False, EVENT_QUIT_NAME)
        if not probe:
            return True
        kernel32.CloseHandle(probe)
        time.sleep(0.03)
    return True


def default_config_copy():
    cfg = dict(DEFAULT_CONFIG)
    cfg["button_map"] = dict(DEFAULT_BUTTON_MAP)
    return cfg


class ConfigStore:
    """Thread-safe configuration store with atomic file replacement and schema validation."""

    def __init__(self, valid_themes=("dark", "light"), valid_actions=None):
        self._lock = threading.RLock()
        self._valid_themes = set(valid_themes)
        self._valid_actions = set(valid_actions) if valid_actions else None
        self.data = default_config_copy()
        self.load()

    @property
    def lock(self):
        return self._lock

    def __getitem__(self, key):
        with self._lock:
            return self.data[key]

    def __setitem__(self, key, value):
        with self._lock:
            self.data[key] = value

    def get(self, key, default=None):
        with self._lock:
            return self.data.get(key, default)

    def set_and_save(self, key, value):
        with self._lock:
            self.data[key] = value
            self.save()

    def set_button_action(self, btn_id, action_id):
        with self._lock:
            self.data["button_map"][btn_id] = action_id
            self.save()

    def reset_buttons(self):
        with self._lock:
            self.data["button_map"] = dict(DEFAULT_BUTTON_MAP)
            self.save()

    def reset_sensitivity(self):
        with self._lock:
            for k in ("deadzone", "base_speed", "precision_factor", "accel_exp", "scroll_step"):
                self.data[k] = DEFAULT_CONFIG[k]
            self.save()

    def reset_all(self):
        with self._lock:
            fresh = default_config_copy()
            self.data.clear()
            self.data.update(fresh)
            self.save()

    def snapshot_mouse_params(self):
        with self._lock:
            return (
                int(self.data["deadzone"]),
                float(self.data["base_speed"]),
                float(self.data["precision_factor"]),
                float(self.data["accel_exp"]),
                int(self.data["scroll_step"]),
                bool(self.data["auto_keyboard_ibeam"]),
                dict(self.data["button_map"]),
            )

    def load(self):
        with self._lock:
            cfg = default_config_copy()
            src_path = CONFIG_PATH
            if not os.path.exists(src_path):
                legacy_cfg = os.path.join(
                    os.environ.get("APPDATA", os.path.expanduser("~")),
                    "BedAssistant",
                    "config.json",
                )
                if os.path.exists(legacy_cfg):
                    src_path = legacy_cfg
            try:
                if os.path.exists(src_path):
                    with open(src_path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    if isinstance(raw, dict):
                        raw_schema = raw.get("schema_version", 1)
                        for k, default_v in DEFAULT_CONFIG.items():
                            if k == "button_map":
                                raw_map = raw.get("button_map")
                                if isinstance(raw_map, dict):
                                    for bid in DEFAULT_BUTTON_MAP:
                                        act = raw_map.get(bid)
                                        if isinstance(act, str) and (
                                            self._valid_actions is None or act in self._valid_actions
                                        ):
                                            cfg["button_map"][bid] = act
                            elif k in raw and isinstance(raw[k], type(default_v)):
                                cfg[k] = raw[k]
                        if raw_schema < 2:
                            cfg["schema_version"] = 2
                            cfg["button_map"]["B"] = "escape"
                            if cfg["button_map"].get("Y") == "none":
                                cfg["button_map"]["Y"] = "right_click"
                            self.data = cfg
                            self.save()
                if src_path != CONFIG_PATH and os.path.exists(src_path):
                    self.data = cfg
                    self.save()
            except Exception as exc:
                log_error("ConfigStore.load", exc)

            if cfg["theme"] not in self._valid_themes:
                cfg["theme"] = "dark"
            self.data = cfg
            return cfg

    def save(self):
        with self._lock:
            tmp_path = None
            try:
                os.makedirs(CONFIG_DIR, exist_ok=True)
                fd, tmp_path = tempfile.mkstemp(prefix="cfg_", suffix=".tmp", dir=CONFIG_DIR)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2)
                os.replace(tmp_path, CONFIG_PATH)
            except Exception as exc:
                log_error("ConfigStore.save", exc)
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass


class SingleInstanceGuard:
    """Manages single-instance mutex, show/quit named events, and PID lifecycle."""

    def __init__(self):
        self._mutex = None
        self._show_event = None
        self._quit_event = None

    def acquire_or_dispatch(self, argv):
        """Return True if this instance acquired the primary mutex, or False if dispatched to an existing one."""
        args = {a.lower() for a in argv}
        if "--quit" in args:
            signal_quit_and_wait(timeout_sec=0.6)
            return False

        self._mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            if "--minimized" not in args and "--tray" not in args:
                h_show = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, EVENT_SHOW_NAME)
                if h_show:
                    kernel32.SetEvent(h_show)
                    kernel32.CloseHandle(h_show)
            self.close()
            return False

        self._show_event = kernel32.CreateEventW(None, False, False, EVENT_SHOW_NAME)
        self._quit_event = kernel32.CreateEventW(None, False, False, EVENT_QUIT_NAME)
        try:
            with open(PID_FILE, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except Exception as exc:
            log_error("SingleInstanceGuard.write_pid", exc)
        return True

    def poll_events(self):
        """Return (show_requested, quit_requested)."""
        show_req = bool(self._show_event and kernel32.WaitForSingleObject(self._show_event, 0) == 0)
        quit_req = bool(self._quit_event and kernel32.WaitForSingleObject(self._quit_event, 0) == 0)
        return show_req, quit_req

    def close(self):
        for attr in ("_show_event", "_quit_event", "_mutex"):
            h = getattr(self, attr, None)
            if h:
                try:
                    kernel32.CloseHandle(h)
                except Exception:
                    pass
                setattr(self, attr, None)
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        except Exception:
            pass
