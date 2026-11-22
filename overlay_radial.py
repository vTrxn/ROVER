import math
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk
from input_synth import get_work_area
from rover_system import log_error
from ui_theme import THEMES, apply_dwm_window_theme, dp, get_dpi_scale, load_pil_font

RADIAL_ACTIONS = [
    ("monitor_off", "Monitor", "Apagar pantalla"),
    ("screenshot", "Captura", "Recorte Win + Shift + S"),
    ("keyboard", "Teclado", "Abrir teclado flotante"),
    ("mute", "Silencio", "Silenciar / activar audio"),
    ("suspend", "Suspender", "Suspender equipo"),
    ("close_app", "Cerrar", "Cerrar app (Alt + F4)"),
    ("toggle_mode", "Modo", "Alternar Juego / Mouse"),
    ("settings", "Ajustes", "Abrir configuracion"),
]


class RadialMenu:
    """High-DPI anti-aliased 8-slice radial couch HUD pre-baked with Pillow 3x supersampling."""

    BASE_SIZE = 416
    OUTER_R_BASE = 186
    INNER_R_BASE = 84

    def __init__(self, root, config_store, focus_guard, audio, on_action):
        self.root = root
        self.config = config_store
        self.focus_guard = focus_guard
        self.audio = audio
        self._on_action = on_action

        self.SIZE = dp(self.BASE_SIZE)
        self.visible = False
        self.selected_idx = 0
        self._frames = []
        self._theme_cached = None
        self._img_item = None

        self._build_ui()
        self.apply_theme()
        self.focus_guard.apply_noactivate_style(self.win)
        self.win.withdraw()

    def _palette(self):
        return THEMES.get(self.config["theme"], THEMES["dark"])

    def _build_ui(self):
        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)

        self.canvas = tk.Canvas(
            self.win,
            width=self.SIZE,
            height=self.SIZE,
            highlightthickness=2,
            bd=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)
        self._img_item = self.canvas.create_image(0, 0, anchor="nw")
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Button-1>", self._on_mouse_click)

    @staticmethod
    def _ring_sector_points(cx, cy, r_in, r_out, a1, a2, steps=18):
        pts = []
        for s in range(steps + 1):
            a = a1 + (a2 - a1) * (s / float(steps))
            pts.append((cx + r_out * math.cos(a), cy + r_out * math.sin(a)))
        for s in range(steps, -1, -1):
            a = a1 + (a2 - a1) * (s / float(steps))
            pts.append((cx + r_in * math.cos(a), cy + r_in * math.sin(a)))
        return pts

    def _bake_frames(self, palette):
        """Pre-render all 8 anti-aliased radial states at 3x supersampling for instant zero-lag switching."""
        ss = 3
        s = get_dpi_scale() * ss
        iw = self.SIZE * ss
        cx = cy = iw / 2.0
        r_out = self.OUTER_R_BASE * s
        r_in = self.INNER_R_BASE * s

        f_slice = load_pil_font(int(round(11 * s)), bold=True)
        f_title = load_pil_font(int(round(14 * s)), bold=True)
        f_sub = load_pil_font(int(round(8.5 * s)), bold=False)
        f_hint = load_pil_font(int(round(8 * s)), bold=False)

        n = len(RADIAL_ACTIONS)
        step_deg = 360.0 / n
        gap_deg = 2.6  # Clean gap between segments

        frames = []
        for sel in range(n):
            img = Image.new("RGBA", (iw, iw), palette["bg"])
            d = ImageDraw.Draw(img)

            for idx, (_act_id, short_lbl, _desc) in enumerate(RADIAL_ACTIONS):
                active = idx == sel
                center_deg = -90.0 + idx * step_deg
                a1 = math.radians(center_deg - step_deg / 2.0 + gap_deg / 2.0)
                a2 = math.radians(center_deg + step_deg / 2.0 - gap_deg / 2.0)
                pts = self._ring_sector_points(cx, cy, r_in, r_out, a1, a2, steps=20)

                fill = palette["inv_bg"] if active else palette["elevated"]
                outline = palette["fg"] if active else palette["border_subtle"]
                d.polygon(pts, fill=fill)
                d.line(pts + [pts[0]], fill=outline, width=max(2, int(round((2.2 if active else 1.2) * s))), joint="curve")

                mid_r = (r_in + r_out) / 2.0
                tx = cx + mid_r * math.cos(math.radians(center_deg))
                ty = cy + mid_r * math.sin(math.radians(center_deg))
                txt_col = palette["inv_fg"] if active else palette["fg"]
                d.text((tx, ty), short_lbl, font=f_slice, fill=txt_col, anchor="mm")

            # Clean inner HUD hub
            hub_r = r_in - 6 * s
            d.ellipse(
                [cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r],
                fill=palette["bg"],
                outline=palette["fg"],
                width=max(2, int(round(1.8 * s))),
            )

            _act_id, short_lbl, desc = RADIAL_ACTIONS[sel]
            d.text((cx, cy - 16 * s), short_lbl.upper(), font=f_title, fill=palette["fg"], anchor="mm")
            d.text((cx, cy + 6 * s), desc, font=f_sub, fill=palette["fg_secondary"], anchor="mm")
            d.text((cx, cy + 28 * s), "A / RB: OK   B: Cerrar", font=f_hint, fill=palette["fg_muted"], anchor="mm")

            down = img.resize((self.SIZE, self.SIZE), Image.Resampling.LANCZOS)
            frames.append(ImageTk.PhotoImage(down))
        return frames

    def apply_theme(self):
        p = self._palette()
        apply_dwm_window_theme(self.win, self.config["theme"], corner_round=False)
        self.win.configure(bg=p["bg"])
        self.canvas.configure(
            bg=p["bg"],
            highlightbackground=p["fg"],
            highlightcolor=p["fg"],
        )
        theme_key = self.config["theme"]
        if self._theme_cached != theme_key or not self._frames:
            self._frames = self._bake_frames(p)
            self._theme_cached = theme_key
        self._refresh_slices()

    def _refresh_slices(self):
        if self._frames and self._img_item is not None:
            self.canvas.itemconfig(self._img_item, image=self._frames[self.selected_idx])

    def _idx_from_xy(self, x, y):
        cx = cy = self.SIZE / 2.0
        dx = x - cx
        dy = y - cy
        if math.hypot(dx, dy) < dp(self.INNER_R_BASE) * 0.65:
            return None
        deg = math.degrees(math.atan2(dy, dx))
        rel = (deg + 90.0 + 22.5) % 360.0
        return int(rel // 45.0) % len(RADIAL_ACTIONS)

    def _on_mouse_move(self, evt):
        idx = self._idx_from_xy(evt.x, evt.y)
        if idx is not None:
            self.set_selected(idx)

    def _on_mouse_click(self, evt):
        idx = self._idx_from_xy(evt.x, evt.y)
        if idx is not None:
            self.selected_idx = idx
            self.confirm()

    def set_selected(self, idx):
        idx = int(idx) % len(RADIAL_ACTIONS)
        if idx != self.selected_idx:
            self.selected_idx = idx
            self._refresh_slices()
            self.audio.play_nav()

    def step_direction(self, d_idx):
        self.set_selected(self.selected_idx + d_idx)

    def select_by_stick(self, sx, sy, deadzone=13500):
        mag = math.hypot(sx, sy)
        if mag < deadzone:
            return
        deg = math.degrees(math.atan2(-sy, sx))
        rel = (deg + 90.0 + 22.5) % 360.0
        idx = int(rel // 45.0) % len(RADIAL_ACTIONS)
        self.set_selected(idx)

    def show(self):
        if self.visible:
            return
        self.visible = True
        self.apply_theme()
        wl, wt, wr, wb = get_work_area()
        x = wl + max(0, ((wr - wl) - self.SIZE) // 2)
        y = wt + max(0, ((wb - wt) - self.SIZE) // 2)
        self.focus_guard.show_noactivate_topmost(self.win, x, y, self.SIZE, self.SIZE)
        self.audio.play_press()

    def hide(self, silent=False):
        if not self.visible:
            return
        self.visible = False
        try:
            self.win.withdraw()
        except Exception as exc:
            log_error("RadialMenu.hide", exc)
        if not silent:
            self.audio.play_back()

    def confirm(self):
        if not self.visible:
            return
        act_id = RADIAL_ACTIONS[self.selected_idx][0]
        self.hide(silent=True)
        self.audio.play_press()
        if self._on_action:
            self._on_action(act_id)
