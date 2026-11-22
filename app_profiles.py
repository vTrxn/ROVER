import ctypes
from ctypes import wintypes
import os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

try:
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
except Exception:
    pass


MEDIA_OVERRIDE_MAP = {
    "D_LEFT": "media_rw",
    "D_RIGHT": "media_ff",
    "D_UP": "vol_up",
    "D_DOWN": "vol_down",
}


def get_foreground_process_name():
    """Return lowercase executable name (e.g. 'netflix.exe') of the current foreground window."""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not h_proc:
            return ""
        try:
            buf_len = wintypes.DWORD(512)
            buf = ctypes.create_unicode_buffer(buf_len.value)
            if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(buf_len)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(h_proc)
    except Exception:
        pass
    return ""


class AppProfileManager:
    """Evaluates foreground app rules to auto-switch Game Mode and apply Media button overrides."""

    def __init__(self, config_store):
        self.config = config_store
        self.last_exe = ""
        self.active_profile = "default"  # "default" | "game" | "media"
        self.auto_switched_to_game = False

    @staticmethod
    def match_exe(exe_name, game_apps, media_apps):
        exe = (exe_name or "").strip().lower()
        if not exe:
            return "default"
        game_set = {g.strip().lower() for g in game_apps if g and g.strip()}
        if exe in game_set:
            return "game"
        media_set = {m.strip().lower() for m in media_apps if m and m.strip()}
        if exe in media_set:
            return "media"
        return "default"

    def evaluate(self, exe_name=None):
        """Return (profile_kind, exe_name, changed_bool)."""
        if not self.config.get("auto_profiles_enabled", True):
            changed = self.active_profile != "default"
            self.active_profile = "default"
            self.last_exe = exe_name if exe_name is not None else self.last_exe
            return "default", self.last_exe, changed

        exe = (get_foreground_process_name() if exe_name is None else exe_name).lower()
        game_apps, media_apps = self.config.snapshot_profile_lists()
        kind = self.match_exe(exe, game_apps, media_apps)
        changed = (kind != self.active_profile) or (exe != self.last_exe)
        self.last_exe = exe
        self.active_profile = kind
        return kind, exe, changed

    def effective_button_map(self, base_map):
        if self.active_profile == "media":
            merged = dict(base_map)
            merged.update(MEDIA_OVERRIDE_MAP)
            return merged
        return base_map
