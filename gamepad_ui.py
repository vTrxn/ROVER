import tkinter as tk
from ui_theme import MonoButton, THEMES, apply_dwm_window_theme, font_tuple

DEFAULT_BUTTON_MAP = {
    "A": "left_click",
    "B": "right_click",
    "X": "show_keyboard",
    "Y": "none",
    "LB": "none",
    "RB": "none",
    "LT": "precision",
    "RT": "browser_back",
    "L3": "play_pause",
    "R3": "none",
    "START": "none",
    "D_UP": "scroll_up",
    "D_DOWN": "scroll_down",
    "D_LEFT": "scroll_left",
    "D_RIGHT": "scroll_right",
}

BUTTON_LABELS = {
    "A": "Boton A (Abajo)",
    "B": "Boton B (Derecha)",
    "X": "Boton X (Izquierda)",
    "Y": "Boton Y (Arriba)",
    "LB": "Gatillo superior LB",
    "RB": "Gatillo superior RB",
    "LT": "Gatillo analogico LT",
    "RT": "Gatillo analogico RT",
    "L3": "Clic stick izquierdo (L3)",
    "R3": "Clic stick derecho (R3)",
    "START": "Boton Menu / Start (+)",
    "D_UP": "D-Pad Arriba",
    "D_DOWN": "D-Pad Abajo",
    "D_LEFT": "D-Pad Izquierda",
    "D_RIGHT": "D-Pad Derecha",
}

BUTTON_ORDER = [
    "A", "B", "X", "Y",
    "LB", "RB", "LT", "RT",
    "L3", "R3", "START",
    "D_UP", "D_DOWN", "D_LEFT", "D_RIGHT",
]

ACTIONS = [
    ("left_click", "Clic izquierdo (mantener)"),
    ("right_click", "Clic derecho (mantener)"),
    ("middle_click", "Clic central (rueda)"),
    ("double_click", "Doble clic izquierdo"),
    ("precision", "Modo precision (mantener)"),
    ("show_keyboard", "Abrir / cerrar teclado"),
    ("scroll_up", "Scroll arriba (mantener)"),
    ("scroll_down", "Scroll abajo (mantener)"),
    ("scroll_left", "Scroll izquierda (mantener)"),
    ("scroll_right", "Scroll derecha (mantener)"),
    ("browser_back", "Atras (Alt + Izq)"),
    ("browser_forward", "Adelante (Alt + Der)"),
    ("play_pause", "Play / Pausa multimedia"),
    ("vol_up", "Subir volumen"),
    ("vol_down", "Bajar volumen"),
    ("vol_mute", "Silenciar audio"),
    ("copy", "Copiar (Ctrl + C)"),
    ("paste", "Pegar (Ctrl + V)"),
    ("close_tab", "Cerrar pestana (Ctrl + W)"),
    ("zoom_in", "Zoom + (Ctrl + +)"),
    ("zoom_out", "Zoom - (Ctrl + -)"),
    ("win_tab", "Vista de tareas (Win + Tab)"),
    ("alt_tab", "Cambiar ventana (Alt + Tab)"),
    ("enter", "Tecla Enter"),
    ("escape", "Tecla Escape"),
    ("none", "Sin asignar"),
]

ACTION_LABELS = dict(ACTIONS)


def _rounded_poly(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x2 - r, y1,
        x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r,
        x1, y1 + r, x1, y1,
    ]


