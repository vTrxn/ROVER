import ctypes
from ctypes import wintypes
import os
import sys
import tkinter as tk
from PIL import Image, ImageDraw

MATTE_DARK = "#1E1E1E"
CRISP_WHITE = "#F5F5F5"

THEMES = {
    "dark": {
        "name": "dark",
        "label": "Gris mate oscuro",
        "bg": MATTE_DARK,
        "fg": CRISP_WHITE,
        "inv_bg": CRISP_WHITE,
        "inv_fg": MATTE_DARK,
        "caption_colorref": 0x001E1E1E,
        "text_colorref": 0x00F5F5F5,
        "dark_caption": 1,
    },
    "light": {
        "name": "light",
        "label": "Blanco invertido",
        "bg": CRISP_WHITE,
        "fg": MATTE_DARK,
        "inv_bg": MATTE_DARK,
        "inv_fg": CRISP_WHITE,
        "caption_colorref": 0x00F5F5F5,
        "text_colorref": 0x001E1E1E,
        "dark_caption": 0,
    },
}

FONT_FAMILY = "JetBrainsMono NF"
_FONT_LOADED = False


def get_resource_path(rel_path):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel_path)


def load_bundled_fonts():
    """Register bundled JetBrainsMono NF fonts privately for the current process."""
    global _FONT_LOADED, FONT_FAMILY
    if _FONT_LOADED:
        return FONT_FAMILY
    _FONT_LOADED = True
    try:
        gdi32 = ctypes.windll.gdi32
        FR_PRIVATE = 0x10
        fonts_dir = get_resource_path(os.path.join("assets", "fonts"))
        if os.path.isdir(fonts_dir):
            for fname in os.listdir(fonts_dir):
                if fname.lower().endswith(".ttf"):
                    fpath = os.path.join(fonts_dir, fname)
                    gdi32.AddFontResourceExW(fpath, FR_PRIVATE, 0)
    except Exception:
        pass
    try:
        import tkinter.font as tkfont

        fams = set(tkfont.families())
        if "JetBrainsMono NF" in fams:
            FONT_FAMILY = "JetBrainsMono NF"
        elif "Consolas" in fams:
            FONT_FAMILY = "Consolas"
        else:
            FONT_FAMILY = "TkFixedFont"
    except Exception:
        FONT_FAMILY = "Consolas"
    return FONT_FAMILY


def font_tuple(size=10, weight="normal"):
    if weight == "bold":
        return (FONT_FAMILY, size, "bold")
    return (FONT_FAMILY, size)


def apply_dwm_window_theme(win, theme_name="dark", corner_round=True):
    """Match native Windows 11 titlebar and border to the active 2-color palette."""
    t = THEMES.get(theme_name, THEMES["dark"])
    try:
        win.update_idletasks()
        hwnd = int(win.wm_frame(), 16) if win.wm_frame() != "0x0" else win.winfo_id()
        dwmapi = ctypes.windll.dwmapi
        attrs = [
            (20, ctypes.c_int(t["dark_caption"])),  # DWMWA_USE_IMMERSIVE_DARK_MODE
            (35, ctypes.c_int(t["caption_colorref"])),  # DWMWA_CAPTION_COLOR
            (36, ctypes.c_int(t["text_colorref"])),  # DWMWA_TEXT_COLOR
            (34, ctypes.c_int(t["text_colorref"])),  # DWMWA_BORDER_COLOR
        ]
        if corner_round:
            attrs.append((33, ctypes.c_int(2)))  # DWMWA_WINDOW_CORNER_PREFERENCE = Round
        for attr_id, c_val in attrs:
            dwmapi.DwmSetWindowAttribute(hwnd, attr_id, ctypes.byref(c_val), ctypes.sizeof(c_val))
    except Exception:
        pass


