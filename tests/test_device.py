import pytest
from engine import protocol as p
from engine.device import HatorDevice, DeviceNotFoundError


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
        self.ctrl_calls.append(data)

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
    # Each ctrl payload is exactly the decoded hex
    first_ctrl_hex = "2727d5fff4e57676"
    assert fake.ctrl_calls[0].hex() == first_ctrl_hex
    # Driver 0 was detached then re-attached on close
    dev.close()
    assert fake.detached == []


def test_device_not_found_raises():
    with pytest.raises(DeviceNotFoundError):
        HatorDevice(dev=None)
