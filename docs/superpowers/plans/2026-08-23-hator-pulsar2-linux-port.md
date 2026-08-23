# HATOR Pulsar 2 Pro Linux Configurator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a native Linux app (CLI + GTK GUI) to configure the HATOR Pulsar 2 Pro wireless mouse: see battery, bind all buttons to arbitrary actions, change polling rate and DPI.

**Architecture:** A layered Python project. A pure, testable protocol engine (`engine/`) encodes the reverse-engineered HID packets and performs USB writes via pyusb. A thin CLI and a thin GTK GUI consume the same engine. Host-side arbitrary button binding is generated for `input-remapper`; on-device writes expose hidden buttons (e.g. the DPI button) so the host can see them.

**Tech Stack:** Python 3.8+, `pyusb` + `libusb-1.0`, GTK4 via `PyGObject` (GUI), `pytest` (tests), `input-remapper` (host-side binding, runtime dep).

**Spec:** `docs/superpowers/specs/2026-08-23-hator-pulsar2-linux-port-design.md`

## Global Constraints

- Device VID/PID: `0x04D9:0xA09F` (Holtek). Verify with `lsusb | grep 04d9`.
- DPI values are multiples of 50, max 12800. Register encoding: `reg = (cpi // 50) - 1`. Decode: `cpi = (reg + 1) * 50`.
- Polling rate: only `125`, `250`, `500`, `1000` Hz.
- On-device button map: 8 slots × 4 bytes. Slots 1-6 = Left, Right, Middle, Forward, Backward, DPI. Slots 7-8 are fixed/unused and must be written as `07000100 07000200`.
- The device is write-only over USB: configuration cannot be read back. The local state file is the source of truth for `--get`.
- Battery is two-tier: Tier 1 reads the kernel sysfs `power_supply` node (no reverse-engineering); Tier 2 (vendor read channel) is a stub until the VM capture confirms the channel.
- Attribution: upstream `hampta/luom-g10-config` has no explicit license. Reimplement protocol logic (factual USB data) rather than wholesale copying, and credit upstream in the README.
- Language/binding conventions: engine functions are pure and take/return plain Python types (ints, lists, hex strings, tuples); no pyusb imports inside `engine/protocol.py` or `engine/state.py`.

---

### Task 1: Protocol engine — packet encoding

The heart of the project. A pure module that turns a config dict into an ordered list of USB operations (control `SET_REPORT` packets and EP3 OUT data bursts), plus validation helpers. No pyusb here.

**Files:**
- Create: `engine/__init__.py`
- Create: `engine/protocol.py`
- Test: `tests/test_protocol.py`

**Interfaces:**
- Produces (used by Task 2 device.py, Task 5 engine, Task 7 cli, Task 9 gui):
  - `VID = 0x04D9`, `PID = 0xA09F`
  - `BUTTON_ACTIONS: dict[str, str]` → hex 4-byte action codes.
  - `POLLING_OPTIONS = (125, 250, 500, 1000)`
  - `validate_dpi(cpi: int) -> int` — validate/round a CPI value (multiple of 50, 0 <= cpi <= 12800). Raise `ValueError` on invalid.
  - `dpi_to_register(cpi: int) -> int` — `(cpi // 50) - 1` clamped to `[0, 255]`.
  - `register_to_dpi(reg: int) -> int` — `(reg + 1) * 50`.
  - `build_apply_sequence(config: dict) -> list[tuple[str, str]]` — returns `[("ctrl", hexstr) | ("out", hexstr), ...]` in device write order. Raises `ValueError` on invalid config.
  - `default_config() -> dict` — factory defaults (see below).
  - `MS_MAP = [1,2,3,4,5,6,7,8,9,10,20,100]` — key-response index → ms.

- Consumes: nothing.

- [ ] **Step 1: Write the failing tests**

Create `engine/__init__.py` (empty package marker) and `tests/test_protocol.py`:

```python
import pytest
from engine import protocol as p


def test_dpi_register_roundtrip():
    assert p.dpi_to_register(400) == 7
    assert p.register_to_dpi(7) == 400


def test_dpi_validation():
    assert p.validate_dpi(400) == 400
    assert p.validate_dpi(50) == 50
    with pytest.raises(ValueError):
        p.validate_dpi(45)          # not a multiple of 50
    with pytest.raises(ValueError):
        p.validate_dpi(13000)       # above max


def test_default_config_has_6_cpi():
    cfg = p.default_config()
    assert len(cfg["cpi"]) == 6
    assert cfg["polling_rate"] == 1000
    assert cfg["button_map"] == ["left", "right", "middle", "forward", "backward", "dpi"]


def test_build_sequence_starts_with_fixed_ctrl():
    seq = p.build_apply_sequence(p.default_config())
    assert seq[0][0] == "ctrl"
    assert seq[0][1] == "2727d5fff4e57676"


def test_build_sequence_is_apply_snapshot():
    # Sanity: 24 operations total (12 ctrl + 12 out), mirroring the decoded capture.
    seq = p.build_apply_sequence(p.default_config())
    assert len(seq) == 24


def test_build_sequence_encodes_button_map():
    seq = p.build_apply_sequence(p.default_config())
    out_ops = [h for kind, h in seq if kind == "out"]
    # Button map packet is the 4th out op (index 3). Slots 7-8 fixed.
    btn = out_ops[3]
    assert btn.endswith("0700010007000200")


def test_build_sequence_polling_encoding():
    cfg = p.default_config()
    cfg["polling_rate"] = 500
    seq = p.build_apply_sequence(cfg)
    # 4th ctrl op (index 3) is the polling packet.
    ctrls = [h for kind, h in seq if kind == "ctrl"]
    assert ctrls[3] == "272bd5ff00d57676"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError` (module/functions missing).

