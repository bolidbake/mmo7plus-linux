"""
Protocol definitions and packet builders/parsers for the Mad Catz M.M.O. 7+
Vendor ID: 0x0738 (Mad Catz, Inc.)
Product IDs: 0x1C02 (2.4 GHz Wireless Dongle), 0x0C19 (Wired Mouse)
"""

from enum import IntEnum
from typing import Dict, List, Optional, Tuple
import struct


# USB Vendor / Product IDs
VENDOR_MADCATZ = 0x0738
PRODUCT_MMO7_DONGLE = 0x1C02
PRODUCT_MMO7_WIRED = 0x0C19

# HID Report IDs
REPORT_SENSOR = 0x04       # DPI & sensor configuration (56 bytes)
REPORT_LIGHT = 0x05        # RGB lighting configuration (15 bytes)
REPORT_RATE = 0x06         # Polling rate configuration (9 bytes)
REPORT_WAKE = 0x07         # Wake mode configuration (8 bytes)
REPORT_KEYS_NORMAL = 0x08  # Normal layer button bindings (95 bytes)
REPORT_KEYS_FN = 0x18      # Fn/Shift layer button bindings (95 bytes)
KEYS_REPORT_LEN = 95
REPORT_MACRO = 0x09        # Onboard macro sequence (131 bytes)
REPORT_FW_VER = 0x0B       # Firmware version query (8 bytes)
REPORT_PROFILE = 0x0C      # Active profile query/set (10 bytes)
REPORT_QUERY = 0xA0        # Query initiation trigger (8 bytes)

# Live status report IDs (Input Reports from device)
REPORT_STATUS_INPUT = 0x03 # Input report for battery, profile change, DPI change
REPORT_MODESHIFT_INPUT = 0x02 # Input report on mode shift button press


class ButtonFunction(IntEnum):
    Blocked = 0
    ButtonOff = 1
    Click = 2
    Menu = 3
    UniversalScrolling = 4
    IEBackward = 5
    IEForward = 6
    DoubleClick = 7
    Firebutton = 8
    ScrollUp = 9
    ScrollDown = 10
    TiltLeft = 11
    TiltRight = 12
    DpiCycle = 13
    DpiUp = 14
    DpiDown = 15
    EasyAimDpi = 16
    AssignShortcut = 17
    AssignMacro = 18
    WindowsKey = 20
    OpenPlayer = 21
    PreTrack = 22
    NextTrack = 23
    PlayPause = 24
    Stop = 25
    Mute = 26
    VolumeUp = 27
    VolumeDown = 28
    WindowsCalculator = 29
    WindowsEMail = 30
    WindowsWwwFavorites = 31
    WindowsWwwForward = 32
    WindowsWwwBack = 33
    WindowsWwwStop = 34
    WindowsMyComputer = 35
    WindowsWwwRefresh = 36
    WindowsIEBrowseHome = 37
    WindowsWwwSearch = 38
    FN = 39
    ReportRateLoop = 40
    ProfileCycle = 52
    ProfileUp = 53
    ProfileDown = 54
    RFModeKeying = 60
    LeftActive = 61
    RightActive = 62


class LightMode(IntEnum):
    Off = 0
    Static = 1
    Breathe = 2
    Neon = 3
    ColorLoop = 4


class PollingRate(IntEnum):
    HZ_125 = 0  # 8 ms
    HZ_250 = 1  # 4 ms
    HZ_500 = 2  # 2 ms
    HZ_1000 = 3 # 1 ms


class ModifierMask(IntEnum):
    NONE = 0
    CTRL = 1
    SHIFT = 2
    ALT = 4
    WIN = 8


# Hold=0 / Toggle=90 is inferred (the HUD calls them HoldPress / ShortPress; the mouse had 90 on the
# profile configured for toggle and 0 elsewhere). The numeric values themselves are not confirmed.
class FnToggleMode(IntEnum):
    Hold = 0
    Toggle = 90


