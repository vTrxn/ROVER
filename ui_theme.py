import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import sys
import time
import tkinter as tk
from PIL import Image, ImageDraw
from rover_system import log_error

# Original 2-Color Matte Monochrome Design System (#1E1E1E / #F5F5F5 + JetBrainsMono NF)
THEMES = {
    "dark": {
        "name": "dark",
        "label": "Gris mate oscuro",
        "bg": "#1E1E1E",
        "surface": "#1E1E1E",
        "elevated": "#2A2A2A",
        "border_subtle": "#3A3A3A",
        "border_strong": "#F5F5F5",
        "fg": "#F5F5F5",
        "fg_secondary": "#CCCCCC",
        "fg_muted": "#8A8A8A",
        "accent": "#F5F5F5",
        "accent_fg": "#1E1E1E",
        "danger": "#F5F5F5",
        "danger_fg": "#1E1E1E",
        "inv_bg": "#F5F5F5",
        "inv_fg": "#1E1E1E",
        "caption_colorref": 0x001E1E1E,  # BGR for #1E1E1E
        "text_colorref": 0x00F5F5F5,     # BGR for #F5F5F5
        "border_colorref": 0x00F5F5F5,   # BGR for #F5F5F5
        "dark_caption": 1,
    },
    "light": {
        "name": "light",
        "label": "Blanco invertido",
        "bg": "#F5F5F5",
        "surface": "#F5F5F5",
        "elevated": "#E5E5E5",
        "border_subtle": "#CCCCCC",
        "border_strong": "#1E1E1E",
        "fg": "#1E1E1E",
        "fg_secondary": "#444444",
        "fg_muted": "#6E6E6E",
        "accent": "#1E1E1E",
        "accent_fg": "#F5F5F5",
        "danger": "#1E1E1E",
        "danger_fg": "#F5F5F5",
        "inv_bg": "#1E1E1E",
        "inv_fg": "#F5F5F5",
        "caption_colorref": 0x00F5F5F5,  # BGR for #F5F5F5
        "text_colorref": 0x001E1E1E,     # BGR for #1E1E1E
        "border_colorref": 0x001E1E1E,   # BGR for #1E1E1E
        "dark_caption": 0,
    },
}

FONT_UI = "JetBrainsMono NF"
FONT_FAMILY = "JetBrainsMono NF"
_FONT_LOADED = False
_GLOBAL_AUDIO_CB = None

# 64-bit safe gdi32 and dwmapi prototypes
try:
    gdi32 = ctypes.windll.gdi32
    gdi32.AddFontResourceExW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID]
    gdi32.AddFontResourceExW.restype = ctypes.c_int
except Exception:
    gdi32 = None

try:
    dwmapi = ctypes.windll.dwmapi
    dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.LPCVOID, wintypes.DWORD]
    dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
except Exception:
    dwmapi = None


def set_ui_audio_callback(cb):
    global _GLOBAL_AUDIO_CB
    _GLOBAL_AUDIO_CB = cb


def _trigger_ui_audio(kind="press"):
    if _GLOBAL_AUDIO_CB is not None:
        try:
            _GLOBAL_AUDIO_CB(kind)
        except Exception:
            pass


def get_resource_path(rel_path):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel_path)


