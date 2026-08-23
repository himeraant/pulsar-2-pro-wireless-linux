import json
from engine import protocol as p
from engine.state import load_state, save_state, default_state_path


def test_save_load_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    cfg = p.default_config()
    cfg["polling_rate"] = 500
    cfg["cpi"] = [400, 800, 1600]
    save_state(cfg, path)
    loaded = load_state(path)
    assert loaded["polling_rate"] == 500
    assert loaded["cpi"] == [400, 800, 1600]


def test_load_missing_returns_none(tmp_path):
    path = str(tmp_path / "nope.json")
    assert load_state(path) is None


def test_default_state_path_under_config():
    assert "hator" in default_state_path()


def test_load_non_dict_json_returns_none(tmp_path):
    path = str(tmp_path / "state.json")
    with open(path, "w") as f:
        json.dump([1, 2, 3], f)
    assert load_state(path) is None

