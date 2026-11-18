# Mad Catz M.M.O. 7+ Configurator for Linux

[![GitHub Release](https://img.shields.io/github/v/release/bolidbake/mmo7plus-linux?style=for-the-badge&logo=github&color=e60012)](https://github.com/bolidbake/mmo7plus-linux/releases/latest)
[![Download Package](https://img.shields.io/badge/Download-Arch%20%2F%20CachyOS%20Package-1793d1?style=for-the-badge&logo=archlinux)](https://github.com/bolidbake/mmo7plus-linux/releases/latest/download/mmo7-config-1.1.0-3-any.pkg.tar.zst)
[![License](https://img.shields.io/badge/License-MIT-333338?style=for-the-badge)](LICENSE)

A native Linux PyQt6 configuration suite for the **Mad Catz M.M.O. 7+** gaming mouse, supporting both the **2.4 GHz wireless dongle (`0738:1c02`)** and **USB wired cable (`0738:0c19`)** with automatic hotplug priority switching.

---

## ⚡ Quick Download & Installation

### Option 1: One-Command Install (CachyOS / Arch Linux)
Install the pre-built package directly into your system with `pacman` (no manual compilation or git cloning required):

```bash
sudo pacman -U https://github.com/bolidbake/mmo7plus-linux/releases/latest/download/mmo7-config-1.1.0-3-any.pkg.tar.zst
```

Or download the `.pkg.tar.zst` file from the **[Releases Page](https://github.com/bolidbake/mmo7plus-linux/releases/latest)** and install it locally:

```bash
sudo pacman -U ~/Downloads/mmo7-config-1.1.0-3-any.pkg.tar.zst
```

### Option 2: One-Line Generic Linux Installer (Ubuntu, Fedora, Debian, etc.)
Download and install the latest version automatically via `curl`:

```bash
curl -sSL https://raw.githubusercontent.com/bolidbake/mmo7plus-linux/main/install.sh | bash
```

---

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
  - 4 independent DPI stages (`200–26,000 DPI` in `200 DPI` steps) with stage enable mask, stage colors, and **independent X / Y axis DPI scaling**.
  - **Sensor Angle Tuning (Rotary Angle Calibration)**: Interactive -30° to +30° wrist orientation correction with a real-time tracking axis tilt diagram.
  - Precision Aim (`EasyAim`) target DPI (`50–25,500 DPI`), Lift-Off Distance (`LOD`), and Linear Angle Snapping.
- **RGB Lighting & Hardware Polling Rate**:
  - Live lighting preview and configuration (`Off`, `Static`, `Breathing`, `Neon`, `Color Loop`), speed, brightness, and sleep timer.
  - Hardware polling rate selection (`125 Hz`, `250 Hz`, `500 Hz`, `1000 Hz`).
- **Onboard Profile Manager & H.U.D. Themes**:
  - Switch between 5 hardware profiles, live battery/DPI/profile monitoring, and import/export `.json` or Windows `.profile` files.
  - Built-in industrial H.U.D. themes (*Mad Catz H.U.D. Crimson*, *Cyborg R.A.T. Orange*, *Stealth Ops Cyan*, *Venom Matrix Green*).

## Build & Install from Source (Optional)

If you prefer building directly from git instead of downloading the pre-built release package:

### Option A: Native Arch / CachyOS Build (`makepkg`)

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

### Optional Environment Variables

```fish
# Enable verbose debug logging to stderr and ~/.config/mmo7-config/debug.log (disabled by default):
env MMO7_DEBUG=1 mmo7-config

# Run in read-only mode (disable hardware writes):
env MMO7_ALLOW_WRITES=0 mmo7-config
```
