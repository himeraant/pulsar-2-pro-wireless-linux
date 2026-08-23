from engine.battery import read_battery, battery_unavailable


def test_reads_sysfs_capacity(tmp_path):
    node = tmp_path / "hid-abc-battery"
    node.mkdir()
    (node / "capacity").write_text("87\n")
    (node / "status").write_text("Discharging\n")
    result = read_battery(str(tmp_path))
    assert result == {"level": 87, "status": "Discharging"}


def test_no_battery_node_returns_none(tmp_path):
    # Only ACAD/BATT (laptop battery) present, no hid battery node.
    (tmp_path / "ACAD").mkdir()
    assert read_battery(str(tmp_path)) is None


def test_tier2_stub():
    assert battery_unavailable()["status"] == "unavailable"
    assert battery_unavailable()["tier"] == 2
