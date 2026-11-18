"""
Device management and HID raw communication for Mad Catz M.M.O. 7+
Handles sysfs discovery, permissions checking, HID feature ioctls,
and background event listening.
"""

import fcntl
import glob
import logging
import os
import select
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

from .protocol import (
    VENDOR_MADCATZ, PRODUCT_MMO7_DONGLE, PRODUCT_MMO7_WIRED,
    REPORT_SENSOR, REPORT_LIGHT, REPORT_RATE, REPORT_KEYS_NORMAL,
    REPORT_KEYS_FN, REPORT_MACRO, MACRO_REPORT_LEN, REPORT_FW_VER, REPORT_PROFILE,
    ButtonFunction, ButtonSetting, LightMode, PollingRate, MacroDefinition,
    BUTTON_MAP_ORDER,
    build_query_packet, build_profile_packet, build_rate_packet,
    build_light_packet, build_sensor_packet, build_keys_packet,
    parse_firmware, light_mode_from_byte, build_keys_chunks,
    build_macro_packet, build_macro_chunks, parse_macro_packet
)


# Safety switch: writing to the mouse is ON by default (set MMO7_ALLOW_WRITES=0 to disable writes).
WRITES_ENABLED = os.environ.get("MMO7_ALLOW_WRITES", "1") != "0"


def _IOC(dir_flag: int, type_char: str, nr: int, size: int) -> int:
    return (dir_flag << 30) | ((size & 0x3FFF) << 16) | (ord(type_char) << 8) | nr

def HIDIOCSFEATURE(length: int) -> int:
    return _IOC(3, 'H', 0x06, length)

def HIDIOCGFEAT(length: int) -> int:
    return _IOC(3, 'H', 0x07, length)


class DeviceInfo:
    def __init__(self, node: str, interface: str, is_dongle: bool, is_writable: bool):
        self.node = node                 # e.g. /dev/hidraw3
        self.interface = interface       # e.g. "02"
        self.is_dongle = is_dongle       # True = 1c02, False = 0c19 (wired)
        self.is_writable = is_writable


def discover_mmo7() -> Optional[Dict[str, DeviceInfo]]:
    """
    Scans /sys/class/hidraw/ to find all interfaces belonging to the MMO 7+.
    Returns a dict mapping interface numbers ('00', '01', '02', '03') to DeviceInfo
    for the preferred connection, or None if no MMO 7+ device is found.
    When both wireless dongle and wired (often charging) are present, prefer the wired connection.
    """
    dongle_ifaces: Dict[str, DeviceInfo] = {}
    wired_ifaces: Dict[str, DeviceInfo] = {}
    dongle_ids = ("00000738:00001C02", "0738:1C02")
    wired_ids = ("00000738:00000C19", "0738:0C19")

    for d in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent_path = os.path.join(d, "device", "uevent")
        if not os.path.exists(uevent_path):
            continue
        try:
            content = open(uevent_path, "r").read().upper()
        except OSError:
            continue

        is_dongle = any(x in content for x in dongle_ids)
        is_wired = any(x in content for x in wired_ids)

        if not (is_dongle or is_wired):
            continue

        dev_real = os.path.realpath(os.path.join(d, "device"))
        # Check bInterfaceNumber in parent USB interface directory
        intf_file = os.path.join(dev_real, "..", "bInterfaceNumber")
        intf_num = None
        if os.path.exists(intf_file):
            try:
                intf_num = open(intf_file, "r").read().strip().zfill(2)
            except OSError:
                pass

        if intf_num is None:
            # Fallback: check device path e.g. "1-3:1.2"
            for part in dev_real.split("/"):
                if ":1." in part:
                    intf_num = part.split(":1.")[-1].zfill(2)
                    break

        node_path = "/dev/" + os.path.basename(d)
        is_writable = os.access(node_path, os.R_OK | os.W_OK)

        if intf_num:
            info = DeviceInfo(node_path, intf_num, is_dongle, is_writable)
            if is_dongle:
                dongle_ifaces[intf_num] = info
            else:
                wired_ifaces[intf_num] = info

    # MMO7_PREFER=dongle|wired overrides the default (wired first, since a cable usually means charging)
    prefer = os.environ.get("MMO7_PREFER", "wired").lower()
    first, second = (dongle_ifaces, wired_ifaces) if prefer == "dongle" else (wired_ifaces, dongle_ifaces)
    if "02" in first:
        return first
    if "02" in second:
        return second
    if wired_ifaces:
        return wired_ifaces
    if dongle_ifaces:
        return dongle_ifaces
    return None


