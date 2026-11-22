import time
import tkinter as tk
from input_synth import get_work_area
from rover_system import log_error
from ui_theme import THEMES, apply_dwm_window_theme, ease_out_cubic, ui_font


class ToastManager:
    """Focus-safe Nordic Cockpit toast notifications with 60fps time-based slide and progress bar."""

    def __init__(self, root, config_store, focus_guard):
        self.root = root
        self.config = config_store
        self.focus_guard = focus_guard
        self._win = None
        self._anim_id = None
        self._hide_id = None
        self._prog_id = None

    def _palette(self):
        return THEMES.get(self.config["theme"], THEMES["dark"])

    def destroy_active(self):
        for attr in ("_anim_id", "_hide_id", "_prog_id"):
            aid = getattr(self, attr, None)
            if aid is not None:
                try:
                    self.root.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)
        if self._win is not None:
            try:
                if self._win.winfo_exists():
                    self._win.destroy()
            except Exception:
                pass
            self._win = None

    def _animate_y(self, win, start_y, end_y, x, w, h, duration_ms, on_done=None):
        start_ts = time.perf_counter()
        dur_s = max(0.016, duration_ms / 1000.0)

        def tick():
            if self._win is not win or not win.winfo_exists():
                return
            t = min(1.0, (time.perf_counter() - start_ts) / dur_s)
            cur_y = int(start_y + (end_y - start_y) * ease_out_cubic(t))
            win.geometry(f"{w}x{h}+{x}+{cur_y}")
            if t < 1.0:
                self._anim_id = self.root.after(15, tick)
            else:
                self._anim_id = None
                if on_done:
                    on_done()

        self._anim_id = self.root.after(1, tick)

    def show(self, title, subtitle=""):
        if not self.config["show_toasts"]:
            return
        self.destroy_active()
        p = self._palette()
        try:
            self.focus_guard.capture_foreground_target()
            t = tk.Toplevel(self.root)
            t.withdraw()
            self._win = t
            t.overrideredirect(True)
            t.configure(bg=p["border_strong"])

            outer = tk.Frame(t, bg=p["surface"])
            outer.pack(padx=1, pady=1)

            top_row = tk.Frame(outer, bg=p["surface"], padx=16, pady=10)
            top_row.pack(fill="both")

            # Volvo Amber status bar indicator
            marker = tk.Canvas(top_row, width=4, height=32, bg=p["surface"], highlightthickness=0)
            marker.create_rectangle(0, 0, 4, 32, fill=p["accent"], outline="")
            marker.pack(side="left", padx=(0, 12), fill="y")

            text_col = tk.Frame(top_row, bg=p["surface"])
            text_col.pack(side="left", fill="both")

            tk.Label(
                text_col,
                text=title,
                font=ui_font(10, "bold"),
                fg=p["fg"],
                bg=p["surface"],
                anchor="w",
            ).pack(anchor="w")
            if subtitle:
                tk.Label(
                    text_col,
                    text=subtitle,
                    font=ui_font(9),
                    fg=p["fg_secondary"],
                    bg=p["surface"],
                    anchor="w",
                ).pack(anchor="w", pady=(2, 0))

            prog_canvas = tk.Canvas(outer, height=3, bg=p["elevated"], highlightthickness=0)
            prog_canvas.pack(fill="x")

            t.update_idletasks()
            apply_dwm_window_theme(t, self.config["theme"], corner_round=True)
            w = max(t.winfo_reqwidth(), 240)
            h = max(t.winfo_reqheight(), 48)
            prog_bar = prog_canvas.create_rectangle(0, 0, w, 3, fill=p["accent"], outline="")

            wa_l, wa_t, wa_r, _wa_b = get_work_area(self.root.winfo_screenwidth(), self.root.winfo_screenheight())
            tx = max(wa_l + 8, min(wa_r - w - 8, wa_l + (wa_r - wa_l - w) // 2))
            start_y = wa_t - h - 8
            target_y = wa_t + 22

            self.focus_guard.show_noactivate_topmost(t, tx, start_y, w, h)

            duration_ms = 1950
            start_time = time.perf_counter()

            def update_prog():
                if self._win is not t or not t.winfo_exists():
                    return
                elapsed = (time.perf_counter() - start_time) * 1000.0
                frac = max(0.0, 1.0 - elapsed / duration_ms)
                prog_canvas.coords(prog_bar, 0, 0, int(w * frac), 3)
                if frac > 0.0:
                    self._prog_id = self.root.after(18, update_prog)

            def start_hide():
                if self._win is t and t.winfo_exists():
                    self._animate_y(t, target_y, start_y, tx, w, h, 130, on_done=self.destroy_active)

            self._animate_y(t, start_y, target_y, tx, w, h, 135)
            self._prog_id = self.root.after(16, update_prog)
            self._hide_id = self.root.after(duration_ms, start_hide)
        except Exception as exc:
            log_error("ToastManager.show", exc)
