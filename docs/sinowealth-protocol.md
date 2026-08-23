# Sinowealth 258a:002f — Decoded Protocol

Reverse-engineered from USBPcap captures of the official HATOR app in a win11 VM
(`pcap/*.pcapng`). Decoder tool: `tools/decode_usbpcap.py`.

## Transport

The receiver exposes a HID interface (interface 1). Configuration and battery
use **HID feature reports over control transfers** to the receiver:

- Control OUT (host→device): `bmRequestType=0x21, bRequest=0x09 (SET_REPORT), wValue=0x0300|reportID, wIndex=0x0001`.
- Control IN (device→host): `bmRequestType=0xA1, bRequest=0x01 (GET_REPORT), wValue=0x0300|reportID, wIndex=0x0001`.

Two feature reports matter:

| Report ID | Size | Purpose |
|-----------|------|---------|
| `0x05` | 8 bytes | Small commands / battery poll |
| `0x08` | 520 bytes | Full configuration blob (DPI, polling, buttons) |

In USBPcap each control transfer appears as: a `SETUP` packet (contains the
setup + any data OUT), then a `COMPLETE` packet (carries data IN). The header
(`USBPCAP_BUFFER_PACKET_HEADER`, 27 bytes; +1 stage byte for control) is decoded
in `tools/decode_usbpcap.py`.

## Common command preamble (used before every config write)

Every read/write starts with a small exchange on report `0x05`:

1. `SET_REPORT 0x05` → `05 80 00 00 00 00 00 00` (command `0x80`)
2. `GET_REPORT 0x05` → `05 80 01 01 00 00 00 00` (ack)
3. `SET_REPORT 0x05` → `05 21 00 00 00 00 00 00` (command `0x21`)
4. `GET_REPORT 0x08` (520 bytes) → the current config blob (used for
   read-modify-write), or proceed straight to a write.

Then the app writes the modified config blob(s) via `SET_REPORT 0x08`.

## Battery

Periodic poll (the app reads it continuously):

- `SET_REPORT 0x05` → `05 90 00 00 00 00 00 00` (command `0x90` = read battery)
- `GET_REPORT 0x05` → `05 90 11 XX 00 00 00 00`

**Battery percentage = response byte 3 (`XX`).** Observed: `0x35`=53%,
`0x36`=54%, `0x37`=55%, `0x41`=65% (charging), `0x43`=67% (charging).
The battery read needs no preamble; it is just the `0x90` command.

## Configuration blob (report 0x08)

The 520-byte blob structure (byte offsets within the data after the 8-byte
`08 21 00 92 00 00 00 00` header):

| Offset | Size | Meaning |
|--------|------|---------|
| 8 | 3 | fixed `64 11 <polling>` |
| 10 | 1 | **Polling rate**: `0x01`=125Hz, `0x02`=250Hz, `0x03`=500Hz, `0x04`=1000Hz |
| 11 | 2 | fixed `27 00` |
| 13 | 2 | DPI slot 1 |
| 15 | 2 | DPI slot 2 |
| 17 | 2 | DPI slot 3 |
| 19 | 2 | DPI slot 4 |
| 21 | 2 | DPI slot 5 |
| 23 | 2 | DPI slot 6 |
| 25 | 2 | DPI slot 7 |

**DPI encoding:** `reg = (cpi // 100) - 1`; `cpi = (reg + 1) * 100`.
Verified: 11500→`0x72`(114), 15500→`0x9a`(154), 1400→`0x0d`(13),
100→`0x00`(0), 1500→`0x0e`(14). DPI is in steps of 100, max ~16000.

**Polling encoding:** single byte at offset 10, 1..4 for 125..1000 Hz.

The DPI slots and polling share this one blob. To change any of them: read the
blob, modify the relevant bytes, write it back.

## Button mapping (command `0x22` blob)

The button map is a second 520-byte blob written with command `0x22`
(`08 22 00 50 00 00 00 00 ...`). It holds per-button entries of the form
`TYPE VALUE P1 P2`:

| TYPE | Meaning | VALUE examples |
|------|---------|----------------|
| `0x11` | mouse button action | `01` left, `02` right, `04` middle, `08` back, `10` forward |
| `0x12` | scroll | `01` scroll up |
| `0x41` | DPI | `01` DPI up, `02` DPI down |
| `0x31` | macro (variable length) | `31 01 32 03` = triple-click |

The first five entries map physical buttons Left/Right/Middle/Backward/Forward
(bits `01 02 04 08 10`); a sixth entry is the DPI button. Button remap changes
the `VALUE`/`TYPE` of the corresponding entry. (Exact physical-button-to-entry
ordering and the full macro/multimedia action table still need pinning down from
the `macro.pcapng` capture.)

## Config write sequence

For a DPI or polling change, the app performs (verified in `DPI.pcapng`):

1. Preamble: `05 80 ...`, ack, `05 21 ...` (above).
2. `GET_REPORT 0x08` → read current 520-byte blob.
3. `SET_REPORT 0x08` command `0x21` → write blob with modified DPI/polling.
4. `SET_REPORT 0x08` command `0x22` → write the button-map blob.

For a battery read, only the `0x90` exchange is needed (no preamble/write).

## Still to decode

- Exact physical-button → entry index mapping and all action codes for button
  remap (including macros/multimedia from `macro.pcapng`).
- Whether changing buttons alone skips the `0x21` write.

## Captures (`pcap/`)

`battery.pcapng`, `DPI.pcapng`, `polling.pcapng`, `remap.pcapng`,
`macro.pcapng`. The user's `pcap/notes` file lists frame numbers for each
operation (mouse is device `1.2`).
