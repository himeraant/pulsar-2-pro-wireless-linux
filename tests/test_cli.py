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
        lambda device_name, evdev, action, preset_dir=None: str(tmp_path / "hator.json"),
    )
    rc = main(["--bind", "6", "KEY_PLAYPAUSE"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "bound" in out.lower()
    assert "key_playpause" in out.lower()
    assert fake is not None
    assert len(fake.applied) == 1


def test_cli_bind_out_of_range_button_is_friendly_error(monkeypatch, capsys):
    """--bind 7 X must not KeyError/traceback; it should hit the same
    friendly 'Invalid button number' path as non-numeric input."""
    monkeypatch.setattr("cli.HatorEngine", _FakeEngine)
    rc = main(["--bind", "7", "KEY_A"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "invalid button number" in err.lower()


def test_cli_bind_zero_is_friendly_error(monkeypatch, capsys):
    monkeypatch.setattr("cli.HatorEngine", _FakeEngine)
    rc = main(["--bind", "0", "KEY_A"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "invalid button number" in err.lower()


def test_cli_bind_button6_warns_about_forward_collision(monkeypatch, capsys, tmp_path):
    """Binding button 6 (DPI) aliases the same on-device action as button 4
    (Forward, default). This must surface a warning, not fail silently."""
    fake = None

    class TrackingEngine(_FakeEngine):
        def __init__(self):
            super().__init__()
            nonlocal fake
            fake = self

        def get_state(self):
            from engine.protocol import default_config
            return default_config()

    monkeypatch.setattr("cli.HatorEngine", TrackingEngine)
    monkeypatch.setattr(
        "cli.write_preset",
        lambda device_name, evdev, action, preset_dir=None: str(tmp_path / "hator.json"),
    )
    rc = main(["--bind", "6", "KEY_PLAYPAUSE"])
    err = capsys.readouterr().err
    assert rc == 0
    assert "warning" in err.lower()
    assert "button 4" in err.lower() or "button 6" in err.lower()


def test_cli_engine_close_called(monkeypatch):
    """engine.close() must be called even on --battery (finally block)."""
    closed = []

    class CloseTracker(_FakeEngine):
        def close(self):
            closed.append(True)

    monkeypatch.setattr("cli.HatorEngine", CloseTracker)
    main(["--battery"])
    assert closed == [True]
