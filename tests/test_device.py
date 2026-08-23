import pytest
from engine import protocol as p
from engine.device import (
    HatorDevice,
    DeviceNotFoundError,
    SinowealthProtocolNotImplemented,
)


class FakeUSB:
    def __init__(self):
        self.ctrl_calls = []
        self.out_calls = []
        self.detached = []
        self.closed = False

    def is_kernel_driver_active(self, i):
        return i == 0

    def detach_kernel_driver(self, i):
        self.detached.append(i)

    def attach_kernel_driver(self, i):
        self.detached.remove(i)

    def set_configuration(self):
        pass

    def ctrl_transfer(self, bm, b, v, idx, data):
        self.ctrl_calls.append((bm, b, v, idx, data))

    def write(self, endpoint, data, timeout=None):
        self.out_calls.append(bytes(data))

    def dispose_resources(self):
        self.closed = True


def test_injected_device_executes_sequence():
    fake = FakeUSB()
    dev = HatorDevice(dev=fake)
    seq = p.build_apply_sequence(p.default_config())
    dev.apply_sequence(seq)
    # 16 ctrl ops -> 16 ctrl_transfer calls; 8 out ops -> 8 writes
    assert len(fake.ctrl_calls) == 16
    assert len(fake.out_calls) == 8
    # Each ctrl call has correct headers (bmRequestType, bRequest, wValue, wIndex)
    for bm, b, v, idx, data in fake.ctrl_calls:
        assert bm == 0x21  # class request, host-to-device
        assert b == 0x09   # SET_REPORT
        assert v == 0x0300 # VALUE_SET_REPORT
        assert idx == 2    # INTERFACE
    # Each ctrl payload is exactly the decoded hex
    first_ctrl_hex = "2727d5fff4e57676"
    assert fake.ctrl_calls[0][4].hex() == first_ctrl_hex  # Extract data from tuple
    # Driver 0 was detached then re-attached on close
    dev.close()
    assert fake.detached == []


def test_device_not_found_raises(monkeypatch):
    import usb.core
    monkeypatch.setattr(usb.core, "find", lambda *a, **kw: None)
    with pytest.raises(DeviceNotFoundError):
        HatorDevice(dev=None)


def test_real_sinowealth_receiver_raises_protocol_not_implemented(monkeypatch):
    import usb.core
    # A real receiver is found, but the protocol isn't decoded yet.
    monkeypatch.setattr(usb.core, "find", lambda *a, **kw: FakeUSB())
    with pytest.raises(SinowealthProtocolNotImplemented):
        HatorDevice(dev=None)

