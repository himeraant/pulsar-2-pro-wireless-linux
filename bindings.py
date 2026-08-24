"""input-remapper integration for host-side arbitrary button binding.

input-remapper 2.x stores per-device presets as JSON under
~/.config/input-remapper-2/presets/<device-name>/<preset>.json. Each preset
file is a JSON list of mapping dicts. For a mapping to actually trigger, its
`input_combination` MUST carry the device's `origin_hash` (the event matcher is
`(type, code, origin_hash)` and every real event carries one). See
input-remapper's input_config.py / utils.py.

Mapping schema (input-remapper 2.x):
  - input_combination: [{"type": EV_KEY=1, "code": evdev code,
                         "origin_hash": "<device hash>"}]
  - target_uinput:     "keyboard" | "mouse" | "gamepad" | "keyboard + mouse"
  - output_symbol:     evdev key name, or a "<macro>...</macro>" string
  - name:              human-readable label
  - mapping_type:      "key_macro"
"""
from __future__ import annotations

import glob
import hashlib
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

# Physical button slot -> evdev code emitted by the mouse. Buttons 1-5 have
# distinct host-visible codes and are host-remappable via input-remapper.
# Button 6 (the DPI button) emits NO standard HID button event (it only cycles
# DPI slots, reported via report 0x07), so it cannot be remapped host-side.
PHYSICAL_TO_EVDEV = {
    0: "BTN_LEFT",    # 1  Left
    1: "BTN_RIGHT",   # 2  Right
    2: "BTN_MIDDLE",  # 3  Middle
    3: "BTN_SIDE",    # 4  Forward (side)
    4: "BTN_EXTRA",   # 5  Backward (extra)
}
# physical index 5 = DPI button: not host-remappable.

PRESET_FILENAME = "hator.json"


class BindError(Exception):
    """Raised for user-facing binding problems (e.g. non-remappable button)."""


def evdev_button_for(physical_btn_index: int) -> str:
    """Map a 0-based physical button index to the evdev name it emits.

    Raises BindError for buttons with no distinct host-visible code (the DPI
    button, index 5).
    """
    if physical_btn_index == 5:
        raise BindError(
            "Button 6 (DPI) emits no distinct host-visible event, so it cannot "
            "be remapped via input-remapper. Use on-device DPI cycling instead."
        )
    if physical_btn_index not in PHYSICAL_TO_EVDEV:
        raise BindError(
            f"No host-visible evdev mapping for physical button index {physical_btn_index}"
        )
    return PHYSICAL_TO_EVDEV[physical_btn_index]


def _target_uinput_for(action: str) -> str:
    """Infer the input-remapper target_uinput from the output action string."""
    if action.strip().startswith("<macro>"):
        return "keyboard"
    if action.upper().startswith(("BTN_", "REL_", "MOUSE")):
        return "mouse"
    return "keyboard"


def sanitize_device_name(name: str) -> str:
    """Mirror input-remapper's PathUtils.sanitize_path_component.

    Only the filename-reserved characters are replaced with '_'; spaces,
    dashes, dots etc. are preserved so the preset folder matches what
    input-remapper uses for the device.
    """
    for character in '/\\?%*:|"<>':
        if character in name:
            name = name.replace(character, "_")
    return name


