import ctypes
from ctypes import wintypes
import os
from rover_system import log_error

user32 = ctypes.windll.user32

# Complete 64-bit Win32 structures for SendInput and Cursor inspection
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


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    _anonymous_ = ("_i",)
    _fields_ = [("type", wintypes.DWORD), ("_i", _I)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hCursor", wintypes.HANDLE),
        ("ptScreenPos", wintypes.POINT),
    ]


# Explicit 64-bit Win32 function prototypes
user32.OpenDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.OpenDesktopW.restype = wintypes.HANDLE
user32.CloseDesktop.argtypes = [wintypes.HANDLE]
user32.CloseDesktop.restype = wintypes.BOOL
user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
user32.SetThreadDesktop.restype = wintypes.BOOL
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadCursorW.restype = wintypes.HANDLE
user32.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
user32.GetCursorInfo.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
user32.VkKeyScanW.restype = ctypes.c_short
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT]
user32.SystemParametersInfoW.restype = wintypes.BOOL

try:
    _get_window_long_ptr = user32.GetWindowLongPtrW
    _set_window_long_ptr = user32.SetWindowLongPtrW
    _get_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_window_long_ptr.restype = ctypes.c_ssize_t
    _set_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _set_window_long_ptr.restype = ctypes.c_ssize_t
except AttributeError:
    _get_window_long_ptr = user32.GetWindowLongW
    _set_window_long_ptr = user32.SetWindowLongW
    _get_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_window_long_ptr.restype = ctypes.c_long
    _set_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    _set_window_long_ptr.restype = ctypes.c_long

H_IBEAM = user32.LoadCursorW(None, ctypes.cast(32513, wintypes.LPCWSTR))
INPUT_SIZE = ctypes.sizeof(INPUT)

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_C = 0x43
VK_F = 0x46
VK_S = 0x53
VK_V = 0x56
VK_W = 0x57
VK_LWIN = 0x5B
VK_F4 = 0x73
VK_VOLUME_MUTE = 0xAD

WM_SYSCOMMAND = 0x0112
SC_MONITORPOWER = 0xF170
HWND_BROADCAST = wintypes.HWND(0xFFFF)

try:
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
except Exception:
    pass

try:
    _powrprof = ctypes.windll.powrprof
    _powrprof.SetSuspendState.argtypes = [wintypes.BOOL, wintypes.BOOL, wintypes.BOOL]
    _powrprof.SetSuspendState.restype = wintypes.BOOL
except Exception:
    _powrprof = None
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

