# Sinowealth 258a:002f — USB Protocol Capture Guide

The wireless HATOR Pulsar 2 Pro uses a **SINOWEALTH 2.4G receiver** (`258a:002f`),
not the Holtek `04d9:a09f` device used by the wired LUOM G10. The current
`engine/protocol.py` is a placeholder for the *wrong* device; the Sinowealth
configuration protocol must be reverse-engineered from captures before the
configurator can talk to your mouse. This guide is that reverse-engineering
step. The architecture (CLI, GUI, battery, state, bindings, device layer) is
already in place and only `engine/protocol.py` + the device id need replacing
once the captures are decoded.

## Goal

Capture enough traffic from the official HATOR Windows app (running in a win11
VM with USB passthrough of the `258a:002f` receiver) to derive, for the
Sinowealth protocol:

1. Battery read (level + charge status) — the #1 priority.
2. DPI set (slot values, active slot, slot count).
3. Polling-rate set (125 / 250 / 500 / 1000 Hz).
4. Button remap (physical button -> action).
5. (Optional, later) macro / multimedia bindings for on-device persistence.

## Environment

- Windows 11 VM with the Sinowealth receiver passed through (the mouse talks to
  the host over it).
- Official HATOR Pulsar 2 Pro app installed in the VM.
- [USBPcap](https://desowin.org/usbpcap/) (or Wireshark's USBPcap feature)
  installed in the VM.

## Capture procedure

1. In the VM, confirm the receiver is attached: Device Manager should show a
   "SINOWEALTH 2.4G Wireless Receiver" (VID 258a, PID 002f).
2. Start a USBPcap capture on the filter matching `\\.\USBPcap` device for the
   receiver. In Wireshark: select "USBPcap1" etc. and start capturing.
3. Perform each scenario, one capture per scenario, pausing/stopping between so
   the operations stay easy to separate:
   - **Battery read:** open the app's battery page. Watch for the app polling
     periodically — capture a solid ~30 seconds including a battery refresh and,
     ideally, a level change (unplug charging state, or note the number).
   - **DPI change:** change the DPI value(s) and active slot in the app; also
     change the number of active slots.
   - **Polling change:** switch 125 -> 250 -> 500 -> 1000 Hz.
   - **Button remap:** rebind one physical button to another standard function.
   - **Macro (optional):** create and assign a macro to a button.
4. Save each capture as a separate `.pcapng` file with a descriptive name
   (`battery.pcapng`, `dpi.pcapng`, `polling.pcapng`, `remap.pcapng`, `macro.pcapng`).

## What to look for when analyzing

For a wireless receiver the interesting traffic is normally:

- **Control transfers** (`SET_REPORT` 0x21/0x09, `GET_REPORT` 0xA1/0x01, and
  vendor requests `0x40`/`0xC0` class) — the config commands and the battery read.
- **Interrupt/OUT writes** to an endpoint — larger config payloads (DPI tables,
  button maps, LED/lighting).
- **IN reports** — HID reports carrying battery percentage and button state.

For each scenario, diff the packets before/after the action to isolate the
bytes that encode the change (the same technique that decoded the Holtek
protocol). Record, for each operation: the `bmRequestType`, `bRequest`,
`wValue`, `wIndex`, `wLength`, and the exact payload bytes.

## Delivering captures

Place the `.pcapng` files somewhere accessible (e.g. `pcap/` in this repo or a
shared folder) and tell me which scenario each covers. From them I will:

- Reimplement `engine/protocol.py` with the Sinowealth packet encoding.
- Update `engine/device.py`'s VID/PID (already `258a:002f`).
- Implement the battery read channel (Tier 2) if no sysfs node exists.

## After decoding

- The CLI/GUI will then configure the real mouse (no further app changes needed).
- Run `docs/hardware-verification.md` on the Linux host to validate DPI /
  polling / battery / button-exposure end-to-end.

## Reference

- Design/spec: `docs/superpowers/specs/2026-08-23-hator-pulsar2-linux-port-design.md`
- Plan: `docs/superpowers/plans/2026-08-23-hator-pulsar2-linux-port.md`
