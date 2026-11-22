import os
import sys
import tkinter as tk
from gamepad_ui import (
    ACTION_LABELS,
    BUTTON_LABELS,
    ActionPickerModal,
    GamepadDiagram,
)
from input_backend import GamepadPoller
from rover_system import (
    APP_NAME,
    APP_VERSION,
    CONFIG_DIR,
    get_app_executable,
    is_startup_enabled,
    set_startup_enabled,
)
from ui_theme import (
    FONT_FAMILY,
    FONT_UI,
    THEMES,
    CardGroup,
    FlatScrollbar,
    MonoButton,
    SegmentedControl,
    StepperControl,
    ThemedEntryRow,
    ToggleSwitch,
    apply_dwm_window_theme,
    center_window_on_parent,
    center_window_on_screen,
    get_resource_path,
    mono_font,
    ui_font,
)


class SettingsWindow:
    """Nordic Cockpit 6-page Settings UI with Top Telemetry Strip, CardGroups, and subtle page transitions."""

    NAV_ITEMS = [
        ("general", "General"),
        ("gamepad", "Mando y Botones"),
        ("mouse", "Mouse y Sticks"),
        ("keyboard", "Teclado Flotante"),
        ("profiles", "Perfiles por App"),
        ("appearance", "Apariencia y Audio"),
        ("system", "Sistema"),
    ]

    def __init__(self, app):
        self.app = app
        self.win = app.root
        self.config = app.config
        self.win.title(f"{APP_NAME} - Configuracion")
        self.win.geometry("940x670")
        self.win.minsize(560, 420)

        self.current_page = "general"
        self.selected_btn = "B"
        self._modal_open = None
        self._diagram_poll_id = None
        self._page_reveal_id = None

        ico_path = get_resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(ico_path):
            try:
                self.win.iconbitmap(ico_path)
            except Exception:
                pass

        center_window_on_screen(self.win, 940, 670)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close_request)
        self.win.bind("<Escape>", self._on_escape)

        self._card_groups = []
        self._nav_buttons = {}

        self._build_shell()
        self.show_page("general", animate=False)
        self.apply_theme()

    def _palette(self):
        return THEMES.get(self.config["theme"], THEMES["dark"])

    def _build_shell(self):
        self.shell = tk.Frame(self.win)
        self.shell.pack(fill="both", expand=True)

        # Top Cockpit Telemetry Bar
        self.telemetry_bar = tk.Frame(self.shell, padx=20, pady=10)
        self.telemetry_bar.pack(side="top", fill="x")

        brand_col = tk.Frame(self.telemetry_bar)
        brand_col.pack(side="left")
        self._brand_col = brand_col

        self.app_title_lbl = tk.Label(brand_col, text=APP_NAME.upper(), font=mono_font(13, "bold"), anchor="w")
        self.app_title_lbl.pack(side="left")

        self.app_ver_badge = tk.Label(brand_col, text=f"v{APP_VERSION}", font=mono_font(8, "bold"), padx=6, pady=1)
        self.app_ver_badge.pack(side="left", padx=(8, 0))

        self.telemetry_right = tk.Frame(self.telemetry_bar)
        self.telemetry_right.pack(side="right")

        # Status chip: Controller connection
        self.ctrl_chip = tk.Frame(self.telemetry_right, padx=10, pady=4, highlightthickness=1)
        self.ctrl_chip.pack(side="left", padx=(0, 8))
        self.ctrl_dot = tk.Canvas(self.ctrl_chip, width=8, height=8, highlightthickness=0)
        self.ctrl_dot.pack(side="left", padx=(0, 6))
        self.ctrl_status_lbl = tk.Label(self.ctrl_chip, text="Esperando mando", font=mono_font(8, "bold"))
        self.ctrl_status_lbl.pack(side="left")

        # Status chip: Active mode (clickable)
        self.mode_chip = tk.Label(
            self.telemetry_right,
            text="MODO JUEGO",
            font=mono_font(8, "bold"),
            padx=10,
            pady=4,
            highlightthickness=1,
            cursor="hand2",
        )
        self.mode_chip.pack(side="left", padx=(0, 8))
        self.mode_chip.bind("<Button-1>", lambda _e: self.app.toggle_mouse_mode())

        # Quick Sound Toggle chip
        self.sound_chip = tk.Label(
            self.telemetry_right,
            text="SONIDO: ON",
            font=mono_font(8, "bold"),
            padx=10,
            pady=4,
            highlightthickness=1,
            cursor="hand2",
        )
        self.sound_chip.pack(side="left", padx=(0, 8))
        self.sound_chip.bind("<Button-1>", lambda _e: self._toggle_sound_quick())

        # Quick Theme Button
        self.btn_top_theme = MonoButton(
            self.telemetry_right,
            "Tema",
            command=self._toggle_theme,
            padx=10,
            pady=4,
            font_size=8,
        )
        self.btn_top_theme.pack(side="left")

        self.top_sep = tk.Frame(self.shell, height=1)
        self.top_sep.pack(side="top", fill="x")

        # Main workspace below telemetry bar
        self.workspace = tk.Frame(self.shell)
        self.workspace.pack(side="top", fill="both", expand=True)

        self.sidebar = tk.Frame(self.workspace, width=236, padx=14, pady=16)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.nav_list = tk.Frame(self.sidebar)
        self.nav_list.pack(fill="x")

        for key, title in self.NAV_ITEMS:
            row = tk.Frame(self.nav_list, cursor="hand2")
            row.pack(fill="x", pady=2)
            bar = tk.Frame(row, width=3)
            bar.pack(side="left", fill="y")
            btn = tk.Label(
                row,
                text=title,
                font=ui_font(10),
                anchor="w",
                padx=12,
                pady=8,
                cursor="hand2",
                takefocus=1,
            )
            btn.pack(side="left", fill="x", expand=True)
            for w in (row, bar, btn):
                w.bind("<Button-1>", lambda _e, k=key: self._on_nav_click(k))
            btn.bind("<Return>", lambda _e, k=key: self._on_nav_click(k))
            btn.bind("<space>", lambda _e, k=key: self._on_nav_click(k))
            btn.bind("<Up>", lambda _e, k=key: self._step_nav(k, -1))
            btn.bind("<Down>", lambda _e, k=key: self._step_nav(k, 1))
            btn.bind("<FocusIn>", lambda _e, b=btn: b.configure(highlightthickness=1))
            btn.bind("<FocusOut>", lambda _e, b=btn: b.configure(highlightthickness=0))
            self._nav_buttons[key] = (row, bar, btn)

        self.sidebar_spacer = tk.Frame(self.sidebar)
        self.sidebar_spacer.pack(fill="both", expand=True)

        # Quick Controller Hint Card in Sidebar Footer
        self.hint_card = tk.Frame(self.sidebar, padx=12, pady=10, highlightthickness=1)
        self.hint_card.pack(fill="x")
        self.hint_title_lbl = tk.Label(self.hint_card, text="Atajos del mando", font=ui_font(8, "bold"), anchor="w")
        self.hint_title_lbl.pack(fill="x")
        self.hint_body_lbl = tk.Label(
            self.hint_card,
            text="2x (-)/Home: Modo Mouse\n1x (-) o X: Teclado\nStart (+): Menu Radial\nB: Cerrar / Escape",
            font=ui_font(8),
            justify="left",
            anchor="w",
            wraplength=184,
        )
        self.hint_body_lbl.pack(fill="x", pady=(4, 8))
        self.btn_quick_kb = MonoButton(
            self.hint_card,
            "Abrir teclado",
            command=self._toggle_kb_from_ui,
            pady=4,
            font_size=8,
        )
        self.btn_quick_kb.pack(fill="x")

        self.v_sep = tk.Frame(self.workspace, width=1)
        self.v_sep.pack(side="left", fill="y")

        self.content_area = tk.Frame(self.workspace, padx=26, pady=16)
        self.content_area.pack(side="left", fill="both", expand=True)

        self.header_frame = tk.Frame(self.content_area)
        self.header_frame.pack(fill="x")
        self.page_title_lbl = tk.Label(self.header_frame, text="", font=ui_font(16, "bold"), anchor="w")
        self.page_title_lbl.pack(fill="x")
        self.page_sub_lbl = tk.Label(
            self.header_frame,
            text="",
            font=ui_font(9),
            anchor="w",
            wraplength=630,
            justify="left",
        )
        self.page_sub_lbl.pack(fill="x", pady=(3, 10))

        self.scroll_wrap = tk.Frame(self.content_area)
        self.scroll_wrap.pack(fill="both", expand=True)
        self.scroll_wrap.grid_rowconfigure(0, weight=1)
        self.scroll_wrap.grid_columnconfigure(0, weight=1)

        self.scroll_canvas = tk.Canvas(self.scroll_wrap, highlightthickness=0, bd=0)
        self.scroll_canvas.grid(row=0, column=0, sticky="nsew")

        self.v_scroll = FlatScrollbar(self.scroll_wrap, orient="vertical", command=self.scroll_canvas.yview, thickness=10)
        self.v_scroll.grid(row=0, column=1, sticky="ns", padx=(4, 0))

        self.h_scroll = FlatScrollbar(self.scroll_wrap, orient="horizontal", command=self.scroll_canvas.xview, thickness=10)
        self.h_scroll.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        self.scroll_canvas.configure(
            yscrollcommand=self._on_yscroll,
            xscrollcommand=self._on_xscroll,
        )

        self.page_body = tk.Frame(self.scroll_canvas)
        self._page_win_id = self.scroll_canvas.create_window((0, 0), window=self.page_body, anchor="nw")

        self.page_body.bind("<Configure>", self._on_scroll_content_configure)
        self.scroll_canvas.bind("<Configure>", self._on_scroll_canvas_configure)
        self.win.bind("<MouseWheel>", self._on_mousewheel)
        self.win.bind("<Shift-MouseWheel>", self._on_shift_mousewheel)

    def _on_yscroll(self, lo, hi):
        self.v_scroll.set(lo, hi)
        if float(hi) - float(lo) >= 0.999:
            self.v_scroll.grid_remove()
        else:
            self.v_scroll.grid()

    def _on_xscroll(self, lo, hi):
        self.h_scroll.set(lo, hi)
        if float(hi) - float(lo) >= 0.999:
            self.h_scroll.grid_remove()
        else:
            self.h_scroll.grid()

    def _on_scroll_content_configure(self, _evt=None):
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))

    def _on_scroll_canvas_configure(self, evt):
        req_w = self.page_body.winfo_reqwidth()
        target_w = max(evt.width, req_w) if self.current_page == "gamepad" else max(evt.width, 460)
        self.scroll_canvas.itemconfigure(self._page_win_id, width=target_w)
        self.page_sub_lbl.configure(wraplength=max(240, evt.width - 10))
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))

    def _on_mousewheel(self, evt):
        if self._modal_open and self._modal_open.winfo_exists():
            return
        if self.v_scroll.winfo_ismapped():
            self.scroll_canvas.yview_scroll(int(-1 * (evt.delta / 120)), "units")

    def _on_shift_mousewheel(self, evt):
        if self._modal_open and self._modal_open.winfo_exists():
            return
        if self.h_scroll.winfo_ismapped():
            self.scroll_canvas.xview_scroll(int(-1 * (evt.delta / 120)), "units")

    def _on_nav_click(self, key):
        if key != self.current_page:
            self.app.audio.play_nav()
            self.show_page(key, animate=True)

    def _step_nav(self, cur_key, delta):
        keys = [k for k, _ in self.NAV_ITEMS]
        nxt = keys[(keys.index(cur_key) + delta) % len(keys)]
        self.app.audio.play_nav()
        self.show_page(nxt, animate=True)
        self._nav_buttons[nxt][2].focus_set()

    def _clear_page(self):
        for attr in ("_page_reveal_id", "_diagram_poll_id"):
            aid = getattr(self, attr, None)
            if aid is not None:
                try:
                    self.win.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)
        for w in self.page_body.winfo_children():
            w.destroy()
        self._card_groups.clear()

    def _make_group(self, title=None):
        grp = CardGroup(self.page_body, title=title)
        grp.pack(fill="x")
        self._card_groups.append(grp)
        return grp

    def _animate_page_entrance(self):
        """Subtle 2-step vertical settle transition on page switch (MOTION 2)."""
        self.header_frame.pack_configure(pady=(4, 0))

        def settle():
            if self.win.winfo_exists():
                self.header_frame.pack_configure(pady=(0, 0))
            self._page_reveal_id = None

        self._page_reveal_id = self.win.after(55, settle)

    def show_page(self, key, animate=False):
        self.current_page = key
        self._clear_page()
        self.scroll_canvas.yview_moveto(0)
        self.scroll_canvas.xview_moveto(0)

        if key == "general":
            self.page_title_lbl.configure(text="General")
            self.page_sub_lbl.configure(text="Estado del mando en tiempo real, modo de operacion y arranque en Windows.")

            g1 = self._make_group("Dispositivo y Modo")
            self._gen_status_row = g1.add_row(
                self._controller_title_text(),
                self._controller_sub_text(),
                lambda p: MonoButton(p, "Detectar ahora", command=self.app.request_controller_rescan),
            )
            self._gen_mode_row = g1.add_row(
                "Modo de entrada activo",
                "Alterna entre Modo Juego (pasa los controles directo al juego) y Modo Mouse.",
                lambda p: SegmentedControl(
                    p,
                    [("game", "Juego"), ("mouse", "Mouse")],
                    "mouse" if self.app.mouse_mode else "game",
                    on_change=lambda k: self.app.set_mouse_mode(k == "mouse", notify=True),
                ),
            )
            self._gen_kb_row = g1.add_row(
                "Teclado flotante en pantalla",
                "Muestra el teclado multicapa compatible con Netflix y navegadores.",
                lambda p: MonoButton(
                    p,
                    "Ocultar teclado" if self.app.keyboard.visible else "Mostrar teclado",
                    command=self._toggle_kb_from_ui,
                ),
            )

            g2 = self._make_group("Arranque y Bandeja")
            self._gen_startup_row = g2.add_row(
                "Iniciar con Windows",
                "Ejecuta Rover minimizado en la bandeja del sistema al iniciar sesion.",
                lambda p: ToggleSwitch(p, value=is_startup_enabled(), on_change=self._on_startup_toggle),
            )
            g2.add_row(
                "Mantener en bandeja al cerrar",
                "Oculta esta ventana sin detener la lectura del mando ni el teclado flotante.",
                lambda p: ToggleSwitch(
                    p,
                    value=self.config["minimize_to_tray"],
                    on_change=lambda v: self.config.set_and_save("minimize_to_tray", v),
                ),
            )

        elif key == "gamepad":
            self.page_title_lbl.configure(text="Mando y Botones")
            self.page_sub_lbl.configure(
                text="Haz clic en un boton del esquema o presionalo fisicamente en tu mando para asignarle accion."
            )

            diag_card = self._make_group()
            diag_wrap = tk.Frame(diag_card.box, padx=8, pady=6)
            diag_wrap.pack(fill="x")
            diag_card._rows.append(diag_wrap)

            self.gamepad_diagram = GamepadDiagram(
                diag_wrap,
                selected_btn=self.selected_btn,
                on_select=self._on_diagram_select,
            )
            self.gamepad_diagram.pack(anchor="center")
            self.gamepad_diagram.bind("<Return>", lambda _e: self._open_action_picker())
            self.gamepad_diagram.bind("<space>", lambda _e: self._open_action_picker())
            diag_card._controls.append(self.gamepad_diagram)

            g_assign = self._make_group("Asignacion en Modo Mouse")
            cur_act = self.config["button_map"].get(self.selected_btn, "none")
            self._gp_assign_row = g_assign.add_row(
                BUTTON_LABELS.get(self.selected_btn, self.selected_btn),
                f"Accion asignada: {ACTION_LABELS.get(cur_act, 'Sin asignar')}",
                lambda p: MonoButton(p, "Cambiar accion", command=self._open_action_picker, primary=True),
                badge_text=self.selected_btn,
            )
            g_assign.add_row(
                "Restaurar mapa predeterminado",
                "Reestablece A (Clic izq), B (Escape), X (Teclado), Y (Clic der), LT (Precision) y RT (Atras).",
                lambda p: MonoButton(p, "Restaurar botones", command=self._reset_button_map),
            )
            self._start_diagram_poll()

        elif key == "mouse":
            self.page_title_lbl.configure(text="Mouse y Sticks")
            self.page_sub_lbl.configure(text="Calibra velocidad, zona muerta, curva exponencial y scroll.")

            g1 = self._make_group("Respuesta del stick izquierdo (Cursor)")
            g1.add_row(
                "Velocidad base",
                "Rapidez maxima del puntero al inclinar el stick al borde (8 a 40).",
                lambda p: StepperControl(
                    p,
                    self.config["base_speed"],
                    8.0,
                    40.0,
                    2.0,
                    "{:.0f}",
                    lambda v: self.config.set_and_save("base_speed", float(v)),
                ),
            )
            g1.add_row(
                "Zona muerta (Deadzone)",
                "Aumenta este umbral si el cursor deriva cuando sueltas el stick (1500 a 12000).",
                lambda p: StepperControl(
                    p,
                    self.config["deadzone"],
                    1500,
                    12000,
                    500,
                    "{:.0f}",
                    lambda v: self.config.set_and_save("deadzone", int(v)),
                ),
            )
            g1.add_row(
                "Multiplicador de precision (LT)",
                "Factor de reduccion de velocidad mientras mantienes presionado LT (0.15 a 0.70).",
                lambda p: StepperControl(
                    p,
                    self.config["precision_factor"],
                    0.15,
                    0.70,
                    0.05,
                    "{:.2f}",
                    lambda v: self.config.set_and_save("precision_factor", float(v)),
                ),
            )
            g1.add_row(
                "Curva de aceleracion",
                "Control fino cerca del centro y desplazamiento rapido en el extremo (1.0 a 2.5).",
                lambda p: StepperControl(
                    p,
                    self.config["accel_exp"],
                    1.0,
                    2.5,
                    0.1,
                    "{:.1f}",
                    lambda v: self.config.set_and_save("accel_exp", float(v)),
                ),
            )
            g1.add_row(
                "Paso de scroll (Stick derecho y D-Pad)",
                "Velocidad de desplazamiento vertical y horizontal (30 a 180).",
                lambda p: StepperControl(
                    p,
                    self.config["scroll_step"],
                    30,
                    180,
                    15,
                    "{:.0f}",
                    lambda v: self.config.set_and_save("scroll_step", int(v)),
                ),
            )

            g2 = self._make_group("Calibracion inicial")
            g2.add_row(
                "Restaurar sensibilidad de fabrica",
                "Vuelve velocidad, deadzone, precision y aceleracion a sus valores originales.",
                lambda p: MonoButton(p, "Restaurar sensibilidad", command=self._reset_sensitivity),
            )

        elif key == "keyboard":
            self.page_title_lbl.configure(text="Teclado Flotante")
            self.page_sub_lbl.configure(
                text="Teclado multicapa con popup Key-Preview, soporte para Netflix y cierre aislado con B."
            )

            g1 = self._make_group("Comportamiento del teclado")
            self._kb_pos_row = g1.add_row(
                "Ubicacion en pantalla",
                "Borde de la pantalla donde se despliega el teclado (también conmutable con R3).",
                lambda p: SegmentedControl(
                    p,
                    [("bottom", "Abajo"), ("top", "Arriba")],
                    "top" if self.config["keyboard_at_top"] else "bottom",
                    on_change=self._on_kb_pos_change,
                ),
            )
            g1.add_row(
                "Auto-abrir al pulsar campos de texto",
                "Detecta cursores de edicion (I-Beam) y buscadores desplegables al hacer clic con A.",
                lambda p: ToggleSwitch(
                    p,
                    value=self.config["auto_keyboard_ibeam"],
                    on_change=lambda v: self.config.set_and_save("auto_keyboard_ibeam", v),
                ),
            )
            self._kb_sound_row = g1.add_row(
                "Sonidos tactiles (estilo intermitentes Volvo)",
                "Clic calido y discreto de baja latencia al navegar, escribir o cerrar el teclado.",
                lambda p: ToggleSwitch(
                    p,
                    value=self.config["tactile_sound"],
                    on_change=self._on_sound_toggle,
                ),
            )
            g1.add_row(
                "Avisos flotantes (Toasts)",
                "Notificaciones breves sin robo de foco al conectar el mando o cambiar de modo.",
                lambda p: ToggleSwitch(
                    p,
                    value=self.config["show_toasts"],
                    on_change=lambda v: self.config.set_and_save("show_toasts", v),
                ),
            )

            g2 = self._make_group("Capas y atajos dentro del teclado")
            shortcuts = [
                ("A / RB", "Escribir tecla seleccionada (con Key-Preview Pop-up)"),
                ("B", "Cerrar teclado (consume el flanco para no enviar Esc a la app)"),
                ("X / Y", "Borrar (con repeticion al mantener) / Espacio"),
                ("LT o tecla [#+=]", "Alternar capa de Simbolos y Acentos (á, é, í, ó, ú, ¿, ¡, @, #)"),
                ("L3 o tecla [Mayus]", "Alternar Mayuscula 1-toque -> Bloq Mayus (CAPS) -> minusculas"),
                ("< / > (teclado)", "Mover cursor de texto a izquierda / derecha dentro del campo"),
                ("Start (+)", "Abrir Menu Radial Control de Sofa (Apagar monitor, Captura, Suspender)"),
            ]
            for badge_txt, desc_txt in shortcuts:
                g2.add_row(desc_txt, "", None, badge_text=badge_txt)

            g3 = self._make_group("Botones rapidos de escritura (fila inferior)")
            snips = self.config.get_kb_snippets()

            g3.add_row(
                "Boton rapido 1",
                "Texto completo que se escribe al pulsar la primera tecla rapida.",
                lambda p, v=snips[0]: ThemedEntryRow(p, v, lambda txt: self._save_snippet(0, txt), width=18),
            )
            g3.add_row(
                "Boton rapido 2",
                "Ideal para tu correo o dominio frecuente (ej. @gmail.com).",
                lambda p, v=snips[1]: ThemedEntryRow(p, v, lambda txt: self._save_snippet(1, txt), width=18),
            )

        elif key == "profiles":
            self.page_title_lbl.configure(text="Perfiles por App")
            self.page_sub_lbl.configure(
                text="Cambio automatico a Modo Juego en videojuegos y controles multimedia en streaming."
            )

            g1 = self._make_group("Deteccion automatica")
            g1.add_row(
                "Activar perfiles por aplicacion",
                "Detecta la ventana en primer plano cada 0.45s sin robar foco.",
                lambda p: ToggleSwitch(
                    p,
                    value=self.config["auto_profiles_enabled"],
                    on_change=lambda v: self.config.set_and_save("auto_profiles_enabled", v),
                ),
            )
            cur_exe = self.app.profile_mgr.last_exe or "ninguna"
            cur_prof = self.app.profile_mgr.active_profile.upper()
            self._prof_live_row = g1.add_row(
                f"Ventana actual: {cur_exe}",
                f"Perfil activo: {cur_prof}",
                lambda p: MonoButton(p, "Abrir Menu Radial", command=self.app.open_radial_menu),
            )

            g2 = self._make_group("Reglas (nombres de .exe separados por coma)")

            g2.add_row(
                "Apps de Juego (Modo Juego auto)",
                "Al enfocar estos .exe, Rover pausa Modo Mouse automaticamente.",
                lambda p: ThemedEntryRow(
                    p,
                    ", ".join(self.config["game_apps"]),
                    lambda txt: self._save_app_list("game_apps", txt),
                    width=26,
                    font_size=8,
                ),
            )
            g2.add_row(
                "Apps Media (D-Pad: ±10s y Volumen)",
                "Netflix, Spotify, VLC o Stremio reciben atajos directos en D-Pad.",
                lambda p: ThemedEntryRow(
                    p,
                    ", ".join(self.config["media_apps"]),
                    lambda txt: self._save_app_list("media_apps", txt),
                    width=26,
                    font_size=8,
                ),
            )

        elif key == "appearance":
            self.page_title_lbl.configure(text="Apariencia y Audio")
            self.page_sub_lbl.configure(
                text="Estetica monocromatica 100% mate (sin glassmorphism), audio estilo Volvo y vibracion."
            )

            g1 = self._make_group("Tema visual")
            self._app_theme_row = g1.add_row(
                "Paleta del sistema",
                "Superficies mate en 2 colores (#1E1E1E y #F5F5F5) de alto contraste.",
                lambda p: SegmentedControl(
                    p,
                    [("dark", "Gris mate"), ("light", "Blanco invertido")],
                    self.config["theme"],
                    on_change=self._set_theme,
                ),
            )
            g1.add_row(
                "Tipografia activa",
                f"UI: {FONT_UI} | Instrumentacion y Teclas: {FONT_FAMILY}",
                lambda p: MonoButton(p, "Alternar tema", command=self._toggle_theme, primary=True),
            )

            g2 = self._make_group("Acustica Tactil Volvo y Vibracion")
            self._app_sound_row = g2.add_row(
                "Activar sonidos tactiles",
                "Sintesis PCM en memoria inspirada en el relé amortiguado de cabina de Volvo.",
                lambda p: ToggleSwitch(
                    p,
                    value=self.config["tactile_sound"],
                    on_change=self._on_sound_toggle,
                ),
            )
            g2.add_row(
                "Probar respuesta acustica",
                "Escucha el par Tick-Tock de baja latencia (< 0.2 ms).",
                lambda p: MonoButton(p, "Probar Tick-Tock", command=lambda: self.app.audio.play_mode()),
            )
            g2.add_row(
                "Micro-vibracion en mando (XInput)",
                "Pulso tactil nitido (125ms) al cambiar de modo o usar el Menu Radial.",
                lambda p: ToggleSwitch(
                    p,
                    value=self.config["haptic_rumble"],
                    on_change=lambda v: self.config.set_and_save("haptic_rumble", v),
                ),
            )
            g2.add_row(
                "Probar vibracion",
                "Envia un pulso firme de 160ms al mando XInput conectado.",
                lambda p: MonoButton(p, "Vibrar", command=lambda: self.app.poller.rumble(0.90, 0.75, 160)),
            )

        elif key == "system":
            self.page_title_lbl.configure(text="Sistema")
            self.page_sub_lbl.configure(text="Diagnostico del motor de entrada, archivos de configuracion y cierre.")

            g1 = self._make_group("Entorno de ejecucion")
            g1.add_row(
                f"{APP_NAME} v{APP_VERSION}",
                GamepadPoller.engine_description(),
                lambda p: MonoButton(p, "Abrir carpeta config", command=self._open_config_dir),
            )
            mode_tag = "Ejecutable Portable" if getattr(sys, "frozen", False) else "Script Python"
            g1.add_row(
                "Binario activo",
                get_app_executable(),
                lambda p, t=mode_tag: tk.Label(p, text=t, font=mono_font(8, "bold")),
            )

            g2 = self._make_group("Mantenimiento y Control")
            g2.add_row(
                "Restaurar configuracion completa",
                "Devuelve tema, sensibilidad, sonido y botones a sus valores de fabrica.",
                lambda p: MonoButton(p, "Restaurar todo", command=self._confirm_reset_all),
            )
            g2.add_row(
                "Detener Rover por completo",
                "Cierra el asistente y elimina el icono de la bandeja del sistema.",
                lambda p: MonoButton(p, "Salir de Rover", command=self.app.quit, danger=True),
            )

        self.apply_theme()
        self.win.update_idletasks()
        cw = max(1, self.scroll_canvas.winfo_width())
        req_w = self.page_body.winfo_reqwidth()
        target_w = max(cw, req_w) if self.current_page == "gamepad" else max(cw, 460)
        self.scroll_canvas.itemconfigure(self._page_win_id, width=target_w)
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))
        if animate:
            self._animate_page_entrance()

    def _controller_title_text(self):
        if not GamepadPoller.has_backend_support():
            return "Sin soporte de mando en este equipo"
        snap = self.app.poller.latest_snapshot
        if self.app.controller_connected and snap.connected:
            b_lbl = "XInput" if snap.backend == "xinput" else "HID"
            extra = f" ({snap.device_name})" if snap.device_name else ""
            return f"Mando conectado: {b_lbl} #{snap.slot + 1}{extra}"
        return "Esperando conexion de mando"

    def _controller_sub_text(self):
        if not GamepadPoller.has_backend_support():
            return "No se detectaron librerias XInput ni winmm HID."
        snap = self.app.poller.latest_snapshot
        if self.app.controller_connected and snap.connected:
            if snap.backend == "winmm":
                return "Lectura activa por HID / DirectInput (winmm)."
            return "Lectura activa por XInput con conmutacion automatica entre 4 slots."
        return "Conecta tu mando por USB, receptor 2.4G o Bluetooth."

    def _toggle_kb_from_ui(self):
        self.app.toggle_keyboard()
        self.refresh_live_status()

    def _on_startup_toggle(self, enabled):
        ico_path = get_resource_path(os.path.join("assets", "app.ico"))
        ok = set_startup_enabled(enabled, icon_path=ico_path)
        if not ok and self.current_page == "general" and hasattr(self, "_gen_startup_row"):
            self._gen_startup_row.control.set(is_startup_enabled(), notify=False)
            self.app.toast.show("No se pudo actualizar el inicio", "Verifica permisos en tu carpeta Startup")

    def _on_kb_pos_change(self, pos_key):
        want_top = pos_key == "top"
        if self.config["keyboard_at_top"] != want_top:
            self.app.keyboard.toggle_position()

    def _on_sound_toggle(self, enabled):
        self.config.set_and_save("tactile_sound", bool(enabled))
        if enabled:
            self.app.audio.play_press()
        self.refresh_live_status()

    def _toggle_sound_quick(self):
        new_val = not self.config["tactile_sound"]
        self._on_sound_toggle(new_val)
        if self.current_page == "keyboard" and hasattr(self, "_kb_sound_row"):
            self._kb_sound_row.control.set(new_val, notify=False)
        elif self.current_page == "appearance" and hasattr(self, "_app_sound_row"):
            self._app_sound_row.control.set(new_val, notify=False)

    def _on_diagram_select(self, btn_id):
        self.selected_btn = btn_id
        self.app.audio.play_nav()
        if self.current_page == "gamepad" and hasattr(self, "_gp_assign_row"):
            row = self._gp_assign_row
            if row.title_lbl.winfo_exists():
                cur_act = self.config["button_map"].get(btn_id, "none")
                row.title_lbl.configure(text=BUTTON_LABELS.get(btn_id, btn_id))
                row.sub_lbl.configure(text=f"Accion asignada: {ACTION_LABELS.get(cur_act, 'Sin asignar')}")
                if row.badge_lbl is not None:
                    row.badge_lbl.configure(text=btn_id)

    def _open_action_picker(self):
        if self._modal_open and self._modal_open.winfo_exists():
            self._modal_open.lift()
            return
        cur_act = self.config["button_map"].get(self.selected_btn, "none")

        def on_pick(act_id):
            self.config.set_button_action(self.selected_btn, act_id)
            self._on_diagram_select(self.selected_btn)
            self.app.toast.show(f"Boton {self.selected_btn} asignado", ACTION_LABELS.get(act_id, ""))

        self._modal_open = ActionPickerModal(self.win, self.selected_btn, cur_act, self.config["theme"], on_pick)

    def _reset_button_map(self):
        self.config.reset_buttons()
        self._on_diagram_select(self.selected_btn)
        self.app.toast.show("Mapa de botones restaurado", "B asignado a Tecla Escape por defecto")

    def _start_diagram_poll(self):
        if self._diagram_poll_id is not None:
            try:
                self.win.after_cancel(self._diagram_poll_id)
            except Exception:
                pass
            self._diagram_poll_id = None

        def tick():
            if not self.win.winfo_exists() or self.current_page != "gamepad":
                self._diagram_poll_id = None
                return
            if hasattr(self, "gamepad_diagram") and self.gamepad_diagram.winfo_exists():
                snap = self.app.poller.latest_snapshot
                self.gamepad_diagram.set_live_state(snap.pressed, snap.stick_axes, auto_select_pressed=True)
            self._diagram_poll_id = self.win.after(60, tick)

        self._diagram_poll_id = self.win.after(60, tick)

    def _reset_sensitivity(self):
        self.config.reset_sensitivity()
        if self.current_page == "mouse":
            self.show_page("mouse", animate=False)
        self.app.toast.show("Sensibilidad restaurada", "Valores de fabrica aplicados")

    def _confirm_reset_all(self):
        if self._modal_open and self._modal_open.winfo_exists():
            self._modal_open.lift()
            return
        p = self._palette()
        dlg = tk.Toplevel(self.win)
        self._modal_open = dlg
        dlg.title("Confirmar restauracion")
        dlg.transient(self.win)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(bg=p["bg"])
        apply_dwm_window_theme(dlg, self.config["theme"])

        frame = tk.Frame(
            dlg,
            bg=p["surface"],
            padx=22,
            pady=18,
            highlightthickness=1,
            highlightbackground=p["border_strong"],
        )
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(
            frame,
            text="Restaurar toda la configuracion?",
            font=ui_font(12, "bold"),
            bg=p["surface"],
            fg=p["fg"],
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            frame,
            text="Se reiniciaran tema, sensibilidad, sonido y el mapa de botones (con B = Escape por defecto).",
            font=ui_font(9),
            bg=p["surface"],
            fg=p["fg_secondary"],
            wraplength=340,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(6, 16))

        btn_row = tk.Frame(frame, bg=p["surface"])
        btn_row.pack(fill="x")

        def do_reset():
            self.config.reset_all()
            dlg.destroy()
            self.show_page(self.current_page, animate=False)
            self.app.keyboard.apply_theme()
            self.app.refresh_tray_icon()
            self.app.toast.show("Configuracion restaurada", "Ajustes de fabrica aplicados")

        b_cancel = MonoButton(btn_row, "Cancelar", command=dlg.destroy)
        b_cancel.apply_theme(p)
        b_cancel.pack(side="right")

        b_ok = MonoButton(btn_row, "Restaurar", command=do_reset, danger=True)
        b_ok.apply_theme(p)
        b_ok.pack(side="right", padx=(0, 8))

        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        center_window_on_parent(dlg, self.win)
        b_cancel.focus_set()

    def _open_config_dir(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        os.startfile(CONFIG_DIR)

    def _toggle_theme(self):
        nxt = "light" if self.config["theme"] == "dark" else "dark"
        self._set_theme(nxt)

    def _save_snippet(self, idx, text_val):
        cleaned = str(text_val or "").strip()[:32]
        if not cleaned:
            return
        snips = self.config.get_kb_snippets()
        snips[idx] = cleaned
        self.config.set_and_save("kb_snippets", snips)
        self.app.keyboard.apply_theme()
        self.app.audio.play_press()
        self.app.toast.show("Boton rapido guardado", f"Tecla {idx + 1}: {cleaned}")

    def _save_app_list(self, cfg_key, raw_text):
        items = [s.strip().lower() for s in str(raw_text or "").split(",") if s.strip()]
        self.config.set_and_save(cfg_key, items)
        self.app.audio.play_press()
        self.app.toast.show("Perfiles guardados", f"{len(items)} aplicaciones configuradas")

    def _set_theme(self, theme_name):
        if theme_name not in THEMES:
            return
        self.config.set_and_save("theme", theme_name)
        self.apply_theme()
        self.app.keyboard.apply_theme()
        self.app.radial.apply_theme()
        self.app.refresh_tray_icon()
        if self.current_page == "appearance" and hasattr(self, "_app_theme_row"):
            self._app_theme_row.control.select(theme_name, notify=False)

    def sync_controls_from_config(self):
        if not self.win.winfo_exists():
            return
        if self.current_page == "keyboard" and hasattr(self, "_kb_pos_row"):
            self._kb_pos_row.control.select("top" if self.config["keyboard_at_top"] else "bottom", notify=False)
        self.refresh_live_status()

    def refresh_live_status(self):
        if not self.win.winfo_exists():
            return
        p = self._palette()
        snap = self.app.poller.latest_snapshot
        self.ctrl_dot.delete("all")
        if self.app.controller_connected and snap.connected:
            b_lbl = "XInput" if snap.backend == "xinput" else "HID"
            bat = f" · {snap.battery_label}" if snap.battery_label else ""
            self.ctrl_dot.create_oval(1, 1, 7, 7, fill=p["accent"], outline="")
            self.ctrl_status_lbl.configure(text=f"{b_lbl} #{snap.slot + 1}{bat}", fg=p["fg"])
        else:
            self.ctrl_dot.create_oval(1, 1, 7, 7, fill=p["surface"], outline=p["fg_muted"])
            self.ctrl_status_lbl.configure(text="Sin mando", fg=p["fg_secondary"])

        prof = self.app.profile_mgr.active_profile
        mode_base = "MOUSE" if self.app.mouse_mode else "JUEGO"
        prof_suffix = f" ({prof.upper()})" if prof != "default" else ""
        if self.app.mouse_mode:
            self.mode_chip.configure(
                text=f"MODO: {mode_base}{prof_suffix}",
                bg=p["accent"],
                fg=p["accent_fg"],
                highlightbackground=p["accent"],
            )
        else:
            self.mode_chip.configure(
                text=f"MODO: {mode_base}{prof_suffix}",
                bg=p["elevated"],
                fg=p["fg_secondary"],
                highlightbackground=p["border_subtle"],
            )

        snd_on = bool(self.config["tactile_sound"])
        self.sound_chip.configure(
            text="SONIDO: ON" if snd_on else "SONIDO: OFF",
            bg=p["elevated"],
            fg=p["accent"] if snd_on else p["fg_muted"],
            highlightbackground=p["border_subtle"],
        )

        self.btn_quick_kb.set_text("Ocultar teclado" if self.app.keyboard.visible else "Abrir teclado")

        if self.current_page == "general":
            if hasattr(self, "_gen_mode_row") and self._gen_mode_row.control.winfo_exists():
                self._gen_mode_row.control.select("mouse" if self.app.mouse_mode else "game", notify=False)
            if hasattr(self, "_gen_kb_row") and self._gen_kb_row.control.winfo_exists():
                self._gen_kb_row.control.set_text("Ocultar teclado" if self.app.keyboard.visible else "Mostrar teclado")
            if hasattr(self, "_gen_status_row") and self._gen_status_row.title_lbl.winfo_exists():
                self._gen_status_row.title_lbl.configure(text=self._controller_title_text())
                self._gen_status_row.sub_lbl.configure(text=self._controller_sub_text())

    def apply_theme(self):
        p = self._palette()
        apply_dwm_window_theme(self.win, self.config["theme"], corner_round=True)
        self.win.configure(bg=p["bg"])

        self.shell.configure(bg=p["bg"])
        self.telemetry_bar.configure(bg=p["surface"])
        self._brand_col.configure(bg=p["surface"])
        self.app_title_lbl.configure(bg=p["surface"], fg=p["fg"])
        self.app_ver_badge.configure(bg=p["elevated"], fg=p["accent"])
        self.telemetry_right.configure(bg=p["surface"])

        self.ctrl_chip.configure(
            bg=p["elevated"],
            highlightbackground=p["border_subtle"],
            highlightcolor=p["border_subtle"],
        )
        self.ctrl_dot.configure(bg=p["elevated"])
        self.ctrl_status_lbl.configure(bg=p["elevated"])
        self.btn_top_theme.apply_theme(p)
        self.top_sep.configure(bg=p["border_subtle"])

        self.workspace.configure(bg=p["bg"])
        self.sidebar.configure(bg=p["surface"])
        self.nav_list.configure(bg=p["surface"])
        self.sidebar_spacer.configure(bg=p["surface"])
        self.v_sep.configure(bg=p["border_subtle"])

        self.hint_card.configure(
            bg=p["bg"],
            highlightbackground=p["border_subtle"],
            highlightcolor=p["border_subtle"],
        )
        self.hint_title_lbl.configure(bg=p["bg"], fg=p["accent"])
        self.hint_body_lbl.configure(bg=p["bg"], fg=p["fg_secondary"])
        self.btn_quick_kb.apply_theme(p)

        self.content_area.configure(bg=p["bg"])
        self.header_frame.configure(bg=p["bg"])
        self.page_title_lbl.configure(bg=p["bg"], fg=p["fg"])
        self.page_sub_lbl.configure(bg=p["bg"], fg=p["fg_secondary"])
        self.scroll_wrap.configure(bg=p["bg"])
        self.scroll_canvas.configure(bg=p["bg"])
        self.v_scroll.apply_theme(p)
        self.h_scroll.apply_theme(p)
        self.page_body.configure(bg=p["bg"])

        for key, (row, bar, btn) in self._nav_buttons.items():
            active = key == self.current_page
            row_bg = p["elevated"] if active else p["surface"]
            row.configure(bg=row_bg)
            bar.configure(bg=p["accent"] if active else p["surface"])
            btn.configure(
                bg=row_bg,
                fg=p["fg"] if active else p["fg_secondary"],
                font=ui_font(10, "bold" if active else "normal"),
                highlightbackground=p["accent"],
                highlightcolor=p["accent"],
            )

        for grp in self._card_groups:
            grp.apply_theme(p)

        self.refresh_live_status()

    def _on_escape(self, _evt=None):
        if self._modal_open and self._modal_open.winfo_exists():
            self._modal_open.destroy()
            return
        if self.config["minimize_to_tray"]:
            self.hide()

    def _on_close_request(self):
        if self.config["minimize_to_tray"]:
            self.hide()
        else:
            self.app.quit()

    def show(self):
        if not self.win.winfo_exists():
            return
        self.apply_theme()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def hide(self):
        if self.win.winfo_exists():
            self.win.withdraw()