# Standard USB HID Keycodes mapping for commonly used keys
HID_KEY_NAMES = {
    0x00: "None",
    # Letters
    0x04: "A", 0x05: "B", 0x06: "C", 0x07: "D", 0x08: "E", 0x09: "F",
    0x0A: "G", 0x0B: "H", 0x0C: "I", 0x0D: "J", 0x0E: "K", 0x0F: "L",
    0x10: "M", 0x11: "N", 0x12: "O", 0x13: "P", 0x14: "Q", 0x15: "R",
    0x16: "S", 0x17: "T", 0x18: "U", 0x19: "V", 0x1A: "W", 0x1B: "X",
    0x1C: "Y", 0x1D: "Z",
    # Digits
    0x1E: "1", 0x1F: "2", 0x20: "3", 0x21: "4", 0x22: "5",
    0x23: "6", 0x24: "7", 0x25: "8", 0x26: "9", 0x27: "0",
    # Controls
    0x28: "Enter", 0x29: "Escape", 0x2A: "Backspace", 0x2B: "Tab", 0x2C: "Space",
    0x2D: "-", 0x2E: "=", 0x2F: "[", 0x30: "]", 0x31: "\\",
    0x33: ";", 0x34: "'", 0x35: "`", 0x36: ",", 0x37: ".", 0x38: "/",
    # Function Keys
    0x3A: "F1", 0x3B: "F2", 0x3C: "F3", 0x3D: "F4", 0x3E: "F5", 0x3F: "F6",
    0x40: "F7", 0x41: "F8", 0x42: "F9", 0x43: "F10", 0x44: "F11", 0x45: "F12",
    # Navigation
    0x49: "Insert", 0x4A: "Home", 0x4B: "Page Up",
    0x4C: "Delete", 0x4D: "End", 0x4E: "Page Down",
    0x4F: "Right Arrow", 0x50: "Left Arrow", 0x51: "Down Arrow", 0x52: "Up Arrow",
    # Keypad
    0x53: "Num Lock", 0x54: "Keypad /", 0x55: "Keypad *", 0x56: "Keypad -",
    0x57: "Keypad +", 0x58: "Keypad Enter",
    0x59: "Keypad 1", 0x5A: "Keypad 2", 0x5B: "Keypad 3",
    0x5C: "Keypad 4", 0x5D: "Keypad 5", 0x5E: "Keypad 6",
    0x5F: "Keypad 7", 0x60: "Keypad 8", 0x61: "Keypad 9",
    0x62: "Keypad 0", 0x63: "Keypad ."
}

# The 30 hardware button slot mappings defined in MOJO7/MMO7 driver
# Physical locations verified from KeyAssignPageView.xaml & KeyAssignPageViewModel.cs
BUTTON_MAP_ORDER = [
    ("LeftClick", 0, "Left Click"),
    ("RightClick", 1, "Right Click"),
    ("WheelClick", 2, "Scroll Wheel Click"),
    # slot 3: blocked
    # slot 4: blocked
    ("SwitchProfile", 5, "Top-Left Outer Button (Profile)"),
    ("LeftActive", 6, "Left Action Lock Button"),
    ("RightActive", 7, "Right Action Lock Button"),
    ("DpiLoop", 8, "DPI Cycle Button"),
    ("FN", 9, "Top-Right Outer Button (Mode Shift / FN)"),
    ("ShortutKey1", 10, "Thumb Front Button (Button 1)"),
    ("ForwardClick", 11, "Thumb Ridge Front (Forward)"),
    ("BackwardClick", 12, "Thumb Ridge Rear (Backward)"),
    ("ShortutKey2", 13, "Thumb Rear Button (Button 2)"),
    ("ShortutKey3", 14, "Thumb Wing Edge (Button 3)"),
    ("ShortutKey4", 15, "5D Rocker Forward (Button 4)"),
    ("ShortutKey5", 16, "5D Rocker Down (Button 5)"),
    ("ShortutKey6", 17, "5D Rocker Up (Button 6)"),
    ("ShortutKey7", 18, "5D Rocker Backward (Button 7)"),
    ("AccurateClick", 19, "5D Rocker Center (Precision Aim)"),
    # slot 20: blocked
    ("ShortutKey8", 21, "Extra Slot 8 (Unmapped)"),
    ("ShortutKey9", 22, "Extra Slot 9 (Unmapped)"),
    ("ShortutKey10", 23, "Extra Slot 10 (Unmapped)"),
    # slot 24: blocked
    # slot 25: blocked
    ("WheelLeft", 26, "Thumb Barrel Scroll Left"),
    ("WheelRight", 27, "Thumb Barrel Scroll Right"),
    ("WheelDown", 28, "Scroll Wheel Down"),
    ("WheelUp", 29, "Scroll Wheel Up"),
]


