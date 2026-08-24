# HATOR Pulsar 2 Pro Linux Configurator

A Python-based CLI and GUI tool for configuring the HATOR Pulsar 2 Pro gaming mouse on Linux. Control DPI settings, button bindings, polling rate, and monitor battery status.

## Features

The configurator exposes four core capabilities:

1. **Battery Monitoring** — Retrieve current battery level via hybrid sysfs/stub strategy
2. **Button Binding** — Remap mouse buttons to keyboard/mouse actions via input-remapper integration
3. **Polling Rate Control** — Adjust USB polling frequency for latency tuning
4. **DPI Settings** — Configure and activate multiple DPI profiles on-device

## Installation

### Prerequisites

Install system dependencies:

```bash
# Ubuntu/Debian  (python3-gi provides the Python `gi` module)
sudo apt-get install libusb-1.0-0 python3-gi gir1.2-gtk-4.0

# Fedora/RHEL  (python3-gobject provides the Python `gi` module)
sudo dnf install libusb python3-gobject gtk4

# Arch  (python-gobject provides the Python `gi` module)
sudo pacman -S libusb python-gobject gtk4
```

### Python Package Installation

Clone the repository and install in development mode:

```bash
git clone <this repository's URL>
cd hator-port
# --system-site-packages makes the system-installed GTK bindings (`gi`)
# visible inside the venv; without it `import gi` fails even after you
# install the system PyGObject package above.
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `requirements.txt` includes:
- `pyusb>=1.2` — USB communication library
- `pytest>=7.0` — Testing framework

`python-evdev` is an optional dependency. Install it to let `--bind`
auto-detect the device's `origin_hash`; without it you pass `--origin-hash`
explicitly (see Button Binding).

PyGObject (the Python `gi` module / GTK4 bindings) is intentionally NOT in
`requirements.txt` because it is a system package on every mainstream distro
(see the Prerequisites block above). Two consequences:

1. Install the matching system package first (e.g. `python-gobject` on Arch,
   `python3-gi` on Debian/Ubuntu, `python3-gobject` on Fedora).
2. Create the venv with `--system-site-packages` so that system `gi` is
   visible inside it. If your venv is already created without that flag,
   recreate it (`rm -rf .venv && python3 -m venv --system-site-packages .venv`)
   or run the GUI with your system Python instead of the venv's.

### udev Rule Installation

To allow unprivileged access to the mouse, install the udev rule:

```bash
sudo cp udev/99-hator-pulsar2.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

After installation, reconnect your mouse or run `sudo udevadm trigger`.

### input-remapper Integration

For button binding functionality, install input-remapper:

```bash
sudo apt-get install input-remapper  # Ubuntu/Debian
# or via your package manager on other distros
```

Ensure the input-remapper service is running:

```bash
sudo systemctl enable input-remapper
sudo systemctl start input-remapper
```

## Usage

### CLI Interface

The `hator` command provides full configurator access via command-line flags:

#### Battery Status

```bash
hator --battery
# Output: Battery: 85%
```

#### DPI Management

Set DPI slot values and active slot count:

```bash
hator --dpi 400 800 1600 3200 6400
# Sets the DPI value for each slot (space-separated CPI values)

hator --dpi-count 5
# Sets the active DPI slot count (1-7)
```

Set active DPI:

```bash
hator --active-dpi 2
# Sets the active DPI slot index (0-6), not a raw CPI value
```

To view the currently applied configuration (including DPI slots, active
slot, polling rate, and button map), use `--get`:

```bash
hator --get
```

#### Polling Rate

```bash
hator --polling 500
# Set polling rate to 500 Hz
```

`--polling` requires one of 125, 250, 500, or 1000. Use `--get` to check the
currently applied rate.

#### Button Binding

Bind a physical mouse button (1-5) to an action. The action is an evdev key
name (or an input-remapper `<macro>...</macro>` string). This writes a preset
to input-remapper so Linux remaps the event system-wide:

```bash
hator --bind 4 KEY_ENTER        # forward button -> Enter
hator --bind 5 KEY_PLAYPAUSE    # backward button -> Play/Pause
```

Multiple `--bind` calls accumulate into one preset per device (each button can
have one action). Remove or list them:

```bash
hator --unbind 4                # clear forward button
hator --list-binds              # show current bindings
```

For a mapping to actually trigger, input-remapper needs the device's
`origin_hash`. If `python-evdev` is installed, it is auto-detected from the
HATOR receiver's event node; otherwise pass it explicitly (it is shown in the
input-remapper GUI) once, and it is remembered:

```bash
hator --bind 4 KEY_ENTER --origin-hash <hash> --device-name "<evdev name>"
```

**Buttons 1-5** (left/right/middle/forward/backward) have distinct
host-visible events and are remappable. **Button 6 (the DPI button) is not**
host-remappable: it emits no standard HID button event (it only cycles DPI
slots, reported via report 0x07), so input-remapper cannot see it.

Reset to defaults:

```bash
hator --default
```

### GUI Interface

A GTK4 graphical interface ships in `gui.py`. Launch it with:

```bash
python3 gui.py
```

Currently the GUI provides:
- **Battery view** — reads and displays current battery level/status.
- **Polling control** — a dropdown to view and change the polling rate,
  wired directly to `engine.apply()`.
- **DPI and button-map views** — read-only/informational labels showing the
  currently saved DPI slots and button map. Editing DPI slots and button
  bindings is CLI-only for now (`--dpi`, `--bind`); GUI editors for these are
  a planned follow-up.

## Architecture

### Host-Side Binding Model

Button remapping is done **host-side** via input-remapper (minimal
reverse-engineering): the tool writes a JSON preset under
`~/.config/input-remapper-2/presets/<device>/hator.json` that maps a physical
button's evdev event to an output action. input-remapper's service intercepts
the event and emits the mapped action system-wide.

The preset's `input_combination` carries the device's `origin_hash` (the hash
input-remapper uses to identify the event node) so the mapping only triggers on
this mouse. Buttons 1-5 (left/right/middle/forward/backward) are remappable;
the DPI button has no distinct host event and is not.

### Battery Monitoring Strategy

Battery level is retrieved via a two-tier strategy:

**Tier 1 (sysfs)** — Attempts to read from standard Linux power supply interface (`/sys/class/power_supply/`). This is preferred when available.

**Tier 2 (Stub)** — Falls back to USB protocol polling if sysfs fails. This stub implementation provides basic battery data when kernel drivers are unavailable.

### Write-Only Caveat

The mouse USB interface is **write-only** for most settings. Configuration changes are written to the device, but the device does not report the current state back over USB. To preserve state across sessions, the configurator stores settings in `~/.config/hator/state.json`. This ensures your bindings, DPI, and polling settings persist even after power-off.

## Attribution

The HATOR Pulsar 2 Pro USB protocol was decoded based on research by [hampta/luom-g10-config](https://github.com/hampta/luom-g10-config). We thank the original authors for reverse-engineering the protocol specification that made this Linux port possible.

## License

Upstream has no explicit license. Until one is added, treat this repository
as "all rights reserved" by its authors; contact the maintainers before
redistributing.

## Contributing

Contributions are welcome. Please open issues and pull requests on the project repository.