- [ ] **Step 3: Implement `engine/protocol.py`**

```python
"""Reverse-engineered HID protocol for the HATOR Pulsar 2 Pro (Holtek 04D9:A09F).

Reimplemented from USB packet captures decoded in hampta/luom-g10-config.
Pure module: no pyusb imports here.
"""
from __future__ import annotations

VID = 0x04D9
PID = 0xA09F

MS_MAP = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 100]

POLLING_OPTIONS = (125, 250, 500, 1000)

DPI_MIN = 0
DPI_MAX = 12800

BUTTON_ACTIONS = {
    "left": "0100f000",
    "right": "0100f100",
    "middle": "0100f200",
    "backward": "0100f300",
    "forward": "0100f400",
    "dpi": "07000100",
    "disabled": "00000000",
}

DEFAULT_BUTTON_MAP = ["left", "right", "middle", "forward", "backward", "dpi"]
DEFAULT_CPI = [300, 500, 900, 1400, 2400, 4800]

POLLING_PACKETS = {
    125: "272b85ff30d57676",
    250: "272ba5ffd0d57676",
    500: "272bd5ff00d57676",
    1000: "272bddffe8d57676",
}

DPI_SLOT_PACKETS = {
    0: "272b6dffe8257676",
    1: "272b65ff00257676",
    2: "272b7dfff8257676",
    3: "272b75ffd0257676",
    4: "272b4dffc8257676",
    5: "272b45ffe0257676",
    6: "272b5dffd8257676",
}

DPI_COUNT_PACKETS = {
    1: "272b1dffe85576b6",
    2: "272b15ff005576b6",
    3: "272bedfff85576b6",
    4: "272be5ffd05576b6",
    5: "272bfdffc85576b6",
    6: "272bf5ffe05576b6",
    7: "272acdffd85576b6",
}

# light_mode: (ctrl5, ctrl6)
LIGHT_MODES = {
    "standard": ("272b85049842556e", "272afdffe83577f6"),
    "off": ("272b6dfff03d7676", "272afdffe83577f6"),
    "breathing": ("272b85049842556e", "272b2dff0035668e"),
    "neon": ("272b85049842556e", "272dcdffe83567f6"),
    "wave": ("272b85049842556e", "272dd5fff834f68e"),
    "key-reaction": ("272b85049842556e", "272dadffc83567f6"),
    "trailing": ("272b85049842556e", "272dadffd034f68e"),
    "drag": ("272b85049842556e", "272b35ffe0356686"),
    "slide": ("272b85049842556e", "272b0dffd8356686"),
    "yo-yo": ("272b85049842556e", "272d0dff2835e7f6"),
    "marbles": ("272b85049842556e", "272dbdff30357ff6"),
    "flying-star": ("272b85049842556e", "272d8dff40357ff6"),
}

STANDARD_COLOR_CTRL6 = "272b65ffe8357d6e"
SINGLE_COLOR = {
    "white": "272b85049842556e",
    "red": "272d4d04a03c6f8e",
    "green": "272bc5ff703d8596",
    "blue": "27293dffe843b67e",
}

# key_response index -> (b1, b2, b6, b7) for ctrl#13
KR_TABLE = [
    (0x2B, 0x8D, 0x76, 0x86),  # 0 = 1ms
    (0x2B, 0x9D, 0x76, 0x96),  # 1 = 2ms
    (0x2B, 0x95, 0x76, 0x9E),  # 2 = 3ms
    (0x2B, 0x6D, 0x76, 0xA6),  # 3 = 4ms
    (0x2B, 0x65, 0x76, 0xAE),  # 4 = 5ms
    (0x2B, 0x7D, 0x76, 0xB6),  # 5 = 6ms
    (0x2B, 0x4D, 0x76, 0xC6),  # 6 = 7ms
    (0x2B, 0x15, 0x76, 0x1E),  # 7 = 8ms
    (0x2A, 0xC5, 0x76, 0x4E),  # 8 = 9ms
    (0x2A, 0x95, 0x77, 0x9E),  # 9 = 10ms
    (0x2A, 0x55, 0x77, 0xDE),  # 10 = 20ms
    (0x2B, 0xB5, 0x76, 0x7E),  # 11 = 100ms
]

# Fixed color data packets (multicolor rainbow palette)
COLOR_PACKET_1 = ("ff000000ff000000ffffff00ff00ff00ffffff8000ffffff"
                  "0000000000000000")
COLOR_PACKET_2 = "00ff000000ffff0000ffff0000ffffff00ffffffffffffff0000000000000000"

FIXED_CTRLS = [
    "2727d5fff4e57676",      # ctrl#0
    "272bd5ffe8ed7676",      # ctrl#2
    "272a8dfff05d7636",
    "272a85ffe85d7636",
    "272d55ffe86d7876",
    "272d2dff006d7876",
    "272bf5fff85d76d6",
    "272c6d024022ccd6",
    "272bb5fff0057676",
]


def default_config() -> dict:
    return {
        "active_slot": 0,
        "cpi": list(DEFAULT_CPI),
        "button_map": list(DEFAULT_BUTTON_MAP),
        "dpi_count": 7,
        "key_response": 11,   # index -> 100ms
        "polling_rate": 1000,
        "lift_off": 2,
        "light_mode": "standard",
        "standard_color": None,
        "custom_color": None,
    }


def validate_dpi(cpi: int) -> int:
    if cpi % 50 != 0:
        raise ValueError(f"DPI must be a multiple of 50, got {cpi}")
    if cpi < DPI_MIN or cpi > DPI_MAX:
        raise ValueError(f"DPI out of range 0-{DPI_MAX}, got {cpi}")
    return cpi


def dpi_to_register(cpi: int) -> int:
    return max(0, min(255, (validate_dpi(cpi) // 50) - 1))


def register_to_dpi(reg: int) -> int:
    return (reg + 1) * 50


def _build_color_packet_1(custom_color: tuple | None) -> str:
    data = bytearray(bytes.fromhex(COLOR_PACKET_1))
    if custom_color is not None:
        r, g, b = custom_color
        for i in range(9):
            data[i * 3] = r
            data[i * 3 + 1] = g
            data[i * 3 + 2] = b
    return data.hex()


def _ctrl13_hex(key_response: int, lift_off: int) -> str:
    kr = max(0, min(11, key_response))
    b1, b2, b6, b7 = KR_TABLE[kr]
    b4 = 0x00
    if lift_off == 1:
        b2 = (b2 + 0x08) & 0xFF
        b4 = 0xE8
    return bytes([0x27, b1, b2, 0xFF, b4, 0xFD, b6, b7]).hex()


def build_apply_sequence(config: dict) -> list[tuple[str, str]]:
    """Return [("ctrl"|"out", hexstr), ...] in device write order."""
    cfg = default_config()
    cfg.update(config)

    if cfg["polling_rate"] not in POLLING_PACKETS:
        raise ValueError(f"Unsupported polling rate {cfg['polling_rate']}")

    for action in cfg["button_map"]:
        if action not in BUTTON_ACTIONS:
            raise ValueError(f"Unknown button action '{action}'")

    for cpi in cfg["cpi"]:
        validate_dpi(cpi)

    # Light ctrl5/ctrl6 selection
    ctrl5_pkt, ctrl6_pkt = LIGHT_MODES.get(cfg["light_mode"], LIGHT_MODES["standard"])
    custom = cfg.get("custom_color")
    standard_color = cfg.get("standard_color")
    if cfg["light_mode"] in ("standard", None):
        if custom is not None:
            ctrl5_pkt = LIGHT_MODES["standard"][0]
            ctrl6_pkt = STANDARD_COLOR_CTRL6
        elif standard_color:
            sc = standard_color.lower()
            if sc in SINGLE_COLOR:
                ctrl5_pkt = SINGLE_COLOR[sc]
                ctrl6_pkt = STANDARD_COLOR_CTRL6
            elif sc in ("multicolor", "rainbow"):
                pass
    elif cfg["light_mode"] == "off":
        pass

    # DPI registers packet
    dpi_regs = bytearray(32)
    dpi_regs[6] = 0xBD
    dpi_regs[7] = 0x5F
    cpi = cfg["cpi"]
    for i in range(min(len(cpi), 6)):
        dpi_regs[i] = dpi_to_register(cpi[i])
    for i in range(len(cpi), 6):
        dpi_regs[i] = dpi_regs[len(cpi) - 1] if len(cpi) > 0 else 0

    # Button map: 6 configured slots + 2 fixed unused slots
    btn_hex = ""
    for i in range(6):
        action = cfg["button_map"][i] if i < len(cfg["button_map"]) else DEFAULT_BUTTON_MAP[i]
        btn_hex += BUTTON_ACTIONS[action]
    btn_hex += "0700010007000200"

    slot = max(0, min(6, cfg["active_slot"]))
    count = max(1, min(7, cfg["dpi_count"]))

    seq: list[tuple[str, str]] = []
    # ctrl#0 fixed
    seq.append(("ctrl", FIXED_CTRLS[0]))
    # ctrl#1 LOD
    if cfg["lift_off"] == 3:
        seq.append(("ctrl", "252db5fff8eae6ee"))
    else:
        seq.append(("ctrl", "252d75fff8ea26ee"))
    # ctrl#2 fixed
    seq.append(("ctrl", FIXED_CTRLS[1]))
    # ctrl#3 polling
    seq.append(("ctrl", POLLING_PACKETS[cfg["polling_rate"]]))
    # ctrl#4 active DPI slot
    seq.append(("ctrl", DPI_SLOT_PACKETS[slot]))
    # ctrl#5 light
    seq.append(("ctrl", ctrl5_pkt))
    # ctrl#6 light params
    seq.append(("ctrl", ctrl6_pkt))
    # fixed
    seq.append(("ctrl", FIXED_CTRLS[2]))
    # out p1 color
    seq.append(("out", _build_color_packet_1(custom)))
    # fixed
    seq.append(("ctrl", FIXED_CTRLS[3]))
    # out p2 color
    seq.append(("out", COLOR_PACKET_2))
    # ctrl#9 DPI count
    seq.append(("ctrl", DPI_COUNT_PACKETS[count]))
    # out DPI registers
    seq.append(("out", dpi_regs.hex()))
    # fixed
    seq.append(("ctrl", FIXED_CTRLS[4]))
    # out button map
    seq.append(("out", btn_hex))
    # out timing/debounce
    seq.append(("out", "0b0000000d000000000000000000000000000000000000000400010004000200"))
    # fixed
    seq.append(("ctrl", FIXED_CTRLS[5]))
    # out reserved
    seq.append(("out", "0" * 64))
    # out scroll
    seq.append(("out", "0b0000000d000000000000000000000000000000000000000000000000000000"))
    # fixed
    seq.append(("ctrl", FIXED_CTRLS[6]))
    # out commit
    seq.append(("out", "ff" + "0" * 62))
    # ctrl#13 key response + LOD
    seq.append(("ctrl", _ctrl13_hex(cfg["key_response"], cfg["lift_off"])))
    # fixed
    seq.append(("ctrl", FIXED_CTRLS[7]))
    seq.append(("ctrl", FIXED_CTRLS[8]))
    return seq
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_protocol.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/__init__.py engine/protocol.py tests/test_protocol.py
git commit -m "feat: protocol engine packet encoding for HATOR Pulsar 2 Pro"
```

