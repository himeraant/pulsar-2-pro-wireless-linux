from media import _bits_to_keys, CONSUMER_KEYS
from evdev import ecodes as E


def test_play_pause_bit_decodes():
    # report 02 08 00 00 -> byte0 bit3 = play/pause
    keys = _bits_to_keys(bytes.fromhex("02 08 00 00"))
    assert E.KEY_PLAYPAUSE in keys
    assert len(keys) == 1


def test_empty_report_no_keys():
    assert _bits_to_keys(bytes.fromhex("02 00 00 00")) == set()


def test_non_consumer_report_ignored():
    # keyboard report (ID 0x01) is ignored
    assert _bits_to_keys(bytes([0x01]) + b"\x00" * 7) == set()


def test_next_prev_mute():
    # byte0 bit0 = next, bit1 = prev, bit4 = mute
    keys = _bits_to_keys(bytes.fromhex("02 13 00 00"))  # bits 0,1,4
    assert {E.KEY_NEXTSONG, E.KEY_PREVIOUSSONG, E.KEY_MUTE} <= keys


def test_mapping_names_are_valid_evdev_keys():
    import evdev
    from evdev import ecodes
    for usage, name in CONSUMER_KEYS.items():
        assert hasattr(ecodes, name), f"{name} is not a valid evdev constant"