# Declarative action catalog shared between gamepad_ui.py and execution engine
ACTION_SPECS = [
    ("left_click", "Clic izquierdo (mantener)", "mouse_hold", (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)),
    ("right_click", "Clic derecho (mantener)", "mouse_hold", (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)),
    ("middle_click", "Clic central (rueda)", "mouse_hold", (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP)),
    ("double_click", "Doble clic izquierdo", "double_click", None),
    ("precision", "Modo precision (mantener)", "modifier", None),
    ("show_keyboard", "Abrir / cerrar teclado", "toggle_keyboard", None),
    ("radial_menu", "Menu Radial (Control de Sofa)", "radial_menu", None),
    ("escape", "Tecla Escape", "vk_tap", (VK_ESCAPE, False)),
    ("enter", "Tecla Enter", "vk_tap", (VK_RETURN, False)),
    ("media_ff", "Adelantar video (Flecha Der)", "vk_tap", (VK_RIGHT, True)),
    ("media_rw", "Retroceder video (Flecha Izq)", "vk_tap", (VK_LEFT, True)),
    ("fullscreen_f", "Pantalla completa (Tecla F)", "vk_tap", (VK_F, False)),
    ("space_play", "Pausa / Play (Espacio)", "vk_tap", (VK_SPACE, False)),
    ("monitor_off", "Apagar monitor", "system_cmd", "monitor_off"),
    ("scroll_up", "Scroll arriba (mantener)", "scroll_hold", (MOUSEEVENTF_WHEEL, 1)),
    ("scroll_down", "Scroll abajo (mantener)", "scroll_hold", (MOUSEEVENTF_WHEEL, -1)),
    ("scroll_left", "Scroll izquierda (mantener)", "scroll_hold", (MOUSEEVENTF_HWHEEL, -1)),
    ("scroll_right", "Scroll derecha (mantener)", "scroll_hold", (MOUSEEVENTF_HWHEEL, 1)),
    ("browser_back", "Atras (Alt + Izq)", "combo_tap", (VK_MENU, VK_LEFT, True)),
    ("browser_forward", "Adelante (Alt + Der)", "combo_tap", (VK_MENU, VK_RIGHT, True)),
    ("play_pause", "Play / Pausa multimedia", "vk_tap", (VK_MEDIA_PLAY_PAUSE, False)),
    ("vol_up", "Subir volumen", "vk_tap", (VK_VOLUME_UP, False)),
    ("vol_down", "Bajar volumen", "vk_tap", (VK_VOLUME_DOWN, False)),
    ("vol_mute", "Silenciar audio", "vk_tap", (VK_VOLUME_MUTE, False)),
    ("copy", "Copiar (Ctrl + C)", "combo_tap", (VK_CONTROL, VK_C, False)),
    ("paste", "Pegar (Ctrl + V)", "combo_tap", (VK_CONTROL, VK_V, False)),
    ("close_tab", "Cerrar pestana (Ctrl + W)", "combo_tap", (VK_CONTROL, VK_W, False)),
    ("zoom_in", "Zoom + (Ctrl + +)", "combo_tap", (VK_OEM_PLUS, VK_CONTROL, False)),
    ("zoom_out", "Zoom - (Ctrl + -)", "combo_tap", (VK_OEM_MINUS, VK_CONTROL, False)),
    ("win_tab", "Vista de tareas (Win + Tab)", "combo_tap", (VK_LWIN, VK_TAB, False)),
    ("alt_tab", "Cambiar ventana (Alt + Tab)", "combo_tap", (VK_MENU, VK_TAB, False)),
    ("none", "Sin asignar", "none", None),
]

# Fix zoom_in / zoom_out modifier order (VK_CONTROL is modifier, VK_OEM_PLUS/MINUS is key)
ACTION_SPECS = [
    (
        aid,
        lbl,
        kind,
        (VK_CONTROL, VK_OEM_PLUS, False)
        if aid == "zoom_in"
        else ((VK_CONTROL, VK_OEM_MINUS, False) if aid == "zoom_out" else payload),
    )
    for aid, lbl, kind, payload in ACTION_SPECS
]

ACTIONS = [(aid, lbl) for aid, lbl, _kind, _payload in ACTION_SPECS]
ACTION_LABELS = dict(ACTIONS)
ACTION_SPEC_MAP = {aid: (kind, payload) for aid, _lbl, kind, payload in ACTION_SPECS}


def switch_to_interactive_desktop():
    try:
        h = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if h:
            user32.SetThreadDesktop(h)
            user32.CloseDesktop(h)
    except Exception:
        pass


def get_work_area(fallback_w=1920, fallback_h=1080):
    rect = wintypes.RECT()
    if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, fallback_w, fallback_h


def get_window_hwnd(win):
    win.update_idletasks()
    frame = win.wm_frame()
    return int(frame, 16) if (frame and frame != "0x0") else win.winfo_id()


def is_cursor_ibeam():
    ci = CURSORINFO(cbSize=ctypes.sizeof(CURSORINFO))
    if user32.GetCursorInfo(ctypes.byref(ci)):
        return ci.hCursor == H_IBEAM
    return False


def get_cursor_pos():
    pt = wintypes.POINT()
    if user32.GetCursorPos(ctypes.byref(pt)):
        return pt.x, pt.y
    return None


def set_cursor_pos(x, y):
    user32.SetCursorPos(int(x), int(y))