def load_bundled_fonts():
    """Register bundled JetBrainsMono NF fonts privately for the current process and resolve UI/Mono families."""
    global _FONT_LOADED, FONT_FAMILY, FONT_UI
    if _FONT_LOADED:
        return FONT_FAMILY
    _FONT_LOADED = True
    try:
        if gdi32 is not None:
            FR_PRIVATE = 0x10
            fonts_dir = get_resource_path(os.path.join("assets", "fonts"))
            if os.path.isdir(fonts_dir):
                for fname in os.listdir(fonts_dir):
                    if fname.lower().endswith(".ttf"):
                        fpath = os.path.join(fonts_dir, fname)
                        gdi32.AddFontResourceExW(fpath, FR_PRIVATE, None)
    except Exception as exc:
        log_error("load_bundled_fonts.gdi32", exc)

    try:
        import tkinter.font as tkfont

        fams = set(tkfont.families())
        if "JetBrainsMono NF" in fams:
            FONT_FAMILY = "JetBrainsMono NF"
        elif "Consolas" in fams:
            FONT_FAMILY = "Consolas"
        else:
            FONT_FAMILY = "TkFixedFont"

        if "Segoe UI Variable Display" in fams:
            FONT_UI = "Segoe UI Variable Display"
        elif "Segoe UI" in fams:
            FONT_UI = "Segoe UI"
        else:
            FONT_UI = FONT_FAMILY
    except Exception:
        FONT_FAMILY = "Consolas"
        FONT_UI = "Segoe UI"
    return FONT_FAMILY


def ui_font(size=10, weight="normal"):
    """Human-readable proportional font for titles, navigation, and settings prose."""
    if weight == "bold":
        return (FONT_UI, size, "bold")
    return (FONT_UI, size)


def mono_font(size=10, weight="normal"):
    """Tabular fixed-width font for keycaps, controller button badges, and numeric steppers."""
    if weight == "bold":
        return (FONT_FAMILY, size, "bold")
    return (FONT_FAMILY, size)


def font_tuple(size=10, weight="normal"):
    return mono_font(size, weight)


def ease_out_cubic(t):
    return 1.0 - (1.0 - max(0.0, min(1.0, t))) ** 3


