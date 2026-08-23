# Design: HATOR Pulsar 2 Pro Linux Configurator

Date: 2026-08-23
Status: Approved (design gate passed)
Author: Jcode / user

## Purpose

Provide a native Linux application to configure the HATOR Pulsar 2 Pro wireless
gaming mouse (a rebrand of the LUOM G10, Holtek chipset `0x04D9:0xA09F`). The app
must let the user:

1. See the mouse battery charge.
2. Bind all buttons to arbitrary actions (macros, multimedia keys, keys, app launches).
3. Change the USB polling rate (125 / 250 / 500 / 1000 Hz).
4. Change the DPI (6 slots, up to 12800 CPI).

Everything else is optional and out of scope for the initial plan.

## Context

A reverse-engineering effort already exists: `hampta/luom-g10-config` fully decoded
the USB protocol for this exact device (same VID:PID) from USBPcap captures. The
device is write-only over USB (configuration cannot be read back), so a local state
file is used as the source of truth for applied settings.

Existing coverage (from the decoded protocol):
- DPI: 6 slots, active slot index, slot count (1-7), up to 12800 CPI.
- Polling rate: 125 / 250 / 500 / 1000 Hz.
- Lift-off distance (3 levels), key debounce (1-10/20/100 ms).
- Light modes (12 effects) and color.
- On-device button map: 8 slots (4 bytes each); buttons 1-6 are
  Left, Right, Middle, Forward, Backward, DPI. Slots 7-8 are fixed/unused.
- Decoded on-device button actions: `left`, `right`, `middle`, `forward`,
  `backward`, `dpi`, `disabled`.

Remaining gaps versus the four required capabilities:
- **Battery**: not handled anywhere in the existing tool. Must be investigated.
- **Full button binding**: only the seven on-device actions above are decoded; no
  firmware macro/multimedia codes. This is intentionally handled host-side.

## Decisions

- **Form**: GUI + CLI. The core is a clean, testable engine; a thin GTK GUI sits on
  top. The CLI is the scriptable interface to the same engine.
- **Binding model**: hybrid.
  - *On-device exposure*: write a standard host-visible action into the mouse
    firmware button map for each of the 6 buttons, so the OS can see hidden buttons
    (notably the DPI button, slot 6).
  - *Host-side freedom*: `input-remapper` binds each now-host-visible button to any
    arbitrary action. The app configures the on-device exposure step and the
    corresponding input-remapper config together.
- **Reverse-engineering scope**: minimal (Option 1). No firmware macro/multimedia
  decoding. The VM is used only to (a) confirm DPI-button exposure behavior and
  (b) confirm/capture the battery read channel if not auto-exposed by the kernel.

## Architecture

Layered Python project with an engine that knows nothing about the GUI/CLI.

```
hator/
├── engine/            # core protocol + device logic (pure Python, testable)
│   ├── __init__.py
│   ├── protocol.py     # decoded HID packet encoding (DPI, polling, buttons, light)
│   ├── device.py       # USB access via pyusb/libusb, kernel-driver detach, udev
│   ├── battery.py      # battery reader (sysfs primary, vendor-RE fallback)
│   └── state.py        # local JSON state (device is write-only; state file = truth)
├── cli.py             # `hator` command wrapping the engine
├── gui.py             # GTK desktop app on top of the engine
├── bindings.py        # input-remapper integration for host-side binding
├── udev/99-hator-pulsar2.rules   # udev rule for passwordless raw USB access
├── tests/             # unit tests for protocol encoding, state, battery
├── requirements.txt
└── README.md
```

### Component responsibilities

- **`engine/protocol.py`**: encode/decode the reverse-engineered HID protocol.
  Exposes typed operations (set DPI, set polling, set button map, set light).
  Owns the packet tables, the DPI register formula `reg = (cpi // 50) - 1`, and the
  per-packet checksum.
- **`engine/device.py`**: locate the device (`0x04D9:0xA09F`), detach kernel driver,
  set configuration, send EP3 OUT bursts and EP0 `SET_REPORT` control packets.
- **`engine/battery.py`**: read battery level. Tier 1 reads the kernel-exposed
  sysfs node `/sys/class/power_supply/hid-*-battery` (if present). Tier 2 (fallback)
  reads a vendor channel reverse-engineered in the VM via USBPcap.
- **`engine/state.py`**: persist last-applied config to `~/.config/hator/state.json`.
  Because the device is write-only, this file is the source of truth for what is
  applied, and for `--get`.
- **`cli.py`**: `hator` command wrapping the engine.
- **`gui.py`**: GTK (PyGObject) app with panels: Battery, DPI editor, Polling rate,
  Button-binding editor.
