#!/usr/bin/env python3
"""Dump and decode the HID report descriptors of the HATOR receiver interfaces.

Shows how each interface's report IDs are declared (usage page, collection,
usages) so we can see whether the media-key report (ID 0x02, value 0x08) maps
to a Consumer / KEY_PLAYPAUSE or to a plain keyboard key on Linux.

Usage:
  dump_hid_descriptors.py [--iface N]      # dump interface N (default: both)
"""
from __future__ import annotations

import sys

import usb.core

VID, PID = 0x258A, 0x002F
INTERFACES = (0, 1)

PAGE_NAMES = {
    0x01: "GenericDesktop", 0x02: "Simulation", 0x04: "VR",
    0x06: "GenericDevice", 0x07: "Keyboard", 0x08: "LED", 0x0C: "Consumer",
    0xFF00: "Vendor",
}


def get_report_descriptor(dev, iface):
    """Read the HID report descriptor for an interface via GET_DESCRIPTOR."""
    # HID class descriptor (type 0x21) gives the report descriptor length.
    try:
        hid = dev.ctrl_transfer(0x81, 0x06, 0x2100 | iface, iface, 9, timeout=1000)
        rpt_len = hid[7] | (hid[8] << 8)
    except Exception:
        rpt_len = 4096
    return bytes(dev.ctrl_transfer(0x81, 0x06, 0x2200 | iface, iface, rpt_len))


def decode(desc: bytes):
    """Return {report_id: sorted list of (usage_page, usage_or_range)}."""
    i, n = 0, len(desc)
    page = usage = 0
    umin = umax = None
    rid = 0
    reports = {}

    def record(u):
        reports.setdefault(rid, set()).add((page, u))

    while i < n:
        b = desc[i]
        if b == 0xFE:  # long item
            i += 3 + desc[i + 1]
            continue
        size = b & 0x03
        itype = (b >> 2) & 0x0F
        itag = (b >> 4) & 0x0F
        size = 4 if size == 3 else size
        data = desc[i + 1 : i + 1 + size] if size else b""
        val = int.from_bytes(data, "little") if data else None
        if itype == 1:  # global
            if itag == 0x0:
                page = val
            elif itag == 0x4:
                rid = val
            elif itag == 0x5:
                umin = val
            elif itag == 0x6:
                umax = val
        elif itype == 2 and itag == 0x0:  # local usage
            usage = val
        elif itype == 0 and itag == 0x8:  # input
            if umin is not None and umax is not None:
                record((umin, umax))
                umin = umax = None
            else:
                record(usage)
        i += 1 + size
    return reports


def main():
    ifaces = INTERFACES
    if "--iface" in sys.argv:
        ifaces = (int(sys.argv[sys.argv.index("--iface") + 1]),)
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        print("HATOR receiver not found (258a:002f)")
        return 1
    for iface in ifaces:
        try:
            desc = get_report_descriptor(dev, iface)
        except Exception as e:
            print(f"interface {iface}: could not read report descriptor: {e}")
            continue
        print(f"\n=== Interface {iface} HID report descriptor ({len(desc)} bytes) ===")
        print(" ".join(f"{x:02x}" for x in desc))
        print("\nInput report IDs and their usages:")
        reports = decode(desc)
        for rid in sorted(reports):
            for page, u in sorted(reports[rid]):
                pname = PAGE_NAMES.get(page, f"{page:#06x}")
                if isinstance(u, tuple):
                    print(f"  report {rid}: page={pname} usages={u[0]:#x}..{u[1]:#x}")
                else:
                    print(f"  report {rid}: page={pname} usage={u:#x} ({u})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
