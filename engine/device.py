"""USB device access for the HATOR Pulsar 2 Pro (wireless) via pyusb.

The wireless Pulsar 2 Pro uses a SINOWEALTH 2.4G receiver (VID 0x258a,
PID 0x002f), NOT the Holtek 0x04d9:0xa09f device that the wired LUOM G10
uses. engine/protocol.py currently contains the (placeholder) Holtek packet
encoding; until the Sinowealth configuration protocol is reverse-engineered
from USBPcap captures, a detected receiver raises SinowealthProtocolNotImplemented
instead of sending those (wrong) packets to the device.
"""
from __future__ import annotations

import time

import usb.core
import usb.util

# The real device: SINOWEALTH 2.4G wireless receiver.
SINOWEALTH_VID = 0x258A
SINOWEALTH_PID = 0x002F

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


class SinowealthProtocolNotImplemented(NotImplementedError):
    """The receiver was found, but its config protocol is not decoded yet."""


class HatorDevice:
    def __init__(self, dev=None):
        injected = dev is not None
        self.dev = dev if injected else usb.core.find(
            idVendor=SINOWEALTH_VID, idProduct=SINOWEALTH_PID
        )
        if self.dev is None:
            raise DeviceNotFoundError(
                f"HATOR Pulsar 2 Pro receiver not found (expect "
                f"{SINOWEALTH_VID:04x}:{SINOWEALTH_PID:04x} SINOWEALTH). "
                "Is the receiver plugged in? Check `lsusb | grep 258a`."
            )
        if not injected:
            # A real receiver is present but we don't have its protocol yet.
            raise SinowealthProtocolNotImplemented(
                "SINOWEALTH 2.4G receiver (258a:002f) detected, but its "
                "configuration protocol is not yet reverse-engineered. "
                "Capture it in the win11 VM with USBPcap (see "
                "docs/vm-capture.md) and reimplement engine/protocol.py; "
                "then this tool will configure the mouse."
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
