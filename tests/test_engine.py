import pytest
from engine import protocol as p
from engine import HatorEngine
from engine.device import DeviceNotFoundError
from tests.helpers import MockDevice


def make_blob(polling_code=4, dpi_regs=(39, 4, 9, 14, 23, 39, 79)):
    blob = bytearray(520)
    blob[0] = 0x08
    blob[1] = 0x21
    blob[3] = 0x92
    blob[8] = 0x64
    blob[9] = 0x11
    blob[10] = polling_code
    blob[11] = 0x27
    for off, reg in zip(p.DPI_OFFSETS, dpi_regs):
        blob[off : off + 2] = (reg & 0xFFFF).to_bytes(2, "little")
    return bytes(blob)


class FakeDevice(MockDevice):
    def __init__(self):
        super().__init__()
        self.config = bytearray(make_blob())

    def feature_in(self, report_id, size):
        if report_id == 0x08:
            return bytes(self.config)
        return bytes([report_id, 0x80, 1, 1]) + bytes(size - 4)  # 0x05 ack


def test_apply_writes_polling_and_persists(tmp_path):
    dev = FakeDevice()
    eng = HatorEngine(device=dev, state_path=str(tmp_path / "s.json"))
    eng.apply({"polling_rate": 500})
    writes = [c for c in dev.feature_out_calls if c[0] == 0x08]
    assert writes
    # payload index 9 (after report id 0x08 + cmd 0x21) is the polling byte
    assert writes[-1][1][9] == p.POLLING_TO_CODE[500]
    assert eng.get_state()["polling_rate"] == 500


def test_apply_defaults_resets(tmp_path):
    dev = FakeDevice()
    eng = HatorEngine(device=dev, state_path=str(tmp_path / "s.json"))
    eng.apply({"polling_rate": 125, "cpi": [100, 100, 100, 100, 100, 100, 100]})
    eng.apply_defaults()
    st = eng.get_state()
    assert st["polling_rate"] == 1000
    assert st["cpi"] == [400, 800, 1200, 1600, 2400, 3200, 6400]


def test_read_battery_via_device():
    dev = MockDevice().enqueue(0x05, bytes.fromhex("05 90 11 35 00 00 00 00"))
    eng = HatorEngine(device=dev)
    info = eng.read_battery()
    assert info["level"] == 0x35


def test_read_battery_unavailable_without_device(monkeypatch, tmp_path):
    # No real receiver -> engine falls back to "unavailable"
    monkeypatch.setattr("engine.HatorDevice", lambda: (_ for _ in ()).throw(DeviceNotFoundError()))
    eng = HatorEngine(device=None, state_path=str(tmp_path / "s.json"))
    info = eng.read_battery()
    assert info["status"] == "unavailable"
