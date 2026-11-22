import atexit
import sys
import threading
import time
import tkinter as tk
import pystray

from app_profiles import AppProfileManager
from audio_feedback import TactileAudioEngine
from gamepad_ui import BUTTON_ORDER
from input_backend import (
    AutoRepeater,
    GamepadPoller,
    InputEdgeTracker,
    MultiTapDetector,
    compute_axis_velocity,
)
from input_synth import (
    ACTION_LABELS,
    MOUSEEVENTF_HWHEEL,
    MOUSEEVENTF_MOVE,
    MOUSEEVENTF_WHEEL,
    VK_VOLUME_MUTE,
    FocusGuard,
    InputSynthesizer,
    is_cursor_ibeam,
    switch_to_interactive_desktop,
)
from overlay_keyboard import FloatingKeyboard
from overlay_radial import RadialMenu
from overlay_toast import ToastManager
from rover_system import (
    APP_NAME,
    ConfigStore,
    SingleInstanceGuard,
    log_error,
)
from settings_window import SettingsWindow
from ui_theme import (
    THEMES,
    apply_font_selection,
    build_tray_pil_image,
    load_bundled_fonts,
    set_ui_audio_callback,
)


class RoverApp:
    """Main application orchestrator connecting input polling, state machine, overlays, audio, and system tray."""

    def __init__(self, instance_guard):
        self.instance_guard = instance_guard
        self.running = True
        self.mouse_mode = False
        self.controller_connected = False

        switch_to_interactive_desktop()

        self.config = ConfigStore(valid_themes=tuple(THEMES.keys()), valid_actions=tuple(ACTION_LABELS.keys()))
        self.audio = TactileAudioEngine(self.config)
        set_ui_audio_callback(lambda kind: self.audio.play_press() if kind == "press" else (self.audio.play_back() if kind == "back" else self.audio.play_nav()))

        self.focus_guard = FocusGuard()
        self.synth = InputSynthesizer(self.focus_guard)
        self.poller = GamepadPoller()
        self.edge_tracker = InputEdgeTracker()
        self.profile_mgr = AppProfileManager(self.config)

        self._nav_repeater = AutoRepeater(initial_delay=0.25, interval=0.095)
        self._back_repeater = AutoRepeater(initial_delay=0.30, interval=0.070)
        self._space_repeater = AutoRepeater(initial_delay=0.30, interval=0.085)
        self._cursor_repeater = AutoRepeater(initial_delay=0.28, interval=0.075)
        self._radial_repeater = AutoRepeater(initial_delay=0.26, interval=0.11)
        self._minus_detector = MultiTapDetector(window_sec=0.34)
        self._radial_tap_detector = MultiTapDetector(window_sec=0.36, immediate_at=2)

        self._auto_kb_timer_id = None
        self.settings_win = None
        self.tray_icon = None

        self.root = tk.Tk()
        self.root.withdraw()
        load_bundled_fonts()
        apply_font_selection(
            self.config.get("font_ui", "JetBrainsMono NF"),
            self.config.get("font_mono", "JetBrainsMono NF"),
        )
        self.root.report_callback_exception = self._on_tk_exception

        self.toast = ToastManager(self.root, self.config, self.focus_guard, audio=self.audio)
        self.keyboard = FloatingKeyboard(
            self.root,
            self.config,
            self.synth,
            self.audio,
            on_state_change=self._on_keyboard_state_change,
            on_consume_buttons=self._consume_active_buttons,
        )
        self.radial = RadialMenu(
            self.root,
            self.config,
            self.focus_guard,
            self.audio,
            on_action=self._execute_radial_action,
        )

    def _on_tk_exception(self, exc, val, tb):
        log_error("Tkinter callback exception", val)

    def _consume_active_buttons(self):
        """Latch all currently held buttons so mode transitions (e.g. B closing keyboard) never leak into Mouse Mode."""
        snap = self.poller.latest_snapshot
        self.edge_tracker.consume_current(snap.pressed, extra=("A", "B", "X", "Y", "START", "LB", "RB", "LT", "RT"))
        self._nav_repeater.reset()
        self._back_repeater.reset()
        self._space_repeater.reset()
        self._cursor_repeater.reset()
        self._radial_tap_detector.reset()
        self.synth.release_all_mouse_buttons()
        self._cancel_pending_auto_kb()

    def _cancel_pending_auto_kb(self):
        if self._auto_kb_timer_id is not None:
            try:
                self.root.after_cancel(self._auto_kb_timer_id)
            except Exception:
                pass
            self._auto_kb_timer_id = None

    def _schedule_ibeam_auto_kb(self):
        """Check for I-Beam text cursor immediately and after 85ms (for expandable search bars like Netflix)."""
        self._cancel_pending_auto_kb()
        if is_cursor_ibeam():
            self._auto_kb_timer_id = self.root.after(65, self._fire_auto_kb_if_still_valid, True)
        else:
            self._auto_kb_timer_id = self.root.after(95, self._fire_auto_kb_if_still_valid, False)

    def _fire_auto_kb_if_still_valid(self, already_matched):
        self._auto_kb_timer_id = None
        if not self.mouse_mode or self.keyboard.visible:
            return
        if already_matched or is_cursor_ibeam():
            self.keyboard.show()

    def _on_keyboard_state_change(self):
        if self.settings_win is not None:
            self.settings_win.sync_controls_from_config()

    def toggle_keyboard(self):
        if self.radial.visible:
            self.radial.hide(silent=True)
        if self.keyboard.visible:
            self.keyboard.hide(reason="toggle")
        else:
            self.keyboard.show()

    def open_radial_menu(self):
        self._consume_active_buttons()
        if self.keyboard.visible:
            self.keyboard.hide(reason="radial")
        if self.config.get("haptic_rumble", True):
            self.poller.rumble(0.65, 0.50, 75)
        self.radial.show()

    def _close_radial_menu(self):
        self._consume_active_buttons()
        self.radial.hide()

    def _execute_radial_action(self, act_id):
        self._consume_active_buttons()
        if self.config.get("haptic_rumble", True):
            self.poller.rumble(0.75, 0.55, 85)
        if act_id == "monitor_off":
            self.synth.turn_off_monitor()
        elif act_id == "screenshot":
            self.synth.capture_screenshot()
        elif act_id == "paste":
            self.synth.execute_action("paste", just_pressed=True, just_released=False, is_held=False)
        elif act_id == "mute":
            self.synth.send_vk_key(VK_VOLUME_MUTE)
        elif act_id == "suspend":
            self.synth.suspend_pc()
        elif act_id == "close_app":
            self.synth.close_active_window()
        elif act_id == "toggle_mode":
            self.toggle_mouse_mode()
        elif act_id == "settings":
            self.open_settings_window()

    def set_mouse_mode(self, enabled, notify=True, auto_profile=False):
        self._consume_active_buttons()
        if self.radial.visible:
            self.radial.hide(silent=True)
        if self.keyboard.visible:
            self.keyboard.hide(reason="mode_switch")
        self.mouse_mode = bool(enabled)
        if not auto_profile:
            self.profile_mgr.auto_switched_to_game = False
        self.audio.play_mode()
        if self.config.get("haptic_rumble", True):
            self.poller.rumble(0.85, 0.70, 125)
        if notify:
            if self.mouse_mode:
                self.toast.show("Modo Mouse ACTIVO", "Stick: Mover | A/RB: Clic | B: Escape | 2x Start: Menu", play_sound=False)
            else:
                self.toast.show("Modo Juego ACTIVO", "Doble clic en (-) o Home para Modo Mouse", play_sound=False)
        if self.settings_win is not None:
            self.settings_win.refresh_live_status()

    def toggle_mouse_mode(self):
        self.set_mouse_mode(not self.mouse_mode, notify=True, auto_profile=False)

    def handle_minus_taps(self, count):
        if count >= 2:
            self.toggle_mouse_mode()
        elif count == 1 and self.mouse_mode:
            self.toggle_keyboard()

    def request_controller_rescan(self):
        self.poller.request_rescan()

    def _on_rescan_completed(self, snap):
        if self.settings_win is not None:
            self.settings_win.refresh_live_status()
        if snap.connected:
            b_lbl = "XInput" if snap.backend == "xinput" else "HID"
            self.toast.show(f"Mando detectado ({b_lbl} #{snap.slot + 1})", snap.device_name or "Listo para usar")
        else:
            self.toast.show("Sin mando conectado", "Verifica cable, receptor 2.4G o bateria")

    def open_settings_window(self):
        if self.settings_win is None or not self.settings_win.win.winfo_exists():
            self.settings_win = SettingsWindow(self)
        self.settings_win.show()

    def refresh_tray_icon(self):
        if self.tray_icon is not None:
            try:
                self.tray_icon.icon = build_tray_pil_image(self.config["theme"], size=64)
            except Exception as exc:
                log_error("refresh_tray_icon", exc)

    def start_tray_icon(self):
        def on_open(_icon, _item):
            self.root.after(0, self.open_settings_window)

        def on_mode(_icon, _item):
            self.root.after(0, self.toggle_mouse_mode)

        def on_kb(_icon, _item):
            self.root.after(0, self.toggle_keyboard)

        def on_sound(_icon, _item):
            new_val = not self.config["tactile_sound"]
            self.config.set_and_save("tactile_sound", new_val)
            if new_val:
                self.audio.play_press()
            if self.settings_win is not None:
                self.root.after(0, self.settings_win.refresh_live_status)

        def on_theme(_icon, _item):
            nxt = "light" if self.config["theme"] == "dark" else "dark"
            if self.settings_win is not None:
                self.root.after(0, lambda: self.settings_win._set_theme(nxt))
            else:
                self.config.set_and_save("theme", nxt)
                self.root.after(0, self.keyboard.apply_theme)
                self.refresh_tray_icon()

        def on_quit(_icon, _item):
            self.root.after(0, self.quit)

        menu = pystray.Menu(
            pystray.MenuItem("Abrir configuracion", on_open, default=True),
            pystray.MenuItem("Alternar Modo Mouse", on_mode),
            pystray.MenuItem("Teclado flotante", on_kb),
            pystray.MenuItem("Alternar sonido tactil", on_sound),
            pystray.MenuItem("Cambiar tema", on_theme),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", on_quit),
        )
        self.tray_icon = pystray.Icon(
            APP_NAME,
            build_tray_pil_image(self.config["theme"], size=64),
            APP_NAME,
            menu,
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _compute_kb_nav_dir(self, snap):
        if "D_UP" in snap.pressed:
            return (-1, 0)
        if "D_DOWN" in snap.pressed:
            return (1, 0)
        if "D_LEFT" in snap.pressed:
            return (0, -1)
        if "D_RIGHT" in snap.pressed:
            return (0, 1)

        abs_x, abs_y = abs(snap.lx), abs(snap.ly)
        thresh = 13500 if self._nav_repeater._active_token is not None else 19000
        if max(abs_x, abs_y) > thresh:
            if abs_y > abs_x * 1.35:
                return (-1 if snap.ly > 0 else 1, 0)
            if abs_x > abs_y * 1.35:
                return (0, 1 if snap.lx > 0 else -1)
        return None

    def _step_keyboard_mode(self, snap, just_pressed, active_holds, now):
        # 1. D-Pad or Left Stick grid navigation
        nav_dir = self._compute_kb_nav_dir(snap)
        if self._nav_repeater.step(nav_dir, now):
            self.root.after(0, self.keyboard.move_selection, nav_dir[0], nav_dir[1])

        # 2. A or RB: Write active key (with Key-Preview Pop-up)
        if "A" in just_pressed or "RB" in just_pressed:
            self.root.after(0, self.keyboard.press_current_key)
            return

        # 3. B: Exclusively close the floating keyboard and consume B so it NEVER leaks Esc into Mouse Mode
        if "B" in just_pressed:
            self.edge_tracker.consume_current(snap.pressed, extra=("B",))
            self.root.after(0, lambda: self.keyboard.hide(reason="b_button"))
            return

        # 4. X (hold-to-repeat): Backspace
        if self._back_repeater.step("X" if "X" in active_holds else None, now):
            self.root.after(0, self.keyboard.press_backspace)

        # 5. Y (hold-to-repeat): Space
        if self._space_repeater.step("Y" if "Y" in active_holds else None, now):
            self.root.after(0, self.keyboard.press_space)

        # 6. LT: Toggle Symbols & Accents layer (#+=)
        if "LT" in just_pressed:
            self.root.after(0, self.keyboard.toggle_symbols_layer)

        # 8. L3: Cycle Shift (1-shot) -> Caps Lock -> Lowercase
        if "L3" in just_pressed:
            self.root.after(0, self.keyboard.cycle_shift_state)

        # 9. R3: Toggle keyboard top/bottom screen position
        if "R3" in just_pressed:
            self.root.after(0, self.keyboard.toggle_position)

        # 10. START: Submit (Enter) and close keyboard
        if "START" in just_pressed:
            self.edge_tracker.consume_current(snap.pressed, extra=("START",))
            self.root.after(0, self.keyboard.submit_and_close)

    def _step_radial_mode(self, snap, just_pressed, now):
        # Stick radial aiming (left or right stick)
        sx, sy = (snap.lx, snap.ly) if max(abs(snap.lx), abs(snap.ly)) >= max(abs(snap.rx), abs(snap.ry)) else (snap.rx, snap.ry)
        if max(abs(sx), abs(sy)) > 14000:
            self.root.after(0, self.radial.select_by_stick, sx, sy)
        else:
            d_dir = None
            if "D_RIGHT" in just_pressed or "D_DOWN" in snap.pressed:
                d_dir = 1
            elif "D_LEFT" in just_pressed or "D_UP" in snap.pressed:
                d_dir = -1
            if self._radial_repeater.step(d_dir, now):
                self.root.after(0, self.radial.step_direction, d_dir)

        if "A" in just_pressed or "RB" in just_pressed:
            self.edge_tracker.consume_current(snap.pressed, extra=("A", "RB"))
            self.root.after(0, self.radial.confirm)
            return

        if "B" in just_pressed or "START" in just_pressed:
            self.edge_tracker.consume_current(snap.pressed, extra=("B", "START"))
            self.root.after(0, self._close_radial_menu)

    def _step_mouse_mode(self, snap, just_pressed, just_released, active_holds, rem):
        dz, b_spd, p_fac, a_exp, s_step, auto_kb, base_map = self.config.snapshot_mouse_params()
        bmap = self.profile_mgr.effective_button_map(base_map)

        # Cancel any pending auto-keyboard timer if the user presses B (Esc) or any non-left-click button
        if any(bmap.get(bid) != "left_click" for bid in just_pressed):
            self.root.after(0, self._cancel_pending_auto_kb)

        precision_held = any((bid in active_holds) and bmap.get(bid) == "precision" for bid in BUTTON_ORDER)
        speed = b_spd * p_fac if precision_held else b_spd

        dx = compute_axis_velocity(snap.lx, dz, a_exp, speed, invert=False)
        dy = compute_axis_velocity(snap.ly, dz, a_exp, speed, invert=True)

        if dx != 0.0 or dy != 0.0:
            rem[0] += dx
            rem[1] += dy
            mx, my = int(rem[0]), int(rem[1])
            rem[0] -= mx
            rem[1] -= my
            if mx != 0 or my != 0:
                self.synth.send_mouse_input(MOUSEEVENTF_MOVE, dx=mx, dy=my)
        else:
            rem[0] = rem[1] = 0.0

        def on_toggle_kb():
            self.edge_tracker.consume_current(snap.pressed)
            self.root.after(0, self.toggle_keyboard)

        radial_edge_fired = False

        def on_open_radial():
            nonlocal radial_edge_fired
            radial_edge_fired = True
            if self._radial_tap_detector.step(True, time.monotonic()) >= 2:
                self.edge_tracker.consume_current(snap.pressed)
                self.root.after(0, self.open_radial_menu)

        def on_left_click_up():
            if auto_kb:
                self.root.after(0, self._schedule_ibeam_auto_kb)

        for bid in BUTTON_ORDER:
            act_id = bmap.get(bid, "none")
            if act_id in ("none", "precision"):
                continue
            self.synth.execute_action(
                act_id,
                just_pressed=(bid in just_pressed),
                just_released=(bid in just_released),
                is_held=(bid in active_holds),
                scroll_step=s_step,
                on_toggle_keyboard=on_toggle_kb,
                on_left_click_released=on_left_click_up,
                on_open_radial=on_open_radial,
            )

        if not radial_edge_fired:
            self._radial_tap_detector.step(False, time.monotonic())

        r_dz = max(6000, dz)
        if abs(snap.ry) > r_dz:
            delta_v = int((snap.ry / 32767.0) * (s_step * 0.5))
            if delta_v != 0:
                self.synth.send_mouse_input(MOUSEEVENTF_WHEEL, data=delta_v)
        if abs(snap.rx) > r_dz:
            delta_h = int((snap.rx / 32767.0) * (s_step * 0.5))
            if delta_h != 0:
                self.synth.send_mouse_input(MOUSEEVENTF_HWHEEL, data=delta_h)

    def controller_loop(self):
        switch_to_interactive_desktop()
        rem = [0.0, 0.0]
        disconnect_start = 0.0
        last_ui_slot = None
        last_ui_backend = None
        last_ui_bat = None
        last_profile_check = 0.0

        while self.running:
            snap, was_manual_rescan = self.poller.poll()
            now = time.monotonic()
            if was_manual_rescan:
                self.root.after(0, self._on_rescan_completed, snap)

            if now - last_profile_check >= 0.45:
                last_profile_check = now
                kind, _exe, prof_changed = self.profile_mgr.evaluate()
                if kind == "game" and self.mouse_mode and not self.keyboard.visible and not self.radial.visible:
                    self.profile_mgr.auto_switched_to_game = True
                    self.root.after(0, lambda: self.set_mouse_mode(False, notify=True, auto_profile=True))
                elif kind != "game" and self.profile_mgr.auto_switched_to_game and not self.mouse_mode:
                    self.profile_mgr.auto_switched_to_game = False
                    self.root.after(0, lambda: self.set_mouse_mode(True, notify=True, auto_profile=True))
                elif prof_changed and self.settings_win is not None:
                    self.root.after(0, self.settings_win.refresh_live_status)

            if snap.connected:
                disconnect_start = 0.0
                if not self.controller_connected:
                    self.controller_connected = True
                    self.mouse_mode = False
                    self.edge_tracker.reset()
                    self._minus_detector.reset()
                    last_ui_slot = snap.slot
                    last_ui_backend = snap.backend
                    last_ui_bat = snap.battery_label
                    if self.keyboard.visible:
                        self.root.after(0, lambda: self.keyboard.hide(reason="reconnect"))
                    if self.radial.visible:
                        self.root.after(0, lambda: self.radial.hide(silent=True))
                    b_lbl = "XInput" if snap.backend == "xinput" else "HID"
                    bat_txt = f" | Bat: {snap.battery_label}" if snap.battery_label else ""
                    self.root.after(
                        0,
                        lambda s=snap.slot, b=b_lbl, bt=bat_txt: self.toast.show(
                            f"Mando #{s + 1} conectado ({b}{bt})",
                            "Doble clic en (-) o Home para Modo Mouse",
                        ),
                    )
                    if self.settings_win is not None:
                        self.root.after(0, self.settings_win.refresh_live_status)
                elif snap.slot != last_ui_slot or snap.backend != last_ui_backend or snap.battery_label != last_ui_bat:
                    last_ui_slot = snap.slot
                    last_ui_backend = snap.backend
                    last_ui_bat = snap.battery_label
                    if self.settings_win is not None:
                        self.root.after(0, self.settings_win.refresh_live_status)

                # Single unified edge computation per frame across all modes
                just_pressed, just_released, active_holds = self.edge_tracker.update(snap.pressed)

                # Lock-free multi-tap detection for '-' (VIEW) or Home
                minus_edge = ("VIEW" in just_pressed) or ("HOME" in just_pressed)
                tap_count = self._minus_detector.step(minus_edge, now)
                if tap_count > 0:
                    self.edge_tracker.consume_current(snap.pressed)
                    self.root.after(0, self.handle_minus_taps, tap_count)

                if self.radial.visible:
                    self._step_radial_mode(snap, just_pressed, now)
                    time.sleep(0.012)
                elif self.keyboard.visible:
                    self._step_keyboard_mode(snap, just_pressed, active_holds, now)
                    time.sleep(0.010)
                elif self.mouse_mode:
                    self._step_mouse_mode(snap, just_pressed, just_released, active_holds, rem)
                    time.sleep(0.008)
                else:
                    rem[0] = rem[1] = 0.0
                    time.sleep(0.035)
            else:
                self.edge_tracker.reset()
                self._minus_detector.reset()
                self.synth.release_all_mouse_buttons()
                rem[0] = rem[1] = 0.0
                if self.controller_connected:
                    if disconnect_start == 0.0:
                        disconnect_start = now
                    elif now - disconnect_start > 2.2:
                        self.controller_connected = False
                        disconnect_start = 0.0
                        if self.settings_win is not None:
                            self.root.after(0, self.settings_win.refresh_live_status)
                time.sleep(0.080)

    def poll_ipc_events(self):
        if not self.running:
            return
        show_req, quit_req = self.instance_guard.poll_events()
        if show_req:
            self.open_settings_window()
        if quit_req:
            self.quit()
            return
        self.root.after(120, self.poll_ipc_events)

    def cleanup(self):
        self.running = False
        self._cancel_pending_auto_kb()
        self.keyboard._cancel_timers()
        self.keyboard._cancel_popup()
        if self.settings_win is not None:
            for attr in ("_page_reveal_id", "_diagram_poll_id"):
                aid = getattr(self.settings_win, attr, None)
                if aid is not None:
                    try:
                        self.root.after_cancel(aid)
                    except Exception:
                        pass
                    setattr(self.settings_win, attr, None)
        self.synth.release_all_mouse_buttons()
        self.poller.stop_rumble()
        self.radial.hide(silent=True)
        self.toast.destroy_active()
        self.audio.close()
        self.instance_guard.close()

    def quit(self):
        if not self.running:
            return
        self.cleanup()
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def run(self, argv):
        args = {a.lower() for a in argv}
        atexit.register(self.cleanup)
        self.start_tray_icon()
        threading.Thread(target=self.controller_loop, daemon=True).start()
        self.root.after(120, self.poll_ipc_events)

        if "--minimized" in args or "--tray" in args:
            self.root.after(
                220,
                lambda: self.toast.show(
                    f"{APP_NAME} activo en bandeja",
                    "Doble clic en (-) o Home para Modo Mouse",
                ),
            )
        else:
            self.open_settings_window()

        self.root.mainloop()


def main():
    guard = SingleInstanceGuard()
    if not guard.acquire_or_dispatch(sys.argv[1:]):
        sys.exit(0)
    app = RoverApp(guard)
    app.run(sys.argv[1:])


if __name__ == "__main__":
    main()