def _default_preset_dir() -> str:
    xdg = os.getenv("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
    return os.path.join(xdg, "input-remapper-2", "presets")


def preset_path(device_name: str, preset_dir: str | None = None) -> str:
    preset_dir = preset_dir or _default_preset_dir()
    return os.path.join(preset_dir, sanitize_device_name(device_name), PRESET_FILENAME)


def _mapping_for(evdev_button: str, action: str, origin_hash: str, name: str | None = None) -> dict:
    if evdev_button not in EVDEV_BUTTON_CODES:
        raise BindError(f"No evdev code mapping for button {evdev_button!r}")
    if not origin_hash:
        raise BindError(
            "origin_hash is required for a working input-remapper preset. "
            "Pass --origin-hash <hash> or run with python-evdev installed so "
            "it can be auto-detected (input-remapper also shows it)."
        )
    type_, code = EVDEV_BUTTON_CODES[evdev_button]
    return {
        "input_combination": [
            {"type": type_, "code": code, "origin_hash": origin_hash}
        ],
        "target_uinput": _target_uinput_for(action),
        "output_symbol": action,
        "name": name or f"{evdev_button} -> {action}",
        "mapping_type": "key_macro",
    }


def generate_preset(
    evdev_button: str, action: str, origin_hash: str, name: str | None = None
) -> str:
    """Build a single-mapping input-remapper preset (a JSON list of dicts)."""
    return json.dumps([_mapping_for(evdev_button, action, origin_hash, name)], indent=4)


def load_preset(device_name: str, preset_dir: str | None = None) -> list:
    """Load the mappings already stored for a device, or an empty list."""
    path = preset_path(device_name, preset_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def save_preset(device_name: str, mappings: list, preset_dir: str | None = None) -> str:
    path = preset_path(device_name, preset_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(mappings, f, indent=4)
        f.write("\n")
    return path


def _code_of(mapping: dict) -> int | None:
    combo = mapping.get("input_combination")
    if isinstance(combo, list) and combo and isinstance(combo[0], dict):
        return combo[0].get("code")
    return None


def set_binding(
    device_name: str,
    physical_btn_index: int,
    action: str,
    origin_hash: str,
    preset_dir: str | None = None,
    name: str | None = None,
) -> str:
    """Add or update one button's binding, preserving all other mappings.

    Returns the path to the written preset file.
    """
    evdev_button = evdev_button_for(physical_btn_index)
    code = EVDEV_BUTTON_CODES[evdev_button][1]
    new_mapping = _mapping_for(evdev_button, action, origin_hash, name)
    mappings = load_preset(device_name, preset_dir)
    for i, mapping in enumerate(mappings):
        if _code_of(mapping) == code:
            mappings[i] = new_mapping
            break
    else:
        mappings.append(new_mapping)
    return save_preset(device_name, mappings, preset_dir)


def unbind(device_name: str, physical_btn_index: int, preset_dir: str | None = None) -> bool:
    """Remove the binding for one button. Returns True if something was removed."""
    evdev_button = evdev_button_for(physical_btn_index)
    code = EVDEV_BUTTON_CODES[evdev_button][1]
    mappings = load_preset(device_name, preset_dir)
    remaining = [m for m in mappings if _code_of(m) != code]
    if len(remaining) == len(mappings):
        return False
    save_preset(device_name, remaining, preset_dir)
    return True


def list_bindings(device_name: str, preset_dir: str | None = None) -> list[dict]:
    """Return a list of {btn, evdev, action} for the device's current bindings."""
    reverse = {code: name for name, (_, code) in EVDEV_BUTTON_CODES.items()}
    physical = {name: idx for idx, name in PHYSICAL_TO_EVDEV.items()}
    result = []
    for mapping in load_preset(device_name, preset_dir):
        code = _code_of(mapping)
        if code is None:
            continue
        evdev_name = reverse.get(code)
        result.append(
            {
                "btn": physical.get(evdev_name) + 1 if evdev_name in physical else None,
                "evdev": evdev_name,
                "action": mapping.get("output_symbol"),
            }
        )
    return result


def compute_origin_hash(evdev_device) -> str:
    """Replicate input-remapper's get_device_hash for a device.

    evdev_device must expose `.capabilities(absinfo=False)` and `.name`.
    """
    s = str(evdev_device.capabilities(absinfo=False)) + evdev_device.name
    return hashlib.md5(s.encode()).hexdigest().lower()


def find_origin_hash(device_name: str | None = None, vendor: int = 0x258A):
    """Best-effort detect the mouse's input-remapper origin_hash via python-evdev.

    Returns (evdev_name, origin_hash) or None. Requires python-evdev and a
    matching /dev/input/event* node. Prefers a node that looks like a mouse
    (exposes the BTN_SIDE/BTN_EXTRA buttons). Matching is by USB vendor, then
    by device-name substring.
    """
    try:
        import evdev
    except ImportError:
        return None
    candidates = []
    for path in glob.glob("/dev/input/event*"):
        try:
            dev = evdev.InputDevice(path)
        except Exception:
            continue
        keys = set(dev.capabilities(absinfo=False).get(EV_KEY, []))
        is_mouse = (0x110 in keys) and (0x113 in keys) and (0x114 in keys)
        try:
            dev_vendor = dev.info.vendor
        except Exception:
            dev_vendor = None
        if vendor and dev_vendor == vendor and is_mouse:
            return dev.name, compute_origin_hash(dev)
        candidates.append((dev.name, dev))
    if device_name:
        for name, dev in candidates:
            if device_name.lower() in name.lower():
                return name, compute_origin_hash(dev)
    return None
