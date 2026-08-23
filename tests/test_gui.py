import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"),
    reason="no display for GTK smoke test",
)


def test_gui_imports_and_builds_window():
    import gui
    win = gui.build_window()
    assert win is not None
    win.destroy()