---

### Task 2: Device layer — USB access via pyusb

Wraps pyusb to find the mouse, detach kernel drivers, and execute the op sequence from Task 1. Testable by injecting a fake USB device.

**Files:**
- Create: `engine/device.py`
- Test: `tests/test_device.py`

**Interfaces:**
- Consumes: `engine.protocol.VID`, `PID`, `build_apply_sequence`.
- Produces (used by Task 5 engine, Task 7 cli, Task 9 gui):
  - `class HatorDevice`:
    - `__init__(self, dev=None)` — accepts an injected pyusb-like device (for tests), else finds `VID:PID`.
    - `apply_sequence(sequence: list[tuple[str, str]]) -> None` — for `("ctrl", hex)` call `ctrl_transfer(0x21, 0x09, 0x0300, 2, bytes)`; for `("out", hex)` call `write(0x03, bytes)`; sleep 10ms between ops.
    - `close()` — dispose resources and re-attach detached kernel drivers.
  - `class DeviceNotFoundError(Exception)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_device.py`:

```python
import pytest
from engine import protocol as p
from engine.device import HatorDevice, DeviceNotFoundError


class FakeUSB:
    def __init__(self):
        self.ctrl_calls = []
        self.out_calls = []
        self.detached = []
        self.closed = False

    def is_kernel_driver_active(self, i):
        return i == 0

    def detach_kernel_driver(self, i):
        self.detached.append(i)

    def attach_kernel_driver(self, i):
        self.detached.remove(i)

    def set_configuration(self):
        pass

    def ctrl_transfer(self, bm, b, v, idx, data):
        self.ctrl_calls.append(data)

    def write(self, endpoint, data, timeout=None):
        self.out_calls.append(bytes(data))

    def dispose_resources(self):
        self.closed = True


def test_injected_device_executes_sequence():
    fake = FakeUSB()
    dev = HatorDevice(dev=fake)
    seq = p.build_apply_sequence(p.default_config())
    dev.apply_sequence(seq)
    # 16 ctrl ops -> 16 ctrl_transfer calls; 8 out ops -> 8 writes
    assert len(fake.ctrl_calls) == 16
    assert len(fake.out_calls) == 8
    # Each ctrl payload is exactly the decoded hex
    first_ctrl_hex = "2727d5fff4e57676"
    assert fake.ctrl_calls[0].hex() == first_ctrl_hex
    # Driver 0 was detached then re-attached on close
    dev.close()
    assert fake.detached == []


def test_device_not_found_raises():
    with pytest.raises(DeviceNotFoundError):
        HatorDevice(dev=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_device.py -v`
