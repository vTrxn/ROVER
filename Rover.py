import atexit
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk

import pystray

from gamepad_ui import (
    ACTION_LABELS,
    BUTTON_LABELS,
    BUTTON_ORDER,
    DEFAULT_BUTTON_MAP,
    ActionPickerModal,
    GamepadDiagram,
)
from ui_theme import (
    FONT_FAMILY,
    THEMES,
    MonoButton,
    SegmentedControl,
    StepperControl,
    ToggleSwitch,
    apply_dwm_window_theme,
    build_tray_pil_image,
    font_tuple,
    get_resource_path,
    load_bundled_fonts,
)

APP_NAME = "Rover"
APP_VERSION = "2.0.0"

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
PID_FILE = os.path.join(tempfile.gettempdir(), "rover.pid")

DEFAULT_CONFIG = {
    "theme": "dark",
    "deadzone": 4500,
    "base_speed": 20.0,
    "precision_factor": 0.32,
    "accel_exp": 1.7,
    "scroll_step": 90,
    "keyboard_at_top": False,
    "auto_keyboard_ibeam": True,
    "show_toasts": True,
    "minimize_to_tray": True,
    "button_map": dict(DEFAULT_BUTTON_MAP),
}


def get_app_executable():
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(__file__)


def get_startup_shortcut_path():
    appdata = os.environ.get("APPDATA", "")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", f"{APP_NAME}.lnk")


def is_startup_enabled():
    return os.path.exists(get_startup_shortcut_path())


def set_startup_enabled(enabled):
    lnk_path = get_startup_shortcut_path()
    if not enabled:
        try:
            if os.path.exists(lnk_path):
                os.remove(lnk_path)
            for legacy_name in ("BedAssistant.lnk", "GameSir Assistant.lnk"):
                legacy = os.path.join(os.path.dirname(lnk_path), legacy_name)
                if os.path.exists(legacy):
                    os.remove(legacy)
            return True
        except Exception:
            return False

    try:
        os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
        exe = get_app_executable()
        if getattr(sys, "frozen", False):
            target = exe
            args = "--minimized"
            workdir = os.path.dirname(exe)
        else:
            py_dir = os.path.dirname(sys.executable)
            pythonw = os.path.join(py_dir, "pythonw.exe")
            target = pythonw if os.path.exists(pythonw) else sys.executable
            args = f'"{exe}" --minimized'
            workdir = os.path.dirname(exe)
        ico_path = get_resource_path(os.path.join("assets", "app.ico"))
        ps = (
            f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{lnk_path}");'
            f'$s.TargetPath="{target}";'
            f'$s.Arguments="{args.replace(chr(34), "`" + chr(34))}";'
            f'$s.WorkingDirectory="{workdir}";'
        )
        if os.path.exists(ico_path):
            ps += f'$s.IconLocation="{ico_path}";'
        ps += "$s.Save()"
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=0x08000000,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except Exception:
        return False


def default_config_copy():
    cfg = dict(DEFAULT_CONFIG)
    cfg["button_map"] = dict(DEFAULT_BUTTON_MAP)
    return cfg


def load_config():
    cfg = default_config_copy()
    src_path = CONFIG_PATH
    if not os.path.exists(src_path):
        legacy_cfg = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "BedAssistant", "config.json")
        if os.path.exists(legacy_cfg):
            src_path = legacy_cfg
    try:
        if os.path.exists(src_path):
            with open(src_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, default_v in DEFAULT_CONFIG.items():
                    if k == "button_map":
                        raw_map = data.get("button_map")
                        if isinstance(raw_map, dict):
                            for bid in DEFAULT_BUTTON_MAP:
                                act = raw_map.get(bid)
                                if isinstance(act, str) and act in ACTION_LABELS:
                                    cfg["button_map"][bid] = act
                    elif k in data and isinstance(data[k], type(default_v)):
                        cfg[k] = data[k]
        if src_path != CONFIG_PATH and os.path.exists(src_path):
            save_config(cfg)
    except Exception:
        pass
    if cfg["theme"] not in THEMES:
        cfg["theme"] = "dark"
    return cfg


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


# Named Win32 events coordinate single-instance show/quit without opening network sockets
kernel32 = ctypes.windll.kernel32
ERROR_ALREADY_EXISTS = 183
EVENT_SHOW_NAME = "Local\\RoverShowUI"
EVENT_QUIT_NAME = "Local\\RoverQuit"
MUTEX_NAME = "Local\\RoverSingleInstance"

_args = set(a.lower() for a in sys.argv[1:])
if "--quit" in _args:
    h_quit = kernel32.OpenEventW(0x0002, False, EVENT_QUIT_NAME)
    if h_quit:
        kernel32.SetEvent(h_quit)
        kernel32.CloseHandle(h_quit)
    sys.exit(0)

_mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
    if "--minimized" not in _args and "--tray" not in _args:
        h_show = kernel32.OpenEventW(0x0002, False, EVENT_SHOW_NAME)
        if h_show:
            kernel32.SetEvent(h_show)
            kernel32.CloseHandle(h_show)
    sys.exit(0)

_show_event = kernel32.CreateEventW(None, False, False, EVENT_SHOW_NAME)
_quit_event = kernel32.CreateEventW(None, False, False, EVENT_QUIT_NAME)

try:
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
except Exception:
    pass


# Windows API & XInput setup
user32 = ctypes.windll.user32
user32.OpenDesktopW.restype = wintypes.HANDLE
user32.CloseDesktop.argtypes = [wintypes.HANDLE]
user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
user32.LoadCursorW.restype = wintypes.HANDLE

xinput = None
xinput_dll_name = "No disponible"
for _dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
    try:
        xinput = getattr(ctypes.windll, _dll)
        xinput_dll_name = f"{_dll}.dll"
        break
    except Exception:
        continue

if xinput is not None:
    try:
        xinput_get_state = xinput[100]
    except Exception:
        xinput_get_state = xinput.XInputGetState
else:
    xinput_get_state = None


def switch_to_interactive_desktop():
    try:
        h = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if h:
            user32.SetThreadDesktop(h)
            user32.CloseDesktop(h)
    except Exception:
        pass


switch_to_interactive_desktop()


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.c_ulong),
        ("Gamepad", XINPUT_GAMEPAD),
    ]


JOY_RETURNALL = 0x000000FF
JOYCAPS_HASZ = 0x0001
JOYCAPS_HASR = 0x0002
JOYCAPS_HASU = 0x0004
JOYCAPS_HASV = 0x0008

JOY_BTN_TO_XINPUT = (
    (0x0001, 0x1000),  # A
    (0x0002, 0x2000),  # B
    (0x0004, 0x4000),  # X
    (0x0008, 0x8000),  # Y
    (0x0010, 0x0100),  # LB
    (0x0020, 0x0200),  # RB
    (0x0040, 0x0020),  # View / -
    (0x0080, 0x0010),  # Start / +
    (0x0100, 0x0040),  # L3
    (0x0200, 0x0080),  # R3
    (0x0400, 0x0400),  # Home
    (0x1000, 0x0400),  # Alternate HID guide bit
)


class JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("dwXpos", wintypes.DWORD),
        ("dwYpos", wintypes.DWORD),
        ("dwZpos", wintypes.DWORD),
        ("dwRpos", wintypes.DWORD),
        ("dwUpos", wintypes.DWORD),
        ("dwVpos", wintypes.DWORD),
        ("dwButtons", wintypes.DWORD),
        ("dwButtonNumber", wintypes.DWORD),
        ("dwPOV", wintypes.DWORD),
        ("dwReserved1", wintypes.DWORD),
        ("dwReserved2", wintypes.DWORD),
    ]


class JOYCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("szPname", ctypes.c_wchar * 32),
        ("wXmin", ctypes.c_uint),
        ("wXmax", ctypes.c_uint),
        ("wYmin", ctypes.c_uint),
        ("wYmax", ctypes.c_uint),
        ("wZmin", ctypes.c_uint),
        ("wZmax", ctypes.c_uint),
        ("wNumButtons", ctypes.c_uint),
        ("wPeriodMin", ctypes.c_uint),
        ("wPeriodMax", ctypes.c_uint),
        ("wRmin", ctypes.c_uint),
        ("wRmax", ctypes.c_uint),
        ("wUmin", ctypes.c_uint),
        ("wUmax", ctypes.c_uint),
        ("wVmin", ctypes.c_uint),
        ("wVmax", ctypes.c_uint),
        ("wCaps", ctypes.c_uint),
        ("wMaxAxes", ctypes.c_uint),
        ("wNumAxes", ctypes.c_uint),
        ("wMaxButtons", ctypes.c_uint),
        ("szRegKey", ctypes.c_wchar * 32),
        ("szOEMVxD", ctypes.c_wchar * 260),
    ]


try:
    winmm = ctypes.windll.winmm
    winmm_joy_get_pos_ex = winmm.joyGetPosEx
    winmm_joy_get_dev_caps = winmm.joyGetDevCapsW
except Exception:
    winmm = None
    winmm_joy_get_pos_ex = None
    winmm_joy_get_dev_caps = None

_joy_info = JOYINFOEX()
_joy_info.dwSize = ctypes.sizeof(JOYINFOEX)
_joy_info.dwFlags = JOY_RETURNALL
_joy_caps_cache = {}
_last_winmm_scan = 0.0


def _gp_has_input(gp, stick_thresh=11000):
    """Return True if any button, trigger, or stick currently deviates beyond idle thresholds."""
    return (
        gp.wButtons != 0
        or gp.bLeftTrigger > 45
        or gp.bRightTrigger > 45
        or abs(gp.sThumbLX) > stick_thresh
        or abs(gp.sThumbLY) > stick_thresh
        or abs(gp.sThumbRX) > stick_thresh
        or abs(gp.sThumbRY) > stick_thresh
    )


def _norm_joy_axis(val, vmin, vmax, invert=False):
    if vmax <= vmin:
        return 0
    scaled = ((int(val) - int(vmin)) / float(int(vmax) - int(vmin))) * 65535.0 - 32768.0
    out = int(round(-scaled if invert else scaled))
    return max(-32768, min(32767, out))


