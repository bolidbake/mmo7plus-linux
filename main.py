#!/usr/bin/env python3
"""
Mad Catz M.M.O. 7+ Linux Configurator
Launch entry point.
"""

import sys
import os
import logging

# Ensure package directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from mmo7.gui import MainWindow


def main():
    os.environ.setdefault("MMO7_DEBUG", "1")
    os.environ.setdefault("MMO7_ALLOW_WRITES", "1")
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mmo7", "debug.log")
    debug_on = os.environ.get("MMO7_DEBUG", "1") != "0"
    level = logging.DEBUG if debug_on else logging.INFO
    handlers = [logging.StreamHandler(sys.stderr)]
    try:
        handlers.append(logging.FileHandler(log_path, mode="a", encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    logging.getLogger(__name__).info(
        "Starting MMO7 configurator (MMO7_DEBUG=%s, MMO7_ALLOW_WRITES=%s, log=%s)",
        os.environ.get("MMO7_DEBUG"), os.environ.get("MMO7_ALLOW_WRITES"), log_path,
    )

    # Enable High DPI scaling
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland;xcb")
    # Suppress noisy Wayland text-input focus warnings
    rules = os.environ.get("QT_LOGGING_RULES", "")
    extra = "qt.qpa.wayland.textinput.warning=false"
    if "qt.qpa.wayland.textinput" not in rules:
        os.environ["QT_LOGGING_RULES"] = f"{rules};{extra}".strip(";")
    app = QApplication(sys.argv)
    app.setApplicationName("Mad Catz M.M.O. 7+ Configurator")
    app.setOrganizationName("MadCatzLinux")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
