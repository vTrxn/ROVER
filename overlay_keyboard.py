import time
import tkinter as tk
from input_synth import (
    VK_BACK,
    VK_LEFT,
    VK_RETURN,
    VK_RIGHT,
    VK_SPACE,
    get_cursor_pos,
    get_work_area,
    set_cursor_pos,
)
from rover_system import log_error
from ui_theme import THEMES, apply_dwm_window_theme, dp, ease_out_cubic, mono_font, ui_font

# 4 complete keyboard layers: lower, shift (1-shot), caps (locked), symbols (#+= & Spanish accents)
KEYBOARD_LAYOUTS = {
    "lower": [
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "Borrar"],
        ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "Mayus"],
        ["a", "s", "d", "f", "g", "h", "j", "k", "l", "ñ", "Enter"],
        ["z", "x", "c", "v", "b", "n", "m", ".", ",", "-", "?"],
        ["#+=", "Espacio", ".com", "@gmail.com", "<", ">"],
    ],
    "shift": [
        ["!", "@", "#", "$", "%", "&", "/", "(", ")", "=", "Borrar"],
        ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "Mayus"],
        ["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ñ", "Enter"],
        ["Z", "X", "C", "V", "B", "N", "M", ":", ";", "_", "¿"],
        ["#+=", "Espacio", ".com", "@gmail.com", "<", ">"],
    ],
    "caps": [
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "Borrar"],
        ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "CAPS"],
        ["A", "S", "D", "F", "G", "H", "J", "K", "L", "Ñ", "Enter"],
        ["Z", "X", "C", "V", "B", "N", "M", ":", ";", "_", "¿"],
        ["#+=", "Espacio", ".com", "@gmail.com", "<", ">"],
    ],
    "symbols": [
        ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "Borrar"],
        ["_", "+", "=", "{", "}", "[", "]", "\\", "|", "~", "Mayus"],
        ["á", "é", "í", "ó", "ú", "ü", ":", ";", "\"", "'", "Enter"],
        ["¿", "?", "¡", "!", "<", ">", "/", ".", ",", "-", "ABC"],
        ["ABC", "Espacio", ".com", "@gmail.com", "<", ">"],
    ],
}

# Normalize bottom-left key label
for _layer_key in ("lower", "shift", "caps"):
    KEYBOARD_LAYOUTS[_layer_key][4][0] = "#+="

KB_HINTS = [
    ("D-Pad", "Mover"),
    ("A/RB", "Escribir"),
    ("X", "Borrar"),
    ("Y", "Espacio"),
    ("LT", "#+="),
    ("B", "Cerrar"),
]

FUNCTION_KEYS = {"Borrar", "Mayus", "CAPS", "Enter", "#+=", "ABC", "Espacio", ".com", "<", ">"}


