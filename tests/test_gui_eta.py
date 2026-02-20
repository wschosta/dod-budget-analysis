"""
Tests for build_budget_gui.py — _fmt_eta() helper

Tests the ETA formatting function in isolation (no Tkinter required).
The import is scoped to avoid loading Tkinter widgets.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock


# Mock tkinter entirely so we can import _fmt_eta without a display
_tk_mock = MagicMock()
sys.modules.setdefault("tkinter", _tk_mock)
sys.modules.setdefault("tkinter.ttk", _tk_mock)
sys.modules.setdefault("tkinter.filedialog", _tk_mock)
sys.modules.setdefault("tkinter.messagebox", _tk_mock)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_budget_gui import _fmt_eta  # noqa: E402


class TestFmtEta:
    def test_zero_seconds(self):
        assert _fmt_eta(0) == ""

    def test_negative_seconds(self):
        assert _fmt_eta(-5) == ""

    def test_under_minute(self):
        result = _fmt_eta(30)
        assert result == "~30s remaining"

    def test_exactly_one_minute(self):
        result = _fmt_eta(60)
        assert result == "~1m 00s remaining"

    def test_minutes_and_seconds(self):
        result = _fmt_eta(135)
        assert result == "~2m 15s remaining"

    def test_exactly_one_hour(self):
        result = _fmt_eta(3600)
        assert result == "~1h 00m remaining"

    def test_hours_and_minutes(self):
        result = _fmt_eta(3930)
        assert result == "~1h 05m remaining"

    def test_one_second(self):
        result = _fmt_eta(1)
        assert result == "~1s remaining"

    def test_59_seconds(self):
        result = _fmt_eta(59)
        assert result == "~59s remaining"

    def test_float_input(self):
        result = _fmt_eta(30.7)
        assert result == "~30s remaining"
