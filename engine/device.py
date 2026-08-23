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
            try:
                if self.dev.is_kernel_driver_active(i):
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
        # Only call dispose_resources on real USB devices, not mocks
        if hasattr(self.dev, '_ctx'):
            usb.util.dispose_resources(self.dev)
        for i in self._detached:
            try:
                self.dev.attach_kernel_driver(i)
            except usb.core.USBError:
                pass