Expected: FAIL with `ModuleNotFoundError: engine.device`.

- [ ] **Step 3: Implement `engine/device.py`**

```python
"""USB device access for the HATOR Pulsar 2 Pro via pyusb."""
from __future__ import annotations

import time

import usb.core
import usb.util

from .protocol import VID, PID

CTRL_OP = "ctrl"
OUT_OP = "out"
EP3_OUT = 0x03
CTRL_REQ = 0x21          # class request, host-to-device
SET_REPORT = 0x09
VALUE_SET_REPORT = 0x0300
INTERFACE = 2
SLEEP_S = 0.01


class DeviceNotFoundError(Exception):
    pass


class HatorDevice:
    def __init__(self, dev=None):
        self.dev = dev or usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            raise DeviceNotFoundError(
                f"HATOR Pulsar 2 Pro not found (expect {VID:04x}:{PID:04x}). "
                "Is it plugged in? Check `lsusb | grep 04d9`."
            )
        self._detached = []
        for i in range(3):
            if self.dev.is_kernel_driver_active(i):
                try:
                    self.dev.detach_kernel_driver(i)
                    self._detached.append(i)
                except usb.core.USBError:
                    pass
        self.dev.set_configuration()

    def apply_sequence(self, sequence):
        for kind, hexstr in sequence:
            data = bytes.fromhex(hexstr)
            if kind == CTRL_OP:
                self.dev.ctrl_transfer(
                    CTRL_REQ, SET_REPORT, VALUE_SET_REPORT, INTERFACE, data
                )
            elif kind == OUT_OP:
                self.dev.write(EP3_OUT, data, timeout=1000)
            else:
                raise ValueError(f"Unknown op kind: {kind}")
            time.sleep(SLEEP_S)

    def close(self):
        if self.dev is None:
            return
        usb.util.dispose_resources(self.dev)
        for i in self._detached:
            try:
                self.dev.attach_kernel_driver(i)
            except usb.core.USBError:
                pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_device.py -v`
Expected: PASS (2 tests). Note: `HatorDevice(dev=None)` must reach the `DeviceNotFoundError` branch before touching the real USB bus — the test relies on the mouse not being present (it is in the VM). If a real mouse is attached to this host, this test may find it; keep it isolated.

- [ ] **Step 5: Commit**

```bash
git add engine/device.py tests/test_device.py
git commit -m "feat: pyusb device layer for HATOR Pulsar 2 Pro"
```

---

### Task 3: State persistence

JSON state file. The device is write-only, so this file is the source of truth for what was applied.

**Files:**
- Create: `engine/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `engine.protocol.default_config`.
- Produces (used by Task 5 engine, Task 7 cli, Task 9 gui):
  - `default_state_path() -> str` — `~/.config/hator/state.json`.
  - `load_state(path=None) -> dict | None` — returns saved dict or `None` if missing/invalid.
  - `save_state(config: dict, path=None) -> None` — writes config to path (create parent dir).

- [ ] **Step 1: Write the failing test**

Create `tests/test_state.py`:

```python
import json
from engine import protocol as p
from engine.state import load_state, save_state, default_state_path