def center_window_on_screen(win, w, h):
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = max(20, (sw - w) // 2)
    y = max(20, (sh - h) // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")


def center_window_on_parent(win, parent_win):
    win.update_idletasks()
    px = parent_win.winfo_x() + max(0, (parent_win.winfo_width() - win.winfo_width()) // 2)
    py = parent_win.winfo_y() + max(0, (parent_win.winfo_height() - win.winfo_height()) // 2)
    win.geometry(f"+{px}+{py}")


def apply_dwm_window_theme(win, theme_name="dark", corner_round=True):
    """Match native Windows 11 titlebar and border to the active Nordic Cockpit palette."""
    t = THEMES.get(theme_name, THEMES["dark"])
    if dwmapi is None:
        return
    try:
        win.update_idletasks()
        frame = win.wm_frame()
        hwnd = int(frame, 16) if (frame and frame != "0x0") else win.winfo_id()
        attrs = [
            (20, ctypes.c_int(t["dark_caption"])),      # DWMWA_USE_IMMERSIVE_DARK_MODE
            (35, ctypes.c_int(t["caption_colorref"])),  # DWMWA_CAPTION_COLOR
            (36, ctypes.c_int(t["text_colorref"])),     # DWMWA_TEXT_COLOR
            (34, ctypes.c_int(t["border_colorref"])),   # DWMWA_BORDER_COLOR
        ]
        if corner_round:
            attrs.append((33, ctypes.c_int(2)))  # DWMWA_WINDOW_CORNER_PREFERENCE = Round
        for attr_id, c_val in attrs:
            dwmapi.DwmSetWindowAttribute(hwnd, attr_id, ctypes.byref(c_val), ctypes.sizeof(c_val))
    except Exception:
        pass


def build_tray_pil_image(theme_name="dark", size=64):
    """Create a tactile tray icon with Nordic Cockpit surface and Volvo Amber status accent."""
    t = THEMES.get(theme_name, THEMES["dark"])
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = max(4, int(size * 0.22))
    d.rounded_rectangle(
        [1, 1, size - 2, size - 2],
        radius=r,
        fill=t["surface"],
        outline=t["accent"],
        width=max(2, size // 16),
    )
    cy = size // 2
    arm = max(3, int(size * 0.14))
    thick = max(2, int(size * 0.08))
    cx_left = int(size * 0.34)
    d.rectangle([cx_left - arm, cy - thick // 2, cx_left + arm, cy + thick // 2], fill=t["fg"])
    d.rectangle([cx_left - thick // 2, cy - arm, cx_left + thick // 2, cy + arm], fill=t["fg"])
    br = max(2, int(size * 0.075))
    bx = int(size * 0.65)
    d.ellipse([bx - br, cy - int(size * 0.10) - br, bx + br, cy - int(size * 0.10) + br], fill=t["accent"])
    d.ellipse(
        [
            bx - br + int(size * 0.10),
            cy + int(size * 0.06) - br,
            bx + br + int(size * 0.10),
            cy + int(size * 0.06) + br,
        ],
        fill=t["fg"],
    )
    return img


class MonoButton(tk.Frame):
    """Flat matte button with explicit primary/danger/disabled states, visible focus ring, and keyboard support."""

    def __init__(
        self,
        parent,
        text,
        command=None,
        primary=False,
        danger=False,
        mono=False,
        width=None,
        padx=14,
        pady=6,
        font_size=9,
    ):
        super().__init__(parent, takefocus=1, highlightthickness=1)
        self._text = text
        self._command = command
        self._primary = primary
        self._danger = danger
        self._mono = mono
        self._font_size = font_size
        self._hovered = False
        self._focused = False
        self._disabled = False
        self._palette = THEMES["dark"]

        fn = mono_font(font_size, "bold" if (primary or danger) else "normal") if mono else ui_font(font_size, "bold" if (primary or danger) else "normal")
        lbl_kw = {"text": text, "font": fn, "padx": padx, "pady": pady}
        if width is not None:
            lbl_kw["width"] = width
        self._label = tk.Label(self, **lbl_kw)
        self._label.pack(fill="both", expand=True)

        for w in (self, self._label):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Return>", self._on_click)
        self.bind("<space>", self._on_click)
        self.configure(cursor="hand2")
        self._label.configure(cursor="hand2")

    def set_text(self, text):
        self._text = text
        self._label.configure(text=text)

    def set_primary(self, primary):
        self._primary = bool(primary)
        self.apply_theme(self._palette)

    def set_enabled(self, enabled):
        self._disabled = not bool(enabled)
        if self._disabled:
            self._hovered = False
        cur = "arrow" if self._disabled else "hand2"
        self.configure(cursor=cur, takefocus=0 if self._disabled else 1)
        self._label.configure(cursor=cur)
        self.apply_theme(self._palette)

    def apply_theme(self, palette):
        self._palette = palette
        if self._disabled:
            face_bg = palette["surface"]
            face_fg = palette["fg_muted"]
            border_col = palette["border_subtle"]
            thick = 1
        elif self._danger:
            face_bg = palette["surface"] if self._hovered else palette["danger"]
            face_fg = palette["danger"] if self._hovered else palette["danger_fg"]
            border_col = palette["danger"]
            thick = 2 if self._focused else 1
        elif self._primary:
            face_bg = palette["elevated"] if self._hovered else palette["accent"]
            face_fg = palette["fg"] if self._hovered else palette["accent_fg"]
            border_col = palette["fg"] if self._focused else palette["accent"]
            thick = 2 if self._focused else 1
        else:
            face_bg = palette["fg"] if self._hovered else palette["elevated"]
            face_fg = palette["bg"] if self._hovered else palette["fg"]
            border_col = palette["accent"] if self._focused else palette["border_strong"]
            thick = 2 if self._focused else 1

        weight = "bold" if (self._primary or self._danger or self._hovered) and not self._disabled else "normal"
        fn = mono_font(self._font_size, weight) if self._mono else ui_font(self._font_size, weight)
        self.configure(
            bg=border_col,
            highlightbackground=border_col,
            highlightcolor=palette["accent"],
            highlightthickness=thick,
        )
        self._label.configure(bg=face_bg, fg=face_fg, font=fn)

    def _on_click(self, _evt=None):
        if not self._disabled and self._command:
            _trigger_ui_audio("press")
            self._command()

    def _on_enter(self, _evt=None):
        if not self._disabled:
            self._hovered = True
            self.apply_theme(self._palette)

    def _on_leave(self, _evt=None):
        if self._hovered:
            self._hovered = False
            self.apply_theme(self._palette)

    def _on_focus_in(self, _evt=None):
        self._focused = True
        self.apply_theme(self._palette)

    def _on_focus_out(self, _evt=None):
        self._focused = False
        self.apply_theme(self._palette)


class ToggleSwitch(tk.Canvas):
    """Animated pill toggle switch with Volvo Amber active state and keyboard accessibility."""

    W = 48
    H = 24

    def __init__(self, parent, value=False, on_change=None):
        super().__init__(parent, width=self.W, height=self.H, highlightthickness=0, bd=0, takefocus=1, cursor="hand2")
        self._value = bool(value)
        self._pos = 1.0 if self._value else 0.0
        self._anim_id = None
        self._on_change = on_change
        self._focused = False
        self._palette = THEMES["dark"]

        self.bind("<Button-1>", self._toggle)
        self.bind("<Return>", self._toggle)
        self.bind("<space>", self._toggle)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)

    def get(self):
        return self._value

    def set(self, val, notify=False, animate=True):
        new_val = bool(val)
        changed = new_val != self._value
        self._value = new_val
        target_pos = 1.0 if self._value else 0.0
        if animate and changed and self.winfo_exists():
            self._animate_to(target_pos)
        else:
            self._pos = target_pos
            self._redraw()
        if notify and self._on_change:
            self._on_change(self._value)

    def _animate_to(self, target_pos):
        if self._anim_id is not None:
            try:
                self.after_cancel(self._anim_id)
            except Exception:
                pass
            self._anim_id = None

        start_pos = self._pos
        start_ts = time.perf_counter()
        dur_s = 0.085

        def step():
            if not self.winfo_exists():
                return
            t = min(1.0, (time.perf_counter() - start_ts) / dur_s)
            self._pos = start_pos + (target_pos - start_pos) * ease_out_cubic(t)
            self._redraw()
            if t < 1.0:
                self._anim_id = self.after(15, step)
            else:
                self._pos = target_pos
                self._anim_id = None

        self._anim_id = self.after(1, step)

    def _toggle(self, _evt=None):
        _trigger_ui_audio("press" if not self._value else "back")
        self.set(not self._value, notify=True, animate=True)

    def _on_focus_in(self, _evt=None):
        self._focused = True
        self._redraw()

    def _on_focus_out(self, _evt=None):
        self._focused = False
        self._redraw()

    def apply_theme(self, palette):
        self._palette = palette
        self._redraw()

    def _redraw(self):
        p = self._palette
        self.delete("all")
        parent_bg = p.get("surface", p["bg"])
        self.configure(bg=parent_bg)

        is_on = self._pos >= 0.5
        track_fill = p["accent"] if is_on else p["elevated"]
        outline_col = p["fg"] if self._focused else (p["accent"] if is_on else p["border_strong"])
        knob_fill = p["accent_fg"] if is_on else p["fg"]

        x1, y1, x2, y2 = 2, 2, self.W - 2, self.H - 2
        self._draw_pill(x1, y1, x2, y2, track_fill, outline_col, 2 if self._focused else 1)

        pad = 5
        d = self.H - pad * 2
        min_x = pad
        max_x = self.W - pad - d
        kx = min_x + (max_x - min_x) * self._pos
        self.create_oval(kx, pad, kx + d, pad + d, fill=knob_fill, outline="")

    def _draw_pill(self, x1, y1, x2, y2, fill, outline, width):
        h = y2 - y1
        self.create_arc(x1, y1, x1 + h, y2, start=90, extent=180, style="pieslice", fill=fill, outline=fill)
        self.create_arc(x2 - h, y1, x2, y2, start=270, extent=180, style="pieslice", fill=fill, outline=fill)
        self.create_rectangle(x1 + h // 2, y1, x2 - h // 2, y2, fill=fill, outline="")
        self.create_arc(x1, y1, x1 + h, y2, start=90, extent=180, style="arc", outline=outline, width=width)
        self.create_arc(x2 - h, y1, x2, y2, start=270, extent=180, style="arc", outline=outline, width=width)
        self.create_line(x1 + h // 2, y1, x2 - h // 2, y1, fill=outline, width=width)
        self.create_line(x1 + h // 2, y2, x2 - h // 2, y2, fill=outline, width=width)


class SegmentedControl(tk.Frame):
    """Segmented selector with Volvo Amber active highlight and arrow-key navigation."""

    def __init__(self, parent, options, selected_key, on_change=None, font_size=9):
        super().__init__(parent, highlightthickness=1, bd=0, takefocus=1)
        self._choices = options
        self._selected = selected_key
        self._on_change = on_change
        self._font_size = font_size
        self._palette = THEMES["dark"]
        self._focused = False
        self._buttons = {}

        for idx, (key, label) in enumerate(options):
            lbl = tk.Label(self, text=label, font=ui_font(font_size, "bold"), padx=12, pady=5, cursor="hand2")
            lbl.pack(side="left", padx=(0 if idx == 0 else 1, 0))
            lbl.bind("<Button-1>", lambda _e, k=key: self._on_user_select(k))
            self._buttons[key] = lbl

        self.bind("<FocusIn>", lambda _e: self._set_focus(True))
        self.bind("<FocusOut>", lambda _e: self._set_focus(False))
        self.bind("<Left>", lambda _e: self._step(-1))
        self.bind("<Right>", lambda _e: self._step(1))
        self.bind("<space>", lambda _e: self._step(1))
        self.bind("<Return>", lambda _e: self._step(1))

    def _set_focus(self, state):
        self._focused = state
        self.apply_theme(self._palette)

    def _on_user_select(self, key):
        if key != self._selected:
            _trigger_ui_audio("press")
        self.select(key, notify=True)

    def _step(self, delta):
        keys = [k for k, _ in self._choices]
        if self._selected in keys:
            idx = (keys.index(self._selected) + delta) % len(keys)
            _trigger_ui_audio("nav")
            self.select(keys[idx], notify=True)

    def select(self, key, notify=False):
        self._selected = key
        self.apply_theme(self._palette)
        if notify and self._on_change:
            self._on_change(key)

    def apply_theme(self, palette):
        self._palette = palette
        border = palette["accent"] if self._focused else palette["border_strong"]
        self.configure(
            bg=border,
            highlightbackground=border,
            highlightcolor=palette["accent"],
            highlightthickness=2 if self._focused else 1,
        )
        for key, lbl in self._buttons.items():
            active = key == self._selected
            lbl.configure(
                bg=palette["accent"] if active else palette["elevated"],
                fg=palette["accent_fg"] if active else palette["fg"],
                font=ui_font(self._font_size, "bold" if active else "normal"),
            )


class StepperControl(tk.Frame):
    """Numeric stepper (- / value / +) with tabular monospace readout."""

    def __init__(self, parent, value, min_val, max_val, step, fmt="{:.0f}", on_change=None):
        super().__init__(parent, highlightthickness=0, bd=0)
        self._val = value
        self._min = min_val
        self._max = max_val
        self._step = step
        self._fmt = fmt
        self._on_change = on_change
        self._palette = THEMES["dark"]

        self._btn_dec = MonoButton(self, "-", command=lambda: self._adjust(-self._step), mono=True, padx=10, pady=3, font_size=10)
        self._btn_dec.pack(side="left")

        self._val_lbl = tk.Label(self, text=self._fmt.format(self._val), font=mono_font(10, "bold"), width=7, anchor="center")
        self._val_lbl.pack(side="left", padx=4)

        self._btn_inc = MonoButton(self, "+", command=lambda: self._adjust(self._step), mono=True, padx=10, pady=3, font_size=10)
        self._btn_inc.pack(side="left")

    def set_value(self, value):
        self._val = max(self._min, min(self._max, value))
        self._val_lbl.configure(text=self._fmt.format(self._val))

    def _adjust(self, delta):
        nxt = round(self._val + delta, 4)
        nxt = max(self._min, min(self._max, nxt))
        if nxt != self._val:
            self._val = nxt
            self._val_lbl.configure(text=self._fmt.format(self._val))
            if self._on_change:
                self._on_change(self._val)

    def apply_theme(self, palette):
        self._palette = palette
        surf = palette.get("surface", palette["bg"])
        self.configure(bg=surf)
        self._val_lbl.configure(bg=surf, fg=palette["fg"])
        self._btn_dec.apply_theme(palette)
        self._btn_inc.apply_theme(palette)


@dataclass
class RowHandle:
    control: tk.Widget
    title_lbl: tk.Label
    sub_lbl: tk.Label = None
    badge_lbl: tk.Label = None


class CardGroup(tk.Frame):
    """Self-theming Nordic Cockpit card container that eliminates manual _themed_* tracking lists."""

    def __init__(self, parent, title=None):
        super().__init__(parent, highlightthickness=0, bd=0)
        self._title_lbl = None
        if title:
            self._title_lbl = tk.Label(self, text=title, font=ui_font(9, "bold"), anchor="w")
            self._title_lbl.pack(fill="x", pady=(6, 5))

        self.box = tk.Frame(self, highlightthickness=1, bd=0)
        self.box.pack(fill="x", pady=(0, 8))

        self._rows = []
        self._seps = []
        self._primary_labels = []
        self._secondary_labels = []
        self._badges = []
        self._controls = []

    def add_row(self, title, subtitle="", control_factory=None, badge_text=None):
        if self._rows:
            sep = tk.Frame(self.box, height=1)
            sep.pack(fill="x")
            self._seps.append(sep)

        row = tk.Frame(self.box, padx=16, pady=10)
        row.pack(fill="x")
        self._rows.append(row)

        ctrl = None
        if control_factory is not None:
            right = tk.Frame(row)
            right.pack(side="right", padx=(12, 0))
            self._rows.append(right)
            ctrl = control_factory(right)
            ctrl.pack(side="right")
            self._controls.append(ctrl)

        left = tk.Frame(row)
        left.pack(side="left", fill="both", expand=True)
        self._rows.append(left)

        title_row = tk.Frame(left)
        title_row.pack(fill="x")
        self._rows.append(title_row)

        badge_lbl = None
        if badge_text:
            badge_lbl = tk.Label(title_row, text=badge_text, font=mono_font(8, "bold"), padx=6, pady=1)
            badge_lbl.pack(side="left", padx=(0, 8))
            self._badges.append(badge_lbl)

        t_lbl = tk.Label(title_row, text=title, font=ui_font(10, "bold"), anchor="w")
        t_lbl.pack(side="left", fill="x", expand=True)
        self._primary_labels.append(t_lbl)

        s_lbl = None
        if subtitle:
            s_lbl = tk.Label(left, text=subtitle, font=ui_font(9), anchor="w", wraplength=410, justify="left")
            s_lbl.pack(fill="x", pady=(2, 0))
            self._secondary_labels.append(s_lbl)

        return RowHandle(control=ctrl, title_lbl=t_lbl, sub_lbl=s_lbl, badge_lbl=badge_lbl)

    def apply_theme(self, palette):
        bg = palette["bg"]
        surf = palette.get("surface", bg)
        self.configure(bg=bg)
        if self._title_lbl is not None:
            self._title_lbl.configure(bg=bg, fg=palette["fg_secondary"])

        self.box.configure(
            bg=surf,
            highlightbackground=palette["border_subtle"],
            highlightcolor=palette["border_subtle"],
        )
        for r in self._rows:
            r.configure(bg=surf)
        for sep in self._seps:
            sep.configure(bg=palette["border_subtle"])
        for lbl in self._primary_labels:
            lbl.configure(bg=surf, fg=palette["fg"])
        for lbl in self._secondary_labels:
            lbl.configure(bg=surf, fg=palette["fg_secondary"])
        for b in self._badges:
            b.configure(bg=palette["elevated"], fg=palette["accent"])
        for ctrl in self._controls:
            if hasattr(ctrl, "apply_theme"):
                ctrl.apply_theme(palette)
            else:
                ctrl.configure(bg=surf, fg=palette["fg_secondary"])


class FlatScrollbar(tk.Canvas):
    """Minimal monochrome Canvas scrollbar supporting vertical and horizontal scrolling."""

    def __init__(self, parent, orient="vertical", command=None, thickness=10):
        kw = {"width": thickness} if orient == "vertical" else {"height": thickness}
        super().__init__(parent, highlightthickness=0, bd=0, cursor="hand2", **kw)
        self._orient = orient
        self._command = command
        self._thickness = thickness
        self._lo = 0.0
        self._hi = 1.0
        self._dragging = False
        self._drag_offset = 0.0
        self._palette = THEMES["dark"]

        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set(self, lo, hi):
        self._lo = max(0.0, min(1.0, float(lo)))
        self._hi = max(self._lo, min(1.0, float(hi)))
        self._redraw()

    def apply_theme(self, palette):
        self._palette = palette
        self._redraw()

    def _span(self):
        return max(1, self.winfo_height() if self._orient == "vertical" else self.winfo_width())

    def _thumb_bounds(self):
        span = self._span()
        if self._hi - self._lo >= 0.999:
            return 0.0, float(span)
        thumb_len = max(24.0, (self._hi - self._lo) * span)
        max_start = max(0.0, span - thumb_len)
        frac_range = max(1e-6, 1.0 - (self._hi - self._lo))
        start = (self._lo / frac_range) * max_start
        return start, start + thumb_len

    def _redraw(self):
        self.delete("all")
        p = self._palette
        self.configure(bg=p["bg"])
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        if self._hi - self._lo >= 0.999:
            return
        t1, t2 = self._thumb_bounds()
        pad = 2
        if self._orient == "vertical":
            self.create_rectangle(pad, t1, w - pad, t2, fill=p["fg_muted"], outline="")
        else:
            self.create_rectangle(t1, pad, t2, h - pad, fill=p["fg_muted"], outline="")

    def _on_press(self, evt):
        if self._hi - self._lo >= 0.999 or not self._command:
            return
        pos = evt.y if self._orient == "vertical" else evt.x
        t1, t2 = self._thumb_bounds()
        if t1 <= pos <= t2:
            self._dragging = True
            self._drag_offset = pos - t1
        else:
            span = self._span()
            thumb_len = t2 - t1
            max_start = max(1.0, span - thumb_len)
            target_start = max(0.0, min(max_start, pos - thumb_len / 2.0))
            frac = (target_start / max_start) * max(0.0, 1.0 - (self._hi - self._lo))
            self._command("moveto", frac)

    def _on_drag(self, evt):
        if not self._dragging or not self._command:
            return
        pos = evt.y if self._orient == "vertical" else evt.x
        t1, t2 = self._thumb_bounds()
        span = self._span()
        thumb_len = t2 - t1
        max_start = max(1.0, span - thumb_len)
        target_start = max(0.0, min(max_start, pos - self._drag_offset))
        frac = (target_start / max_start) * max(0.0, 1.0 - (self._hi - self._lo))
        self._command("moveto", frac)

    def _on_release(self, _evt):
        self._dragging = False
