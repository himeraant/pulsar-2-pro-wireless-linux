"""Media-key daemon for the HATOR receiver.

The receiver's Consumer Control report (ID 0x02) is declared with the
"constant" flag in its HID report descriptor, so the Linux kernel's hid driver
ignores it and no input events are generated (which is why libinput sees
nothing when a button is bound to play_pause). hidraw still receives every raw
report, so we read it here and inject the decoded media keys via uinput.

Usage:
  python3 media.py                 # run the daemon (needs /dev/uinput access)
"""
from __future__ import annotations

import glob
import os
import time

try:
    import evdev
    from evdev import UInput, ecodes as E
except ImportError:
    evdev = None

VID = 0x258A
PID = 0x002F

REPORT_CONSUMER = 0x02

# Consumer usage -> evdev key constant name. Only the well-known ones are
# mapped; byte0 covers the common media controls (incl. play/pause = bit 3).
CONSUMER_KEYS = {
    0x00B5: "KEY_NEXTSONG",
    0x00B6: "KEY_PREVIOUSSONG",
    0x00B7: "KEY_STOPCD",
    0x00CD: "KEY_PLAYPAUSE",
    0x00E2: "KEY_MUTE",
    0x00E9: "KEY_VOLUMEUP",
    0x00EA: "KEY_VOLUMEDOWN",
    0x0183: "KEY_HOMEPAGE",
    0x0194: "KEY_SEARCH",
    0x0186: "KEY_BACK",
    0x0188: "KEY_FORWARD",
    0x018A: "KEY_STOP",
    0x0192: "KEY_REFRESH",
    0x0184: "KEY_BOOKMARKS",
    0x0221: "KEY_VOLUMEDOWN",
    0x0223: "KEY_VOLUMEDOWN",
    0x0224: "KEY_VOLUMEDOWN",
    0x02B1: "KEY_PLAYPAUSE",
}


def _usb_id(path: str):
    """Return (vid, pid, interface) for a hidraw sysfs path, or None."""
    try:
        with open(os.path.join(path, "uevent")) as f:
            u = f.read()
    except OSError:
        return None
    vid = pid = None
    for line in u.splitlines():
        if line.startswith("HID_ID="):
            # HID_ID=bus:vendor:product
            try:
                bus, v, p = line.split("=")[1].split(":")
                vid, pid = int(v, 16), int(p, 16)
            except ValueError:
                pass
    iface = None
    # device path contains e.g. .../1-2:1.1/...  -> interface 1
    for part in path.split("/"):
        if ":" in part and part[0].isdigit():
            try:
                iface = int(part.split(":")[1].split(".")[0])
            except (ValueError, IndexError):
                pass
    return vid, pid, iface


def find_hidraw(interface=1):
    """Return the /dev/hidraw* node for the given interface of the receiver."""
    for dev in glob.glob("/dev/hidraw*"):
        name = os.path.basename(dev)
        syspath = os.path.join("/sys/class/hidraw", name, "device")
        info = _usb_id(syspath)
        if not info:
            continue
        vid, _pid, iface = info
        if vid == VID and iface == interface:
            return dev
    return None


def build_uinput():
    keys = [getattr(E, n) for n in CONSUMER_KEYS.values() if hasattr(E, n)]
    cap = {E.EV_KEY: keys}
    ui = UInput(cap, name="HATOR media", version=1)
    return ui


def _bits_to_keys(report: bytes):
    """Map a 4-byte consumer report (02 b0 b1 b2) to a set of pressed keys."""
    pressed = set()
    if len(report) < 4 or report[0] != REPORT_CONSUMER:
        return pressed
    for byte_idx in range(3):
        b = report[1 + byte_idx]
        for bit in range(8):
            if b & (1 << bit):
                usage = {
                    0: [0x00B5, 0x00B6, 0x00B7, 0x00CD, 0x00E2, 0x00A2, 0x00E9, 0x00EA],
                    1: [0x0183, 0x0194, 0x0186, 0x0188, 0x018A, 0x0192, 0x02A8, 0x0184],
                    2: [0x0221, 0x0223, 0x0224, 0x0225, 0x0226, 0x0227, 0x022A, 0x02B1],
                }[byte_idx][bit]
                name = CONSUMER_KEYS.get(usage)
                if name and hasattr(E, name):
                    pressed.add(getattr(E, name))
    return pressed


def list_hidraws():
    """Return (dev, vid, pid, iface) for every hidraw node (for diagnostics)."""
    out = []
    for dev in glob.glob("/dev/hidraw*"):
        syspath = os.path.join("/sys/class/hidraw", os.path.basename(dev), "device")
        info = _usb_id(syspath)
        out.append((dev,) + info if info else (dev, None, None, None))
    return out


def run(dev_path=None):
    if evdev is None:
        raise SystemExit("python-evdev is required for the media daemon "
                         "(pip install evdev)")
    dev_path = dev_path or find_hidraw(interface=1)
    if not dev_path:
        print("HATOR receiver hidraw interface 1 not found. Available hidraws:")
        for dev, vid, pid, iface in list_hidraws():
            print(f"  {dev}: vendor={vid and hex(vid)} product={pid and hex(pid)} "
                  f"interface={iface}")
        raise SystemExit("use --dev <path> to specify the hidraw node manually")
    ui = build_uinput()
    fd = os.open(dev_path, os.O_RDONLY | os.O_NONBLOCK)
    print(f"media daemon: reading {dev_path}, injecting media keys")
    last = set()
    try:
        while True:
            try:
                data = os.read(fd, 16)
            except BlockingIOError:
                time.sleep(0.005)
                continue
            except OSError:
                time.sleep(0.05)
                continue
            if not data:
                continue
            pressed = _bits_to_keys(bytes(data))
            for key in pressed - last:
                ui.write(E.EV_KEY, key, 1)
            for key in last - pressed:
                ui.write(E.EV_KEY, key, 0)
            if pressed != last:
                ui.syn()
            last = pressed
    except KeyboardInterrupt:
        pass
    finally:
        os.close(fd)
        ui.close()


if __name__ == "__main__":
    run()