def _get_joy_caps(joy_id):
    if joy_id in _joy_caps_cache:
        return _joy_caps_cache[joy_id]
    caps = JOYCAPSW()
    if winmm_joy_get_dev_caps is not None and winmm_joy_get_dev_caps(joy_id, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
        _joy_caps_cache[joy_id] = caps
        return caps
    return None


def _populate_state_from_joy(joy_id, info, target_state):
    """Map WinMM JOYINFOEX HID input into XINPUT_STATE fields."""
    caps = _get_joy_caps(joy_id)
    xmin, xmax = (caps.wXmin, caps.wXmax) if caps else (0, 65535)
    ymin, ymax = (caps.wYmin, caps.wYmax) if caps else (0, 65535)
    zmin, zmax = (caps.wZmin, caps.wZmax) if caps else (0, 65535)
    rmin, rmax = (caps.wRmin, caps.wRmax) if caps else (0, 65535)
    umin, umax = (caps.wUmin, caps.wUmax) if caps else (0, 65535)
    vmin, vmax = (caps.wVmin, caps.wVmax) if caps else (0, 65535)
    wcaps = caps.wCaps if caps else (JOYCAPS_HASZ | JOYCAPS_HASR)

    gp = target_state.Gamepad
    gp.sThumbLX = _norm_joy_axis(info.dwXpos, xmin, xmax, invert=False)
    gp.sThumbLY = _norm_joy_axis(info.dwYpos, ymin, ymax, invert=True)

    if (wcaps & JOYCAPS_HASZ) and (wcaps & JOYCAPS_HASR):
        gp.sThumbRX = _norm_joy_axis(info.dwZpos, zmin, zmax, invert=False)
        gp.sThumbRY = _norm_joy_axis(info.dwRpos, rmin, rmax, invert=True)
    elif (wcaps & JOYCAPS_HASU) and (wcaps & JOYCAPS_HASV):
        gp.sThumbRX = _norm_joy_axis(info.dwUpos, umin, umax, invert=False)
        gp.sThumbRY = _norm_joy_axis(info.dwVpos, vmin, vmax, invert=True)
    else:
        gp.sThumbRX = 0
        gp.sThumbRY = 0

    wbtn = 0
    raw_btns = info.dwButtons
    for jmask, xmask in JOY_BTN_TO_XINPUT:
        if raw_btns & jmask:
            wbtn |= xmask

    pov = info.dwPOV
    if pov != 0xFFFF and pov < 36000:
        if pov <= 4500 or pov >= 31500:
            wbtn |= 0x0001
        if 4500 <= pov <= 13500:
            wbtn |= 0x0008
        if 13500 <= pov <= 22500:
            wbtn |= 0x0002
        if 22500 <= pov <= 31500:
            wbtn |= 0x0004

    gp.wButtons = wbtn
    gp.bLeftTrigger = 0
    gp.bRightTrigger = 0
    return caps.szPname.strip() if caps and caps.szPname else ""


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    _anonymous_ = ("_i",)
    _fields_ = [("type", wintypes.DWORD), ("_i", _I)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hCursor", wintypes.HANDLE),
        ("ptScreenPos", wintypes.POINT),
    ]


H_IBEAM = user32.LoadCursorW(None, 32513)
INPUT_SIZE = ctypes.sizeof(INPUT)

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_C = 0x43
VK_V = 0x56
VK_W = 0x57
VK_LWIN = 0x5B
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_OEM_PLUS = 0xBB
VK_OEM_MINUS = 0xBD

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000


def is_cursor_ibeam():
    ci = CURSORINFO(cbSize=ctypes.sizeof(CURSORINFO))
    if user32.GetCursorInfo(ctypes.byref(ci)):
        return ci.hCursor == H_IBEAM
    return False


def send_unicode_char(char):
    code = ord(char)
    arr = (INPUT * 2)(
        INPUT(type=1, ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)),
        INPUT(type=1, ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)),
    )
    user32.SendInput(2, ctypes.byref(arr), INPUT_SIZE)


def send_unicode_text(text):
    for ch in text:
        send_unicode_char(ch)


def send_vk_key(vk, extended=False):
    flags_down = KEYEVENTF_EXTENDEDKEY if extended else 0
    flags_up = flags_down | KEYEVENTF_KEYUP
    arr = (INPUT * 2)(
        INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags_down, time=0, dwExtraInfo=0)),
        INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags_up, time=0, dwExtraInfo=0)),
    )
    user32.SendInput(2, ctypes.byref(arr), INPUT_SIZE)


def send_key_combo(vk_mod, vk_key, key_extended=False):
    flags_down = KEYEVENTF_EXTENDEDKEY if key_extended else 0
    flags_up = flags_down | KEYEVENTF_KEYUP
    arr = (INPUT * 4)(
        INPUT(type=1, ki=KEYBDINPUT(wVk=vk_mod, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)),
        INPUT(type=1, ki=KEYBDINPUT(wVk=vk_key, wScan=0, dwFlags=flags_down, time=0, dwExtraInfo=0)),
        INPUT(type=1, ki=KEYBDINPUT(wVk=vk_key, wScan=0, dwFlags=flags_up, time=0, dwExtraInfo=0)),
        INPUT(type=1, ki=KEYBDINPUT(wVk=vk_mod, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)),
    )
    user32.SendInput(4, ctypes.byref(arr), INPUT_SIZE)


def send_mouse_input(flags, dx=0, dy=0, data=0):
    inp = INPUT(type=0, mi=MOUSEINPUT(dx=dx, dy=dy, mouseData=data, dwFlags=flags, time=0, dwExtraInfo=0))
    user32.SendInput(1, ctypes.byref(inp), INPUT_SIZE)


BUTTON_MASKS = {
    "A": 0x1000,
    "B": 0x2000,
    "X": 0x4000,
    "Y": 0x8000,
    "LB": 0x0100,
    "RB": 0x0200,
    "L3": 0x0040,
    "R3": 0x0080,
    "START": 0x0010,
    "D_UP": 0x0001,
    "D_DOWN": 0x0002,
    "D_LEFT": 0x0004,
    "D_RIGHT": 0x0008,
}


def get_pressed_buttons(btn_mask, lt_val, rt_val):
    pressed = {bid for bid, mask in BUTTON_MASKS.items() if btn_mask & mask}
    if lt_val > 90:
        pressed.add("LT")
    if rt_val > 110:
        pressed.add("RT")
    return pressed


def execute_mapped_action(action_id, is_down, was_down, auto_kb, scroll_step=90):
    if action_id == "left_click":
        if is_down and not was_down:
            send_mouse_input(MOUSEEVENTF_LEFTDOWN)
        elif not is_down and was_down:
            send_mouse_input(MOUSEEVENTF_LEFTUP)
            if auto_kb and is_cursor_ibeam():
                root.after(80, show_keyboard)
    elif action_id == "right_click":
        if is_down and not was_down:
            send_mouse_input(MOUSEEVENTF_RIGHTDOWN)
        elif not is_down and was_down:
            send_mouse_input(MOUSEEVENTF_RIGHTUP)
    elif action_id == "middle_click":
        if is_down and not was_down:
            send_mouse_input(MOUSEEVENTF_MIDDLEDOWN)
        elif not is_down and was_down:
            send_mouse_input(MOUSEEVENTF_MIDDLEUP)
    elif action_id == "scroll_up" and is_down:
        send_mouse_input(MOUSEEVENTF_WHEEL, data=scroll_step)
    elif action_id == "scroll_down" and is_down:
        send_mouse_input(MOUSEEVENTF_WHEEL, data=-scroll_step)
    elif action_id == "scroll_left" and is_down:
        send_mouse_input(MOUSEEVENTF_HWHEEL, data=-scroll_step)
    elif action_id == "scroll_right" and is_down:
        send_mouse_input(MOUSEEVENTF_HWHEEL, data=scroll_step)
    elif is_down and not was_down:
        if action_id == "double_click":
            for _ in range(2):
                send_mouse_input(MOUSEEVENTF_LEFTDOWN)
                send_mouse_input(MOUSEEVENTF_LEFTUP)
        elif action_id == "show_keyboard":
            root.after(0, lambda: hide_keyboard() if keyboard_visible else show_keyboard())
        elif action_id == "browser_back":
            send_key_combo(VK_MENU, VK_LEFT, key_extended=True)
        elif action_id == "browser_forward":
            send_key_combo(VK_MENU, VK_RIGHT, key_extended=True)
        elif action_id == "play_pause":
            send_vk_key(VK_MEDIA_PLAY_PAUSE)
        elif action_id == "vol_up":
            send_vk_key(VK_VOLUME_UP)
        elif action_id == "vol_down":
            send_vk_key(VK_VOLUME_DOWN)
        elif action_id == "vol_mute":
            send_vk_key(VK_VOLUME_MUTE)
        elif action_id == "copy":
            send_key_combo(VK_CONTROL, VK_C)
        elif action_id == "paste":
            send_key_combo(VK_CONTROL, VK_V)
        elif action_id == "close_tab":
            send_key_combo(VK_CONTROL, VK_W)
        elif action_id == "zoom_in":
            send_key_combo(VK_CONTROL, VK_OEM_PLUS)
        elif action_id == "zoom_out":
            send_key_combo(VK_CONTROL, VK_OEM_MINUS)
        elif action_id == "enter":
            send_vk_key(VK_RETURN)
        elif action_id == "escape":
            send_vk_key(VK_ESCAPE)
        elif action_id == "win_tab":
            send_key_combo(VK_LWIN, VK_TAB)
        elif action_id == "alt_tab":
            send_key_combo(VK_MENU, VK_TAB)


live_pressed_buttons = set()
live_stick_axes = (0, 0, 0, 0)


# Application state
config = load_config()
config_lock = threading.Lock()
running_flag = True

mouse_mode = False
keyboard_visible = False
shift_active = False
saved_cursor_x = 600
saved_cursor_y = 400

controller_connected = False
active_slot = 0
active_backend = "none"
active_joy_name = ""

KEYBOARD_LAYOUT_LOWER = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "Borrar"],
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "Mayus"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l", "ñ", "Enter"],
    ["z", "x", "c", "v", "b", "n", "m", ".", ",", "-", "?"],
    ["Espacio", ".com"],
]

KEYBOARD_LAYOUT_UPPER = [
    ["!", "@", "#", "$", "%", "&", "/", "(", ")", "=", "Borrar"],
    ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "Mayus"],
    ["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ñ", "Enter"],
    ["Z", "X", "C", "V", "B", "N", "M", ":", ";", "_", "¿"],
    ["Espacio", ".com"],
]

cur_row = 1
cur_col = 0
saved_col = 0
last_highlighted = (cur_row, cur_col)


def current_palette():
    return THEMES.get(config["theme"], THEMES["dark"])


