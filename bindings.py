"""input-remapper integration for host-side arbitrary button binding.

input-remapper 2.x stores per-device presets as JSON under
~/.config/input-remapper-2/presets/<sanitized-device>/<preset>.json.
Each preset file is a JSON list of mapping dicts, each with:
  - input_combination: [{"type": <EV_KEY=1>, "code": <evdev code>}]
  - target_uinput: "keyboard" or "mouse"
  - output_symbol: an evdev key name, or a "<macro>...</macro>" string

This module generates those files.
"""
from __future__ import annotations

import json
import os

# EV_KEY event type (linux/input-event-codes.h)
EV_KEY = 1

# evdev button name -> (type, code). Hardcoded rather than importing
# python-evdev, since it is not a required runtime dependency of this tool.
EVDEV_BUTTON_CODES = {
    "BTN_LEFT": (EV_KEY, 0x110),
    "BTN_RIGHT": (EV_KEY, 0x111),
    "BTN_MIDDLE": (EV_KEY, 0x112),
    "BTN_SIDE": (EV_KEY, 0x113),
    "BTN_EXTRA": (EV_KEY, 0x114),
}

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


def _target_uinput_for(action: str) -> str:
    """Infer the input-remapper target_uinput from the output action string."""
    if action.strip().startswith("<macro>"):
        return "keyboard"
    if action.upper().startswith(("BTN_", "REL_", "MOUSE")):
        return "mouse"
    return "keyboard"


def generate_preset(evdev_button: str, action: str) -> str:
    """Build a real input-remapper preset (a JSON list of mapping dicts).

    Returns the JSON-encoded string (json.dumps output), so callers that
    previously treated this as opaque text to write to disk keep working.
    """
    if evdev_button not in EVDEV_BUTTON_CODES:
        raise ValueError(f"No evdev code mapping for button {evdev_button!r}")
    type_, code = EVDEV_BUTTON_CODES[evdev_button]
    mapping = [{
        "input_combination": [{"type": type_, "code": code}],
        "target_uinput": _target_uinput_for(action),
        "output_symbol": action,
    }]
    return json.dumps(mapping, indent=4)


def write_preset(device_name: str, evdev_button: str, action: str, preset_dir=None) -> str:
    preset_dir = preset_dir or os.path.expanduser(
        "~/.config/input-remapper-2/presets"
    )
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in device_name)
    path = os.path.join(preset_dir, safe, "hator.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(generate_preset(evdev_button, action))
    return path
