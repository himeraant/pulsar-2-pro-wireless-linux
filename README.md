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
# Ubuntu/Debian
sudo apt-get install libusb-1.0-0-dev
sudo apt-get install gir1.2-gtk-4.0 libgirepository1.0-dev

# Fedora/RHEL
sudo dnf install libusb-devel
sudo dnf install gtk4-devel gobject-introspection-devel

# Arch
sudo pacman -S libusb gtk4 gobject-introspection
```

### Python Package Installation

Clone the repository and install in development mode:

```bash
git clone https://github.com/yourusername/hator-port.git
cd hator-port
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `requirements.txt` includes:
- `pyusb>=1.2` — USB communication library
- `pytest>=7.0` — Testing framework

PyGObject (Python GTK4 bindings) must be installed as a system package, not via pip. See platform-specific instructions above.

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

View DPI profiles:

```bash
hator --dpi-count
# Output: Available DPI profiles: 5

hator --dpi
# Output: DPI profiles: [400, 800, 1600, 3200, 6400]
```

Set active DPI:

```bash
hator --active-dpi 3200
```

#### Polling Rate

Check current polling rate:

```bash
hator --polling
# Output: Polling rate: 1000 Hz

hator --polling 500
# Set polling rate to 500 Hz
```

#### Button Binding

View button mapping:

```bash
hator --get
# Output: Current bindings...
```

Bind a mouse button to an action:

```bash
hator --bind BTN_SIDE keyboard:Return
hator --bind BTN_EXTRA mouse:MiddleClick
```

Reset to defaults:

```bash
hator --default
```

### GUI Interface

A graphical configuration tool is available for visual management of all settings. (GUI implementation: see Task 9.)

## Architecture

### Hybrid Binding Model

Button binding operates on two layers:

1. **On-Device Exposure** — The mouse exposes up to 20 button slots via USB protocol. CLI bindings directly configure these slots.
2. **input-remapper Integration** — For advanced remapping (e.g., multi-key sequences), bindings are registered in input-remapper's configuration, allowing Linux to intercept and remap events system-wide.

This hybrid approach gives you both immediate on-device configuration and the flexibility of system-wide input transformation.

### Battery Monitoring Strategy

Battery level is retrieved via a two-tier strategy:

**Tier 1 (sysfs)** — Attempts to read from standard Linux power supply interface (`/sys/class/power_supply/`). This is preferred when available.

**Tier 2 (Stub)** — Falls back to USB protocol polling if sysfs fails. This stub implementation provides basic battery data when kernel drivers are unavailable.

### Write-Only Caveat

The mouse USB interface is **write-only** for most settings. Configuration changes are written to the device, but the device does not report the current state back over USB. To preserve state across sessions, the configurator stores settings in `~/.config/hator/state.json`. This ensures your bindings, DPI, and polling settings persist even after power-off.

## Attribution

The HATOR Pulsar 2 Pro USB protocol was decoded based on research by [hampta/luom-g10-config](https://github.com/hampta/luom-g10-config). We thank the original authors for reverse-engineering the protocol specification that made this Linux port possible.

## License

[Your License Here]

## Contributing

Contributions are welcome. Please open issues and pull requests on the project repository.