def apply_overlay_window_style(win):
    try:
        win.update_idletasks()
        hwnd = int(win.wm_frame(), 16) if win.wm_frame() != "0x0" else win.winfo_id()
        style = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000008 | 0x00000080)
        apply_dwm_window_theme(win, config["theme"], corner_round=True)
    except Exception:
        pass


# Main Tk root is the Settings window (withdrawn when minimized to tray);
# floating keyboard and toasts are independent Toplevel overlays.
root = tk.Tk()
root.withdraw()
load_bundled_fonts()


def _log_tk_exception(_self, exc, val, tb):
    import traceback

    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(os.path.join(CONFIG_DIR, "error.log"), "a", encoding="utf-8") as f:
            traceback.print_exception(exc, val, tb, file=f)
    except Exception:
        pass


root.report_callback_exception = _log_tk_exception

scr_w = root.winfo_screenwidth()
scr_h = root.winfo_screenheight()

kb_win = tk.Toplevel(root)
kb_win.overrideredirect(True)
kb_win.attributes("-topmost", True)

kb_outer = tk.Frame(kb_win, padx=14, pady=12)
kb_outer.pack(fill="both", expand=True, padx=1, pady=1)

kb_header = tk.Frame(kb_outer)
kb_header.pack(fill="x", pady=(0, 8))

kb_hints_frame = tk.Frame(kb_header)
kb_hints_frame.pack(side="left")

KB_HINTS = [
    ("D-Pad", "Mover"),
    ("A", "Escribir"),
    ("X", "Borrar"),
    ("Y", "Espacio"),
    ("B", "Cerrar"),
    ("R3", "Posicion"),
]
kb_hint_badges = []
kb_hint_labels = []
for btn_txt, act_txt in KB_HINTS:
    item = tk.Frame(kb_hints_frame)
    item.pack(side="left", padx=(0, 8))
    b_lbl = tk.Label(item, text=btn_txt, font=font_tuple(8, "bold"), padx=6, pady=2)
    b_lbl.pack(side="left")
    a_lbl = tk.Label(item, text=act_txt, font=font_tuple(8), padx=4)
    a_lbl.pack(side="left")
    kb_hint_badges.append((item, b_lbl, a_lbl))

kb_status_frame = tk.Frame(kb_header)
kb_status_frame.pack(side="right")

pos_badge = tk.Label(kb_status_frame, text="ABAJO", font=font_tuple(8, "bold"), padx=8, pady=3)
pos_badge.pack(side="right", padx=(6, 0))

shift_badge = tk.Label(kb_status_frame, text="MAYUS", font=font_tuple(8, "bold"), padx=8, pady=3)
shift_badge.pack(side="right")

COL_W = 58
ACT_W = 118
KEY_H = 44
GAP = 6
PAD = 4
GRID_W = PAD * 2 + 10 * COL_W + ACT_W + 10 * GAP
GRID_H = PAD * 2 + 5 * KEY_H + 4 * GAP + 4

kb_canvas = tk.Canvas(kb_outer, width=GRID_W, height=GRID_H, highlightthickness=0, bd=0)
kb_canvas.pack()

key_items = []
for r_idx, row in enumerate(KEYBOARD_LAYOUT_LOWER):
    row_items = []
    y1 = PAD + r_idx * (KEY_H + GAP) + (4 if r_idx == 4 else 0)
    y2 = y1 + KEY_H
    if r_idx == 4:
        sx1, sx2 = PAD, PAD + 9 * COL_W + 8 * GAP
        bg = kb_canvas.create_rectangle(sx1, y1, sx2, y2, width=1)
        tx = kb_canvas.create_text((sx1 + sx2) / 2, (y1 + y2) / 2, text=row[0], font=font_tuple(10, "bold"))
        row_items.append({"bg": bg, "text": tx})

        cx1, cx2 = sx2 + GAP, GRID_W - PAD
        bg = kb_canvas.create_rectangle(cx1, y1, cx2, y2, width=1)
        tx = kb_canvas.create_text((cx1 + cx2) / 2, (y1 + y2) / 2, text=row[1], font=font_tuple(10, "bold"))
        row_items.append({"bg": bg, "text": tx})
    else:
        for c_idx, key_text in enumerate(row):
            x1 = PAD + c_idx * (COL_W + GAP)
            w = ACT_W if c_idx == 10 else COL_W
            x2 = x1 + w
            bg = kb_canvas.create_rectangle(x1, y1, x2, y2, width=1)
            fsize = 9 if c_idx == 10 else 11
            tx = kb_canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=key_text, font=font_tuple(fsize, "bold"))
            row_items.append({"bg": bg, "text": tx})
    key_items.append(row_items)

def _get_work_area():
    rect = wintypes.RECT()
    if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, scr_w, scr_h


kb_w = 1
kb_h = 1
kb_x = 0
kb_anim_id = None


