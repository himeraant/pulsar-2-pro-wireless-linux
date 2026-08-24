"""Sinowealth 258a:002f HID feature-report protocol for the HATOR Pulsar 2 Pro.

Decoded from USBPcap captures (see docs/sinowealth-protocol.md). The mouse is
configured through HID feature reports sent over the receiver's hidraw node:

  report 0x05 (8 bytes)  - small commands / battery poll
  report 0x08 (520 bytes)- full configuration blob (DPI, polling, buttons)

Pure module (no USB/hidraw/fcntl): it operates on an injected "device" object
exposing feature_out(report_id, data) and feature_in(report_id, size). Only
`os` is imported (to locate the bundled config template).
"""
from __future__ import annotations

import os

REPORT_CMD = 0x05
REPORT_CONFIG = 0x08
CONFIG_SIZE = 520  # total feature report 0x08 size (report id byte + 519 data)

CMD_ENTER = 0x80
CMD_PREP = 0x21
CMD_BUTTONS = 0x22
CMD_BATTERY = 0x90

# Polling rate byte (config blob offset 10) -> Hz
POLLING_CODES = {1: 125, 2: 250, 3: 500, 4: 1000}
POLLING_OPTIONS = (125, 250, 500, 1000)
POLLING_TO_CODE = {v: k for k, v in POLLING_CODES.items()}

# DPI slot byte offsets in the config blob (each 2 bytes, little-endian).
# Offset 11 is a fixed 0x27; the 7 DPI slots start at offset 13.
DPI_OFFSETS = [13, 15, 17, 19, 21, 23, 25]
DPI_MIN = 100
DPI_MAX = 16000

BUTTON_OFFSET = 27  # command 0x22 blob, per-button entries start here (see notes)

DEFAULT_CPI = [400, 800, 1200, 1600, 2400, 3200, 6400]  # 7 slots
DEFAULT_POLLING_HZ = 1000


def default_config() -> dict:
    return {
        "polling_rate": DEFAULT_POLLING_HZ,
        "cpi": list(DEFAULT_CPI),
        "button_map": ["left", "right", "middle", "backward", "forward", "dpi"],
    }


def read_battery(dev) -> int | None:
    """Return battery percentage (0-100) via feature report 0x05, cmd 0x90."""
    dev.feature_out(REPORT_CMD, bytes([CMD_BATTERY]) + bytes(6))
    resp = dev.feature_in(REPORT_CMD, 8)  # 05 90 11 XX 00 00 00 00
    if len(resp) >= 4 and resp[1] == CMD_BATTERY:
        return resp[3]
    return None


def _preamble(dev) -> None:
    """The command preamble observed before config reads/writes."""
    dev.feature_out(REPORT_CMD, bytes([CMD_ENTER]) + bytes(6))   # 05 80 ...
    dev.feature_in(REPORT_CMD, 8)                                # ack
    dev.feature_out(REPORT_CMD, bytes([CMD_PREP]) + bytes(6))    # 05 21 ...


def read_config(dev) -> bytes:
    """Run the preamble and read the 520-byte config blob (report 0x08)."""
    _preamble(dev)
    blob = dev.feature_in(REPORT_CONFIG, CONFIG_SIZE)  # report id + 520
    # blob = [0x08, 0x21, 0x00, 0x92, 0x00...] -> return data after report id + cmd
    return blob


def _blob_data(blob: bytes) -> bytes:
    """Return the usable config data (strip report id + '21 00 92 00 00 00 00')."""
    # blob[0]=0x08 (report id), blob[1]=0x21 (cmd); data meaningfully starts at 8.
    return blob


def get_polling_hz(blob: bytes) -> int | None:
    code = blob[10] if len(blob) > 10 else None
    return POLLING_CODES.get(code)


def get_dpi_slots(blob: bytes) -> list[int]:
    slots = []
    for off in DPI_OFFSETS:
        reg = int.from_bytes(blob[off : off + 2], "little")
        slots.append((reg + 1) * 100)
    return slots


def build_config(blob: bytes, *, polling_hz=None, dpi_slots=None) -> bytes:
    """Return a modified copy of the config blob with polling/DPI changed."""
    out = bytearray(blob)
    if polling_hz is not None:
        out[10] = POLLING_TO_CODE[polling_hz]
    if dpi_slots is not None:
        for off, cpi in zip(DPI_OFFSETS, dpi_slots):
            cpi = max(DPI_MIN, min(DPI_MAX, cpi))
            reg = (cpi // 100) - 1
            out[off : off + 2] = reg.to_bytes(2, "little")
    return bytes(out)


CONFIG_TEMPLATE = os.path.join(os.path.dirname(__file__), "config_template.bin")


def _load_config_template() -> bytearray:
    with open(CONFIG_TEMPLATE, "rb") as f:
        return bytearray(f.read())


def apply_config(dev, *, polling_hz=None, dpi_slots=None) -> bytes:
    """Write DPI/polling to the receiver's config (report 0x08, 520 bytes).

    The device only accepts a full 520-byte write with a longer timeout. The
    config data (polling byte 10, DPI slots 13-25) lives in the first 154 bytes;
    the trailing bytes (button map) come from the bundled template (captured
    from this device, see config_template.bin).
    """
    _preamble(dev)
    blob = _load_config_template()
    if polling_hz is not None:
        blob[10] = POLLING_TO_CODE[polling_hz]
    if dpi_slots is not None:
        for off, cpi in zip(DPI_OFFSETS, dpi_slots):
            cpi = max(DPI_MIN, min(DPI_MAX, cpi))
            reg = (cpi // 100) - 1
            blob[off : off + 2] = reg.to_bytes(2, "little")
    dev.feature_out(REPORT_CONFIG, blob[1:])
    return bytes(blob)