class MMO7Device:
    def __init__(self, config_node: str, is_dongle: bool = False):
        self.config_node = config_node
        self.is_dongle = is_dongle
        self.fd: Optional[int] = None
        self._lock = threading.RLock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._monitor_pause_count = 0
        self._monitor_pause_cond = threading.Condition(self._lock)

        # Safety bookkeeping: which (kind, profile) were read successfully this session, the sensor
        # fields the builder cannot see in the GUI, and the last error text.
        self._read_ok = set()
        self._sensor_extra = {}
        self.last_error = ""
        self.last_ack = None      # (cmd byte, status, time) from the mouse's write acknowledgment, if seen

        # Status callbacks
        self.on_battery_changed: Optional[Callable[[int], None]] = None
        self.on_profile_changed: Optional[Callable[[int], None]] = None
        self.on_dpi_stage_changed: Optional[Callable[[int], None]] = None
        self.on_mode_shift_toggled: Optional[Callable[[], None]] = None

    def open(self) -> bool:
        """Open the device node for reading and writing."""
        with self._lock:
            if self.fd is not None:
                return True
            try:
                self.fd = os.open(self.config_node, os.O_RDWR | os.O_NONBLOCK)
                return True
            except OSError as e:
                self.fd = None
                return False

    def close(self):
        """Stop background monitor and close device file descriptor."""
        self.stop_monitor()
        with self._lock:
            if self.fd is not None:
                try:
                    os.close(self.fd)
                except OSError:
                    pass
                self.fd = None

    def is_open(self) -> bool:
        return self.fd is not None

    def send_feature(self, data: bytes) -> bool:
        """Send a HID feature report using HIDIOCSFEATURE ioctl."""
        with self._lock:
            if self.fd is None:
                return False
            try:
                buf = bytearray(data)
                log.debug("send_feature(len=%d, id=0x%02x): %s", len(buf), buf[0], data.hex())
                fcntl.ioctl(self.fd, HIDIOCSFEATURE(len(buf)), buf)
                return True
            except OSError as e:
                log.debug("send_feature(len=%d, id=0x%02x) FAILED: %s", len(data), data[0] if data else -1, e)
                return False

    def get_feature(self, report_id: int, length: int) -> Optional[bytes]:
        """Read a HID feature report using HIDIOCGFEAT ioctl."""
        with self._lock:
            if self.fd is None:
                return None
            try:
                buf = bytearray(length)
                buf[0] = report_id
                fcntl.ioctl(self.fd, HIDIOCGFEAT(length), buf)
                res = bytes(buf)
                log.debug("get_feature(id=0x%02x, len=%d): %s", report_id, length, res.hex())
                return res
            except OSError as e:
                log.debug("get_feature(id=0x%02x, len=%d) FAILED: %s", report_id, length, e)
                return None

    def query_feature(self, target_report_id: int, length: int, profile_id: int = 0) -> Optional[bytes]:
        """
        Send the 0xA0 query command, wait for the mouse's acknowledgment (reply byte 1 == 1,
        exactly as the Windows HUD does), then read the requested feature report.
        """
        setup = build_query_packet(target_report_id, length, profile_id)
        for _ in range(5):
            if not self.send_feature(setup):
                time.sleep(0.1)
                continue
            for _ in range(4):
                time.sleep(0.1)
                ack = self.get_feature(0xA0, 8)
                if ack and len(ack) > 1 and ack[1] == 1:
                    return self.get_feature(target_report_id, length)
        return None

    # --- Safety helpers ---

    @staticmethod
    def _valid_reply(res: Optional[bytes], report_id: int, profile_id: Optional[int], min_len: int) -> bool:
        return (res is not None and len(res) >= min_len and res[0] == report_id
                and (profile_id is None or res[2] == profile_id))

    def failed_reads(self, profile_id: int) -> List[str]:
        """Names of the settings of this profile that could not be read (the GUI then shows defaults)."""
        return sorted(k for k in ("sensor", "light", "rate", "keys", "keys_fn")
                      if (k, profile_id) not in self._read_ok)

    def _can_write(self, kind: str, profile_id: int) -> bool:
        if not WRITES_ENABLED:
            self.last_error = "writes are disabled (set MMO7_ALLOW_WRITES=1 to enable them)"
            return False
        if kind not in ("profile", "macro") and (kind, profile_id) not in self._read_ok:
            self.last_error = f"{kind}: profile {profile_id} was not read successfully, refusing to write"
            return False
        return True

    def _write_verified(self, kind: str, profile_id: int, packet: bytes, report_id: int, cmp_end: int,
                        frames: Optional[List[bytes]] = None) -> bool:
        """Send a packet, read it back, and only report success if the mouse now holds the same data."""
        if not self._can_write(kind, profile_id):
            return False
        frames = frames or [packet]             # key tables go out as two chunks, everything else as one report
        for attempt in range(1, 4):
            sent = True
            for frame in frames:
                if not self.send_feature(frame):
                    sent = False
                    break
                time.sleep(0.4)
            if sent:
                back = self.query_feature(report_id, len(packet), profile_id)
                if back and len(back) >= cmp_end and back[2:cmp_end] == packet[2:cmp_end]:
                    log.debug("_write_verified(%s, id=%d) confirmed on attempt %d", kind, profile_id, attempt)
                    return True
                log.debug("_write_verified(%s, id=%d) mismatch on attempt %d: expected=%s got=%s",
                          kind, profile_id, attempt, packet[2:cmp_end].hex(),
                          back[2:cmp_end].hex() if back else None)
            time.sleep(0.4)
        ack = self.last_ack
        ack_txt = ""
        if ack and time.time() - ack[2] < 5:
            ack_txt = f" (last acknowledgment from the mouse: cmd {ack[0]:#04x}, status {ack[1]})"
        self.last_error = f"{kind}: the mouse did not report the new values after the write{ack_txt}"
        return False

    # --- High-level Mouse Controls ---

    def get_firmware_version(self) -> Optional[str]:
        """Firmware version from Report 0x0B (bytes 2 and 3 are hex digits: 01 22 -> "1.22")."""
        res = self.query_feature(REPORT_FW_VER, 8)
        if self._valid_reply(res, REPORT_FW_VER, None, 4):
            return parse_firmware(res)
        return None

    def _read_profile(self) -> Optional[int]:
        res = self.query_feature(REPORT_PROFILE, 10)
        if (res and len(res) >= 6 and res[0] == REPORT_PROFILE and 1 <= res[2] <= 5
                and res[3] == (~res[2]) & 0xFF):
            return res[2]
        return None

    def get_active_profile(self) -> int:
        """Query active onboard profile ID (1 to 5). Falls back to 1 (and sets last_error) if unreadable."""
        p = self._read_profile()
        if p is None:
            self.last_error = "could not read the active profile; assuming profile 1"
            return 1
        return p

    def set_active_profile(self, profile_id: int) -> bool:
        """Switch active profile on hardware (1 to 5) and confirm it by reading it back."""
        if not self._can_write("profile", profile_id):
            return False
        pkt = build_profile_packet(profile_id)
        for _ in range(3):
            if self.send_feature(pkt):
                time.sleep(0.4)
                if self._read_profile() == profile_id:
                    return True
            time.sleep(0.4)
        self.last_error = "profile switch was not confirmed by the mouse"
        return False

    def get_polling_rate(self, profile_id: int = 1) -> PollingRate:
        """Query polling rate for profile."""
        res = self.query_feature(REPORT_RATE, 9, profile_id)
        if self._valid_reply(res, REPORT_RATE, profile_id, 5) and res[4] == (~res[3]) & 0xFF:
            self._read_ok.add(("rate", profile_id))
            interval = res[3]
            if interval == 8:
                return PollingRate.HZ_125
            elif interval == 4:
                return PollingRate.HZ_250
            elif interval == 2:
                return PollingRate.HZ_500
        return PollingRate.HZ_1000

    def set_polling_rate(self, profile_id: int, rate: PollingRate) -> bool:
        """Set polling rate on hardware (verified by reading it back)."""
        pkt = build_rate_packet(profile_id, rate)
        return self._write_verified("rate", profile_id, pkt, REPORT_RATE, 5)

    def get_light_settings(self, profile_id: int = 1) -> Dict:
        """Query RGB lighting configuration."""
        res = self.query_feature(REPORT_LIGHT, 15, profile_id)
        if self._valid_reply(res, REPORT_LIGHT, profile_id, 13):
            self._read_ok.add(("light", profile_id))
            return {
                "mode": light_mode_from_byte(res[3]),   # factory profiles return 0x22; the HUD masks with 0x0F
                "speed": res[4],
                "brightness": res[5],
                "color": (res[6], res[7], res[8]),
                "sleep_time": res[9]
            }
        return {
            "mode": LightMode.Static,
            "speed": 3,
            "brightness": 8,
            "color": (255, 0, 0),
            "sleep_time": 2
        }

    def set_light_settings(self, profile_id: int, mode: LightMode, speed: int,
                           brightness: int, r: int, g: int, b: int, sleep_time: int = 2) -> bool:
        """Set RGB lighting on hardware (verified by reading it back)."""
        pkt = build_light_packet(profile_id, mode, speed, brightness, r, g, b, sleep_time)
        return self._write_verified("light", profile_id, pkt, REPORT_LIGHT, 13)

    def get_sensor_settings(self, profile_id: int = 1) -> Dict:
        """Query DPI stages and sensor parameters."""
        res = self.query_feature(REPORT_SENSOR, 56, profile_id)
        if self._valid_reply(res, REPORT_SENSOR, profile_id, 52):
            self._read_ok.add(("sensor", profile_id))
            colors8 = [(res[25 + i * 3], res[26 + i * 3], res[27 + i * 3]) for i in range(8)]
            # Fields the GUI does not edit are remembered so a later write keeps them unchanged.
            self._sensor_extra[profile_id] = (res[7], res[49], colors8)
            dpi_x = [res[8 + i] * 200 for i in range(4)]
            dpi_y = [res[16 + i] * 200 for i in range(4)]
            return {
                "lift": res[3],
                "angle_snap": res[4],
                "stage_mask": res[5],
                "dpi_stages": list(zip(dpi_x, dpi_y)),
                "current_stage": res[24],
                "stage_colors": colors8[:4],
                "center_offset": res[7],
                "indication_type": res[49],
            }
        # Fallback defaults (writing is refused for this profile until a read succeeds)
        return {
            "lift": 0,
            "angle_snap": 1,
            "stage_mask": 0x0F,
            "dpi_stages": [(800, 800), (1600, 1600), (3200, 3200), (6400, 6400)],
            "current_stage": 1,
            "stage_colors": [(255, 0, 0), (0, 128, 0), (0, 0, 255), (255, 255, 255)]
        }

    def set_sensor_settings(self, profile_id: int,
                            dpi_stages: List[Tuple[int, int]],
                            current_stage: int = 1,
                            stage_mask: int = 0x0F,
                            stage_colors: Optional[List[Tuple[int, int, int]]] = None,
                            lift: int = 0, angle_snap: int = 1,
                            center_offset: Optional[int] = None,
                            indication_type: Optional[int] = None) -> bool:
        """Set DPI stages and sensor settings (unedited fields are kept as last read; verified by readback)."""
        extra = self._sensor_extra.get(profile_id)
        if extra:
            center_offset = extra[0] if center_offset is None else center_offset
            indication_type = extra[1] if indication_type is None else indication_type
            colors8 = list(extra[2])
            if stage_colors:
                colors8[:len(stage_colors)] = list(stage_colors)[:8]
            stage_colors = colors8
        pkt = build_sensor_packet(profile_id, dpi_stages, current_stage, stage_mask, stage_colors,
                                  lift, angle_snap,
                                  2 if center_offset is None else center_offset,
                                  1 if indication_type is None else indication_type)
        return self._write_verified("sensor", profile_id, pkt, REPORT_SENSOR, 52)

    def get_keys(self, profile_id: int = 1, is_fn: bool = False) -> Dict[str, ButtonSetting]:
        """Query button assignments for Normal (0x08) or Fn (0x18) layer."""
        report_id = REPORT_KEYS_FN if is_fn else REPORT_KEYS_NORMAL
        res = self.query_feature(report_id, 95, profile_id)
        buttons = {}
        if self._valid_reply(res, report_id, profile_id, 93):
            self._read_ok.add(("keys_fn" if is_fn else "keys", profile_id))
            slot_map = {slot: name for name, slot, desc in BUTTON_MAP_ORDER}
            for slot, name in slot_map.items():
                idx = 3 + slot * 3
                code = res[idx]
                # Keep unknown function codes as raw numbers instead of silently turning them into Click.
                func = ButtonFunction(code) if code in ButtonFunction._value2member_map_ else code
                buttons[name] = ButtonSetting(func, res[idx + 1], res[idx + 2])
        return buttons

    def set_keys(self, profile_id: int, buttons: Dict[str, ButtonSetting], is_fn: bool = False) -> bool:
        """Save button assignments to hardware memory (verified by reading them back)."""
        report_id = REPORT_KEYS_FN if is_fn else REPORT_KEYS_NORMAL
        pkt = build_keys_packet(report_id, profile_id, buttons)          # what the mouse should read back
        frames = build_keys_chunks(report_id, profile_id, buttons)       # what actually has to be sent
        return self._write_verified("keys_fn" if is_fn else "keys", profile_id, pkt, report_id, 95, frames)

    def get_macro(self, macro_index: int) -> Optional[MacroDefinition]:
        """Query an onboard macro slot (1..255) from Report 0x09 (131 bytes)."""
        res = self.query_feature(REPORT_MACRO, MACRO_REPORT_LEN, macro_index)
        if self._valid_reply(res, REPORT_MACRO, macro_index, MACRO_REPORT_LEN):
            return parse_macro_packet(res)
        return None

    def set_macro(self, macro: MacroDefinition) -> bool:
        """Write an onboard macro slot (Report 0x09, three 64-byte chunks) and verify by readback."""
        pkt = build_macro_packet(macro)
        frames = build_macro_chunks(macro)
        # Compare bytes 2..129 (Index, LoopType, Reserve, LoopCount, MacroName[20], KeyMacroNumber, KeyInfo[50]);
        # the firmware returns the 16-bit checksum at bytes 129..131 in little-endian order on readback.
        return self._write_verified("macro", macro.index, pkt, REPORT_MACRO, 129, frames)

    # --- Background Event Monitor ---

    def start_monitor(self):
        """Starts a background thread to listen for input reports (battery, DPI, profile changes)."""
        if self._running or self.fd is None:
            return
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitor(self):
        self._running = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=0.5)
            self._monitor_thread = None

    def pause_monitor(self):
        """Pause the monitor thread's reading while bulk configuration I/O runs (safe to nest)."""
        with self._lock:
            self._monitor_pause_count += 1

    def resume_monitor(self):
        """Resume the monitor thread after bulk I/O operations."""
        with self._lock:
            self._monitor_pause_count = max(0, self._monitor_pause_count - 1)
            if self._monitor_pause_count == 0:
                self._monitor_pause_cond.notify_all()

    def _monitor_loop(self):
        while self._running and self.fd is not None:
            try:
                if self._monitor_pause_count > 0:
                    time.sleep(0.05)            # paused: leave input reports queued in the kernel
                    continue
                r, _, _ = select.select([self.fd], [], [], 0.2)
                if not r:
                    continue
                data = os.read(self.fd, 64)
                if not data:
                    continue

                # Battery Level Report: 03 10 40 01 XX (XX * 10%); byte 3 is not interpreted
                if len(data) >= 5 and data[0] == 0x03 and data[1:3] == bytes([0x10, 0x40]):
                    battery_pct = min(100, data[4] * 10)
                    if self.on_battery_changed:
                        self.on_battery_changed(battery_pct)

                # Profile Change Report: 03 00 80 NN 00 (NN is 0-indexed profile)
                elif len(data) >= 5 and data[0] == 0x03 and data[1:3] == bytes([0x00, 0x80]):
                    profile_idx = data[3] + 1
                    if self.on_profile_changed:
                        self.on_profile_changed(profile_idx)

                # DPI Level Change Report: 03 00 10 LL 00 (LL is 1-indexed stage)
                elif len(data) >= 5 and data[0] == 0x03 and data[1:3] == bytes([0x00, 0x10]):
                    dpi_stage = data[3]
                    if self.on_dpi_stage_changed:
                        self.on_dpi_stage_changed(dpi_stage)

                # Write acknowledgment: 03 CC 50 SS 00 (SS == 0 means the mouse accepted the write).
                # Read from the Windows driver DLL; the HUD resends up to 10 times until it sees SS == 0.
                elif len(data) >= 5 and data[0] == 0x03 and data[2] == 0x50:
                    self.last_ack = (data[1], data[3], time.time())

                # Mode Shift Toggle Event: 02 00 00
                elif len(data) >= 3 and data[0] == 0x02 and data[1:3] == bytes([0x00, 0x00]):
                    if self.on_mode_shift_toggled:
                        self.on_mode_shift_toggled()

            except BlockingIOError:
                continue
            except (OSError, ValueError):
                break
