import math
import tkinter as tk
from input_synth import get_work_area
from rover_system import log_error
from ui_theme import THEMES, apply_dwm_window_theme, mono_font

RADIAL_ACTIONS = [
    ("monitor_off", "Monitor\nOFF", "Apagar pantalla"),
    ("screenshot", "Captura\nWin+Sh+S", "Recorte de pantalla"),
    ("keyboard", "Teclado", "Abrir teclado flotante"),
    ("mute", "Silencio", "Silenciar / activar audio"),
    ("suspend", "Suspender\nPC", "Suspender equipo"),
    ("close_app", "Cerrar\nAlt+F4", "Cerrar ventana activa"),
    ("toggle_mode", "Modo\nJuego/M", "Alternar Juego / Mouse"),
    ("settings", "Ajustes", "Abrir configuracion"),
]


class RadialMenu:
    """2-color monochrome 8-slice radial couch menu controlled by stick, D-Pad, or mouse."""

    SIZE = 344
    OUTER_R = 154
    INNER_R = 52

    def __init__(self, root, config_store, focus_guard, audio, on_action):
        self.root = root
        self.config = config_store
        self.focus_guard = focus_guard
        self.audio = audio
        self._on_action = on_action

        self.visible = False
        self.selected_idx = 0
        self._slice_polys = []
        self._slice_texts = []

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
        )
        self.canvas.pack(fill="both", expand=True)

        cx = self.SIZE / 2.0
        cy = self.SIZE / 2.0
        n = len(RADIAL_ACTIONS)
        step_deg = 360.0 / n

        for idx, (_act_id, short_lbl, _desc) in enumerate(RADIAL_ACTIONS):
            # 0 is North (-90 deg in screen coordinates)
            center_deg = -90.0 + idx * step_deg
            a1 = math.radians(center_deg - step_deg / 2.0)
            a2 = math.radians(center_deg + step_deg / 2.0)
            pts = self._ring_sector_points(cx, cy, self.INNER_R, self.OUTER_R, a1, a2, steps=10)
            poly = self.canvas.create_polygon(pts, width=1)

            mid_r = (self.INNER_R + self.OUTER_R) / 2.0
            tx = cx + mid_r * math.cos(math.radians(center_deg))
            ty = cy + mid_r * math.sin(math.radians(center_deg))
            txt = self.canvas.create_text(tx, ty, text=short_lbl, font=mono_font(8, "bold"), justify="center")

            for item in (poly, txt):
                self.canvas.tag_bind(item, "<Enter>", lambda _e, i=idx: self.set_selected(i))
                self.canvas.tag_bind(item, "<Button-1>", lambda _e, i=idx: self._click_slice(i))

            self._slice_polys.append(poly)
            self._slice_texts.append(txt)

        self.hub_circle = self.canvas.create_oval(
            cx - self.INNER_R,
            cy - self.INNER_R,
            cx + self.INNER_R,
            cy + self.INNER_R,
            width=2,
        )
        self.hub_title = self.canvas.create_text(cx, cy - 6, text="ROVER", font=mono_font(9, "bold"), justify="center")
        self.hub_sub = self.canvas.create_text(cx, cy + 14, text="A/RB: OK", font=mono_font(7), justify="center")
        self.footer_hint = self.canvas.create_text(
            cx,
            self.SIZE - 10,
            text="Stick/D-Pad: Elegir | A/RB: Usar | B: Cerrar",
            font=mono_font(7),
        )

    @staticmethod
    def _ring_sector_points(cx, cy, r_in, r_out, a1, a2, steps=10):
        pts = []
        for s in range(steps + 1):
            a = a1 + (a2 - a1) * (s / float(steps))
            pts.extend((cx + r_out * math.cos(a), cy + r_out * math.sin(a)))
        for s in range(steps, -1, -1):
            a = a1 + (a2 - a1) * (s / float(steps))
            pts.extend((cx + r_in * math.cos(a), cy + r_in * math.sin(a)))
        return pts

    def apply_theme(self):
        p = self._palette()
        apply_dwm_window_theme(self.win, self.config["theme"], corner_round=False)
        self.win.configure(bg=p["bg"])
        self.canvas.configure(
            bg=p["bg"],
            highlightbackground=p["fg"],
            highlightcolor=p["fg"],
        )
        self.canvas.itemconfig(self.hub_circle, fill=p["bg"], outline=p["fg"])
        self.canvas.itemconfig(self.hub_title, fill=p["fg"])
        self.canvas.itemconfig(self.hub_sub, fill=p["fg_secondary"])
        self.canvas.itemconfig(self.footer_hint, fill=p["fg_secondary"])
        self._refresh_slices()

    def _refresh_slices(self):
        p = self._palette()
        for idx, (poly, txt) in enumerate(zip(self._slice_polys, self._slice_texts)):
            active = idx == self.selected_idx
            self.canvas.itemconfig(
                poly,
                fill=p["inv_bg"] if active else p["bg"],
                outline=p["fg"],
                width=2 if active else 1,
            )
            self.canvas.itemconfig(txt, fill=p["inv_fg"] if active else p["fg"])
        act_id, _short, desc = RADIAL_ACTIONS[self.selected_idx]
        self.canvas.itemconfig(self.hub_title, text=RADIAL_ACTIONS[self.selected_idx][1].replace("\n", " "))
        self.canvas.itemconfig(self.hub_sub, text="A / RB")

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
        # Screen Y is inverted relative to XInput thumb Y (+Y is North / Up)
        deg = math.degrees(math.atan2(-sy, sx))
        # Shift so 0 deg is North (-90 deg)
        rel = (deg + 90.0 + 22.5) % 360.0
        idx = int(rel // 45.0) % len(RADIAL_ACTIONS)
        self.set_selected(idx)

    def _click_slice(self, idx):
        self.selected_idx = idx
        self.confirm()

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