def build_tray_pil_image(theme_name="dark", size=64):
    """Create a 2-color tray icon matching the active theme."""
    t = THEMES.get(theme_name, THEMES["dark"])
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = max(4, int(size * 0.22))
    d.rounded_rectangle([1, 1, size - 2, size - 2], radius=r, fill=t["bg"], outline=t["fg"], width=max(2, size // 16))
    cy = size // 2
    arm = max(3, int(size * 0.14))
    thick = max(2, int(size * 0.08))
    cx_left = int(size * 0.34)
    d.rectangle([cx_left - arm, cy - thick // 2, cx_left + arm, cy + thick // 2], fill=t["fg"])
    d.rectangle([cx_left - thick // 2, cy - arm, cx_left + thick // 2, cy + arm], fill=t["fg"])
    br = max(2, int(size * 0.07))
    bx = int(size * 0.66)
    d.ellipse([bx - br, cy - int(size * 0.10) - br, bx + br, cy - int(size * 0.10) + br], fill=t["fg"])
    d.ellipse([bx - br + int(size * 0.10), cy + int(size * 0.05) - br, bx + br + int(size * 0.10), cy + int(size * 0.05) + br], fill=t["fg"])
    return img


class MonoButton(tk.Frame):
    """Flat 2-color button with focus ring and keyboard Space/Enter support."""

    def __init__(self, parent, text, command=None, primary=False, width=None, padx=14, pady=6, font_size=9):
        super().__init__(parent, takefocus=1, highlightthickness=2)
        self._text = text
        self._command = command
        self._primary = primary
        self._hovered = False
        self._focused = False
        self._disabled = False
        self._palette = THEMES["dark"]

        lbl_kw = {"text": text, "font": font_tuple(font_size, "bold" if primary else "normal"), "padx": padx, "pady": pady}
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
        self._primary = primary
        self.apply_theme(self._palette)

    def set_enabled(self, enabled):
        self._disabled = not enabled
        cur = "arrow" if self._disabled else "hand2"
        self.configure(cursor=cur, takefocus=1 if enabled else 0)
        self._label.configure(cursor=cur)
        self.apply_theme(self._palette)

    def apply_theme(self, palette):
        self._palette = palette
        bg = palette["bg"]
        fg = palette["fg"]
        if self._primary:
            face_bg = bg if self._hovered else fg
            face_fg = fg if self._hovered else bg
        else:
            face_bg = fg if self._hovered else bg
            face_fg = bg if self._hovered else fg
        ring_color = fg if self._focused else (fg if not self._primary else fg)
        self.configure(
            bg=fg,
            highlightbackground=fg,
            highlightcolor=ring_color,
            highlightthickness=2 if self._focused else 1,
        )
        self._label.configure(bg=face_bg, fg=face_fg)

    def _on_click(self, _evt=None):
        if not self._disabled and self._command:
            self._command()

    def _on_enter(self, _evt=None):
        self._hovered = True
        self.apply_theme(self._palette)

    def _on_leave(self, _evt=None):
        self._hovered = False
        self.apply_theme(self._palette)

    def _on_focus_in(self, _evt=None):
        self._focused = True
        self.apply_theme(self._palette)

    def _on_focus_out(self, _evt=None):
        self._focused = False
        self.apply_theme(self._palette)


class ToggleSwitch(tk.Canvas):
    """macOS-style pill toggle switch rendered strictly in 2 colors."""

    W = 46
    H = 24

    def __init__(self, parent, value=False, on_change=None):
        super().__init__(parent, width=self.W, height=self.H, highlightthickness=2, bd=0, takefocus=1, cursor="hand2")
        self._value = bool(value)
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

    def set(self, val, notify=False):
        self._value = bool(val)
        self._redraw()
        if notify and self._on_change:
            self._on_change(self._value)

    def _toggle(self, _evt=None):
        self.set(not self._value, notify=True)

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
        self.configure(bg=p["bg"], highlightbackground=p["bg"], highlightcolor=p["fg"])
        track_fill = p["fg"] if self._value else p["bg"]
        knob_fill = p["bg"] if self._value else p["fg"]
        r = (self.H - 4) // 2
        x1, y1, x2, y2 = 2, 2, self.W - 2, self.H - 2
        self._draw_pill(x1, y1, x2, y2, track_fill, p["fg"], 2)
        pad = 5
        d = self.H - pad * 2
        kx = (self.W - pad - d) if self._value else pad
        self.create_oval(kx, pad, kx + d, pad + d, fill=knob_fill, outline="")
        if self._focused:
            self.create_rectangle(0, 0, self.W - 1, self.H - 1, outline=p["fg"], width=1)

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
    """Segmented 2-color selector where the active item inverts bg/fg."""

    def __init__(self, parent, options, selected_key, on_change=None, font_size=9):
        super().__init__(parent, highlightthickness=1, bd=0, takefocus=1)
        self._choices = options  # list of (key, label)
        self._selected = selected_key
        self._on_change = on_change
        self._palette = THEMES["dark"]
        self._focused = False
        self._buttons = {}

        for idx, (key, label) in enumerate(options):
            lbl = tk.Label(self, text=label, font=font_tuple(font_size, "bold"), padx=12, pady=5, cursor="hand2")
            lbl.pack(side="left", padx=(0 if idx == 0 else 1, 0))
            lbl.bind("<Button-1>", lambda _e, k=key: self.select(k, notify=True))
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

    def _step(self, delta):
        keys = [k for k, _ in self._choices]
        if self._selected in keys:
            idx = (keys.index(self._selected) + delta) % len(keys)
            self.select(keys[idx], notify=True)

    def select(self, key, notify=False):
        self._selected = key
        self.apply_theme(self._palette)
        if notify and self._on_change:
            self._on_change(key)

    def apply_theme(self, palette):
        self._palette = palette
        self.configure(
            bg=palette["fg"],
            highlightbackground=palette["fg"],
            highlightcolor=palette["fg"],
            highlightthickness=2 if self._focused else 1,
        )
        for key, lbl in self._buttons.items():
            active = key == self._selected
            lbl.configure(
                bg=palette["fg"] if active else palette["bg"],
                fg=palette["bg"] if active else palette["fg"],
                font=font_tuple(9, "bold" if active else "normal"),
            )


class StepperControl(tk.Frame):
    """Numeric stepper (- / value / +) with keyboard arrow and click support."""

    def __init__(self, parent, value, min_val, max_val, step, fmt="{:.0f}", on_change=None):
        super().__init__(parent, highlightthickness=0, bd=0)
        self._val = value
        self._min = min_val
        self._max = max_val
        self._step = step
        self._fmt = fmt
        self._on_change = on_change
        self._palette = THEMES["dark"]

        self._btn_dec = MonoButton(self, "-", command=lambda: self._adjust(-self._step), padx=10, pady=3, font_size=10)
        self._btn_dec.pack(side="left")

        self._val_lbl = tk.Label(self, text=self._fmt.format(self._val), font=font_tuple(10, "bold"), width=7, anchor="center")
        self._val_lbl.pack(side="left", padx=4)

        self._btn_inc = MonoButton(self, "+", command=lambda: self._adjust(self._step), padx=10, pady=3, font_size=10)
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
        self.configure(bg=palette["bg"])
        self._val_lbl.configure(bg=palette["bg"], fg=palette["fg"])
        self._btn_dec.apply_theme(palette)
        self._btn_inc.apply_theme(palette)
