"""Reverse-engineered HID protocol for the HATOR Pulsar 2 Pro (Holtek 04D9:A09F).

PLACEHOLDER / WRONG DEVICE: this encoding was reimplemented from the wired
Holtek LUOM G10 captures (hampta/luom-g10-config). The wireless Pulsar 2 Pro
uses a SINOWEALTH 2.4G receiver (258a:002f), whose configuration protocol is
NOT yet decoded. Until it is captured in the win11 VM (see docs/vm-capture.md)
and reimplemented here, the packets in this module must NOT be sent to the
device (engine.device raises SinowealthProtocolNotImplemented for a real
receiver). The public API shape (build_apply_sequence, default_config, etc.)
is intended to be reused by the Sinowealth implementation.
Pure module: no pyusb imports here.
"""
from __future__ import annotations

# Placeholder Holtek device id; the real receiver is 258a:002f (see engine.device).
VID = 0x04D9
PID = 0xA09F

MS_MAP = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 100]

POLLING_OPTIONS = (125, 250, 500, 1000)

DPI_MIN = 0
DPI_MAX = 12800

BUTTON_ACTIONS = {
    "left": "0100f000",
    "right": "0100f100",
    "middle": "0100f200",
    "backward": "0100f300",
    "forward": "0100f400",
    "dpi": "07000100",
    "disabled": "00000000",
}

DEFAULT_BUTTON_MAP = ["left", "right", "middle", "forward", "backward", "dpi"]
DEFAULT_CPI = [300, 500, 900, 1400, 2400, 4800]

POLLING_PACKETS = {
    125: "272b85ff30d57676",
    250: "272ba5ffd0d57676",
    500: "272bd5ff00d57676",
    1000: "272bddffe8d57676",
}

DPI_SLOT_PACKETS = {
    0: "272b6dffe8257676",
    1: "272b65ff00257676",
    2: "272b7dfff8257676",
    3: "272b75ffd0257676",
    4: "272b4dffc8257676",
    5: "272b45ffe0257676",
    6: "272b5dffd8257676",
}

DPI_COUNT_PACKETS = {
    1: "272b1dffe85576b6",
    2: "272b15ff005576b6",
    3: "272bedfff85576b6",
    4: "272be5ffd05576b6",
    5: "272bfdffc85576b6",
    6: "272bf5ffe05576b6",
    7: "272acdffd85576b6",
}

# light_mode: (ctrl5, ctrl6)
LIGHT_MODES = {
    "standard": ("272b85049842556e", "272afdffe83577f6"),
    "off": ("272b6dfff03d7676", "272afdffe83577f6"),
    "breathing": ("272b85049842556e", "272b2dff0035668e"),
    "neon": ("272b85049842556e", "272dcdffe83567f6"),
    "wave": ("272b85049842556e", "272dd5fff834f68e"),
    "key-reaction": ("272b85049842556e", "272dadffc83567f6"),
    "trailing": ("272b85049842556e", "272dadffd034f68e"),
    "drag": ("272b85049842556e", "272b35ffe0356686"),
    "slide": ("272b85049842556e", "272b0dffd8356686"),
    "yo-yo": ("272b85049842556e", "272d0dff2835e7f6"),
    "marbles": ("272b85049842556e", "272dbdff30357ff6"),
    "flying-star": ("272b85049842556e", "272d8dff40357ff6"),
}

STANDARD_COLOR_CTRL6 = "272b65ffe8357d6e"
SINGLE_COLOR = {
    "white": "272b85049842556e",
    "red": "272d4d04a03c6f8e",
    "green": "272bc5ff703d8596",
    "blue": "27293dffe843b67e",
}

