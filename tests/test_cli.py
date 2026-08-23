import tempfile
import os
from cli import main
from engine.protocol import default_config


class _FakeEngine:
    def __init__(self):
        self.applied = []
        self.closed = False

    def read_battery(self):
        return {"level": 50, "status": "Discharging"}

    def get_state(self):
        return None

    def apply_defaults(self):
        return {"polling_rate": 1000}

    def apply(self, cfg):
        self.applied.append(cfg)
        return cfg

    def close(self):
        self.closed = True


def test_cli_battery_no_device_ok(monkeypatch, capsys):
    # --battery with no real device should print a message, exit 0.
    monkeypatch.setattr("cli.HatorEngine", _FakeEngine)
    rc = main(["--battery"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "battery" in out.lower()


def test_cli_get(monkeypatch, capsys):
    monkeypatch.setattr("cli.HatorEngine", _FakeEngine)
    rc = main(["--get"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "polling" in out.lower()
    assert "dpi" in out.lower()


def test_cli_polling(monkeypatch, capsys):
    fake = None

    class TrackingEngine(_FakeEngine):
        def __init__(self):
            super().__init__()
            nonlocal fake
            fake = self

    monkeypatch.setattr("cli.HatorEngine", TrackingEngine)
    rc = main(["--polling", "500"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "applied" in out.lower()
    assert fake is not None
    assert len(fake.applied) == 1
    assert fake.applied[0]["polling_rate"] == 500


def test_cli_bind(monkeypatch, capsys, tmp_path):
    fake = None

    class TrackingEngine(_FakeEngine):
        def __init__(self):
            super().__init__()
            nonlocal fake
            fake = self

    monkeypatch.setattr("cli.HatorEngine", TrackingEngine)
    # Redirect write_preset to a temp dir to avoid touching real config
    monkeypatch.setattr(
        "cli.write_preset",
        lambda device_name, evdev, action, preset_dir=None: str(tmp_path / "hator.toml"),
    )
    rc = main(["--bind", "6", "KEY_PLAYPAUSE"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "bound" in out.lower()
    assert "key_playpause" in out.lower()
    assert fake is not None
    assert len(fake.applied) == 1


def test_cli_engine_close_called(monkeypatch):
    """engine.close() must be called even on --battery (finally block)."""
    closed = []

    class CloseTracker(_FakeEngine):
        def close(self):
            closed.append(True)

    monkeypatch.setattr("cli.HatorEngine", CloseTracker)
    main(["--battery"])
    assert closed == [True]