- **`bindings.py`**: write `input-remapper` presets for host-side bindings and
  coordinate them with on-device exposure.

## Data flow

```
GUI / CLI
   │
   ▼
engine (protocol + device + battery + state)
   │
   ├── on-device writes via pyusb (EP3 OUT + EP0 SET_REPORT)
   └── bindings.py → input-remapper config → host-side remap
```

A single "bind button X → action Y" operation:
1. On-device: ensure button X is set to a host-visible standard action (write to the
   firmware button map) so the OS emits a HID event for it.
2. Host-side: write the input-remapper preset mapping that host-visible event to the
   user's arbitrary action Y.

## Battery

Two-tier strategy, resolved in order at runtime:

- **Tier 1 (zero RE)**: if the mouse/dongle reports battery through the standard HID
  battery usage page, the Linux kernel auto-creates a `power_supply` node. The module
  reads capacity/status from it. This requires the mouse to be connected to the Linux
  host (currently it is in the VM).
- **Tier 2 (RE fallback)**: if no sysfs node appears, capture the battery read
  channel in the win11 VM with USBPcap (the same technique used to decode the rest of
  the protocol) and implement it in `engine/battery.py` via pyusb.

First verification milestone: connect the mouse to the Linux host and check whether
Tier 1 already works.

## Button binding (hybrid)

The GUI/CLI present a single "bind" operation per physical button.

- The engine writes the on-device action for each of the 6 physical buttons using the
  decoded standard actions. Defaults mirror the factory map:
  `left, right, middle, forward, backward, dpi`.
- To make a hidden button (e.g. DPI button, slot 6) remappable, the engine writes a
  host-visible standard action to that slot (e.g. forward/X2), so the OS begins
  emitting a HID event for it.
- `bindings.py` then maps that host-visible event to the user's chosen arbitrary
  action via `input-remapper`.
- Fallback: if the firmware cannot expose a given button at all (to be confirmed in
  the VM), the on-device action is still redefinable within the decoded action-code
  space, giving limited on-device binding even for unexposable buttons.

## GUI + CLI

- **CLI** (`hator`):
  - `hator --battery`
  - `hator --dpi <n...> [--active-dpi <i>] [--dpi-count <n>]`
  - `hator --polling <hz>` (125/250/500/1000)
  - `hator --bind btn6=<action>` (arbitrary action → on-device + input-remapper)
  - `hator --get`
  - `hator --default`
- **GUI**: GTK panels:
  - Battery indicator (level % + status, live).
  - DPI editor (per-slot values, active slot, slot count).
  - Polling-rate selector.
  - Button-binding editor (per physical button → arbitrary action).
  Uses the same engine; writes are reflected through the same code path as the CLI.

## Error handling

- **Device not found**: clear message, verify `lsusb | grep 04d9`.
- **USB permission denied**: print the udev rule path and instruct applying
  `udev/99-hator-pulsar2.rules`.
- **Write-only device**: document that settings cannot be read back; the local state
  file is authoritative for `--get`.
- **Battery node missing**: log that Tier 1 is unavailable and report via Tier 2 if
  implemented, else surface a clear "battery unavailable" state.

## Testing & verification

- **Unit tests** (`tests/`):
  - DPI register encoding `(cpi // 50) - 1`, clamping and multiples-of-50 validation.
  - Polling-rate and button-action packet selection.
  - Checksum correctness for control packets.
  - State persistence (save/load, defaults, backward-compat).
  - Battery sysfs node parsing (capacity, status).
  - input-remapper preset generation.
- **VM verification tasks** (win11 + USB passthrough):
  1. Confirm whether the DPI button (slot 6) emits any HID report by default.
  2. If not, write a standard action to slot 6 via the protocol and confirm the host
     then sees the press.
  3. If Tier 1 battery is absent on the Linux host, capture the battery read channel
     with USBPcap and implement Tier 2.
- **Manual hardware test**: requires moving the mouse from the VM to the Linux host;
   end-to-end DPI/polling/binding/battery validation.

## Licensing note

The decoded protocol and packet tables are adapted from `hampta/luom-g10-config`.
Before reusing, verify the upstream license and include attribution. If the license
is incompatible with this project's intent, re-derive the tables from the pcap
fixtures independently.

## Out of scope (initially)

- Firmware-level macro/multimedia decoding (deferred; host-side binding covers it).
- On-device macro persistence across machines (deferred).
- Windows/macOS support.
- Contributions to libratbag/piper (possible later, not in this plan).
