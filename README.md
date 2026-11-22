# Rover

**Rover** es una utilidad ligera para Windows que convierte cualquier mando compatible con XInput o HID en un raton y teclado flotante para tu escritorio. Detecta el mando automaticamente, alterna entre Modo Juego y Modo Mouse con doble toque, incluye un teclado en pantalla de 4 capas compatible con Netflix y navegadores, y ofrece respuesta acustica tactil inspirada en los intermitentes de cabina de Volvo.

## Caracteristicas principales

- **Deteccion automatica (XInput + WinMM HID):** Escanea los 4 slots XInput (`xinput1_4`, `xinput1_3`, `xinput9_1_0`) con cambio automatico al mando activo y soporte de respaldo HID / DirectInput (`winmm`).
- **Teclado flotante multicapa con Key-Preview Pop-up:**
  - 4 capas completas: minusculas (`abc`), mayuscula de 1 toque (`Mayus`), bloqueo de mayusculas (`CAPS`) y capa de simbolos y vocales acentuadas (`#+=`, `á, é, í, ó, ú, ü, ¿, ¡, @, #`).
  - Animacion emergente **Key-Preview Pop-up** sobre la tecla accionada para lectura clara a distancia.
  - Preservacion estricta de foco (`WS_EX_NOACTIVATE` + `SWP_NOACTIVATE`) e inyeccion hibrida `VkKeyScanW` + `ScanCode` + `Unicode` compatible con Netflix (app y navegador en pantalla completa).
- **Aislamiento de flancos en el boton B (`Escape` / `Cerrar`):** Por defecto `B` esta asignado a `Tecla Escape`. Cuando el teclado flotante esta abierto, `B` lo cierra limpiamente y consume el flanco para no enviar `Esc` a la aplicacion activa; cuando el teclado esta cerrado, `B` actua directamente como `Escape`.
- **Acustica tactil estilo Volvo:** Sintesis PCM en memoria de baja latencia (`tick` / `tock` calido y amortiguado) al navegar, escribir o cambiar de modo, con interruptor rapido para activarlo o silenciarlo.
- **Diseno Nordic Cockpit (100% mate, sin glassmorphism):** Paletas *Obsidian Cockpit* (oscuro) y *Daylight Instrument* (claro) verificadas con contraste WCAG AAA y acento focal Ambar Volvo (`#E5A93C`).

## Controles por defecto en Modo Mouse

| Control | Accion en Modo Mouse | Accion en Teclado Flotante |
| --- | --- | --- |
| Doble clic `-` o `Home` | Alternar entre Modo Juego y Modo Mouse | Salir a Modo Juego |
| 1 clic `-` o `Home` | Mostrar u ocultar el teclado flotante | Cerrar teclado flotante |
| Stick izquierdo | Mover el cursor | Navegar por las teclas |
| Stick derecho | Scroll vertical y horizontal | - |
| `A` | Clic izquierdo (auto-abre teclado en texto) | Escribir tecla activa |
| `B` | Tecla Escape (`Esc`) | Cerrar teclado (sin enviar `Esc`) |
| `X` | Abrir o cerrar teclado flotante | Borrar (`Backspace` con repeticion) |
| `Y` | Clic derecho | Espacio (con repeticion) |
| `LT` / `RT` | Modo precision / Atras (`Alt + Izq`) | Capa Simbolos (`#+=`) / - |
| `LB` / `RB` | Sin asignar | Mover cursor de texto (`<` / `>`) |
| `L3` / `R3` | Play / Pausa multimedia / Sin asignar | Alternar `Mayus/CAPS` / Posicion Arriba/Abajo |
| `Start (+)` | Tecla Enter | Enviar `Enter` y cerrar teclado |
| D-Pad | Scroll continuo (reasignable) | Navegar por las teclas |

## Ejecutar o compilar desde codigo fuente

Requiere Python 3.11+ en Windows.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python Rover.py
```

Para generar los ejecutables independientes (`Rover.exe` y `Rover-Setup.exe`):

```powershell
.\.venv\Scripts\pip install pyinstaller
.\.venv\Scripts\python -m PyInstaller --clean Rover.spec
mkdir payload -Force
copy dist\Rover.exe payload\Rover.exe
.\.venv\Scripts\python -m PyInstaller --clean Rover-Setup.spec
```

La configuracion personal se guarda de forma atomica en `%APPDATA%\Rover\config.json`.