# key_response index -> (b1, b2, b6, b7) for ctrl#13
KR_TABLE = [
    (0x2B, 0x8D, 0x76, 0x86),  # 0 = 1ms
    (0x2B, 0x9D, 0x76, 0x96),  # 1 = 2ms
    (0x2B, 0x95, 0x76, 0x9E),  # 2 = 3ms
    (0x2B, 0x6D, 0x76, 0xA6),  # 3 = 4ms
    (0x2B, 0x65, 0x76, 0xAE),  # 4 = 5ms
    (0x2B, 0x7D, 0x76, 0xB6),  # 5 = 6ms
    (0x2B, 0x4D, 0x76, 0xC6),  # 6 = 7ms
    (0x2B, 0x15, 0x76, 0x1E),  # 7 = 8ms
    (0x2A, 0xC5, 0x76, 0x4E),  # 8 = 9ms
    (0x2A, 0x95, 0x77, 0x9E),  # 9 = 10ms
    (0x2A, 0x55, 0x77, 0xDE),  # 10 = 20ms
    (0x2B, 0xB5, 0x76, 0x7E),  # 11 = 100ms
]

# Fixed color data packets (multicolor rainbow palette)
COLOR_PACKET_1 = ("ff000000ff000000ffffff00ff00ff00ffffff8000ffffff"
                  "0000000000000000")
COLOR_PACKET_2 = "00ff000000ffff0000ffff0000ffffff00ffffffffffffff0000000000000000"

FIXED_CTRLS = [
    "2727d5fff4e57676",      # ctrl#0
    "272bd5ffe8ed7676",      # ctrl#2
    "272a8dfff05d7636",
    "272a85ffe85d7636",
    "272d55ffe86d7876",
    "272d2dff006d7876",
    "272bf5fff85d76d6",
    "272c6d024022ccd6",
    "272bb5fff0057676",
]


def default_config() -> dict:
    return {
        "active_slot": 0,
        "cpi": list(DEFAULT_CPI),
        "button_map": list(DEFAULT_BUTTON_MAP),
        "dpi_count": 7,
        "key_response": 11,   # index -> 100ms
        "polling_rate": 1000,
        "lift_off": 2,
        "light_mode": "standard",
        "standard_color": None,
        "custom_color": None,
    }


def validate_dpi(cpi: int) -> int:
    if cpi % 50 != 0:
        raise ValueError(f"DPI must be a multiple of 50, got {cpi}")
    if cpi < DPI_MIN or cpi > DPI_MAX:
        raise ValueError(f"DPI out of range 0-{DPI_MAX}, got {cpi}")
    return cpi


