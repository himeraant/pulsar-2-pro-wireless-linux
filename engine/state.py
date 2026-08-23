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
            data = json.load(f)
            return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_state(config: dict, path=None) -> None:
    path = path or default_state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
