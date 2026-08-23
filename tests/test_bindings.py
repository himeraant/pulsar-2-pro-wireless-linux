from bindings import evdev_button_for, generate_preset, write_preset


def test_evdev_button_for_physical_index():
    assert evdev_button_for(0) == "BTN_LEFT"
    assert evdev_button_for(1) == "BTN_RIGHT"
    assert evdev_button_for(2) == "BTN_MIDDLE"
    assert evdev_button_for(5) == "BTN_SIDE"  # DPI button re-exposed


def test_generate_preset_key_action():
    preset = generate_preset("BTN_SIDE", "KEY_PLAYPAUSE")
    assert "KEY_PLAYPAUSE" in preset
    assert "BTN_SIDE" in preset


def test_generate_preset_macro():
    preset = generate_preset("BTN_EXTRA", "<macro>k(KEY_LEFTSHIFT)h(KEY_A)</macro>")
    assert "macro" in preset


def test_write_preset_writes_file(tmp_path):
    path = write_preset("HATOR Mouse", "BTN_SIDE", "KEY_PLAYPAUSE", preset_dir=str(tmp_path))
    with open(path) as f:
        assert "KEY_PLAYPAUSE" in f.read()
