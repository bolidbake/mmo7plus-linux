"""
PyQt6 GUI Application for Mad Catz M.M.O. 7+ Mouse Configuration.
Features an interactive visual mouse diagram (Top & Side views with callout lines/pins
from the original MadCatz H.U.D.), press-to-bind key capture, DPI & Sensor visuals,
RGB lighting preview, polling rate, and profile management.
"""

import json
import logging
import math
import os
import struct
import sys
import threading
import time
import traceback
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QRectF, QPointF, QSize
from PyQt6.QtGui import (
    QColor, QFont, QIcon, QImage, QKeyEvent, QMouseEvent,
    QPainter, QPainterPath, QPen, QPixmap
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QComboBox, QSlider, QSpinBox,
    QCheckBox, QRadioButton, QButtonGroup, QGroupBox, QGridLayout,
    QColorDialog, QFileDialog, QMessageBox, QScrollArea, QFrame,
    QProgressBar, QStatusBar, QDialog, QTextEdit, QStackedWidget,
    QSizePolicy, QListWidget, QListWidgetItem, QLineEdit
)

from .protocol import (
    ButtonFunction, ButtonSetting, LightMode, PollingRate,
    ModifierMask, FnToggleMode, HID_KEY_NAMES, BUTTON_MAP_ORDER,
    aim_dpi_from_buttons, apply_aim_dpi, decode_aim_dpi, encode_aim_dpi,
    AIM_DPI_MIN, AIM_DPI_MAX,
    MacroLoopType, MacroStep, MacroDefinition, MACRO_KEY_NAMES, MACRO_MAX_STEPS
)
from .device import discover_mmo7, MMO7Device, DeviceInfo


ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def asset_path(filename: str) -> str:
    return os.path.join(ASSETS_DIR, filename)


# Factory defaults for each button slot (from KeysModel.cs)
DEFAULT_BUTTON_SETTINGS: Dict[str, Tuple[ButtonFunction, int, int]] = {
    "LeftClick":     (ButtonFunction.Click, 0, 0),
    "RightClick":    (ButtonFunction.Menu, 0, 0),
    "WheelClick":    (ButtonFunction.UniversalScrolling, 0, 0),
    "SwitchProfile": (ButtonFunction.ProfileCycle, 0, 0),
    "LeftActive":    (ButtonFunction.LeftActive, 0, 0),
    "RightActive":   (ButtonFunction.RightActive, 0, 0),
    "DpiLoop":       (ButtonFunction.DpiCycle, 0, 0),
    "FN":            (ButtonFunction.FN, int(FnToggleMode.Toggle), 0),
    "ShortutKey1":   (ButtonFunction.AssignShortcut, 0, 0x22),  # '5'
    "ForwardClick":  (ButtonFunction.IEForward, 0, 0),
    "BackwardClick": (ButtonFunction.IEBackward, 0, 0),
    "ShortutKey2":   (ButtonFunction.AssignShortcut, 0, 0x23),  # '6'
    "ShortutKey3":   (ButtonFunction.AssignShortcut, 0, 0x24),  # '7'
    "ShortutKey4":   (ButtonFunction.AssignShortcut, 0, 0x20),  # '3'
    "ShortutKey5":   (ButtonFunction.AssignShortcut, 0, 0x1F),  # '2'
    "ShortutKey6":   (ButtonFunction.AssignShortcut, 0, 0x1E),  # '1'
    "ShortutKey7":   (ButtonFunction.AssignShortcut, 0, 0x21),  # '4'
    "AccurateClick": (ButtonFunction.EasyAimDpi, 0, 7),         # 350 DPI
    "ShortutKey8":   (ButtonFunction.AssignShortcut, 0, 0x27),  # '0'
    "ShortutKey9":   (ButtonFunction.AssignShortcut, 0, 0x25),  # '8'
    "ShortutKey10":  (ButtonFunction.AssignShortcut, 0, 0x26),  # '9'
    "WheelLeft":     (ButtonFunction.TiltLeft, 0, 0),
    "WheelRight":    (ButtonFunction.TiltRight, 0, 0),
    "WheelDown":     (ButtonFunction.ScrollDown, 0, 0),
    "WheelUp":       (ButtonFunction.ScrollUp, 0, 0),
}


FUNCTION_DISPLAY_ITEMS: List[Tuple[str, ButtonFunction]] = [
    ("Left Click", ButtonFunction.Click),
    ("Right Click (Context Menu)", ButtonFunction.Menu),
    ("Middle Click (Universal Scroll)", ButtonFunction.UniversalScrolling),
    ("Browser Forward", ButtonFunction.IEForward),
    ("Browser Backward", ButtonFunction.IEBackward),
    ("Double Click", ButtonFunction.DoubleClick),
    ("Fire Button", ButtonFunction.Firebutton),
    ("Keyboard Shortcut", ButtonFunction.AssignShortcut),
    ("Precision Aim (EasyAim DPI)", ButtonFunction.EasyAimDpi),
    ("DPI Cycle", ButtonFunction.DpiCycle),
    ("DPI +", ButtonFunction.DpiUp),
    ("DPI -", ButtonFunction.DpiDown),
    ("Mode Shift (FN)", ButtonFunction.FN),
    ("Profile Cycle", ButtonFunction.ProfileCycle),
    ("Profile Up", ButtonFunction.ProfileUp),
    ("Profile Down", ButtonFunction.ProfileDown),
    ("Polling Rate Loop", ButtonFunction.ReportRateLoop),
    ("Left Action Lock (Hold LMB)", ButtonFunction.LeftActive),
    ("Right Action Lock (Hold RMB)", ButtonFunction.RightActive),
    ("Tilt Wheel Left", ButtonFunction.TiltLeft),
    ("Tilt Wheel Right", ButtonFunction.TiltRight),
    ("Scroll Wheel Up", ButtonFunction.ScrollUp),
    ("Scroll Wheel Down", ButtonFunction.ScrollDown),
    ("Volume Up", ButtonFunction.VolumeUp),
    ("Volume Down", ButtonFunction.VolumeDown),
    ("Mute Audio", ButtonFunction.Mute),
    ("Play / Pause Media", ButtonFunction.PlayPause),
    ("Stop Media", ButtonFunction.Stop),
    ("Next Track", ButtonFunction.NextTrack),
    ("Previous Track", ButtonFunction.PreTrack),
    ("Open Media Player", ButtonFunction.OpenPlayer),
    ("Calculator", ButtonFunction.WindowsCalculator),
    ("My Computer / Explorer", ButtonFunction.WindowsMyComputer),
    ("Email Client", ButtonFunction.WindowsEMail),
    ("Web Home", ButtonFunction.WindowsIEBrowseHome),
    ("Web Search", ButtonFunction.WindowsWwwSearch),
    ("Web Favorites", ButtonFunction.WindowsWwwFavorites),
    ("Web Refresh", ButtonFunction.WindowsWwwRefresh),
    ("Web Stop", ButtonFunction.WindowsWwwStop),
    ("Web Forward", ButtonFunction.WindowsWwwForward),
    ("Web Back", ButtonFunction.WindowsWwwBack),
    ("Super / Windows Key", ButtonFunction.WindowsKey),
    ("Disabled", ButtonFunction.Blocked),
    ("Button Off", ButtonFunction.ButtonOff),
]

FUNCTION_SHORT_NAMES: Dict[int, str] = {int(fn): label for label, fn in FUNCTION_DISPLAY_ITEMS}


# Authentic Mad Catz H.U.D. Categories & Preset Items (from KeyAssignPageViewModel.cs)
# Each preset item is (display_label, action_kind, function_code, modify_byte, key_byte)
# where action_kind is "default", "assign", or "keyboard".
HUD_CATEGORIES = [
    {
        "id": "recover",
        "title": "Recover Default",
        "icon_default": "recover_default.png",
        "icon_selected": "recover_selected.png",
        "items": [
            ("Recover to Default", "default", 0, 0, 0),
            ("Disable Button",     "assign",  int(ButtonFunction.Blocked), 0, 0),
        ],
    },
    {
        "id": "keyboard",
        "title": "Keyboard Function",
        "icon_default": "keyboard_default.png",
        "icon_selected": "keyboard_selected.png",
        "items": [],  # Rendered with the dedicated Keyboard Function panel (modifiers + key groups + press-to-bind)
    },
    {
        "id": "mouse",
        "title": "Mouse Function",
        "icon_default": "mouse_default.png",
        "icon_selected": "mouse_selected.png",
        "items": [
            ("Left Click",              "assign", int(ButtonFunction.Click), 0, 0),
            ("Right Click",             "assign", int(ButtonFunction.Menu), 0, 0),
            ("Wheel Click (Middle)",    "assign", int(ButtonFunction.UniversalScrolling), 0, 0),
            ("Wheel Up",                "assign", int(ButtonFunction.ScrollUp), 0, 0),
            ("Wheel Down",              "assign", int(ButtonFunction.ScrollDown), 0, 0),
            ("Wheel Left",              "assign", int(ButtonFunction.TiltLeft), 0, 0),
            ("Wheel Right",             "assign", int(ButtonFunction.TiltRight), 0, 0),
            ("Forward Click",           "assign", int(ButtonFunction.IEForward), 0, 0),
            ("Backward Click",          "assign", int(ButtonFunction.IEBackward), 0, 0),
            ("Precision Aim (EasyAim)", "assign", int(ButtonFunction.EasyAimDpi), 0, 7),
            ("DPI +",                   "assign", int(ButtonFunction.DpiUp), 0, 0),
            ("DPI -",                   "assign", int(ButtonFunction.DpiDown), 0, 0),
            ("DPI Loop",                "assign", int(ButtonFunction.DpiCycle), 0, 0),
            ("Switch Profile",          "assign", int(ButtonFunction.ProfileCycle), 0, 0),
            ("Left Action Lock (Hold LMB)",  "assign", int(ButtonFunction.LeftActive), 0, 0),
            ("Right Action Lock (Hold RMB)", "assign", int(ButtonFunction.RightActive), 0, 0),
            ("Mode Shift (FN)",         "assign", int(ButtonFunction.FN), 90, 0),
            ("Double Click",            "assign", int(ButtonFunction.DoubleClick), 0, 0),
            ("Fire Button",             "assign", int(ButtonFunction.Firebutton), 0, 0),
        ],
    },
    {
        "id": "multimedia",
        "title": "Multimedia",
        "icon_default": "multimedia_default.png",
        "icon_selected": "multimedia_selected.png",
        "items": [
            ("Previous Track", "assign", int(ButtonFunction.PreTrack), 0, 0),
            ("Next Track",     "assign", int(ButtonFunction.NextTrack), 0, 0),
            ("Volume Up",      "assign", int(ButtonFunction.VolumeUp), 0, 0),
            ("Volume Down",    "assign", int(ButtonFunction.VolumeDown), 0, 0),
            ("Mute",           "assign", int(ButtonFunction.Mute), 0, 0),
            ("Play / Pause",   "assign", int(ButtonFunction.PlayPause), 0, 0),
            ("Stop Media",     "assign", int(ButtonFunction.Stop), 0, 0),
        ],
    },
    {
        "id": "internet",
        "title": "Internet",
        "icon_default": "internet_default.png",
        "icon_selected": "internet_selected.png",
        "items": [
            ("Web Home Page",         "assign", int(ButtonFunction.WindowsIEBrowseHome), 0, 0),
            ("Previous Page",         "assign", int(ButtonFunction.WindowsWwwBack), 0, 0),
            ("Next Page",             "assign", int(ButtonFunction.WindowsWwwForward), 0, 0),
            ("Stop Loading",          "assign", int(ButtonFunction.WindowsWwwStop), 0, 0),
            ("Refresh Page",          "assign", int(ButtonFunction.WindowsWwwRefresh), 0, 0),
            ("Web Search",            "assign", int(ButtonFunction.WindowsWwwSearch), 0, 0),
            ("Add Favorite",          "assign", int(ButtonFunction.WindowsWwwFavorites), 0, 0),
            ("New Tab (Ctrl+T)",      "assign", int(ButtonFunction.AssignShortcut), 1, 23),
            ("E-Mail",                "assign", int(ButtonFunction.WindowsEMail), 0, 0),
        ],
    },
    {
        "id": "word",
        "title": "Word / Editing",
        "icon_default": "word_default.png",
        "icon_selected": "word_selected.png",
        "items": [
            ("Cut (Ctrl+X)",          "assign", int(ButtonFunction.AssignShortcut), 1, 27),
            ("Copy (Ctrl+C)",         "assign", int(ButtonFunction.AssignShortcut), 1, 6),
            ("Paste (Ctrl+V)",        "assign", int(ButtonFunction.AssignShortcut), 1, 25),
            ("Delete",                "assign", int(ButtonFunction.AssignShortcut), 0, 76),
            ("Find / Search (Ctrl+F)","assign", int(ButtonFunction.AssignShortcut), 1, 9),
            ("Select All (Ctrl+A)",   "assign", int(ButtonFunction.AssignShortcut), 1, 4),
            ("Undo (Ctrl+Z)",         "assign", int(ButtonFunction.AssignShortcut), 1, 29),
            ("Redo (Ctrl+Y)",         "assign", int(ButtonFunction.AssignShortcut), 1, 28),
            ("New (Ctrl+N)",          "assign", int(ButtonFunction.AssignShortcut), 1, 17),
            ("Open (Ctrl+O)",         "assign", int(ButtonFunction.AssignShortcut), 1, 18),
            ("Save (Ctrl+S)",         "assign", int(ButtonFunction.AssignShortcut), 1, 22),
            ("Print (Ctrl+P)",        "assign", int(ButtonFunction.AssignShortcut), 1, 19),
        ],
    },
    {
        "id": "system",
        "title": "System",
        "icon_default": "system_default.png",
        "icon_selected": "system_selected.png",
        "items": [
            ("Explorer (Super+E)",       "assign", int(ButtonFunction.AssignShortcut), 8, 8),
            ("Calculator",               "assign", int(ButtonFunction.WindowsCalculator), 0, 0),
            ("Zoom Out (Super+-)",       "assign", int(ButtonFunction.AssignShortcut), 8, 0x2D),
            ("Zoom In (Super+=)",        "assign", int(ButtonFunction.AssignShortcut), 8, 0x2E),
            ("Maximize (Super+Up)",      "assign", int(ButtonFunction.AssignShortcut), 8, 82),
            ("Minimize (Super+Down)",    "assign", int(ButtonFunction.AssignShortcut), 8, 81),
            ("Show Desktop (Super+D)",   "assign", int(ButtonFunction.AssignShortcut), 8, 7),
            ("Close Window (Alt+F4)",    "assign", int(ButtonFunction.AssignShortcut), 4, 61),
        ],
    },
    {
        "id": "macro",
        "title": "Macro",
        "icon_default": "macro_default.png",
        "icon_selected": "macro_selected.png",
        "items": [],  # Rendered with the Macro Assignment panel (select macro + loop mode)
    },
]

# Keyboard key sub-categories matching KeyAssignKeyboardList in the original H.U.D.
HUD_KEYBOARD_GROUPS: List[Tuple[str, List[Tuple[str, int]]]] = [
    ("All Keys", [(name, code) for code, name in sorted(HID_KEY_NAMES.items(), key=lambda x: (x[0] == 0, x[0])) if code != 0]),
    ("Numpad / Keypad", [(HID_KEY_NAMES[c], c) for c in range(0x53, 0x64) if c in HID_KEY_NAMES]),
    ("Number Row (0–9)", [(HID_KEY_NAMES[c], c) for c in range(0x1E, 0x28) if c in HID_KEY_NAMES]),
    ("Letters (A–Z)", [(HID_KEY_NAMES[c], c) for c in range(0x04, 0x1E) if c in HID_KEY_NAMES]),
    ("Function Keys (F1–F12)", [(HID_KEY_NAMES[c], c) for c in range(0x3A, 0x46) if c in HID_KEY_NAMES]),
    ("Navigation & Control", [(HID_KEY_NAMES[c], c) for c in (0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x49, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x50, 0x51, 0x52) if c in HID_KEY_NAMES]),
    ("Symbols & Punctuation", [(HID_KEY_NAMES[c], c) for c in (0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38) if c in HID_KEY_NAMES]),
]


def format_button_binding(btn: Optional[ButtonSetting], aim_dpi: Optional[int] = None,
                          macros: Optional[Dict[int, MacroDefinition]] = None) -> str:
    """Format a ButtonSetting into a concise, human-readable summary for visual callout pills."""
    if btn is None:
        return "Unassigned"
    try:
        fn_int = int(btn.function)
    except Exception:
        fn_int = 0

    if fn_int == int(ButtonFunction.AssignShortcut):
        mods = []
        if btn.modify & ModifierMask.CTRL:
            mods.append("Ctrl")
        if btn.modify & ModifierMask.SHIFT:
            mods.append("Shift")
        if btn.modify & ModifierMask.ALT:
            mods.append("Alt")
        if btn.modify & ModifierMask.WIN:
            mods.append("Super")
        key_name = HID_KEY_NAMES.get(btn.key_index, f"Key {btn.key_index}")
        return " + ".join(mods + [key_name]) if mods else key_name

    if fn_int == int(ButtonFunction.AssignMacro):
        m_idx = btn.key_index
        if macros and m_idx in macros:
            return f"Macro: {macros[m_idx].name}"
        return f"Macro #{m_idx}"

    if fn_int == int(ButtonFunction.EasyAimDpi):
        dpi = decode_aim_dpi(btn.modify, btn.key_index) or aim_dpi
        return f"Precision Aim ({dpi} DPI)" if dpi else "Precision Aim"

    if fn_int == int(ButtonFunction.FN):
        mode_str = "Toggle" if btn.modify == int(FnToggleMode.Toggle) else "Hold"
        return f"Mode Shift ({mode_str})"

    return FUNCTION_SHORT_NAMES.get(fn_int, f"Func {fn_int}")


# Map Qt Key enum + Keypad modifier to USB HID Usage ID
QT_KEY_TO_HID: Dict[int, int] = {
    Qt.Key.Key_A: 0x04, Qt.Key.Key_B: 0x05, Qt.Key.Key_C: 0x06, Qt.Key.Key_D: 0x07,
    Qt.Key.Key_E: 0x08, Qt.Key.Key_F: 0x09, Qt.Key.Key_G: 0x0A, Qt.Key.Key_H: 0x0B,
    Qt.Key.Key_I: 0x0C, Qt.Key.Key_J: 0x0D, Qt.Key.Key_K: 0x0E, Qt.Key.Key_L: 0x0F,
    Qt.Key.Key_M: 0x10, Qt.Key.Key_N: 0x11, Qt.Key.Key_O: 0x12, Qt.Key.Key_P: 0x13,
    Qt.Key.Key_Q: 0x14, Qt.Key.Key_R: 0x15, Qt.Key.Key_S: 0x16, Qt.Key.Key_T: 0x17,
    Qt.Key.Key_U: 0x18, Qt.Key.Key_V: 0x19, Qt.Key.Key_W: 0x1A, Qt.Key.Key_X: 0x1B,
    Qt.Key.Key_Y: 0x1C, Qt.Key.Key_Z: 0x1D,
    Qt.Key.Key_1: 0x1E, Qt.Key.Key_2: 0x1F, Qt.Key.Key_3: 0x20, Qt.Key.Key_4: 0x21,
    Qt.Key.Key_5: 0x22, Qt.Key.Key_6: 0x23, Qt.Key.Key_7: 0x24, Qt.Key.Key_8: 0x25,
    Qt.Key.Key_9: 0x26, Qt.Key.Key_0: 0x27,
    Qt.Key.Key_Return: 0x28, Qt.Key.Key_Escape: 0x29, Qt.Key.Key_Backspace: 0x2A,
    Qt.Key.Key_Tab: 0x2B, Qt.Key.Key_Space: 0x2C, Qt.Key.Key_Minus: 0x2D,
    Qt.Key.Key_Equal: 0x2E, Qt.Key.Key_BracketLeft: 0x2F, Qt.Key.Key_BracketRight: 0x30,
    Qt.Key.Key_Backslash: 0x31, Qt.Key.Key_Semicolon: 0x33, Qt.Key.Key_Apostrophe: 0x34,
    Qt.Key.Key_QuoteLeft: 0x35, Qt.Key.Key_Comma: 0x36, Qt.Key.Key_Period: 0x37,
    Qt.Key.Key_Slash: 0x38,
    Qt.Key.Key_F1: 0x3A, Qt.Key.Key_F2: 0x3B, Qt.Key.Key_F3: 0x3C, Qt.Key.Key_F4: 0x3D,
    Qt.Key.Key_F5: 0x3E, Qt.Key.Key_F6: 0x3F, Qt.Key.Key_F7: 0x40, Qt.Key.Key_F8: 0x41,
    Qt.Key.Key_F9: 0x42, Qt.Key.Key_F10: 0x43, Qt.Key.Key_F11: 0x44, Qt.Key.Key_F12: 0x45,
    Qt.Key.Key_Insert: 0x49, Qt.Key.Key_Home: 0x4A, Qt.Key.Key_PageUp: 0x4B,
    Qt.Key.Key_Delete: 0x4C, Qt.Key.Key_End: 0x4D, Qt.Key.Key_PageDown: 0x4E,
    Qt.Key.Key_Right: 0x4F, Qt.Key.Key_Left: 0x50, Qt.Key.Key_Down: 0x51, Qt.Key.Key_Up: 0x52,
    Qt.Key.Key_NumLock: 0x53, Qt.Key.Key_Enter: 0x58,
}

QT_KEYPAD_TO_HID: Dict[int, int] = {
    Qt.Key.Key_Slash: 0x54,
    Qt.Key.Key_Asterisk: 0x55,
    Qt.Key.Key_Minus: 0x56,
    Qt.Key.Key_Plus: 0x57,
    Qt.Key.Key_Enter: 0x58,
    Qt.Key.Key_Return: 0x58,
    Qt.Key.Key_1: 0x59, Qt.Key.Key_End: 0x59,
    Qt.Key.Key_2: 0x5A, Qt.Key.Key_Down: 0x5A,
    Qt.Key.Key_3: 0x5B, Qt.Key.Key_PageDown: 0x5B,
    Qt.Key.Key_4: 0x5C, Qt.Key.Key_Left: 0x5C,
    Qt.Key.Key_5: 0x5D, Qt.Key.Key_Clear: 0x5D,
    Qt.Key.Key_6: 0x5E, Qt.Key.Key_Right: 0x5E,
    Qt.Key.Key_7: 0x5F, Qt.Key.Key_Home: 0x5F,
    Qt.Key.Key_8: 0x60, Qt.Key.Key_Up: 0x60,
    Qt.Key.Key_9: 0x61, Qt.Key.Key_PageUp: 0x61,
    Qt.Key.Key_0: 0x62, Qt.Key.Key_Insert: 0x62,
    Qt.Key.Key_Period: 0x63, Qt.Key.Key_Delete: 0x63,
}