class FocusGuard:
    """Preserves external target window activation (Netflix, browsers, games) when overlays appear."""

    def __init__(self):
        self._own_pid = os.getpid()
        self._target_hwnd = None

    def capture_foreground_target(self):
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value and pid.value != self._own_pid:
            self._target_hwnd = hwnd

    def apply_noactivate_style(self, win):
        """Set WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW without calling Tk attributes('-topmost') after."""
        try:
            hwnd = get_window_hwnd(win)
            ex_style = _get_window_long_ptr(hwnd, GWL_EXSTYLE)
            new_style = ex_style | WS_EX_NOACTIVATE | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
            _set_window_long_ptr(hwnd, GWL_EXSTYLE, new_style)
            return hwnd
        except Exception as exc:
            log_error("FocusGuard.apply_noactivate_style", exc)
            return None

    def show_noactivate_topmost(self, win, x, y, w, h):
        """Position and show an overlay window via Win32 SetWindowPos(SWP_NOACTIVATE) so focus never leaves Netflix."""
        try:
            self.capture_foreground_target()
            win.geometry(f"{w}x{h}+{x}+{y}")
            hwnd = self.apply_noactivate_style(win)
            win.deiconify()
            hwnd = self.apply_noactivate_style(win) or hwnd
            if hwnd:
                user32.SetWindowPos(
                    hwnd,
                    HWND_TOPMOST,
                    int(x),
                    int(y),
                    int(w),
                    int(h),
                    SWP_NOACTIVATE | SWP_SHOWWINDOW,
                )
        except Exception as exc:
            log_error("FocusGuard.show_noactivate_topmost", exc)

    def ensure_target_focus(self):
        """If Rover accidentally owns foreground focus, restore activation to the captured external window."""
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            pid = wintypes.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != self._own_pid:
                self._target_hwnd = hwnd
                return
        if self._target_hwnd and user32.IsWindow(self._target_hwnd):
            try:
                user32.SetForegroundWindow(self._target_hwnd)
            except Exception:
                pass


