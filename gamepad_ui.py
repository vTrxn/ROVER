import math
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk
from input_synth import ACTION_LABELS, ACTIONS
from rover_system import DEFAULT_BUTTON_MAP
from ui_theme import (
    THEMES,
    MonoButton,
    apply_dwm_window_theme,
    center_window_on_parent,
    dp,
    get_dpi_scale,
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


def _catmull_rom_closed(pts, samples_per_seg=14):
    """Interpolate a closed smooth curve through control points for crisp controller ergonomics."""
    n = len(pts)
    out = []
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        for s in range(samples_per_seg):
            t = s / float(samples_per_seg)
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * (
                (2.0 * p1[0])
                + (-p0[0] + p2[0]) * t
                + (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t2
                + (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t3
            )
            y = 0.5 * (
                (2.0 * p1[1])
                + (-p0[1] + p2[1]) * t
                + (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2
                + (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3
            )
            out.append((x, y))
    return out


class GamepadDiagram(tk.Canvas):
    """High-DPI anti-aliased 2-color gamepad schematic with live sticks, D-Pad, press states, and selection."""

    BASE_W = 560
    BASE_H = 252

    L3_BASE = (156, 108)
    R3_BASE = (344, 150)
    STICK_R_BASE = 15
    STICK_TRAVEL_BASE = 8

    def __init__(self, parent, selected_btn="A", on_select=None):
        self.W = dp(self.BASE_W)
        self.H = dp(self.BASE_H)
        self.L3_CX, self.L3_CY = dp(self.L3_BASE[0]), dp(self.L3_BASE[1])
        self.R3_CX, self.R3_CY = dp(self.R3_BASE[0]), dp(self.R3_BASE[1])
        self.STICK_R = dp(self.STICK_R_BASE)
        self.STICK_TRAVEL = dp(self.STICK_TRAVEL_BASE)

        super().__init__(parent, width=self.W, height=self.H, highlightthickness=1, bd=0, takefocus=1, cursor="hand2")
        self._selected = selected_btn
        self._on_select = on_select
        self._pressed = set()
        self._stick_axes = (0, 0, 0, 0)
        self._palette = THEMES["dark"]
        self._focused = False
        self._btn_items = {}
        self._system_items = {}
        self._ring_shapes = []
        self._static_texts = []
        self._bg_photo = None
        self._bg_item = None

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

    def _render_aa_background(self, palette):
        """Render controller silhouette & stick wells at 3x supersampling via Pillow for zero jagged edges."""
        ss = 3
        s = get_dpi_scale() * ss
        iw, ih = self.W * ss, self.H * ss
        surf = palette.get("surface", palette["bg"])
        img = Image.new("RGBA", (iw, ih), surf)
        draw = ImageDraw.Draw(img)

        # Clean ergonomic Xbox/GameSir Pro contour (fits y=60..210, leaving y=224..250 clear for legends)
        ctrl_pts = [
            (170, 62),
            (280, 60),
            (390, 62),
            (442, 72),
            (474, 108),
            (494, 168),
            (486, 204),
            (456, 212),
            (416, 194),
            (382, 174),
            (280, 172),
            (178, 174),
            (144, 194),
            (104, 212),
            (74, 204),
            (66, 168),
            (86, 108),
            (118, 72),
        ]
        smooth_pts = [(x * s, y * s) for x, y in _catmull_rom_closed(ctrl_pts, samples_per_seg=16)]
        draw.polygon(smooth_pts, fill=palette["bg"])
        draw.line(smooth_pts + [smooth_pts[0]], fill=palette["border_strong"], width=max(2, int(round(2.2 * s))), joint="curve")

        # Recessed stick wells for L3 and R3
        for cx_b, cy_b in (self.L3_BASE, self.R3_BASE):
            r = 25 * s
            cx, cy = cx_b * s, cy_b * s
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=surf, outline=palette["border_subtle"], width=max(1, int(round(1.4 * s))))

        # Subtle center divider rule above legend footer
        ly = 224 * s
        draw.line([(16 * s, ly), (iw - 16 * s, ly)], fill=palette["border_subtle"], width=max(1, int(round(1.0 * s))))

        down = img.resize((self.W, self.H), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(down)

    def _build_schematic(self):
        self._bg_item = self.create_image(0, 0, anchor="nw")

        # Triggers LT / RT
        for bid, x1, x2 in (("LT", 126, 186), ("RT", 374, 434)):
            sh = self.create_rectangle(dp(x1), dp(12), dp(x2), dp(33), width=1)
            tx = self.create_text(dp((x1 + x2) / 2), dp(22.5), text=bid, font=mono_font(8, "bold"))
            self._register_btn(bid, [sh], [tx])

        # Bumpers LB / RB
        for bid, x1, x2 in (("LB", 112, 200), ("RB", 360, 448)):
            sh = self.create_rectangle(dp(x1), dp(37), dp(x2), dp(57), width=1)
            tx = self.create_text(dp((x1 + x2) / 2), dp(47), text=bid, font=mono_font(8, "bold"))
            self._register_btn(bid, [sh], [tx])

        # Left stick cap (L3)
        l3_cap = self.create_oval(
            self.L3_CX - self.STICK_R,
            self.L3_CY - self.STICK_R,
            self.L3_CX + self.STICK_R,
            self.L3_CY + self.STICK_R,
            width=1,
        )
        l3_tx = self.create_text(self.L3_CX, self.L3_CY, text="L3", font=mono_font(8, "bold"))
        self._register_btn("L3", [l3_cap], [l3_tx])

        # Interactive 4-way D-Pad
        dcx, dcy = dp(212), dp(148)
        arm_w, arm_l = dp(16), dp(17)
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

        # Center system buttons (- / VIEW, H / HOME, + / START)
        view_btn = self.create_oval(dp(234), dp(96), dp(252), dp(114), width=1)
        view_tx = self.create_text(dp(243), dp(105), text="-", font=mono_font(9, "bold"))
        self._system_items["VIEW"] = (view_btn, view_tx)

        home_btn = self.create_oval(dp(266), dp(80), dp(294), dp(108), width=1)
        home_tx = self.create_text(dp(280), dp(94), text="H", font=mono_font(8, "bold"))
        self._system_items["HOME"] = (home_btn, home_tx)

        start_btn = self.create_oval(dp(308), dp(96), dp(326), dp(114), width=1)
        start_tx = self.create_text(dp(317), dp(105), text="+", font=mono_font(9, "bold"))
        self._register_btn("START", [start_btn], [start_tx])

        # Right stick cap (R3)
        r3_cap = self.create_oval(
            self.R3_CX - self.STICK_R,
            self.R3_CY - self.STICK_R,
            self.R3_CX + self.STICK_R,
            self.R3_CY + self.STICK_R,
            width=1,
        )
        r3_tx = self.create_text(self.R3_CX, self.R3_CY, text="R3", font=mono_font(8, "bold"))
        self._register_btn("R3", [r3_cap], [r3_tx])

        # Face buttons Y, X, B, A
        for bid, cx, cy in (("Y", 404, 86), ("X", 382, 107), ("B", 426, 107), ("A", 404, 128)):
            r = dp(12)
            px, py = dp(cx), dp(cy)
            ov = self.create_oval(px - r, py - r, px + r, py + r, width=1)
            tx = self.create_text(px, py, text=bid, font=mono_font(8, "bold"))
            self._register_btn(bid, [ov], [tx])

        # Clean footer legends well below the controller silhouette
        self._legend_left = self.create_text(
            dp(16),
            dp(238),
            text="Clic o pulsa boton en el mando",
            anchor="w",
            font=ui_font(8),
        )
        self._legend_right = self.create_text(
            self.W - dp(16),
            dp(238),
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
        self._bg_photo = self._render_aa_background(palette)
        self.itemconfig(self._bg_item, image=self._bg_photo)
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
    """Keyboard-accessible matte modal to pick a mapped action for a gamepad button."""

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

        outer = tk.Frame(self, bg=p["surface"], padx=dp(18), pady=dp(16), highlightthickness=1, highlightbackground=p["border_strong"])
        outer.pack(fill="both", expand=True, padx=dp(10), pady=dp(10))

        tk.Label(
            outer,
            text=BUTTON_LABELS.get(button_id, button_id),
            font=ui_font(12, "bold"),
            bg=p["surface"],
            fg=p["fg"],
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text="Elige la accion en Modo Mouse (Esc para cancelar):",
            font=ui_font(8),
            bg=p["surface"],
            fg=p["fg_secondary"],
            anchor="w",
        ).pack(fill="x", pady=(dp(2), dp(10)))

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
                width=29,
                padx=dp(8),
                pady=dp(5),
                font_size=8,
            )
            btn.apply_theme(p)
            btn.grid(row=r, column=c, padx=dp(4), pady=dp(2), sticky="ew")
            self._btns.append((act_id, btn))

        footer = tk.Frame(outer, bg=p["surface"])
        footer.pack(fill="x", pady=(dp(12), 0))
        b_cancel = MonoButton(footer, "Cancelar", command=self.destroy, padx=dp(14), pady=dp(5))
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
