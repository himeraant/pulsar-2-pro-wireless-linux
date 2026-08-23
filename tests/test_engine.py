import pytest
from engine import protocol as p
from engine import HatorEngine
from engine.device import DeviceNotFoundError


class FakeDevice:
    def __init__(self):
        self.applied = []

    def apply_sequence(self, sequence):
        self.applied.append(sequence)

    def close(self):
        pass


def test_apply_persists_and_applies(tmp_path):
    fake = FakeDevice()
    eng = HatorEngine(device=fake, state_path=str(tmp_path / "s.json"))
    cfg = p.default_config()
    cfg["polling_rate"] = 500
    eff = eng.apply(cfg)
    assert eff["polling_rate"] == 500
    assert len(fake.applied) == 1
    assert eng.get_state()["polling_rate"] == 500


def test_apply_defaults(tmp_path):
    fake = FakeDevice()
    eng = HatorEngine(device=fake, state_path=str(tmp_path / "s.json"))
    eff = eng.apply_defaults()
    assert eff["button_map"] == ["left", "right", "middle", "forward", "backward", "dpi"]
    assert fake.applied  # a sequence was sent


def test_apply_merges_over_saved(tmp_path):
    fake = FakeDevice()
    eng = HatorEngine(device=fake, state_path=str(tmp_path / "s.json"))
    eng.apply({"polling_rate": 250})
    # Now only override DPI; polling should remain 250 from saved state
    eng.apply({"active_slot": 2})
    eff = eng.get_state()
    assert eff["polling_rate"] == 250
    assert eff["active_slot"] == 2