def test_save_load_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    cfg = p.default_config()
    cfg["polling_rate"] = 500
    cfg["cpi"] = [400, 800, 1600]
    save_state(cfg, path)
    loaded = load_state(path)
    assert loaded["polling_rate"] == 500
    assert loaded["cpi"] == [400, 800, 1600]


def test_load_missing_returns_none(tmp_path):
    path = str(tmp_path / "nope.json")
    assert load_state(path) is None


def test_default_state_path_under_config():
    assert "hator" in default_state_path()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: engine.state`.

- [ ] **Step 3: Implement `engine/state.py`**

```python
"""Local JSON state persistence (device is write-only; file is the truth)."""
from __future__ import annotations

import json
import os


def default_state_path() -> str:
    return os.path.expanduser("~/.config/hator/state.json")


def load_state(path=None):
    path = path or default_state_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def save_state(config: dict, path=None) -> None:
    path = path or default_state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_state.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/state.py tests/test_state.py
git commit -m "feat: JSON state persistence for HATOR configurator"
```

---

### Task 4: Battery reader (Tier 1 sysfs + Tier 2 stub)

Reads the kernel-exposed battery node. Tier 2 (vendor read channel) is a stub until the VM capture confirms it.

**Files:**
- Create: `engine/battery.py`
- Test: `tests/test_battery.py`

**Interfaces:**
- Consumes: nothing (pure filesystem reads).
- Produces (used by Task 5 engine, Task 7 cli, Task 9 gui):
  - `read_battery(power_supply_dir: str | None = None) -> dict | None`
    - Scans `power_supply_dir` (default `/sys/class/power_supply`) for a node whose name contains `battery` (e.g. `hid-...-battery`).
    - Reads `capacity` and `status` files.
    - Returns `{"level": int|None, "status": str|None}` on success, else `None` if no battery node found.
  - `battery_unavailable() -> dict` — returns `{"level": None, "status": "unavailable", "tier": 2}` for the Tier 2 fallback stub.

- [ ] **Step 1: Write the failing test**

Create `tests/test_battery.py`:

```python
from engine.battery import read_battery, battery_unavailable


def test_reads_sysfs_capacity(tmp_path):
    node = tmp_path / "hid-abc-battery"
    node.mkdir()
    (node / "capacity").write_text("87\n")
    (node / "status").write_text("Discharging\n")
    result = read_battery(str(tmp_path))
    assert result == {"level": 87, "status": "Discharging"}


def test_no_battery_node_returns_none(tmp_path):
    # Only ACAD/BATT (laptop battery) present, no hid battery node.
    (tmp_path / "ACAD").mkdir()
    assert read_battery(str(tmp_path)) is None


