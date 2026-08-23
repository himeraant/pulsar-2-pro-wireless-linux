"""USB device access for the HATOR Pulsar 2 Pro (wireless) via hidraw.

The wireless Pulsar 2 Pro uses a SINOWEALTH 2.4G receiver (VID 0x258a, PID
0x002f). Configuration and battery use HID feature reports (report IDs 0x05 and
0x08) sent over the receiver's hidraw node via the HIDIOCSFEATURE / HIDIOCGFEATURE
ioctls. This works alongside usbhid (the mouse keeps working) without detaching
any kernel driver. Requires a udev rule granting the hidraw nodes access (see
udev/99-hator-pulsar2.rules).
"""
from __future__ import annotations

import fcntl
import glob
import os

SINOWEALTH_VID = 0x258A
SINOWEALTH_PID = 0x002F

# ioctl encoding (Linux asm-generic/ioctl.h)
_IOC_NRBITS, _IOC_TYPEBITS, _IOC_SIZEBITS, _IOC_DIRBITS = 8, 8, 14, 2
_IOC_NRSHIFT, _IOC_TYPESHIFT, _IOC_SIZESHIFT, _IOC_DIRSHIFT = 0, 8, 16, 30
_IOC_WRITE, _IOC_READ = 1, 2


def _ioc(direction, type_, nr, size):
    return (direction << _IOC_DIRSHIFT) | (size << _IOC_SIZESHIFT) | (
        ord(type_) << _IOC_TYPESHIFT) | nr


def _sfeat(size):
    return _ioc(_IOC_WRITE, "H", 0x06, size)   # HIDIOCSFEATURE


def _gfeat(size):
    return _ioc(_IOC_WRITE | _IOC_READ, "H", 0x07, size)  # HIDIOCGFEATURE


class DeviceNotFoundError(Exception):
    pass


class PermissionError2(Exception):
    pass


def _receiver_hidraw_nodes(vid=SINOWEALTH_VID, pid=SINOWEALTH_PID):
    target = f"{vid:04x}:{pid:04x}".lower()
    nodes = []
    for node in glob.glob("/sys/class/hidraw/hidraw*"):
        try:
            real = os.path.realpath(node)
        except OSError:
            continue
        if target in real.lower():
            nodes.append((real, "/dev/" + os.path.basename(node)))
    return nodes


def find_hidraw(vid=SINOWEALTH_VID, pid=SINOWEALTH_PID) -> str | None:
    """Return the receiver's config hidraw node (interface 1 preferred)."""
    nodes = _receiver_hidraw_nodes(vid, pid)
    if not nodes:
        return None
    # Prefer the node whose path references the second interface (3-2:1.1),
    # which carried the config/battery feature reports (wIndex=0x0001).
    for real, dev in nodes:
        if ":1.1" in real:
            return dev
    return nodes[0][1]


class HatorDevice:
    def __init__(self, path: str | None = None, _fd=None):
        if _fd is not None:  # tests
            self._fd = _fd
            return
        self.path = path or find_hidraw()
        if self.path is None:
            raise DeviceNotFoundError(
                f"HATOR Pulsar 2 Pro receiver not found (expect "
                f"{SINOWEALTH_VID:04x}:{SINOWEALTH_PID:04x} SINOWEALTH). "
                "Is the receiver plugged in? Check `lsusb | grep 258a`."
            )
        try:
            self._fd = os.open(self.path, os.O_RDWR)
        except PermissionError as e:
            raise PermissionError2(
                f"Cannot open {self.path} (need the udev rule for hidraw; see "
                "udev/99-hator-pulsar2.rules, then `sudo udevadm control "
                "--reload-rules && sudo udevadm trigger`)."
            ) from e

    def feature_out(self, report_id: int, data: bytes) -> None:
        """Send a feature report: data is the payload WITHOUT the report id."""
        buf = bytes([report_id]) + data
        fcntl.ioctl(self._fd, _sfeat(len(buf)), buf)

    def feature_in(self, report_id: int, size: int) -> bytes:
        """Read a feature report; returns report_id + size-1 data bytes."""
        buf = bytearray(size)
        buf[0] = report_id
        # Pass the mutable bytearray so the kernel writes the response back.
        fcntl.ioctl(self._fd, _gfeat(size), buf)
        return bytes(buf)

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
