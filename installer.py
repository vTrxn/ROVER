import ctypes
from ctypes import wintypes
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog
import winreg

from ui_theme import (
    FONT_FAMILY,
    THEMES,
    MonoButton,
    ToggleSwitch,
    apply_dwm_window_theme,
    font_tuple,
    get_resource_path,
    load_bundled_fonts,
)

APP_NAME = "Rover"
APP_VERSION = "2.0.0"
UNINSTALL_REG_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Rover"


def default_install_dir():
    local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return os.path.join(local, "Programs", APP_NAME)


def get_desktop_dir():
    try:
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        # CSIDL_DESKTOPDIRECTORY resolves redirected OneDrive desktop paths reliably
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0 and buf.value:
            return buf.value
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def create_shortcut(lnk_path, target, args="", workdir="", icon_path=""):
    os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
    ps = (
        f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{lnk_path}");'
        f'$s.TargetPath="{target}";'
        f'$s.Arguments="{args.replace(chr(34), "`" + chr(34))}";'
        f'$s.WorkingDirectory="{workdir}";'
    )
    if icon_path:
        ps += f'$s.IconLocation="{icon_path}";'
    ps += "$s.Save()"
    subprocess.run(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
        creationflags=0x08000000,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def stop_running_app(exe_path=None):
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
            "-WindowStyle",
            "Hidden",
            "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -like '*BedAssistant.py*' -or $_.CommandLine -like '*Rover.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
        ],
        creationflags=0x08000000,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class SetupApp:
    def __init__(self, uninstall_mode=False):
        self.uninstall_mode = uninstall_mode
        self.theme_name = "dark"
        self.installing = False
        self.finished = False
        self.install_dir = default_install_dir()

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

        self._containers = []
        self._labels = []
        self._separators = []
        self._bordered_boxes = []
        self._controls = []

        self._build_ui()
        self.apply_theme()
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        req_w = max(580 if not uninstall_mode else 520, self.root.winfo_reqwidth() + 8)
        req_h = min(sh - 60, self.root.winfo_reqheight() + 8)
        self._center(min(sw - 40, req_w), req_h)

    def _center(self, w, h):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _build_ui(self):
        self.outer = tk.Frame(self.root, padx=24, pady=16)
        self.outer.pack(fill="both", expand=True)
        self._containers.append(self.outer)

        hdr = tk.Frame(self.outer)
        hdr.pack(fill="x", pady=(0, 12))
        self._containers.append(hdr)

        title_col = tk.Frame(hdr)
        title_col.pack(side="left", fill="x", expand=True)
        self._containers.append(title_col)

        t_txt = f"Desinstalar {APP_NAME}" if self.uninstall_mode else f"Instalar {APP_NAME}"
        s_txt = f"v{APP_VERSION} | Control de PC con mando (XInput)"
        self.hdr_title = tk.Label(title_col, text=t_txt, font=font_tuple(15, "bold"), anchor="w")
        self.hdr_title.pack(fill="x")
        self._labels.append(self.hdr_title)

        self.hdr_sub = tk.Label(title_col, text=s_txt, font=font_tuple(8), anchor="w")
        self.hdr_sub.pack(fill="x", pady=(3, 0))
        self._labels.append(self.hdr_sub)

        self.btn_theme = MonoButton(hdr, "Invertir tema", command=self._toggle_theme, padx=10, pady=5, font_size=8)
        self.btn_theme.pack(side="right", anchor="n")
        self._controls.append(self.btn_theme)

        if self.uninstall_mode:
            box = tk.Frame(self.outer, padx=14, pady=14, highlightthickness=1)
            box.pack(fill="x", pady=(4, 14))
            self._bordered_boxes.append(box)
            self._containers.append(box)

            msg = tk.Label(
                box,
                text="Se eliminara Rover, sus accesos directos y el inicio automatico. Tu configuracion personal en AppData se conservara.",
                font=font_tuple(9),
                wraplength=430,
                justify="left",
                anchor="w",
            )
            msg.pack(fill="x")
            self._labels.append(msg)
        else:
            lbl_dest = tk.Label(self.outer, text="Carpeta de instalacion", font=font_tuple(9, "bold"), anchor="w")
            lbl_dest.pack(fill="x", pady=(0, 5))
            self._labels.append(lbl_dest)

            dest_box = tk.Frame(self.outer, padx=12, pady=10, highlightthickness=1)
            dest_box.pack(fill="x", pady=(0, 14))
            self._bordered_boxes.append(dest_box)
            self._containers.append(dest_box)

            self.dest_lbl = tk.Label(dest_box, text=self.install_dir, font=font_tuple(8), anchor="w")
            self.dest_lbl.pack(side="left", fill="x", expand=True, padx=(0, 10))
            self._labels.append(self.dest_lbl)

            self.btn_browse = MonoButton(dest_box, "Cambiar", command=self._pick_folder, padx=10, pady=4, font_size=8)
            self.btn_browse.pack(side="right")
            self._controls.append(self.btn_browse)

            lbl_opt = tk.Label(self.outer, text="Opciones", font=font_tuple(9, "bold"), anchor="w")
            lbl_opt.pack(fill="x", pady=(0, 5))
            self._labels.append(lbl_opt)

            opt_box = tk.Frame(self.outer, highlightthickness=1)
            opt_box.pack(fill="x", pady=(0, 14))
            self._bordered_boxes.append(opt_box)
            self._containers.append(opt_box)

            self.sw_desktop = self._add_opt_row(opt_box, "Acceso directo en Escritorio", True, is_first=True)
            self.sw_startmenu = self._add_opt_row(opt_box, "Acceso directo en Menu Inicio", True)
            self.sw_startup = self._add_opt_row(opt_box, "Iniciar con Windows (en bandeja)", True)
            self.sw_font = self._add_opt_row(opt_box, f"Instalar fuente {FONT_FAMILY}", True)
            self.sw_launch = self._add_opt_row(opt_box, "Abrir Rover al finalizar", True)

        self.status_lbl = tk.Label(self.outer, text="Listo para continuar.", font=font_tuple(8), anchor="w")
        self.status_lbl.pack(fill="x", pady=(2, 6))
        self._labels.append(self.status_lbl)

        self.prog_canvas = tk.Canvas(self.outer, height=8, highlightthickness=1, bd=0)
        self.prog_canvas.pack(fill="x", pady=(0, 16))
        self._prog_val = 0.0

        footer = tk.Frame(self.outer)
        footer.pack(fill="x", pady=(4, 0))
        self._containers.append(footer)

        self.btn_cancel = MonoButton(footer, "Cancelar", command=self._on_cancel, padx=16, pady=6)
        self.btn_cancel.pack(side="right")
        self._controls.append(self.btn_cancel)

        act_text = "Desinstalar" if self.uninstall_mode else "Instalar"
        self.btn_action = MonoButton(footer, act_text, command=self._on_action, primary=True, padx=18, pady=6)
        self.btn_action.pack(side="right", padx=(0, 10))
        self._controls.append(self.btn_action)

    def _add_opt_row(self, parent_box, text, default_val, is_first=False):
        if not is_first:
            sep = tk.Frame(parent_box, height=1)
            sep.pack(fill="x")
            self._separators.append(sep)
        row = tk.Frame(parent_box, padx=12, pady=6)
        row.pack(fill="x")
        self._containers.append(row)

        lbl = tk.Label(row, text=text, font=font_tuple(9), anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        self._labels.append(lbl)

        sw = ToggleSwitch(row, value=default_val)
        sw.pack(side="right")
        self._controls.append(sw)
        return sw

    def _pick_folder(self):
        if self.installing or self.finished:
            return
        chosen = filedialog.askdirectory(initialdir=os.path.dirname(self.install_dir), title="Seleccionar carpeta")
        if chosen:
            if os.path.basename(chosen).lower() != APP_NAME.lower():
                chosen = os.path.join(chosen, APP_NAME)
            self.install_dir = chosen
            self.dest_lbl.configure(text=self.install_dir)

    def _toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.apply_theme()

    def apply_theme(self):
        p = THEMES[self.theme_name]
        apply_dwm_window_theme(self.root, self.theme_name, corner_round=True)
        self.root.configure(bg=p["bg"])
        for c in self._containers:
            c.configure(bg=p["bg"])
        for b in self._bordered_boxes:
            b.configure(bg=p["bg"], highlightbackground=p["fg"], highlightcolor=p["fg"])
        for s in self._separators:
            s.configure(bg=p["fg"])
        for lbl in self._labels:
            lbl.configure(bg=p["bg"], fg=p["fg"])
        for ctrl in self._controls:
            ctrl.apply_theme(p)
        self._draw_progress(self._prog_val)

    def _draw_progress(self, frac):
        self._prog_val = max(0.0, min(1.0, frac))
        p = THEMES[self.theme_name]
        self.prog_canvas.configure(bg=p["bg"], highlightbackground=p["fg"], highlightcolor=p["fg"])
        self.prog_canvas.delete("all")
        w = max(1, self.prog_canvas.winfo_width())
        if self._prog_val > 0.0:
            self.prog_canvas.create_rectangle(0, 0, int(w * self._prog_val), 8, fill=p["fg"], outline="")

    def _set_status(self, text, prog):
        self.root.after(0, lambda: (self.status_lbl.configure(text=text), self._draw_progress(prog)))

    def _on_cancel(self):
        if not self.installing:
            self.root.destroy()

    def _on_action(self):
        if self.finished:
            self.root.destroy()
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
                    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as k:
                        for fname in os.listdir(font_src_dir):
                            if fname.lower().endswith(".ttf"):
                                fdest = os.path.join(user_fonts, fname)
                                if not os.path.exists(fdest):
                                    shutil.copy2(os.path.join(font_src_dir, fname), fdest)
                                winreg.SetValueEx(k, f"{os.path.splitext(fname)[0]} (TrueType)", 0, winreg.REG_SZ, fdest)

            self._set_status("Creando accesos directos...", 0.72)
            appdata = os.environ.get("APPDATA", "")
            desktop = get_desktop_dir()
            start_menu = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME)
            startup = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")

            if self.sw_desktop.get():
                create_shortcut(os.path.join(desktop, f"{APP_NAME}.lnk"), exe_dest, "", dest, ico_dest)
            if self.sw_startmenu.get():
                create_shortcut(os.path.join(start_menu, f"{APP_NAME}.lnk"), exe_dest, "", dest, ico_dest)
                if os.path.exists(uninst_dest):
                    create_shortcut(os.path.join(start_menu, f"Desinstalar {APP_NAME}.lnk"), uninst_dest, "--uninstall", dest, ico_dest)
            if self.sw_startup.get():
                create_shortcut(os.path.join(startup, f"{APP_NAME}.lnk"), exe_dest, "--minimized", dest, ico_dest)
                for legacy_name in ("BedAssistant.lnk", "GameSir Assistant.lnk"):
                    legacy = os.path.join(startup, legacy_name)
                    if os.path.exists(legacy):
                        os.remove(legacy)

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
            startup_lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", f"{APP_NAME}.lnk")
            for p in (desktop_lnk, startup_lnk):
                if os.path.exists(p):
                    os.remove(p)
            if os.path.isdir(start_menu_dir):
                shutil.rmtree(start_menu_dir, ignore_errors=True)

            self._set_status("Limpiando registro...", 0.75)
            install_loc = default_install_dir()
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH) as k:
                    install_loc, _ = winreg.QueryValueEx(k, "InstallLocation")
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_REG_PATH)
            except Exception:
                pass

            if os.path.isdir(install_loc):
                subprocess.Popen(
                    f'cmd /c timeout /t 2 /nobreak >nul & rmdir /s /q "{install_loc}"',
                    shell=True,
                    creationflags=0x08000000,
                )

            self._set_status("Desinstalacion completada.", 1.0)
            self.root.after(0, self._mark_done)
        except Exception as exc:
            self._set_status(f"Error: {exc}", 0.0)
            self.root.after(0, self._mark_error)

    def _mark_done(self):
        self.installing = False
        self.finished = True
        self.btn_action.set_text("Finalizar")
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
