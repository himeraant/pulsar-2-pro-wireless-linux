#!/usr/bin/env python3
"""hator: CLI for configuring the HATOR Pulsar 2 Pro wireless mouse."""
import argparse
import sys

from engine import HatorEngine
from engine.protocol import default_config, POLLING_OPTIONS, BUTTON_ACTIONS
from engine.state import save_state
from bindings import (
    BindError,
    set_binding,
    unbind,
    list_bindings,
    find_origin_hash,
)
import shutil
import media


def _print_battery(engine):
    info = engine.read_battery()
    if not info or info.get("status") == "unavailable":
        print("Battery: unavailable (no sysfs node and receiver busy/unreachable)")
        return
    level = info.get("level")
    print(f"Battery: {level if level is not None else '?'}%  ({info.get('status')})")


def _resolve_origin_hash(engine, args) -> tuple[str, str] | None:
    """Return (device_name, origin_hash), resolving from arg -> state -> evdev."""
    origin = args.origin_hash or (engine.get_state() or {}).get("origin_hash")
    device = args.device_name or (engine.get_state() or {}).get("device_name")
    if not origin:
        found = find_origin_hash(device)
        if found:
            name, origin = found
            if not device or name != device:
                device = name
    if origin and device:
        # persist for next time so the user only does this once
        try:
            st = engine.get_state() or default_config()
            st["origin_hash"] = origin
            st["device_name"] = device
            save_state(st, engine.state_path)
        except Exception:
            pass
        return device, origin
    if origin:
        # have the hash but no known device name; use the requested one
        return args.device_name or "HATOR Mouse", origin
    return None


def _input_remapper_available() -> bool:
    """True if an input-remapper binary or service is installed."""
    for name in ("input-remapper", "input-remapper-service", "input-remapper-control"):
        if shutil.which(name):
            return True
    return False


def _cmd_bind(engine, args):
    try:
        btn_num = int(args.bind[0])
        bind_action = args.bind[1]
    except (ValueError, TypeError):
        print(f"Invalid button number: {args.bind[0]}", file=sys.stderr)
        return 2
    if not 1 <= btn_num <= 6:
        print(f"Invalid button number: {btn_num}", file=sys.stderr)
        return 2
    # Preferred: on-device remap for device-native actions (works for button 6).
    if bind_action.lower() in BUTTON_ACTIONS:
        action = bind_action.lower()
        try:
            engine.apply_button(btn_num, action)
        except Exception as e:
            print(f"error: could not write on-device button map: {e}", file=sys.stderr)
            return 2
        print(f"Bound button {btn_num} to on-device action '{action}'.")
        return 0
    # Fallback: host-side input-remapper for arbitrary keys on buttons 1-5.
    if btn_num == 6:
        print(
            "error: button 6 (DPI) has no host-visible event, so it can only be "
            "set to an on-device action. Use one of: "
            + ", ".join(sorted(BUTTON_ACTIONS)),
            file=sys.stderr,
        )
        return 2
    resolved = _resolve_origin_hash(engine, args)
    if resolved is None:
        print(
            "error: could not determine the device origin_hash (needed for a "
            "working input-remapper preset). Install python-evdev so it can be "
            "auto-detected, or pass --origin-hash <hash> from input-remapper.",
            file=sys.stderr,
        )
        return 2
    device_name, origin_hash = resolved
    try:
        path = set_binding(
            device_name, btn_num - 1, bind_action, origin_hash,
            name=f"Button {btn_num} -> {bind_action}",
        )
    except BindError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"Bound button {btn_num} to {bind_action} via input-remapper ({path})")
    print(f"  device: {device_name}  origin_hash: {origin_hash}")
    if not _input_remapper_available():
        print(
            "  warning: input-remapper is not installed/running, so this preset "
            "is not applied yet. Install it (Arch: yay -S input-remapper), then "
            "start it and enable the 'hator' preset for the device (or set it in "
            "autoload).",
            file=sys.stderr,
        )
    return 0