class GamepadDiagram(tk.Canvas):
    """Interactive 2-color gamepad schematic with live sticks, D-Pad, press states, and selection."""

    W = 540
    H = 228

    L3_CX, L3_CY = 150, 102
    R3_CX, R3_CY = 340, 148
    STICK_R = 16
    STICK_TRAVEL = 9

    def __init__(self, parent, selected_btn="A", on_select=None):
        super().__init__(parent, width=self.W, height=self.H, highlightthickness=1, bd=0, takefocus=1, cursor="hand2")
        self._selected = selected_btn
        self._on_select = on_select
        self._pressed = set()
        self._stick_axes = (0, 0, 0, 0)
        self._palette = THEMES["dark"]
        self._focused = False
        self._btn_items = {}
        self._static_shapes = []
        self._static_texts = []

        self._build_schematic()
        self.bind("<FocusIn>", lambda _e: self._set_focus(True))
        self.bind("<FocusOut>", lambda _e: self._set_focus(False))
        self.bind("<Left>", lambda _e: self._step_select(-1))
        self.bind("<Right>", lambda _e: self._step_select(1))
        self.bind("<Up>", lambda _e: self._step_select(-1))
        self.bind("<Down>", lambda _e: self._step_select(1))

    def _set_focus(self, val):
        self._focused = val
        self.apply_theme(self._palette)

    def _step_select(self, delta):
        if self._selected in BUTTON_ORDER:
            idx = (BUTTON_ORDER.index(self._selected) + delta) % len(BUTTON_ORDER)
            self.set_selected(BUTTON_ORDER[idx], notify=True)

    def set_selected(self, btn_id, notify=False):
        if btn_id not in BUTTON_ORDER:
            return
        self._selected = btn_id
        self._refresh_styles()
        if notify and self._on_select:
            self._on_select(btn_id)

    def set_live_state(self, pressed_set, stick_axes=(0, 0, 0, 0)):
        if pressed_set != self._pressed:
            self._pressed = set(pressed_set)
            self._refresh_styles()
        if stick_axes != self._stick_axes:
            self._stick_axes = stick_axes
            self._update_stick_positions()

    def _update_stick_positions(self):
        lx, ly, rx, ry = self._stick_axes
        dx_l = (lx / 32767.0) * self.STICK_TRAVEL
        dy_l = -(ly / 32767.0) * self.STICK_TRAVEL
        dx_r = (rx / 32767.0) * self.STICK_TRAVEL
        dy_r = -(ry / 32767.0) * self.STICK_TRAVEL

        for bid, cx, cy, dx, dy in (
            ("L3", self.L3_CX, self.L3_CY, dx_l, dy_l),
            ("R3", self.R3_CX, self.R3_CY, dx_r, dy_r),
        ):
            r = self.STICK_R
            nx, ny = cx + dx, cy + dy
            self.coords(self._btn_items[bid]["shapes"][0], nx - r, ny - r, nx + r, ny + r)
            self.coords(self._btn_items[bid]["texts"][0], nx, ny)

    def _register_btn(self, btn_id, shapes, texts):
        self._btn_items[btn_id] = {"shapes": shapes, "texts": texts}
        for item_id in shapes + texts:
            self.tag_bind(item_id, "<Button-1>", lambda _e, b=btn_id: self.set_selected(b, notify=True))

    def _build_schematic(self):
        for bid, x1, x2 in (("LT", 118, 178), ("RT", 362, 422)):
            sh = self.create_polygon(_rounded_poly(x1, 10, x2, 34, 8), smooth=True, splinesteps=16, width=1)
            tx = self.create_text((x1 + x2) / 2, 22, text=bid, font=font_tuple(8, "bold"))
            self._register_btn(bid, [sh], [tx])

        for bid, x1, x2 in (("LB", 104, 192), ("RB", 348, 436)):
            sh = self.create_polygon(_rounded_poly(x1, 38, x2, 58, 8), smooth=True, splinesteps=16, width=1)
            tx = self.create_text((x1 + x2) / 2, 48, text=bid, font=font_tuple(8, "bold"))
            self._register_btn(bid, [sh], [tx])

        body_pts = [
            140, 58,
            400, 58,
            446, 72,
            476, 134,
            484, 192,
            458, 214,
            416, 206,
            378, 166,
            162, 166,
            124, 206,
            82, 214,
            56, 192,
            64, 134,
            94, 72,
        ]
        body = self.create_polygon(body_pts, smooth=True, splinesteps=24, width=2)
        self._static_shapes.append(body)

        # Left stick (L3)
        l3_ring = self.create_oval(self.L3_CX - 24, self.L3_CY - 24, self.L3_CX + 24, self.L3_CY + 24, width=1)
        l3_cap = self.create_oval(
            self.L3_CX - self.STICK_R, self.L3_CY - self.STICK_R,
            self.L3_CX + self.STICK_R, self.L3_CY + self.STICK_R,
            width=1,
        )
        l3_tx = self.create_text(self.L3_CX, self.L3_CY, text="L3", font=font_tuple(8, "bold"))
        self._static_shapes.append(l3_ring)
        self._register_btn("L3", [l3_cap], [l3_tx])

        # Interactive 4-way D-Pad
        dcx, dcy = 200, 148
        arm_w, arm_l = 16, 18
        dpad_arms = [
            ("D_UP", dcx - arm_w // 2, dcy - arm_w // 2 - arm_l, dcx + arm_w // 2, dcy - arm_w // 2, "^"),
            ("D_DOWN", dcx - arm_w // 2, dcy + arm_w // 2, dcx + arm_w // 2, dcy + arm_w // 2 + arm_l, "v"),
            ("D_LEFT", dcx - arm_w // 2 - arm_l, dcy - arm_w // 2, dcx - arm_w // 2, dcy + arm_w // 2, "<"),
            ("D_RIGHT", dcx + arm_w // 2, dcy - arm_w // 2, dcx + arm_w // 2 + arm_l, dcy + arm_w // 2, ">"),
        ]
        d_hub = self.create_rectangle(dcx - arm_w // 2, dcy - arm_w // 2, dcx + arm_w // 2, dcy + arm_w // 2, width=1)
        self._static_shapes.append(d_hub)
        for bid, x1, y1, x2, y2, glyph in dpad_arms:
            rect = self.create_rectangle(x1, y1, x2, y2, width=1)
            tx = self.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=glyph, font=font_tuple(7, "bold"))
            self._register_btn(bid, [rect], [tx])

        # Center controls
        view_btn = self.create_oval(222, 92, 240, 110, width=1)
        view_tx = self.create_text(231, 101, text="-", font=font_tuple(9, "bold"))
        home_btn = self.create_oval(256, 76, 284, 104, width=1)
        home_tx = self.create_text(270, 90, text="H", font=font_tuple(8, "bold"))
        self._static_shapes.extend([view_btn, home_btn])
        self._static_texts.extend([view_tx, home_tx])

        start_btn = self.create_oval(300, 92, 318, 110, width=1)
        start_tx = self.create_text(309, 101, text="+", font=font_tuple(9, "bold"))
        self._register_btn("START", [start_btn], [start_tx])

        # Right stick (R3)
        r3_ring = self.create_oval(self.R3_CX - 24, self.R3_CY - 24, self.R3_CX + 24, self.R3_CY + 24, width=1)
        r3_cap = self.create_oval(
            self.R3_CX - self.STICK_R, self.R3_CY - self.STICK_R,
            self.R3_CX + self.STICK_R, self.R3_CY + self.STICK_R,
            width=1,
        )
        r3_tx = self.create_text(self.R3_CX, self.R3_CY, text="R3", font=font_tuple(8, "bold"))
        self._static_shapes.append(r3_ring)
        self._register_btn("R3", [r3_cap], [r3_tx])

        for bid, cx, cy in (("Y", 390, 82), ("X", 368, 102), ("B", 412, 102), ("A", 390, 122)):
            ov = self.create_oval(cx - 11, cy - 11, cx + 11, cy + 11, width=1)
            tx = self.create_text(cx, cy, text=bid, font=font_tuple(8, "bold"))
            self._register_btn(bid, [ov], [tx])

        self._legend_left = self.create_text(14, 212, text="Clic en boton/D-Pad para asignar", anchor="w", font=font_tuple(8))
        self._legend_right = self.create_text(self.W - 14, 212, text="-/H: Modo | Stick der: Scroll", anchor="e", font=font_tuple(8))
        self._static_texts.extend([self._legend_left, self._legend_right])

    def apply_theme(self, palette):
        self._palette = palette
        self.configure(
            bg=palette["bg"],
            highlightbackground=palette["fg"],
            highlightcolor=palette["fg"],
            highlightthickness=2 if self._focused else 1,
        )
        for sh in self._static_shapes:
            self.itemconfig(sh, fill=palette["bg"], outline=palette["fg"])
        for tx in self._static_texts:
            self.itemconfig(tx, fill=palette["fg"])
        self._refresh_styles()

    def _refresh_styles(self):
        p = self._palette
        for bid, items in self._btn_items.items():
            is_pressed = bid in self._pressed
            is_selected = bid == self._selected
            inverted = is_pressed or is_selected
            fill = p["fg"] if inverted else p["bg"]
            fg = p["bg"] if inverted else p["fg"]
            width = 3 if (is_selected and is_pressed) else (2 if is_selected else 1)
            for sh in items["shapes"]:
                self.itemconfig(sh, fill=fill, outline=p["fg"], width=width)
            for tx in items["texts"]:
                self.itemconfig(tx, fill=fg)


class ActionPickerModal(tk.Toplevel):
    """Keyboard-accessible 2-color modal to pick a mapped action for a gamepad button."""

    def __init__(self, parent_win, button_id, current_action, theme_name, on_pick):
        super().__init__(parent_win)
        self._on_pick = on_pick
        p = THEMES.get(theme_name, THEMES["dark"])

        self.title(f"Asignar {BUTTON_LABELS.get(button_id, button_id)}")
        self.transient(parent_win)
        self.grab_set()
        self.resizable(False, False)
        self.configure(bg=p["bg"])
        apply_dwm_window_theme(self, theme_name)

        outer = tk.Frame(self, bg=p["bg"], padx=16, pady=14, highlightthickness=1, highlightbackground=p["fg"])
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(
            outer,
            text=BUTTON_LABELS.get(button_id, button_id),
            font=font_tuple(11, "bold"),
            bg=p["bg"],
            fg=p["fg"],
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text="Elige la accion en Modo Mouse (Esc para cancelar):",
            font=font_tuple(8),
            bg=p["bg"],
            fg=p["fg"],
            anchor="w",
        ).pack(fill="x", pady=(2, 8))

        grid = tk.Frame(outer, bg=p["bg"])
        grid.pack(fill="both", expand=True)

        self._btns = []
        for idx, (act_id, act_label) in enumerate(ACTIONS):
            r, c = divmod(idx, 2)
            is_cur = act_id == current_action
            btn = MonoButton(
                grid,
                act_label,
                command=lambda a=act_id: self._select(a),
                primary=is_cur,
                width=27,
                padx=8,
                pady=4,
                font_size=8,
            )
            btn.apply_theme(p)
            btn.grid(row=r, column=c, padx=4, pady=2, sticky="ew")
            self._btns.append((act_id, btn))

        footer = tk.Frame(outer, bg=p["bg"])
        footer.pack(fill="x", pady=(10, 0))
        b_cancel = MonoButton(footer, "Cancelar", command=self.destroy, padx=14, pady=4)
        b_cancel.apply_theme(p)
        b_cancel.pack(side="right")

        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        px = parent_win.winfo_x() + max(0, (parent_win.winfo_width() - self.winfo_width()) // 2)
        py = parent_win.winfo_y() + max(0, (parent_win.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        target_btn = next((b for a, b in self._btns if a == current_action), self._btns[0][1])
        target_btn.focus_set()

    def _select(self, act_id):
        if self._on_pick:
            self._on_pick(act_id)
        self.destroy()
