import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import threading
import time

# XInput & WinMM structures and constants
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
    "VIEW": 0x0020,
    "HOME": 0x0400,
    "D_UP": 0x0001,
    "D_DOWN": 0x0002,
    "D_LEFT": 0x0004,
    "D_RIGHT": 0x0008,
}

# Load XInput DLL and configure 64-bit prototype
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
    xinput_get_state.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
    xinput_get_state.restype = wintypes.DWORD
else:
    xinput_get_state = None

try:
    winmm = ctypes.windll.winmm
    winmm_joy_get_pos_ex = winmm.joyGetPosEx
    winmm_joy_get_pos_ex.argtypes = [wintypes.UINT, ctypes.POINTER(JOYINFOEX)]
    winmm_joy_get_pos_ex.restype = wintypes.UINT
    winmm_joy_get_dev_caps = winmm.joyGetDevCapsW
    winmm_joy_get_dev_caps.argtypes = [ctypes.c_size_t, ctypes.POINTER(JOYCAPSW), wintypes.UINT]
    winmm_joy_get_dev_caps.restype = wintypes.UINT
except Exception:
    winmm = None
    winmm_joy_get_pos_ex = None
    winmm_joy_get_dev_caps = None


def decode_pressed_buttons(btn_mask, lt_val, rt_val):
    pressed = {bid for bid, mask in BUTTON_MASKS.items() if btn_mask & mask}
    if lt_val > 90:
        pressed.add("LT")
    if rt_val > 110:
        pressed.add("RT")
    return frozenset(pressed)


def compute_axis_velocity(val, deadzone, accel_exp, speed, invert=False):
    """Pure 1D deadzone + exponential response curve calculation."""
    if abs(val) <= deadzone:
        return 0.0
    sign = -1.0 if (val > 0 if invert else val < 0) else 1.0
    mag = (abs(val) - deadzone) / max(1.0, 32767.0 - deadzone)
    return sign * (mag ** accel_exp) * speed


@dataclass(frozen=True)
class GamepadSnapshot:
    connected: bool = False
    slot: int = 0
    backend: str = "none"
    device_name: str = ""
    pressed: frozenset = frozenset()
    lx: int = 0
    ly: int = 0
    rx: int = 0
    ry: int = 0
    lt: int = 0
    rt: int = 0

    @property
    def stick_axes(self):
        return (self.lx, self.ly, self.rx, self.ry)


class InputEdgeTracker:
    """Single source of truth for button press/release edges and mode-switch button consumption.
    When consume_current() is called on a mode transition (e.g., B closing keyboard or X opening keyboard),
    all currently held buttons are latched in _consumed until physically released, preventing phantom Esc/Backspace leaks.
    """

    def __init__(self):
        self._prev_pressed = frozenset()
        self._consumed = set()

    def reset(self):
        self._prev_pressed = frozenset()
        self._consumed.clear()

    def consume_current(self, current_pressed=None, extra=()):
        target = self._prev_pressed if current_pressed is None else frozenset(current_pressed)
        self._consumed.update(target)
        self._consumed.update(extra)

    def update(self, current_pressed):
        cur = frozenset(current_pressed)
        raw_pressed = cur - self._prev_pressed
        raw_released = self._prev_pressed - cur

        # Suppress release edge for any button that was consumed while held, then clear released buttons from _consumed
        just_released = frozenset(raw_released - self._consumed)
        self._consumed.intersection_update(cur)

        just_pressed = frozenset(raw_pressed - self._consumed)
        active_holds = frozenset(cur - self._consumed)

        self._prev_pressed = cur
        return just_pressed, just_released, active_holds


class AutoRepeater:
    """Deterministic hold-to-repeat timer driven by the main polling loop clock."""

    def __init__(self, initial_delay=0.30, interval=0.08):
        self.initial_delay = initial_delay
        self.interval = interval
        self._active_token = None
        self._start_ts = 0.0
        self._last_ts = 0.0

    def reset(self):
        self._active_token = None

    def step(self, token, now):
        if not token:
            self._active_token = None
            return False
        if token != self._active_token:
            self._active_token = token
            self._start_ts = self._last_ts = now
            return True
        if (now - self._start_ts >= self.initial_delay) and (now - self._last_ts >= self.interval):
            self._last_ts = now
            return True
        return False


class MultiTapDetector:
    """Lock-free, thread-free multi-press detector for '-' (VIEW) and Home buttons."""

    def __init__(self, window_sec=0.34):
        self.window_sec = window_sec
        self._count = 0
        self._last_tap_ts = 0.0

    def reset(self):
        self._count = 0
        self._last_tap_ts = 0.0

    def step(self, tap_edge, now):
        """Return finished tap count (> 0) once the multi-tap window expires, or 0 while waiting."""
        if tap_edge:
            if self._count > 0 and (now - self._last_tap_ts < self.window_sec):
                self._count += 1
            else:
                self._count = 1
            self._last_tap_ts = now
            return 0

        if self._count > 0 and (now - self._last_tap_ts >= self.window_sec):
            c = self._count
            self._count = 0
            return c
        return 0


def _gp_has_input(gp, stick_thresh=11000):
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


def _copy_gamepad_state(dst, src):
    dst.dwPacketNumber = src.dwPacketNumber
    dst.Gamepad.wButtons = src.Gamepad.wButtons
    dst.Gamepad.bLeftTrigger = src.Gamepad.bLeftTrigger
    dst.Gamepad.bRightTrigger = src.Gamepad.bRightTrigger
    dst.Gamepad.sThumbLX = src.Gamepad.sThumbLX
    dst.Gamepad.sThumbLY = src.Gamepad.sThumbLY
    dst.Gamepad.sThumbRX = src.Gamepad.sThumbRX
    dst.Gamepad.sThumbRY = src.Gamepad.sThumbRY


