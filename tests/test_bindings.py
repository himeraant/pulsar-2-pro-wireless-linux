import json

from bindings import evdev_button_for, generate_preset, write_preset, EVDEV_BUTTON_CODES


def test_evdev_button_for_physical_index():
    assert evdev_button_for(0) == "BTN_LEFT"
    assert evdev_button_for(1) == "BTN_RIGHT"
    assert evdev_button_for(2) == "BTN_MIDDLE"
    assert evdev_button_for(5) == "BTN_SIDE"  # DPI button re-exposed


def test_evdev_button_codes_table():
    assert EVDEV_BUTTON_CODES["BTN_LEFT"] == (1, 0x110)
    assert EVDEV_BUTTON_CODES["BTN_RIGHT"] == (1, 0x111)
    assert EVDEV_BUTTON_CODES["BTN_MIDDLE"] == (1, 0x112)
    assert EVDEV_BUTTON_CODES["BTN_SIDE"] == (1, 0x113)
    assert EVDEV_BUTTON_CODES["BTN_EXTRA"] == (1, 0x114)


def test_generate_preset_key_action():
    preset = generate_preset("BTN_SIDE", "KEY_PLAYPAUSE")
    mapping = json.loads(preset)
    assert isinstance(mapping, list)
    assert len(mapping) == 1
    entry = mapping[0]
    assert entry["input_combination"] == [{"type": 1, "code": 0x113}]
    assert entry["output_symbol"] == "KEY_PLAYPAUSE"
    assert entry["target_uinput"] == "keyboard"


def test_generate_preset_macro():
    action = "<macro>k(KEY_LEFTSHIFT)h(KEY_A)</macro>"
    preset = generate_preset("BTN_EXTRA", action)
    mapping = json.loads(preset)
    entry = mapping[0]
    assert entry["input_combination"] == [{"type": 1, "code": 0x114}]
    assert entry["output_symbol"] == action
    assert "macro" in entry["output_symbol"]


def test_generate_preset_unknown_button_raises():
    import pytest
    with pytest.raises(ValueError):
        generate_preset("BTN_NOPE", "KEY_A")


def test_write_preset_writes_json_file(tmp_path):
    path = write_preset("HATOR Mouse", "BTN_SIDE", "KEY_PLAYPAUSE", preset_dir=str(tmp_path))
    assert path.endswith(".json")
    with open(path) as f:
        mapping = json.load(f)
    assert mapping[0]["output_symbol"] == "KEY_PLAYPAUSE"
    assert mapping[0]["input_combination"] == [{"type": 1, "code": 0x113}]
