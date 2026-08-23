import pytest
from engine import protocol as p


def test_dpi_register_roundtrip():
    assert p.dpi_to_register(400) == 7
    assert p.register_to_dpi(7) == 400


def test_dpi_validation():
    assert p.validate_dpi(400) == 400
    assert p.validate_dpi(50) == 50
    with pytest.raises(ValueError):
        p.validate_dpi(45)          # not a multiple of 50
    with pytest.raises(ValueError):
        p.validate_dpi(13000)       # above max


def test_default_config_has_6_cpi():
    cfg = p.default_config()
    assert len(cfg["cpi"]) == 6
    assert cfg["polling_rate"] == 1000
    assert cfg["button_map"] == ["left", "right", "middle", "forward", "backward", "dpi"]


def test_build_sequence_starts_with_fixed_ctrl():
    seq = p.build_apply_sequence(p.default_config())
    assert seq[0][0] == "ctrl"
    assert seq[0][1] == "2727d5fff4e57676"


def test_build_sequence_is_apply_snapshot():
    # Sanity: 24 operations total (12 ctrl + 12 out), mirroring the decoded capture.
    seq = p.build_apply_sequence(p.default_config())
    assert len(seq) == 24


def test_build_sequence_encodes_button_map():
    seq = p.build_apply_sequence(p.default_config())
    out_ops = [h for kind, h in seq if kind == "out"]
    # Button map packet is the 4th out op (index 3). Slots 7-8 fixed.
    btn = out_ops[3]
    assert btn.endswith("0700010007000200")


def test_build_sequence_polling_encoding():
    cfg = p.default_config()
    cfg["polling_rate"] = 500
    seq = p.build_apply_sequence(cfg)
    # 4th ctrl op (index 3) is the polling packet.
    ctrls = [h for kind, h in seq if kind == "ctrl"]
    assert ctrls[3] == "272bd5ff00d57676"
