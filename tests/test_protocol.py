import pytest
from engine import protocol as p
from tests.helpers import MockDevice

# A realistic 520-byte config blob (report 0x08 read): first bytes match the
# decoded structure (offset 10 polling, offsets 13-25 DPI slots).
def make_blob(polling_code=4, dpi_regs=(39, 4, 9, 14, 23, 39, 79)):
    blob = bytearray(520)
    blob[0] = 0x08  # report id
    blob[1] = 0x21  # cmd
    blob[3] = 0x92
    blob[8] = 0x64
    blob[9] = 0x11
    blob[10] = polling_code
    blob[11] = 0x27
    for off, reg in zip(p.DPI_OFFSETS, dpi_regs):
        blob[off : off + 2] = (reg & 0xFFFF).to_bytes(2, "little")
    return bytes(blob)


def test_read_battery_parses_percentage():
    dev = MockDevice().enqueue(0x05, bytes.fromhex("05 90 11 35 00 00 00 00"))
    assert p.read_battery(dev) == 0x35  # 53%


def test_read_battery_none_on_missing():
    dev = MockDevice().enqueue(0x05, bytes.fromhex("05 91 11 35 00 00 00 00"))
    assert p.read_battery(dev) is None  # cmd byte mismatch


def test_polling_decode():
    assert p.get_polling_hz(make_blob(polling_code=1)) == 125
    assert p.get_polling_hz(make_blob(polling_code=4)) == 1000


def test_dpi_decode():
    # reg 39 -> 4000, reg 4 -> 500, reg 9 -> 1000
    slots = p.get_dpi_slots(make_blob(dpi_regs=(39, 4, 9, 14, 23, 39, 79)))
    assert slots == [4000, 500, 1000, 1500, 2400, 4000, 8000]


def test_build_config_polling():
    blob = make_blob(polling_code=4)
    out = p.build_config(blob, polling_hz=500)
    assert p.get_polling_hz(out) == 500
    # other bytes unchanged
    assert out[11] == 0x27


def test_build_config_dpi():
    blob = make_blob(dpi_regs=(39, 4, 9, 14, 23, 39, 79))
    out = p.build_config(blob, dpi_slots=[4000, 500, 1500, 1500, 2400, 4000, 8000])
    # slot 3 (offset 17) -> 1500 -> reg 14 = 0x0e
    assert int.from_bytes(out[17:19], "little") == 14


def test_apply_config_reads_then_writes():
    blob = make_blob(polling_code=4, dpi_regs=(39, 4, 9, 14, 23, 39, 79))
    dev = MockDevice()
    dev.enqueue(0x05, bytes.fromhex("05 80 01 01 00 00 00 00"))  # ack
    dev.enqueue(0x08, blob)  # config read
    p.apply_config(dev, polling_hz=500)
    # preamble sent two 0x05 reports, then a 0x08 write
    written = [c for c in dev.feature_out_calls if c[0] == 0x08]
    assert written, "expected a config write"
    data = written[-1][1]
    # written data starts at report id+cmd; polling byte at index 9 of payload
    # (feature_out sends report_id + blob[1:])
    assert data[9] == p.POLLING_TO_CODE[500]


def test_default_config_shape():
    cfg = p.default_config()
    assert len(cfg["cpi"]) == 7
    assert cfg["polling_rate"] == 1000


def test_dpi_count_encoding():
    blob = make_blob()
    out = p.build_config(blob, dpi_count=3)
    assert out[11] == 0x20 + 3


def test_dpi_count_out_of_range():
    blob = make_blob()
    with pytest.raises(ValueError):
        p.build_config(blob, dpi_count=9)


def _button_blob(entries=None):
    blob = bytearray(520)
    blob[:8] = bytes.fromhex("08 22 00 50 00 00 00 00")
    entries = entries or [
        (0x11, 0x01, 0, 0), (0x11, 0x02, 0, 0), (0x11, 0x04, 0, 0),
        (0x11, 0x08, 0, 0), (0x11, 0x10, 0, 0), (0x41, 0x02, 0, 0),
    ]
    for i, (t, v, p1, p2) in enumerate(entries):
        off = p.BUTTON_ENTRY_OFFSET + i * p.BUTTON_ENTRY_SIZE
        blob[off : off + 4] = bytes([t, v, p1, p2])
    return bytes(blob)


def test_get_button_action_defaults():
    blob = _button_blob()
    assert p.get_button_action(blob, 0) == "left"
    assert p.get_button_action(blob, 1) == "right"
    assert p.get_button_action(blob, 2) == "middle"
    assert p.get_button_action(blob, 3) == "back"
    assert p.get_button_action(blob, 4) == "forward"
    assert p.get_button_action(blob, 5) == "dpi_down"  # button 6


def test_build_button_blob_sets_entry():
    blob = _button_blob()
    out = p.build_button_blob(blob, 5, "forward")  # button 6 -> forward
    assert out[28:32] == bytes.fromhex("11 10 00 00")
    assert p.get_button_action(out, 5) == "forward"
    # other entries unchanged
    assert p.get_button_action(out, 0) == "left"


def test_build_button_blob_unknown_action_raises():
    blob = _button_blob()
    with pytest.raises(ValueError):
        p.build_button_blob(blob, 5, "next_track")  # not decoded yet


def test_play_pause_is_a_known_on_device_action():
    blob = _button_blob()
    out = p.build_button_blob(blob, 5, "play_pause")
    assert out[28:32] == bytes.fromhex("22 08 00 00")
    assert p.get_button_action(out, 5) == "play_pause"


def test_build_button_blob_bad_index_raises():
    blob = _button_blob()
    with pytest.raises(ValueError):
        p.build_button_blob(blob, 99, "forward")


def test_apply_button_map_writes_button_blob():
    dev = MockDevice()
    dev.enqueue(0x05, bytes.fromhex("05 80 01 01 00 00 00 00"))  # ack
    dev.enqueue(0x08, make_blob())  # current config read, echoed back
    blob = p.build_full_button_blob(
        ["left", "right", "middle", "back", "forward", "forward"]  # button6->forward
    )
    p.apply_button_map(dev, blob)
    writes = [c for c in dev.feature_out_calls if c[0] == 0x08]
    assert len(writes) == 2  # config echo (0x21) then button blob (0x22)
    # first write is the echoed config (cmd 0x21)
    assert writes[0][1][0] == 0x21
    # second write is the button blob (cmd 0x22)
    data = writes[1][1]
    assert data[0] == 0x22
    assert data[7 + 20 : 7 + 24] == bytes.fromhex("11 10 00 00")  # btn6 entry5


def test_build_full_button_blob_preserves_all_buttons():
    blob = p.build_full_button_blob(
        ["left", "right", "middle", "back", "forward", "play_pause"]
    )
    assert p.get_button_action(blob, 0) == "left"
    assert p.get_button_action(blob, 4) == "forward"
    assert p.get_button_action(blob, 5) == "play_pause"
