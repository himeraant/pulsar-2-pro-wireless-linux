# HATOR Pulsar 2 Pro — Real-Hardware Setup & Verification

This is the step-by-step guide for taking the configurator from "unit-tested" to
"verified on the actual mouse." The automated test suite (36 tests) validates the
protocol encoding, USB write sequence, state persistence, CLI wiring, and GUI
construction, but it never talks to a physical device. Everything in this file
requires the mouse and a Linux host.

Two reverse-engineering questions are intentionally left open and are answered
here (see sections 5 and 6). The protocol constants are software-verified only
until a hardware pass confirms them.

---

## 1. Prerequisites on the Linux host

```bash
# System packages (Debian/Ubuntu/Mint shown; adapt for your distro)
sudo apt install libusb-1.0-0 python3-gi gir1.2-gtk-4.0 input-remapper
```

```bash
# Python deps. --system-site-packages makes the system-installed GTK
# bindings (`gi`, e.g. Arch `python-gobject`) visible inside the venv,
# so the GUI can import it.
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt        # pyusb, pytest
```

Install the udev rule so you can talk to the mouse without `sudo`:

```bash
sudo cp udev/99-hator-pulsar2.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
# add yourself to the plugdev group if needed, then re-login
sudo usermod -aG plugdev $USER
```

## 2. Connect the mouse and confirm it enumerates

Plug the receiver into the host and confirm the device is visible:

```bash
lsusb | grep 04d9
# expected: ... Holtek Semiconductor, Inc. ...  (04d9:a09f)
```

If it does not appear, the receiver may be bound to the VM or another host; free
it before continuing.

## 3. Battery (your #1 priority — Tier 1 sysfs first)

Battery is read from the kernel first; no reverse-engineering is needed if the
mouse exposes a standard HID battery node.

```bash
ls /sys/class/power_supply/ | grep -i battery
# if a node like hid-xxxx-battery exists, Tier 1 works:
hator --battery
```

- If a node appears and `hator --battery` prints a level → **done, no VM work
  needed for battery**.
- If no `hid-*-battery` node exists → Tier 1 is unavailable. Battery then needs
  Tier 2 (section 6) via the VM capture.

## 4. Verify DPI, polling rate, and state

Set a DPI + polling rate and confirm they stick:

```bash
hator --dpi 400 800 1600 3200 6400 12800 --active-dpi 1
hator --polling 1000
hator --get        # reads the local state file (device is write-only)
```

Confirm behaviorally: move the mouse and feel the sensitivity change; a fast
scrolling tool or the OS input settings can confirm the polling/report rate.
Note the device is write-only — `hator --get` reports what you last wrote, not a
device read-back.

## 5. DPI-button (button 6) exposure — the key open question

The host may not see the DPI button by default (the firmware handles it onboard).
This is why host-side remapping alone is insufficient and on-device exposure is
the gateway.

1. Watch for input events while you press the DPI button:
   ```bash
   sudo evtest        # select the mouse; press the DPI button and watch
   # or:  libinput debug-events
   ```
   Note whether any event fires for the DPI button.

2. Expose it on-device, then re-test:
   ```bash
   hator --bind 6 KEY_ENTER     # writes a host-visible action to slot 6
   ```
   Re-run `evtest`/`libinput debug-events` and press the DPI button again. It
   should now emit an event.

3. If it becomes visible → the hybrid model works for the DPI button. If it
   still produces no event, the firmware cannot expose slot 6; fall back to
   on-device-only rebinding within the decoded action space and note this as a
   limitation.

## 6. Validate input-remapper binding end-to-end

The generated preset uses input-remapper 2.x's JSON schema, but the
`target_uinput` inference (heuristic) and evdev key-name validity have not been
checked against a live install.

```bash
# after a bind, the preset is written to:
# ~/.config/input-remapper-2/presets/<device>/hator.json
hator --bind 4 KEY_ENTER
```

Start input-remapper, confirm it loads the preset, and that pressing button 4
emits the mapped action. If input-remapper rejects the preset, capture its error
and adjust `bindings.py`'s schema/`target_uinput` inference accordingly.

## 7. Tier 2 battery (only if section 3 found no sysfs node)

In the win11 VM with USB passthrough:

1. Install [USBPcap](https://desowin.org/usbpcap/).
2. Capture the traffic while the official HATOR app shows the battery level (and
   while the level changes).
3. Identify the read channel (likely a vendor HID input/feature report carrying
   the percentage).
4. Implement it in `engine/battery.py` replacing the `battery_unavailable()`
   stub, then re-run the battery tests.

## 8. Optional / later: on-device macros & multimedia

The current design binds arbitrary actions host-side (input-remapper). If you
later want bindings to persist on-device across machines (like the official app),
capture the official app writing macro/multimedia bindings in the VM (USBPcap,
same technique) and decode those firmware action codes into `protocol.py`.
Not required for the initial scope.

## Reference

- Design/spec: `docs/superpowers/specs/2026-08-23-hator-pulsar2-linux-port-design.md`
- Implementation plan (incl. the VM/hardware verification tasks it derives
  from): `docs/superpowers/plans/2026-08-23-hator-pulsar2-linux-port.md`