HUD_THEMES: Dict[str, Dict[str, str]] = {
    "hud_crimson": {
        "name": "Mad Catz H.U.D. (Crimson)",
        "bg_main": "#0d0d0f",
        "bg_panel": "#191919",
        "bg_card": "#131315",
        "bg_control": "#202024",
        "bg_hover": "#2b2b31",
        "border": "#2f2f36",
        "border_subtle": "#242429",
        "text": "#bcbcbc",
        "text_bright": "#ffffff",
        "text_muted": "#82828c",
        "primary": "#e60012",
        "primary_hover": "#ff1a2c",
        "primary_pressed": "#b8000e",
        "primary_soft": "#ff4d5a",
        "primary_disabled_bg": "#481217",
        "pill_sel_bg": "#2b1014",
        "pill_hov_bg": "#24181b",
    },
    "cyborg_orange": {
        "name": "Cyborg R.A.T. (Industrial Orange)",
        "bg_main": "#0e0e11",
        "bg_panel": "#191919",
        "bg_card": "#141417",
        "bg_control": "#222228",
        "bg_hover": "#2c2c34",
        "border": "#32323c",
        "border_subtle": "#26262e",
        "text": "#c4c4cc",
        "text_bright": "#ffffff",
        "text_muted": "#888896",
        "primary": "#ff5500",
        "primary_hover": "#ff6d1f",
        "primary_pressed": "#cc4400",
        "primary_soft": "#ff8844",
        "primary_disabled_bg": "#4d2612",
        "pill_sel_bg": "#2e1a12",
        "pill_hov_bg": "#261f1c",
    },
    "stealth_cyan": {
        "name": "Stealth Ops (Tactical Cyan)",
        "bg_main": "#0b0e12",
        "bg_panel": "#16191e",
        "bg_card": "#111419",
        "bg_control": "#1d222a",
        "bg_hover": "#262d38",
        "border": "#2c3542",
        "border_subtle": "#202731",
        "text": "#b8c4d0",
        "text_bright": "#ffffff",
        "text_muted": "#788696",
        "primary": "#00c8ff",
        "primary_hover": "#33d4ff",
        "primary_pressed": "#009ecc",
        "primary_soft": "#5ce1ff",
        "primary_disabled_bg": "#103b48",
        "pill_sel_bg": "#102834",
        "pill_hov_bg": "#17242c",
    },
    "venom_green": {
        "name": "Venom Matrix (Acid Green)",
        "bg_main": "#0b0f0c",
        "bg_panel": "#161a17",
        "bg_card": "#111512",
        "bg_control": "#1d241f",
        "bg_hover": "#263029",
        "border": "#2b382e",
        "border_subtle": "#1f2922",
        "text": "#b8c8bc",
        "text_bright": "#ffffff",
        "text_muted": "#7a8c7e",
        "primary": "#00e676",
        "primary_hover": "#26ff8d",
        "primary_pressed": "#00b359",
        "primary_soft": "#5cffaa",
        "primary_disabled_bg": "#123d26",
        "pill_sel_bg": "#112b1d",
        "pill_hov_bg": "#18261e",
    },
}


def build_hud_stylesheet(t: Dict[str, str]) -> str:
    """Build the sharp industrial Mad Catz H.U.D. stylesheet from a theme dictionary."""
    return f"""
QMainWindow, QWidget {{
    background-color: {t['bg_main']};
    color: {t['text']};
    font-family: 'Rajdhani', 'Orbitron', 'Segoe UI', 'Inter', 'Ubuntu', sans-serif;
    font-size: 13px;
}}

QFrame#hudHeader {{
    background-color: {t['bg_panel']};
    border: 1px solid {t['border']};
    border-top: 2px solid {t['primary']};
    border-radius: 2px;
    padding: 4px;
}}

QFrame#hudToolbar {{
    background-color: {t['bg_panel']};
    border: 1px solid {t['border']};
    border-left: 3px solid {t['primary']};
    border-radius: 2px;
}}

QFrame#hudSidePanel {{
    background-color: {t['bg_panel']};
    border: 1px solid {t['border']};
    border-top: 2px solid {t['primary']};
    border-radius: 2px;
}}

QFrame#hudSummaryCard {{
    background-color: {t['bg_card']};
    border: 1px solid {t['border']};
    border-left: 3px solid {t['primary']};
    border-radius: 2px;
    padding: 4px;
}}

QLabel#hudBrandTitle {{
    font-size: 16px;
    font-weight: 800;
    letter-spacing: 1px;
    color: {t['text_bright']};
    background: transparent;
    border: none;
}}

QLabel#hudDeviceStatus {{
    color: {t['text']};
    font-size: 11px;
    background: transparent;
    border: none;
}}

QLabel#hudSectionTitle {{
    color: {t['primary']};
    font-weight: 800;
    font-size: 11px;
    letter-spacing: 0.8px;
    background: transparent;
    border: none;
    border-bottom: 1px solid {t['primary']};
    padding-bottom: 4px;
    padding-left: 2px;
}}

QLabel#hudAccentText {{
    color: {t['primary_soft']};
    font-weight: bold;
    font-size: 11px;
    background: transparent;
    border: none;
}}

QLabel#hudBrightTitle {{
    color: {t['text_bright']};
    font-size: 13px;
    font-weight: bold;
    background: transparent;
    border: none;
}}

QLabel#hudMutedText {{
    color: {t['text_muted']};
    font-size: 10px;
    background: transparent;
    border: none;
}}

QTabWidget::pane {{
    border: 1px solid {t['border']};
    border-top: 2px solid {t['primary']};
    background-color: {t['bg_card']};
    border-radius: 2px;
    padding: 6px;
}}

QTabBar::tab {{
    background-color: {t['bg_card']};
    color: {t['text']};
    border: 1px solid {t['border_subtle']};
    border-bottom: none;
    padding: 9px 18px;
    margin-right: 3px;
    border-top-left-radius: 2px;
    border-top-right-radius: 2px;
    font-weight: 700;
    letter-spacing: 0.4px;
}}

QTabBar::tab:selected {{
    background-color: {t['bg_panel']};
    color: {t['text_bright']};
    border: 1px solid {t['primary']};
    border-top: 3px solid {t['primary']};
    border-bottom: 1px solid {t['bg_panel']};
}}

QTabBar::tab:hover:!selected {{
    background-color: {t['bg_hover']};
    color: {t['text_bright']};
    border-color: {t['primary']};
}}

QGroupBox {{
    border: 1px solid {t['border']};
    border-top: 2px solid {t['primary']};
    border-radius: 2px;
    margin-top: 16px;
    padding-top: 14px;
    padding-bottom: 10px;
    padding-left: 12px;
    padding-right: 12px;
    font-weight: bold;
    color: {t['primary']};
    background-color: {t['bg_panel']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 10px;
    color: {t['primary']};
    font-weight: 800;
    letter-spacing: 0.5px;
}}

QPushButton {{
    background-color: {t['bg_control']};
    color: {t['text_bright']};
    border: 1px solid {t['border']};
    border-radius: 2px;
    padding: 7px 14px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {t['bg_hover']};
    border-color: {t['primary']};
    color: {t['text_bright']};
}}

QPushButton:pressed {{
    background-color: {t['primary']};
    color: #ffffff;
}}

QPushButton:checked {{
    background-color: {t['primary']};
    color: #ffffff;
    border-color: {t['primary_hover']};
    font-weight: bold;
}}

QPushButton:disabled {{
    background-color: {t['bg_card']};
    color: {t['text_muted']};
    border-color: {t['border_subtle']};
}}

QPushButton#hudCatBtn {{
    text-align: left;
    padding: 6px 10px;
    background-color: {t['bg_control']};
    border: 1px solid {t['border_subtle']};
    border-left: 3px solid transparent;
    border-radius: 2px;
    color: {t['text']};
    font-weight: 600;
}}

QPushButton#hudCatBtn:hover:!checked {{
    background-color: {t['bg_hover']};
    border-color: {t['primary']};
    border-left: 3px solid {t['primary']};
    color: {t['text_bright']};
}}

QPushButton#hudCatBtn:checked {{
    background-color: {t['primary']};
    border-color: {t['primary_hover']};
    border-left: 3px solid {t['text_bright']};
    color: #ffffff;
    font-weight: bold;
}}

QPushButton#applyBtn {{
    background-color: {t['primary']};
    color: #ffffff;
    font-weight: 800;
    font-size: 13px;
    letter-spacing: 0.6px;
    padding: 9px 26px;
    border: 1px solid {t['primary_hover']};
    border-radius: 2px;
}}

QPushButton#applyBtn:hover {{
    background-color: {t['primary_hover']};
}}

QPushButton#applyBtn:pressed {{
    background-color: {t['primary_pressed']};
}}

QPushButton#applyBtn:disabled {{
    background-color: {t['primary_disabled_bg']};
    color: {t['text_muted']};
    border-color: {t['border_subtle']};
}}

QComboBox, QSpinBox, QLineEdit {{
    background-color: {t['bg_control']};
    border: 1px solid {t['border']};
    border-radius: 2px;
    padding: 5px 9px;
    color: {t['text_bright']};
    selection-background-color: {t['primary']};
}}

QComboBox:hover, QSpinBox:hover, QLineEdit:hover, QLineEdit:focus {{
    border-color: {t['primary']};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background-color: {t['bg_panel']};
    color: {t['text_bright']};
    border: 1px solid {t['primary']};
    selection-background-color: {t['primary']};
    selection-color: #ffffff;
}}

QListWidget#hudList {{
    background-color: {t['bg_card']};
    border: 1px solid {t['border']};
    border-radius: 2px;
    padding: 3px;
    outline: none;
}}

QListWidget#hudList::item {{
    padding: 7px 10px;
    border-radius: 2px;
    color: {t['text']};
    margin-bottom: 2px;
}}

QListWidget#hudList::item:hover {{
    background-color: {t['bg_hover']};
    color: {t['text_bright']};
}}

QListWidget#hudList::item:selected {{
    background-color: {t['primary']};
    color: #ffffff;
    font-weight: bold;
}}

QListWidget#hudMonoList {{
    background-color: {t['bg_card']};
    border: 1px solid {t['border']};
    border-radius: 2px;
    padding: 4px;
    font-family: 'JetBrains Mono', 'Fira Code', 'Ubuntu Mono', monospace;
    font-size: 12px;
    outline: none;
}}

QListWidget#hudMonoList::item {{
    padding: 6px 8px;
    border-radius: 2px;
    color: {t['text_bright']};
    margin-bottom: 2px;
}}

QListWidget#hudMonoList::item:hover {{
    background-color: {t['bg_hover']};
}}

QListWidget#hudMonoList::item:selected {{
    background-color: {t['primary']};
    color: #ffffff;
    font-weight: bold;
}}

QSlider::groove:horizontal {{
    border: 1px solid {t['border']};
    height: 5px;
    background: {t['bg_main']};
    border-radius: 1px;
}}

QSlider::sub-page:horizontal {{
    background: {t['primary']};
    border-radius: 1px;
}}

QSlider::handle:horizontal {{
    background: {t['text_bright']};
    border: 2px solid {t['primary']};
    width: 14px;
    margin-top: -6px;
    margin-bottom: -6px;
    border-radius: 2px;
}}

QSlider::handle:horizontal:hover {{
    background: {t['primary']};
}}

QProgressBar {{
    border: 1px solid {t['border']};
    border-radius: 2px;
    text-align: center;
    color: {t['text_bright']};
    background-color: {t['bg_main']};
    font-weight: bold;
}}

QProgressBar::chunk {{
    background-color: {t['primary']};
    border-radius: 1px;
}}

QCheckBox, QRadioButton {{
    color: {t['text_bright']};
    background: transparent;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 2px;
    border: 1px solid {t['border']};
    background-color: {t['bg_control']};
}}

QRadioButton::indicator {{
    border-radius: 8px;
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {t['primary']};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {t['primary']};
    border-color: {t['primary_hover']};
}}

QScrollArea {{
    border: none;
    background-color: transparent;
}}

QStatusBar {{
    background-color: {t['bg_panel']};
    color: {t['text']};
    border-top: 1px solid {t['border']};
}}
"""


DARK_STYLE = build_hud_stylesheet(HUD_THEMES["hud_crimson"])


class KeyCaptureButton(QPushButton):
    """Button that listens for a single key press (+ modifiers) and emits (modifier_mask, hid_keycode)."""
    shortcut_captured = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__("⌨️ Press Key to Bind...", parent)
        self._listening = False
        self.setCheckable(True)
        self.clicked.connect(self._toggle_listen)

    def _toggle_listen(self, checked: bool):
        self._listening = checked
        if checked:
            self.setText("🔴 Press any key now (Esc to cancel)...")
            self.grabKeyboard()
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self._stop_listen()

    def _stop_listen(self):
        if self._listening:
            self._listening = False
        self.releaseKeyboard()
        self.setChecked(False)
        self.setText("⌨️ Press Key to Bind...")

    def keyPressEvent(self, event: QKeyEvent):
        if not self._listening:
            super().keyPressEvent(event)
            return

        key = event.key()
        # Ignore bare modifier presses while waiting for the main key
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                   Qt.Key.Key_Meta, Qt.Key.Key_Super_L, Qt.Key.Key_Super_R, Qt.Key.Key_AltGr):
            event.accept()
            return

        mods = event.modifiers()
        if key == Qt.Key.Key_Escape and not (mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)):
            self._stop_listen()
            event.accept()
            return

        mod_mask = 0
        if mods & Qt.KeyboardModifier.ControlModifier:
            mod_mask |= int(ModifierMask.CTRL)
        if mods & Qt.KeyboardModifier.ShiftModifier:
            mod_mask |= int(ModifierMask.SHIFT)
        if mods & Qt.KeyboardModifier.AltModifier:
            mod_mask |= int(ModifierMask.ALT)
        if mods & Qt.KeyboardModifier.MetaModifier:
            mod_mask |= int(ModifierMask.WIN)

        hid_code = None
        if mods & Qt.KeyboardModifier.KeypadModifier:
            hid_code = QT_KEYPAD_TO_HID.get(key)
        if hid_code is None:
            hid_code = QT_KEY_TO_HID.get(key)

        self._stop_listen()
        if hid_code is not None:
            self.shortcut_captured.emit(mod_mask, hid_code)
        event.accept()


QT_MOD_KEY_TO_HID: Dict[int, int] = {
    Qt.Key.Key_Control: 0xE0,
    Qt.Key.Key_Shift: 0xE1,
    Qt.Key.Key_Alt: 0xE2,
    Qt.Key.Key_AltGr: 0xE6,
    Qt.Key.Key_Meta: 0xE3,
    Qt.Key.Key_Super_L: 0xE3,
    Qt.Key.Key_Super_R: 0xE7,
}


class MacroRecorderButton(QPushButton):
    """
    Live keyboard macro recorder button (matching MadCatz H.U.D. Record / Stop behavior).
    Emits step_recorded(key_code, is_release, elapsed_ms_since_prev_event).
    """
    step_recorded = pyqtSignal(int, bool, int)

    def __init__(self, parent=None):
        super().__init__("🔴 Start Recording Keys", parent)
        self._recording = False
        self._last_time: Optional[float] = None
        self.setCheckable(True)
        self.clicked.connect(self._toggle_record)

    def _toggle_record(self, checked: bool):
        if checked:
            self._recording = True
            self._last_time = None
            self.setText("⏹ Stop Recording (Press keys now...)")
            self.grabKeyboard()
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self.stop_recording()

    def stop_recording(self):
        if self._recording:
            self._recording = False
        self.releaseKeyboard()
        self.setChecked(False)
        self.setText("🔴 Start Recording Keys")

    @staticmethod
    def _qt_event_to_hid(event: QKeyEvent) -> Optional[int]:
        key = event.key()
        if key in QT_MOD_KEY_TO_HID:
            return QT_MOD_KEY_TO_HID[key]
        if event.modifiers() & Qt.KeyboardModifier.KeypadModifier:
            code = QT_KEYPAD_TO_HID.get(key)
            if code is not None:
                return code
        return QT_KEY_TO_HID.get(key)

    def keyPressEvent(self, event: QKeyEvent):
        if not self._recording:
            super().keyPressEvent(event)
            return
        if event.isAutoRepeat():
            event.accept()
            return
        code = self._qt_event_to_hid(event)
        if code is not None:
            now = time.monotonic()
            elapsed = int((now - self._last_time) * 1000) if self._last_time is not None else 0
            self._last_time = now
            self.step_recorded.emit(code, False, elapsed)
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent):
        if not self._recording:
            super().keyReleaseEvent(event)
            return
        if event.isAutoRepeat():
            event.accept()
            return
        code = self._qt_event_to_hid(event)
        if code is not None:
            now = time.monotonic()
            elapsed = int((now - self._last_time) * 1000) if self._last_time is not None else 0
            self._last_time = now
            self.step_recorded.emit(code, True, elapsed)
        event.accept()


