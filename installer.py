import os
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog
import winreg

from rover_system import (
    APP_NAME,
    APP_VERSION,
    UNINSTALL_REG_PATH,
    create_shortcut,
    get_desktop_dir,
    get_startup_dir,
    remove_legacy_startup_shortcuts,
    signal_quit_and_wait,
)
from ui_theme import (
    FONT_FAMILY,
    THEMES,
    CardGroup,
    MonoButton,
    ToggleSwitch,
    apply_dwm_window_theme,
    center_window_on_screen,
    get_resource_path,
    load_bundled_fonts,
    mono_font,
    ui_font,
)


def default_install_dir():
    local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return os.path.join(local, "Programs", APP_NAME)


def stop_running_app(exe_path=None):
    """Signal graceful IPC quit first and wait for clean shutdown before fallback termination."""
    signal_quit_and_wait(timeout_sec=0.6)
    if exe_path and os.path.exists(exe_path):
        try:
            subprocess.run(
                [exe_path, "--quit"],
                creationflags=0x08000000,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except Exception:
            pass
    for img in ("Rover.exe", "BedAssistant.exe"):
        subprocess.run(
            ["taskkill", "/F", "/IM", img],
            creationflags=0x08000000,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -like '*BedAssistant.py*' -or $_.CommandLine -like '*Rover.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
        ],
        creationflags=0x08000000,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def schedule_deferred_rmdir(target_dir):
    """Safely remove target_dir after Uninstall.exe exits, passing the path via environment variable."""
    if not target_dir or not os.path.isdir(target_dir):
        return
    abs_target = os.path.abspath(target_dir)
    env = os.environ.copy()
    env["ROVER_UNINSTALL_DIR"] = abs_target
    ps_cmd = (
        "Start-Sleep -Seconds 2; "
        "if ($env:ROVER_UNINSTALL_DIR -and (Test-Path -LiteralPath $env:ROVER_UNINSTALL_DIR)) { "
        "Remove-Item -LiteralPath $env:ROVER_UNINSTALL_DIR -Recurse -Force -ErrorAction SilentlyContinue "
        "}"
    )
    subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps_cmd],
        env=env,
        cwd=tempfile.gettempdir(),
        creationflags=0x08000000,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class SetupApp:
    """Nordic Cockpit installer and uninstaller sharing CardGroup and rover_system utilities."""

    def __init__(self, uninstall_mode=False):
        self.uninstall_mode = uninstall_mode
        self.theme_name = "dark"
        self.installing = False
        self.finished = False
        self.install_dir = default_install_dir()
        self._pending_rmdir = None

        self.root = tk.Tk()
        load_bundled_fonts()
        self.root.title(f"{APP_NAME} - {'Desinstalar' if uninstall_mode else 'Instalador'}")
        self.root.resizable(False, False)

        ico_path = get_resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(ico_path):
            try:
                self.root.iconbitmap(ico_path)
            except Exception:
                pass

        self.root.bind("<Escape>", lambda _e: self._on_cancel())
        self.root.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._card_groups = []
        self._controls = []
        self._prog_val = 0.0

        self._build_ui()
        self.apply_theme()
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        req_w = max(600 if not uninstall_mode else 530, self.root.winfo_reqwidth() + 8)
        req_h = min(sh - 60, self.root.winfo_reqheight() + 8)
        center_window_on_screen(self.root, min(sw - 40, req_w), req_h)

    def _build_ui(self):
        self.outer = tk.Frame(self.root, padx=24, pady=18)
        self.outer.pack(fill="both", expand=True)

        self.hdr = tk.Frame(self.outer)
        self.hdr.pack(fill="x", pady=(0, 14))

        self.title_col = tk.Frame(self.hdr)
        self.title_col.pack(side="left", fill="x", expand=True)

        t_txt = f"Desinstalar {APP_NAME}" if self.uninstall_mode else f"Instalar {APP_NAME}"
        s_txt = f"v{APP_VERSION} | Control de escritorio y teclado flotante para mando (XInput / HID)"
        self.hdr_title = tk.Label(self.title_col, text=t_txt, font=ui_font(16, "bold"), anchor="w")
        self.hdr_title.pack(fill="x")

        self.hdr_sub = tk.Label(self.title_col, text=s_txt, font=ui_font(9), anchor="w")
        self.hdr_sub.pack(fill="x", pady=(3, 0))

        self.btn_theme = MonoButton(self.hdr, "Tema", command=self._toggle_theme, padx=10, pady=5, font_size=8)
        self.btn_theme.pack(side="right", anchor="n")
        self._controls.append(self.btn_theme)

        if self.uninstall_mode:
            g_info = CardGroup(self.outer, title="Resumen")
            g_info.pack(fill="x", pady=(0, 8))
            self._card_groups.append(g_info)
            g_info.add_row(
                "Eliminacion limpia del sistema",
                "Se eliminaran los ejecutables de Rover, los accesos directos y el inicio automatico. Tu configuracion personal en AppData se conservara.",
            )
        else:
            g_dest = CardGroup(self.outer, title="Carpeta de instalacion")
            g_dest.pack(fill="x")
            self._card_groups.append(g_dest)
            self._dest_row = g_dest.add_row(
                "Ubicacion de destino",
                self.install_dir,
                lambda p: MonoButton(p, "Cambiar", command=self._pick_folder, padx=12, pady=4, font_size=8),
            )
            self.btn_browse = self._dest_row.control

            g_opt = CardGroup(self.outer, title="Opciones de instalacion")
            g_opt.pack(fill="x")
            self._card_groups.append(g_opt)

            self.sw_desktop = g_opt.add_row(
                "Acceso directo en Escritorio",
                "",
                lambda p: ToggleSwitch(p, value=True),
            ).control
            self.sw_startmenu = g_opt.add_row(
                "Acceso directo en Menu Inicio",
                "",
                lambda p: ToggleSwitch(p, value=True),
            ).control
            self.sw_startup = g_opt.add_row(
                "Iniciar automaticamente con Windows (en bandeja)",
                "",
                lambda p: ToggleSwitch(p, value=True),
            ).control
            self.sw_font = g_opt.add_row(
                f"Instalar fuente {FONT_FAMILY} en el usuario",
                "",
                lambda p: ToggleSwitch(p, value=True),
            ).control
            self.sw_launch = g_opt.add_row(
                "Ejecutar Rover al finalizar",
                "",
                lambda p: ToggleSwitch(p, value=True),
            ).control

        self.status_lbl = tk.Label(self.outer, text="Listo para continuar.", font=mono_font(8), anchor="w")
        self.status_lbl.pack(fill="x", pady=(6, 6))

        self.prog_canvas = tk.Canvas(self.outer, height=8, highlightthickness=1, bd=0)
        self.prog_canvas.pack(fill="x", pady=(0, 16))

        self.footer = tk.Frame(self.outer)
        self.footer.pack(fill="x", pady=(4, 0))

        self.btn_cancel = MonoButton(self.footer, "Cancelar", command=self._on_cancel, padx=16, pady=6)
        self.btn_cancel.pack(side="right")
        self._controls.append(self.btn_cancel)

        act_text = "Desinstalar" if self.uninstall_mode else "Instalar"
        self.btn_action = MonoButton(
            self.footer,
            act_text,
            command=self._on_action,
            primary=not self.uninstall_mode,
            danger=self.uninstall_mode,
            padx=18,
            pady=6,
        )
        self.btn_action.pack(side="right", padx=(0, 10))
        self._controls.append(self.btn_action)

    def _pick_folder(self):
        if self.installing or self.finished:
            return
        chosen = filedialog.askdirectory(initialdir=os.path.dirname(self.install_dir), title="Seleccionar carpeta")
        if chosen:
            if os.path.basename(chosen).lower() != APP_NAME.lower():
                chosen = os.path.join(chosen, APP_NAME)
            self.install_dir = chosen
            self._dest_row.sub_lbl.configure(text=self.install_dir)

    def _toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.apply_theme()

    def apply_theme(self):
        p = THEMES[self.theme_name]
        apply_dwm_window_theme(self.root, self.theme_name, corner_round=True)
        self.root.configure(bg=p["bg"])
        for f in (self.outer, self.hdr, self.title_col, self.footer):
            f.configure(bg=p["bg"])
        self.hdr_title.configure(bg=p["bg"], fg=p["fg"])
        self.hdr_sub.configure(bg=p["bg"], fg=p["fg_secondary"])
        self.status_lbl.configure(bg=p["bg"], fg=p["fg_secondary"])

        for grp in self._card_groups:
            grp.apply_theme(p)
        for ctrl in self._controls:
            ctrl.apply_theme(p)
        self._draw_progress(self._prog_val)

    def _draw_progress(self, frac):
        self._prog_val = max(0.0, min(1.0, frac))
        p = THEMES[self.theme_name]
        self.prog_canvas.configure(
            bg=p["surface"],
            highlightbackground=p["border_subtle"],
            highlightcolor=p["border_subtle"],
        )
        self.prog_canvas.delete("all")
        w = max(1, self.prog_canvas.winfo_width())
        if self._prog_val > 0.0:
            self.prog_canvas.create_rectangle(0, 0, int(w * self._prog_val), 8, fill=p["accent"], outline="")

    def _set_status(self, text, prog):
        self.root.after(0, lambda: (self.status_lbl.configure(text=text), self._draw_progress(prog)))

    def _finish_and_exit(self):
        if self._pending_rmdir:
            schedule_deferred_rmdir(self._pending_rmdir)
            self._pending_rmdir = None
        self.root.destroy()

    def _on_cancel(self):
        if not self.installing:
            self._finish_and_exit()

    def _on_action(self):
        if self.finished:
            self._finish_and_exit()
            return
        if self.installing:
            return
        self.installing = True
        self.btn_action.set_enabled(False)
        self.btn_cancel.set_enabled(False)
        if not self.uninstall_mode:
            self.btn_browse.set_enabled(False)

        target = self._run_uninstall if self.uninstall_mode else self._run_install
        threading.Thread(target=target, daemon=True).start()

    def _run_install(self):
        try:
            dest = self.install_dir
            exe_dest = os.path.join(dest, f"{APP_NAME}.exe")
            uninst_dest = os.path.join(dest, "Uninstall.exe")
            ico_dest = os.path.join(dest, "app.ico")

            self._set_status("Cerrando instancias previas...", 0.12)
            stop_running_app(exe_dest)

            self._set_status("Copiando archivos de Rover...", 0.30)
            os.makedirs(dest, exist_ok=True)
            payload_exe = get_resource_path(os.path.join("payload", f"{APP_NAME}.exe"))
            if not os.path.exists(payload_exe):
                raise FileNotFoundError(f"No se encontro {payload_exe}")
            shutil.copy2(payload_exe, exe_dest)

            ico_src = get_resource_path(os.path.join("assets", "app.ico"))
            if os.path.exists(ico_src):
                shutil.copy2(ico_src, ico_dest)

            if getattr(sys, "frozen", False):
                shutil.copy2(sys.executable, uninst_dest)

            if self.sw_font.get():
                self._set_status("Instalando fuente JetBrainsMono NF...", 0.50)
                user_fonts = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")
                os.makedirs(user_fonts, exist_ok=True)
                font_src_dir = get_resource_path(os.path.join("assets", "fonts"))
                if os.path.isdir(font_src_dir):
                    with winreg.CreateKey(
                        winreg.HKEY_CURRENT_USER,
                        r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
                    ) as k:
                        for fname in os.listdir(font_src_dir):
                            if fname.lower().endswith(".ttf"):
                                fdest = os.path.join(user_fonts, fname)
                                if not os.path.exists(fdest):
                                    shutil.copy2(os.path.join(font_src_dir, fname), fdest)
                                winreg.SetValueEx(
                                    k,
                                    f"{os.path.splitext(fname)[0]} (TrueType)",
                                    0,
                                    winreg.REG_SZ,
                                    fdest,
                                )

            self._set_status("Creando accesos directos...", 0.72)
            appdata = os.environ.get("APPDATA", "")
            desktop = get_desktop_dir()
            start_menu = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME)
            startup = get_startup_dir()

            if self.sw_desktop.get():
                create_shortcut(os.path.join(desktop, f"{APP_NAME}.lnk"), exe_dest, "", dest, ico_dest)
            if self.sw_startmenu.get():
                create_shortcut(os.path.join(start_menu, f"{APP_NAME}.lnk"), exe_dest, "", dest, ico_dest)
                if os.path.exists(uninst_dest):
                    create_shortcut(
                        os.path.join(start_menu, f"Desinstalar {APP_NAME}.lnk"),
                        uninst_dest,
                        "--uninstall",
                        dest,
                        ico_dest,
                    )
            if self.sw_startup.get():
                create_shortcut(os.path.join(startup, f"{APP_NAME}.lnk"), exe_dest, "--minimized", dest, ico_dest)
                remove_legacy_startup_shortcuts(startup)

            self._set_status("Registrando en Windows...", 0.88)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH) as key:
                winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
                winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
                winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "vTrxn")
                winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, dest)
                if os.path.exists(ico_dest):
                    winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, ico_dest)
                if os.path.exists(uninst_dest):
                    winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninst_dest}" --uninstall')
                winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)

            if self.sw_launch.get():
                subprocess.Popen([exe_dest], cwd=dest)

            self._set_status("Instalacion completada.", 1.0)
            self.root.after(0, self._mark_done)
        except Exception as exc:
            self._set_status(f"Error: {exc}", 0.0)
            self.root.after(0, self._mark_error)

    def _run_uninstall(self):
        try:
            self._set_status("Cerrando Rover...", 0.20)
            stop_running_app()

            self._set_status("Eliminando accesos directos...", 0.50)
            appdata = os.environ.get("APPDATA", "")
            desktop_lnk = os.path.join(get_desktop_dir(), f"{APP_NAME}.lnk")
            start_menu_dir = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME)
            startup_lnk = os.path.join(get_startup_dir(), f"{APP_NAME}.lnk")
            for p in (desktop_lnk, startup_lnk):
                if os.path.exists(p):
                    os.remove(p)
            if os.path.isdir(start_menu_dir):
                shutil.rmtree(start_menu_dir, ignore_errors=True)

            self._set_status("Limpiando registro...", 0.78)
            install_loc = default_install_dir()
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH) as k:
                    reg_loc, _ = winreg.QueryValueEx(k, "InstallLocation")
                    if isinstance(reg_loc, str) and reg_loc.strip():
                        install_loc = os.path.abspath(reg_loc.strip())
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH)
            except Exception:
                pass

            if os.path.isdir(install_loc):
                self._pending_rmdir = install_loc

            self._set_status("Desinstalacion completada.", 1.0)
            self.root.after(0, self._mark_done)
        except Exception as exc:
            self._set_status(f"Error: {exc}", 0.0)
            self.root.after(0, self._mark_error)

    def _mark_done(self):
        self.installing = False
        self.finished = True
        self.btn_action.set_text("Finalizar")
        self.btn_action.set_primary(True)
        self.btn_action.set_enabled(True)
        self.btn_action.focus_set()

    def _mark_error(self):
        self.installing = False
        self.btn_action.set_enabled(True)
        self.btn_cancel.set_enabled(True)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    is_uninst = "--uninstall" in [a.lower() for a in sys.argv[1:]]
    SetupApp(uninstall_mode=is_uninst).run()