def _refresh_kb_metrics():
    global kb_w, kb_h, kb_x
    kb_win.update_idletasks()
    # Use requested size because unmapped Toplevels report placeholder width/height (e.g. 200x200)
    kb_w = max(kb_win.winfo_reqwidth(), 1)
    kb_h = max(kb_win.winfo_reqheight(), 1)
    wa_l, _wa_t, wa_r, _wa_b = _get_work_area()
    kb_x = max(wa_l + 8, min(wa_r - kb_w - 8, wa_l + (wa_r - wa_l - kb_w) // 2))


def _target_kb_y():
    _wa_l, wa_t, _wa_r, wa_b = _get_work_area()
    if config["keyboard_at_top"]:
        return wa_t + 24
    return max(wa_t + 12, wa_b - kb_h - 18)


_refresh_kb_metrics()


def _ease_out_cubic(t):
    return 1.0 - (1.0 - t) ** 3


def _animate_window_y(win, start_y, end_y, x, w, h, duration_ms, on_done=None, id_setter=None):
    steps = max(1, duration_ms // 16)
    state_anim = {"step": 0}

    def tick():
        if not win.winfo_exists():
            return
        state_anim["step"] += 1
        t = min(1.0, state_anim["step"] / steps)
        cur_y = int(start_y + (end_y - start_y) * _ease_out_cubic(t))
        win.geometry(f"{w}x{h}+{x}+{cur_y}")
        if t < 1.0:
            aid = win.after(16, tick)
            if id_setter:
                id_setter(aid)
        else:
            if id_setter:
                id_setter(None)
            if on_done:
                on_done()

    aid = win.after(1, tick)
    if id_setter:
        id_setter(aid)


def _set_kb_anim_id(aid):
    global kb_anim_id
    kb_anim_id = aid


def _cancel_kb_anim():
    global kb_anim_id
    if kb_anim_id is not None:
        try:
            root.after_cancel(kb_anim_id)
        except Exception:
            pass
        kb_anim_id = None


def update_key_cell(r_idx, c_idx, active=False, flash=False):
    p = current_palette()
    layout = KEYBOARD_LAYOUT_UPPER if shift_active else KEYBOARD_LAYOUT_LOWER
    item = key_items[r_idx][c_idx]
    text = layout[r_idx][c_idx]
    is_shift_on = ("Mayus" in text) and shift_active
    inverted = active or is_shift_on

    if flash:
        fill = p["bg"]
        fg = p["fg"]
        width = 3
    elif inverted:
        fill = p["fg"]
        fg = p["bg"]
        width = 2
    else:
        fill = p["bg"]
        fg = p["fg"]
        width = 1

    kb_canvas.itemconfig(item["bg"], fill=fill, outline=p["fg"], width=width)
    kb_canvas.itemconfig(item["text"], fill=fg)


def apply_keyboard_theme():
    p = current_palette()
    kb_win.configure(bg=p["fg"])
    kb_outer.configure(bg=p["bg"])
    kb_header.configure(bg=p["bg"])
    kb_hints_frame.configure(bg=p["bg"])
    kb_status_frame.configure(bg=p["bg"])
    kb_canvas.configure(bg=p["bg"])

    for item, b_lbl, a_lbl in kb_hint_badges:
        item.configure(bg=p["bg"])
        b_lbl.configure(bg=p["fg"], fg=p["bg"])
        a_lbl.configure(bg=p["bg"], fg=p["fg"])

    pos_badge.configure(
        text="ARRIBA" if config["keyboard_at_top"] else "ABAJO",
        bg=p["bg"],
        fg=p["fg"],
        highlightbackground=p["fg"],
        highlightthickness=1,
    )
    if shift_active:
        shift_badge.configure(bg=p["fg"], fg=p["bg"], highlightthickness=1, highlightbackground=p["fg"])
    else:
        shift_badge.configure(bg=p["bg"], fg=p["fg"], highlightthickness=1, highlightbackground=p["fg"])

    layout = KEYBOARD_LAYOUT_UPPER if shift_active else KEYBOARD_LAYOUT_LOWER
    for r_idx, row in enumerate(key_items):
        for c_idx, item in enumerate(row):
            kb_canvas.itemconfig(item["text"], text=layout[r_idx][c_idx])
            update_key_cell(r_idx, c_idx, active=(r_idx == cur_row and c_idx == cur_col))


kb_win.geometry(f"{kb_w}x{kb_h}+{kb_x}+{_target_kb_y()}")
apply_keyboard_theme()
apply_overlay_window_style(kb_win)
kb_win.withdraw()


# Toast notifications (strict 2-color)
toast_win = None
toast_anim_id = None
toast_hide_id = None
toast_prog_id = None


def _set_toast_anim_id(aid):
    global toast_anim_id
    toast_anim_id = aid


def _destroy_toast():
    global toast_win, toast_anim_id, toast_hide_id, toast_prog_id
    for aid in (toast_anim_id, toast_hide_id, toast_prog_id):
        if aid is not None:
            try:
                root.after_cancel(aid)
            except Exception:
                pass
    toast_anim_id = None
    toast_hide_id = None
    toast_prog_id = None
    if toast_win is not None:
        try:
            if toast_win.winfo_exists():
                toast_win.destroy()
        except Exception:
            pass
        toast_win = None


def show_toast(title, subtitle=""):
    global toast_win, toast_hide_id, toast_prog_id
    if not config["show_toasts"]:
        return
    _destroy_toast()
    p = current_palette()
    try:
        t = tk.Toplevel(root)
        toast_win = t
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        t.configure(bg=p["fg"])

        outer = tk.Frame(t, bg=p["bg"])
        outer.pack(padx=1, pady=1)

        top_row = tk.Frame(outer, bg=p["bg"], padx=16, pady=10)
        top_row.pack(fill="both")

        marker = tk.Canvas(top_row, width=10, height=10, bg=p["bg"], highlightthickness=0)
        marker.create_rectangle(1, 1, 9, 9, fill=p["fg"], outline="")
        marker.pack(side="left", padx=(0, 12), anchor="n", pady=5)

        text_col = tk.Frame(top_row, bg=p["bg"])
        text_col.pack(side="left", fill="both")

        tk.Label(text_col, text=title, font=font_tuple(10, "bold"), fg=p["fg"], bg=p["bg"], anchor="w").pack(anchor="w")
        if subtitle:
            tk.Label(text_col, text=subtitle, font=font_tuple(8), fg=p["fg"], bg=p["bg"], anchor="w").pack(anchor="w", pady=(2, 0))

        prog_canvas = tk.Canvas(outer, height=3, bg=p["bg"], highlightthickness=0)
        prog_canvas.pack(fill="x")

        t.update_idletasks()
        apply_overlay_window_style(t)
        w = max(t.winfo_reqwidth(), t.winfo_width())
        h = max(t.winfo_reqheight(), t.winfo_height())
        prog_bar = prog_canvas.create_rectangle(0, 0, w, 3, fill=p["fg"], outline="")

        wa_l, wa_t, wa_r, _wa_b = _get_work_area()
        tx = max(wa_l + 8, min(wa_r - w - 8, wa_l + (wa_r - wa_l - w) // 2))
        start_y = -h - 8
        target_y = wa_t + 24
        t.geometry(f"{w}x{h}+{tx}+{start_y}")

        duration_ms = 1850
        start_time = time.monotonic()

        def update_prog():
            global toast_prog_id
            if toast_win is not t or not t.winfo_exists():
                return
            elapsed = (time.monotonic() - start_time) * 1000.0
            frac = max(0.0, 1.0 - elapsed / duration_ms)
            prog_canvas.coords(prog_bar, 0, 0, int(w * frac), 3)
            if frac > 0.0:
                toast_prog_id = t.after(20, update_prog)

        def start_hide():
            if toast_win is t and t.winfo_exists():
                _animate_window_y(t, target_y, start_y, tx, w, h, 140, on_done=_destroy_toast, id_setter=_set_toast_anim_id)

        _animate_window_y(t, start_y, target_y, tx, w, h, 140, id_setter=_set_toast_anim_id)
        toast_prog_id = t.after(16, update_prog)
        toast_hide_id = root.after(duration_ms, start_hide)
    except Exception:
        pass


def show_keyboard():
    global keyboard_visible, saved_cursor_x, saved_cursor_y
    if keyboard_visible:
        return
    keyboard_visible = True
    _cancel_kb_anim()

    pt = wintypes.POINT()
    if user32.GetCursorPos(ctypes.byref(pt)):
        if pt.x < scr_w - 5 or pt.y < scr_h - 5:
            saved_cursor_x, saved_cursor_y = pt.x, pt.y
    user32.SetCursorPos(scr_w + 500, scr_h + 500)

    apply_keyboard_theme()
    _refresh_kb_metrics()
    target_y = _target_kb_y()
    start_y = -kb_h - 10 if config["keyboard_at_top"] else scr_h + 10

    kb_win.geometry(f"{kb_w}x{kb_h}+{kb_x}+{start_y}")
    kb_win.deiconify()
    apply_overlay_window_style(kb_win)
    kb_win.attributes("-topmost", True)
    kb_win.lift()
    _animate_window_y(kb_win, start_y, target_y, kb_x, kb_w, kb_h, 140, id_setter=_set_kb_anim_id)


def hide_keyboard():
    global keyboard_visible
    if not keyboard_visible:
        return
    keyboard_visible = False
    _cancel_kb_anim()
    user32.SetCursorPos(saved_cursor_x, saved_cursor_y)

    start_y = _target_kb_y()
    end_y = -kb_h - 10 if config["keyboard_at_top"] else scr_h + 10
    _animate_window_y(
        kb_win,
        start_y,
        end_y,
        kb_x,
        kb_w,
        kb_h,
        120,
        on_done=lambda: kb_win.withdraw() if not keyboard_visible else None,
        id_setter=_set_kb_anim_id,
    )


def toggle_keyboard_position():
    old_y = _target_kb_y()
    with config_lock:
        config["keyboard_at_top"] = not config["keyboard_at_top"]
        save_config(config)
    new_y = _target_kb_y()
    apply_keyboard_theme()
    if keyboard_visible:
        _cancel_kb_anim()
        _animate_window_y(kb_win, old_y, new_y, kb_x, kb_w, kb_h, 160, id_setter=_set_kb_anim_id)
    if settings_app is not None:
        settings_app.sync_controls_from_config()


def press_current_key():
    global shift_active
    layout = KEYBOARD_LAYOUT_UPPER if shift_active else KEYBOARD_LAYOUT_LOWER
    val = layout[cur_row][cur_col]

    r_snap, c_snap = cur_row, cur_col
    update_key_cell(r_snap, c_snap, active=True, flash=True)
    root.after(95, lambda: update_key_cell(r_snap, c_snap, active=(r_snap == cur_row and c_snap == cur_col), flash=False))

    if val == "Borrar":
        send_vk_key(VK_BACK)
    elif val == "Enter":
        send_vk_key(VK_RETURN)
        root.after(95, hide_keyboard)
    elif val == "Espacio":
        send_vk_key(VK_SPACE)
    elif val == "Mayus":
        shift_active = not shift_active
        apply_keyboard_theme()
    elif val == ".com":
        send_unicode_text(".com")
    else:
        send_unicode_char(val)


def move_selection(d_row, d_col):
    global cur_row, cur_col, saved_col, last_highlighted
    layout = KEYBOARD_LAYOUT_UPPER if shift_active else KEYBOARD_LAYOUT_LOWER
    prev_r, prev_c = last_highlighted

    if d_row != 0:
        cur_row = (cur_row + d_row) % len(layout)
        max_cols = len(layout[cur_row])
        cur_col = (1 if saved_col >= 9 else 0) if cur_row == 4 else min(saved_col, max_cols - 1)
    elif d_col != 0:
        max_cols = len(layout[cur_row])
        if max_cols > 1:
            cur_col = (cur_col + d_col) % max_cols
            saved_col = (9 if cur_col == 1 else 4) if cur_row == 4 else cur_col

    if (prev_r, prev_c) != (cur_row, cur_col):
        update_key_cell(prev_r, prev_c, active=False)
        update_key_cell(cur_row, cur_col, active=True)
        last_highlighted = (cur_row, cur_col)


def set_mouse_mode(enabled, notify=True):
    global mouse_mode
    if keyboard_visible:
        hide_keyboard()
    mouse_mode = bool(enabled)
    if notify:
        if mouse_mode:
            show_toast("Modo Mouse ACTIVO", "Stick: Mover | LT: Precision | RT: Atras | X: Teclado")
        else:
            show_toast("Modo Juego ACTIVO", "Doble clic en '-' o Home para Modo Mouse")
    if settings_app is not None:
        settings_app.refresh_live_status()


def toggle_mouse_mode():
    set_mouse_mode(not mouse_mode, notify=True)


def handle_minus_press(count):
    if count >= 2:
        toggle_mouse_mode()
    elif count == 1 and mouse_mode:
        if keyboard_visible:
            hide_keyboard()
        else:
            show_keyboard()


# macOS System Settings style GUI
class SettingsWindow:
    NAV_ITEMS = [
        ("general", "General"),
        ("gamepad", "Mando y Botones"),
        ("mouse", "Mouse y Sticks"),
        ("keyboard", "Teclado"),
        ("appearance", "Apariencia"),
        ("system", "Sistema"),
    ]

    def __init__(self):
        self.win = root
        self.win.title(f"{APP_NAME} - Configuracion")
        self.win.geometry("860x600")
        self.win.minsize(760, 500)
        self.current_page = "general"
        self.selected_btn = "A"
        self._modal_open = None
        self._diagram_poll_id = None

        ico_path = get_resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(ico_path):
            try:
                self.win.iconbitmap(ico_path)
            except Exception:
                pass

        self._center_on_screen(840, 560)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self.win.bind("<Escape>", self._on_escape)

        self._themed_containers = []
        self._themed_labels = []
        self._themed_separators = []
        self._themed_bordered_boxes = []
        self._themed_controls = []
        self._nav_buttons = {}

        self._build_layout()
        self.show_page("general")
        self.apply_theme()
        self.win.update_idletasks()
        w = min(scr_w - 40, max(860, self.win.winfo_reqwidth() + 12))
        h = min(scr_h - 60, max(600, self.win.winfo_reqheight() + 12))
        self._center_on_screen(w, h)

    def _center_on_screen(self, w, h):
        x = max(20, (scr_w - w) // 2)
        y = max(20, (scr_h - h) // 2)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _build_layout(self):
        self.shell = tk.Frame(self.win)
        self.shell.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(self.shell, width=230, padx=16, pady=18)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.app_title_lbl = tk.Label(self.sidebar, text=APP_NAME, font=font_tuple(14, "bold"), anchor="w")
        self.app_title_lbl.pack(fill="x")

        self.ctrl_status_row = tk.Frame(self.sidebar)
        self.ctrl_status_row.pack(fill="x", pady=(6, 18))

        self.ctrl_dot = tk.Canvas(self.ctrl_status_row, width=10, height=10, highlightthickness=0)
        self.ctrl_dot.pack(side="left", padx=(0, 8))
        self.ctrl_status_lbl = tk.Label(self.ctrl_status_row, text="Verificando mando...", font=font_tuple(8), anchor="w")
        self.ctrl_status_lbl.pack(side="left", fill="x")

        self.nav_list = tk.Frame(self.sidebar)
        self.nav_list.pack(fill="x", expand=False)

        for key, title in self.NAV_ITEMS:
            btn = tk.Label(
                self.nav_list,
                text=title,
                font=font_tuple(10),
                anchor="w",
                padx=12,
                pady=8,
                cursor="hand2",
                takefocus=1,
            )
            btn.pack(fill="x", pady=2)
            btn.bind("<Button-1>", lambda _e, k=key: self.show_page(k))
            btn.bind("<Return>", lambda _e, k=key: self.show_page(k))
            btn.bind("<space>", lambda _e, k=key: self.show_page(k))
            btn.bind("<Up>", lambda _e, k=key: self._step_nav(k, -1))
            btn.bind("<Down>", lambda _e, k=key: self._step_nav(k, 1))
            btn.bind("<FocusIn>", lambda _e, b=btn: b.configure(highlightthickness=1))
            btn.bind("<FocusOut>", lambda _e, b=btn: b.configure(highlightthickness=0))
            self._nav_buttons[key] = btn

        self.sidebar_spacer = tk.Frame(self.sidebar)
        self.sidebar_spacer.pack(fill="both", expand=True)

        self.mode_card = tk.Frame(self.sidebar, padx=10, pady=10, highlightthickness=1)
        self.mode_card.pack(fill="x", pady=(0, 8))
        self.mode_caption_lbl = tk.Label(self.mode_card, text="Modo activo", font=font_tuple(8), anchor="w")
        self.mode_caption_lbl.pack(fill="x")
        self.mode_value_lbl = tk.Label(self.mode_card, text="Modo Juego", font=font_tuple(10, "bold"), anchor="w")
        self.mode_value_lbl.pack(fill="x", pady=(2, 8))
        self.btn_quick_mode = MonoButton(self.mode_card, "Cambiar modo", command=toggle_mouse_mode, pady=4, font_size=8)
        self.btn_quick_mode.pack(fill="x")

        self.btn_quick_theme = MonoButton(
            self.sidebar,
            "Invertir tema",
            command=self._toggle_theme,
            pady=5,
            font_size=8,
        )
        self.btn_quick_theme.pack(fill="x")

        self.v_sep = tk.Frame(self.shell, width=1)
        self.v_sep.pack(side="left", fill="y")

        self.content_area = tk.Frame(self.shell, padx=28, pady=22)
        self.content_area.pack(side="left", fill="both", expand=True)

        self.page_title_lbl = tk.Label(self.content_area, text="", font=font_tuple(17, "bold"), anchor="w")
        self.page_title_lbl.pack(fill="x")
        self.page_sub_lbl = tk.Label(self.content_area, text="", font=font_tuple(9), anchor="w")
        self.page_sub_lbl.pack(fill="x", pady=(4, 16))

        self.page_body = tk.Frame(self.content_area)
        self.page_body.pack(fill="both", expand=True)

    def _step_nav(self, cur_key, delta):
        keys = [k for k, _ in self.NAV_ITEMS]
        nxt = keys[(keys.index(cur_key) + delta) % len(keys)]
        self.show_page(nxt)
        self._nav_buttons[nxt].focus_set()

    def _clear_page(self):
        for w in self.page_body.winfo_children():
            w.destroy()
        self._themed_containers.clear()
        self._themed_labels.clear()
        self._themed_separators.clear()
        self._themed_bordered_boxes.clear()
        self._themed_controls.clear()

    def _make_group(self, title=None):
        if title:
            lbl = tk.Label(self.page_body, text=title, font=font_tuple(9, "bold"), anchor="w")
            lbl.pack(fill="x", pady=(10, 5))
            self._themed_labels.append(lbl)
        box = tk.Frame(self.page_body, highlightthickness=1)
        box.pack(fill="x", pady=(0, 8))
        self._themed_bordered_boxes.append(box)
        self._themed_containers.append(box)
        return box

    def _add_row(self, parent_box, title, subtitle, control_factory, is_first=False):
        if not is_first:
            sep = tk.Frame(parent_box, height=1)
            sep.pack(fill="x")
            self._themed_separators.append(sep)
        row = tk.Frame(parent_box, padx=14, pady=10)
        row.pack(fill="x")
        self._themed_containers.append(row)

        left = tk.Frame(row)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        self._themed_containers.append(left)

        t_lbl = tk.Label(left, text=title, font=font_tuple(10, "bold"), anchor="w")
        t_lbl.pack(fill="x")
        self._themed_labels.append(t_lbl)

        if subtitle:
            s_lbl = tk.Label(left, text=subtitle, font=font_tuple(8), anchor="w", wraplength=340, justify="left")
            s_lbl.pack(fill="x", pady=(2, 0))
            self._themed_labels.append(s_lbl)
        else:
            s_lbl = None
        self._last_row_labels = (t_lbl, s_lbl)

        right = tk.Frame(row)
        right.pack(side="right")
        self._themed_containers.append(right)

        ctrl = control_factory(right)
        ctrl.pack(side="right")
        self._themed_controls.append(ctrl)
        return ctrl

    def show_page(self, key):
        self.current_page = key
        self._clear_page()

        if key == "general":
            self.page_title_lbl.configure(text="General")
            self.page_sub_lbl.configure(text="Estado del mando, modo de entrada y arranque en Windows.")

            g1 = self._make_group("Dispositivo")
            self.gen_status_btn = self._add_row(
                g1,
                self._controller_title_text(),
                self._controller_sub_text(),
                lambda p: MonoButton(p, "Detectar ahora", command=self._manual_rescan),
                is_first=True,
            )
            self._gen_status_title_lbl, self._gen_status_sub_lbl = self._last_row_labels
            self.gen_mode_seg = self._add_row(
                g1,
                "Modo de entrada",
                "Cambia entre modo normal de juego o control de cursor en escritorio.",
                lambda p: SegmentedControl(
                    p,
                    [("game", "Juego"), ("mouse", "Mouse")],
                    "mouse" if mouse_mode else "game",
                    on_change=lambda k: set_mouse_mode(k == "mouse", notify=True),
                ),
            )
            self.gen_kb_btn = self._add_row(
                g1,
                "Teclado en pantalla",
                "Abre o cierra el teclado flotante navegable con D-Pad o stick.",
                lambda p: MonoButton(p, "Mostrar teclado" if not keyboard_visible else "Ocultar teclado", command=self._toggle_kb_from_ui),
            )

            g2 = self._make_group("Comportamiento")
            self.gen_startup_sw = self._add_row(
                g2,
                "Iniciar con Windows",
                "Ejecuta Rover silenciosamente en la bandeja al iniciar sesion.",
                lambda p: ToggleSwitch(p, value=is_startup_enabled(), on_change=self._on_startup_toggle),
                is_first=True,
            )
            self.gen_tray_sw = self._add_row(
                g2,
                "Mantener en bandeja al cerrar",
                "Oculta la ventana de ajustes sin detener la deteccion del control.",
                lambda p: ToggleSwitch(p, value=config["minimize_to_tray"], on_change=lambda v: self._set_cfg("minimize_to_tray", v)),
            )

        elif key == "gamepad":
            self.page_title_lbl.configure(text="Mando y Botones")
            self.page_sub_lbl.configure(text="Haz clic en un boton del esquema o presionalo en tu mando para asignarle accion.")

            diag_box = tk.Frame(self.page_body, padx=10, pady=8, highlightthickness=1)
            diag_box.pack(fill="x", pady=(0, 8))
            self._themed_bordered_boxes.append(diag_box)
            self._themed_containers.append(diag_box)

            self.gamepad_diagram = GamepadDiagram(diag_box, selected_btn=self.selected_btn, on_select=self._on_diagram_select)
            self.gamepad_diagram.pack(anchor="center")
            self.gamepad_diagram.bind("<Return>", lambda _e: self._open_action_picker())
            self.gamepad_diagram.bind("<space>", lambda _e: self._open_action_picker())
            self._themed_controls.append(self.gamepad_diagram)

            g_assign = self._make_group("Asignacion del boton")
            cur_act = config["button_map"].get(self.selected_btn, "none")
            self.gp_assign_btn = self._add_row(
                g_assign,
                BUTTON_LABELS.get(self.selected_btn, self.selected_btn),
                f"Accion actual: {ACTION_LABELS.get(cur_act, 'Sin asignar')}",
                lambda p: MonoButton(p, "Cambiar accion", command=self._open_action_picker, primary=True),
                is_first=True,
            )
            self._gp_assign_title_lbl = self._themed_labels[-2]
            self._gp_assign_sub_lbl = self._themed_labels[-1]

            self._add_row(
                g_assign,
                "Restaurar botones de fabrica",
                "Vuelve A/B/X/LT/RT/L3 a los controles predeterminados de Modo Mouse.",
                lambda p: MonoButton(p, "Restaurar botones", command=self._reset_button_map),
            )
            self._start_diagram_poll()

        elif key == "mouse":
            self.page_title_lbl.configure(text="Mouse y Sticks")
            self.page_sub_lbl.configure(text="Ajusta sensibilidad, zona muerta y desplazamiento en tiempo real.")

            g1 = self._make_group("Movimiento del cursor")
            self.st_speed = self._add_row(
                g1,
                "Velocidad base",
                "Rapidez maxima del puntero con el stick izquierdo (8 a 40).",
                lambda p: StepperControl(p, config["base_speed"], 8.0, 40.0, 2.0, "{:.0f}", lambda v: self._set_cfg("base_speed", float(v))),
                is_first=True,
            )
            self.st_deadzone = self._add_row(
                g1,
                "Zona muerta (Deadzone)",
                "Sube este valor si el stick se mueve solo por desgaste (1500 a 12000).",
                lambda p: StepperControl(p, config["deadzone"], 1500, 12000, 500, "{:.0f}", lambda v: self._set_cfg("deadzone", int(v))),
            )
            self.st_prec = self._add_row(
                g1,
                "Precision con gatillo LT",
                "Multiplicador de velocidad al mantener presionado LT (0.15 a 0.70).",
                lambda p: StepperControl(p, config["precision_factor"], 0.15, 0.70, 0.05, "{:.2f}", lambda v: self._set_cfg("precision_factor", float(v))),
            )
            self.st_accel = self._add_row(
                g1,
                "Curva de aceleracion",
                "Control fino cerca del centro vs avance rapido al borde (1.0 a 2.5).",
                lambda p: StepperControl(p, config["accel_exp"], 1.0, 2.5, 0.1, "{:.1f}", lambda v: self._set_cfg("accel_exp", float(v))),
            )
            self.st_scroll = self._add_row(
                g1,
                "Velocidad de scroll",
                "Intensidad de desplazamiento con D-Pad o stick derecho (30 a 180).",
                lambda p: StepperControl(p, config["scroll_step"], 30, 180, 15, "{:.0f}", lambda v: self._set_cfg("scroll_step", int(v))),
            )

            g2 = self._make_group("Valores de fabrica")
            self._add_row(
                g2,
                "Restaurar sensibilidad",
                "Vuelve velocidad, deadzone y aceleracion a sus valores iniciales.",
                lambda p: MonoButton(p, "Restaurar", command=self._reset_sensitivity),
                is_first=True,
            )

        elif key == "keyboard":
            self.page_title_lbl.configure(text="Teclado")
            self.page_sub_lbl.configure(text="Opciones del teclado flotante y referencia rapida del control.")

            g1 = self._make_group("Preferencias")
            self.kb_pos_seg = self._add_row(
                g1,
                "Posicion en pantalla",
                "Ubicacion donde aparece el teclado flotante.",
                lambda p: SegmentedControl(
                    p,
                    [("bottom", "Abajo"), ("top", "Arriba")],
                    "top" if config["keyboard_at_top"] else "bottom",
                    on_change=self._on_kb_pos_change,
                ),
                is_first=True,
            )
            self.kb_auto_sw = self._add_row(
                g1,
                "Abrir en campos de texto",
                "Muestra el teclado al hacer clic izquierdo con A sobre una caja de texto.",
                lambda p: ToggleSwitch(p, value=config["auto_keyboard_ibeam"], on_change=lambda v: self._set_cfg("auto_keyboard_ibeam", v)),
            )
            self.kb_toast_sw = self._add_row(
                g1,
                "Notificaciones en pantalla",
                "Muestra avisos breves al conectar el mando o cambiar de modo.",
                lambda p: ToggleSwitch(p, value=config["show_toasts"], on_change=lambda v: self._set_cfg("show_toasts", v)),
            )

            g2 = self._make_group("Controles en Modo Mouse")
            bmap = config["button_map"]
            bindings = [
                ("Doble clic '-' o Home", "Activar o salir de Modo Mouse"),
                ("1 clic '-' o Home", "Abrir o cerrar teclado flotante"),
                ("Stick izq / Stick der", "Mover cursor / Scroll vertical y horizontal"),
                (
                    f"A: {ACTION_LABELS.get(bmap.get('A', 'none'), '-')}",
                    f"B: {ACTION_LABELS.get(bmap.get('B', 'none'), '-')}",
                ),
            ]
            for idx, (btn_combo, desc) in enumerate(bindings):
                self._add_row(
                    g2,
                    btn_combo,
                    "",
                    lambda p, d=desc: tk.Label(p, text=d, font=font_tuple(8)),
                    is_first=(idx == 0),
                )
            self._add_row(
                g2,
                "Personalizar botones del mando",
                "Abre el diagrama interactivo para reasignar cualquier boton.",
                lambda p: MonoButton(p, "Ir a Mando y Botones", command=lambda: self.show_page("gamepad")),
            )

        elif key == "appearance":
            self.page_title_lbl.configure(text="Apariencia")
            self.page_sub_lbl.configure(text="Interfaz de 2 colores invertibles con tipografia de terminal.")

            g1 = self._make_group("Tema")
            self.app_theme_seg = self._add_row(
                g1,
                "Paleta activa",
                "Invierte los 2 colores en ajustes, teclado flotante, avisos y bandeja.",
                lambda p: SegmentedControl(
                    p,
                    [("dark", "Gris mate oscuro"), ("light", "Blanco invertido")],
                    config["theme"],
                    on_change=self._set_theme,
                ),
                is_first=True,
            )
            self._add_row(
                g1,
                "Invertir ahora",
                f"Fuente activa: {FONT_FAMILY} | Contraste verificado: 15.29:1",
                lambda p: MonoButton(p, "Invertir colores", command=self._toggle_theme, primary=True),
            )

        elif key == "system":
            self.page_title_lbl.configure(text="Sistema")
            self.page_sub_lbl.configure(text="Informacion de ejecucion, configuracion guardada y control de proceso.")

            g1 = self._make_group("Entorno")
            engine_desc = f"Motor: {xinput_dll_name} + winmm HID" if winmm_joy_get_pos_ex is not None else f"Motor: {xinput_dll_name}"
            self._add_row(
                g1,
                f"{APP_NAME} v{APP_VERSION}",
                engine_desc,
                lambda p: MonoButton(p, "Abrir carpeta config", command=self._open_config_dir),
                is_first=True,
            )
            self._add_row(
                g1,
                "Ruta activa",
                get_app_executable(),
                lambda p: tk.Label(p, text="Portable" if getattr(sys, "frozen", False) else "Script Python", font=font_tuple(8, "bold")),
            )

            g2 = self._make_group("Acciones")
            self._add_row(
                g2,
                "Restaurar configuracion completa",
                "Reinicia tema, sensibilidad y opciones a valores de fabrica.",
                lambda p: MonoButton(p, "Restaurar todo", command=self._confirm_reset_all),
                is_first=True,
            )
            self._add_row(
                g2,
                "Cerrar aplicacion",
                "Detiene el asistente por completo (incluyendo la bandeja del sistema).",
                lambda p: MonoButton(p, "Salir ahora", command=quit_application, primary=True),
            )

        self.apply_theme()
        self.win.update_idletasks()
        cur_w = max(840, self.win.winfo_width(), self.win.winfo_reqwidth() + 12)
        need_h = min(scr_h - 60, max(580, self.win.winfo_reqheight() + 12))
        if need_h > self.win.winfo_height():
            self.win.geometry(f"{min(scr_w - 40, cur_w)}x{need_h}")

    def _controller_title_text(self):
        if xinput_get_state is None and winmm_joy_get_pos_ex is None:
            return "Sin soporte de mando en este equipo"
        if controller_connected:
            b_lbl = "XInput" if active_backend == "xinput" else "HID"
            extra = f" - {active_joy_name}" if active_joy_name else ""
            return f"Mando conectado ({b_lbl} #{active_slot + 1}{extra})"
        return "Esperando mando"

    def _controller_sub_text(self):
        if xinput_get_state is None and winmm_joy_get_pos_ex is None:
            return "No se encontro soporte XInput ni winmm HID."
        if controller_connected:
            if active_backend == "winmm":
                return "Deteccion automatica activa via HID / DirectInput (winmm)."
            return "Deteccion automatica activa via XInput (cambio automatico entre mandos)."
        return "Conecta tu control por cable, dongle 2.4G o Bluetooth (XInput / HID)."

    def _manual_rescan(self):
        found = poll_active_controller(force_hid=True)
        self.refresh_live_status()
        if found:
            b_lbl = "XInput" if active_backend == "xinput" else "HID"
            show_toast(f"Mando detectado ({b_lbl} #{active_slot + 1})", active_joy_name or "Listo para usar")
        else:
            show_toast("Sin mando conectado", "Verifica cable, dongle o bateria")

    def _toggle_kb_from_ui(self):
        if keyboard_visible:
            hide_keyboard()
        else:
            show_keyboard()
        if self.current_page == "general" and hasattr(self, "gen_kb_btn"):
            self.gen_kb_btn.set_text("Ocultar teclado" if keyboard_visible else "Mostrar teclado")

    def _on_startup_toggle(self, enabled):
        ok = set_startup_enabled(enabled)
        if not ok and hasattr(self, "gen_startup_sw"):
            self.gen_startup_sw.set(is_startup_enabled(), notify=False)
            show_toast("No se pudo cambiar el inicio", "Revisa permisos de tu carpeta Inicio")

    def _on_kb_pos_change(self, pos_key):
        want_top = pos_key == "top"
        if config["keyboard_at_top"] != want_top:
            toggle_keyboard_position()

    def _set_cfg(self, key, val):
        with config_lock:
            config[key] = val
            save_config(config)

    def _on_diagram_select(self, btn_id):
        self.selected_btn = btn_id
        if hasattr(self, "_gp_assign_title_lbl") and self._gp_assign_title_lbl.winfo_exists():
            cur_act = config["button_map"].get(btn_id, "none")
            self._gp_assign_title_lbl.configure(text=BUTTON_LABELS.get(btn_id, btn_id))
            self._gp_assign_sub_lbl.configure(text=f"Accion actual: {ACTION_LABELS.get(cur_act, 'Sin asignar')}")

    def _open_action_picker(self):
        if self._modal_open and self._modal_open.winfo_exists():
            self._modal_open.lift()
            return
        cur_act = config["button_map"].get(self.selected_btn, "none")

        def on_pick(act_id):
            with config_lock:
                config["button_map"][self.selected_btn] = act_id
                save_config(config)
            self._on_diagram_select(self.selected_btn)
            show_toast(f"Boton {self.selected_btn} actualizado", ACTION_LABELS.get(act_id, ""))

        self._modal_open = ActionPickerModal(self.win, self.selected_btn, cur_act, config["theme"], on_pick)

    def _reset_button_map(self):
        with config_lock:
            config["button_map"] = dict(DEFAULT_BUTTON_MAP)
            save_config(config)
        self._on_diagram_select(self.selected_btn)
        show_toast("Botones restaurados", "Asignacion predeterminada aplicada")

    def _start_diagram_poll(self):
        if self._diagram_poll_id is not None:
            try:
                self.win.after_cancel(self._diagram_poll_id)
            except Exception:
                pass
            self._diagram_poll_id = None

        def tick():
            if not self.win.winfo_exists() or self.current_page != "gamepad":
                self._diagram_poll_id = None
                return
            if hasattr(self, "gamepad_diagram") and self.gamepad_diagram.winfo_exists():
                self.gamepad_diagram.set_live_state(live_pressed_buttons, live_stick_axes)
            self._diagram_poll_id = self.win.after(70, tick)

        self._diagram_poll_id = self.win.after(70, tick)

    def _reset_sensitivity(self):
        with config_lock:
            for k in ("deadzone", "base_speed", "precision_factor", "accel_exp", "scroll_step"):
                config[k] = DEFAULT_CONFIG[k]
            save_config(config)
        if self.current_page == "mouse":
            self.show_page("mouse")
        show_toast("Sensibilidad restaurada", "Valores de fabrica aplicados")

    def _confirm_reset_all(self):
        if self._modal_open and self._modal_open.winfo_exists():
            self._modal_open.lift()
            return
        p = current_palette()
        dlg = tk.Toplevel(self.win)
        self._modal_open = dlg
        dlg.title("Confirmar")
        dlg.transient(self.win)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(bg=p["bg"])
        apply_dwm_window_theme(dlg, config["theme"])

        frame = tk.Frame(dlg, bg=p["bg"], padx=22, pady=18, highlightthickness=1, highlightbackground=p["fg"])
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(frame, text="Restaurar configuracion?", font=font_tuple(12, "bold"), bg=p["bg"], fg=p["fg"], anchor="w").pack(fill="x")
        tk.Label(
            frame,
            text="Se reiniciaran tema, sensibilidad y opciones de teclado a sus valores iniciales.",
            font=font_tuple(9),
            bg=p["bg"],
            fg=p["fg"],
            wraplength=320,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(6, 16))

        btn_row = tk.Frame(frame, bg=p["bg"])
        btn_row.pack(fill="x")

        def do_reset():
            with config_lock:
                fresh = default_config_copy()
                config.clear()
                config.update(fresh)
                save_config(config)
            dlg.destroy()
            self.show_page(self.current_page)
            apply_keyboard_theme()
            refresh_tray_icon()
            show_toast("Configuracion restaurada", "Tema y ajustes reiniciados")

        b_cancel = MonoButton(btn_row, "Cancelar", command=dlg.destroy)
        b_cancel.apply_theme(p)
        b_cancel.pack(side="right")

        b_ok = MonoButton(btn_row, "Restaurar", command=do_reset, primary=True)
        b_ok.apply_theme(p)
        b_ok.pack(side="right", padx=(0, 8))

        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        dlg.update_idletasks()
        dx = self.win.winfo_x() + (self.win.winfo_width() - dlg.winfo_width()) // 2
        dy = self.win.winfo_y() + (self.win.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{dx}+{dy}")
        b_cancel.focus_set()

    def _open_config_dir(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        os.startfile(CONFIG_DIR)

    def _toggle_theme(self):
        nxt = "light" if config["theme"] == "dark" else "dark"
        self._set_theme(nxt)

    def _set_theme(self, theme_name):
        if theme_name not in THEMES:
            return
        with config_lock:
            config["theme"] = theme_name
            save_config(config)
        self.apply_theme()
        apply_keyboard_theme()
        refresh_tray_icon()
        if self.current_page == "appearance" and hasattr(self, "app_theme_seg"):
            self.app_theme_seg.select(theme_name, notify=False)

    def sync_controls_from_config(self):
        if not self.win.winfo_exists():
            return
        if self.current_page == "keyboard" and hasattr(self, "kb_pos_seg"):
            self.kb_pos_seg.select("top" if config["keyboard_at_top"] else "bottom", notify=False)
        self.refresh_live_status()

    def refresh_live_status(self):
        if not self.win.winfo_exists():
            return
        p = current_palette()
        self.ctrl_dot.delete("all")
        if controller_connected:
            b_lbl = "XInput" if active_backend == "xinput" else "HID"
            self.ctrl_dot.create_rectangle(1, 1, 9, 9, fill=p["fg"], outline=p["fg"])
            self.ctrl_status_lbl.configure(text=f"Conectado | {b_lbl} #{active_slot + 1}")
        else:
            self.ctrl_dot.create_rectangle(1, 1, 9, 9, fill=p["bg"], outline=p["fg"], width=1)
            self.ctrl_status_lbl.configure(text="Esperando mando")

        self.mode_value_lbl.configure(text="Modo Mouse" if mouse_mode else "Modo Juego")
        if self.current_page == "general":
            if hasattr(self, "gen_mode_seg"):
                self.gen_mode_seg.select("mouse" if mouse_mode else "game", notify=False)
            if hasattr(self, "gen_kb_btn"):
                self.gen_kb_btn.set_text("Ocultar teclado" if keyboard_visible else "Mostrar teclado")
            if hasattr(self, "_gen_status_title_lbl") and self._gen_status_title_lbl.winfo_exists():
                self._gen_status_title_lbl.configure(text=self._controller_title_text())
            if hasattr(self, "_gen_status_sub_lbl") and self._gen_status_sub_lbl is not None and self._gen_status_sub_lbl.winfo_exists():
                self._gen_status_sub_lbl.configure(text=self._controller_sub_text())

    def apply_theme(self):
        p = current_palette()
        apply_dwm_window_theme(self.win, config["theme"], corner_round=True)
        self.win.configure(bg=p["bg"])
        for f in (
            self.shell,
            self.sidebar,
            self.ctrl_status_row,
            self.nav_list,
            self.sidebar_spacer,
            self.content_area,
            self.page_body,
        ):
            f.configure(bg=p["bg"])

        self.v_sep.configure(bg=p["fg"])
        self.mode_card.configure(bg=p["bg"], highlightbackground=p["fg"], highlightcolor=p["fg"])
        self.ctrl_dot.configure(bg=p["bg"])
        for lbl in (
            self.app_title_lbl,
            self.ctrl_status_lbl,
            self.mode_caption_lbl,
            self.mode_value_lbl,
            self.page_title_lbl,
            self.page_sub_lbl,
        ):
            lbl.configure(bg=p["bg"], fg=p["fg"])

        for key, btn in self._nav_buttons.items():
            active = key == self.current_page
            btn.configure(
                bg=p["fg"] if active else p["bg"],
                fg=p["bg"] if active else p["fg"],
                font=font_tuple(10, "bold" if active else "normal"),
                highlightbackground=p["fg"],
                highlightcolor=p["fg"],
            )

        self.btn_quick_mode.apply_theme(p)
        self.btn_quick_theme.apply_theme(p)

        for c in self._themed_containers:
            c.configure(bg=p["bg"])
        for b in self._themed_bordered_boxes:
            b.configure(bg=p["bg"], highlightbackground=p["fg"], highlightcolor=p["fg"])
        for s in self._themed_separators:
            s.configure(bg=p["fg"])
        for lbl in self._themed_labels:
            lbl.configure(bg=p["bg"], fg=p["fg"])
        for ctrl in self._themed_controls:
            if hasattr(ctrl, "apply_theme"):
                ctrl.apply_theme(p)
            else:
                ctrl.configure(bg=p["bg"], fg=p["fg"])

        self.refresh_live_status()

    def _on_escape(self, _evt=None):
        if self._modal_open and self._modal_open.winfo_exists():
            self._modal_open.destroy()
            return
        if config["minimize_to_tray"]:
            self.hide()

    def _on_close_request(self):
        if config["minimize_to_tray"]:
            self.hide()
        else:
            quit_application()

    def show(self):
        if not self.win.winfo_exists():
            return
        self.apply_theme()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def hide(self):
        if self.win.winfo_exists():
            self.win.withdraw()


settings_app = None
tray_icon = None


def open_settings_window():
    global settings_app
    if settings_app is None or not settings_app.win.winfo_exists():
        settings_app = SettingsWindow()
    settings_app.show()


def refresh_tray_icon():
    if tray_icon is not None:
        try:
            tray_icon.icon = build_tray_pil_image(config["theme"], size=64)
        except Exception:
            pass


def quit_application():
    global running_flag
    running_flag = False
    if keyboard_visible:
        try:
            user32.SetCursorPos(saved_cursor_x, saved_cursor_y)
        except Exception:
            pass
    if tray_icon is not None:
        try:
            tray_icon.stop()
        except Exception:
            pass
    try:
        root.quit()
        root.destroy()
    except Exception:
        pass
    os._exit(0)


def start_tray_icon():
    global tray_icon

    def on_open(_icon, _item):
        root.after(0, open_settings_window)

    def on_mode(_icon, _item):
        root.after(0, toggle_mouse_mode)

    def on_kb(_icon, _item):
        root.after(0, lambda: hide_keyboard() if keyboard_visible else show_keyboard())

    def on_theme(_icon, _item):
        nxt = "light" if config["theme"] == "dark" else "dark"
        if settings_app is not None:
            root.after(0, lambda: settings_app._set_theme(nxt))
        else:
            with config_lock:
                config["theme"] = nxt
                save_config(config)
            root.after(0, apply_keyboard_theme)
            refresh_tray_icon()

    def on_quit(_icon, _item):
        root.after(0, quit_application)

    menu = pystray.Menu(
        pystray.MenuItem("Abrir configuracion", on_open, default=True),
        pystray.MenuItem("Alternar Modo Mouse", on_mode),
        pystray.MenuItem("Teclado en pantalla", on_kb),
        pystray.MenuItem("Invertir tema", on_theme),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Salir", on_quit),
    )
    tray_icon = pystray.Icon(APP_NAME, build_tray_pil_image(config["theme"], size=64), APP_NAME, menu)
    threading.Thread(target=tray_icon.run, daemon=True).start()


# Controller polling loop
state = XINPUT_STATE()
_scan_state = XINPUT_STATE()
prev_a = prev_b = prev_x = prev_y = False
prev_start = prev_trigger = prev_r3 = False
prev_mouse_btns = set()
press_count = 0
last_press_time = 0.0
timer_obj = None
timer_lock = threading.Lock()
last_nav_time = 0.0
nav_held = False
prev_nav_dir = (0, 0)
x_hold_start = x_last_repeat = 0.0
y_hold_start = y_last_repeat = 0.0
rem_x = rem_y = 0.0
disconnect_start = 0.0


def execute_minus_action():
    global press_count
    with timer_lock:
        c = press_count
        press_count = 0
    root.after(0, handle_minus_press, c)


def _copy_gamepad_state(dst, src):
    dst.dwPacketNumber = src.dwPacketNumber
    dst.Gamepad.wButtons = src.Gamepad.wButtons
    dst.Gamepad.bLeftTrigger = src.Gamepad.bLeftTrigger
    dst.Gamepad.bRightTrigger = src.Gamepad.bRightTrigger
    dst.Gamepad.sThumbLX = src.Gamepad.sThumbLX
    dst.Gamepad.sThumbLY = src.Gamepad.sThumbLY
    dst.Gamepad.sThumbRX = src.Gamepad.sThumbRX
    dst.Gamepad.sThumbRY = src.Gamepad.sThumbRY


def poll_active_controller(force_hid=False):
    global active_slot, active_backend, active_joy_name, _last_winmm_scan

    if xinput_get_state is not None:
        if active_backend == "xinput" and xinput_get_state(active_slot, ctypes.byref(state)) == 0:
            # Keep active slot while it has input; switch slots only if idle and another controller moves/presses.
            if _gp_has_input(state.Gamepad):
                return True
            for slot in range(4):
                if slot != active_slot and xinput_get_state(slot, ctypes.byref(_scan_state)) == 0:
                    if _gp_has_input(_scan_state.Gamepad):
                        active_slot = slot
                        active_joy_name = ""
                        _copy_gamepad_state(state, _scan_state)
                        return True
            return True

        first_xinput_slot = None
        for slot in range(4):
            if xinput_get_state(slot, ctypes.byref(_scan_state)) == 0:
                if _gp_has_input(_scan_state.Gamepad):
                    active_backend = "xinput"
                    active_slot = slot
                    active_joy_name = ""
                    _copy_gamepad_state(state, _scan_state)
                    return True
                if first_xinput_slot is None:
                    first_xinput_slot = slot
                    _copy_gamepad_state(state, _scan_state)
        if first_xinput_slot is not None:
            active_backend = "xinput"
            active_slot = first_xinput_slot
            active_joy_name = ""
            return True

    if winmm_joy_get_pos_ex is not None:
        if active_backend == "winmm" and winmm_joy_get_pos_ex(active_slot, ctypes.byref(_joy_info)) == 0:
            active_joy_name = _populate_state_from_joy(active_slot, _joy_info, state)
            return True

        if active_backend == "winmm":
            _joy_caps_cache.pop(active_slot, None)

        now = time.time()
        if force_hid or (now - _last_winmm_scan >= 0.4):
            _last_winmm_scan = now
            for joy_id in range(16):
                if winmm_joy_get_pos_ex(joy_id, ctypes.byref(_joy_info)) == 0:
                    active_backend = "winmm"
                    active_slot = joy_id
                    active_joy_name = _populate_state_from_joy(joy_id, _joy_info, state)
                    return True

    active_backend = "none"
    active_joy_name = ""
    return False


def controller_loop():
    global prev_a, prev_b, prev_x, prev_y, prev_start, prev_trigger, prev_r3, prev_mouse_btns
    global press_count, last_press_time, timer_obj, last_nav_time, nav_held, prev_nav_dir
    global x_hold_start, x_last_repeat, y_hold_start, y_last_repeat
    global rem_x, rem_y, controller_connected, disconnect_start, mouse_mode
    global live_pressed_buttons, live_stick_axes

    switch_to_interactive_desktop()
    last_cursor_hide = 0.0
    last_ui_slot = None
    last_ui_backend = None

    while running_flag:
        if poll_active_controller():
            disconnect_start = 0.0
            if not controller_connected:
                controller_connected = True
                mouse_mode = False
                last_ui_slot = active_slot
                last_ui_backend = active_backend
                if keyboard_visible:
                    root.after(0, hide_keyboard)
                b_lbl = "XInput" if active_backend == "xinput" else "HID"
                root.after(0, lambda s=active_slot, b=b_lbl: show_toast(f"Mando #{s + 1} conectado ({b} | Modo Juego)", "Doble clic en '-' o Home para Modo Mouse"))
                if settings_app is not None:
                    root.after(0, settings_app.refresh_live_status)
            elif active_slot != last_ui_slot or active_backend != last_ui_backend:
                last_ui_slot = active_slot
                last_ui_backend = active_backend
                if settings_app is not None:
                    root.after(0, settings_app.refresh_live_status)

            btn = state.Gamepad.wButtons
            lt_val = state.Gamepad.bLeftTrigger
            rt_val = state.Gamepad.bRightTrigger
            live_pressed_buttons = get_pressed_buttons(btn, lt_val, rt_val)
            live_stick_axes = (
                state.Gamepad.sThumbLX,
                state.Gamepad.sThumbLY,
                state.Gamepad.sThumbRX,
                state.Gamepad.sThumbRY,
            )
            now = time.time()

            curr_trigger = bool((btn & 0x0020) or (btn & 0x0400))
            if curr_trigger and not prev_trigger:
                with timer_lock:
                    if timer_obj:
                        timer_obj.cancel()
                        timer_obj = None
                    if now - last_press_time < 0.38:
                        press_count += 1
                    else:
                        press_count = 1
                    last_press_time = now
                    timer_obj = threading.Timer(0.38, execute_minus_action)
                    timer_obj.start()
            prev_trigger = curr_trigger

            if keyboard_visible:
                if now - last_cursor_hide > 0.25:
                    user32.SetCursorPos(scr_w + 500, scr_h + 500)
                    last_cursor_hide = now

                lx, ly = state.Gamepad.sThumbLX, state.Gamepad.sThumbLY
                d_row = d_col = 0
                if btn & 0x0001:
                    d_row = -1
                elif btn & 0x0002:
                    d_row = 1
                elif btn & 0x0004:
                    d_col = -1
                elif btn & 0x0008:
                    d_col = 1
                else:
                    abs_x, abs_y = abs(lx), abs(ly)
                    thresh = 13000 if nav_held else 19500
                    if max(abs_x, abs_y) > thresh:
                        if abs_y > abs_x * 1.35:
                            d_row = -1 if ly > 0 else 1
                        elif abs_x > abs_y * 1.35:
                            d_col = 1 if lx > 0 else -1

                cur_dir = (d_row, d_col)
                if cur_dir != (0, 0):
                    if cur_dir != prev_nav_dir:
                        nav_held = False
                    delay = 0.11 if nav_held else 0.24
                    if (not nav_held and now - last_nav_time >= 0.07) or (nav_held and now - last_nav_time >= delay):
                        root.after(0, move_selection, d_row, d_col)
                        last_nav_time = now
                        nav_held = True
                        prev_nav_dir = cur_dir
                elif max(abs(lx), abs(ly)) < 11000 and not (btn & 0x000F):
                    nav_held = False
                    prev_nav_dir = (0, 0)

                curr_a = bool((btn & 0x1000) or (btn & 0x0200))
                if curr_a and not prev_a:
                    root.after(0, press_current_key)
                prev_a = curr_a

                curr_b = bool((btn & 0x2000) or (btn & 0x0100))
                if curr_b and not prev_b:
                    root.after(0, hide_keyboard)
                prev_b = curr_b

                curr_x = bool(btn & 0x4000)
                if curr_x and not prev_x:
                    send_vk_key(VK_BACK)
                    x_hold_start = x_last_repeat = now
                elif curr_x and (now - x_hold_start > 0.32) and (now - x_last_repeat >= 0.075):
                    send_vk_key(VK_BACK)
                    x_last_repeat = now
                prev_x = curr_x

                curr_y = bool(btn & 0x8000)
                if curr_y and not prev_y:
                    send_vk_key(VK_SPACE)
                    y_hold_start = y_last_repeat = now
                elif curr_y and (now - y_hold_start > 0.32) and (now - y_last_repeat >= 0.09):
                    send_vk_key(VK_SPACE)
                    y_last_repeat = now
                prev_y = curr_y

                curr_r3 = bool(btn & 0x0080)
                if curr_r3 and not prev_r3:
                    root.after(0, toggle_keyboard_position)
                prev_r3 = curr_r3

                curr_start = bool(btn & 0x0010)
                if curr_start and not prev_start:
                    send_vk_key(VK_RETURN)
                    root.after(90, hide_keyboard)
                prev_start = curr_start

                time.sleep(0.01)

            elif mouse_mode:
                with config_lock:
                    dz = config["deadzone"]
                    b_spd = config["base_speed"]
                    p_fac = config["precision_factor"]
                    a_exp = config["accel_exp"]
                    s_step = config["scroll_step"]
                    auto_kb = config["auto_keyboard_ibeam"]
                    bmap = dict(config["button_map"])

                lx, ly = state.Gamepad.sThumbLX, state.Gamepad.sThumbLY
                precision_held = any((bid in live_pressed_buttons) and bmap.get(bid) == "precision" for bid in BUTTON_ORDER)
                speed = b_spd * p_fac if precision_held else b_spd

                dx = dy = 0.0
                if abs(lx) > dz:
                    sign_x = 1.0 if lx > 0 else -1.0
                    mag_x = (abs(lx) - dz) / max(1.0, 32767.0 - dz)
                    dx = sign_x * (mag_x ** a_exp) * speed
                if abs(ly) > dz:
                    sign_y = -1.0 if ly > 0 else 1.0
                    mag_y = (abs(ly) - dz) / max(1.0, 32767.0 - dz)
                    dy = sign_y * (mag_y ** a_exp) * speed

                if dx != 0.0 or dy != 0.0:
                    rem_x += dx
                    rem_y += dy
                    mx, my = int(rem_x), int(rem_y)
                    rem_x -= mx
                    rem_y -= my
                    if mx != 0 or my != 0:
                        send_mouse_input(MOUSEEVENTF_MOVE, dx=mx, dy=my)
                else:
                    rem_x = rem_y = 0.0

                for bid in BUTTON_ORDER:
                    act_id = bmap.get(bid, "none")
                    if act_id in ("none", "precision"):
                        continue
                    execute_mapped_action(act_id, bid in live_pressed_buttons, bid in prev_mouse_btns, auto_kb, s_step)
                prev_mouse_btns = set(live_pressed_buttons)

                rx, ry = state.Gamepad.sThumbRX, state.Gamepad.sThumbRY
                r_dz = max(6000, dz)
                if abs(ry) > r_dz:
                    delta_v = int((ry / 32767.0) * (s_step * 0.5))
                    if delta_v != 0:
                        send_mouse_input(MOUSEEVENTF_WHEEL, data=delta_v)
                if abs(rx) > r_dz:
                    delta_h = int((rx / 32767.0) * (s_step * 0.5))
                    if delta_h != 0:
                        send_mouse_input(MOUSEEVENTF_HWHEEL, data=delta_h)

                time.sleep(0.008)
            else:
                prev_mouse_btns = set()
                time.sleep(0.04)
        else:
            live_pressed_buttons = set()
            live_stick_axes = (0, 0, 0, 0)
            prev_mouse_btns = set()
            if controller_connected:
                if disconnect_start == 0.0:
                    disconnect_start = time.time()
                elif time.time() - disconnect_start > 2.5:
                    controller_connected = False
                    disconnect_start = 0.0
                    if settings_app is not None:
                        root.after(0, settings_app.refresh_live_status)
            time.sleep(0.08)


def poll_ipc_events():
    if not running_flag:
        return
    if _show_event and kernel32.WaitForSingleObject(_show_event, 0) == 0:
        open_settings_window()
    if _quit_event and kernel32.WaitForSingleObject(_quit_event, 0) == 0:
        quit_application()
        return
    root.after(150, poll_ipc_events)


def restore_cursor_on_exit():
    if keyboard_visible:
        try:
            user32.SetCursorPos(saved_cursor_x, saved_cursor_y)
        except Exception:
            pass


atexit.register(restore_cursor_on_exit)
start_tray_icon()
threading.Thread(target=controller_loop, daemon=True).start()
root.after(150, poll_ipc_events)

if "--minimized" in _args or "--tray" in _args:
    root.after(250, lambda: show_toast(f"{APP_NAME} activo en bandeja", "Doble clic en '-' o Home para Modo Mouse"))
else:
    open_settings_window()

root.mainloop()