class MouseDiagramWidget(QWidget):
    """
    Interactive visual diagram of the Mad Catz M.M.O. 7+ (Top View & Side View),
    adapted directly from the original MadCatz H.U.D. XAML coordinates and assets.
    """
    button_selected = pyqtSignal(str)

    LOGICAL_W = 760.0
    LOGICAL_H = 435.0

    # (slot_name, physical_title, pill_rect, elbow_points, mouse_pin_point)
    TOP_CALLOUTS = [
        # Left Column
        ("WheelUp",       "Scroll Wheel Up",          QRectF(12,  16, 206, 44), [(218,  38), (392.5,  38)], (392.5,  83.0)),
        ("LeftClick",     "Left Click",               QRectF(12,  76, 206, 44), [(218,  98), (288,  76)],   (344.5,  76.0)),
        ("SwitchProfile", "Top-Left Outer (Profile)", QRectF(12, 136, 206, 44), [(218, 158), (265, 129)],   (297.5, 129.0)),
        ("LeftActive",    "Left Action Lock",          QRectF(12, 196, 206, 44), [(218, 218), (275, 155)],   (357.5, 155.0)),
        ("ShortutKey3",   "Thumb Wing Edge (Btn 3)",  QRectF(12, 256, 206, 44), [(218, 278), (232, 232)],   (243.5, 232.0)),
        ("WheelLeft",     "Barrel Scroll Left",       QRectF(12, 316, 206, 44), [(218, 338), (265, 262)],   (307.5, 262.0)),

        # Right Column
        ("RightClick",    "Right Click",              QRectF(542,  12, 206, 44), [(542,  34), (475,  34)],   (442.5,  76.0)),
        ("WheelClick",    "Middle Click (Wheel)",     QRectF(542,  70, 206, 44), [(542,  92), (465,  92), (435, 113)], (392.5, 113.0)),
        ("FN",            "Top-Right Outer (Mode Shift)", QRectF(542, 128, 206, 44), [(542, 150), (505, 125)], (474.5, 125.0)),
        ("WheelDown",     "Scroll Wheel Down",        QRectF(542, 186, 206, 44), [(542, 208), (500, 208), (475, 143)], (392.5, 143.0)),
        ("DpiLoop",       "DPI Cycle Button",         QRectF(542, 244, 206, 44), [(542, 266), (485, 266), (460, 167)], (392.5, 167.0)),
        ("RightActive",   "Right Action Lock",         QRectF(542, 302, 206, 44), [(542, 324), (470, 324), (445, 185)], (417.5, 185.0)),
        ("WheelRight",    "Barrel Scroll Right",      QRectF(542, 360, 206, 44), [(542, 382), (455, 382), (425, 262)], (340.5, 262.0)),
    ]

    SIDE_CALLOUTS = [
        # Left Column (When mouse lays flat: nose=Front/Forward, palm=Rear/Backward, base=Down, top=Up)
        ("ShortutKey1",   "Thumb Front (Button 1)",     QRectF(12,  34, 212, 46), [(224,  57), (290, 205)], (362.5, 205.0)),
        ("ForwardClick",  "Thumb Ridge Front (Fwd)",    QRectF(12,  96, 212, 46), [(224, 119), (290, 232)], (394.5, 232.0)),
        ("ShortutKey5",   "5D Rocker Down (Button 5)",  QRectF(12, 158, 212, 46), [(224, 181), (285, 267)], (362.5, 267.0)),
        ("AccurateClick", "5D Rocker Center (Aim)",     QRectF(12, 220, 212, 46), [(224, 243), (345, 290)], (374.5, 267.0)),
        ("BackwardClick", "Thumb Ridge Rear (Back)",    QRectF(12, 282, 212, 46), [(224, 305), (290, 312)], (405.5, 312.0)),
        ("ShortutKey2",   "Thumb Rear (Button 2)",      QRectF(12, 344, 212, 46), [(224, 367), (290, 335)], (382.5, 335.0)),

        # Right Column (5D Rocker Forward / Up / Backward when mouse lays flat)
        ("ShortutKey4",   "5D Rocker Fwd (Button 4)",   QRectF(536, 116, 212, 48), [(536, 140), (415, 242)], (374.5, 255.0)),
        ("ShortutKey6",   "5D Rocker Up (Button 6)",    QRectF(536, 196, 212, 48), [(536, 220), (425, 267)], (386.5, 267.0)),
        ("ShortutKey7",   "5D Rocker Back (Button 7)",  QRectF(536, 276, 212, 48), [(536, 300), (415, 292)], (374.5, 279.0)),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(580, 380)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        self.img_top = QImage(asset_path("main.png"))
        self.img_side = QImage(asset_path("side.png"))

        self.view_mode = "top"  # "top" or "side"
        self.selected_slot = "LeftClick"
        self.hovered_slot: Optional[str] = None
        self.bindings: Dict[str, ButtonSetting] = {}
        self.macros: Dict[int, MacroDefinition] = {}
        self.aim_dpi: Optional[int] = 400
        self.is_fn_layer = False
        self.theme: Dict[str, str] = HUD_THEMES["hud_crimson"]

    def set_theme(self, theme: Dict[str, str]):
        self.theme = theme
        self.update()

    def set_view_mode(self, mode: str):
        if mode in ("top", "side") and mode != self.view_mode:
            self.view_mode = mode
            slots = [c[0] for c in self._active_callouts()]
            if self.selected_slot not in slots and slots:
                self.selected_slot = slots[0]
                self.button_selected.emit(self.selected_slot)
            self.update()

    def set_state(self, bindings: Dict[str, ButtonSetting], is_fn: bool,
                  aim_dpi: Optional[int] = None,
                  macros: Optional[Dict[int, MacroDefinition]] = None):
        self.bindings = bindings
        self.is_fn_layer = is_fn
        self.aim_dpi = aim_dpi
        if macros is not None:
            self.macros = macros
        self.update()

    def select_slot(self, slot_name: str, switch_view_if_needed: bool = True):
        if switch_view_if_needed:
            top_slots = {c[0] for c in self.TOP_CALLOUTS}
            side_slots = {c[0] for c in self.SIDE_CALLOUTS}
            if slot_name in side_slots and self.view_mode != "side":
                self.view_mode = "side"
            elif slot_name in top_slots and self.view_mode != "top":
                self.view_mode = "top"
        self.selected_slot = slot_name
        self.update()

    def _active_callouts(self):
        return self.TOP_CALLOUTS if self.view_mode == "top" else self.SIDE_CALLOUTS

    def _transform_params(self) -> Tuple[float, float, float]:
        w = max(1.0, float(self.width()))
        h = max(1.0, float(self.height()))
        scale = min(w / self.LOGICAL_W, h / self.LOGICAL_H)
        ox = (w - self.LOGICAL_W * scale) / 2.0
        oy = (h - self.LOGICAL_H * scale) / 2.0
        return scale, ox, oy

    def _widget_to_logical(self, pos: QPointF) -> QPointF:
        scale, ox, oy = self._transform_params()
        return QPointF((pos.x() - ox) / scale, (pos.y() - oy) / scale)

    def _hit_test(self, lpos: QPointF) -> Optional[str]:
        callouts = self._active_callouts()
        # Check pins first (radius 11 in logical coords)
        for slot, _title, _rect, _elbows, pin in callouts:
            if math.hypot(lpos.x() - pin[0], lpos.y() - pin[1]) <= 11.0:
                return slot
        # Check callout pills
        for slot, _title, rect, _elbows, _pin in callouts:
            if rect.contains(lpos):
                return slot
        return None

    def mouseMoveEvent(self, event: QMouseEvent):
        lpos = self._widget_to_logical(event.position())
        hit = self._hit_test(lpos)
        if hit != self.hovered_slot:
            self.hovered_slot = hit
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)
            self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            lpos = self._widget_to_logical(event.position())
            hit = self._hit_test(lpos)
            if hit:
                self.selected_slot = hit
                self.button_selected.emit(hit)
                self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        t = self.theme
        c_primary = QColor(t["primary"])
        c_soft = QColor(t["primary_soft"])
        c_panel = QColor(t["bg_panel"])
        c_card = QColor(t["bg_card"])
        c_border = QColor(t["border"])

        # Background card + top HUD accent bar
        p.fillRect(self.rect(), c_panel)
        p.setPen(QPen(c_border, 1.0))
        p.drawRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0))
        p.fillRect(QRectF(0, 0, self.width(), 2.0), c_primary)

        scale, ox, oy = self._transform_params()
        p.translate(ox, oy)
        p.scale(scale, scale)

        # Subtle HUD targeting ring behind mouse
        p.setPen(QPen(QColor(c_primary.red(), c_primary.green(), c_primary.blue(), 42), 1.0))
        p.setBrush(QColor(18, 18, 22, 160))
        p.drawEllipse(QPointF(380, 218), 152, 172)

        # Draw Mouse Image
        if self.view_mode == "top":
            if not self.img_top.isNull():
                p.drawImage(QRectF(230.0, 54.0, 260.0, 322.0), self.img_top)
        else:
            if not self.img_side.isNull():
                sw = 162.0 * (322.0 / 379.0)
                sx = 157.5 + 222.5 + 11.0 - sw / 2.0
                p.drawImage(QRectF(sx, 57.0, sw, 322.0), self.img_side)

        # Sharp angular HUD Layer badge at bottom center
        layer_badge_rect = QRectF(290, 396, 180, 25)
        p.setBrush(QColor(t["pill_sel_bg"]) if self.is_fn_layer else c_card)
        p.setPen(QPen(c_primary if self.is_fn_layer else c_border, 1.3))
        p.drawRoundedRect(layer_badge_rect, 2, 2)
        f_badge = QFont(self.font())
        f_badge.setPointSizeF(8.5)
        f_badge.setBold(True)
        p.setFont(f_badge)
        p.setPen(c_soft if self.is_fn_layer else QColor(t["text_bright"]))
        p.drawText(
            layer_badge_rect,
            Qt.AlignmentFlag.AlignCenter,
            "⚡ MODE SHIFT (FN) LAYER" if self.is_fn_layer else "● NORMAL LAYER"
        )

        callouts = self._active_callouts()

        # Draw non-selected callouts first, then selected/hovered on top
        ordered = sorted(
            callouts,
            key=lambda c: (c[0] == self.selected_slot, c[0] == self.hovered_slot)
        )

        for slot, title, rect, elbows, pin in ordered:
            is_sel = (slot == self.selected_slot)
            is_hov = (slot == self.hovered_slot)

            if is_sel:
                line_color = c_primary
                pill_bg = QColor(t["pill_sel_bg"])
                pill_border = c_primary
                line_w = 2.0
            elif is_hov:
                line_color = c_soft
                pill_bg = QColor(t["pill_hov_bg"])
                pill_border = c_soft
                line_w = 1.6
            else:
                line_color = QColor("#bcbcbc")
                pill_bg = c_card
                pill_border = c_border
                line_w = 1.1

            # 1. Polyline from pill to pin on mouse (matching KeyAssignPageView.xaml)
            pts = [QPointF(x, y) for x, y in elbows] + [QPointF(pin[0], pin[1])]
            p.setPen(QPen(line_color, line_w))
            for i in range(len(pts) - 1):
                p.drawLine(pts[i], pts[i + 1])

            # Anchor dot on pill edge
            p.setBrush(line_color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(pts[0], 2.8, 2.8)

            # Pin on the mouse button
            if is_sel or is_hov:
                p.setBrush(QColor(c_primary.red(), c_primary.green(), c_primary.blue(), 95))
                p.drawEllipse(pts[-1], 8.5, 8.5)
            p.setBrush(c_primary if (is_sel or is_hov) else QColor("#bcbcbc"))
            p.setPen(QPen(QColor("#0d0d0f"), 1.4))
            p.drawEllipse(pts[-1], 4.8 if is_sel else 4.2, 4.8 if is_sel else 4.2)

            # 2. Sharp angular HUD Callout Card (2px corner radius)
            p.setPen(QPen(pill_border, 1.6 if is_sel else 1.0))
            p.setBrush(pill_bg)
            p.drawRoundedRect(rect, 2, 2)

            # Left industrial stripe inside pill
            accent_rect = QRectF(rect.left() + 1, rect.top() + 1, 3.5, rect.height() - 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c_primary if is_sel else (c_soft if is_hov else QColor(t["border"])))
            p.drawRect(accent_rect)

            # Title (physical button name)
            f_title = QFont(self.font())
            f_title.setPointSizeF(8.5)
            f_title.setBold(True)
            p.setFont(f_title)
            p.setPen(QColor(t["text_bright"]) if (is_sel or is_hov) else QColor(t["text"]))
            p.drawText(
                rect.adjusted(10, 3, -6, -21),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                title
            )

            # Subtitle (current binding)
            binding_str = format_button_binding(self.bindings.get(slot), self.aim_dpi, self.macros)
            f_sub = QFont(self.font())
            f_sub.setPointSizeF(8.2)
            f_sub.setBold(is_sel)
            p.setFont(f_sub)
            p.setPen(c_soft if is_sel else c_primary)
            p.drawText(
                rect.adjusted(10, 21, -6, -3),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"▸ {binding_str}"
            )

        p.end()


class MouseLightingPreviewWidget(QWidget):
    """
    Visual preview of the MMO 7+ mouse with tinted RGB LED zones,
    matching LightSettingPageView.xaml (Mouse_Non_Light.png + tinted Light_Left.png & Light_Right.png).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 340)
        self.img_base = QImage(asset_path("mouse_non_light.png"))
        self.img_left = QImage(asset_path("light_left.png"))
        self.img_right = QImage(asset_path("light_right.png"))
        self.mode = LightMode.Static
        self.rgb = (255, 0, 0)
        self.brightness = 8
        self.theme: Dict[str, str] = HUD_THEMES["hud_crimson"]

    def set_theme(self, theme: Dict[str, str]):
        self.theme = theme
        self.update()

    def set_lighting(self, mode: LightMode, rgb: Tuple[int, int, int], brightness: int):
        self.mode = mode
        self.rgb = rgb
        self.brightness = brightness
        self.update()

    @staticmethod
    def _tint_led_image(src: QImage, color: QColor) -> QImage:
        """Recolor non-transparent pixels of Light_Left.png / Light_Right.png (like ImageUtil.ChangePngImageColor)."""
        if src.isNull():
            return src
        out = src.convertToFormat(QImage.Format.Format_ARGB32)
        r, g, b, a_scale = color.red(), color.green(), color.blue(), color.alpha() / 255.0
        for y in range(out.height()):
            for x in range(out.width()):
                px = out.pixelColor(x, y)
                if px.alpha() > 0:
                    out.setPixelColor(x, y, QColor(r, g, b, int(px.alpha() * a_scale)))
        return out

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # #191919 matches mouse_non_light.png seamlessly
        p.fillRect(self.rect(), QColor("#191919"))

        if self.img_base.isNull():
            p.end()
            return

        w = float(self.width())
        h = float(self.height())
        scale = min((w - 24) / 320.0, (h - 24) / 390.0)
        ox = (w - 320.0 * scale) / 2.0
        oy = (h - 390.0 * scale) / 2.0

        p.translate(ox, oy)
        p.scale(scale, scale)

        p.drawImage(QRectF(0, 0, 320, 390), self.img_base)

        # Draw only the two front button RGB LEDs (Light_Left.png & Light_Right.png from LightSettingPageView.xaml)
        if self.mode != LightMode.Off:
            if self.mode in (LightMode.Neon, LightMode.ColorLoop):
                col = QColor(230, 0, 18, int(115 + self.brightness * 14))
            else:
                alpha = int(85 + max(1, min(10, self.brightness)) * 17)
                col = QColor(self.rgb[0], self.rgb[1], self.rgb[2], alpha)

            if not self.img_left.isNull():
                tinted_l = self._tint_led_image(self.img_left, col)
                lh = 42.0 * (self.img_left.height() / max(1.0, float(self.img_left.width())))
                p.drawImage(QRectF(105.0, 15.0, 42.0, lh), tinted_l)

            if not self.img_right.isNull():
                tinted_r = self._tint_led_image(self.img_right, col)
                rh = 42.0 * (self.img_right.height() / max(1.0, float(self.img_right.width())))
                p.save()
                p.translate(228.0, 25.0)
                p.rotate(9.0)
                p.drawImage(QRectF(0.0, 0.0, 42.0, rh), tinted_r)
                p.restore()

        p.end()


class SensorAngleDiagram(QWidget):
    """
    Interactive visual crosshair widget representing the sensor rotation angle.
    Displays neutral horizontal/vertical axis in subtle gray and the rotated
    tracking orientation in theme accent color.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(130, 95)
        self.angle_deg = 0.0

    def set_angle(self, deg: float):
        self.angle_deg = float(deg)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.fillRect(rect, QColor("#121216"))
        painter.setPen(QPen(QColor("#2c2c36"), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)

        cx = rect.width() / 2.0
        cy = (rect.height() - 14) / 2.0

        # Neutral reference grid (dashed)
        pen_grid = QPen(QColor("#3d3d4a"), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen_grid)
        painter.drawLine(QPointF(12, cy), QPointF(rect.width() - 12, cy))
        painter.drawLine(QPointF(cx, 8), QPointF(cx, rect.height() - 20))

        # Rotate painter for the active tracking axis
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.angle_deg)

        pen_axis = QPen(QColor("#E60012"), 2)
        painter.setPen(pen_axis)
        r = 38.0
        painter.drawLine(QPointF(-r, 0), QPointF(r, 0))
        painter.drawLine(QPointF(0, -r * 0.6), QPointF(0, r * 0.6))

        # Center reticle dot
        painter.setBrush(QColor("#E60012"))
        painter.drawEllipse(QPointF(0, 0), 2.5, 2.5)

        # Arrowhead indicator on horizontal tracking line
        path = QPainterPath()
        path.moveTo(r, 0)
        path.lineTo(r - 6, -3.5)
        path.lineTo(r - 6, 3.5)
        path.closeSubpath()
        painter.drawPath(path)

        painter.restore()

        # Angle text
        painter.setPen(QColor("#ffffff" if abs(self.angle_deg) > 0.1 else "#888899"))
        painter.setFont(QFont("sans-serif", 8, QFont.Weight.Bold))
        text = f"{self.angle_deg:+.0f}°" if abs(self.angle_deg) > 0.1 else "0°"
        painter.drawText(QRectF(0, rect.height() - 18, rect.width(), 16), Qt.AlignmentFlag.AlignCenter, text)


class SignalBridge(QObject):
    battery_changed = pyqtSignal(int)
    profile_changed = pyqtSignal(int)
    dpi_stage_changed = pyqtSignal(int)
    mode_shift_toggled = pyqtSignal()
    apply_finished = pyqtSignal(dict, str)
    reload_finished = pyqtSignal(dict)
    light_apply_finished = pyqtSignal(bool, str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mad Catz M.M.O. 7+ Configurator (Linux)")
        self.resize(1120, 760)
        self.setMinimumSize(960, 660)
        self.current_theme_key = self._load_saved_theme_key()
        self.setStyleSheet(build_hud_stylesheet(HUD_THEMES[self.current_theme_key]))

        self.device: Optional[MMO7Device] = None
        self.current_profile_id = 1
        self.bridge = SignalBridge()
        self._io_busy = False
        self._updating_inspector = False

        # Cached hardware states
        self.sensor_data = {
            "dpi_stages": [(800, 800), (1600, 1600), (3200, 3200), (6400, 6400)],
            "current_stage": 1,
            "stage_mask": 0x0F,
            "stage_colors": [(255, 0, 0), (0, 128, 0), (0, 0, 255), (255, 255, 255)],
            "lift": 0,
            "angle_snap": 1,
            "center_offset": 2
        }
        self.wake_mode = 0
        self.light_data = {
            "mode": LightMode.Static,
            "speed": 3,
            "brightness": 8,
            "color": (255, 0, 0),
            "sleep_time": 2
        }
        self.rate_data = PollingRate.HZ_1000
        self.keys_normal: Dict[str, ButtonSetting] = {
            k: ButtonSetting(fn, mod, key) for k, (fn, mod, key) in DEFAULT_BUTTON_SETTINGS.items()
        }
        self.keys_fn: Dict[str, ButtonSetting] = {
            k: ButtonSetting(fn, mod, key) for k, (fn, mod, key) in DEFAULT_BUTTON_SETTINGS.items()
        }
        self.fn_toggle_mode = FnToggleMode.Toggle
        self.macros: Dict[int, MacroDefinition] = {}
        self._load_local_macros()

        self.bridge.battery_changed.connect(self._on_hw_battery)
        self.bridge.profile_changed.connect(self._on_hw_profile)
        self.bridge.dpi_stage_changed.connect(self._on_hw_dpi_stage)
        self.bridge.mode_shift_toggled.connect(self._on_hw_mode_shift)
        self.bridge.apply_finished.connect(self._on_apply_finished)
        self.bridge.reload_finished.connect(self._on_reload_finished)
        self.bridge.light_apply_finished.connect(self._on_light_apply_finished)

        self._init_ui()
        self._apply_theme(self.current_theme_key)
        self._connect_device()

        # Periodically poll for USB cable plug/unplug events on the main Qt thread
        # so plugging in the USB cable automatically takes priority over the wireless dongle.
        self._hotplug_timer = QTimer(self)
        self._hotplug_timer.setInterval(1500)
        self._hotplug_timer.timeout.connect(self._check_hotplug)
        self._hotplug_timer.start()

    @staticmethod
    def _ui_settings_path() -> str:
        cfg_dir = os.path.join(os.path.expanduser("~"), ".config", "mmo7-config")
        os.makedirs(cfg_dir, exist_ok=True)
        return os.path.join(cfg_dir, "ui_settings.json")

    def _load_saved_theme_key(self) -> str:
        try:
            p = self._ui_settings_path()
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                key = d.get("theme", "hud_crimson")
                if key in HUD_THEMES:
                    return key
        except Exception:
            pass
        return "hud_crimson"

    def _save_theme_key(self, key: str):
        try:
            with open(self._ui_settings_path(), "w", encoding="utf-8") as f:
                json.dump({"theme": key}, f, indent=2)
        except Exception:
            pass

    def _apply_theme(self, theme_key: str):
        if theme_key not in HUD_THEMES:
            theme_key = "hud_crimson"
        self.current_theme_key = theme_key
        theme = HUD_THEMES[theme_key]
        self.setStyleSheet(build_hud_stylesheet(theme))
        if hasattr(self, "mouse_diagram"):
            self.mouse_diagram.set_theme(theme)
        if hasattr(self, "light_preview"):
            self.light_preview.set_theme(theme)
        self._save_theme_key(theme_key)

    def _on_theme_selector_changed(self, _idx: int):
        key = self.combo_theme.currentData()
        if key:
            self._apply_theme(str(key))

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 10, 14, 10)
        main_layout.setSpacing(8)

        # 1. Top Header Bar
        main_layout.addWidget(self._create_header())

        # 2. Permissions Warning Banner (hidden by default)
        self.perm_banner = self._create_perm_banner()
        main_layout.addWidget(self.perm_banner)
        self.perm_banner.hide()

        # 3. Main Configuration Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_buttons_tab(), "🎮 Button Mapping")
        self.tabs.addTab(self._create_macro_tab(), "🎬 Macro Builder")
        self.tabs.addTab(self._create_dpi_tab(), "🎯 DPI & Sensor")
        self.tabs.addTab(self._create_lighting_tab(), "💡 RGB Lighting")
        self.tabs.addTab(self._create_rate_tab(), "⚡ Polling Rate & Power")
        self.tabs.addTab(self._create_profile_tab(), "📁 Profile Manager")
        main_layout.addWidget(self.tabs, stretch=1)

        # 4. Bottom Action Footer
        main_layout.addWidget(self._create_footer())

        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")

        # Initialize visual diagram with defaults before hardware load completes
        self._populate_buttons_table()
        self._on_diagram_button_selected("LeftClick")

    # --- Header Bar ---

    def _create_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("hudHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 6, 12, 6)

        # Mouse icon + Official M.M.O. 7+ Wordmark Logo
        icon_lbl = QLabel()
        dev_pix = QPixmap(asset_path("mouse_sample.png"))
        if not dev_pix.isNull():
            icon_lbl.setPixmap(dev_pix.scaled(18, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            layout.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        logo_lbl = QLabel()
        model_pix = QPixmap(asset_path("model.png"))
        if not model_pix.isNull():
            cropped = model_pix.copy(6, 5, 500, 98)
            logo_lbl.setPixmap(cropped.scaledToHeight(22, Qt.TransformationMode.SmoothTransformation))
            title_box.addWidget(logo_lbl)
        else:
            title = QLabel("MAD CATZ M.M.O. 7+")
            title.setObjectName("hudBrandTitle")
            title_box.addWidget(title)

        self.lbl_device_info = QLabel("Searching for device...")
        self.lbl_device_info.setObjectName("hudDeviceStatus")
        title_box.addWidget(self.lbl_device_info)
        layout.addLayout(title_box)

        layout.addStretch()

        # Theme Selector
        lbl_theme = QLabel("Theme:")
        lbl_theme.setStyleSheet("border: none; font-weight: 700;")
        layout.addWidget(lbl_theme)
        self.combo_theme = QComboBox()
        for t_key, t_info in HUD_THEMES.items():
            self.combo_theme.addItem(t_info["name"], t_key)
        t_idx = self.combo_theme.findData(self.current_theme_key)
        if t_idx >= 0:
            self.combo_theme.setCurrentIndex(t_idx)
        self.combo_theme.currentIndexChanged.connect(self._on_theme_selector_changed)
        layout.addWidget(self.combo_theme)

        layout.addSpacing(14)

        # Active Profile Selector
        lbl_prof = QLabel("Active Profile:")
        lbl_prof.setStyleSheet("border: none; font-weight: 700;")
        layout.addWidget(lbl_prof)
        self.combo_profile = QComboBox()
        for i in range(1, 6):
            self.combo_profile.addItem(f"On-Board Profile {i}", i)
        self.combo_profile.currentIndexChanged.connect(self._on_profile_selector_changed)
        layout.addWidget(self.combo_profile)

        layout.addSpacing(14)

        # Battery Indicator
        lbl_bat = QLabel("Battery:")
        lbl_bat.setStyleSheet("border: none; font-weight: 700;")
        layout.addWidget(lbl_bat)
        self.battery_bar = QProgressBar()
        self.battery_bar.setRange(0, 100)
        self.battery_bar.setValue(100)
        self.battery_bar.setFixedWidth(105)
        self.battery_bar.setFixedHeight(22)
        self.battery_bar.setFormat("%v%")
        layout.addWidget(self.battery_bar)

        return header

    def _create_perm_banner(self) -> QWidget:
        banner = QFrame()
        banner.setStyleSheet("background-color: #4a2200; border: 1px solid #ff7700; border-radius: 6px; padding: 6px;")
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(10, 4, 10, 4)

        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 16px;")
        layout.addWidget(icon_lbl)

        msg = QLabel("Write access to /dev/hidraw is restricted. Settings cannot be applied without udev permissions.")
        msg.setStyleSheet("color: #ffeedd; font-weight: 500;")
        layout.addWidget(msg, stretch=1)

        btn_rule = QPushButton("Install udev Rule")
        btn_rule.setStyleSheet("background-color: #ff5500; font-weight: bold;")
        btn_rule.clicked.connect(self._show_udev_dialog)
        layout.addWidget(btn_rule)

        return banner

    # --- Tab 1: Interactive Button Remapping ---

    def _create_buttons_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        # Top Toolbar: View Switcher (Top / Side / Table) + Layer Switcher (Normal / Mode Shift) + FN Mode
        toolbar = QFrame()
        toolbar.setObjectName("hudToolbar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(10, 6, 10, 6)
        tb_layout.setSpacing(8)

        lbl_view = QLabel("View:")
        lbl_view.setStyleSheet("font-weight: bold; border: none;")
        tb_layout.addWidget(lbl_view)

        self.btn_view_top = QPushButton("🖱️ Top View (Front)")
        self.btn_view_top.setCheckable(True)
        self.btn_view_top.setChecked(True)
        self.btn_view_side = QPushButton("👈 Side View (Thumb)")
        self.btn_view_side.setCheckable(True)
        self.btn_view_table = QPushButton("📋 All Buttons Table")
        self.btn_view_table.setCheckable(True)

        self.view_btn_group = QButtonGroup(self)
        self.view_btn_group.setExclusive(True)
        self.view_btn_group.addButton(self.btn_view_top, 0)
        self.view_btn_group.addButton(self.btn_view_side, 1)
        self.view_btn_group.addButton(self.btn_view_table, 2)
        self.view_btn_group.idClicked.connect(self._on_view_mode_clicked)

        tb_layout.addWidget(self.btn_view_top)
        tb_layout.addWidget(self.btn_view_side)
        tb_layout.addWidget(self.btn_view_table)

        tb_layout.addSpacing(16)

        lbl_layer = QLabel("Layer:")
        lbl_layer.setStyleSheet("font-weight: bold; border: none;")
        tb_layout.addWidget(lbl_layer)

        self.radio_layer_normal = QRadioButton("Normal Layer")
        self.radio_layer_fn = QRadioButton("Mode Shift (FN) Layer")
        self.radio_layer_normal.setChecked(True)
        self.radio_layer_normal.toggled.connect(self._on_layer_switched)
        tb_layout.addWidget(self.radio_layer_normal)
        tb_layout.addWidget(self.radio_layer_fn)

        tb_layout.addStretch()

        lbl_fntype = QLabel("Mode Shift Action:")
        lbl_fntype.setStyleSheet("font-weight: bold; border: none;")
        tb_layout.addWidget(lbl_fntype)
        self.combo_fn_type = QComboBox()
        self.combo_fn_type.addItem("Toggle (Click to switch)", FnToggleMode.Toggle)
        self.combo_fn_type.addItem("Hold (Hold for FN layer)", FnToggleMode.Hold)
        self.combo_fn_type.setCurrentIndex(0)
        self.combo_fn_type.currentIndexChanged.connect(self._on_fn_type_changed)
        tb_layout.addWidget(self.combo_fn_type)

        layout.addWidget(toolbar)

        # Stacked content: Page 0 = Visual Mouse Diagram + Inspector, Page 1 = Full Table
        self.buttons_stack = QStackedWidget()

        # --- Page 0: Visual Editor (Mad Catz H.U.D. Two-Column Selector + Mouse Diagram) ---
        visual_page = QWidget()
        vp_layout = QHBoxLayout(visual_page)
        vp_layout.setContentsMargins(0, 0, 0, 0)
        vp_layout.setSpacing(6)

        # Column 1: Mad Catz H.U.D. Category Menu (with original icons)
        cat_panel = QFrame()
        cat_panel.setObjectName("hudSidePanel")
        cat_panel.setFixedWidth(186)
        cat_layout = QVBoxLayout(cat_panel)
        cat_layout.setContentsMargins(8, 10, 8, 10)
        cat_layout.setSpacing(6)

        lbl_cat_hdr = QLabel("FUNCTION MENU")
        lbl_cat_hdr.setObjectName("hudSectionTitle")
        cat_layout.addWidget(lbl_cat_hdr)

        self.cat_btn_group = QButtonGroup(self)
        self.cat_btn_group.setExclusive(True)
        self.cat_buttons: List[QPushButton] = []

        for idx, cat in enumerate(HUD_CATEGORIES):
            btn = QPushButton(f"  {cat['title']}")
            btn.setObjectName("hudCatBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(36)
            icon_pix = QPixmap(asset_path(cat["icon_default"]))
            if not icon_pix.isNull():
                btn.setIcon(QIcon(icon_pix))
                btn.setIconSize(QSize(16, 16))
            self.cat_btn_group.addButton(btn, idx)
            self.cat_buttons.append(btn)
            cat_layout.addWidget(btn)

        self.cat_btn_group.idClicked.connect(self._on_hud_category_clicked)
        cat_layout.addStretch()

        # Selected Button Summary Box at bottom of Column 1
        sel_summary = QFrame()
        sel_summary.setObjectName("hudSummaryCard")
        ss_layout = QVBoxLayout(sel_summary)
        ss_layout.setContentsMargins(8, 6, 8, 6)
        ss_layout.setSpacing(3)

        lbl_sel_cap = QLabel("EDITING BUTTON")
        lbl_sel_cap.setObjectName("hudSectionTitle")
        ss_layout.addWidget(lbl_sel_cap)

        self.lbl_insp_title = QLabel("Left Click")
        self.lbl_insp_title.setObjectName("hudBrightTitle")
        self.lbl_insp_title.setWordWrap(True)
        ss_layout.addWidget(self.lbl_insp_title)

        self.lbl_insp_slot = QLabel("Slot: LeftClick")
        self.lbl_insp_slot.setObjectName("hudMutedText")
        ss_layout.addWidget(self.lbl_insp_slot)

        self.lbl_insp_normal_val = QLabel("Normal: Left Click")
        self.lbl_insp_normal_val.setStyleSheet("font-size: 11px; border: none;")
        self.lbl_insp_normal_val.setWordWrap(True)
        ss_layout.addWidget(self.lbl_insp_normal_val)

        self.lbl_insp_fn_val = QLabel("Shift: Left Click")
        self.lbl_insp_fn_val.setObjectName("hudAccentText")
        self.lbl_insp_fn_val.setWordWrap(True)
        ss_layout.addWidget(self.lbl_insp_fn_val)

        cat_layout.addWidget(sel_summary)
        vp_layout.addWidget(cat_panel)

        # Column 2: Mad Catz H.U.D. Function List Panel (changes based on selected category)
        func_panel = QFrame()
        func_panel.setObjectName("hudSidePanel")
        func_panel.setFixedWidth(225)
        fp_layout = QVBoxLayout(func_panel)
        fp_layout.setContentsMargins(8, 10, 8, 10)
        fp_layout.setSpacing(8)

        self.lbl_func_list_title = QLabel("MOUSE FUNCTION")
        self.lbl_func_list_title.setObjectName("hudSectionTitle")
        fp_layout.addWidget(self.lbl_func_list_title)

        self.func_sub_stack = QStackedWidget()
        self.func_sub_stack.setStyleSheet("border: none;")

        # Sub-page 0: Preset Function List (used by Recover, Mouse, Multimedia, Internet, Word, System)
        preset_page = QWidget()
        pp_layout = QVBoxLayout(preset_page)
        pp_layout.setContentsMargins(0, 0, 0, 0)
        pp_layout.setSpacing(6)

        self.hud_func_list = QListWidget()
        self.hud_func_list.setObjectName("hudList")
        self.hud_func_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hud_func_list.itemClicked.connect(self._on_hud_preset_item_clicked)
        pp_layout.addWidget(self.hud_func_list)
        self.func_sub_stack.addWidget(preset_page)

        # Sub-page 1: Keyboard Function Panel (Modifiers + Group Filter + Scrollable Key List + Press-to-Bind)
        kb_page = QWidget()
        kb_layout = QVBoxLayout(kb_page)
        kb_layout.setContentsMargins(0, 0, 0, 0)
        kb_layout.setSpacing(6)

        self.btn_key_capture = KeyCaptureButton()
        self.btn_key_capture.shortcut_captured.connect(self._on_shortcut_captured)
        kb_layout.addWidget(self.btn_key_capture)

        lbl_mods = QLabel("Modifier Keys:")
        lbl_mods.setStyleSheet("font-size: 11px; font-weight: 700;")
        kb_layout.addWidget(lbl_mods)

        mod_grid = QGridLayout()
        mod_grid.setSpacing(4)
        self.insp_chk_ctrl = QCheckBox("Ctrl")
        self.insp_chk_shift = QCheckBox("Shift")
        self.insp_chk_alt = QCheckBox("Alt")
        self.insp_chk_win = QCheckBox("Super")
        for i, chk in enumerate((self.insp_chk_ctrl, self.insp_chk_shift, self.insp_chk_alt, self.insp_chk_win)):
            chk.toggled.connect(self._on_kb_modifier_toggled)
            mod_grid.addWidget(chk, i // 2, i % 2)
        kb_layout.addLayout(mod_grid)

        lbl_kb_grp = QLabel("Key Group:")
        lbl_kb_grp.setStyleSheet("font-size: 11px; font-weight: 700;")
        kb_layout.addWidget(lbl_kb_grp)

        self.combo_kb_group = QComboBox()
        for grp_name, _keys in HUD_KEYBOARD_GROUPS:
            self.combo_kb_group.addItem(grp_name)
        self.combo_kb_group.currentIndexChanged.connect(self._populate_kb_key_list)
        kb_layout.addWidget(self.combo_kb_group)

        self.hud_kb_list = QListWidget()
        self.hud_kb_list.setObjectName("hudList")
        self.hud_kb_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hud_kb_list.itemClicked.connect(self._on_hud_kb_key_clicked)
        kb_layout.addWidget(self.hud_kb_list, stretch=1)

        self.func_sub_stack.addWidget(kb_page)

        # Sub-page 2: Macro Assignment Panel (select macro + loop mode + open Macro Builder)
        macro_assign_page = QWidget()
        ma_layout = QVBoxLayout(macro_assign_page)
        ma_layout.setContentsMargins(0, 0, 0, 0)
        ma_layout.setSpacing(6)

        lbl_m_loop = QLabel("Playback Mode:")
        lbl_m_loop.setStyleSheet("font-size: 11px; font-weight: 700;")
        ma_layout.addWidget(lbl_m_loop)

        self.combo_assign_macro_loop = QComboBox()
        self.combo_assign_macro_loop.addItem("Repeat N Times", MacroLoopType.LoopCount)
        self.combo_assign_macro_loop.addItem("Toggle (Until Pressed Again)", MacroLoopType.LoopToPressAgain)
        self.combo_assign_macro_loop.addItem("Hold (While Button Held)", MacroLoopType.LoopToRelease)
        self.combo_assign_macro_loop.currentIndexChanged.connect(self._on_assign_macro_loop_edited)
        ma_layout.addWidget(self.combo_assign_macro_loop)

        cnt_row = QHBoxLayout()
        cnt_row.addWidget(QLabel("Repeat Count:"))
        self.spin_assign_macro_count = QSpinBox()
        self.spin_assign_macro_count.setRange(1, 255)
        self.spin_assign_macro_count.setValue(1)
        self.spin_assign_macro_count.valueChanged.connect(self._on_assign_macro_loop_edited)
        cnt_row.addWidget(self.spin_assign_macro_count)
        ma_layout.addLayout(cnt_row)

        lbl_m_pick = QLabel("Select Macro to Assign:")
        lbl_m_pick.setStyleSheet("font-size: 11px; font-weight: 700;")
        ma_layout.addWidget(lbl_m_pick)

        self.hud_macro_list = QListWidget()
        self.hud_macro_list.setObjectName("hudList")
        self.hud_macro_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hud_macro_list.itemClicked.connect(self._on_hud_macro_item_clicked)
        ma_layout.addWidget(self.hud_macro_list, stretch=1)

        btn_open_mb = QPushButton("🎬 Open Macro Builder...")
        btn_open_mb.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        ma_layout.addWidget(btn_open_mb)

        self.func_sub_stack.addWidget(macro_assign_page)

        fp_layout.addWidget(self.func_sub_stack, stretch=1)
        vp_layout.addWidget(func_panel)

        # Column 3: Interactive Mouse Diagram
        self.mouse_diagram = MouseDiagramWidget()
        self.mouse_diagram.button_selected.connect(self._on_diagram_button_selected)
        vp_layout.addWidget(self.mouse_diagram, stretch=1)

        self.buttons_stack.addWidget(visual_page)

        # Populate initial keyboard list and select Mouse Function category by default
        self._current_hud_cat_idx = 2
        self._populate_kb_key_list(0)
        self.cat_buttons[2].setChecked(True)
        self._populate_hud_category_list(2)

        # --- Page 1: Full Table View ---
        table_page = QWidget()
        tp_layout = QVBoxLayout(table_page)
        tp_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll.setWidget(scroll_content)
        self.button_grid = QGridLayout(scroll_content)
        self.button_grid.setSpacing(8)

        for col_i, text in enumerate(("Physical Button", "Assigned Function", "Modifiers", "Keycode / Value")):
            lbl = QLabel(text)
            lbl.setObjectName("hudSectionTitle")
            self.button_grid.addWidget(lbl, 0, col_i)

        self.button_rows = {}
        for row_idx, (slot_name, slot_id, desc) in enumerate(BUTTON_MAP_ORDER, start=1):
            lbl_desc = QLabel(desc)
            lbl_desc.setStyleSheet("font-weight: 500;")

            combo_func = QComboBox()
            for label, fn_enum in FUNCTION_DISPLAY_ITEMS:
                combo_func.addItem(label, fn_enum)

            mod_frame = QWidget()
            mod_layout = QHBoxLayout(mod_frame)
            mod_layout.setContentsMargins(0, 0, 0, 0)
            mod_layout.setSpacing(4)
            chk_ctrl = QCheckBox("Ctrl")
            chk_shift = QCheckBox("Shift")
            chk_alt = QCheckBox("Alt")
            chk_win = QCheckBox("Super")
            mod_layout.addWidget(chk_ctrl)
            mod_layout.addWidget(chk_shift)
            mod_layout.addWidget(chk_alt)
            mod_layout.addWidget(chk_win)

            combo_key = QComboBox()
            for code, name in sorted(HID_KEY_NAMES.items(), key=lambda x: (x[0] != 0, x[1])):
                combo_key.addItem(name, code)

            combo_func.currentIndexChanged.connect(
                lambda _, s=slot_name, f=combo_func, mf=mod_frame, k=combo_key: self._on_table_row_changed(s, f, mf, k)
            )
            for chk in (chk_ctrl, chk_shift, chk_alt, chk_win):
                chk.toggled.connect(lambda _, s=slot_name: self._on_table_row_edited(s))
            combo_key.currentIndexChanged.connect(lambda _, s=slot_name: self._on_table_row_edited(s))

            self.button_grid.addWidget(lbl_desc, row_idx, 0)
            self.button_grid.addWidget(combo_func, row_idx, 1)
            self.button_grid.addWidget(mod_frame, row_idx, 2)
            self.button_grid.addWidget(combo_key, row_idx, 3)

            self.button_rows[slot_name] = {
                "combo_func": combo_func,
                "chk_ctrl": chk_ctrl,
                "chk_shift": chk_shift,
                "chk_alt": chk_alt,
                "chk_win": chk_win,
                "combo_key": combo_key,
                "mod_frame": mod_frame
            }

        tp_layout.addWidget(scroll)
        self.buttons_stack.addWidget(table_page)

        layout.addWidget(self.buttons_stack, stretch=1)
        return container

    def _on_view_mode_clicked(self, btn_id: int):
        if btn_id == 0:
            self.buttons_stack.setCurrentIndex(0)
            self.mouse_diagram.set_view_mode("top")
        elif btn_id == 1:
            self.buttons_stack.setCurrentIndex(0)
            self.mouse_diagram.set_view_mode("side")
        else:
            self._harvest_buttons_from_ui()
            self._populate_buttons_table()
            self.buttons_stack.setCurrentIndex(1)

    def _on_hud_category_clicked(self, cat_idx: int):
        self._current_hud_cat_idx = cat_idx
        for i, btn in enumerate(self.cat_buttons):
            cat = HUD_CATEGORIES[i]
            icon_file = cat["icon_selected"] if i == cat_idx else cat["icon_default"]
            pix = QPixmap(asset_path(icon_file))
            if not pix.isNull():
                btn.setIcon(QIcon(pix))
        self._populate_hud_category_list(cat_idx)
        self._highlight_active_in_hud_lists()

    def _populate_hud_category_list(self, cat_idx: int):
        cat = HUD_CATEGORIES[cat_idx]
        self.lbl_func_list_title.setText(cat["title"].upper())
        if cat["id"] == "keyboard":
            self.func_sub_stack.setCurrentIndex(1)
        elif cat["id"] == "macro":
            self.func_sub_stack.setCurrentIndex(2)
            self._populate_hud_macro_assign_list()
        else:
            self.func_sub_stack.setCurrentIndex(0)
            self.hud_func_list.clear()
            for label, kind, fn_code, mod_val, key_val in cat["items"]:
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, (kind, fn_code, mod_val, key_val))
                self.hud_func_list.addItem(item)

    def _populate_hud_macro_assign_list(self):
        if not hasattr(self, "hud_macro_list"):
            return
        self.hud_macro_list.blockSignals(True)
        self.hud_macro_list.clear()
        for m_idx in sorted(self.macros.keys()):
            m = self.macros[m_idx]
            item = QListWidgetItem(f"#{m.index}: {m.name} ({len(m.steps)} steps)")
            item.setData(Qt.ItemDataRole.UserRole, m.index)
            self.hud_macro_list.addItem(item)
        self.hud_macro_list.blockSignals(False)

    def _populate_kb_key_list(self, grp_idx: int = 0):
        if grp_idx < 0 or grp_idx >= len(HUD_KEYBOARD_GROUPS):
            grp_idx = 0
        _grp_name, keys = HUD_KEYBOARD_GROUPS[grp_idx]
        self.hud_kb_list.clear()
        for key_name, code in keys:
            item = QListWidgetItem(f"{key_name}")
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.hud_kb_list.addItem(item)
        if not getattr(self, "_updating_inspector", False):
            self._highlight_active_in_hud_lists()

    @staticmethod
    def _find_hud_category_for_binding(btn: Optional[ButtonSetting]) -> int:
        if btn is None:
            return 2
        fn_int = int(btn.function)
        if fn_int in (int(ButtonFunction.Blocked), int(ButtonFunction.ButtonOff)):
            return 0
        if fn_int == int(ButtonFunction.AssignMacro):
            return 7  # Macro category
        # Check exact preset matches in Internet (4), Word (5), System (6), Multimedia (3), Mouse (2)
        for cat_idx in (4, 5, 6, 3, 2):
            for _label, kind, c_fn, c_mod, c_key in HUD_CATEGORIES[cat_idx]["items"]:
                if kind == "assign" and c_fn == fn_int:
                    if fn_int == int(ButtonFunction.AssignShortcut):
                        if c_mod == btn.modify and c_key == btn.key_index:
                            return cat_idx
                    else:
                        return cat_idx
        if fn_int == int(ButtonFunction.AssignShortcut):
            return 1  # Keyboard Function
        return 2      # Default to Mouse Function

    def _highlight_active_in_hud_lists(self):
        slot_name = self.mouse_diagram.selected_slot
        if not slot_name:
            return
        is_fn = self.radio_layer_fn.isChecked()
        active_btn = (self.keys_fn if is_fn else self.keys_normal).get(slot_name)
        if not active_btn:
            return

        fn_int = int(active_btn.function)
        cat = HUD_CATEGORIES[self._current_hud_cat_idx]
        if cat["id"] == "keyboard":
            self.hud_kb_list.blockSignals(True)
            self.hud_kb_list.clearSelection()
            if fn_int == int(ButtonFunction.AssignShortcut):
                for i in range(self.hud_kb_list.count()):
                    it = self.hud_kb_list.item(i)
                    if it.data(Qt.ItemDataRole.UserRole) == active_btn.key_index:
                        it.setSelected(True)
                        self.hud_kb_list.scrollToItem(it)
                        break
            self.hud_kb_list.blockSignals(False)
        elif cat["id"] == "macro":
            self.hud_macro_list.blockSignals(True)
            self.hud_macro_list.clearSelection()
            if fn_int == int(ButtonFunction.AssignMacro):
                m_obj = self.macros.get(active_btn.key_index)
                if m_obj:
                    l_idx = self.combo_assign_macro_loop.findData(m_obj.loop_type)
                    if l_idx >= 0:
                        self.combo_assign_macro_loop.blockSignals(True)
                        self.combo_assign_macro_loop.setCurrentIndex(l_idx)
                        self.combo_assign_macro_loop.blockSignals(False)
                    self.spin_assign_macro_count.blockSignals(True)
                    self.spin_assign_macro_count.setValue(m_obj.loop_count)
                    self.spin_assign_macro_count.blockSignals(False)
                for i in range(self.hud_macro_list.count()):
                    it = self.hud_macro_list.item(i)
                    if it.data(Qt.ItemDataRole.UserRole) == active_btn.key_index:
                        it.setSelected(True)
                        self.hud_macro_list.scrollToItem(it)
                        break
            self.hud_macro_list.blockSignals(False)
        else:
            self.hud_func_list.blockSignals(True)
            self.hud_func_list.clearSelection()
            for i in range(self.hud_func_list.count()):
                it = self.hud_func_list.item(i)
                kind, c_fn, c_mod, c_key = it.data(Qt.ItemDataRole.UserRole)
                if kind == "assign" and c_fn == fn_int:
                    if fn_int == int(ButtonFunction.AssignShortcut):
                        if c_mod == active_btn.modify and c_key == active_btn.key_index:
                            it.setSelected(True)
                            self.hud_func_list.scrollToItem(it)
                            break
                    else:
                        it.setSelected(True)
                        self.hud_func_list.scrollToItem(it)
                        break
            self.hud_func_list.blockSignals(False)

    def _on_hud_macro_item_clicked(self, item: QListWidgetItem):
        if self._updating_inspector:
            return
        slot_name = self.mouse_diagram.selected_slot
        if not slot_name:
            return
        m_idx = int(item.data(Qt.ItemDataRole.UserRole))
        m_obj = self.macros.get(m_idx)
        if m_obj:
            m_obj.loop_type = MacroLoopType(int(self.combo_assign_macro_loop.currentData() or MacroLoopType.LoopCount))
            m_obj.loop_count = self.spin_assign_macro_count.value()
            self._save_local_macros()
        is_fn = self.radio_layer_fn.isChecked()
        target_dict = self.keys_fn if is_fn else self.keys_normal
        target_dict[slot_name] = ButtonSetting(ButtonFunction.AssignMacro, 0, m_idx)
        self._sync_single_slot_to_table(slot_name)
        self._refresh_visual_diagram()
        self._load_slot_into_inspector(slot_name, auto_switch_category=False)

    def _on_assign_macro_loop_edited(self):
        if self._updating_inspector:
            return
        slot_name = self.mouse_diagram.selected_slot
        if not slot_name:
            return
        is_fn = self.radio_layer_fn.isChecked()
        cur = (self.keys_fn if is_fn else self.keys_normal).get(slot_name)
        if cur and int(cur.function) == int(ButtonFunction.AssignMacro):
            m_obj = self.macros.get(cur.key_index)
            if m_obj:
                m_obj.loop_type = MacroLoopType(int(self.combo_assign_macro_loop.currentData() or MacroLoopType.LoopCount))
                m_obj.loop_count = self.spin_assign_macro_count.value()
                self._save_local_macros()
                self._refresh_macro_builder_ui()

    def _on_diagram_button_selected(self, slot_name: str):
        self.mouse_diagram.select_slot(slot_name, switch_view_if_needed=False)
        self._load_slot_into_inspector(slot_name, auto_switch_category=True)

    def _load_slot_into_inspector(self, slot_name: str, auto_switch_category: bool = False):
        self._updating_inspector = True
        try:
            desc_map = {name: (slot_id, desc) for name, slot_id, desc in BUTTON_MAP_ORDER}
            slot_id, desc = desc_map.get(slot_name, (-1, slot_name))
            self.lbl_insp_title.setText(desc)
            self.lbl_insp_slot.setText(f"Slot: {slot_name} (#{slot_id})")

            aim_val = self.spin_aim.value() if hasattr(self, "spin_aim") else 400
            btn_n = self.keys_normal.get(slot_name)
            btn_f = self.keys_fn.get(slot_name)
            self.lbl_insp_normal_val.setText(f"Normal: {format_button_binding(btn_n, aim_val, self.macros)}")
            self.lbl_insp_fn_val.setText(f"Shift:  {format_button_binding(btn_f, aim_val, self.macros)}")

            is_fn = self.radio_layer_fn.isChecked()
            active_btn = (self.keys_fn if is_fn else self.keys_normal).get(slot_name)
            if not active_btn:
                return

            is_shortcut = int(active_btn.function) == int(ButtonFunction.AssignShortcut)
            self.insp_chk_ctrl.setChecked(bool(active_btn.modify & ModifierMask.CTRL) if is_shortcut else False)
            self.insp_chk_shift.setChecked(bool(active_btn.modify & ModifierMask.SHIFT) if is_shortcut else False)
            self.insp_chk_alt.setChecked(bool(active_btn.modify & ModifierMask.ALT) if is_shortcut else False)
            self.insp_chk_win.setChecked(bool(active_btn.modify & ModifierMask.WIN) if is_shortcut else False)

            if auto_switch_category:
                target_cat = self._find_hud_category_for_binding(active_btn)
                if target_cat != self._current_hud_cat_idx:
                    self.cat_buttons[target_cat].setChecked(True)
                    self._on_hud_category_clicked(target_cat)
                else:
                    self._highlight_active_in_hud_lists()
            else:
                self._highlight_active_in_hud_lists()
        finally:
            self._updating_inspector = False

    def _on_hud_preset_item_clicked(self, item: QListWidgetItem):
        if self._updating_inspector:
            return
        slot_name = self.mouse_diagram.selected_slot
        if not slot_name:
            return
        kind, fn_code, mod_val, key_val = item.data(Qt.ItemDataRole.UserRole)
        if kind == "default":
            self._reset_selected_button_default()
            return

        is_fn = self.radio_layer_fn.isChecked()
        target_dict = self.keys_fn if is_fn else self.keys_normal
        prev = target_dict.get(slot_name)

        fn_enum = ButtonFunction(fn_code) if fn_code in ButtonFunction._value2member_map_ else fn_code
        if fn_code == int(ButtonFunction.FN):
            mod_val = int(self.combo_fn_type.currentData() or FnToggleMode.Toggle)
            key_val = 0
        elif fn_code == int(ButtonFunction.EasyAimDpi):
            if prev and int(prev.function) == int(ButtonFunction.EasyAimDpi) and (prev.modify or prev.key_index):
                mod_val, key_val = prev.modify, prev.key_index
            else:
                aim_val = self.spin_aim.value() if hasattr(self, "spin_aim") else 400
                mod_val, key_val = encode_aim_dpi(aim_val)

        target_dict[slot_name] = ButtonSetting(fn_enum, mod_val, key_val)
        self._sync_single_slot_to_table(slot_name)
        self._refresh_visual_diagram()
        self._load_slot_into_inspector(slot_name, auto_switch_category=False)
        self._refresh_aim_dpi_widget_state()

    def _current_kb_mod_mask(self) -> int:
        mod = 0
        if self.insp_chk_ctrl.isChecked():
            mod |= int(ModifierMask.CTRL)
        if self.insp_chk_shift.isChecked():
            mod |= int(ModifierMask.SHIFT)
        if self.insp_chk_alt.isChecked():
            mod |= int(ModifierMask.ALT)
        if self.insp_chk_win.isChecked():
            mod |= int(ModifierMask.WIN)
        return mod

    def _on_hud_kb_key_clicked(self, item: QListWidgetItem):
        if self._updating_inspector:
            return
        slot_name = self.mouse_diagram.selected_slot
        if not slot_name:
            return
        key_code = int(item.data(Qt.ItemDataRole.UserRole))
        mod = self._current_kb_mod_mask()
        is_fn = self.radio_layer_fn.isChecked()
        target_dict = self.keys_fn if is_fn else self.keys_normal
        target_dict[slot_name] = ButtonSetting(ButtonFunction.AssignShortcut, mod, key_code)
        self._sync_single_slot_to_table(slot_name)
        self._refresh_visual_diagram()
        self._load_slot_into_inspector(slot_name, auto_switch_category=False)
        self._refresh_aim_dpi_widget_state()

    def _on_kb_modifier_toggled(self):
        if self._updating_inspector:
            return
        slot_name = self.mouse_diagram.selected_slot
        if not slot_name:
            return
        is_fn = self.radio_layer_fn.isChecked()
        target_dict = self.keys_fn if is_fn else self.keys_normal
        cur = target_dict.get(slot_name)
        if cur and int(cur.function) == int(ButtonFunction.AssignShortcut):
            cur.modify = self._current_kb_mod_mask()
            self._sync_single_slot_to_table(slot_name)
            self._refresh_visual_diagram()
            self._load_slot_into_inspector(slot_name, auto_switch_category=False)

    def _on_shortcut_captured(self, mod_mask: int, hid_code: int):
        slot_name = self.mouse_diagram.selected_slot
        if not slot_name:
            return
        self._updating_inspector = True
        try:
            self.insp_chk_ctrl.setChecked(bool(mod_mask & ModifierMask.CTRL))
            self.insp_chk_shift.setChecked(bool(mod_mask & ModifierMask.SHIFT))
            self.insp_chk_alt.setChecked(bool(mod_mask & ModifierMask.ALT))
            self.insp_chk_win.setChecked(bool(mod_mask & ModifierMask.WIN))
            # Switch to "All Keys" group if the captured key isn't in the current filtered group
            found = False
            for i in range(self.hud_kb_list.count()):
                if self.hud_kb_list.item(i).data(Qt.ItemDataRole.UserRole) == hid_code:
                    found = True
                    break
            if not found and self.combo_kb_group.currentIndex() != 0:
                self.combo_kb_group.setCurrentIndex(0)
        finally:
            self._updating_inspector = False

        is_fn = self.radio_layer_fn.isChecked()
        target_dict = self.keys_fn if is_fn else self.keys_normal
        target_dict[slot_name] = ButtonSetting(ButtonFunction.AssignShortcut, mod_mask, hid_code)
        self._sync_single_slot_to_table(slot_name)
        self._refresh_visual_diagram()
        self._load_slot_into_inspector(slot_name, auto_switch_category=False)
        self._refresh_aim_dpi_widget_state()

    def _reset_selected_button_default(self):
        slot_name = self.mouse_diagram.selected_slot
        if not slot_name or slot_name not in DEFAULT_BUTTON_SETTINGS:
            return
        fn, mod, key = DEFAULT_BUTTON_SETTINGS[slot_name]
        if fn == ButtonFunction.FN:
            mod = int(self.combo_fn_type.currentData() or FnToggleMode.Toggle)
        elif fn == ButtonFunction.EasyAimDpi and hasattr(self, "spin_aim"):
            mod, key = encode_aim_dpi(self.spin_aim.value())
        is_fn = self.radio_layer_fn.isChecked()
        target_dict = self.keys_fn if is_fn else self.keys_normal
        target_dict[slot_name] = ButtonSetting(fn, mod, key)
        self._sync_single_slot_to_table(slot_name)
        self._refresh_visual_diagram()
        self._load_slot_into_inspector(slot_name, auto_switch_category=True)
        self._refresh_aim_dpi_widget_state()

    def _on_fn_type_changed(self):
        fn_type_val = int(self.combo_fn_type.currentData() or FnToggleMode.Toggle)
        for layer in (self.keys_normal, self.keys_fn):
            for name, btn in layer.items():
                if int(btn.function) == int(ButtonFunction.FN):
                    btn.modify = fn_type_val
                    btn.key_index = 0
        self._refresh_visual_diagram()
        if self.mouse_diagram.selected_slot == "FN":
            self._load_slot_into_inspector("FN")

    def _on_table_row_changed(self, slot_name: str, combo_func: QComboBox, mod_frame: QWidget, combo_key: QComboBox):
        func = combo_func.currentData()
        is_shortcut = (func == ButtonFunction.AssignShortcut)
        mod_frame.setEnabled(is_shortcut)
        if combo_key is not None:
            combo_key.setEnabled(is_shortcut)
        self._on_table_row_edited(slot_name)

    def _on_table_row_edited(self, slot_name: str):
        if getattr(self, "_populating_table", False):
            return
        self._harvest_single_row_from_table(slot_name)
        self._refresh_visual_diagram()
        if self.mouse_diagram.selected_slot == slot_name:
            self._load_slot_into_inspector(slot_name)
        self._refresh_aim_dpi_widget_state()

    def _refresh_visual_diagram(self):
        is_fn = self.radio_layer_fn.isChecked()
        layer_dict = self.keys_fn if is_fn else self.keys_normal
        aim_val = self.spin_aim.value() if hasattr(self, "spin_aim") else 400
        self.mouse_diagram.set_state(layer_dict, is_fn, aim_val, self.macros)

    def _refresh_aim_dpi_widget_state(self):
        if not hasattr(self, "spin_aim"):
            return
        aim = aim_dpi_from_buttons(self.keys_normal) or aim_dpi_from_buttons(self.keys_fn)
        has_aim = aim is not None
        self.slider_aim.setEnabled(has_aim)
        self.spin_aim.setEnabled(has_aim)
        self.lbl_aim_note.setText(
            "Applies to every button set to \"Precision Aim\" (both layers). Range: 50 – 25,500 DPI."
            if has_aim else
            "No button on this profile is set to \"Precision Aim\", so there is no aim DPI to edit."
        )

    # --- Tab 2: Macro Builder ---

    @staticmethod
    def _macros_storage_path() -> str:
        cfg_dir = os.path.join(os.path.expanduser("~"), ".config", "mmo7-config")
        os.makedirs(cfg_dir, exist_ok=True)
        return os.path.join(cfg_dir, "macros.json")

    def _load_local_macros(self):
        path = self._macros_storage_path()
        loaded = False
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    arr = json.load(f)
                if isinstance(arr, list):
                    for item in arr:
                        m = MacroDefinition.from_dict(item)
                        self.macros[m.index] = m
                        loaded = True
            except Exception as e:
                log.warning("Could not load local macros: %s", e)
        if not loaded or not self.macros:
            # Create a default starter macro in slot 1
            self.macros[1] = MacroDefinition(
                index=1,
                name="Macro 1",
                loop_type=MacroLoopType.LoopCount,
                loop_count=1,
                steps=[]
            )

    def _save_local_macros(self):
        try:
            path = self._macros_storage_path()
            arr = [self.macros[k].to_dict() for k in sorted(self.macros.keys())]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(arr, f, indent=2)
        except Exception as e:
            log.warning("Could not save local macros: %s", e)

    def _create_macro_tab(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        # Left Column: Macro Library List
        grp_lib = QGroupBox("Macro Library")
        grp_lib.setFixedWidth(250)
        lib_layout = QVBoxLayout(grp_lib)
        lib_layout.setSpacing(8)

        self.macro_lib_list = QListWidget()
        self.macro_lib_list.setObjectName("hudList")
        self.macro_lib_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.macro_lib_list.currentRowChanged.connect(self._on_macro_lib_row_changed)
        lib_layout.addWidget(self.macro_lib_list, stretch=1)

        row_lib1 = QHBoxLayout()
        btn_new_m = QPushButton("➕ New")
        btn_new_m.clicked.connect(self._new_macro)
        btn_dup_m = QPushButton("📋 Copy")
        btn_dup_m.clicked.connect(self._duplicate_macro)
        btn_del_m = QPushButton("🗑️ Delete")
        btn_del_m.clicked.connect(self._delete_macro)
        row_lib1.addWidget(btn_new_m)
        row_lib1.addWidget(btn_dup_m)
        row_lib1.addWidget(btn_del_m)
        lib_layout.addLayout(row_lib1)

        row_lib2 = QHBoxLayout()
        btn_imp_m = QPushButton("📂 Import...")
        btn_imp_m.clicked.connect(self._import_macro_file)
        btn_exp_m = QPushButton("💾 Export...")
        btn_exp_m.clicked.connect(self._export_macro_file)
        row_lib2.addWidget(btn_imp_m)
        row_lib2.addWidget(btn_exp_m)
        lib_layout.addLayout(row_lib2)

        layout.addWidget(grp_lib)

        # Center Column: Macro Properties & Action Sequence List
        grp_seq = QGroupBox("Macro Action Sequence (Max 50 Hardware Events)")
        seq_layout = QVBoxLayout(grp_seq)
        seq_layout.setSpacing(8)

        meta_grid = QGridLayout()
        meta_grid.setSpacing(8)
        meta_grid.addWidget(QLabel("Macro Name:"), 0, 0)
        self.edit_macro_name = QLineEdit()
        self.edit_macro_name.setMaxLength(20)
        self.edit_macro_name.setPlaceholderText("Up to 20 characters")
        self.edit_macro_name.editingFinished.connect(self._on_macro_meta_edited)
        meta_grid.addWidget(self.edit_macro_name, 0, 1)

        meta_grid.addWidget(QLabel("Loop Mode:"), 0, 2)
        self.combo_macro_loop = QComboBox()
        self.combo_macro_loop.addItem("Repeat N Times", MacroLoopType.LoopCount)
        self.combo_macro_loop.addItem("Toggle (Until Pressed Again)", MacroLoopType.LoopToPressAgain)
        self.combo_macro_loop.addItem("Hold (While Button Held)", MacroLoopType.LoopToRelease)
        self.combo_macro_loop.currentIndexChanged.connect(self._on_macro_meta_edited)
        meta_grid.addWidget(self.combo_macro_loop, 0, 3)

        meta_grid.addWidget(QLabel("Repeat Count:"), 0, 4)
        self.spin_macro_loop_count = QSpinBox()
        self.spin_macro_loop_count.setRange(1, 255)
        self.spin_macro_loop_count.setValue(1)
        self.spin_macro_loop_count.valueChanged.connect(self._on_macro_meta_edited)
        meta_grid.addWidget(self.spin_macro_loop_count, 0, 5)
        seq_layout.addLayout(meta_grid)

        self.lbl_macro_step_count = QLabel("0 / 50 steps")
        self.lbl_macro_step_count.setObjectName("hudAccentText")
        seq_layout.addWidget(self.lbl_macro_step_count)

        self.macro_steps_list = QListWidget()
        self.macro_steps_list.setObjectName("hudMonoList")
        self.macro_steps_list.currentRowChanged.connect(self._on_macro_step_selected)
        seq_layout.addWidget(self.macro_steps_list, stretch=1)

        step_bar = QHBoxLayout()
        btn_up = QPushButton("▲ Up")
        btn_up.clicked.connect(lambda: self._move_macro_step(-1))
        btn_dn = QPushButton("▼ Down")
        btn_dn.clicked.connect(lambda: self._move_macro_step(1))
        btn_rm = QPushButton("🗑️ Delete Step")
        btn_rm.clicked.connect(self._delete_macro_step)
        btn_clr = QPushButton("🧹 Clear All")
        btn_clr.clicked.connect(self._clear_macro_steps)
        step_bar.addWidget(btn_up)
        step_bar.addWidget(btn_dn)
        step_bar.addWidget(btn_rm)
        step_bar.addWidget(btn_clr)
        step_bar.addStretch()

        step_bar.addWidget(QLabel("Step Delay:"))
        self.spin_step_delay = QSpinBox()
        self.spin_step_delay.setRange(10, 25500)
        self.spin_step_delay.setSingleStep(10)
        self.spin_step_delay.setSuffix(" ms")
        self.spin_step_delay.setValue(50)
        self.spin_step_delay.valueChanged.connect(self._on_selected_step_delay_changed)
        step_bar.addWidget(self.spin_step_delay)
        seq_layout.addLayout(step_bar)

        layout.addWidget(grp_seq, stretch=1)

        # Right Column: Live Recorder & Manual Event Inserter
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        grp_rec = QGroupBox("Live Keyboard Recorder")
        grp_rec.setFixedWidth(275)
        rec_layout = QVBoxLayout(grp_rec)
        rec_layout.setSpacing(8)

        self.radio_rec_fixed = QRadioButton("Fixed Delay Between Keys:")
        self.radio_rec_real = QRadioButton("Record Real Typing Delays")
        self.radio_rec_fixed.setChecked(True)
        rec_layout.addWidget(self.radio_rec_fixed)

        fix_row = QHBoxLayout()
        fix_row.addSpacing(20)
        self.spin_rec_default_delay = QSpinBox()
        self.spin_rec_default_delay.setRange(10, 1270)
        self.spin_rec_default_delay.setSingleStep(10)
        self.spin_rec_default_delay.setSuffix(" ms")
        self.spin_rec_default_delay.setValue(50)
        fix_row.addWidget(self.spin_rec_default_delay)
        rec_layout.addLayout(fix_row)
        rec_layout.addWidget(self.radio_rec_real)

        self.btn_macro_recorder = MacroRecorderButton()
        self.btn_macro_recorder.step_recorded.connect(self._on_macro_step_recorded)
        rec_layout.addWidget(self.btn_macro_recorder)

        right_col.addWidget(grp_rec)

        grp_ins = QGroupBox("Insert Action Manually")
        grp_ins.setFixedWidth(275)
        ins_layout = QVBoxLayout(grp_ins)
        ins_layout.setSpacing(8)

        ins_layout.addWidget(QLabel("Key or Mouse Button:"))
        self.combo_macro_ins_key = QComboBox()
        for code, name in sorted(MACRO_KEY_NAMES.items(), key=lambda kv: (kv[0] >= 0xE0, kv[1])):
            self.combo_macro_ins_key.addItem(f"{name} (0x{code:02X})", code)
        ins_layout.addWidget(self.combo_macro_ins_key)

        btn_ins_tap = QPushButton("➕ Insert Tap (↓ Press + ↑ Release)")
        btn_ins_tap.clicked.connect(lambda: self._insert_macro_key_action("tap"))
        ins_layout.addWidget(btn_ins_tap)

        row_pr = QHBoxLayout()
        btn_ins_p = QPushButton("↓ Press Only")
        btn_ins_p.clicked.connect(lambda: self._insert_macro_key_action("press"))
        btn_ins_r = QPushButton("↑ Release Only")
        btn_ins_r.clicked.connect(lambda: self._insert_macro_key_action("release"))
        row_pr.addWidget(btn_ins_p)
        row_pr.addWidget(btn_ins_r)
        ins_layout.addLayout(row_pr)

        delay_row = QHBoxLayout()
        self.spin_ins_delay = QSpinBox()
        self.spin_ins_delay.setRange(25, 25500)
        self.spin_ins_delay.setSingleStep(25)
        self.spin_ins_delay.setSuffix(" ms")
        self.spin_ins_delay.setValue(100)
        btn_ins_d = QPushButton("⏱ Insert Delay")
        btn_ins_d.clicked.connect(self._insert_macro_delay_action)
        delay_row.addWidget(self.spin_ins_delay)
        delay_row.addWidget(btn_ins_d)
        ins_layout.addLayout(delay_row)

        right_col.addWidget(grp_ins)

        self.btn_save_macro = QPushButton("💾 Save Macro")
        self.btn_save_macro.setObjectName("applyBtn")
        self.btn_save_macro.clicked.connect(self._save_current_macro_button)
        right_col.addWidget(self.btn_save_macro)

        right_col.addStretch()
        layout.addLayout(right_col)

        self._selected_macro_index = min(self.macros.keys()) if self.macros else 1
        self._refresh_macro_builder_ui()
        return container

    def _current_macro(self) -> Optional[MacroDefinition]:
        return self.macros.get(getattr(self, "_selected_macro_index", 1))

    def _refresh_macro_builder_ui(self):
        if not hasattr(self, "macro_lib_list"):
            return
        self._updating_macro_ui = True
        try:
            self.macro_lib_list.blockSignals(True)
            self.macro_lib_list.clear()
            sel_row = 0
            for row_i, m_idx in enumerate(sorted(self.macros.keys())):
                m = self.macros[m_idx]
                it = QListWidgetItem(f"Slot #{m.index}: {m.name} ({len(m.steps)})")
                it.setData(Qt.ItemDataRole.UserRole, m.index)
                self.macro_lib_list.addItem(it)
                if m.index == self._selected_macro_index:
                    sel_row = row_i
            if self.macro_lib_list.count() > 0:
                self.macro_lib_list.setCurrentRow(sel_row)
            self.macro_lib_list.blockSignals(False)

            self._populate_hud_macro_assign_list()
            self._load_current_macro_into_editor()
        finally:
            self._updating_macro_ui = False

    def _load_current_macro_into_editor(self):
        m = self._current_macro()
        if not m:
            return
        self._updating_macro_ui = True
        try:
            self.edit_macro_name.setText(m.name)
            l_idx = self.combo_macro_loop.findData(m.loop_type)
            if l_idx >= 0:
                self.combo_macro_loop.setCurrentIndex(l_idx)
            self.spin_macro_loop_count.setValue(m.loop_count)
            self.spin_macro_loop_count.setEnabled(m.loop_type == MacroLoopType.LoopCount)
            self._repopulate_macro_steps_widget(m)
        finally:
            self._updating_macro_ui = False

    def _repopulate_macro_steps_widget(self, m: MacroDefinition, select_row: Optional[int] = None):
        prev_row = self.macro_steps_list.currentRow() if select_row is None else select_row
        self.macro_steps_list.blockSignals(True)
        self.macro_steps_list.clear()
        for i, st in enumerate(m.steps):
            it = QListWidgetItem(f"{i+1:02d}.  {st.format_label()}")
            self.macro_steps_list.addItem(it)
        if 0 <= prev_row < self.macro_steps_list.count():
            self.macro_steps_list.setCurrentRow(prev_row)
        elif self.macro_steps_list.count() > 0:
            self.macro_steps_list.setCurrentRow(self.macro_steps_list.count() - 1)
        self.macro_steps_list.blockSignals(False)
        self.lbl_macro_step_count.setText(f"{len(m.steps)} / {MACRO_MAX_STEPS} hardware events")
        self._on_macro_step_selected(self.macro_steps_list.currentRow())

    def _on_macro_lib_row_changed(self, row: int):
        if getattr(self, "_updating_macro_ui", False) or row < 0:
            return
        it = self.macro_lib_list.item(row)
        if it:
            self._selected_macro_index = int(it.data(Qt.ItemDataRole.UserRole))
            self._load_current_macro_into_editor()

    def _on_macro_meta_edited(self):
        if getattr(self, "_updating_macro_ui", False):
            return
        m = self._current_macro()
        if not m:
            return
        new_name = self.edit_macro_name.text().strip() or f"Macro {m.index}"
        m.name = new_name[:20]
        m.loop_type = MacroLoopType(int(self.combo_macro_loop.currentData() or MacroLoopType.LoopCount))
        m.loop_count = self.spin_macro_loop_count.value()
        self.spin_macro_loop_count.setEnabled(m.loop_type == MacroLoopType.LoopCount)
        self._save_local_macros()
        self._refresh_macro_builder_ui()
        self._refresh_visual_diagram()

    def _next_free_macro_index(self) -> int:
        for i in range(1, 256):
            if i not in self.macros:
                return i
        return 1

    def _new_macro(self):
        idx = self._next_free_macro_index()
        self.macros[idx] = MacroDefinition(index=idx, name=f"Macro {idx}", steps=[])
        self._selected_macro_index = idx
        self._save_local_macros()
        self._refresh_macro_builder_ui()

    def _duplicate_macro(self):
        cur = self._current_macro()
        if not cur:
            return
        idx = self._next_free_macro_index()
        copied_steps = [MacroStep(s.key_code, s.is_release, s.delay_ms) for s in cur.steps]
        self.macros[idx] = MacroDefinition(
            index=idx,
            name=f"{cur.name[:16]} ({idx})",
            loop_type=cur.loop_type,
            loop_count=cur.loop_count,
            steps=copied_steps
        )
        self._selected_macro_index = idx
        self._save_local_macros()
        self._refresh_macro_builder_ui()

    def _delete_macro(self):
        if len(self.macros) <= 1:
            QMessageBox.information(self, "Macro Library", "At least one macro slot must remain in the library.")
            return
        cur = self._current_macro()
        if not cur:
            return
        del self.macros[cur.index]
        self._selected_macro_index = min(self.macros.keys())
        self._save_local_macros()
        self._refresh_macro_builder_ui()
        self._refresh_visual_diagram()

    def _on_macro_step_selected(self, row: int):
        m = self._current_macro()
        if not m or row < 0 or row >= len(m.steps):
            self.spin_step_delay.setEnabled(False)
            return
        self.spin_step_delay.setEnabled(True)
        self.spin_step_delay.blockSignals(True)
        self.spin_step_delay.setValue(max(10, m.steps[row].delay_ms))
        self.spin_step_delay.blockSignals(False)

    def _on_selected_step_delay_changed(self, val: int):
        m = self._current_macro()
        row = self.macro_steps_list.currentRow()
        if not m or row < 0 or row >= len(m.steps):
            return
        m.steps[row].delay_ms = val
        self.macro_steps_list.item(row).setText(f"{row+1:02d}.  {m.steps[row].format_label()}")
        self._save_local_macros()

    def _on_macro_step_recorded(self, key_code: int, is_release: bool, elapsed_ms: int):
        m = self._current_macro()
        if not m:
            return
        if len(m.steps) >= MACRO_MAX_STEPS:
            self.btn_macro_recorder.stop_recording()
            self.statusBar.showMessage("Macro reached maximum 50 hardware events.", 4000)
            return

        if self.radio_rec_real.isChecked() and m.steps and elapsed_ms > 0:
            # Store real elapsed timing on the previous event (or insert a standalone delay if > 1270ms)
            if elapsed_ms <= 1270 and m.steps[-1].key_code >= 0x04:
                m.steps[-1].delay_ms = max(10, (elapsed_ms // 10) * 10)
            elif len(m.steps) + 1 < MACRO_MAX_STEPS:
                m.steps.append(MacroStep(key_code=1, is_release=False, delay_ms=min(25500, max(25, elapsed_ms))))

        default_d = self.spin_rec_default_delay.value()
        m.steps.append(MacroStep(key_code=key_code, is_release=is_release, delay_ms=default_d))
        self._save_local_macros()
        self._repopulate_macro_steps_widget(m, select_row=len(m.steps) - 1)
        self._populate_hud_macro_assign_list()

    def _insert_macro_key_action(self, mode: str):
        m = self._current_macro()
        if not m:
            return
        code = int(self.combo_macro_ins_key.currentData() or 0x04)
        d_ms = self.spin_rec_default_delay.value()
        needed = 2 if mode == "tap" else 1
        if len(m.steps) + needed > MACRO_MAX_STEPS:
            QMessageBox.warning(self, "Macro Full", f"Each macro supports up to {MACRO_MAX_STEPS} hardware events.")
            return
        if mode in ("tap", "press"):
            m.steps.append(MacroStep(key_code=code, is_release=False, delay_ms=d_ms))
        if mode in ("tap", "release"):
            m.steps.append(MacroStep(key_code=code, is_release=True, delay_ms=d_ms))
        self._save_local_macros()
        self._repopulate_macro_steps_widget(m, select_row=len(m.steps) - 1)
        self._refresh_macro_builder_ui()

    def _insert_macro_delay_action(self):
        m = self._current_macro()
        if not m:
            return
        if len(m.steps) >= MACRO_MAX_STEPS:
            QMessageBox.warning(self, "Macro Full", f"Each macro supports up to {MACRO_MAX_STEPS} hardware events.")
            return
        d_ms = self.spin_ins_delay.value()
        k_type = 1 if d_ms <= 6375 else (2 if d_ms <= 12750 else 3)
        m.steps.append(MacroStep(key_code=k_type, is_release=False, delay_ms=d_ms))
        self._save_local_macros()
        self._repopulate_macro_steps_widget(m, select_row=len(m.steps) - 1)
        self._refresh_macro_builder_ui()

    def _move_macro_step(self, delta: int):
        m = self._current_macro()
        row = self.macro_steps_list.currentRow()
        if not m or row < 0:
            return
        new_row = row + delta
        if 0 <= new_row < len(m.steps):
            m.steps[row], m.steps[new_row] = m.steps[new_row], m.steps[row]
            self._save_local_macros()
            self._repopulate_macro_steps_widget(m, select_row=new_row)

    def _delete_macro_step(self):
        m = self._current_macro()
        row = self.macro_steps_list.currentRow()
        if not m or row < 0 or row >= len(m.steps):
            return
        del m.steps[row]
        self._save_local_macros()
        self._repopulate_macro_steps_widget(m, select_row=min(row, len(m.steps) - 1))
        self._refresh_macro_builder_ui()

    def _clear_macro_steps(self):
        m = self._current_macro()
        if not m or not m.steps:
            return
        m.steps.clear()
        self._save_local_macros()
        self._repopulate_macro_steps_widget(m)
        self._refresh_macro_builder_ui()

    def _commit_macro_editor_fields(self) -> Optional[MacroDefinition]:
        """Harvest any in-progress edits from the Macro Builder widgets into the active MacroDefinition."""
        if hasattr(self, "btn_macro_recorder") and getattr(self.btn_macro_recorder, "_recording", False):
            self.btn_macro_recorder.stop_recording()
        m = self._current_macro()
        if not m:
            return None
        if hasattr(self, "edit_macro_name"):
            new_name = self.edit_macro_name.text().strip() or f"Macro {m.index}"
            m.name = new_name[:20]
        if hasattr(self, "combo_macro_loop"):
            m.loop_type = MacroLoopType(int(self.combo_macro_loop.currentData() or MacroLoopType.LoopCount))
        if hasattr(self, "spin_macro_loop_count"):
            m.loop_count = self.spin_macro_loop_count.value()
        if hasattr(self, "macro_steps_list") and hasattr(self, "spin_step_delay"):
            row = self.macro_steps_list.currentRow()
            if 0 <= row < len(m.steps) and self.spin_step_delay.isEnabled():
                m.steps[row].delay_ms = self.spin_step_delay.value()
        self._save_local_macros()
        return m

    def _save_current_macro_button(self):
        m = self._commit_macro_editor_fields()
        if not m:
            return
        self._refresh_macro_builder_ui()
        self._refresh_visual_diagram()
        log.info("Saved Macro #%d ('%s', %d steps, loop=%s, count=%d) to local library",
                 m.index, m.name, len(m.steps), m.loop_type, m.loop_count)
        self.statusBar.showMessage(
            f"Saved Macro #{m.index} ('{m.name}', {len(m.steps)} steps). Click 'Apply to Mouse' to send to hardware.",
            4000,
        )

    def _export_macro_file(self):
        m = self._current_macro()
        if not m:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Macro", f"{m.name}.macro.json", "Macro JSON Files (*.json *.macro)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(m.to_dict(), f, indent=2)
        QMessageBox.information(self, "Macro Exported", f"Saved macro to:\n{path}")

    def _import_macro_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Macro", "", "Macro Files (*.json *.macro)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if "steps" in data:
                m = MacroDefinition.from_dict(data)
                m.index = self._next_free_macro_index()
            elif "Value" in data and isinstance(data["Value"], list):
                # Native Windows MadCatz H.U.D. .macro JSON format
                idx = self._next_free_macro_index()
                name = str(data.get("Text", f"Macro {idx}"))[:20]
                steps = []
                for act in data["Value"]:
                    k = int(act.get("Key", 0))
                    act_t = int(act.get("ActType", 0))
                    delay = int(act.get("Delay", 5))
                    if k in (1, 2, 3):
                        steps.append(MacroStep(key_code=k, is_release=False, delay_ms=delay))
                    elif k > 0:
                        steps.append(MacroStep(key_code=k, is_release=(act_t == 1), delay_ms=delay * 10 if delay <= 127 else delay))
                m = MacroDefinition(index=idx, name=name, steps=steps)
            else:
                raise ValueError("Unrecognized macro file format.")
            self.macros[m.index] = m
            self._selected_macro_index = m.index
            self._save_local_macros()
            self._refresh_macro_builder_ui()
            QMessageBox.information(self, "Macro Imported", f"Imported '{m.name}' into Slot #{m.index}.")
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to import macro:\n{e}")

    # --- Tab 2: DPI & Sensor ---

    def _create_dpi_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setSpacing(14)

        # DPI Stages Group
        grp_stages = QGroupBox("DPI Stages (200 – 26,000 DPI, 200 DPI steps)")
        grid = QGridLayout(grp_stages)
        grid.setSpacing(10)

        grid.addWidget(QLabel("Stage"), 0, 0, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(QLabel("Active"), 0, 1, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(QLabel("Enabled"), 0, 2, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(QLabel("DPI Value (X / Y)"), 0, 3)
        lbl_stage_color = QLabel("Stage Color")
        lbl_stage_color.setToolTip(
            "Saved to the mouse with the sensor settings (the H.U.D. also shows them on screen)."
        )
        grid.addWidget(lbl_stage_color, 0, 4, Qt.AlignmentFlag.AlignCenter)

        self.dpi_active_group = QButtonGroup(self)
        self.dpi_stage_widgets = []

        for i in range(4):
            stage_num = i + 1
            lbl_num = QLabel(f"Stage {stage_num}")
            lbl_num.setStyleSheet("font-weight: bold;")

            radio_active = QRadioButton()
            self.dpi_active_group.addButton(radio_active, stage_num)
            if i == 0:
                radio_active.setChecked(True)

            chk_enabled = QCheckBox()
            chk_enabled.setChecked(True)

            initial_dpi = [800, 1600, 3200, 6400][i]

            slider_x = QSlider(Qt.Orientation.Horizontal)
            slider_x.setRange(200, 26000)
            slider_x.setSingleStep(200)
            slider_x.setPageStep(400)
            slider_x.setValue(initial_dpi)

            spin_x = QSpinBox()
            spin_x.setRange(200, 26000)
            spin_x.setSingleStep(200)
            spin_x.setValue(initial_dpi)

            slider_x.valueChanged.connect(lambda v, s=spin_x: s.setValue((v // 200) * 200))
            spin_x.valueChanged.connect(lambda v, sl=slider_x: sl.setValue((v // 200) * 200))

            slider_y = QSlider(Qt.Orientation.Horizontal)
            slider_y.setRange(200, 26000)
            slider_y.setSingleStep(200)
            slider_y.setPageStep(400)
            slider_y.setValue(initial_dpi)

            spin_y = QSpinBox()
            spin_y.setRange(200, 26000)
            spin_y.setSingleStep(200)
            spin_y.setValue(initial_dpi)

            slider_y.valueChanged.connect(lambda v, s=spin_y: s.setValue((v // 200) * 200))
            spin_y.valueChanged.connect(lambda v, sl=slider_y: sl.setValue((v // 200) * 200))

            chk_split = QCheckBox("Split X/Y")
            chk_split.setToolTip("Unlock separate horizontal (X) and vertical (Y) DPI sensitivities")

            btn_color = QPushButton()
            btn_color.setFixedSize(36, 24)
            col = self.sensor_data["stage_colors"][i]
            btn_color.setStyleSheet(f"background-color: rgb({col[0]},{col[1]},{col[2]}); border: 1px solid #666; border-radius: 4px;")
            btn_color.clicked.connect(lambda _, idx=i, b=btn_color: self._pick_stage_color(idx, b))

            row = i + 1
            grid.addWidget(lbl_num, row, 0, Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(radio_active, row, 1, Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(chk_enabled, row, 2, Qt.AlignmentFlag.AlignCenter)

            v_dpi_box = QVBoxLayout()
            v_dpi_box.setSpacing(3)

            x_box = QHBoxLayout()
            lbl_x = QLabel("X:")
            lbl_x.setStyleSheet("font-weight: bold; min-width: 14px;")
            x_box.addWidget(lbl_x)
            x_box.addWidget(slider_x, stretch=1)
            x_box.addWidget(spin_x)
            x_box.addWidget(chk_split)
            v_dpi_box.addLayout(x_box)

            y_container = QWidget()
            y_box = QHBoxLayout(y_container)
            y_box.setContentsMargins(0, 0, 0, 0)
            lbl_y = QLabel("Y:")
            lbl_y.setStyleSheet("font-weight: bold; min-width: 14px;")
            y_box.addWidget(lbl_y)
            y_box.addWidget(slider_y, stretch=1)
            y_box.addWidget(spin_y)
            lbl_spacer = QLabel()
            lbl_spacer.setFixedWidth(72)
            y_box.addWidget(lbl_spacer)
            y_container.setVisible(False)
            v_dpi_box.addWidget(y_container)

            def _bind_split(cs=chk_split, yc=y_container, sx=spin_x, sy=spin_y):
                def _on_split_toggled(checked):
                    yc.setVisible(checked)
                    if not checked:
                        sy.setValue(sx.value())
                return _on_split_toggled

            chk_split.toggled.connect(_bind_split(chk_split, y_container, spin_x, spin_y))

            def _bind_x_sync(cs=chk_split, sy=spin_y):
                def _on_x_changed(val):
                    if not cs.isChecked():
                        sy.setValue(val)
                return _on_x_changed

            spin_x.valueChanged.connect(_bind_x_sync(chk_split, spin_y))

            grid.addLayout(v_dpi_box, row, 3)
            grid.addWidget(btn_color, row, 4, Qt.AlignmentFlag.AlignCenter)

            self.dpi_stage_widgets.append({
                "radio": radio_active,
                "checkbox": chk_enabled,
                "chk_split": chk_split,
                "slider": slider_x,
                "spin": spin_x,
                "slider_x": slider_x,
                "spin_x": spin_x,
                "slider_y": slider_y,
                "spin_y": spin_y,
                "y_container": y_container,
                "btn_color": btn_color,
                "color": col
            })

        layout.addWidget(grp_stages)

        # Precision Aim Group
        grp_aim = QGroupBox("Precision Aim (EasyAim) DPI")
        aim_layout = QVBoxLayout(grp_aim)
        aim_box = QHBoxLayout()
        aim_box.addWidget(QLabel("Aim Target DPI:"))
        self.slider_aim = QSlider(Qt.Orientation.Horizontal)
        self.slider_aim.setRange(AIM_DPI_MIN, AIM_DPI_MAX)
        self.slider_aim.setSingleStep(50)
        self.slider_aim.setPageStep(200)
        self.slider_aim.setValue(350)
        self.spin_aim = QSpinBox()
        self.spin_aim.setRange(AIM_DPI_MIN, AIM_DPI_MAX)
        self.spin_aim.setSingleStep(50)
        self.spin_aim.setValue(350)
        self.slider_aim.valueChanged.connect(lambda v: self.spin_aim.setValue((v // 50) * 50))
        self.spin_aim.valueChanged.connect(self._on_aim_spin_changed)
        aim_box.addWidget(self.slider_aim, stretch=1)
        aim_box.addWidget(self.spin_aim)
        aim_layout.addLayout(aim_box)

        self.lbl_aim_note = QLabel("Applies to every button set to \"Precision Aim\" (both layers). Range: 50 – 25,500 DPI.")
        self.lbl_aim_note.setStyleSheet("color: #a0a0b0; font-style: italic;")
        self.lbl_aim_note.setWordWrap(True)
        aim_layout.addWidget(self.lbl_aim_note)
        layout.addWidget(grp_aim)

        # Sensor Visual Cards (LOD + Angle Snapping + Sensor Rotary Angle Tuning)
        sensor_row = QHBoxLayout()
        sensor_row.setSpacing(12)

        grp_lod = QGroupBox("Lift-Off Distance (LOD)")
        lod_vbox = QVBoxLayout(grp_lod)
        lbl_lod_img = QLabel()
        lod_pix = QPixmap(asset_path("mouse_lifting.png"))
        if not lod_pix.isNull():
            lbl_lod_img.setPixmap(lod_pix)
            lbl_lod_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lod_vbox.addWidget(lbl_lod_img)
        self.combo_lod = QComboBox()
        self.combo_lod.addItems(["Low (1 mm - Standard)", "High (2 mm)"])
        lod_vbox.addWidget(self.combo_lod)
        sensor_row.addWidget(grp_lod, stretch=1)

        grp_snap = QGroupBox("Linear Correction (Angle Snapping)")
        snap_vbox = QVBoxLayout(grp_snap)
        lbl_snap_img = QLabel()
        snap_pix = QPixmap(asset_path("mouse_linear.png"))
        if not snap_pix.isNull():
            lbl_snap_img.setPixmap(snap_pix)
            lbl_snap_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            snap_vbox.addWidget(lbl_snap_img)
        self.chk_angle_snap = QCheckBox("Enable Linear Angle Snapping")
        snap_vbox.addWidget(self.chk_angle_snap)
        sensor_row.addWidget(grp_snap, stretch=1)

        grp_rot = QGroupBox("Sensor Angle Tuning (Rotary Calibration)")
        rot_vbox = QVBoxLayout(grp_rot)
        rot_vbox.setSpacing(6)

        rot_top = QHBoxLayout()
        self.angle_diagram = SensorAngleDiagram()
        rot_top.addWidget(self.angle_diagram)

        rot_controls = QVBoxLayout()
        lbl_rotary_title = QLabel("Rotation Offset:")
        lbl_rotary_title.setStyleSheet("font-size: 11px; font-weight: bold;")
        self.lbl_rotary_desc = QLabel("0° (Neutral Alignment)")
        self.lbl_rotary_desc.setObjectName("hudAccentText")
        self.lbl_rotary_desc.setStyleSheet("font-weight: bold;")

        self.slider_rotary = QSlider(Qt.Orientation.Horizontal)
        self.slider_rotary.setRange(0, 4)
        self.slider_rotary.setValue(2)  # 2 = 0°
        self.slider_rotary.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_rotary.setTickInterval(1)

        ANGLE_LABELS = {
            0: (-30, "-30° (Inward Arc)"),
            1: (-10, "-10° (Slight Inward)"),
            2: (0, "0° (Neutral / Default)"),
            3: (10, "+10° (Slight Outward)"),
            4: (30, "+30° (Outward Arc)"),
        }

        def _on_rotary_changed(val):
            deg, desc = ANGLE_LABELS.get(val, (0, "0° (Neutral / Default)"))
            self.lbl_rotary_desc.setText(desc)
            self.angle_diagram.set_angle(deg)

        self.slider_rotary.valueChanged.connect(_on_rotary_changed)

        rot_scale = QHBoxLayout()
        lbl_m30 = QLabel("-30°")
        lbl_m30.setStyleSheet("font-size: 9px; color: #888;")
        lbl_zero = QLabel("0°")
        lbl_zero.setStyleSheet("font-size: 9px; color: #888;")
        lbl_p30 = QLabel("+30°")
        lbl_p30.setStyleSheet("font-size: 9px; color: #888;")
        rot_scale.addWidget(lbl_m30)
        rot_scale.addStretch()
        rot_scale.addWidget(lbl_zero)
        rot_scale.addStretch()
        rot_scale.addWidget(lbl_p30)

        rot_controls.addWidget(lbl_rotary_title)
        rot_controls.addWidget(self.lbl_rotary_desc)
        rot_controls.addWidget(self.slider_rotary)
        rot_controls.addLayout(rot_scale)

        rot_top.addLayout(rot_controls, stretch=1)
        rot_vbox.addLayout(rot_top)

        lbl_rot_note = QLabel("Rotates tracking axis up to ±30° to align with natural wrist angle.")
        lbl_rot_note.setStyleSheet("color: #a0a0b0; font-size: 10px; font-style: italic;")
        lbl_rot_note.setWordWrap(True)
        rot_vbox.addWidget(lbl_rot_note)

        sensor_row.addWidget(grp_rot, stretch=1)

        layout.addLayout(sensor_row)
        layout.addStretch()
        return scroll

    def _on_aim_spin_changed(self, val: int):
        snapped = max(AIM_DPI_MIN, min(AIM_DPI_MAX, (val // 50) * 50))
        self.slider_aim.blockSignals(True)
        self.slider_aim.setValue(snapped)
        self.slider_aim.blockSignals(False)
        self._refresh_visual_diagram()
        if hasattr(self, "mouse_diagram") and self.mouse_diagram.selected_slot:
            self._load_slot_into_inspector(self.mouse_diagram.selected_slot)

    def _pick_stage_color(self, idx: int, btn: QPushButton):
        curr = QColor(*self.dpi_stage_widgets[idx]["color"])
        new_col = QColorDialog.getColor(curr, self, f"Select Stage {idx+1} Color")
        if new_col.isValid():
            rgb = (new_col.red(), new_col.green(), new_col.blue())
            self.dpi_stage_widgets[idx]["color"] = rgb
            btn.setStyleSheet(f"background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]}); border: 1px solid #666; border-radius: 4px;")

    # --- Tab 3: RGB Lighting ---

    def _create_lighting_tab(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setSpacing(16)

        left_col = QVBoxLayout()
        grp_light = QGroupBox("RGB Lighting Effects")
        grid = QGridLayout(grp_light)
        grid.setSpacing(12)

        grid.addWidget(QLabel("Light Mode:"), 0, 0)
        self.combo_light_mode = QComboBox()
        self.combo_light_mode.addItems(["Off", "Static (Solid Color)", "Breathing", "Neon (Spectrum Cycle)", "Color Loop"])
        self.combo_light_mode.currentIndexChanged.connect(self._on_light_mode_changed)
        grid.addWidget(self.combo_light_mode, 0, 1)

        grid.addWidget(QLabel("Primary Color:"), 1, 0)
        col_box = QHBoxLayout()
        self.btn_light_color = QPushButton()
        self.btn_light_color.setFixedSize(54, 28)
        self.light_color = (255, 0, 0)
        self.btn_light_color.setStyleSheet("background-color: #ff0000; border: 1px solid #666; border-radius: 4px;")
        self.btn_light_color.clicked.connect(self._pick_light_color)
        col_box.addWidget(self.btn_light_color)
        self.lbl_color_hex = QLabel("#FF0000")
        self.lbl_color_hex.setStyleSheet("font-weight: bold;")
        col_box.addWidget(self.lbl_color_hex)
        col_box.addStretch()
        grid.addLayout(col_box, 1, 1)

        grid.addWidget(QLabel("Effect Speed:"), 2, 0)
        speed_box = QHBoxLayout()
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(1, 10)
        self.slider_speed.setValue(3)
        self.lbl_speed = QLabel("3")
        self.slider_speed.valueChanged.connect(lambda v: self.lbl_speed.setText(str(v)))
        speed_box.addWidget(self.slider_speed, stretch=1)
        speed_box.addWidget(self.lbl_speed)
        grid.addLayout(speed_box, 2, 1)

        grid.addWidget(QLabel("Brightness:"), 3, 0)
        bright_box = QHBoxLayout()
        self.slider_brightness = QSlider(Qt.Orientation.Horizontal)
        self.slider_brightness.setRange(1, 10)
        self.slider_brightness.setValue(8)
        self.lbl_brightness = QLabel("80%")
        self.slider_brightness.valueChanged.connect(self._on_brightness_changed)
        bright_box.addWidget(self.slider_brightness, stretch=1)
        bright_box.addWidget(self.lbl_brightness)
        grid.addLayout(bright_box, 3, 1)

        grid.addWidget(QLabel("LED Sleep Timer:"), 4, 0)
        sleep_box = QHBoxLayout()
        self.slider_sleep = QSlider(Qt.Orientation.Horizontal)
        self.slider_sleep.setRange(1, 15)
        self.slider_sleep.setValue(2)
        self.lbl_sleep = QLabel("2 min")
        self.slider_sleep.valueChanged.connect(lambda v: self.lbl_sleep.setText(f"{v} min"))
        sleep_box.addWidget(self.slider_sleep, stretch=1)
        sleep_box.addWidget(self.lbl_sleep)
        grid.addLayout(sleep_box, 4, 1)

        left_col.addWidget(grp_light)

        self.btn_apply_light = QPushButton("💡 Apply Lighting Only")
        self.btn_apply_light.clicked.connect(self._apply_lighting_only)
        left_col.addWidget(self.btn_apply_light)
        left_col.addStretch()

        layout.addLayout(left_col, stretch=1)

        # Right side: Live Mouse Lighting Preview
        grp_prev = QGroupBox("Mouse LED Preview")
        prev_layout = QVBoxLayout(grp_prev)
        self.light_preview = MouseLightingPreviewWidget()
        prev_layout.addWidget(self.light_preview, stretch=1)

        tip_row = QHBoxLayout()
        tip_row.addStretch()
        lbl_t1 = QLabel("Left & Right Primary Button RGB Zones")
        lbl_t1.setObjectName("hudMutedText")
        tip_row.addWidget(lbl_t1)
        light_strip_pix = QPixmap(asset_path("light.png"))
        if not light_strip_pix.isNull():
            lbl_ls = QLabel()
            lbl_ls.setPixmap(light_strip_pix.scaledToWidth(76, Qt.TransformationMode.SmoothTransformation))
            tip_row.addWidget(lbl_ls)
        tip_row.addStretch()
        prev_layout.addLayout(tip_row)

        layout.addWidget(grp_prev, stretch=1)

        return container

    def _update_light_preview(self):
        if hasattr(self, "light_preview"):
            mode = LightMode(self.combo_light_mode.currentIndex())
            self.light_preview.set_lighting(mode, self.light_color, self.slider_brightness.value())

    def _on_brightness_changed(self, v: int):
        self.lbl_brightness.setText(f"{v*10}%")
        self._update_light_preview()

    def _pick_light_color(self):
        curr = QColor(*self.light_color)
        new_col = QColorDialog.getColor(curr, self, "Select Mouse RGB Color")
        if new_col.isValid():
            self.light_color = (new_col.red(), new_col.green(), new_col.blue())
            hex_str = f"#{new_col.red():02X}{new_col.green():02X}{new_col.blue():02X}"
            self.btn_light_color.setStyleSheet(f"background-color: {hex_str}; border: 1px solid #666; border-radius: 4px;")
            self.lbl_color_hex.setText(hex_str)
            self._update_light_preview()

    def _on_light_mode_changed(self, idx: int):
        has_color = idx in (1, 2)
        self.btn_light_color.setEnabled(has_color)
        self.slider_speed.setEnabled(idx in (2, 3, 4))
        self._update_light_preview()

    # --- Tab 4: Polling Rate & Power ---

    def _create_rate_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)

        grp_rate = QGroupBox("Hardware Polling Rate (Report 0x06)")
        vbox = QVBoxLayout(grp_rate)
        vbox.setSpacing(12)

        self.rate_group = QButtonGroup(self)
        rates = [
            ("1000 Hz (1 ms response) — Recommended for gaming and lowest latency", PollingRate.HZ_1000),
            ("500 Hz (2 ms response) — Balanced performance", PollingRate.HZ_500),
            ("250 Hz (4 ms response) — Moderate battery savings", PollingRate.HZ_250),
            ("125 Hz (8 ms response) — Maximum wireless battery efficiency", PollingRate.HZ_125),
        ]

        for text, val in rates:
            rb = QRadioButton(text)
            self.rate_group.addButton(rb, int(val))
            if val == PollingRate.HZ_1000:
                rb.setChecked(True)
            vbox.addWidget(rb)

        layout.addWidget(grp_rate)

        # Standby & Wake Mode Group (Report 0x07)
        grp_wake = QGroupBox("Wireless Standby & Wake Mode (Report 0x07)")
        wake_vbox = QVBoxLayout(grp_wake)
        wake_vbox.setSpacing(10)

        lbl_wake_desc = QLabel(
            "Configure how the 2.4 GHz wireless sensor resumes from standby sleep:"
        )
        lbl_wake_desc.setStyleSheet("color: #a0a0b0; font-size: 11px;")
        wake_vbox.addWidget(lbl_wake_desc)

        self.wake_group = QButtonGroup(self)
        self.rb_wake_move = QRadioButton("Wake on Movement (Instant response upon moving the mouse)")
        self.rb_wake_key = QRadioButton("Wake on Button Click (Click to wake — prevents desk vibrations from waking mouse)")
        self.wake_group.addButton(self.rb_wake_move, 0)
        self.wake_group.addButton(self.rb_wake_key, 1)
        self.rb_wake_move.setChecked(True)
        wake_vbox.addWidget(self.rb_wake_move)
        wake_vbox.addWidget(self.rb_wake_key)

        lbl_wake_tip = QLabel("Click-to-wake saves battery and keeps the mouse asleep when accidentally bumped.")
        lbl_wake_tip.setStyleSheet("color: #888899; font-size: 10px; font-style: italic;")
        wake_vbox.addWidget(lbl_wake_tip)

        layout.addWidget(grp_wake)
        layout.addStretch()
        return container

    # --- Tab 5: Profile Manager ---

    def _create_profile_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)

        grp_files = QGroupBox("Profile Backup, Restore & Windows H.U.D. Import")
        grid = QGridLayout(grp_files)
        grid.setSpacing(12)

        btn_export = QPushButton("💾 Export Active Profile to JSON...")
        btn_export.clicked.connect(self._export_profile_json)
        grid.addWidget(btn_export, 0, 0)

        btn_import = QPushButton("📂 Import Profile (.json or Windows .profile)...")
        btn_import.clicked.connect(self._import_profile_json)
        grid.addWidget(btn_import, 0, 1)

        btn_defaults = QPushButton("↺ Reset Active Profile to Factory Defaults")
        btn_defaults.clicked.connect(self._reset_defaults)
        grid.addWidget(btn_defaults, 1, 0, 1, 2)

        layout.addWidget(grp_files)
        layout.addStretch()
        return container

    # --- Footer Bar ---

    def _create_footer(self) -> QWidget:
        footer = QFrame()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 6, 0, 0)

        self.btn_reload = QPushButton("🔄 Reload from Mouse")
        self.btn_reload.clicked.connect(self._reload_from_device)
        layout.addWidget(self.btn_reload)

        layout.addStretch()

        self.btn_apply = QPushButton("💾 Apply to Mouse")
        self.btn_apply.setObjectName("applyBtn")
        self.btn_apply.clicked.connect(self._apply_to_device)
        layout.addWidget(self.btn_apply)

        return footer

    # --- Layer & Table Synchronization Helpers ---

    def _on_layer_switched(self):
        shown = getattr(self, "_shown_layer_fn", None)
        if shown is not None and self.buttons_stack.currentIndex() == 1:
            self._harvest_buttons_from_ui(is_fn=shown)
        self._populate_buttons_table()
        self._refresh_visual_diagram()
        if hasattr(self, "mouse_diagram") and self.mouse_diagram.selected_slot:
            self._load_slot_into_inspector(self.mouse_diagram.selected_slot, auto_switch_category=True)

    def _sync_single_slot_to_table(self, slot_name: str):
        widgets = self.button_rows.get(slot_name)
        if not widgets:
            return
        is_fn = self.radio_layer_fn.isChecked()
        btn_setting = (self.keys_fn if is_fn else self.keys_normal).get(slot_name)
        if not btn_setting:
            return
        self._populating_table = True
        try:
            func_val = btn_setting.function
            idx = widgets["combo_func"].findData(func_val)
            if idx < 0:
                try:
                    f_int = int(func_val)
                except Exception:
                    f_int = func_val
                widgets["combo_func"].addItem(f"Unknown ({f_int})", func_val)
                idx = widgets["combo_func"].findData(func_val)
            if idx >= 0:
                widgets["combo_func"].setCurrentIndex(idx)

            is_shortcut = int(func_val) == int(ButtonFunction.AssignShortcut)
            widgets["chk_ctrl"].setChecked(bool(btn_setting.modify & ModifierMask.CTRL) if is_shortcut else False)
            widgets["chk_shift"].setChecked(bool(btn_setting.modify & ModifierMask.SHIFT) if is_shortcut else False)
            widgets["chk_alt"].setChecked(bool(btn_setting.modify & ModifierMask.ALT) if is_shortcut else False)
            widgets["chk_win"].setChecked(bool(btn_setting.modify & ModifierMask.WIN) if is_shortcut else False)

            k_idx = widgets["combo_key"].findData(btn_setting.key_index)
            if k_idx < 0 and btn_setting.key_index != 0:
                widgets["combo_key"].addItem(f"Code {btn_setting.key_index}", btn_setting.key_index)
                k_idx = widgets["combo_key"].findData(btn_setting.key_index)
            if k_idx >= 0:
                widgets["combo_key"].setCurrentIndex(k_idx)

            widgets["mod_frame"].setEnabled(is_shortcut)
            widgets["combo_key"].setEnabled(is_shortcut)
        finally:
            self._populating_table = False

    def _populate_buttons_table(self):
        self._populating_table = True
        try:
            is_fn = self.radio_layer_fn.isChecked()
            self._shown_layer_fn = is_fn
            layer_dict = self.keys_fn if is_fn else self.keys_normal

            # Sync combo_fn_type from FN button if present
            fn_btn = self.keys_normal.get("FN") or self.keys_fn.get("FN")
            if fn_btn and int(fn_btn.function) == int(ButtonFunction.FN):
                fn_mode = FnToggleMode.Toggle if fn_btn.modify == int(FnToggleMode.Toggle) else FnToggleMode.Hold
                fn_idx = self.combo_fn_type.findData(fn_mode)
                if fn_idx >= 0:
                    self.combo_fn_type.blockSignals(True)
                    self.combo_fn_type.setCurrentIndex(fn_idx)
                    self.combo_fn_type.blockSignals(False)

            for name in self.button_rows:
                self._sync_single_slot_to_table(name)
        finally:
            self._populating_table = False

    def _harvest_single_row_from_table(self, name: str, is_fn: Optional[bool] = None):
        if is_fn is None:
            is_fn = self.radio_layer_fn.isChecked()
        target_dict = self.keys_fn if is_fn else self.keys_normal
        widgets = self.button_rows.get(name)
        if not widgets:
            return

        func = widgets["combo_func"].currentData()
        try:
            func_int = int(func)
        except Exception:
            func_int = func

        prev = target_dict.get(name)
        if func_int == int(ButtonFunction.AssignShortcut):
            mod = 0
            if widgets["chk_ctrl"].isChecked():
                mod |= int(ModifierMask.CTRL)
            if widgets["chk_shift"].isChecked():
                mod |= int(ModifierMask.SHIFT)
            if widgets["chk_alt"].isChecked():
                mod |= int(ModifierMask.ALT)
            if widgets["chk_win"].isChecked():
                mod |= int(ModifierMask.WIN)
            key_code = widgets["combo_key"].currentData() or 0
        elif func_int == int(ButtonFunction.FN):
            fn_type_val = self.combo_fn_type.currentData()
            mod = int(fn_type_val) if fn_type_val is not None else int(FnToggleMode.Toggle)
            key_code = 0
        elif func_int == int(ButtonFunction.EasyAimDpi):
            if prev and int(prev.function) == int(ButtonFunction.EasyAimDpi) and (prev.modify or prev.key_index):
                mod, key_code = prev.modify, prev.key_index
            else:
                aim_val = self.spin_aim.value() if hasattr(self, "spin_aim") else 400
                mod, key_code = encode_aim_dpi(aim_val)
        elif func_int == int(ButtonFunction.AssignMacro):
            if prev and int(prev.function) == int(ButtonFunction.AssignMacro) and prev.key_index:
                mod, key_code = 0, prev.key_index
            else:
                first_idx = min(self.macros.keys()) if getattr(self, "macros", None) else 1
                mod, key_code = 0, first_idx
        else:
            mod = 0
            key_code = 0

        target_dict[name] = ButtonSetting(func, mod, key_code)

    def _harvest_buttons_from_ui(self, is_fn: Optional[bool] = None):
        for name in self.button_rows:
            self._harvest_single_row_from_table(name, is_fn=is_fn)

    # --- Hardware Communication Logic ---

    def _sync_device(self) -> bool:
        devs = discover_mmo7()
        if not devs:
            if self.device:
                self.device.close()
                self.device = None
            self.lbl_device_info.setText("🔴 Disconnected (No Mad Catz MMO 7+ found)")
            self.perm_banner.hide()
            self.btn_apply.setEnabled(False)
            if hasattr(self, "btn_apply_light"):
                self.btn_apply_light.setEnabled(False)
            if hasattr(self, "btn_reload"):
                self.btn_reload.setEnabled(True)
            self.statusBar.showMessage("Device not connected.")
            return False

        info = devs.get("02")
        if not info:
            if self.device:
                self.device.close()
                self.device = None
            self.lbl_device_info.setText("⚠️ MMO 7+ found, but config interface is missing")
            self.perm_banner.hide()
            self.btn_apply.setEnabled(False)
            if hasattr(self, "btn_apply_light"):
                self.btn_apply_light.setEnabled(False)
            if hasattr(self, "btn_reload"):
                self.btn_reload.setEnabled(True)
            self.statusBar.showMessage("Config interface not found.")
            return False

        conn_type = "2.4 GHz Wireless Dongle" if info.is_dongle else "USB Wired Cable"
        self.lbl_device_info.setText(f"🟢 Connected via {conn_type} ({info.node})")

        if not info.is_writable:
            if self.device:
                self.device.close()
                self.device = None
            self.perm_banner.show()
            self.btn_apply.setEnabled(False)
            if hasattr(self, "btn_apply_light"):
                self.btn_apply_light.setEnabled(False)
            if hasattr(self, "btn_reload"):
                self.btn_reload.setEnabled(True)
            self.statusBar.showMessage("Restricted permissions on /dev/hidraw. Install udev rule.")
            return False

        self.perm_banner.hide()
        need_new = (self.device is None or not self.device.is_open()
                    or self.device.config_node != info.node
                    or getattr(self.device, "is_dongle", None) != info.is_dongle)
        if need_new:
            if self.device:
                self.device.close()
            self.device = MMO7Device(info.node, is_dongle=info.is_dongle)
            if not self.device.open():
                self.device = None
                self.btn_apply.setEnabled(False)
                if hasattr(self, "btn_apply_light"):
                    self.btn_apply_light.setEnabled(False)
                if hasattr(self, "btn_reload"):
                    self.btn_reload.setEnabled(True)
                self.statusBar.showMessage(f"Failed to open {info.node}")
                return False
            self.device.on_battery_changed = self.bridge.battery_changed.emit
            self.device.on_profile_changed = self.bridge.profile_changed.emit
            self.device.on_dpi_stage_changed = self.bridge.dpi_stage_changed.emit
            self.device.on_mode_shift_toggled = self.bridge.mode_shift_toggled.emit
            self.device.start_monitor()

        self.btn_apply.setEnabled(True)
        if hasattr(self, "btn_apply_light"):
            self.btn_apply_light.setEnabled(True)
        if hasattr(self, "btn_upload_macro"):
            self.btn_upload_macro.setEnabled(True)
        if hasattr(self, "btn_reload"):
            self.btn_reload.setEnabled(True)
        return True

    def _connect_device(self):
        if self._sync_device():
            self._reload_from_device()

    def _check_hotplug(self):
        """
        Detect when the USB wired cable is plugged in or unplugged while the app is running.
        discover_mmo7() prioritizes the wired USB cable (0738:0c19) over the wireless dongle (0738:1c02).
        """
        if self._io_busy:
            return

        devs = discover_mmo7()
        info = devs.get("02") if devs else None

        cur_open = (
            self.device is not None
            and self.device.is_open()
            and os.path.exists(self.device.config_node)
        )
        cur_state = (self.device.config_node, self.device.is_dongle) if cur_open else None
        new_state = (info.node, info.is_dongle) if (info and info.is_writable) else None

        if new_state != cur_state:
            log.info("Hotplug connection change detected: %s -> %s", cur_state, new_state)
            if self._sync_device():
                conn_label = "USB Wired Cable" if not self.device.is_dongle else "2.4 GHz Wireless Dongle"
                self.statusBar.showMessage(f"Switched to {conn_label} ({self.device.config_node}) — reloading...", 3000)
                self._reload_from_device()

    def _reload_from_device(self):
        if self._io_busy:
            log.info("Reload skipped: I/O busy")
            return
        if not self._sync_device():
            return
        if not self.device or not self.device.is_open():
            return
        self._io_busy = True

        log.info("Reload requested (profile=%s node=%s dongle=%s)", self.current_profile_id,
                 getattr(self.device, "config_node", None), getattr(self.device, "is_dongle", None))
        self.statusBar.showMessage("Reading configuration from mouse memory...")
        if hasattr(self, "btn_reload"):
            self.btn_reload.setEnabled(False)
        self.btn_apply.setEnabled(False)
        if hasattr(self, "btn_apply_light"):
            self.btn_apply_light.setEnabled(False)
        if hasattr(self, "btn_upload_macro"):
            self.btn_upload_macro.setEnabled(False)
        QApplication.processEvents()

        device = self.device

        def worker():
            device.pause_monitor()
            try:
                p_id = device.get_active_profile()
                sensor_data = device.get_sensor_settings(p_id)
                light_data = device.get_light_settings(p_id)
                rate_data = device.get_polling_rate(p_id)
                wake_data = device.get_wake_mode()
                keys_normal = device.get_keys(p_id, is_fn=False)
                keys_fn = device.get_keys(p_id, is_fn=True)
                bad = device.failed_reads(p_id)

                # Read any macros assigned to buttons on this profile from hardware
                hw_macros = []
                seen_m_idx = set()
                for layer_dict in (keys_normal or {}, keys_fn or {}):
                    for btn in layer_dict.values():
                        if int(btn.function) == int(ButtonFunction.AssignMacro) and 0 < btn.key_index <= 255:
                            if btn.key_index not in seen_m_idx:
                                seen_m_idx.add(btn.key_index)
                                m_obj = device.get_macro(btn.key_index)
                                if m_obj and m_obj.steps:
                                    hw_macros.append(m_obj)

                log.info("Reload complete: profile=%s bad_reads=%s hw_macros=%d last_error=%s",
                         p_id, bad, len(hw_macros), device.last_error)
                self.bridge.reload_finished.emit({
                    "p_id": p_id,
                    "sensor_data": sensor_data,
                    "light_data": light_data,
                    "rate_data": rate_data,
                    "wake_data": wake_data,
                    "keys_normal": keys_normal,
                    "keys_fn": keys_fn,
                    "hw_macros": hw_macros,
                    "bad": bad,
                })
            except Exception as e:
                log.exception("Reload failed with exception")
                self.bridge.reload_finished.emit({"error": f"{e}\n{traceback.format_exc()}"})
            finally:
                device.resume_monitor()

        threading.Thread(target=worker, daemon=True).start()

    def _on_reload_finished(self, data):
        self._io_busy = False
        if data.get("error"):
            if hasattr(self, "btn_reload"):
                self.btn_reload.setEnabled(True)
            writable = self.device is not None and self.device.is_open()
            self.btn_apply.setEnabled(writable)
            if hasattr(self, "btn_apply_light"):
                self.btn_apply_light.setEnabled(writable)
            if hasattr(self, "btn_upload_macro"):
                self.btn_upload_macro.setEnabled(writable)
            self.statusBar.showMessage(f"Reload failed: {data['error']}", 8000)
            QMessageBox.warning(self, "Reload Failed", f"Could not read from mouse:\n{data['error']}")
            return
        if data.get("switch_failed"):
            if hasattr(self, "btn_reload"):
                self.btn_reload.setEnabled(True)
            writable = self.device is not None and self.device.is_open()
            self.btn_apply.setEnabled(writable)
            if hasattr(self, "btn_apply_light"):
                self.btn_apply_light.setEnabled(writable)
            if hasattr(self, "btn_upload_macro"):
                self.btn_upload_macro.setEnabled(writable)
            self.statusBar.showMessage(f"Profile switch not sent: {data.get('err', '')}", 6000)
            return

        p_id = data["p_id"]
        self.current_profile_id = p_id
        self.combo_profile.blockSignals(True)
        self.combo_profile.setCurrentIndex(p_id - 1)
        self.combo_profile.blockSignals(False)

        self.sensor_data = data["sensor_data"]
        for i, (slider_info, dpi_val) in enumerate(zip(self.dpi_stage_widgets, self.sensor_data["dpi_stages"])):
            dx, dy = (dpi_val[0], dpi_val[1]) if isinstance(dpi_val, (tuple, list)) else (dpi_val, dpi_val)
            slider_info["slider_x"].setValue(dx)
            slider_info["spin_x"].setValue(dx)
            slider_info["slider_y"].setValue(dy)
            slider_info["spin_y"].setValue(dy)
            is_split = (dx != dy)
            slider_info["chk_split"].setChecked(is_split)
            slider_info["y_container"].setVisible(is_split)
            is_enabled = bool(self.sensor_data["stage_mask"] & (1 << i))
            slider_info["checkbox"].setChecked(is_enabled)
            col = self.sensor_data["stage_colors"][i]
            slider_info["color"] = col
            slider_info["btn_color"].setStyleSheet(
                f"background-color: rgb({col[0]},{col[1]},{col[2]}); border: 1px solid #666; border-radius: 4px;"
            )

        active_stage = self.sensor_data.get("current_stage", 1)
        if 1 <= active_stage <= 4:
            self.dpi_stage_widgets[active_stage - 1]["radio"].setChecked(True)

        self.combo_lod.setCurrentIndex(1 if self.sensor_data.get("lift") else 0)
        self.chk_angle_snap.setChecked(bool(self.sensor_data.get("angle_snap")))

        # Restore Sensor Angle Tuning
        c_off = self.sensor_data.get("center_offset", 2)
        if hasattr(self, "slider_rotary"):
            self.slider_rotary.blockSignals(True)
            self.slider_rotary.setValue(max(0, min(4, c_off)))
            self.slider_rotary.blockSignals(False)
            ANGLE_LABELS = {
                0: (-30, "-30° (Inward Arc)"),
                1: (-10, "-10° (Slight Inward)"),
                2: (0, "0° (Neutral / Default)"),
                3: (10, "+10° (Slight Outward)"),
                4: (30, "+30° (Outward Arc)"),
            }
            deg, desc = ANGLE_LABELS.get(c_off, (0, "0° (Neutral / Default)"))
            self.lbl_rotary_desc.setText(desc)
            self.angle_diagram.set_angle(deg)

        self.light_data = data["light_data"]
        self.combo_light_mode.setCurrentIndex(int(self.light_data["mode"]))
        self.slider_speed.setValue(self.light_data["speed"])
        self.slider_brightness.setValue(self.light_data["brightness"])
        self.slider_sleep.setValue(self.light_data["sleep_time"])
        r, g, b = self.light_data["color"]
        self.light_color = (r, g, b)
        hex_str = f"#{r:02X}{g:02X}{b:02X}"
        self.btn_light_color.setStyleSheet(f"background-color: {hex_str}; border: 1px solid #666; border-radius: 4px;")
        self.lbl_color_hex.setText(hex_str)
        self._update_light_preview()

        self.rate_data = data["rate_data"]
        btn = self.rate_group.button(int(self.rate_data))
        if btn:
            btn.setChecked(True)

        # Restore Wake Mode
        wake_mode = data.get("wake_data", 0)
        if hasattr(self, "wake_group"):
            btn_w = self.wake_group.button(wake_mode)
            if btn_w:
                btn_w.setChecked(True)

        if data["keys_normal"]:
            self.keys_normal = data["keys_normal"]
        if data["keys_fn"]:
            self.keys_fn = data["keys_fn"]
        self.loaded_keys_normal = {k: ButtonSetting(v.function, v.modify, v.key_index) for k, v in self.keys_normal.items()}
        self.loaded_keys_fn = {k: ButtonSetting(v.function, v.modify, v.key_index) for k, v in self.keys_fn.items()}

        hw_macros = data.get("hw_macros") or []
        if hw_macros:
            added_any = False
            for hm in hw_macros:
                if hm.index not in self.macros or not self.macros[hm.index].steps:
                    self.macros[hm.index] = hm
                    added_any = True
            if added_any:
                self._save_local_macros()
                if hasattr(self, "macro_lib_list"):
                    self._refresh_macro_builder_ui()

        aim = aim_dpi_from_buttons(self.keys_normal) or aim_dpi_from_buttons(self.keys_fn)
        self.loaded_aim_dpi = aim
        if aim is not None:
            self.spin_aim.blockSignals(True)
            self.slider_aim.blockSignals(True)
            clamped_aim = max(AIM_DPI_MIN, min(AIM_DPI_MAX, aim))
            self.spin_aim.setValue(clamped_aim)
            self.slider_aim.setValue(clamped_aim)
            self.spin_aim.blockSignals(False)
            self.slider_aim.blockSignals(False)
        self._refresh_aim_dpi_widget_state()

        self._populate_buttons_table()
        self._refresh_visual_diagram()
        if self.mouse_diagram.selected_slot:
            self._load_slot_into_inspector(self.mouse_diagram.selected_slot, auto_switch_category=True)

        if hasattr(self, "btn_reload"):
            self.btn_reload.setEnabled(True)
        writable = self.device is not None and self.device.is_open()
        self.btn_apply.setEnabled(writable)
        if hasattr(self, "btn_apply_light"):
            self.btn_apply_light.setEnabled(writable)
        if hasattr(self, "btn_upload_macro"):
            self.btn_upload_macro.setEnabled(writable)

        bad = data["bad"]
        if bad:
            self.statusBar.showMessage(
                f"Could not read {', '.join(bad)} for profile {p_id}: showing defaults, writing those is blocked.", 10000)
        else:
            self.statusBar.showMessage(f"Loaded Profile {p_id} from hardware.", 3000)

    def _apply_aim_dpi_to_keys(self, keys_normal: Dict[str, ButtonSetting], keys_fn: Dict[str, ButtonSetting]):
        """Encode the Precision Aim DPI into every Precision Aim button of both layers."""
        if not self.spin_aim.isEnabled():
            return
        aim = self.spin_aim.value()
        for layer in (keys_normal, keys_fn):
            apply_aim_dpi(layer, aim)

    def _apply_to_device(self):
        if not self.device or not self.device.is_open():
            QMessageBox.warning(self, "Device Error", "Device is not connected or not writable.")
            return
        if self._io_busy:
            log.info("Apply skipped: I/O busy")
            return
        self._io_busy = True

        p_id = self.current_profile_id
        log.info("Apply requested (profile=%s)", p_id)
        self.statusBar.showMessage("Applying settings to hardware...")
        self.btn_apply.setEnabled(False)
        if hasattr(self, "btn_reload"):
            self.btn_reload.setEnabled(False)
        if hasattr(self, "btn_apply_light"):
            self.btn_apply_light.setEnabled(False)
        if hasattr(self, "btn_upload_macro"):
            self.btn_upload_macro.setEnabled(False)
        QApplication.processEvents()

        # 1. Collect Sensor & DPI
        dpi_stages = []
        stage_mask = 0
        stage_colors = []
        current_stage = 1

        for i, widgets in enumerate(self.dpi_stage_widgets):
            dx = widgets["spin_x"].value()
            dy = widgets["spin_y"].value() if widgets["chk_split"].isChecked() else dx
            dpi_stages.append((dx, dy))
            if widgets["checkbox"].isChecked():
                stage_mask |= (1 << i)
            if widgets["radio"].isChecked():
                current_stage = i + 1
            stage_colors.append(widgets["color"])

        lift = self.combo_lod.currentIndex()
        angle_snap = 1 if self.chk_angle_snap.isChecked() else 0
        center_offset = self.slider_rotary.value() if hasattr(self, "slider_rotary") else 2

        # 2. Collect Lighting
        mode = LightMode(self.combo_light_mode.currentIndex())
        speed = self.slider_speed.value()
        brightness = self.slider_brightness.value()
        r, g, b = self.light_color
        sleep_time = self.slider_sleep.value()

        # 3. Collect Polling Rate & Wake Mode
        rate = PollingRate(self.rate_group.checkedId())
        wake_mode = self.wake_group.checkedId() if hasattr(self, "wake_group") else 0
        if wake_mode < 0:
            wake_mode = 0

        # 4. Commit any active Macro Builder edits and collect Buttons
        self._commit_macro_editor_fields()
        if self.buttons_stack.currentIndex() == 1:
            self._harvest_buttons_from_ui()
        keys_normal = {k: ButtonSetting(v.function, v.modify, v.key_index) for k, v in self.keys_normal.items()}
        keys_fn = {k: ButtonSetting(v.function, v.modify, v.key_index) for k, v in self.keys_fn.items()}

        self._apply_aim_dpi_to_keys(keys_normal, keys_fn)

        def same_keys(a, b):
            if a.keys() != b.keys():
                return False, f"keys differ: {sorted(a.keys())} vs {sorted(b.keys())}"
            for k in a:
                va = (int(a[k].function), a[k].modify, a[k].key_index)
                vb = (int(b[k].function), b[k].modify, b[k].key_index)
                if va != vb:
                    return False, f"{k}: {va} vs {vb}"
            return True, ""

        loaded_n = getattr(self, "loaded_keys_normal", {})
        loaded_f = getattr(self, "loaded_keys_fn", {})
        same_n, diff_n = same_keys(keys_normal, loaded_n) if loaded_n else (False, "no loaded normal keys")
        same_f, diff_f = same_keys(keys_fn, loaded_f) if loaded_f else (False, "no loaded fn keys")

        # Collect any macros referenced by assigned buttons so they are uploaded before key mappings
        macros_by_idx = getattr(self, "macros", {})
        assigned_macros: List[MacroDefinition] = []
        seen_macro_idx = set()
        has_macro_normal = False
        has_macro_fn = False
        for is_fn_layer, layer_dict in ((False, keys_normal), (True, keys_fn)):
            for btn in layer_dict.values():
                if int(btn.function) == int(ButtonFunction.AssignMacro) and btn.key_index in macros_by_idx:
                    if is_fn_layer:
                        has_macro_fn = True
                    else:
                        has_macro_normal = True
                    if btn.key_index not in seen_macro_idx:
                        seen_macro_idx.add(btn.key_index)
                        assigned_macros.append(MacroDefinition.from_dict(macros_by_idx[btn.key_index].to_dict()))

        skip_normal = bool(loaded_n) and same_n and not has_macro_normal
        skip_fn = bool(loaded_f) and same_f and not has_macro_fn
        log.info("Keys apply decision: loaded_normal=%s loaded_fn=%s skip_normal=%s skip_fn=%s assigned_macros=%s diff_normal=%s diff_fn=%s",
                 len(loaded_n), len(loaded_f), skip_normal, skip_fn, [m.index for m in assigned_macros], diff_n, diff_f)

        device = self.device

        def worker():
            device.pause_monitor()
            try:
                results = {}
                errors = {}
                macro_steps = [
                    (f"macro #{m.index} ({m.name})", lambda m=m: device.set_macro(m))
                    for m in assigned_macros
                ]
                key_steps = []
                if skip_normal:
                    results["buttons (normal layer)"] = True
                    log.info("Skipping buttons (normal layer): unchanged since last reload")
                else:
                    key_steps.append(("buttons (normal layer)", lambda: device.set_keys(p_id, keys_normal, is_fn=False)))
                if skip_fn:
                    results["buttons (Fn layer)"] = True
                    log.info("Skipping buttons (Fn layer): unchanged since last reload")
                else:
                    key_steps.append(("buttons (Fn layer)", lambda: device.set_keys(p_id, keys_fn, is_fn=True)))

                other_steps = [
                    ("sensor", lambda: device.set_sensor_settings(
                        p_id, dpi_stages, current_stage, stage_mask, stage_colors, lift, angle_snap,
                        center_offset=center_offset
                    )),
                    ("light", lambda: device.set_light_settings(p_id, mode, speed, brightness, r, g, b, sleep_time)),
                    ("polling rate", lambda: device.set_polling_rate(p_id, rate)),
                    ("wake mode", lambda: device.set_wake_mode(wake_mode)),
                    ("active profile", lambda: device.set_active_profile(p_id)),
                ]
                steps = macro_steps + key_steps + other_steps

                for name, fn in steps:
                    ok = fn()
                    results[name] = ok
                    if not ok:
                        errors[name] = device.last_error or "Unknown error"
                        if name.startswith("buttons") or "I/O error" in (device.last_error or ""):
                            break
                    time.sleep(0.1)
                log.info("Apply complete: results=%s errors=%s", results, errors)
                self.bridge.apply_finished.emit(results, "\n".join(f"{k}: {v}" for k, v in errors.items()))
            except Exception as e:
                log.exception("Apply failed with exception")
                self.bridge.apply_finished.emit(
                    {"apply": False}, f"Exception while applying: {e}\n{traceback.format_exc()}"
                )
            finally:
                device.resume_monitor()

        threading.Thread(target=worker, daemon=True).start()

    def _on_apply_finished(self, results, last_error):
        self._io_busy = False
        writable = self.device is not None and self.device.is_open()
        self.btn_apply.setEnabled(writable)
        if hasattr(self, "btn_apply_light"):
            self.btn_apply_light.setEnabled(writable)
        if hasattr(self, "btn_upload_macro"):
            self.btn_upload_macro.setEnabled(writable)
        if hasattr(self, "btn_reload"):
            self.btn_reload.setEnabled(writable)
        p_id = self.current_profile_id
        failed = [name for name, ok in results.items() if not ok]
        log.info("Apply finished UI: profile=%s failed=%s last_error=%s", p_id, failed, last_error)
        if failed:
            msg = "These were NOT confirmed by the mouse: " + ", ".join(failed)
            if last_error:
                msg += "\n\n" + last_error
            QMessageBox.warning(self, "Not everything was written", msg)
            self.statusBar.showMessage(f"Profile {p_id}: {len(failed)} item(s) not written.", 6000)
        else:
            # Update loaded cache so subsequent applies know buttons are clean
            self.loaded_keys_normal = {k: ButtonSetting(v.function, v.modify, v.key_index) for k, v in self.keys_normal.items()}
            self.loaded_keys_fn = {k: ButtonSetting(v.function, v.modify, v.key_index) for k, v in self.keys_fn.items()}
            self.loaded_aim_dpi = self.spin_aim.value()
            self.statusBar.showMessage(f"Profile {p_id} settings written and confirmed by the mouse.", 4000)

    def _apply_lighting_only(self):
        if not self.device or not self.device.is_open():
            QMessageBox.warning(self, "Device Error", "Device is not connected or not writable.")
            return
        if self._io_busy:
            log.info("Apply lighting skipped: I/O busy")
            return
        self._io_busy = True

        p_id = self.current_profile_id
        mode = LightMode(self.combo_light_mode.currentIndex())
        speed = self.slider_speed.value()
        brightness = self.slider_brightness.value()
        r, g, b = self.light_color
        sleep_time = self.slider_sleep.value()

        log.info("Apply lighting requested (profile=%s mode=%s color=%s)", p_id, int(mode), (r, g, b))
        self.statusBar.showMessage("Applying lighting to hardware...")
        self.btn_apply.setEnabled(False)
        if hasattr(self, "btn_apply_light"):
            self.btn_apply_light.setEnabled(False)
        if hasattr(self, "btn_reload"):
            self.btn_reload.setEnabled(False)
        QApplication.processEvents()

        device = self.device

        def worker():
            device.pause_monitor()
            try:
                ok = device.set_light_settings(p_id, mode, speed, brightness, r, g, b, sleep_time)
                err = "" if ok else (device.last_error or "Unknown error")
                log.info("Apply lighting complete: ok=%s err=%s", ok, err)
                self.bridge.light_apply_finished.emit(ok, err)
            except Exception as e:
                log.exception("Apply lighting failed with exception")
                self.bridge.light_apply_finished.emit(False, f"Exception while applying lighting: {e}\n{traceback.format_exc()}")
            finally:
                device.resume_monitor()

        threading.Thread(target=worker, daemon=True).start()

    def _on_light_apply_finished(self, ok, err):
        self._io_busy = False
        writable = self.device is not None and self.device.is_open()
        self.btn_apply.setEnabled(writable)
        if hasattr(self, "btn_apply_light"):
            self.btn_apply_light.setEnabled(writable)
        if hasattr(self, "btn_reload"):
            self.btn_reload.setEnabled(writable)
        p_id = self.current_profile_id
        if ok:
            self.statusBar.showMessage(f"Profile {p_id} lighting written and confirmed by the mouse.", 4000)
        else:
            msg = "Lighting was NOT confirmed by the mouse."
            if err:
                msg += "\n\n" + err
            QMessageBox.warning(self, "Lighting not written", msg)
            self.statusBar.showMessage(f"Profile {p_id}: lighting not written.", 6000)

    def _on_profile_selector_changed(self, idx: int):
        new_pid = idx + 1
        if new_pid != self.current_profile_id:
            self.current_profile_id = new_pid
            if self.device and self.device.is_open():
                self.statusBar.showMessage(f"Switching to profile {new_pid}...")
                if hasattr(self, "btn_reload"):
                    self.btn_reload.setEnabled(False)
                self.btn_apply.setEnabled(False)
                if hasattr(self, "btn_apply_light"):
                    self.btn_apply_light.setEnabled(False)
                self._switch_profile_async(new_pid)

    def _switch_profile_async(self, new_pid: int):
        device = self.device
        if not device or not device.is_open():
            return

        def worker():
            device.pause_monitor()
            try:
                ok = device.set_active_profile(new_pid)
                if ok:
                    p_id = device.get_active_profile()
                    sensor_data = device.get_sensor_settings(p_id)
                    light_data = device.get_light_settings(p_id)
                    rate_data = device.get_polling_rate(p_id)
                    keys_normal = device.get_keys(p_id, is_fn=False)
                    keys_fn = device.get_keys(p_id, is_fn=True)
                    bad = device.failed_reads(p_id)
                    self.bridge.reload_finished.emit({
                        "p_id": p_id, "sensor_data": sensor_data, "light_data": light_data,
                        "rate_data": rate_data, "keys_normal": keys_normal, "keys_fn": keys_fn,
                        "bad": bad, "switch_failed": False,
                    })
                else:
                    self.bridge.reload_finished.emit({
                        "switch_failed": True, "err": device.last_error or "", "target": new_pid,
                    })
            except Exception as e:
                self.bridge.reload_finished.emit({"error": str(e)})
            finally:
                device.resume_monitor()

        threading.Thread(target=worker, daemon=True).start()

    # --- Live Event Callbacks ---

    def _on_hw_battery(self, pct: int):
        self.battery_bar.setValue(pct)
        self.statusBar.showMessage(f"Battery level: {pct}%", 2000)

    def _on_hw_profile(self, p_id: int):
        if 1 <= p_id <= 5 and p_id != self.current_profile_id:
            self.current_profile_id = p_id
            self.combo_profile.blockSignals(True)
            self.combo_profile.setCurrentIndex(p_id - 1)
            self.combo_profile.blockSignals(False)
            if not self._io_busy:
                self._reload_from_device()

    def _on_hw_dpi_stage(self, stage: int):
        if 1 <= stage <= 4:
            self.dpi_stage_widgets[stage - 1]["radio"].setChecked(True)
            val = self.dpi_stage_widgets[stage - 1]["spin"].value()
            self.statusBar.showMessage(f"DPI Stage {stage} ({val} DPI)", 2000)

    def _on_hw_mode_shift(self):
        self.statusBar.showMessage("Mode Shift pressed on the mouse (the editor layer was not changed)", 3000)

    # --- JSON / .profile Export & Import ---

    def _export_profile_json(self):
        if self.buttons_stack.currentIndex() == 1:
            self._harvest_buttons_from_ui()
        self._apply_aim_dpi_to_keys(self.keys_normal, self.keys_fn)

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Profile JSON", f"mmo7_profile_{self.current_profile_id}.json", "JSON Files (*.json)"
        )
        if not path:
            return

        stage_mask = 0
        current_stage = 1
        for i, w in enumerate(self.dpi_stage_widgets):
            if w["checkbox"].isChecked():
                stage_mask |= (1 << i)
            if w["radio"].isChecked():
                current_stage = i + 1

        data = {
            "ProfileId": self.current_profile_id - 1,
            "ProfileName": f"Profile {self.current_profile_id}",
            "AimDpi": self.spin_aim.value(),
            "FnType": int(self.combo_fn_type.currentData() or FnToggleMode.Toggle),
            "Sensor": {
                "Lift": self.combo_lod.currentIndex(),
                "AngleSnap": 1 if self.chk_angle_snap.isChecked() else 0,
                "CenterOffset": self.slider_rotary.value() if hasattr(self, "slider_rotary") else 2,
                "DpiOnOff": stage_mask,
                "CurrentDpiLevel": current_stage,
                "DpiStages": [
                    [w["spin_x"].value(), w["spin_y"].value() if w["chk_split"].isChecked() else w["spin_x"].value()]
                    for w in self.dpi_stage_widgets
                ],
                "StageColors": [list(w["color"]) for w in self.dpi_stage_widgets]
            },
            "Power": {
                "WakeMode": self.wake_group.checkedId() if hasattr(self, "wake_group") else 0
            },
            "Light": {
                "Mode": int(self.combo_light_mode.currentIndex()),
                "Speed": self.slider_speed.value(),
                "Brightness": self.slider_brightness.value(),
                "Color": list(self.light_color),
                "SleepTime": self.slider_sleep.value()
            },
            "Rate": {"HZ": int(self.rate_group.checkedId())},
            "Keys": {
                "Normal": {
                    name: {"ButtonFunction": int(b.function), "ModifyKeyCodeType": b.modify, "KeyIndex": b.key_index}
                    for name, b in self.keys_normal.items()
                },
                "Fn": {
                    name: {"ButtonFunction": int(b.function), "ModifyKeyCodeType": b.modify, "KeyIndex": b.key_index}
                    for name, b in self.keys_fn.items()
                }
            },
            "Macros": [
                m.to_dict() for m in getattr(self, "macros", {}).values()
            ],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        QMessageBox.information(self, "Export Success", f"Profile successfully saved to:\n{path}")

    def _import_profile_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Profile", "", "Profile Files (*.json *.profile)"
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

            if "Sensor" in data:
                s = data["Sensor"]
                if "Lift" in s:
                    self.combo_lod.setCurrentIndex(1 if s["Lift"] else 0)
                if "AngleSnap" in s:
                    self.chk_angle_snap.setChecked(bool(s["AngleSnap"]))
                if "DpiOnOff" in s:
                    mask = int(s["DpiOnOff"])
                    for i, w in enumerate(self.dpi_stage_widgets):
                        w["checkbox"].setChecked(bool(mask & (1 << i)))
                if "CurrentDpiLevel" in s:
                    lvl = int(s["CurrentDpiLevel"])
                    if 1 <= lvl <= 4:
                        self.dpi_stage_widgets[lvl - 1]["radio"].setChecked(True)

                if "CenterOffset" in s and hasattr(self, "slider_rotary"):
                    co = int(s["CenterOffset"])
                    self.slider_rotary.setValue(max(0, min(4, co)))

                if "DpiStages" in s:
                    for val, w in zip(s["DpiStages"], self.dpi_stage_widgets):
                        if isinstance(val, (list, tuple)) and len(val) >= 2:
                            w["slider_x"].setValue(int(val[0]))
                            w["spin_x"].setValue(int(val[0]))
                            w["slider_y"].setValue(int(val[1]))
                            w["spin_y"].setValue(int(val[1]))
                            is_split = (val[0] != val[1])
                            w["chk_split"].setChecked(is_split)
                            w["y_container"].setVisible(is_split)
                        else:
                            w["slider_x"].setValue(int(val))
                            w["spin_x"].setValue(int(val))
                            w["slider_y"].setValue(int(val))
                            w["spin_y"].setValue(int(val))
                            w["chk_split"].setChecked(False)
                            w["y_container"].setVisible(False)
                elif "DpiX" in s and isinstance(s["DpiX"], int):
                    # Windows H.U.D. .profile format packs 8 DPI stage bytes into a uint64
                    dpi_bytes_x = struct.unpack("<8B", struct.pack("<Q", s["DpiX"] & 0xFFFFFFFFFFFFFFFF))
                    dpi_bytes_y = dpi_bytes_x
                    if "DpiY" in s and isinstance(s["DpiY"], int):
                        dpi_bytes_y = struct.unpack("<8B", struct.pack("<Q", s["DpiY"] & 0xFFFFFFFFFFFFFFFF))
                    for bx, by, w in zip(dpi_bytes_x[:4], dpi_bytes_y[:4], self.dpi_stage_widgets):
                        vx = (bx * 200) if bx > 0 else 800
                        vy = (by * 200) if by > 0 else vx
                        w["slider_x"].setValue(vx)
                        w["spin_x"].setValue(vx)
                        w["slider_y"].setValue(vy)
                        w["spin_y"].setValue(vy)
                        is_split = (vx != vy)
                        w["chk_split"].setChecked(is_split)
                        w["y_container"].setVisible(is_split)

                stage_cols = s.get("StageColors", s.get("StageColorsHudCosmetic", s.get("Colors")))
                if not stage_cols and "DpiColor" in s and isinstance(s["DpiColor"], list) and len(s["DpiColor"]) >= 12:
                    raw_c = s["DpiColor"]
                    stage_cols = [[raw_c[i * 3], raw_c[i * 3 + 1], raw_c[i * 3 + 2]] for i in range(4)]
                if stage_cols:
                    for col, w in zip(stage_cols, self.dpi_stage_widgets):
                        w["color"] = tuple(col)
                        w["btn_color"].setStyleSheet(
                            f"background-color: rgb({col[0]},{col[1]},{col[2]}); border: 1px solid #666; border-radius: 4px;"
                        )

            if "AimDpi" in data:
                self.spin_aim.setValue(max(AIM_DPI_MIN, min(AIM_DPI_MAX, int(data["AimDpi"]))))

            if "FnType" in data:
                fn_mode = FnToggleMode.Toggle if int(data["FnType"]) == int(FnToggleMode.Toggle) else FnToggleMode.Hold
                fn_idx = self.combo_fn_type.findData(fn_mode)
                if fn_idx >= 0:
                    self.combo_fn_type.setCurrentIndex(fn_idx)

            if "Light" in data:
                l = data["Light"]
                mode_val = l.get("Mode", l.get("LightMode", 1))
                self.combo_light_mode.setCurrentIndex(int(mode_val) & 0x0F)
                self.slider_speed.setValue(int(l.get("Speed", l.get("BreathSpeed", 3))))
                self.slider_brightness.setValue(int(l.get("Brightness", l.get("LightBrightness", 8))))
                self.slider_sleep.setValue(int(l.get("SleepTime", 2)))
                if "Color" in l:
                    col = l["Color"]
                elif "FixedColor" in l and isinstance(l["FixedColor"], dict):
                    fc = l["FixedColor"]
                    col = [fc.get("R", 255), fc.get("G", 0), fc.get("B", 0)]
                else:
                    col = [255, 0, 0]
                self.light_color = (int(col[0]), int(col[1]), int(col[2]))
                hex_str = f"#{self.light_color[0]:02X}{self.light_color[1]:02X}{self.light_color[2]:02X}"
                self.btn_light_color.setStyleSheet(f"background-color: {hex_str}; border: 1px solid #666; border-radius: 4px;")
                self.lbl_color_hex.setText(hex_str)
                self._update_light_preview()

            if "Rate" in data and "HZ" in data["Rate"]:
                btn = self.rate_group.button(int(data["Rate"]["HZ"]))
                if btn:
                    btn.setChecked(True)

            valid_slots = {name for name, _, _ in BUTTON_MAP_ORDER}
            if "Keys" in data:
                k = data["Keys"]
                if "Normal" in k and isinstance(k["Normal"], dict):
                    for name, v in k["Normal"].items():
                        if name in valid_slots:
                            code = int(v["ButtonFunction"])
                            fn_val = ButtonFunction(code) if code in ButtonFunction._value2member_map_ else code
                            self.keys_normal[name] = ButtonSetting(fn_val, int(v["ModifyKeyCodeType"]), int(v["KeyIndex"]))
                if "Fn" in k and isinstance(k["Fn"], dict):
                    for name, v in k["Fn"].items():
                        if name in valid_slots:
                            code = int(v["ButtonFunction"])
                            fn_val = ButtonFunction(code) if code in ButtonFunction._value2member_map_ else code
                            self.keys_fn[name] = ButtonSetting(fn_val, int(v["ModifyKeyCodeType"]), int(v["KeyIndex"]))

            if "Macros" in data and isinstance(data["Macros"], list):
                for item in data["Macros"]:
                    m_obj = MacroDefinition.from_dict(item)
                    self.macros[m_obj.index] = m_obj
                self._save_local_macros()
                if hasattr(self, "macro_lib_list"):
                    self._refresh_macro_builder_ui()

            self._refresh_aim_dpi_widget_state()
            self._populate_buttons_table()
            self._refresh_visual_diagram()
            if self.mouse_diagram.selected_slot:
                self._load_slot_into_inspector(self.mouse_diagram.selected_slot)

            QMessageBox.information(
                self, "Import Success",
                f"Profile loaded from:\n{path}\n\nClick 'Apply to Mouse' to commit to hardware."
            )
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to parse profile file:\n{e}")

    def _reset_defaults(self):
        reply = QMessageBox.question(
            self, "Confirm Reset",
            "Reset active profile settings in the editor to factory defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            for i, dpi in enumerate((800, 1600, 3200, 6400)):
                self.dpi_stage_widgets[i]["slider_x"].setValue(dpi)
                self.dpi_stage_widgets[i]["spin_x"].setValue(dpi)
                self.dpi_stage_widgets[i]["slider_y"].setValue(dpi)
                self.dpi_stage_widgets[i]["spin_y"].setValue(dpi)
                self.dpi_stage_widgets[i]["chk_split"].setChecked(False)
                self.dpi_stage_widgets[i]["y_container"].setVisible(False)
                self.dpi_stage_widgets[i]["checkbox"].setChecked(True)
            self.dpi_stage_widgets[0]["radio"].setChecked(True)
            if hasattr(self, "slider_rotary"):
                self.slider_rotary.setValue(2)
            if hasattr(self, "wake_group"):
                self.rb_wake_move.setChecked(True)
            self.spin_aim.setValue(350)
            self.combo_light_mode.setCurrentIndex(1)
            self.light_color = (255, 0, 0)
            self.btn_light_color.setStyleSheet("background-color: #FF0000; border: 1px solid #666; border-radius: 4px;")
            self.lbl_color_hex.setText("#FF0000")
            self._update_light_preview()
            self.rate_group.button(int(PollingRate.HZ_1000)).setChecked(True)
            self.keys_normal = {
                k: ButtonSetting(fn, mod, key) for k, (fn, mod, key) in DEFAULT_BUTTON_SETTINGS.items()
            }
            self.keys_fn = {
                k: ButtonSetting(fn, mod, key) for k, (fn, mod, key) in DEFAULT_BUTTON_SETTINGS.items()
            }
            self._populate_buttons_table()
            self._refresh_visual_diagram()
            if self.mouse_diagram.selected_slot:
                self._load_slot_into_inspector(self.mouse_diagram.selected_slot)
            self.statusBar.showMessage("Settings reset to defaults. Click 'Apply to Mouse' to commit.", 3000)

    def _show_udev_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Install udev Permissions Rule")
        dlg.resize(580, 320)
        vbox = QVBoxLayout(dlg)

        vbox.addWidget(QLabel("<b>Granting Non-Root Access to MMO 7+</b>"))
        vbox.addWidget(QLabel(
            "To configure your mouse without root privileges, Linux requires a udev rule.<br>"
            "Run this command in a terminal to install the rule:"
        ))

        rules_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "99-madcatz-mmo7.rules")
        rule_cmd = (
            f"sudo cp \"{rules_path}\" "
            "/etc/udev/rules.d/ && sudo udevadm control --reload-rules && sudo udevadm trigger"
        )
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setText(rule_cmd)
        edit.setFixedHeight(70)
        vbox.addWidget(edit)

        btn_box = QHBoxLayout()
        btn_copy = QPushButton("📋 Copy Command")
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(rule_cmd))
        btn_box.addWidget(btn_copy)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dlg.accept)
        btn_box.addWidget(btn_close)
        vbox.addLayout(btn_box)

        dlg.exec()

    def closeEvent(self, event):
        if hasattr(self, "_hotplug_timer"):
            self._hotplug_timer.stop()
        if self.device:
            self.device.close()
        event.accept()
