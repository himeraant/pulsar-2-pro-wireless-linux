"""USB device access for the HATOR Pulsar 2 Pro (wireless) via pyusb.

The wireless Pulsar 2 Pro uses a SINOWEALTH 2.4G receiver (VID 0x258a, PID
0x002f). Configuration and battery use vendor HID reports (report IDs 0x05 and
0x08) on USB interface 1, accessed as HID control transfers:

  SET_REPORT (OUT): bmRequestType=0x21, bRequest=0x09, wValue=0x0300|report_id,
                    wIndex=0x0001, data = [report_id, payload...]
  GET_REPORT (IN) : bmRequestType=0xA1, bRequest=0x01, wValue=0x0300|report_id,
                    wIndex=0x0001, wLength = report size

Interface 1 must be claimed (usbhid detached) to send these control transfers.
The mouse pointer lives on interface 0, so it keeps working; interface 1
(keyboard/vendor) is claimed for the duration and released + re-bound on close.
"""
from __future__ import annotations

import usb.core
import usb.util

SINOWEALTH_VID = 0x258A
SINOWEALTH_PID = 0x002F

SET_REPORT = 0x09
GET_REPORT = 0x01
HID_FEATURE = 0x0300  # report type 3 (feature) in the high byte of wValue
INTERFACE = 1         # wIndex: the vendor/config interface


class DeviceNotFoundError(Exception):
    pass


class HatorDevice:
    def __init__(self, dev=None, _auto_claim=True):
        self.dev = dev if dev is not None else usb.core.find(
            idVendor=SINOWEALTH_VID, idProduct=SINOWEALTH_PID
        )
        if self.dev is None:
            raise DeviceNotFoundError(
                f"HATOR Pulsar 2 Pro receiver not found (expect "
                f"{SINOWEALTH_VID:04x}:{SINOWEALTH_PID:04x} SINOWEALTH). "
                "Is the receiver plugged in? Check `lsusb | grep 258a`."
            )
        self._detached = False
        self._claimed = False
        if _auto_claim:
            self._claim()

    def _claim(self):
        """Detach usbhid from interface 1 and claim it for control transfers."""
        try:
            if self.dev.is_kernel_driver_active(INTERFACE):
                self.dev.detach_kernel_driver(INTERFACE)
                self._detached = True
        except usb.core.USBError:
            pass
        usb.util.claim_interface(self.dev, INTERFACE)
        self._claimed = True

    def feature_out(self, report_id: int, data: bytes) -> None:
        buf = bytes([report_id]) + data
        self.dev.ctrl_transfer(
            0x21, SET_REPORT, HID_FEATURE | report_id, INTERFACE, buf
        )

    def feature_in(self, report_id: int, size: int) -> bytes:
        resp = self.dev.ctrl_transfer(
            0xA1, GET_REPORT, HID_FEATURE | report_id, INTERFACE, size
        )
        return bytes(resp)

    def close(self) -> None:
        try:
            if self._claimed:
                usb.util.release_interface(self.dev, INTERFACE)
        except Exception:
            pass
        try:
            if self._detached:
                self.dev.attach_kernel_driver(INTERFACE)
        except Exception:
            pass
        self._claimed = False
        self._detached = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
