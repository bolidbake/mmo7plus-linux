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

## Full System Installation

### Option A: Native CachyOS / Arch Linux Package (`makepkg`)

Installs `/usr/bin/mmo7-config`, the `udev` rule (`/usr/lib/udev/rules.d/99-madcatz-mmo7.rules`), the desktop menu launcher (`madcatz-mmo7.desktop`), and application icon, tracked cleanly by `pacman`:

```fish
sudo pacman -S --needed python-pyqt6 python-build python-installer python-setuptools python-wheel
makepkg -si
sudo udevadm control --reload-rules; and sudo udevadm trigger
```

Once installed, launch **Mad Catz M.M.O. 7+ Configurator** from your desktop application launcher or run:

```fish
mmo7-config
```

### Option B: Generic Linux Installer Script

```fish
./install.sh
```

### Option C: Run Directly Without Installing

```fish
sudo cp 99-madcatz-mmo7.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules; and sudo udevadm trigger
python3 main.py
```

### Optional Environment Variables (Fish Shell)

```fish
# Disable debug logging (enabled by default in ~/.config/mmo7-config/debug.log):
env MMO7_DEBUG=0 mmo7-config

# Run in read-only mode (disable hardware writes):
env MMO7_ALLOW_WRITES=0 mmo7-config
```
