"""HATOR Pulsar 2 Pro configuration engine (CLI/GUI-independent core)."""
from __future__ import annotations

from .protocol import default_config, apply_config
from .state import save_state, load_state, default_state_path
from .battery import read_battery, battery_unavailable
from .device import HatorDevice, DeviceNotFoundError

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

    def apply(self, config: dict, reset: bool = False) -> dict:
        if reset:
            merged = default_config()
        else:
            base = load_state(self.state_path) or default_config()
            merged = default_config()
            merged.update(base)
        merged.update(config)
        dev = self._get_device()
        apply_config(
            dev,
            polling_hz=merged["polling_rate"],
            dpi_slots=merged["cpi"],
        )
        save_state(merged, self.state_path)
        return merged

    def apply_defaults(self) -> dict:
        return self.apply({}, reset=True)

    def get_state(self) -> dict | None:
        return load_state(self.state_path)

    def read_battery(self) -> dict | None:
        # Tier 1: sysfs node; Tier 2: device feature report.
        try:
            dev = self._get_device()
        except DeviceNotFoundError:
            dev = None
        info = read_battery(dev)
        if info is None:
            return battery_unavailable()
        return info

    def close(self):
        if self._device is not None and self._owns_device:
            self._device.close()
            self._device = None
