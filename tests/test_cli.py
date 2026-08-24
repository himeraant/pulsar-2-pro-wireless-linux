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
    monkeypatch.setattr("cli.HatorEngine", _FakeEngine)
    written = {}

    def fake_set_binding(device_name, btn, action, origin_hash, preset_dir=None, name=None):
        written["device_name"] = device_name
        written["btn"] = btn
        written["action"] = action
        written["origin_hash"] = origin_hash
        return str(tmp_path / "hator.json")

    monkeypatch.setattr("cli.set_binding", fake_set_binding)
    rc = main(["--bind", "4", "KEY_PLAYPAUSE", "--origin-hash", "aa" * 16])
    out = capsys.readouterr().out
    assert rc == 0
    assert "bound" in out.lower()
    assert "key_playpause" in out.lower()
    assert written["btn"] == 3  # button 4 -> physical index 3 (forward)
    assert written["origin_hash"] == "aa" * 16


def test_cli_bind_requires_origin_hash_without_evdev(monkeypatch, capsys):
    """Without --origin-hash and without python-evdev, bind must fail with a
    clear message instead of writing a broken preset."""
    monkeypatch.setattr("cli.HatorEngine", _FakeEngine)
    monkeypatch.setattr("cli.find_origin_hash", lambda *a, **k: None)
    rc = main(["--bind", "4", "KEY_A"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "origin_hash" in err.lower()


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


def test_cli_bind_button6_dpi_is_not_remappable(monkeypatch, capsys):
    """Button 6 (DPI) emits no distinct host event, so it cannot be remapped
    host-side. This must be a clear error, not a silent alias."""
    monkeypatch.setattr("cli.HatorEngine", _FakeEngine)
    monkeypatch.setattr("cli.find_origin_hash", lambda *a, **k: None)
    rc = main(["--bind", "6", "KEY_PLAYPAUSE", "--origin-hash", "aa" * 16])
    err = capsys.readouterr().err
    assert rc == 2
    assert "dpi" in err.lower()


def test_cli_unbind_and_list_binds(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("cli.HatorEngine", _FakeEngine)

    def fake_unbind(device, btn, preset_dir=None):
        assert btn == 3
        return True

    monkeypatch.setattr("cli.unbind", fake_unbind)
    rc = main(["--unbind", "4", "--device-name", "HATOR Mouse"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "unbound" in out.lower()

    monkeypatch.setattr("cli.list_bindings", lambda device, preset_dir=None: [
        {"btn": 4, "evdev": "BTN_SIDE", "action": "KEY_A"},
        {"btn": 5, "evdev": "BTN_EXTRA", "action": "KEY_B"},
    ])
    rc = main(["--list-binds", "--device-name", "HATOR Mouse"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "key_a" in out.lower()
    assert "button 4" in out.lower()


def test_cli_engine_close_called(monkeypatch):
    """engine.close() must be called even on --battery (finally block)."""
    closed = []

    class CloseTracker(_FakeEngine):
        def close(self):
            closed.append(True)

    monkeypatch.setattr("cli.HatorEngine", CloseTracker)
    main(["--battery"])
    assert closed == [True]
