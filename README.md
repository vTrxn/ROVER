# Rover

**Rover** es una aplicacion ligera para Windows que convierte cualquier control compatible con XInput en un raton y teclado para tu escritorio. Detecta el mando automaticamente, permite alternar entre modo juego y modo mouse con un toque, incluye teclado flotante en pantalla y te deja reasignar cada boton, gatillo y direccion del D-Pad desde un esquema interactivo.

## Que incluye

- **Deteccion automatica:** Escanea los 4 slots XInput de forma continua (`xinput1_4`, `xinput1_3` y `xinput9_1_0`) con cambio automatico al control que uses si tienes mas de uno conectado, y respaldo HID / DirectInput (`winmm`) para controles por Bluetooth o cable.
- **Control de cursor y scroll:** Stick izquierdo para mover el puntero con zona muerta, curva de aceleracion y modo precision con gatillo configurable; stick derecho para scroll vertical y horizontal.
- **Teclado flotante en pantalla:** Se abre desde el control o al detectar un campo de texto, navegable con D-Pad o stick izquierdo.
- **Diagrama interactivo de botones:** Muestra pulsaciones y movimiento de los sticks en tiempo real, y permite reasignar acciones de raton, scroll, multimedia, volumen, zoom o atajos en los 11 botones y 4 direcciones del D-Pad.
- **Interfaz de dos colores invertibles:** Paleta en gris mate oscuro (`#1E1E1E`) y blanco (`#F5F5F5`), con tipografia `JetBrainsMono NF` embebida e inversion de colores entre tema oscuro y claro en ajustes, teclado flotante, avisos y bandeja del sistema.
- **Instalador y version portable:** Puede ejecutarse directo como ejecutable portable o instalarse con accesos directos, inicio automatico en bandeja y registro de desinstalacion en Windows.

## Controles por defecto en Modo Mouse

| Control | Accion |
| --- | --- |
| Doble clic `-` o `Home` | Alternar entre Modo Juego y Modo Mouse |
| 1 clic `-` o `Home` | Mostrar u ocultar el teclado flotante |
| Stick izquierdo | Mover el cursor |
| Stick derecho | Scroll vertical y horizontal |
| `A` / `B` | Clic izquierdo / Clic derecho |
| `X` | Abrir o cerrar teclado flotante |
| `LT` / `RT` | Modo precision / Atras (`Alt + Izq`) |
| `L3` | Play / Pausa multimedia |
| D-Pad | Scroll continuo (reasignable) |

## Ejecutar o compilar desde codigo fuente

Requiere Python 3.11+ en Windows.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python Rover.py
```

Para generar los ejecutables independientes (`Rover.exe` y `Rover-Setup.exe`) en un entorno limpio:

```powershell
.\.venv\Scripts\pip install pyinstaller
.\.venv\Scripts\python -m PyInstaller --onefile --noconsole --clean --name Rover --icon "assets\app.ico" --add-data "assets;assets" Rover.py
mkdir payload -Force
copy dist\Rover.exe payload\Rover.exe
.\.venv\Scripts\python -m PyInstaller --onefile --noconsole --clean --name Rover-Setup --icon "assets\app.ico" --add-data "assets;assets" --add-data "payload;payload" installer.py
```

La configuracion personal se guarda en `%APPDATA%\Rover\config.json`.
