import json

import pytest

from bindings import (
    BindError,
    evdev_button_for,
    generate_preset,
    set_binding,
    unbind,
    list_bindings,
    sanitize_device_name,
    load_preset,
    EVDEV_BUTTON_CODES,
    PRESET_FILENAME,
)

OH = "4790f6e20b87c369dcfe985187897b13"


def test_evdev_button_for_physical_index():
    assert evdev_button_for(0) == "BTN_LEFT"
    assert evdev_button_for(1) == "BTN_RIGHT"
    assert evdev_button_for(2) == "BTN_MIDDLE"
    assert evdev_button_for(3) == "BTN_SIDE"
    assert evdev_button_for(4) == "BTN_EXTRA"


def test_evdev_button_for_dpi_not_remappable():
    with pytest.raises(BindError):
        evdev_button_for(5)  # DPI button: no distinct host event


def test_evdev_button_codes_table():
    assert EVDEV_BUTTON_CODES["BTN_LEFT"] == (1, 0x110)
    assert EVDEV_BUTTON_CODES["BTN_RIGHT"] == (1, 0x111)
    assert EVDEV_BUTTON_CODES["BTN_MIDDLE"] == (1, 0x112)
    assert EVDEV_BUTTON_CODES["BTN_SIDE"] == (1, 0x113)
    assert EVDEV_BUTTON_CODES["BTN_EXTRA"] == (1, 0x114)


def test_generate_preset_key_action():
    preset = generate_preset("BTN_SIDE", "KEY_PLAYPAUSE", OH)
    mapping = json.loads(preset)
    assert isinstance(mapping, list)
    assert len(mapping) == 1
    entry = mapping[0]
    assert entry["input_combination"] == [
        {"type": 1, "code": 0x113, "origin_hash": OH}
    ]
    assert entry["output_symbol"] == "KEY_PLAYPAUSE"
    assert entry["target_uinput"] == "keyboard"
    assert entry["mapping_type"] == "key_macro"


def test_generate_preset_requires_origin_hash():
    with pytest.raises(BindError):
        generate_preset("BTN_SIDE", "KEY_A", "")


def test_generate_preset_macro_targets_keyboard():
    action = "<macro>k(KEY_LEFTSHIFT)h(KEY_A)</macro>"
    entry = json.loads(generate_preset("BTN_EXTRA", action, OH))[0]
    assert entry["output_symbol"] == action
    assert entry["target_uinput"] == "keyboard"


def test_mouse_output_targets_mouse():
    entry = json.loads(generate_preset("BTN_SIDE", "BTN_MIDDLE", OH))[0]
    assert entry["target_uinput"] == "mouse"


def test_unknown_button_raises():
    with pytest.raises(BindError):
        generate_preset("BTN_NOPE", "KEY_A", OH)


def test_sanitize_device_name_matches_input_remapper():
    assert sanitize_device_name("HATOR Mouse") == "HATOR Mouse"
    assert sanitize_device_name("A/B:C") == "A_B_C"
    assert sanitize_device_name("My Mouse 2.0") == "My Mouse 2.0"


def test_set_binding_accumulates_and_updates(tmp_path):
    p1 = set_binding("HATOR Mouse", 3, "KEY_A", OH, preset_dir=str(tmp_path))  # forward
    p2 = set_binding("HATOR Mouse", 4, "KEY_B", OH, preset_dir=str(tmp_path))  # backward
    assert p1 == p2  # same preset file, accumulated
    mappings = load_preset("HATOR Mouse", str(tmp_path))
    assert len(mappings) == 2
    # update existing binding in place
    set_binding("HATOR Mouse", 3, "KEY_C", OH, preset_dir=str(tmp_path))
    mappings = load_preset("HATOR Mouse", str(tmp_path))
    assert len(mappings) == 2
    codes = [m["input_combination"][0]["code"] for m in mappings]
    assert codes.count(0x113) == 1
    updated = next(m for m in mappings if m["input_combination"][0]["code"] == 0x113)
    assert updated["output_symbol"] == "KEY_C"


def test_unbind_removes_only_target_button(tmp_path):
    set_binding("HATOR Mouse", 3, "KEY_A", OH, preset_dir=str(tmp_path))
    set_binding("HATOR Mouse", 4, "KEY_B", OH, preset_dir=str(tmp_path))
    assert unbind("HATOR Mouse", 3, preset_dir=str(tmp_path)) is True
    mappings = load_preset("HATOR Mouse", str(tmp_path))
    assert [m["input_combination"][0]["code"] for m in mappings] == [0x114]
    assert unbind("HATOR Mouse", 3, preset_dir=str(tmp_path)) is False


def test_list_bindings(tmp_path):
    set_binding("HATOR Mouse", 3, "KEY_A", OH, preset_dir=str(tmp_path))
    set_binding("HATOR Mouse", 4, "KEY_B", OH, preset_dir=str(tmp_path))
    binds = list_bindings("HATOR Mouse", str(tmp_path))
    by_btn = {b["btn"]: b["action"] for b in binds}
    assert by_btn == {4: "KEY_A", 5: "KEY_B"}


def test_list_bindings_empty(tmp_path):
    assert list_bindings("HATOR Mouse", str(tmp_path)) == []


def test_preset_filename_constant():
    assert PRESET_FILENAME == "hator.json"
