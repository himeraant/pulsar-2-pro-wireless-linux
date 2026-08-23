#!/usr/bin/env python3
"""Parse a USBPcap pcapng file, extracting Enhanced Packet Blocks.

Prints each USB packet's index (1-based, matching Wireshark frame number),
timestamp (seconds, using IDB tsresol), and a hexdump of the first N bytes of
the raw packet data (the USBPCAP header + payload).
"""
import struct
import sys


def parse_pcapng(path, max_packets=None, dump=48):
    with open(path, "rb") as f:
        data = f.read()

    off = 0
    packets = []
    tsresol = 6  # default 10^-6 seconds
    pkt_index = 0

    while off + 12 <= len(data):
        block_type = struct.unpack_from("<I", data, off)[0]
        block_len = struct.unpack_from("<I", data, off + 4)[0]
        if block_len < 12 or off + block_len > len(data):
            print(f"[stop] bad block length {block_len} at {off}")
            break
        body = data[off + 8 : off + block_len - 4]  # between len fields

        if block_type == 0x0A0D0D0A:  # SHB
            pass
        elif block_type == 0x00000001:  # IDB
            # linktype @0 (2), reserved @2, snaplen @4
            linktype = struct.unpack_from("<H", body, 0)[0]
            print(f"IDB: linktype={linktype}")
            # options: look for if_tsresol (code 9)
            o = 8
            while o + 4 <= len(body):
                code, olen = struct.unpack_from("<HH", body, o)
                if code == 0:
                    break
                if code == 9:  # if_tsresol
                    b = body[o + 4]
                    if b & 0x80:
                        tsresol = 2 ** -(b & 0x7F)
                    else:
                        tsresol = 10 ** b
                o += 4 + ((olen + 3) & ~3)
        elif block_type == 0x00000006:  # EPB
            iface, tshi, tslo, caplen, origlen = struct.unpack_from(
                "<IIIII", body, 0
            )
            ts = (tshi << 32) | tslo
            ts_sec = ts * tsresol
            pkt_data = body[20 : 20 + caplen]
            pkt_index += 1
            if max_packets and pkt_index > max_packets:
                break
            packets.append((pkt_index, ts_sec, pkt_data))
            if dump:
                print(f"\n--- pkt {pkt_index} ts={ts_sec:.6f} caplen={caplen} ---")
                hexl = pkt_data[:dump].hex()
                print(" ".join(hexl[i : i + 2] for i in range(0, len(hexl), 2)))
        elif block_type == 0x00000003:  # SPB (old)
            caplen, origlen = struct.unpack_from("<II", body, 0)
            pkt_data = body[8 : 8 + caplen]
            pkt_index += 1
            packets.append((pkt_index, 0.0, pkt_data))
            if dump:
                print(f"\n--- pkt {pkt_index} (SPB) caplen={caplen} ---")
        # else: ignore NRB etc.
        off += block_len

    print(f"\n==== total packets: {pkt_index} ====")
    return packets


if __name__ == "__main__":
    path = sys.argv[1]
    max_pkts = int(sys.argv[2]) if len(sys.argv) > 2 else None
    dump = int(sys.argv[3]) if len(sys.argv) > 3 else 48
    parse_pcapng(path, max_pkts, dump)
