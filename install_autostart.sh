#!/usr/bin/env bash
# Install autostart for the HATOR media daemon:
#   - udev rules granting /dev/uinput + receiver USB access
#   - a udev rule that starts the media daemon (system service) on device plug
#
# Usage: sudo ./install_autostart.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="${REPO}/.venv/bin/python"
MEDIA="${REPO}/media.py"

if [ ! -x "$VENV_PY" ]; then
  echo "error: $VENV_PY not found; create the venv first" >&2
  exit 1
fi

# 1. udev rules: access (uinput + receiver USB) and the systemd trigger.
echo ">> Installing udev rules"
install -m 0644 "$REPO/udev/99-hator-uinput.rules" /etc/udev/rules.d/99-hator-uinput.rules
install -m 0644 "$REPO/udev/99-hator-media.rules"   /etc/udev/rules.d/99-hator-media.rules
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --subsystem-match=uinput --subsystem-match=hidraw || true

# 2. Install the systemd system service (runs as root, started by udev).
echo ">> Installing systemd service"
sed -e "s|@PYTHON@|$VENV_PY|g" -e "s|@MEDIA@|$MEDIA|g" \
  "$REPO/systemd/hator-media.service.template" > /etc/systemd/system/hator-media.service
systemctl daemon-reload

# Start it now if the receiver is present.
if lsusb -d 258a:002f >/dev/null 2>&1; then
  systemctl start hator-media.service
fi

echo
echo ">> Installed. The daemon starts automatically when the receiver is plugged in."
echo "   Start now:  systemctl start hator-media"
echo "   Status:     systemctl status hator-media"
echo "   Logs:       journalctl -u hator-media -f"
