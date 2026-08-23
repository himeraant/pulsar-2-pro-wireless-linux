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