class ButtonSetting:
    def __init__(self, function: ButtonFunction = ButtonFunction.Click,
                 modify: int = 0, key_index: int = 0):
        self.function = function
        self.modify = modify  # modifier mask (Ctrl=1, Shift=2, Alt=4, Win=8) or FnType (0 or 90)
        self.key_index = key_index

    def to_bytes(self) -> bytes:
        return bytes([int(self.function) & 0xFF, self.modify & 0xFF, self.key_index & 0xFF])

    @classmethod
    def from_bytes(cls, b: bytes) -> 'ButtonSetting':
        if len(b) < 3:
            return cls()
        return cls(ButtonFunction(b[0]), b[1], b[2])


# --- Packet Builders ---

def build_query_packet(target_report_id: int, length: int, profile_id: int = 0) -> bytes:
    """Build the 8-byte setup report sent to Report ID 0xA0 to trigger a feature query."""
    return bytes([REPORT_QUERY, target_report_id, length, 0x00, profile_id, 0x00, 0x00, 0x00])


def build_profile_packet(profile_id: int, count: int = 5) -> bytes:
    """
    Build 10-byte packet to switch or set active profile.
    profile_id is 1-indexed (1 to 5).
    """
    p_id = max(1, min(5, profile_id))
    return bytes([
        REPORT_PROFILE,
        0x0A,
        p_id,
        (~p_id) & 0xFF,
        count,
        (~count) & 0xFF,
        0x00, 0x00, 0x00, 0x00
    ])


def build_rate_packet(profile_id: int, rate: PollingRate) -> bytes:
    """
    Build 9-byte packet to set polling rate.
    Interval: 125Hz -> 8, 250Hz -> 4, 500Hz -> 2, 1000Hz -> 1.
    """
    intervals = {
        PollingRate.HZ_125: 8,
        PollingRate.HZ_250: 4,
        PollingRate.HZ_500: 2,
        PollingRate.HZ_1000: 1
    }
    interval = intervals.get(rate, 1)
    return bytes([
        REPORT_RATE,
        0x09,
        profile_id,
        interval,
        (~interval) & 0xFF,
        0x00, 0x00, 0x00, 0x00
    ])


def build_wake_packet(mode: int) -> bytes:
    """
    Build 8-byte packet for wireless wake mode (REPORT_WAKE = 0x07).
    mode: 0 = Wake on Movement, 1 = Wake on Button Click (Key).
    """
    m = 1 if mode else 0
    return bytes([REPORT_WAKE, 0x08, m, (~m) & 0xFF, 0x01, 0xFE, 0x00, 0x00])


def parse_wake_packet(reply: Optional[bytes]) -> int:
    """
    Parse 8-byte reply for wake mode.
    Returns 0 for Wake on Movement, 1 for Wake on Button Click.
    """
    if reply and len(reply) >= 3 and reply[0] == REPORT_WAKE:
        return 1 if reply[2] != 0 else 0
    return 0


