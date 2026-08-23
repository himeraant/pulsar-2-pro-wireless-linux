#!/usr/bin/env python3
"""hator: CLI for configuring the HATOR Pulsar 2 Pro wireless mouse."""
import argparse
import sys

from engine import HatorEngine
from engine.protocol import default_config, POLLING_OPTIONS
from bindings import evdev_button_for, write_preset


def _print_battery(engine):
    info = engine.read_battery()
    if not info or info.get("status") == "unavailable":
        print("Battery: unavailable (no sysfs node; Tier 2 not yet implemented)")
        return
    level = info.get("level")
    print(f"Battery: {level if level is not None else '?'}%  ({info.get('status')})")


def _cmd_bind(engine, args):
    cfg = engine.get_state() or default_config()
    try:
        physical_idx = int(args.bind_btn) - 1
    except (ValueError, TypeError):
        print(f"Invalid button number: {args.bind_btn}", file=sys.stderr)
        return 2
    # On-device exposure: assign a host-visible standard action to this slot.
    mapping = {0: "left", 1: "right", 2: "middle", 3: "forward", 4: "backward", 5: "forward"}
    while len(cfg["button_map"]) < 6:
        cfg["button_map"].append(default_config()["button_map"][len(cfg["button_map"])])
    cfg["button_map"][physical_idx] = mapping[physical_idx]
    engine.apply(cfg)
    evdev = evdev_button_for(physical_idx)
    write_preset(args.device_name, evdev, args.bind_action)
    print(f"Bound button {args.bind_btn} to {args.bind_action} (on-device + input-remapper)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="HATOR Pulsar 2 Pro configurator")
    parser.add_argument("--battery", action="store_true", help="Show battery charge")
    parser.add_argument("--dpi", nargs="+", type=int, metavar="CPI", help="Set DPI slots")
    parser.add_argument("--active-dpi", type=int, metavar="IDX", help="Active DPI slot index 0-6")
    parser.add_argument("--dpi-count", type=int, metavar="N", help="Active DPI slot count 1-7")
    parser.add_argument("--polling", type=int, metavar="HZ", choices=list(POLLING_OPTIONS),
                        help="Polling rate: 125/250/500/1000")
    parser.add_argument("--bind", nargs=2, metavar=("BTN", "ACTION"),
                        help="Bind a physical button (1-6) to an action (e.g. --bind 6 KEY_PLAYPAUSE)")
    parser.add_argument("--device-name", default="HATOR Mouse", help="input-remapper device name")
    parser.add_argument("--get", action="store_true", help="Show last applied config")
    parser.add_argument("--default", action="store_true", help="Apply factory defaults")
    args = parser.parse_args(argv)

    engine = HatorEngine()
    try:
        if args.battery:
            _print_battery(engine)
            return 0
        if args.get:
            state = engine.get_state() or default_config()
            print(f"Polling rate : {state['polling_rate']} Hz")
            print(f"DPI slots    : {state['cpi']}")
            print(f"Active DPI   : slot {state['active_slot'] + 1}")
            print(f"Button map   : {state['button_map']}")
            return 0
        if args.default:
            engine.apply_defaults()
            print("Applied factory defaults.")
            return 0
        if args.bind:
            return _cmd_bind(engine, args)

        cfg = default_config()
        changed = False
        if args.dpi is not None:
            cfg["cpi"] = args.dpi
            changed = True
        if args.active_dpi is not None:
            cfg["active_slot"] = args.active_dpi
            changed = True
        if args.dpi_count is not None:
            cfg["dpi_count"] = args.dpi_count
            changed = True
        if args.polling is not None:
            cfg["polling_rate"] = args.polling
            changed = True
        if not changed:
            parser.print_help()
            return 1
        engine.apply(cfg)
        print("Configuration applied.")
        return 0
    finally:
        # HatorDevice.close is owned by the engine; no-op here for engine lifecycle.
        pass


if __name__ == "__main__":
    sys.exit(main())