class GamepadPoller:
    """Thread-confined XInput + WinMM HID poller that publishes immutable GamepadSnapshots."""

    def __init__(self):
        self._state = XINPUT_STATE()
        self._scan_state = XINPUT_STATE()
        self._joy_info = JOYINFOEX()
        self._joy_info.dwSize = ctypes.sizeof(JOYINFOEX)
        self._joy_info.dwFlags = JOY_RETURNALL
        self._joy_caps_cache = {}
        self._last_winmm_scan = 0.0

        self.active_slot = 0
        self.active_backend = "none"
        self.active_joy_name = ""

        self._rescan_event = threading.Event()
        self._latest_snapshot = GamepadSnapshot()

    @property
    def latest_snapshot(self):
        return self._latest_snapshot

    @staticmethod
    def has_backend_support():
        return (xinput_get_state is not None) or (winmm_joy_get_pos_ex is not None)

    @staticmethod
    def engine_description():
        if winmm_joy_get_pos_ex is not None:
            return f"Motor: {xinput_dll_name} + winmm HID"
        return f"Motor: {xinput_dll_name}"

    def request_rescan(self):
        """Thread-safe signal from UI thread asking the polling thread to force a full scan on its next tick."""
        self._rescan_event.set()

    def _get_joy_caps(self, joy_id):
        if joy_id in self._joy_caps_cache:
            return self._joy_caps_cache[joy_id]
        caps = JOYCAPSW()
        if (
            winmm_joy_get_dev_caps is not None
            and winmm_joy_get_dev_caps(joy_id, ctypes.byref(caps), ctypes.sizeof(caps)) == 0
        ):
            self._joy_caps_cache[joy_id] = caps
            return caps
        return None

    def _populate_from_joy(self, joy_id):
        caps = self._get_joy_caps(joy_id)
        xmin, xmax = (caps.wXmin, caps.wXmax) if caps else (0, 65535)
        ymin, ymax = (caps.wYmin, caps.wYmax) if caps else (0, 65535)
        zmin, zmax = (caps.wZmin, caps.wZmax) if caps else (0, 65535)
        rmin, rmax = (caps.wRmin, caps.wRmax) if caps else (0, 65535)
        umin, umax = (caps.wUmin, caps.wUmax) if caps else (0, 65535)
        vmin, vmax = (caps.wVmin, caps.wVmax) if caps else (0, 65535)
        wcaps = caps.wCaps if caps else (JOYCAPS_HASZ | JOYCAPS_HASR)

        gp = self._state.Gamepad
        info = self._joy_info
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

    def _poll_hardware(self, force_hid=False):
        if xinput_get_state is not None:
            if self.active_backend == "xinput" and xinput_get_state(self.active_slot, ctypes.byref(self._state)) == 0:
                if _gp_has_input(self._state.Gamepad):
                    return True
                for slot in range(4):
                    if slot != self.active_slot and xinput_get_state(slot, ctypes.byref(self._scan_state)) == 0:
                        if _gp_has_input(self._scan_state.Gamepad):
                            self.active_slot = slot
                            self.active_joy_name = ""
                            _copy_gamepad_state(self._state, self._scan_state)
                            return True
                return True

            first_slot = None
            for slot in range(4):
                if xinput_get_state(slot, ctypes.byref(self._scan_state)) == 0:
                    if _gp_has_input(self._scan_state.Gamepad):
                        self.active_backend = "xinput"
                        self.active_slot = slot
                        self.active_joy_name = ""
                        _copy_gamepad_state(self._state, self._scan_state)
                        return True
                    if first_slot is None:
                        first_slot = slot
                        _copy_gamepad_state(self._state, self._scan_state)
            if first_slot is not None:
                self.active_backend = "xinput"
                self.active_slot = first_slot
                self.active_joy_name = ""
                return True

        if winmm_joy_get_pos_ex is not None:
            if self.active_backend == "winmm" and winmm_joy_get_pos_ex(self.active_slot, ctypes.byref(self._joy_info)) == 0:
                self.active_joy_name = self._populate_from_joy(self.active_slot)
                return True

            if self.active_backend == "winmm":
                self._joy_caps_cache.pop(self.active_slot, None)

            now = time.monotonic()
            if force_hid or (now - self._last_winmm_scan >= 0.4):
                self._last_winmm_scan = now
                for joy_id in range(16):
                    if winmm_joy_get_pos_ex(joy_id, ctypes.byref(self._joy_info)) == 0:
                        self.active_backend = "winmm"
                        self.active_slot = joy_id
                        self.active_joy_name = self._populate_from_joy(joy_id)
                        return True

        self.active_backend = "none"
        self.active_joy_name = ""
        return False

    def poll(self):
        force = self._rescan_event.is_set()
        if force:
            self._rescan_event.clear()

        ok = self._poll_hardware(force_hid=force)
        if not ok:
            self._latest_snapshot = GamepadSnapshot(connected=False)
            return self._latest_snapshot, force

        gp = self._state.Gamepad
        pressed = decode_pressed_buttons(gp.wButtons, gp.bLeftTrigger, gp.bRightTrigger)
        self._latest_snapshot = GamepadSnapshot(
            connected=True,
            slot=self.active_slot,
            backend=self.active_backend,
            device_name=self.active_joy_name,
            pressed=pressed,
            lx=int(gp.sThumbLX),
            ly=int(gp.sThumbLY),
            rx=int(gp.sThumbRX),
            ry=int(gp.sThumbRY),
            lt=int(gp.bLeftTrigger),
            rt=int(gp.bRightTrigger),
        )
        return self._latest_snapshot, force