def build_light_packet(profile_id: int, mode: LightMode, speed: int,
                       brightness: int, r: int, g: int, b: int, sleep_time: int = 2) -> bytes:
    """
    Build 15-byte packet for RGB lighting.
    Checksum: 16-bit sum of bytes [3:11] (everything after the ProfileId), big-endian at bytes [11:13].
    """
    payload = bytes([
        profile_id,
        int(mode) & 0xFF,
        max(1, min(10, speed)),
        max(1, min(10, brightness)),
        r & 0xFF,
        g & 0xFF,
        b & 0xFF,
        sleep_time & 0xFF,
        0x00  # reserve
    ])
    # Verified against real replies and the DLL's SendLight: the checksum is the 16-bit sum of the
    # struct bytes AFTER the ProfileId byte (bytes 3..10 of the report), big-endian at bytes 11-12.
    chk = sum(payload[1:]) & 0xFFFF
    return bytes([REPORT_LIGHT, 0x0F]) + payload + struct.pack('>H', chk) + bytes([0x00, 0x00])


def build_sensor_packet(profile_id: int,
                        dpi_stages: List[Tuple[int, int]], # list of 4 (x_dpi, y_dpi) tuples
                        current_stage: int = 1,            # 1-4
                        stage_mask: int = 0x0F,            # 0x0F = all 4 enabled
                        stage_colors: Optional[List[Tuple[int, int, int]]] = None,
                        lift: int = 0, angle_snap: int = 1,
                        center_offset: int = 2, indication_type: int = 1) -> bytes:
    """
    Build 56-byte packet for DPI stages and sensor parameters.
    Real DPI = stored_byte * 200 (stored_byte = dpi // 200).
    Checksum: 16-bit sum of bytes [3:50] (everything after the ProfileId), big-endian at [50:52].
    center_offset / indication_type should be the values read from the mouse (a real mouse
    returned CenterOffset 0 and DpiIndicationType 3 on factory profiles).
    """
    buf = bytearray(56)
    buf[0] = REPORT_SENSOR
    buf[1] = 0x38  # 56 bytes total
    buf[2] = profile_id
    buf[3] = lift & 0xFF
    buf[4] = angle_snap & 0xFF
    buf[5] = stage_mask & 0xFF
    buf[6] = 0x00  # reserve
    buf[7] = center_offset & 0xFF

    # 8 bytes DpiX (up to 8 stages, first 4 active). Stored byte * 200 = DPI; HUD max is 130 (26000).
    for i in range(8):
        if i < len(dpi_stages):
            buf[8 + i] = max(1, min(130, dpi_stages[i][0] // 200))
        else:
            buf[8 + i] = 0

    # 8 bytes DpiY
    for i in range(8):
        if i < len(dpi_stages):
            buf[16 + i] = max(1, min(130, dpi_stages[i][1] // 200))
        else:
            buf[16 + i] = 0

    buf[24] = max(1, min(4, current_stage))

    # 24 bytes stage colors (8 stages * 3 RGB). The mouse stores these (they come back in its replies
    # and the HUD writes them); what the mouse itself does with them is not confirmed.
    default_colors = [
        (255, 0, 0),     # Stage 1: Red
        (0, 128, 0),     # Stage 2: Green
        (0, 0, 255),     # Stage 3: Blue
        (255, 255, 255), # Stage 4: White
        (255, 255, 0),
        (255, 0, 255),
        (0, 255, 255),
        (255, 128, 0)
    ]
    colors = stage_colors if stage_colors else default_colors
    for i in range(8):
        c = colors[i] if i < len(colors) else (0, 0, 0)
        buf[25 + i * 3] = c[0] & 0xFF
        buf[26 + i * 3] = c[1] & 0xFF
        buf[27 + i * 3] = c[2] & 0xFF

    buf[49] = indication_type & 0xFF

    # Checksum of bytes 3..49 (the struct after the ProfileId byte)
    chk = sum(buf[3:50]) & 0xFFFF
    buf[50] = (chk >> 8) & 0xFF
    buf[51] = chk & 0xFF
    # bytes 52..55 remain 0
    return bytes(buf)


def build_keys_packet(report_id: int, profile_id: int, buttons: Dict[str, ButtonSetting]) -> bytes:
    """
    Build 95-byte packet for button configuration (Normal: 0x08, Fn Layer: 0x18).
    Checksum: 16-bit sum of bytes [3:93] (everything after the ProfileId), big-endian at bytes [93:95].
    """
    buf = bytearray(KEYS_REPORT_LEN)
    buf[0] = report_id
    buf[1] = KEYS_REPORT_LEN      # 0x5F (95): the length byte the Windows driver uses (the report is 95 bytes long)
    buf[2] = profile_id

    # 30 slots * 3 bytes = 90 bytes (offsets 3..92)
    slot_map = {name: (slot, desc) for name, slot, desc in BUTTON_MAP_ORDER}
    for name, (slot, desc) in slot_map.items():
        btn = buttons.get(name)
        if btn:
            idx = 3 + slot * 3
            if idx + 2 < KEYS_REPORT_LEN - 2:
                buf[idx] = int(btn.function) & 0xFF
                buf[idx + 1] = btn.modify & 0xFF
                buf[idx + 2] = btn.key_index & 0xFF

    chk = sum(buf[3:KEYS_REPORT_LEN - 2]) & 0xFFFF
    buf[KEYS_REPORT_LEN - 2] = (chk >> 8) & 0xFF
    buf[KEYS_REPORT_LEN - 1] = chk & 0xFF
    return bytes(buf)


# --- Reply decoding helpers (verified against a real mouse) ---

def parse_firmware(reply: bytes) -> str:
    """Firmware reply bytes 2 and 3 are hex digits: 01 22 means version 1.22."""
    return f"{reply[2]:x}.{reply[3]:x}"


def light_mode_from_byte(value: int) -> LightMode:
    """The mouse may return factory values like 0x22 in the mode byte; the HUD masks with 0x0F."""
    return LightMode(min(4, value & 0x0F))


def build_keys_chunks(report_id: int, profile_id: int, buttons: Dict[str, ButtonSetting]) -> List[bytes]:
    """
    Key tables are NOT written as one 95-byte report. The Windows drivers (SendKeys / SendKeys_Fn in both
    hidDriver.dll and hidDriver_dongle.dll) split the data into TWO Feature reports, each 64 bytes on USB
    (matching the HID report descriptor's 1 + 0x3F = 64-byte feature size for 0x08 and 0x18):

        [report id][length][profile id][chunk index][60 data bytes]

    chunk 0: length 0x40 (4 + 60), data = bytes 0..59 of the stream
    chunk 1: length 0x24 (4 + 32), data = bytes 60..91 of the stream (padded with 28 zeroes to 64 bytes)

    The stream is the 90 slot bytes followed by the 16-bit big-endian checksum (the same bytes
    build_keys_packet puts at [3:93] and [93:95]). The mouse's *reply* to a query is the single
    contiguous 95-byte report, which is why reads never needed this.
    """
    packet = build_keys_packet(report_id, profile_id, buttons)
    stream = packet[3:KEYS_REPORT_LEN]           # 90 slot bytes + 2 checksum bytes
    stream = stream + bytes(120 - len(stream))
    chunks = []
    for index, length in ((0, 0x40), (1, 0x24)):
        data = stream[index * 60:(index + 1) * 60]
        frame = bytes([report_id, length, profile_id, index]) + data
        chunks.append(frame)
    return chunks


# --- Precision Aim ("Easy Aim") DPI ---------------------------------------------------------------
# The aim DPI is not a separate setting on the mouse. It is stored inside every button whose function
# is EasyAimDpi (16), in BOTH layers (the HUD's SaveAimDpi does exactly this):
#     dpi <= 12750 :  modify = 0, key = dpi // 50
#     dpi  > 12750 :  modify = 1, key = dpi // 100
# (the HUD clamps to 25500). Your real profiles hold function 16, modify 0, key 7 = 350 DPI.

AIM_DPI_MIN = 50
AIM_DPI_MAX = 25500


def encode_aim_dpi(dpi: int) -> Tuple[int, int]:
    """Return (modify, key_index) for an aim DPI."""
    num = max(AIM_DPI_MIN, min(AIM_DPI_MAX, int(dpi)))
    if num > 12750:
        return 1, (num // 2 // 50) & 0xFF
    return 0, (num // 50) & 0xFF


def decode_aim_dpi(modify: int, key_index: int) -> Optional[int]:
    """Aim DPI stored in an EasyAimDpi button, or None if the modify byte is not 0 or 1."""
    if modify == 0:
        return key_index * 50
    if modify == 1:
        return key_index * 100
    return None


def aim_dpi_from_buttons(buttons: Dict[str, ButtonSetting]) -> Optional[int]:
    """Read the aim DPI from a layer's buttons (AccurateClick first, then any EasyAimDpi button)."""
    ordered = sorted(buttons.items(), key=lambda kv: kv[0] != "AccurateClick")
    for _name, btn in ordered:
        if int(btn.function) == int(ButtonFunction.EasyAimDpi):
            return decode_aim_dpi(btn.modify, btn.key_index)
    return None


def apply_aim_dpi(buttons: Dict[str, ButtonSetting], dpi: int) -> int:
    """Write the aim DPI into every EasyAimDpi button of a layer; returns how many were changed."""
    modify, key = encode_aim_dpi(dpi)
    count = 0
    for btn in buttons.values():
        if int(btn.function) == int(ButtonFunction.EasyAimDpi):
            btn.modify, btn.key_index = modify, key
            count += 1
    return count


# --- Onboard Macro Protocol (Report 0x09, 131 bytes logical / three 64-byte write chunks) --------

MACRO_REPORT_LEN = 131
MACRO_MAX_STEPS = 50


class MacroLoopType(IntEnum):
    LoopCount = 0         # Repeat N times (MacroExecBehavior = count)
    LoopToPressAgain = 1  # Toggle loop until pressed again
    LoopToRelease = 2     # Loop continuously while button is held down


# Extended HidKey codes used inside Macro steps (from mcz.allinone.common.Enum.HidKey)
MACRO_MOUSE_AND_MOD_KEYS: Dict[int, str] = {
    0xE0: "Left Ctrl",
    0xE1: "Left Shift",
    0xE2: "Left Alt",
    0xE3: "Left Super",
    0xE4: "Right Ctrl",
    0xE5: "Right Shift",
    0xE6: "Right Alt",
    0xE7: "Right Super",
    0xF0: "Mouse Left Click",
    0xF1: "Mouse Right Click",
    0xF2: "Mouse Middle Click",
    0xF3: "Mouse Back (Button 4)",
    0xF4: "Mouse Forward (Button 5)",
    0xF5: "Mouse Tilt Left",
    0xF6: "Mouse Tilt Right",
    0xF7: "Mouse Wheel Up",
    0xF8: "Mouse Wheel Down",
}

MACRO_KEY_NAMES: Dict[int, str] = {
    **{k: v for k, v in HID_KEY_NAMES.items() if k != 0},
    **MACRO_MOUSE_AND_MOD_KEYS,
}


class MacroStep:
    """
    A single action in an onboard macro.
    - For key/mouse actions (key_code >= 0x04):
        is_release: False = Press (Make), True = Release (Break)
        delay_ms: delay after this event in ms (encoded in 10ms units, 1..127 -> 10..1270ms,
                  or followed by a standalone delay entry for longer delays).
    - For standalone delay actions (key_code in 1, 2, 3):
        key_code 1 = 25ms unit, 2 = 50ms unit, 3 = 100ms unit.
    """
    def __init__(self, key_code: int = 0x04, is_release: bool = False, delay_ms: int = 50):
        self.key_code = key_code & 0xFF
        self.is_release = bool(is_release)
        self.delay_ms = max(0, int(delay_ms))

    def to_dict(self) -> Dict:
        return {
            "key_code": self.key_code,
            "is_release": self.is_release,
            "delay_ms": self.delay_ms,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'MacroStep':
        return cls(
            key_code=int(d.get("key_code", 0x04)),
            is_release=bool(d.get("is_release", False)),
            delay_ms=int(d.get("delay_ms", 50)),
        )

    def format_label(self) -> str:
        if self.key_code in (1, 2, 3):
            return f"⏱ Delay {self.delay_ms} ms"
        name = MACRO_KEY_NAMES.get(self.key_code, f"Key 0x{self.key_code:02X}")
        act = "↑ Release" if self.is_release else "↓ Press  "
        return f"{act}  {name:<22s}  (+{self.delay_ms} ms)"


class MacroDefinition:
    """Represents an onboard macro slot (Index 1..255)."""
    def __init__(self, index: int = 1, name: str = "Macro 1",
                 loop_type: MacroLoopType = MacroLoopType.LoopCount,
                 loop_count: int = 1,
                 steps: Optional[List[MacroStep]] = None):
        self.index = max(1, min(255, int(index)))
        self.name = str(name)[:20]
        self.loop_type = MacroLoopType(int(loop_type))
        self.loop_count = max(1, min(255, int(loop_count)))
        self.steps: List[MacroStep] = list(steps) if steps else []

    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "name": self.name,
            "loop_type": int(self.loop_type),
            "loop_count": self.loop_count,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'MacroDefinition':
        return cls(
            index=int(d.get("index", 1)),
            name=str(d.get("name", "Macro 1")),
            loop_type=MacroLoopType(int(d.get("loop_type", 0))),
            loop_count=int(d.get("loop_count", 1)),
            steps=[MacroStep.from_dict(s) for s in d.get("steps", [])],
        )


def encode_macro_hw_pairs(steps: List[MacroStep]) -> List[Tuple[int, int]]:
    """
    Convert MacroStep list into up to 50 (AttributeCode, KeyCode) pairs matching MacroModel.cs:
    - Standalone delay step (key_code in 1, 2, 3):
        <= 6375ms  -> KeyCode=1 (25ms),  AttributeCode = delay // 25
        <= 12750ms -> KeyCode=2 (50ms),  AttributeCode = delay // 50
        >  12750ms -> KeyCode=3 (100ms), AttributeCode = min(255, delay // 100)
    - Key/Mouse Press/Release step:
        AttributeCode = ((1 if is_release else 0) << 7) | (delay_units & 0x7F)
        where delay_units = min(127, max(1, delay_ms // 10)) (in 10ms ticks, as in MacroSettingPageView.xaml.cs).
    """
    pairs: List[Tuple[int, int]] = []
    for st in steps:
        if len(pairs) >= MACRO_MAX_STEPS:
            break
        if st.key_code in (1, 2, 3):
            d = min(25500, max(25, st.delay_ms))
            if d <= 6375:
                pairs.append((max(1, d // 25) & 0xFF, 1))
            elif d <= 12750:
                pairs.append((max(1, d // 50) & 0xFF, 2))
            else:
                pairs.append((max(1, d // 100) & 0xFF, 3))
        else:
            delay_ticks = min(127, max(1, st.delay_ms // 10)) if st.delay_ms >= 10 else max(1, st.delay_ms)
            attr = ((1 if st.is_release else 0) << 7) | (delay_ticks & 0x7F)
            pairs.append((attr & 0xFF, st.key_code & 0xFF))
    return pairs


def build_macro_packet(macro: MacroDefinition) -> bytes:
    """
    Build the 131-byte (0x83) logical Report 0x09 packet for a macro.
    Layout (from DriverApi.MACRO and SendMacro in hiddriver.dll):
        buf[0]      = 0x09 (REPORT_MACRO)
        buf[1]      = 0x83 (131)
        buf[2]      = Index (1..255)
        buf[3]      = MacroCodeType (LoopType: 0, 1, 2)
        buf[4..6]   = Reserve[3] (0, 0, 0)
        buf[7]      = MacroExecBehavior (LoopCount: 1..255)
        buf[8..27]  = MacroName[20] (UTF-8, zero-padded)
        buf[28]     = KeyMacroNumber (number of active pairs, 0..50)
        buf[29..128]= KeyInfo[50] (50 * (AttributeCode, KeyCode))
        buf[129..130]= 16-bit big-endian sum of buf[3:129]
    """
    buf = bytearray(MACRO_REPORT_LEN)
    buf[0] = REPORT_MACRO
    buf[1] = MACRO_REPORT_LEN
    buf[2] = macro.index & 0xFF
    buf[3] = int(macro.loop_type) & 0xFF
    # buf[4..6] = Reserve (0)
    buf[7] = max(1, min(255, macro.loop_count)) & 0xFF

    name_bytes = macro.name.encode("utf-8")[:20]
    buf[8:8 + len(name_bytes)] = name_bytes

    pairs = encode_macro_hw_pairs(macro.steps)
    buf[28] = len(pairs) & 0xFF
    for i, (attr, key_code) in enumerate(pairs[:MACRO_MAX_STEPS]):
        buf[29 + i * 2] = attr & 0xFF
        buf[30 + i * 2] = key_code & 0xFF

    chk = sum(buf[3:129]) & 0xFFFF
    buf[129] = (chk >> 8) & 0xFF
    buf[130] = chk & 0xFF
    return bytes(buf)


def build_macro_chunks(macro: MacroDefinition) -> List[bytes]:
    """
    Split the 131-byte macro packet into THREE 64-byte Feature reports (matching SendMacro in hiddriver.dll):
        chunk 0: [0x09, 0x40, index, 0x00] + stream[0:60]  (64 bytes)
        chunk 1: [0x09, 0x40, index, 0x01] + stream[60:120] (64 bytes)
        chunk 2: [0x09, 0x0C, index, 0x02] + stream[120:128] + 52 zero bytes (64 bytes)
    where stream = packet[3:131] (126 payload bytes after Index + 2 checksum bytes = 128 bytes).
    """
    packet = build_macro_packet(macro)
    stream = packet[3:MACRO_REPORT_LEN]  # 128 bytes
    stream = stream + bytes(180 - len(stream))
    chunks = []
    for chunk_idx, length in ((0, 0x40), (1, 0x40), (2, 0x0C)):
        data = stream[chunk_idx * 60:(chunk_idx + 1) * 60]
        frame = bytes([REPORT_MACRO, length, macro.index & 0xFF, chunk_idx]) + data
        chunks.append(frame)
    return chunks


def parse_macro_packet(res: bytes) -> Optional[MacroDefinition]:
    """Parse a 131-byte Report 0x09 reply from the mouse into a MacroDefinition."""
    if not res or len(res) < 131 or res[0] != REPORT_MACRO:
        return None
    idx = res[2]
    if idx == 0 or idx == 0xFF:
        return None
    loop_type_val = res[3]
    loop_type = MacroLoopType(loop_type_val) if loop_type_val in (0, 1, 2) else MacroLoopType.LoopCount
    loop_count = max(1, res[7])
    raw_name = bytes(res[8:28]).split(b"\x00", 1)[0]
    try:
        name = raw_name.decode("utf-8", errors="replace").strip() or f"Macro {idx}"
    except Exception:
        name = f"Macro {idx}"
    count = min(MACRO_MAX_STEPS, res[28])
    steps: List[MacroStep] = []
    for i in range(count):
        attr = res[29 + i * 2]
        key_code = res[30 + i * 2]
        if key_code == 0 and attr == 0:
            continue
        if key_code == 1:
            steps.append(MacroStep(key_code=1, is_release=False, delay_ms=attr * 25))
        elif key_code == 2:
            steps.append(MacroStep(key_code=2, is_release=False, delay_ms=attr * 50))
        elif key_code == 3:
            steps.append(MacroStep(key_code=3, is_release=False, delay_ms=attr * 100))
        elif key_code != 254:
            is_rel = bool(attr & 0x80)
            ticks = attr & 0x7F
            steps.append(MacroStep(key_code=key_code, is_release=is_rel, delay_ms=max(10, ticks * 10)))
    return MacroDefinition(index=idx, name=name, loop_type=loop_type, loop_count=loop_count, steps=steps)
