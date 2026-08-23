import pytest
from engine.device import (
    HatorDevice,
    DeviceNotFoundError,
    PermissionError2,
    find_hidraw,
    _sfeat,
    _gfeat,
    _receiver_hidraw_nodes,
)


def test_feature_out_sends_set_report(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "engine.device.fcntl.ioctl",
        lambda fd, req, buf: calls.append((req, bytes(buf))),
    )
    dev = HatorDevice(_fd=object())
    dev.feature_out(0x05, bytes.fromhex("90 00 00 00 00 00 00"))
    req, buf = calls[-1]
    assert req == _sfeat(8)
    assert buf == bytes.fromhex("05 90 00 00 00 00 00 00")


def test_feature_in_reads_get_report(monkeypatch):
    def fake_ioctl(fd, req, buf):
        # kernel writes the response into the passed mutable buffer
        buf[:] = bytes.fromhex("05 90 11 35 00 00 00 00")

    monkeypatch.setattr("engine.device.fcntl.ioctl", fake_ioctl)
    dev = HatorDevice(_fd=object())
    resp = dev.feature_in(0x05, 8)
    assert resp == bytes.fromhex("05 90 11 35 00 00 00 00")


def test_feature_in_uses_expected_request(monkeypatch):
    seen = {}
    def fake_ioctl(fd, req, buf):
        seen["req"] = req
        buf[:] = bytes.fromhex("05 90 11 35 00 00 00 00")
    monkeypatch.setattr("engine.device.fcntl.ioctl", fake_ioctl)
    HatorDevice(_fd=object()).feature_in(0x05, 8)
    assert seen["req"] == _gfeat(8)


def test_find_hidraw_prefers_interface1(monkeypatch):
    nodes = [
        ("/sys/.../3-2:1.0/0003:258A:002F.0004/hidraw/hidraw0", "/dev/hidraw0"),
        ("/sys/.../3-2:1.1/0003:258A:002F.0005/hidraw/hidraw1", "/dev/hidraw1"),
    ]
    monkeypatch.setattr("engine.device._receiver_hidraw_nodes", lambda *a, **k: nodes)
    assert find_hidraw() == "/dev/hidraw1"


def test_find_hidraw_none_raises(monkeypatch):
    monkeypatch.setattr("engine.device.find_hidraw", lambda *a, **k: None)
    with pytest.raises(DeviceNotFoundError):
        HatorDevice(path=None)


def test_permission_denied(monkeypatch):
    monkeypatch.setattr("engine.device.find_hidraw", lambda *a, **k: "/dev/hidraw0")
    def raise_perm(p, flags):
        raise PermissionError()
    monkeypatch.setattr("engine.device.os.open", raise_perm)
    with pytest.raises(PermissionError2):
        HatorDevice(path=None)
