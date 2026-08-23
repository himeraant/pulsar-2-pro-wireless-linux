from engine.battery import read_battery, battery_unavailable, _read_sysfs
from tests.helpers import MockDevice


def test_reads_sysfs_capacity(tmp_path):
    node = tmp_path / "hid-abc-battery"
    node.mkdir()
    (node / "capacity").write_text("87\n")
    (node / "status").write_text("Discharging\n")
    assert read_battery(power_supply_dir=str(tmp_path)) == {"level": 87, "status": "Discharging"}


def test_no_sysfs_falls_back_to_device(tmp_path):
    node = tmp_path / "ACAD"
    node.mkdir()
    dev = MockDevice().enqueue(0x05, bytes.fromhex("05 90 11 35 00 00 00 00"))
    info = read_battery(dev, power_supply_dir=str(tmp_path))
    assert info["level"] == 0x35


def test_no_sysfs_no_device_returns_none(tmp_path):
    (tmp_path / "ACAD").mkdir()
    assert read_battery(None, power_supply_dir=str(tmp_path)) is None


def test_sysfs_listdir_oserror(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(os, "listdir", lambda d: (_ for _ in ()).throw(OSError()))
    assert _read_sysfs(str(tmp_path)) is None


def test_tier2_stub():
    assert battery_unavailable()["status"] == "unavailable"
    assert battery_unavailable()["tier"] == 2
