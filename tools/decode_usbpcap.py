#!/usr/bin/env python3
"""Decode USBPcap (linktype 249) pcapng captures for the HATOR Pulsar 2 Pro.

Decodes the 27-byte USBPCAP_BUFFER_PACKET_HEADER (control transfers append a
1-byte stage, so headerLen==28 for control). Prints frame index (== Wireshark
frame number), bus/device/endpoint/transfer/function, and the payload hex.

Usage:
  decode_usbpcap.py <file.pcapng> [--dev D] [--from N] [--to N] [--all]
"""
import struct
import sys


TRANSFER = {0: "ISO", 1: "INTERRUPT", 2: "CONTROL", 3: "BULK", 0xFE: "IRP_INFO", 0xFF: "UNKNOWN"}
STAGE = {0: "SETUP", 1: "DATA", 2: "STATUS", 3: "COMPLETE"}

URB_FUNC = {
    0x00: "SELECT_CONFIGURATION", 0x01: "SELECT_INTERFACE",
    0x02: "ABORT_PIPE", 0x08: "SYNC_RESET_PIPE_AND_CLEAR_STALL",
    0x09: "BULK_OR_INTERRUPT_TRANSFER", 0x0a: "GET_FRAME_LENGTH",
    0x0b: "CONTROL_TRANSFER", 0x0c: "GET_DESCRIPTOR_FROM_DEVICE",
    0x0d: "GET_DESCRIPTOR_FROM_ENDPOINT", 0x0e: "GET_DESCRIPTOR_FROM_INTERFACE",
    0x0f: "SET_DESCRIPTOR", 0x1b: "VENDOR_DEVICE", 0x1c: "VENDOR_INTERFACE",
    0x1d: "CLASS_INTERFACE", 0x1e: "CLASS_DEVICE",
}


def parse_pcapng(path):
    with open(path, "rb") as f:
        data = f.read()
    off = 0
    packets = []
    pkt_index = 0
    while off + 12 <= len(data):
        btype = struct.unpack_from("<I", data, off)[0]
        blen = struct.unpack_from("<I", data, off + 4)[0]
        if blen < 12 or off + blen > len(data):
            break
        body = data[off + 8 : off + blen - 4]
        if btype == 0x00000006:  # EPB
            iface, tshi, tslo, caplen, origlen = struct.unpack_from("<IIIII", body, 0)
            pkt_data = body[20 : 20 + caplen]
            pkt_index += 1
            packets.append((pkt_index, pkt_data))
        off += blen
    return packets


def decode(pkt_data):
    if len(pkt_data) < 27:
        return None
    headerLen = struct.unpack_from("<H", pkt_data, 0)[0]
    irpId = struct.unpack_from("<Q", pkt_data, 2)[0]
    status = struct.unpack_from("<I", pkt_data, 10)[0]
    function = struct.unpack_from("<H", pkt_data, 14)[0]
    info = pkt_data[16]
    bus = struct.unpack_from("<H", pkt_data, 17)[0]
    device = struct.unpack_from("<H", pkt_data, 19)[0]
    endpoint = pkt_data[21]
    transfer = pkt_data[22]
    dataLength = struct.unpack_from("<I", pkt_data, 23)[0]
    # payload starts at headerLen; control has a stage byte at headerLen-1
    payload = pkt_data[headerLen:] if headerLen <= len(pkt_data) else b""
    stage = None
    if transfer == 2 and headerLen >= 28:
        stage = pkt_data[27]
    return {
        "headerLen": headerLen, "irpId": irpId, "status": status,
        "function": function, "info": info, "bus": bus, "device": device,
        "endpoint": endpoint, "transfer": transfer, "dataLength": dataLength,
        "stage": stage, "payload": payload,
    }


def fmt_hex(b, n=None):
    h = b.hex()
    if n:
        h = h[: n * 2]
    return " ".join(h[i : i + 2] for i in range(0, len(h), 2))


def setup_decode(payload):
    if len(payload) >= 8:
        bm, br, wv, wi, wl = struct.unpack_from("<BBHHH", payload, 0)
        return f"SETUP bm=0x{bm:02x} bRequest={br} wValue=0x{wv:04x} wIndex=0x{wi:04x} wLen={wl}"
    return ""


def main():
    args = sys.argv[1:]
    path = args[0]
    dev = None
    fr = 0
    to = 10 ** 9
    show_all = False
    if "--dev" in args:
        dev = int(args[args.index("--dev") + 1])
    if "--from" in args:
        fr = int(args[args.index("--from") + 1])
    if "--to" in args:
        to = int(args[args.index("--to") + 1])
    if "--all" in args:
        show_all = True

    for idx, pkt in parse_pcapng(path):
        d = decode(pkt)
        if d is None:
            continue
        if not (fr <= idx <= to):
            continue
        if dev is not None and d["device"] != dev:
            continue
        dirchar = "I" if d["endpoint"] & 0x80 else "O"
        print(f"\n#{idx} bus.{d['bus']}.{d['device']} EP=0x{d['endpoint']:02x}{dirchar} "
              f"{TRANSFER.get(d['transfer'],'?')} func={URB_FUNC.get(d['function'],hex(d['function']))} "
              f"st={d['status']} datalen={d['dataLength']} "
              f"{('stage='+STAGE.get(d['stage'],str(d['stage']))) if d['stage'] is not None else ''}")
        if d["transfer"] == 2 and d["stage"] == 0:
            print(f"    {setup_decode(d['payload'])}")
        if show_all or d["stage"] != 2:
            print(f"    payload[{len(d['payload'])}]: {fmt_hex(d['payload'])}")


if __name__ == "__main__":
    main()
