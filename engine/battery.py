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
