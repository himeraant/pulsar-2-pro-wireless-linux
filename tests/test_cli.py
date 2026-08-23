from cli import main


def test_cli_battery_no_device_ok(monkeypatch, capsys):
    # --battery with no real device should print a message, exit 0.
    monkeypatch.setattr("cli.HatorEngine", _FakeEngine)
    rc = main(["--battery"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "battery" in out.lower()


class _FakeEngine:
    def read_battery(self):
        return {"level": 50, "status": "Discharging"}

    def get_state(self):
        return None

    def apply_defaults(self):
        return {"polling_rate": 1000}
