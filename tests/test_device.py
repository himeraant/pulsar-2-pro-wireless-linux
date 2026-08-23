import pytest
from engine.device import HatorDevice, DeviceNotFoundError


class FakeUSB:
    def __init__(self):
        self.ctrl_calls = []
        self.in_results = {}

    def ctrl_transfer(self, bm, b, v, idx, data):
        if isinstance(data, int):  # GET_REPORT read length
            resp = self.in_results.get(v, bytes(data))
            self.ctrl_calls.append((bm, b, v, idx, data, resp))
            return bytes(resp)
        self.ctrl_calls.append((bm, b, v, idx, bytes(data), None))
        return None


def test_feature_out_encodes_set_report():
    fake = FakeUSB()
    dev = HatorDevice(dev=fake)
    dev.feature_out(0x05, bytes.fromhex("90 00 00 00 00 00 00"))
    bm, b, v, idx, data, _ = fake.ctrl_calls[-1]
    assert bm == 0x21
    assert b == 0x09  # SET_REPORT
    assert v == 0x0305  # feature report id 0x05
    assert idx == 0x0001
    assert data == bytes.fromhex("05 90 00 00 00 00 00 00")


def test_feature_in_encodes_get_report():
    fake = FakeUSB()
    fake.in_results[0x0305] = bytes.fromhex("05 90 11 35 00 00 00 00")
    dev = HatorDevice(dev=fake)
    resp = dev.feature_in(0x05, 8)
    bm, b, v, idx, length, _ = fake.ctrl_calls[-1]
    assert bm == 0xA1
    assert b == 0x01  # GET_REPORT
    assert v == 0x0305
    assert idx == 0x0001
    assert length == 8
    assert resp == bytes.fromhex("05 90 11 35 00 00 00 00")


def test_device_not_found_raises(monkeypatch):
    import usb.core
    monkeypatch.setattr(usb.core, "find", lambda *a, **kw: None)
    with pytest.raises(DeviceNotFoundError):
        HatorDevice(dev=None)