def _cmd_unbind(engine, args):
    try:
        btn_num = int(args.unbind)
    except (ValueError, TypeError):
        print(f"Invalid button number: {args.unbind}", file=sys.stderr)
        return 2
    if not 1 <= btn_num <= 6:
        print(f"Invalid button number: {btn_num}", file=sys.stderr)
        return 2
    device = args.device_name or (engine.get_state() or {}).get("device_name") or "HATOR Mouse"
    try:
        removed = unbind(device, btn_num - 1)
    except BindError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if removed:
        print(f"Unbound button {btn_num}.")
    else:
        print(f"Button {btn_num} had no binding to remove.")
    return 0


def _cmd_list_binds(engine, args):
    device = args.device_name or (engine.get_state() or {}).get("device_name") or "HATOR Mouse"
    binds = list_bindings(device)
    if not binds:
        print(f"No bindings for {device!r}.")
        return 0
    print(f"Bindings for {device!r}:")
    for b in binds:
        label = f"Button {b['btn']}" if b["btn"] else b["evdev"]
        print(f"  {label:<12} -> {b['action']}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="HATOR Pulsar 2 Pro configurator")
    parser.add_argument("--battery", action="store_true", help="Show battery charge")
    parser.add_argument("--dpi", nargs="+", type=int, metavar="CPI", help="Set DPI slots")
    parser.add_argument("--active-dpi", type=int, metavar="N", help="Number of active DPI slots 1-7 (same as --dpi-count)")
    parser.add_argument("--dpi-count", type=int, metavar="N", help="Number of active DPI slots 1-7")
    parser.add_argument("--polling", type=int, metavar="HZ", choices=list(POLLING_OPTIONS),
                        help="Polling rate: 125/250/500/1000")
    parser.add_argument("--bind", nargs=2, metavar=("BTN", "ACTION"),
                        help="Bind a physical button (1-5) to an action (e.g. --bind 4 KEY_PLAYPAUSE)")
    parser.add_argument("--unbind", type=int, metavar="BTN",
                        help="Remove the binding for a physical button (1-5)")
    parser.add_argument("--list-binds", action="store_true",
                        help="Show the current input-remapper bindings")
    parser.add_argument("--media-daemon", action="store_true",
                        help="Run the media-key daemon (reads raw hidraw, injects media keys via uinput)")
    parser.add_argument("--media-dev", default=None,
                        help="hidraw node for --media-daemon (e.g. /dev/hidraw3; auto-detected if omitted)")
    parser.add_argument("--media-debug", action="store_true",
                        help="Print raw hidraw reports in --media-daemon")
    parser.add_argument("--origin-hash", default=None,
                        help="input-remapper device origin_hash (auto-detected if python-evdev is installed)")
    parser.add_argument("--device-name", default=None, help="input-remapper device name (default: auto-detect)")
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
            print(f"DPI slot count: {state.get('dpi_count', 7)} (DPI button cycles these)")
            print(f"Button map   : {state['button_map']}")
            return 0
        if args.default:
            engine.apply_defaults()
            print("Applied factory defaults.")
            return 0
        if args.bind:
            return _cmd_bind(engine, args)
        if args.unbind is not None:
            return _cmd_unbind(engine, args)
        if args.list_binds:
            return _cmd_list_binds(engine, args)
        if args.media_daemon:
            return media.run(args.media_dev, debug=args.media_debug)

        cfg = default_config()
        changed = False
        if args.dpi is not None:
            cfg["cpi"] = args.dpi
            changed = True
        if args.active_dpi is not None or args.dpi_count is not None:
            count = args.dpi_count if args.dpi_count is not None else args.active_dpi
            if not 1 <= count <= 7:
                print(f"error: DPI slot count must be 1-7, got {count}", file=sys.stderr)
                return 2
            cfg["dpi_count"] = count
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
    except NotImplementedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    finally:
        engine.close()


if __name__ == "__main__":
    sys.exit(main())
