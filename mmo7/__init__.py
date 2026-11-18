"""Mad Catz M.M.O. 7+ Linux Configuration Package."""

import logging
import os
import sys

__version__ = "1.1.0"


def main():
    """Entry point for the `mmo7-config` GUI executable."""
    os.environ.setdefault("MMO7_DEBUG", "0")
    os.environ.setdefault("MMO7_ALLOW_WRITES", "1")

    debug_val = os.environ.get("MMO7_DEBUG", "0").lower()
    debug_on = debug_val in ("1", "true", "yes", "debug")

    handlers = [logging.StreamHandler(sys.stderr)]
    if debug_on:
        cfg_dir = os.path.join(os.path.expanduser("~"), ".config", "mmo7-config")
        try:
            os.makedirs(cfg_dir, exist_ok=True)
            log_path = os.path.join(cfg_dir, "debug.log")
            handlers.append(logging.FileHandler(log_path, mode="a", encoding="utf-8"))
        except OSError:
            pass

    level = logging.DEBUG if debug_on else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    if debug_on:
        logging.getLogger(__name__).info(
            "Starting MMO7 configurator v%s (MMO7_DEBUG=%s, MMO7_ALLOW_WRITES=%s)",
            __version__, os.environ.get("MMO7_DEBUG"), os.environ.get("MMO7_ALLOW_WRITES"),
        )

    os.environ.setdefault("QT_QPA_PLATFORM", "wayland;xcb")
    rules = os.environ.get("QT_LOGGING_RULES", "")
    extra = "qt.qpa.wayland.textinput.warning=false"
    if "qt.qpa.wayland.textinput" not in rules:
        os.environ["QT_LOGGING_RULES"] = f"{rules};{extra}".strip(";")

    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication
    from .gui import MainWindow, asset_path

    app = QApplication(sys.argv)
    app.setApplicationName("Mad Catz M.M.O. 7+ Configurator")
    app.setDesktopFileName("madcatz-mmo7")
    app.setOrganizationName("MadCatzLinux")
    icon_file = asset_path("device.png")
    if os.path.exists(icon_file):
        app.setWindowIcon(QIcon(icon_file))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