class FloatingKeyboard:
    """Focus-safe 4-layer Nordic Cockpit on-screen keyboard with Key-Preview Pop-up animation and reliable close."""

    COL_W = 58
    ACT_W = 120
    KEY_H = 44
    GAP = 6
    PAD = 6
    POPUP_HEADROOM = 38  # Vertical canvas space above Row 0 reserved for the Key-Preview Pop-up callout

    def __init__(self, root, config_store, synth, audio, on_state_change=None, on_consume_buttons=None):
        self.root = root
        self.config = config_store
        self.synth = synth
        self.audio = audio
        self._on_state_change = on_state_change
        self._on_consume_buttons = on_consume_buttons

        self.visible = False
        self.layer = "lower"
        self.cur_row = 1
        self.cur_col = 0
        self.saved_col = 0

        self._kb_w = 1
        self._kb_h = 1
        self._kb_x = 0
        self._anim_id = None
        self._enter_hide_id = None
        self._popup_anim_id = None
        self._popup_hide_id = None

        self.COL_W = dp(58)
        self.ACT_W = dp(120)
        self.KEY_H = dp(44)
        self.GAP = dp(6)
        self.PAD = dp(6)
        self.POPUP_HEADROOM = dp(40)

        self.grid_w = self.PAD * 2 + 10 * self.COL_W + self.ACT_W + 10 * self.GAP
        self.grid_h = self.POPUP_HEADROOM + self.PAD * 2 + 5 * self.KEY_H + 4 * self.GAP + dp(4)

        self._build_ui()
        self._refresh_metrics()
        self.win.geometry(f"{self._kb_w}x{self._kb_h}+{self._kb_x}+{self._target_y()}")
        self.apply_theme()
        self.synth.focus_guard.apply_noactivate_style(self.win)
        self.win.withdraw()

    def _palette(self):
        return THEMES.get(self.config["theme"], THEMES["dark"])

    def _current_grid(self):
        base = KEYBOARD_LAYOUTS.get(self.layer, KEYBOARD_LAYOUTS["lower"])
        snips = self.config.get_kb_snippets()
        grid = [list(r) for r in base]
        grid[4] = [base[4][0], "Espacio", snips[0], snips[1], "<", ">"]
        return grid

    def _build_ui(self):
        self.win = tk.Toplevel(self.root)
        self.win.withdraw()
        self.win.overrideredirect(True)

        self.outer = tk.Frame(self.win, padx=14, pady=10)
        self.outer.pack(fill="both", expand=True, padx=1, pady=1)

        self.header = tk.Frame(self.outer)
        self.header.pack(fill="x", pady=(0, 4))

        self.hints_frame = tk.Frame(self.header)
        self.hints_frame.pack(side="left")

        self._hint_badges = []
        for btn_txt, act_txt in KB_HINTS:
            item = tk.Frame(self.hints_frame)
            item.pack(side="left", padx=(0, 6))
            b_lbl = tk.Label(item, text=btn_txt, font=mono_font(8, "bold"), padx=5, pady=1)
            b_lbl.pack(side="left")
            a_lbl = tk.Label(item, text=act_txt, font=ui_font(8), padx=3)
            a_lbl.pack(side="left")
            self._hint_badges.append((item, b_lbl, a_lbl))

        self.status_frame = tk.Frame(self.header)
        self.status_frame.pack(side="right")

        self.close_badge = tk.Label(
            self.status_frame,
            text="× Cerrar",
            font=ui_font(8, "bold"),
            padx=8,
            pady=2,
            cursor="hand2",
        )
        self.close_badge.pack(side="right", padx=(6, 0))
        self.close_badge.bind("<Button-1>", lambda _e: self.hide(reason="close_button"))

        self.pos_badge = tk.Label(
            self.status_frame,
            text="ABAJO",
            font=mono_font(8, "bold"),
            padx=7,
            pady=2,
            cursor="hand2",
        )
        self.pos_badge.pack(side="right", padx=(6, 0))
        self.pos_badge.bind("<Button-1>", lambda _e: self.toggle_position())

        self.layer_badge = tk.Label(
            self.status_frame,
            text="ABC",
            font=mono_font(8, "bold"),
            padx=7,
            pady=2,
            cursor="hand2",
        )
        self.layer_badge.pack(side="right")
        self.layer_badge.bind("<Button-1>", lambda _e: self.cycle_shift_state())

        self.canvas = tk.Canvas(self.outer, width=self.grid_w, height=self.grid_h, highlightthickness=0, bd=0)
        self.canvas.pack()

        # Compute geometry for all 5 rows (Row 4 has 6 keys including 2 configurable snippets)
        self.key_items = []
        base_layout = self._current_grid()
        # Row 4 spans in grid-column units: [#+= (2)] [Espacio (3)] [Snippet1 (2)] [Snippet2 (2)] [< (1)] [> (1)]
        r4_spans = [
            (0, 2),   # #+= / ABC
            (2, 5),   # Espacio
            (5, 7),   # Snippet 1
            (7, 9),   # Snippet 2
            (9, 10),  # <
            (10, 11), # >
        ]

        for r_idx, row in enumerate(base_layout):
            row_items = []
            y1 = self.POPUP_HEADROOM + self.PAD + r_idx * (self.KEY_H + self.GAP) + (3 if r_idx == 4 else 0)
            y2 = y1 + self.KEY_H
            if r_idx == 4:
                for c_idx, key_text in enumerate(row):
                    c_start, c_end = r4_spans[c_idx]
                    x1 = self.PAD + c_start * (self.COL_W + self.GAP)
                    if c_end == 11:
                        x2 = self.grid_w - self.PAD
                    else:
                        x2 = self.PAD + c_end * self.COL_W + (c_end - 1) * self.GAP
                    row_items.append(self._create_key_cell(r_idx, c_idx, x1, y1, x2, y2, key_text, (c_start, c_end)))
            else:
                for c_idx, key_text in enumerate(row):
                    x1 = self.PAD + c_idx * (self.COL_W + self.GAP)
                    w = self.ACT_W if c_idx == 10 else self.COL_W
                    x2 = x1 + w
                    row_items.append(self._create_key_cell(r_idx, c_idx, x1, y1, x2, y2, key_text, (c_idx, c_idx + 1)))
            self.key_items.append(row_items)

        # Build Key-Preview Pop-up overlay items on top of the canvas (hidden initially)
        self._popup_shadow = self.canvas.create_rectangle(0, 0, 1, 1, state="hidden", width=0)
        self._popup_box = self.canvas.create_rectangle(0, 0, 1, 1, state="hidden", width=2)
        self._popup_bar = self.canvas.create_rectangle(0, 0, 1, 1, state="hidden", width=0)
        self._popup_text = self.canvas.create_text(0, 0, text="", font=mono_font(18, "bold"), state="hidden")

    def _create_key_cell(self, r_idx, c_idx, x1, y1, x2, y2, key_text, col_span):
        bg = self.canvas.create_rectangle(x1, y1, x2, y2, width=1)
        accent_bar = self.canvas.create_rectangle(x1 + 2, y1 + 2, x2 - 2, y1 + 5, width=0, state="hidden")
        fsize = 9 if len(key_text) > 2 else 11
        tx = self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=key_text, font=mono_font(fsize, "bold"))
        for item_id in (bg, accent_bar, tx):
            self.canvas.tag_bind(item_id, "<Button-1>", lambda _e, r=r_idx, c=c_idx: self._on_mouse_key_click(r, c))
        return {
            "bg": bg,
            "bar": accent_bar,
            "text": tx,
            "coords": (x1, y1, x2, y2),
            "span": col_span,
        }

    def _on_mouse_key_click(self, r_idx, c_idx):
        prev_r, prev_c = self.cur_row, self.cur_col
        self.cur_row, self.cur_col = r_idx, c_idx
        self.update_key_cell(prev_r, prev_c, active=False)
        self.update_key_cell(self.cur_row, self.cur_col, active=True)
        self.press_current_key()

    def _refresh_metrics(self):
        self.win.update_idletasks()
        self._kb_w = max(self.win.winfo_reqwidth(), 1)
        self._kb_h = max(self.win.winfo_reqheight(), 1)
        wa_l, _wa_t, wa_r, _wa_b = get_work_area(self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        self._kb_x = max(wa_l + 8, min(wa_r - self._kb_w - 8, wa_l + (wa_r - wa_l - self._kb_w) // 2))

    def _target_y(self):
        _wa_l, wa_t, _wa_r, wa_b = get_work_area(self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        if self.config["keyboard_at_top"]:
            return wa_t + 20
        return max(wa_t + 12, wa_b - self._kb_h - 16)

    def _cancel_timers(self):
        for attr in ("_anim_id", "_enter_hide_id"):
            aid = getattr(self, attr, None)
            if aid is not None:
                try:
                    self.root.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)

    def _cancel_popup(self):
        for attr in ("_popup_anim_id", "_popup_hide_id"):
            aid = getattr(self, attr, None)
            if aid is not None:
                try:
                    self.root.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)
        for item_id in (self._popup_shadow, self._popup_box, self._popup_bar, self._popup_text):
            self.canvas.itemconfig(item_id, state="hidden")

    def _show_key_preview_popup(self, r_idx, c_idx, label_text):
        """Animate a tactile Key-Preview Pop-up above the pressed key cell (150ms total lifecycle)."""
        self._cancel_popup()
        p = self._palette()
        cell = self.key_items[r_idx][c_idx]
        x1, y1, x2, _y2 = cell["coords"]
        cx = (x1 + x2) / 2.0

        is_wide = len(label_text) > 2
        pw = dp(min(210, max(96, len(label_text) * 12 + 24))) if is_wide else dp(56)
        ph = dp(44)
        px1 = max(dp(6), min(self.grid_w - pw - dp(6), cx - pw / 2.0))
        px2 = px1 + pw

        # Start slightly lower and lift up by 9px over 80ms
        base_py2 = max(ph + dp(4), y1 - dp(3))
        start_offset = float(dp(9))

        fsize = 10 if len(label_text) > 8 else (12 if is_wide else 19)
        self.canvas.itemconfig(self._popup_text, text=label_text, font=mono_font(fsize, "bold"), fill=p["fg"])
        self.canvas.itemconfig(self._popup_shadow, fill=p["bg"], state="normal")
        self.canvas.itemconfig(self._popup_box, fill=p["elevated"], outline=p["accent"], state="normal")
        self.canvas.itemconfig(self._popup_bar, fill=p["accent"], state="normal")
        self.canvas.itemconfig(self._popup_text, state="normal")
        self.canvas.tag_raise(self._popup_shadow)
        self.canvas.tag_raise(self._popup_box)
        self.canvas.tag_raise(self._popup_bar)
        self.canvas.tag_raise(self._popup_text)

        start_ts = time.perf_counter()
        dur_s = 0.080

        def step():
            if not self.win.winfo_exists() or not self.visible:
                self._cancel_popup()
                return
            t = min(1.0, (time.perf_counter() - start_ts) / dur_s)
            dy = start_offset * (1.0 - ease_out_cubic(t))
            py2 = base_py2 + dy
            py1 = py2 - ph
            self.canvas.coords(self._popup_shadow, px1 + 2, py1 + 2, px2 + 2, py2 + 2)
            self.canvas.coords(self._popup_box, px1, py1, px2, py2)
            self.canvas.coords(self._popup_bar, px1 + 2, py1 + 2, px2 - 2, py1 + 6)
            self.canvas.coords(self._popup_text, (px1 + px2) / 2.0, (py1 + py2) / 2.0 + 2)
            if t < 1.0:
                self._popup_anim_id = self.root.after(14, step)
            else:
                self._popup_anim_id = None

        step()
        self._popup_hide_id = self.root.after(165, self._cancel_popup)

    def _animate_y(self, start_y, end_y, duration_ms, on_done=None):
        start_ts = time.perf_counter()
        dur_s = max(0.016, duration_ms / 1000.0)

        def tick():
            if not self.win.winfo_exists():
                return
            t = min(1.0, (time.perf_counter() - start_ts) / dur_s)
            cur_y = int(start_y + (end_y - start_y) * ease_out_cubic(t))
            self.win.geometry(f"{self._kb_w}x{self._kb_h}+{self._kb_x}+{cur_y}")
            if t < 1.0:
                self._anim_id = self.root.after(15, tick)
            else:
                self._anim_id = None
                if on_done:
                    on_done()

        self._anim_id = self.root.after(1, tick)

    def update_key_cell(self, r_idx, c_idx, active=False, flash=False):
        p = self._palette()
        grid = self._current_grid()
        item = self.key_items[r_idx][c_idx]
        text = grid[r_idx][c_idx]

        is_shift_key = text in ("Mayus", "CAPS") and self.layer in ("shift", "caps")
        is_sym_key = text in ("#+=", "ABC") and self.layer == "symbols"
        is_func = text in FUNCTION_KEYS or (r_idx == 4 and c_idx in (2, 3))

        if flash:
            fill = p["fg"]
            fg = p["bg"]
            outline = p["accent"]
            width = 2
            show_bar = True
        elif active:
            fill = p["accent"]
            fg = p["accent_fg"]
            outline = p["fg"]
            width = 2
            show_bar = False
        elif is_shift_key or is_sym_key:
            fill = p["elevated"]
            fg = p["accent"]
            outline = p["accent"]
            width = 2
            show_bar = True
        elif is_func:
            fill = p["elevated"]
            fg = p["fg_secondary"] if text not in ("Espacio", "Enter") else p["fg"]
            outline = p["border_subtle"]
            width = 1
            show_bar = False
        else:
            fill = p["surface"]
            fg = p["fg"]
            outline = p["border_subtle"]
            width = 1
            show_bar = False

        disp_text = (text[:10] + "..") if (r_idx == 4 and c_idx in (2, 3) and len(text) > 12) else text
        fsize = 8 if len(disp_text) > 7 else (9 if len(disp_text) > 2 else 11)
        self.canvas.itemconfig(item["bg"], fill=fill, outline=outline, width=width)
        self.canvas.itemconfig(item["text"], text=disp_text, fill=fg, font=mono_font(fsize, "bold"))
        self.canvas.itemconfig(item["bar"], fill=p["accent"], state="normal" if show_bar else "hidden")

    def apply_theme(self):
        p = self._palette()
        self.win.configure(bg=p["border_strong"])
        self.outer.configure(bg=p["bg"])
        self.header.configure(bg=p["bg"])
        self.hints_frame.configure(bg=p["bg"])
        self.status_frame.configure(bg=p["bg"])
        self.canvas.configure(bg=p["bg"])

        for item, b_lbl, a_lbl in self._hint_badges:
            item.configure(bg=p["bg"])
            b_lbl.configure(bg=p["elevated"], fg=p["accent"])
            a_lbl.configure(bg=p["bg"], fg=p["fg_secondary"])

        self.close_badge.configure(
            bg=p["elevated"],
            fg=p["fg"],
            highlightbackground=p["border_strong"],
            highlightthickness=1,
        )
        self.pos_badge.configure(
            text="ARRIBA" if self.config["keyboard_at_top"] else "ABAJO",
            bg=p["surface"],
            fg=p["fg_secondary"],
            highlightbackground=p["border_subtle"],
            highlightthickness=1,
        )

        layer_labels = {
            "lower": ("abc", False),
            "shift": ("MAYUS 1", True),
            "caps": ("CAPS LOCK", True),
            "symbols": ("SIMBOLOS", True),
        }
        l_txt, l_active = layer_labels.get(self.layer, ("abc", False))
        self.layer_badge.configure(
            text=l_txt,
            bg=p["accent"] if l_active else p["surface"],
            fg=p["accent_fg"] if l_active else p["fg_secondary"],
            highlightbackground=p["accent"] if l_active else p["border_subtle"],
            highlightthickness=1,
        )

        for r_idx, row in enumerate(self.key_items):
            for c_idx in range(len(row)):
                self.update_key_cell(r_idx, c_idx, active=(r_idx == self.cur_row and c_idx == self.cur_col))

    def show(self):
        if self.visible:
            return
        self.visible = True
        self._cancel_timers()
        self._cancel_popup()
        if self._on_consume_buttons:
            self._on_consume_buttons()

        self.apply_theme()
        self._refresh_metrics()
        target_y = self._target_y()
        scr_h = self.root.winfo_screenheight()
        start_y = -self._kb_h - 10 if self.config["keyboard_at_top"] else scr_h + 10

        # Do NOT banish cursor to (scr_w+500, scr_h+500) (which breaks Netflix hover/focus).
        # Only nudge cursor slightly above/below the keyboard if it happens to overlap the overlay rectangle.
        pos = get_cursor_pos()
        if pos is not None:
            cx, cy = pos
            if (self._kb_x <= cx <= self._kb_x + self._kb_w) and (target_y <= cy <= target_y + self._kb_h):
                nudge_y = (target_y + self._kb_h + 18) if self.config["keyboard_at_top"] else max(16, target_y - 18)
                set_cursor_pos(cx, nudge_y)

        apply_dwm_window_theme(self.win, self.config["theme"], corner_round=True)
        self.synth.focus_guard.show_noactivate_topmost(self.win, self._kb_x, start_y, self._kb_w, self._kb_h)
        self._animate_y(start_y, target_y, 130)
        if self._on_state_change:
            self._on_state_change()

    def hide(self, reason="manual"):
        if not self.visible:
            return
        self.visible = False
        self._cancel_timers()
        self._cancel_popup()
        if self._on_consume_buttons:
            self._on_consume_buttons()
        if reason in ("b_button", "close_button"):
            self.audio.play_back()

        start_y = self._target_y()
        scr_h = self.root.winfo_screenheight()
        end_y = -self._kb_h - 10 if self.config["keyboard_at_top"] else scr_h + 10
        self._animate_y(
            start_y,
            end_y,
            105,
            on_done=lambda: self.win.withdraw() if not self.visible else None,
        )
        if self._on_state_change:
            self._on_state_change()

    def toggle_position(self):
        old_y = self._target_y()
        self.config.set_and_save("keyboard_at_top", not self.config["keyboard_at_top"])
        new_y = self._target_y()
        self.apply_theme()
        self.audio.play_nav()
        if self.visible:
            self._cancel_timers()
            self._animate_y(old_y, new_y, 145)
        if self._on_state_change:
            self._on_state_change()

    def cycle_shift_state(self):
        """Cycle lower -> shift (1-shot) -> caps (locked) -> lower."""
        if self.layer == "lower":
            self.layer = "shift"
            self.audio.play_press()
        elif self.layer == "shift":
            self.layer = "caps"
            self.audio.play_press()
        else:
            self.layer = "lower"
            self.audio.play_back()
        self.apply_theme()

    def toggle_symbols_layer(self):
        """Toggle between symbols (#+=) and alphabetical layers."""
        if self.layer == "symbols":
            self.layer = "lower"
            self.audio.play_back()
        else:
            self.layer = "symbols"
            self.audio.play_press()
        self.apply_theme()

    def press_backspace(self):
        self.audio.play_back()
        self.synth.send_vk_key(VK_BACK)

    def press_space(self):
        self.audio.play_press()
        self.synth.send_vk_key(VK_SPACE)

    def move_text_cursor(self, direction):
        self.audio.play_nav()
        self.synth.send_vk_key(VK_LEFT if direction < 0 else VK_RIGHT, extended=True)

    def submit_and_close(self):
        self.audio.play_press()
        self.synth.send_vk_key(VK_RETURN)
        if self._enter_hide_id is not None:
            try:
                self.root.after_cancel(self._enter_hide_id)
            except Exception:
                pass
        self._enter_hide_id = self.root.after(75, lambda: self.hide(reason="enter"))

    def press_current_key(self):
        grid = self._current_grid()
        val = grid[self.cur_row][self.cur_col]

        r_snap, c_snap = self.cur_row, self.cur_col
        self.update_key_cell(r_snap, c_snap, active=True, flash=True)
        self._show_key_preview_popup(r_snap, c_snap, val)
        self.root.after(
            95,
            lambda: self.update_key_cell(
                r_snap,
                c_snap,
                active=(r_snap == self.cur_row and c_snap == self.cur_col),
                flash=False,
            ),
        )

        if val == "Borrar":
            self.press_backspace()
        elif val == "Enter":
            self.submit_and_close()
        elif val == "Espacio":
            self.press_space()
        elif val in ("Mayus", "CAPS"):
            self.cycle_shift_state()
        elif val in ("#+=", "ABC"):
            self.toggle_symbols_layer()
        elif val == "<":
            self.move_text_cursor(-1)
        elif val == ">":
            self.move_text_cursor(1)
        elif r_snap == 4 and c_snap in (2, 3):
            self.audio.play_press()
            self.synth.send_text(val)
        else:
            self.audio.play_press()
            self.synth.send_char(val)
            # Auto-return from 1-shot shift to lowercase after typing one character
            if self.layer == "shift":
                self.layer = "lower"
                self.apply_theme()

    def move_selection(self, d_row, d_col):
        grid = self._current_grid()
        prev_r, prev_c = self.cur_row, self.cur_col

        if d_row != 0:
            cur_span = self.key_items[self.cur_row][self.cur_col]["span"]
            anchor_col = self.saved_col if self.cur_row == 4 else cur_span[0]
            self.cur_row = (self.cur_row + d_row) % len(grid)
            row_cells = self.key_items[self.cur_row]
            best_c = 0
            for idx, cell in enumerate(row_cells):
                c_start, c_end = cell["span"]
                if c_start <= anchor_col < c_end:
                    best_c = idx
                    break
            self.cur_col = best_c
        elif d_col != 0:
            max_cols = len(grid[self.cur_row])
            if max_cols > 1:
                self.cur_col = (self.cur_col + d_col) % max_cols
                self.saved_col = self.key_items[self.cur_row][self.cur_col]["span"][0]

        if (prev_r, prev_c) != (self.cur_row, self.cur_col):
            self.update_key_cell(prev_r, prev_c, active=False)
            self.update_key_cell(self.cur_row, self.cur_col, active=True)
            self.audio.play_nav()
