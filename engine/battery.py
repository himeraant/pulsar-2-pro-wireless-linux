"""Battery level reader.

Tier 1: kernel-exposed HID power_supply node (no reverse-engineering).
Tier 2: Sinowealth feature-report read (report 0x05, cmd 0x90) over hidraw.
"""
from __future__ import annotations

import os

from . import protocol as p


def read_battery(dev=None, power_supply_dir: str | None = None) -> dict | None:
    """Return {"level","status"} from sysfs (Tier 1) or the device (Tier 2)."""
    sysfs = _read_sysfs(power_supply_dir)
    if sysfs:
        return sysfs
    if dev is not None:
        try:
            level = p.read_battery(dev)
        except Exception:
            level = None
        if level is not None:
            return {"level": level, "status": "unknown"}
    return None


def battery_unavailable() -> dict:
    return {"level": None, "status": "unavailable", "tier": 2}


def _read_sysfs(power_supply_dir: str | None = None) -> dict | None:
    power_supply_dir = power_supply_dir or "/sys/class/power_supply"
    if not os.path.isdir(power_supply_dir):
        return None
    try:
        names = os.listdir(power_supply_dir)
    except OSError:
        return None
    for name in names:
        if "battery" not in name:
            continue
        node = os.path.join(power_supply_dir, name)
        level = _read_int(os.path.join(node, "capacity"))
        status = _read_text(os.path.join(node, "status"))
        if level is None and status is None:
            continue
        return {"level": level, "status": status}
    return None


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
