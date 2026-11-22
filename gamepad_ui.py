import tkinter as tk
from input_synth import ACTION_LABELS, ACTIONS
from rover_system import DEFAULT_BUTTON_MAP
from ui_theme import (
    THEMES,
    MonoButton,
    apply_dwm_window_theme,
    center_window_on_parent,
    mono_font,
    ui_font,
)

BUTTON_LABELS = {
    "A": "Boton A (Inferior)",
    "B": "Boton B (Derecha)",
    "X": "Boton X (Izquierda)",
    "Y": "Boton Y (Superior)",
    "LB": "Bumper izquierdo (LB)",
    "RB": "Bumper derecho (RB)",
    "LT": "Gatillo analogico (LT)",
    "RT": "Gatillo analogico (RT)",
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
    """Interactive Nordic Cockpit gamepad schematic with live sticks, D-Pad, View/Home indicators, and auto-select on press."""

    W = 560
    H = 216

    L3_CX, L3_CY = 156, 98
    R3_CX, R3_CY = 348, 142
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
        self._system_items = {}
        self._body_shape = None
        self._ring_shapes = []
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

    def set_live_state(self, pressed_set, stick_axes=(0, 0, 0, 0), auto_select_pressed=True):
        new_pressed = set(pressed_set)
        just_down = new_pressed - self._pressed
        if new_pressed != self._pressed:
            self._pressed = new_pressed
            if auto_select_pressed and just_down:
                for bid in BUTTON_ORDER:
                    if bid in just_down and bid != self._selected:
                        self._selected = bid
                        if self._on_select:
                            self._on_select(bid)
                        break
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
        for bid, x1, x2 in (("LT", 124, 184), ("RT", 374, 434)):
            sh = self.create_polygon(_rounded_poly(x1, 10, x2, 34, 8), smooth=True, splinesteps=16, width=1)
            tx = self.create_text((x1 + x2) / 2, 22, text=bid, font=mono_font(8, "bold"))
            self._register_btn(bid, [sh], [tx])

        for bid, x1, x2 in (("LB", 110, 198), ("RB", 360, 448)):
            sh = self.create_polygon(_rounded_poly(x1, 38, x2, 58, 8), smooth=True, splinesteps=16, width=1)
            tx = self.create_text((x1 + x2) / 2, 48, text=bid, font=mono_font(8, "bold"))
            self._register_btn(bid, [sh], [tx])

        body_pts = [
            146, 58,
            414, 58,
            460, 72,
            490, 136,
            498, 194,
            472, 216,
            428, 208,
            390, 168,
            170, 168,
            132, 208,
            88, 216,
            62, 194,
            70, 136,
            100, 72,
        ]
        self._body_shape = self.create_polygon(body_pts, smooth=True, splinesteps=24, width=2)

        # Left stick (L3)
        l3_ring = self.create_oval(self.L3_CX - 25, self.L3_CY - 25, self.L3_CX + 25, self.L3_CY + 25, width=1)
        l3_cap = self.create_oval(
            self.L3_CX - self.STICK_R,
            self.L3_CY - self.STICK_R,
            self.L3_CX + self.STICK_R,
            self.L3_CY + self.STICK_R,
            width=1,
        )
        l3_tx = self.create_text(self.L3_CX, self.L3_CY, text="L3", font=mono_font(8, "bold"))
        self._ring_shapes.append(l3_ring)
        self._register_btn("L3", [l3_cap], [l3_tx])

        # Interactive 4-way D-Pad
        dcx, dcy = 208, 150
        arm_w, arm_l = 16, 18
        dpad_arms = [
            ("D_UP", dcx - arm_w // 2, dcy - arm_w // 2 - arm_l, dcx + arm_w // 2, dcy - arm_w // 2, "^"),
            ("D_DOWN", dcx - arm_w // 2, dcy + arm_w // 2, dcx + arm_w // 2, dcy + arm_w // 2 + arm_l, "v"),
            ("D_LEFT", dcx - arm_w // 2 - arm_l, dcy - arm_w // 2, dcx - arm_w // 2, dcy + arm_w // 2, "<"),
            ("D_RIGHT", dcx + arm_w // 2, dcy - arm_w // 2, dcx + arm_w // 2 + arm_l, dcy + arm_w // 2, ">"),
        ]
        d_hub = self.create_rectangle(dcx - arm_w // 2, dcy - arm_w // 2, dcx + arm_w // 2, dcy + arm_w // 2, width=1)
        self._ring_shapes.append(d_hub)
        for bid, x1, y1, x2, y2, glyph in dpad_arms:
            rect = self.create_rectangle(x1, y1, x2, y2, width=1)
            tx = self.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=glyph, font=mono_font(8, "bold"))
            self._register_btn(bid, [rect], [tx])

        # System buttons (- / VIEW and H / HOME) with live press highlighting
        view_btn = self.create_oval(230, 92, 248, 110, width=1)
        view_tx = self.create_text(239, 101, text="-", font=mono_font(9, "bold"))
        self._system_items["VIEW"] = (view_btn, view_tx)

        home_btn = self.create_oval(266, 76, 294, 104, width=1)
        home_tx = self.create_text(280, 90, text="H", font=mono_font(8, "bold"))
        self._system_items["HOME"] = (home_btn, home_tx)

        start_btn = self.create_oval(310, 92, 328, 110, width=1)
        start_tx = self.create_text(319, 101, text="+", font=mono_font(9, "bold"))
        self._register_btn("START", [start_btn], [start_tx])

        # Right stick (R3)
        r3_ring = self.create_oval(self.R3_CX - 25, self.R3_CY - 25, self.R3_CX + 25, self.R3_CY + 25, width=1)
        r3_cap = self.create_oval(
            self.R3_CX - self.STICK_R,
            self.R3_CY - self.STICK_R,
            self.R3_CX + self.STICK_R,
            self.R3_CY + self.STICK_R,
            width=1,
        )
        r3_tx = self.create_text(self.R3_CX, self.R3_CY, text="R3", font=mono_font(8, "bold"))
        self._ring_shapes.append(r3_ring)
        self._register_btn("R3", [r3_cap], [r3_tx])

        for bid, cx, cy in (("Y", 402, 82), ("X", 380, 103), ("B", 424, 103), ("A", 402, 124)):
            ov = self.create_oval(cx - 12, cy - 12, cx + 12, cy + 12, width=1)
            tx = self.create_text(cx, cy, text=bid, font=mono_font(8, "bold"))
            self._register_btn(bid, [ov], [tx])

        self._legend_left = self.create_text(
            14,
            202,
            text="Clic o pulsa boton en el mando",
            anchor="w",
            font=ui_font(8),
        )
        self._legend_right = self.create_text(
            self.W - 14,
            202,
            text="2x (-)/H: Modo | R-Stick: Scroll",
            anchor="e",
            font=ui_font(8),
        )
        self._static_texts.extend([self._legend_left, self._legend_right])

    def apply_theme(self, palette):
        self._palette = palette
        surf = palette.get("surface", palette["bg"])
        border = palette["accent"] if self._focused else palette["border_subtle"]
        self.configure(
            bg=surf,
            highlightbackground=border,
            highlightcolor=palette["accent"],
            highlightthickness=2 if self._focused else 1,
        )
        if self._body_shape is not None:
            self.itemconfig(self._body_shape, fill=palette["bg"], outline=palette["border_strong"])
        for sh in self._ring_shapes:
            self.itemconfig(sh, fill=surf, outline=palette["border_subtle"])
        for tx in self._static_texts:
            self.itemconfig(tx, fill=palette["fg_secondary"])
        self._refresh_styles()

    def _refresh_styles(self):
        p = self._palette
        for sys_id, (sh, tx) in self._system_items.items():
            active = sys_id in self._pressed
            self.itemconfig(
                sh,
                fill=p["accent"] if active else p["elevated"],
                outline=p["accent"] if active else p["border_strong"],
                width=2 if active else 1,
            )
            self.itemconfig(tx, fill=p["accent_fg"] if active else p["fg_secondary"])

        for bid, items in self._btn_items.items():
            is_pressed = bid in self._pressed
            is_selected = bid == self._selected
            if is_pressed:
                fill = p["accent"]
                fg = p["accent_fg"]
                outline = p["fg"] if is_selected else p["accent"]
                width = 2
            elif is_selected:
                fill = p["fg"]
                fg = p["bg"]
                outline = p["accent"]
                width = 2
            else:
                fill = p["elevated"]
                fg = p["fg"]
                outline = p["border_strong"]
                width = 1
            for sh in items["shapes"]:
                self.itemconfig(sh, fill=fill, outline=outline, width=width)
            for tx in items["texts"]:
                self.itemconfig(tx, fill=fg)


class ActionPickerModal(tk.Toplevel):
    """Keyboard-accessible Nordic Cockpit modal to pick a mapped action for a gamepad button."""

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

        outer = tk.Frame(
            self,
            bg=p["surface"],
            padx=18,
            pady=16,
            highlightthickness=1,
            highlightbackground=p["border_strong"],
        )
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        hdr = tk.Frame(outer, bg=p["surface"])
        hdr.pack(fill="x")
        badge = tk.Label(hdr, text=button_id, font=mono_font(9, "bold"), bg=p["accent"], fg=p["accent_fg"], padx=8, pady=2)
        badge.pack(side="left", padx=(0, 10))
        tk.Label(
            hdr,
            text=BUTTON_LABELS.get(button_id, button_id),
            font=ui_font(12, "bold"),
            bg=p["surface"],
            fg=p["fg"],
            anchor="w",
        ).pack(side="left", fill="x")

        tk.Label(
            outer,
            text="Elige la accion que ejecutara este boton en Modo Mouse (Esc para cancelar):",
            font=ui_font(9),
            bg=p["surface"],
            fg=p["fg_secondary"],
            anchor="w",
        ).pack(fill="x", pady=(6, 10))

        grid = tk.Frame(outer, bg=p["surface"])
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
                width=28,
                padx=8,
                pady=4,
                font_size=9,
            )
            btn.apply_theme(p)
            btn.grid(row=r, column=c, padx=4, pady=2, sticky="ew")
            self._btns.append((act_id, btn))

        footer = tk.Frame(outer, bg=p["surface"])
        footer.pack(fill="x", pady=(12, 0))
        b_cancel = MonoButton(footer, "Cancelar", command=self.destroy, padx=14, pady=5)
        b_cancel.apply_theme(p)
        b_cancel.pack(side="right")

        self.bind("<Escape>", lambda _e: self.destroy())
        center_window_on_parent(self, parent_win)

        target_btn = next((b for a, b in self._btns if a == current_action), self._btns[0][1])
        target_btn.focus_set()

    def _select(self, act_id):
        if self._on_pick:
            self._on_pick(act_id)
        self.destroy()