def test_tier2_stub():
    assert battery_unavailable()["status"] == "unavailable"
    assert battery_unavailable()["tier"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_battery.py -v`
Expected: FAIL with `ModuleNotFoundError: engine.battery`.

- [ ] **Step 3: Implement `engine/battery.py`**

```python
"""Battery level reader.

Tier 1: kernel-exposed HID power_supply node (no reverse-engineering).
Tier 2: vendor read channel, stubbed until the VM capture confirms it.
"""
from __future__ import annotations

import os


def read_battery(power_supply_dir: str | None = None) -> dict | None:
    power_supply_dir = power_supply_dir or "/sys/class/power_supply"
    if not os.path.isdir(power_supply_dir):
        return None
    for name in os.listdir(power_supply_dir):
        if "battery" not in name:
            continue
        node = os.path.join(power_supply_dir, name)
        level = _read_int(os.path.join(node, "capacity"))
        status = _read_text(os.path.join(node, "status"))
        if level is None and status is None:
            continue
        return {"level": level, "status": status}
    return None


def battery_unavailable() -> dict:
    return {"level": None, "status": "unavailable", "tier": 2}


def _read_int(path: str) -> int | None:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _read_text(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_battery.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/battery.py tests/test_battery.py
git commit -m "feat: battery reader with Tier 1 sysfs and Tier 2 stub"
```

---

### Task 5: Engine orchestrator

A facade combining device, protocol, state, and battery into one API used by CLI and GUI.

**Files:**
- Create: `engine/__init__.py` (expand from empty marker)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `HatorDevice`, `build_apply_sequence`, `default_config`, `save_state`, `load_state`, `read_battery`.
- Produces (used by Task 7 cli, Task 9 gui):
  - `class HatorEngine`:
    - `__init__(self, device=None, state_path=None)` — device may be injected (test), else `HatorDevice()`.
    - `apply(config: dict) -> dict` — merge over saved/defaults, build sequence, apply via device, persist state, return the effective config.
    - `apply_defaults() -> dict` — apply `default_config()`.
    - `get_state() -> dict | None` — current state.
    - `read_battery() -> dict | None` — delegate to battery module.

- [ ] **Step 1: Write the failing test**

Update `engine/__init__.py` to import the submodules, and create `tests/test_engine.py`:

```python
import pytest
from engine import protocol as p
from engine import HatorEngine
from engine.device import DeviceNotFoundError


class FakeDevice:
    def __init__(self):
        self.applied = []

    def apply_sequence(self, sequence):
        self.applied.append(sequence)

    def close(self):
        pass


def test_apply_persists_and_applies(tmp_path):
    fake = FakeDevice()
    eng = HatorEngine(device=fake, state_path=str(tmp_path / "s.json"))
    cfg = p.default_config()
    cfg["polling_rate"] = 500
    eff = eng.apply(cfg)
    assert eff["polling_rate"] == 500
    assert len(fake.applied) == 1
    assert eng.get_state()["polling_rate"] == 500


def test_apply_defaults():
    fake = FakeDevice()
    eng = HatorEngine(device=fake)
    eff = eng.apply_defaults()
    assert eff["button_map"] == ["left", "right", "middle", "forward", "backward", "dpi"]
    assert fake.applied  # a sequence was sent


def test_apply_merges_over_saved(tmp_path):
    fake = FakeDevice()
    eng = HatorEngine(device=fake, state_path=str(tmp_path / "s.json"))
    eng.apply({"polling_rate": 250})
    # Now only override DPI; polling should remain 250 from saved state
    eng.apply({"active_slot": 2})
    eff = eng.get_state()
    assert eff["polling_rate"] == 250
    assert eff["active_slot"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_engine.py -v`
Expected: FAIL with `ImportError: cannot import name 'HatorEngine'`.

- [ ] **Step 3: Implement the engine facade**

Replace `engine/__init__.py`:

```python
"""HATOR Pulsar 2 Pro configuration engine (CLI/GUI-independent core)."""
from __future__ import annotations

from .protocol import default_config, build_apply_sequence
from .state import save_state, load_state, default_state_path
from .battery import read_battery
from .device import HatorDevice

__all__ = ["HatorEngine", "HatorDevice", "default_config", "read_battery"]


class HatorEngine:
    def __init__(self, device=None, state_path=None):
        self._device = device
        self.state_path = state_path or default_state_path()
        self._owns_device = device is None

    def _get_device(self):
        if self._device is None:
            self._device = HatorDevice()
        return self._device

    def apply(self, config: dict) -> dict:
        base = load_state(self.state_path) or default_config()
        merged = default_config()
        merged.update(base)
        merged.update(config)
        sequence = build_apply_sequence(merged)
        self._get_device().apply_sequence(sequence)
        save_state(merged, self.state_path)
        return merged

    def apply_defaults(self) -> dict:
        return self.apply({})

    def get_state(self):
        return load_state(self.state_path)

    def read_battery(self):
        return read_battery()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_engine.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/__init__.py tests/test_engine.py
git commit -m "feat: HatorEngine facade combining device, protocol, state, battery"
```

---

### Task 6: Host-side binding via input-remapper

Generates input-remapper preset configuration so a host-visible button (evdev name) maps to an arbitrary action. Coordinates with on-device exposure done by the engine.

**Files:**
- Create: `bindings.py`
- Test: `tests/test_bindings.py`

**Interfaces:**
- Consumes: nothing from engine (evdev names and actions are host concepts).
- Produces (used by Task 7 cli, Task 9 gui):
  - `evdev_button_for(physical_btn_index: int) -> str` — returns the host-visible evdev button name the on-device exposure should use. For indexes 0-2 (left/right/middle) returns `"BTN_LEFT"/"BTN_RIGHT"/"BTN_MIDDLE"`; index 3 → `"BTN_SIDE"`; index 4 → `"BTN_EXTRA"`; index 5 (DPI) → `"BTN_SIDE"` (re-exposed as a side button).
  - `generate_preset(evdev_button: str, action: str) -> str` — returns an input-remapper preset config string (TOML) mapping the button to the action. For a key action `action` is the evdev key code string; for macros use `<macro>...` as in input-remapper syntax.
  - `write_preset(device_name: str, evdev_button: str, action: str, preset_dir=None) -> str` — writes a TOML preset file and returns its path.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bindings.py`:

```python
from bindings import evdev_button_for, generate_preset, write_preset


def test_evdev_button_for_physical_index():
    assert evdev_button_for(0) == "BTN_LEFT"
    assert evdev_button_for(1) == "BTN_RIGHT"
    assert evdev_button_for(2) == "BTN_MIDDLE"
    assert evdev_button_for(5) == "BTN_SIDE"  # DPI button re-exposed


def test_generate_preset_key_action():
    preset = generate_preset("BTN_SIDE", "KEY_PLAYPAUSE")
    assert "KEY_PLAYPAUSE" in preset
    assert "BTN_SIDE" in preset


def test_generate_preset_macro():
    preset = generate_preset("BTN_EXTRA", "<macro>k(KEY_LEFTSHIFT)h(KEY_A)</macro>")
    assert "macro" in preset


def test_write_preset_writes_file(tmp_path):
    path = write_preset("HATOR Mouse", "BTN_SIDE", "KEY_PLAYPAUSE", preset_dir=str(tmp_path))
    with open(path) as f:
        assert "KEY_PLAYPAUSE" in f.read()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bindings.py -v`
Expected: FAIL with `ModuleNotFoundError: bindings`.

- [ ] **Step 3: Implement `bindings.py`**

```python
"""input-remapper integration for host-side arbitrary button binding.

input-remapper stores per-device presets as TOML under
~/.config/input-remapper-2/presets/<device>/<preset>.toml (or the
input-remapper-1 path). This module generates those files.
"""
from __future__ import annotations

import os

PHYSICAL_TO_EVDEV = {
    0: "BTN_LEFT",
    1: "BTN_RIGHT",
    2: "BTN_MIDDLE",
    3: "BTN_SIDE",    # physical Forward
    4: "BTN_EXTRA",   # physical Backward
    5: "BTN_SIDE",    # DPI button, re-exposed as a side button
}


def evdev_button_for(physical_btn_index: int) -> str:
    if physical_btn_index not in PHYSICAL_TO_EVDEV:
        raise ValueError(f"No evdev mapping for physical button index {physical_btn_index}")
    return PHYSICAL_TO_EVDEV[physical_btn_index]


def generate_preset(evdev_button: str, action: str) -> str:
    return (
        "# Generated by hator-config; remove this file to disable.\n"
        f'[[mappings]]\n'
        f'input = "{evdev_button}"\n'
        f'output = "{action}"\n'
    )


def write_preset(device_name: str, evdev_button: str, action: str, preset_dir=None) -> str:
    preset_dir = preset_dir or os.path.expanduser(
        "~/.config/input-remapper-2/presets"
    )
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in device_name)
    path = os.path.join(preset_dir, safe, "hator.toml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(generate_preset(evdev_button, action))
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bindings.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add bindings.py tests/test_bindings.py
git commit -m "feat: input-remapper host-side binding preset generation"
```

---

### Task 7: CLI

A `hator` command wrapping the engine. Subcommands for battery, DPI, polling, bind, get, default.

**Files:**
- Create: `cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `HatorEngine`, `default_config`, `evdev_button_for`, `write_preset`, `generate_preset`.
- Produces: a runnable `python3 cli.py ...` CLI. Exposes `main(argv=None) -> int`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
from cli import main


def test_cli_battery_no_device_ok(monkeypatch, capsys):
    # --battery with no real device should print a message, exit 0.
    monkeypatch.setattr("cli.HatorEngine", _FakeEngine)
    rc = main(["--battery"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "battery" in out.lower()


class _FakeEngine:
    def read_battery(self):
        return {"level": 50, "status": "Discharging"}

    def get_state(self):
        return None

    def apply_defaults(self):
        return {"polling_rate": 1000}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: cli`.

- [ ] **Step 3: Implement `cli.py`**

```python
#!/usr/bin/env python3
"""hator: CLI for configuring the HATOR Pulsar 2 Pro wireless mouse."""
import argparse
import sys

from engine import HatorEngine
from engine.protocol import default_config, POLLING_OPTIONS
from bindings import evdev_button_for, write_preset


def _print_battery(engine):
    info = engine.read_battery()
    if not info or info.get("status") == "unavailable":
        print("Battery: unavailable (no sysfs node; Tier 2 not yet implemented)")
        return
    level = info.get("level")
    print(f"Battery: {level if level is not None else '?'}%  ({info.get('status')})")


def _cmd_bind(engine, args):
    cfg = engine.get_state() or default_config()
    try:
        physical_idx = int(args.bind_btn) - 1
    except (ValueError, TypeError):
        print(f"Invalid button number: {args.bind_btn}", file=sys.stderr)
        return 2
    # On-device exposure: assign a host-visible standard action to this slot.
    mapping = {0: "left", 1: "right", 2: "middle", 3: "forward", 4: "backward", 5: "forward"}
    while len(cfg["button_map"]) < 6:
        cfg["button_map"].append(default_config()["button_map"][len(cfg["button_map"])])
    cfg["button_map"][physical_idx] = mapping[physical_idx]
    engine.apply(cfg)
    evdev = evdev_button_for(physical_idx)
    write_preset(args.device_name, evdev, args.bind_action)
    print(f"Bound button {args.bind_btn} to {args.bind_action} (on-device + input-remapper)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="HATOR Pulsar 2 Pro configurator")
    parser.add_argument("--battery", action="store_true", help="Show battery charge")
    parser.add_argument("--dpi", nargs="+", type=int, metavar="CPI", help="Set DPI slots")
    parser.add_argument("--active-dpi", type=int, metavar="IDX", help="Active DPI slot index 0-6")
    parser.add_argument("--dpi-count", type=int, metavar="N", help="Active DPI slot count 1-7")
    parser.add_argument("--polling", type=int, metavar="HZ", choices=list(POLLING_OPTIONS),
                        help="Polling rate: 125/250/500/1000")
    parser.add_argument("--bind", nargs=2, metavar=("BTN", "ACTION"),
                        help="Bind a physical button (1-6) to an action (e.g. --bind 6 KEY_PLAYPAUSE)")
    parser.add_argument("--device-name", default="HATOR Mouse", help="input-remapper device name")
    parser.add_argument("--get", action="store_true", help="Show last applied config")
    parser.add_argument("--default", action="store_true", help="Apply factory defaults")
    args = parser.parse_args(argv)

    engine = HatorEngine()
    try:
        if args.battery:
            _print_battery(engine)
            return 0
        if args.get:
            state = engine.get_state() or default_config()
            print(f"Polling rate : {state['polling_rate']} Hz")
            print(f"DPI slots    : {state['cpi']}")
            print(f"Active DPI   : slot {state['active_slot'] + 1}")
            print(f"Button map   : {state['button_map']}")
            return 0
        if args.default:
            engine.apply_defaults()
            print("Applied factory defaults.")
            return 0
        if args.bind:
            return _cmd_bind(engine, args)

        cfg = default_config()
        changed = False
        if args.dpi is not None:
            cfg["cpi"] = args.dpi
            changed = True
        if args.active_dpi is not None:
            cfg["active_slot"] = args.active_dpi
            changed = True
        if args.dpi_count is not None:
            cfg["dpi_count"] = args.dpi_count
            changed = True
        if args.polling is not None:
            cfg["polling_rate"] = args.polling
            changed = True
        if not changed:
            parser.print_help()
            return 1
        engine.apply(cfg)
        print("Configuration applied.")
        return 0
    finally:
        # HatorDevice.close is owned by the engine; no-op here for engine lifecycle.
        pass


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Manual smoke test (no mouse needed for --battery path)**

Run: `python3 cli.py --battery`
Expected: prints `Battery: unavailable (...)` or a real level if a sysfs node exists, exit 0.

- [ ] **Step 6: Commit**

```bash
git add cli.py tests/test_cli.py
git commit -m "feat: hator CLI"
```

---

### Task 8: udev rule + README + packaging

Passwordless USB access and documentation.

**Files:**
- Create: `udev/99-hator-pulsar2.rules`
- Create: `README.md`
- Create: `requirements.txt`

**Interfaces:**
- Produces: installable dependencies list, udev rule, and user documentation.

- [ ] **Step 1: Create the udev rule**

Create `udev/99-hator-pulsar2.rules`:

```
SUBSYSTEM=="usb", ATTRS{idVendor}=="04d9", ATTRS{idProduct}=="a09f", MODE="0666", GROUP="plugdev"
```

- [ ] **Step 2: Create `requirements.txt`**

```
pyusb>=1.2
pytest>=7.0
```

(GTK4 via PyGObject is a system package, not pip; note in README.)

- [ ] **Step 3: Create `README.md`**

Document: purpose, the four capabilities, install (libusb, pyusb, PyGObject, input-remapper), udev rule install, usage examples for `--battery`, `--dpi`, `--polling`, `--bind`, `--get`, `--default`, the hybrid binding model (on-device exposure + input-remapper), the battery two-tier strategy, write-only caveat, and attribution to `hampta/luom-g10-config` for the decoded protocol.

- [ ] **Step 4: Commit**

```bash
git add udev/99-hator-pulsar2.rules requirements.txt README.md
git commit -m "docs: README, udev rule, and requirements"
```

---

### Task 9: GTK GUI

A thin GTK4 desktop app on top of the engine and bindings. All logic stays in the engine; the GUI is a view. Because GTK is hard to unit-test headless, this task verifies the module imports, builds its window, and wires the panels to engine calls.

**Files:**
- Create: `gui.py`
- Test: `tests/test_gui.py`

**Interfaces:**
- Consumes: `HatorEngine`, `default_config`, `evdev_button_for`, `write_preset`.
- Produces: `build_window(engine=None) -> Gtk.Window` and `run()` entrypoint.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gui.py`:

```python
def test_gui_imports_and_builds_window():
    import gui
    win = gui.build_window()
    assert win is not None
    win.destroy()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gui.py -v`
Expected: FAIL with `ModuleNotFoundError: gui`.

- [ ] **Step 3: Implement `gui.py`**

A GTK4 app with four panels: Battery, DPI, Polling, and Button bindings. Each panel reads/writes through `HatorEngine`. Example skeleton:

```python
#!/usr/bin/env python3
"""GTK GUI for the HATOR Pulsar 2 Pro configurator."""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from engine import HatorEngine
from engine.protocol import default_config, POLLING_OPTIONS
from bindings import evdev_button_for, write_preset


def build_window(engine=None):
    engine = engine or HatorEngine()
    window = Gtk.ApplicationWindow()
    window.set_title("HATOR Pulsar 2 Pro")
    window.set_default_size(420, 480)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    window.set_child(box)

    # Battery
    battery_label = Gtk.Label(label="Battery: reading...")
    box.append(battery_label)
    info = engine.read_battery()
    if info and info.get("status") != "unavailable":
        battery_label.set_label(f"Battery: {info.get('level')}% ({info.get('status')})")
    else:
        battery_label.set_label("Battery: unavailable")

    # DPI
    dpi_label = Gtk.Label(label="DPI slots: (state)")
    box.append(dpi_label)
    state = engine.get_state() or default_config()
    dpi_label.set_label(f"DPI slots: {state['cpi']}  active: slot {state['active_slot'] + 1}")

    # Polling selector
    polling_box = Gtk.Box(spacing=4)
    polling_box.append(Gtk.Label(label="Polling rate:"))
    combo = Gtk.DropDown.new_from_strings([str(h) for h in POLLING_OPTIONS])
    combo.set_selected(list(POLLING_OPTIONS).index(state["polling_rate"]))
    polling_box.append(combo)
    box.append(polling_box)

    def on_polling_change(*_):
        idx = combo.get_selected()
        hz = POLLING_OPTIONS[idx]
        engine.apply({"polling_rate": hz})

    combo.connect("notify::selected", on_polling_change)

    # Button bindings (informational here; full editor wires --bind + input-remapper)
    bind_label = Gtk.Label(label=f"Button map: {state['button_map']}")
    box.append(bind_label)

    return window


def run():
    from gi.repository import Gtk as _Gtk
    app = _Gtk.Application()
    app.connect("activate", lambda a: build_window().present())
    app.run()


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gui.py -v`
Expected: PASS (1 test). If the environment lacks a display, GTK object construction may still work headless via `GDK_BACKEND=headless`; if it fails, mark the test to skip when `DISPLAY` and `WAYLAND_DISPLAY` are both unset:

```python
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"),
    reason="no display for GTK smoke test",
)
```

- [ ] **Step 5: Manual smoke test**

Run: `python3 gui.py`
Expected: a GTK window opens with the four panels. Closing it exits cleanly.

- [ ] **Step 6: Commit**

```bash
git add gui.py tests/test_gui.py
git commit -m "feat: GTK GUI for HATOR Pulsar 2 Pro configurator"
```

---

## Verification tasks (VM / hardware)

These are gated on real hardware and are not part of the automated test suite. They resolve the two open reverse-engineering questions from the spec.

1. **Connect the mouse to the Linux host** and run `python3 cli.py --battery`. If a sysfs `power_supply/hid-*-battery` node exists, Tier 1 battery works with zero reverse-engineering. Confirm via `ls /sys/class/power_supply/`.
2. **DPI-button exposure**: with the mouse on the Linux host, press the DPI button (slot 6) and run `sudo evtest` (or `libinput debug-events`) to check whether any event appears. Then run `hator --bind 6 KEY_PLAYPAUSE` (or set on-device slot 6 to `forward`) and re-test whether the press is now visible. This confirms the on-device exposure + input-remapper flow.
3. **Tier 2 battery (only if Tier 1 fails)**: in the win11 VM, capture the battery-poll traffic with USBPcap while the official app shows battery, then implement the read channel in `engine/battery.py` and re-run test task 4.
