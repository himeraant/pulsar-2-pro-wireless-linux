#!/usr/bin/env python3
"""GTK GUI for the HATOR Pulsar 2 Pro configurator."""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from engine import HatorEngine
from engine.protocol import default_config, POLLING_OPTIONS
from bindings import evdev_button_for, write_preset


def build_window(engine=None):
    engine = engine or HatorEngine()
    window = Gtk.ApplicationWindow()
    window.set_title("HATOR Pulsar 2 Pro")
    window.set_default_size(420, 480)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    window.set_child(box)

    # Battery
    battery_label = Gtk.Label(label="Battery: reading...")
    box.append(battery_label)
    info = engine.read_battery()
    if info and info.get("status") != "unavailable":
        battery_label.set_label(f"Battery: {info.get('level')}% ({info.get('status')})")
    else:
        battery_label.set_label("Battery: unavailable")

    # DPI
    dpi_label = Gtk.Label(label="DPI slots: (state)")
    box.append(dpi_label)
    state = engine.get_state() or default_config()
    dpi_label.set_label(f"DPI slots: {state['cpi']}  active: slot {state['active_slot'] + 1}")

    # Polling selector
    polling_box = Gtk.Box(spacing=4)
    polling_box.append(Gtk.Label(label="Polling rate:"))
    combo = Gtk.DropDown.new_from_strings([str(h) for h in POLLING_OPTIONS])
    combo.set_selected(list(POLLING_OPTIONS).index(state["polling_rate"]))
    polling_box.append(combo)
    box.append(polling_box)

    def on_polling_change(*_):
        idx = combo.get_selected()
        hz = POLLING_OPTIONS[idx]
        engine.apply({"polling_rate": hz})

    combo.connect("notify::selected", on_polling_change)

    # Button bindings (informational here; full editor wires --bind + input-remapper)
    bind_label = Gtk.Label(label=f"Button map: {state['button_map']}")
    box.append(bind_label)

    return window


def run():
    from gi.repository import Gtk as _Gtk
    app = _Gtk.Application()
    def on_activate(a):
        win = build_window()
        win.connect("close-request", lambda *_: a.quit())
        win.present()
    app.connect("activate", on_activate)
    app.run()


if __name__ == "__main__":
    run()