class InputSynthesizer:
    """Win32 SendInput wrapper with hybrid VK/ScanCode + Unicode injection and safe mouse button release."""

    _DOWN_TO_UP = {
        MOUSEEVENTF_LEFTDOWN: MOUSEEVENTF_LEFTUP,
        MOUSEEVENTF_RIGHTDOWN: MOUSEEVENTF_RIGHTUP,
        MOUSEEVENTF_MIDDLEDOWN: MOUSEEVENTF_MIDDLEUP,
    }

    def __init__(self, focus_guard=None):
        self.focus_guard = focus_guard or FocusGuard()
        self._held_mouse_downs = set()

    def _make_vk_input(self, vk, up=False, extended=False):
        scan = user32.MapVirtualKeyW(vk, 0) & 0xFFFF
        flags = KEYEVENTF_EXTENDEDKEY if extended else 0
        if up:
            flags |= KEYEVENTF_KEYUP
        return INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0))

    def send_vk_key(self, vk, extended=False):
        self.focus_guard.ensure_target_focus()
        arr = (INPUT * 2)(
            self._make_vk_input(vk, up=False, extended=extended),
            self._make_vk_input(vk, up=True, extended=extended),
        )
        user32.SendInput(2, arr, INPUT_SIZE)

    def send_key_combo(self, vk_mod, vk_key, key_extended=False):
        self.focus_guard.ensure_target_focus()
        arr = (INPUT * 4)(
            self._make_vk_input(vk_mod, up=False, extended=False),
            self._make_vk_input(vk_key, up=False, extended=key_extended),
            self._make_vk_input(vk_key, up=True, extended=key_extended),
            self._make_vk_input(vk_mod, up=True, extended=False),
        )
        user32.SendInput(4, arr, INPUT_SIZE)

    def send_unicode_char(self, char):
        self.focus_guard.ensure_target_focus()
        code = ord(char)
        arr = (INPUT * 2)(
            INPUT(type=1, ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)),
            INPUT(
                type=1,
                ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0),
            ),
        )
        user32.SendInput(2, arr, INPUT_SIZE)

    def send_char(self, char):
        """Send standard ASCII letters/digits as real VK+ScanCode events for Netflix/UWP/Game compatibility,
        and non-ASCII/accented/AltGr symbols via KEYEVENTF_UNICODE to avoid dead-key issues."""
        if not char:
            return
        self.focus_guard.ensure_target_focus()
        if len(char) == 1 and ord(char) < 128 and (char.isalnum() or char == " "):
            vk_res = user32.VkKeyScanW(char)
            if vk_res != -1:
                vk = vk_res & 0xFF
                shift_state = (vk_res >> 8) & 0xFF
                if shift_state == 0:
                    self.send_vk_key(vk)
                    return
                if shift_state == 1:
                    self.send_key_combo(VK_SHIFT, vk)
                    return
        self.send_unicode_char(char)

    def send_text(self, text):
        for ch in text:
            self.send_char(ch)

    def send_mouse_input(self, flags, dx=0, dy=0, data=0):
        if flags in self._DOWN_TO_UP:
            self._held_mouse_downs.add(flags)
        else:
            for down_flag, up_flag in self._DOWN_TO_UP.items():
                if flags == up_flag:
                    self._held_mouse_downs.discard(down_flag)
        inp = INPUT(
            type=0,
            mi=MOUSEINPUT(
                dx=int(dx),
                dy=int(dy),
                mouseData=ctypes.c_uint32(int(data)).value,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            ),
        )
        user32.SendInput(1, ctypes.byref(inp), INPUT_SIZE)

    def release_all_mouse_buttons(self):
        """Release any held OS mouse buttons when switching modes or disconnecting."""
        for down_flag in list(self._held_mouse_downs):
            up_flag = self._DOWN_TO_UP.get(down_flag)
            if up_flag:
                self.send_mouse_input(up_flag)
        self._held_mouse_downs.clear()

    def turn_off_monitor(self):
        try:
            user32.PostMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
        except Exception as exc:
            log_error("InputSynthesizer.turn_off_monitor", exc)

    def capture_screenshot(self):
        """Trigger Windows Snipping Tool (Win + Shift + S)."""
        try:
            self.focus_guard.ensure_target_focus()
            inputs = (INPUT * 6)(
                self._make_vk_input(VK_LWIN, up=False, extended=True),
                self._make_vk_input(VK_SHIFT, up=False),
                self._make_vk_input(VK_S, up=False),
                self._make_vk_input(VK_S, up=True),
                self._make_vk_input(VK_SHIFT, up=True),
                self._make_vk_input(VK_LWIN, up=True, extended=True),
            )
            user32.SendInput(6, inputs, INPUT_SIZE)
        except Exception as exc:
            log_error("InputSynthesizer.capture_screenshot", exc)

    def close_active_window(self):
        self.send_key_combo(VK_MENU, VK_F4)

    def suspend_pc(self):
        try:
            if _powrprof is not None:
                _powrprof.SetSuspendState(False, True, False)
        except Exception as exc:
            log_error("InputSynthesizer.suspend_pc", exc)

    def execute_action(
        self,
        action_id,
        just_pressed,
        just_released,
        is_held,
        scroll_step=90,
        on_toggle_keyboard=None,
        on_left_click_released=None,
        on_open_radial=None,
    ):
        spec = ACTION_SPEC_MAP.get(action_id)
        if not spec:
            return
        kind, payload = spec

        if kind == "mouse_hold":
            down_flag, up_flag = payload
            if just_pressed:
                self.send_mouse_input(down_flag)
            elif just_released:
                self.send_mouse_input(up_flag)
                if action_id == "left_click" and on_left_click_released:
                    on_left_click_released()
        elif kind == "scroll_hold":
            if is_held:
                wheel_flag, direction = payload
                self.send_mouse_input(wheel_flag, data=direction * int(scroll_step))
        elif just_pressed:
            if kind == "vk_tap":
                vk, ext = payload
                self.send_vk_key(vk, extended=ext)
            elif kind == "combo_tap":
                vk_mod, vk_key, ext = payload
                self.send_key_combo(vk_mod, vk_key, key_extended=ext)
            elif kind == "double_click":
                for _ in range(2):
                    self.send_mouse_input(MOUSEEVENTF_LEFTDOWN)
                    self.send_mouse_input(MOUSEEVENTF_LEFTUP)
            elif kind == "toggle_keyboard" and on_toggle_keyboard:
                on_toggle_keyboard()
            elif kind == "radial_menu" and on_open_radial:
                on_open_radial()
            elif kind == "system_cmd" and payload == "monitor_off":
                self.turn_off_monitor()
