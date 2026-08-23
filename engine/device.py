"""USB device access for the HATOR Pulsar 2 Pro (wireless) via pyusb.

The wireless Pulsar 2 Pro uses a SINOWEALTH 2.4G receiver (VID 0x258a, PID
0x002f). Configuration and battery use HID feature reports (report IDs 0x05 and
0x08) sent as standard control transfers to the default control pipe:

  SET_REPORT (OUT): bmRequestType=0x21, bRequest=0x09, wValue=0x0300|report_id,
                    wIndex=0x0001, data = [report_id, payload...]
  GET_REPORT (IN) : bmRequestType=0xA1, bRequest=0x01, wValue=0x0300|report_id,
                    wIndex=0x0001, wLength = report size

The receiver's HID interfaces are bound to usbfs (not usbhid), so no kernel
driver detach is required for control transfers.
"""
from __future__ import annotations

import usb.core
import usb.util

SINOWEALTH_VID = 0x258A
SINOWEALTH_PID = 0x002F

SET_REPORT = 0x09
GET_REPORT = 0x01
HID_FEATURE = 0x0300  # report type 3 (feature) in the high byte of wValue
INTERFACE = 0x0001    # wIndex (HID interface 1)


class DeviceNotFoundError(Exception):
    pass


class HatorDevice:
    def __init__(self, dev=None):
        self.dev = dev if dev is not None else usb.core.find(
            idVendor=SINOWEALTH_VID, idProduct=SINOWEALTH_PID
        )
        if self.dev is None:
            raise DeviceNotFoundError(
                f"HATOR Pulsar 2 Pro receiver not found (expect "
                f"{SINOWEALTH_VID:04x}:{SINOWEALTH_PID:04x} SINOWEALTH). "
                "Is the receiver plugged in? Check `lsusb | grep 258a`."
            )

    def feature_out(self, report_id: int, data: bytes) -> None:
        """Send a feature report: data is the payload WITHOUT the report id."""
        buf = bytes([report_id]) + data
        self.dev.ctrl_transfer(
            0x21, SET_REPORT, HID_FEATURE | report_id, INTERFACE, buf
        )

    def feature_in(self, report_id: int, size: int) -> bytes:
        """Read a feature report; returns report_id + size-1 data bytes."""
        resp = self.dev.ctrl_transfer(
            0xA1, GET_REPORT, HID_FEATURE | report_id, INTERFACE, size
        )
        return bytes(resp)

    def close(self) -> None:
        try:
            usb.util.dispose_resources(self.dev)
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
