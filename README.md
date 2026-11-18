# Mad Catz M.M.O. 7+ Configurator for Linux

A native Linux PyQt6 configuration suite for the **Mad Catz M.M.O. 7+** gaming mouse, supporting both the **2.4 GHz wireless dongle (`0738:1c02`)** and **USB wired cable (`0738:0c19`)** with automatic hotplug priority switching.

## Features

- **Interactive Visual Button Remapping**:
  - Top View and Side View diagrams with callout pins matching the original Mad Catz H.U.D.
  - Two-column H.U.D. Function Menu (`Recover Default`, `Keyboard Function`, `Mouse Function`, `Multimedia`, `Internet`, `Word / Editing`, `System`, `Macro`) plus press-to-bind key capture and a full 25-slot table editor.
  - Normal Layer and Mode Shift (`FN`) Layer configuration with Hold/Toggle support and Left/Right Action Lock (`LeftActive` / `RightActive`).
- **Onboard Macro Builder (`Report 0x09`)**:
  - Live keyboard recording (fixed delay or real measured typing delays) and manual key/mouse/delay step insertion (up to 50 hardware events per macro).
  - Playback loop modes: *Repeat N Times* (`1–255`), *Toggle (Until Pressed Again)*, and *Hold (While Button Held)*.
  - Import/export support for both `.json` and Windows Mad Catz H.U.D. `.macro` files.
- **DPI & Sensor Settings**:
  - 4 independent DPI stages (`200–26,000 DPI` in `200 DPI` steps) with stage enable mask and stage colors.
  - Precision Aim (`EasyAim`) target DPI (`50–25,500 DPI`), Lift-Off Distance (`LOD`), and Linear Angle Snapping.
- **RGB Lighting & Polling Rate**:
  - Live lighting preview and configuration (`Off`, `Static`, `Breathing`, `Neon`, `Color Loop`), speed, brightness, and sleep timer.
  - Hardware polling rate selection (`125 Hz`, `250 Hz`, `500 Hz`, `1000 Hz`).
- **Onboard Profile Manager & H.U.D. Themes**:
  - Switch between 5 hardware profiles, live battery/DPI/profile monitoring, and import/export `.json` or Windows `.profile` files.
  - Built-in industrial H.U.D. themes (*Mad Catz H.U.D. Crimson*, *Cyborg R.A.T. Orange*, *Stealth Ops Cyan*, *Venom Matrix Green*).

## Installation

### 1. Install Dependencies

**CachyOS / Arch Linux:**
```fish
sudo pacman -S python-pyqt6
```

**Or via pip:**
```fish
pip install -r requirements.txt
```

### 2. Install `udev` Permissions Rule (for non-root `/dev/hidraw` access)

```fish
sudo cp 99-madcatz-mmo7.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 3. Run the Configurator

```fish
python3 main.py
```

### Optional Environment Variables (Fish Shell)

```fish
# Disable debug logging (enabled by default):
env MMO7_DEBUG=0 python3 main.py

# Run in read-only mode (disable hardware writes):
env MMO7_ALLOW_WRITES=0 python3 main.py
```
