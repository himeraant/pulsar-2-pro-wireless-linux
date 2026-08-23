import pytest
import usb.core
import usb.util
from engine.device import HatorDevice, DeviceNotFoundError


class FakeUSB:
    def __init__(self, driver_active=True):
        self.ctrl_calls = []
        self.in_results = {}
        self.detached = False
        self.driver_active = driver_active

    def is_kernel_driver_active(self, i):
        return self.driver_active and not self.detached

    def detach_kernel_driver(self, i):
        self.detached = True

    def attach_kernel_driver(self, i):
        self.detached = False

    def ctrl_transfer(self, bm, b, v, idx, data):
        if isinstance(data, int):  # GET_REPORT read length
            resp = self.in_results.get(v, bytes(data))
            self.ctrl_calls.append((bm, b, v, idx, data, resp))
            return bytes(resp)
        self.ctrl_calls.append((bm, b, v, idx, bytes(data), None))
        return None


def make_dev(monkeypatch, fake=None):
    monkeypatch.setattr(usb.util, "claim_interface", lambda d, i: None)
    monkeypatch.setattr(usb.util, "release_interface", lambda d, i: None)
    return HatorDevice(dev=fake or FakeUSB())


def test_claims_and_detaches_interface1(monkeypatch):
    fake = FakeUSB()
    make_dev(monkeypatch, fake)
    assert fake.detached is True  # usbhid detached from interface 1


def test_reattaches_on_close(monkeypatch):
    fake = FakeUSB()
    dev = make_dev(monkeypatch, fake)
    dev.close()
    assert fake.detached is False


def test_feature_out_encodes_set_report(monkeypatch):
    fake = FakeUSB()
    dev = make_dev(monkeypatch, fake)
    dev.feature_out(0x05, bytes.fromhex("90 00 00 00 00 00 00"))
    bm, b, v, idx, data, _ = fake.ctrl_calls[-1]
    assert (bm, b, v, idx) == (0x21, 0x09, 0x0305, 0x0001)
    assert data == bytes.fromhex("05 90 00 00 00 00 00 00")


def test_feature_in_encodes_get_report(monkeypatch):
    fake = FakeUSB()
    fake.in_results[0x0305] = bytes.fromhex("05 90 11 35 00 00 00 00")
    dev = make_dev(monkeypatch, fake)
    resp = dev.feature_in(0x05, 8)
    bm, b, v, idx, length, _ = fake.ctrl_calls[-1]
    assert (bm, b, v, idx, length) == (0xA1, 0x01, 0x0305, 0x0001, 8)
    assert resp == bytes.fromhex("05 90 11 35 00 00 00 00")


def test_device_not_found_raises(monkeypatch):
    monkeypatch.setattr(usb.core, "find", lambda *a, **kw: None)
    with pytest.raises(DeviceNotFoundError):
        HatorDevice(dev=None)