def dpi_to_register(cpi: int) -> int:
    return max(0, min(255, (validate_dpi(cpi) // 50) - 1))


def register_to_dpi(reg: int) -> int:
    return (reg + 1) * 50


def _build_color_packet_1(custom_color: tuple | None) -> str:
    data = bytearray(bytes.fromhex(COLOR_PACKET_1))
    if custom_color is not None:
        r, g, b = custom_color
        for i in range(9):
            data[i * 3] = r
            data[i * 3 + 1] = g
            data[i * 3 + 2] = b
    return data.hex()


def _ctrl13_hex(key_response: int, lift_off: int) -> str:
    kr = max(0, min(11, key_response))
    b1, b2, b6, b7 = KR_TABLE[kr]
    b4 = 0x00
    if lift_off == 1:
        b2 = (b2 + 0x08) & 0xFF
        b4 = 0xE8
    return bytes([0x27, b1, b2, 0xFF, b4, 0xFD, b6, b7]).hex()


def build_apply_sequence(config: dict) -> list[tuple[str, str]]:
    """Return [("ctrl"|"out", hexstr), ...] in device write order."""
    cfg = default_config()
    cfg.update(config)

    if cfg["polling_rate"] not in POLLING_PACKETS:
        raise ValueError(f"Unsupported polling rate {cfg['polling_rate']}")

    for action in cfg["button_map"]:
        if action not in BUTTON_ACTIONS:
            raise ValueError(f"Unknown button action '{action}'")

    for cpi in cfg["cpi"]:
        validate_dpi(cpi)

    # Light ctrl5/ctrl6 selection
    ctrl5_pkt, ctrl6_pkt = LIGHT_MODES.get(cfg["light_mode"], LIGHT_MODES["standard"])
    custom = cfg.get("custom_color")
    standard_color = cfg.get("standard_color")
    if cfg["light_mode"] in ("standard", None):
        if custom is not None:
            ctrl5_pkt = LIGHT_MODES["standard"][0]
            ctrl6_pkt = STANDARD_COLOR_CTRL6
        elif standard_color:
            sc = standard_color.lower()
            if sc in SINGLE_COLOR:
                ctrl5_pkt = SINGLE_COLOR[sc]
                ctrl6_pkt = STANDARD_COLOR_CTRL6
            elif sc in ("multicolor", "rainbow"):
                pass
    elif cfg["light_mode"] == "off":
        pass

    # DPI registers packet
    dpi_regs = bytearray(32)
    dpi_regs[6] = 0xBD
    dpi_regs[7] = 0x5F
    cpi = cfg["cpi"]
    for i in range(min(len(cpi), 6)):
        dpi_regs[i] = dpi_to_register(cpi[i])
    for i in range(len(cpi), 6):
        dpi_regs[i] = dpi_regs[len(cpi) - 1] if len(cpi) > 0 else 0

    # Button map: 6 configured slots + 2 fixed unused slots
    btn_hex = ""
    for i in range(6):
        action = cfg["button_map"][i] if i < len(cfg["button_map"]) else DEFAULT_BUTTON_MAP[i]
        btn_hex += BUTTON_ACTIONS[action]
    btn_hex += "0700010007000200"

    slot = max(0, min(6, cfg["active_slot"]))
    count = max(1, min(7, cfg["dpi_count"]))

    seq: list[tuple[str, str]] = []
    # ctrl#0 fixed
    seq.append(("ctrl", FIXED_CTRLS[0]))
    # ctrl#1 LOD
    if cfg["lift_off"] == 3:
        seq.append(("ctrl", "252db5fff8eae6ee"))
    else:
        seq.append(("ctrl", "252d75fff8ea26ee"))
    # ctrl#2 fixed
    seq.append(("ctrl", FIXED_CTRLS[1]))
    # ctrl#3 polling
    seq.append(("ctrl", POLLING_PACKETS[cfg["polling_rate"]]))
    # ctrl#4 active DPI slot
    seq.append(("ctrl", DPI_SLOT_PACKETS[slot]))
    # ctrl#5 light
    seq.append(("ctrl", ctrl5_pkt))
    # ctrl#6 light params
    seq.append(("ctrl", ctrl6_pkt))
    # fixed
    seq.append(("ctrl", FIXED_CTRLS[2]))
    # out p1 color
    seq.append(("out", _build_color_packet_1(custom)))
    # fixed
    seq.append(("ctrl", FIXED_CTRLS[3]))
    # out p2 color
    seq.append(("out", COLOR_PACKET_2))
    # ctrl#9 DPI count
    seq.append(("ctrl", DPI_COUNT_PACKETS[count]))
    # out DPI registers
    seq.append(("out", dpi_regs.hex()))
    # fixed
    seq.append(("ctrl", FIXED_CTRLS[4]))
    # out button map
    seq.append(("out", btn_hex))
    # out timing/debounce
    seq.append(("out", "0b0000000d000000000000000000000000000000000000000400010004000200"))
    # fixed
    seq.append(("ctrl", FIXED_CTRLS[5]))
    # out reserved
    seq.append(("out", "0" * 64))
    # out scroll
    seq.append(("out", "0b0000000d000000000000000000000000000000000000000000000000000000"))
    # fixed
    seq.append(("ctrl", FIXED_CTRLS[6]))
    # out commit
    seq.append(("out", "ff" + "0" * 62))
    # ctrl#13 key response + LOD
    seq.append(("ctrl", _ctrl13_hex(cfg["key_response"], cfg["lift_off"])))
    # fixed
    seq.append(("ctrl", FIXED_CTRLS[7]))
    seq.append(("ctrl", FIXED_CTRLS[8]))
    return seq
