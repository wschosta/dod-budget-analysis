"""
Tests for GuiProgressTracker to guard against the tkinter StringVar
deallocator 'main thread is not in main loop' RuntimeError.

Root cause
----------
``StringVar.__del__`` calls into the Tcl interpreter.  If Python's garbage
collector runs these destructors from the *main* thread — which happens at
interpreter shutdown — after the GUI daemon thread has already exited, tkinter
raises::

    RuntimeError: main thread is not in main loop

The fix adds ``_cleanup_vars()`` which deletes all StringVar instance attributes
and forces ``gc.collect()`` **on the GUI thread** while the Tcl interpreter is
still valid.  This is called from both ``_on_close()`` and ``_do_close()``
(scheduled via ``root.after()`` by ``close()``).

Test strategy
-------------
* Unit tests (no display required): verify ``_cleanup_vars()``, ``_on_close()``,
  ``_do_close()``, and ``close()`` behave correctly using mock objects.
* Integration test (requires a display / xvfb): run a real
  ``GuiProgressTracker`` lifecycle in a subprocess and assert that
  "main thread is not in main loop" never appears in stderr.
"""

import gc
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# dod_budget_downloader requires bs4 (beautifulsoup4) which may not be installed
pytest.importorskip("bs4", reason="bs4 (beautifulsoup4) not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Every StringVar attribute created by _run_gui() that _cleanup_vars() must delete.
_STRINGVAR_ATTRS = (
    '_src_var',
    '_overall_lbl',
    '_stats_var',
    '_file_lbl',
    '_file_stats_var',
    '_count_var',
)

PROJECT_ROOT = Path(__file__).parent.parent


def _make_tracker_stub():
    """Return a GuiProgressTracker instance without starting the GUI thread.

    Uses ``object.__new__`` to skip ``__init__``, then sets ``_closed = True``
    to prevent any incidental GUI activity from methods under test.
    """
    from dod_budget_downloader import GuiProgressTracker
    tracker = object.__new__(GuiProgressTracker)
    tracker._closed = True
    return tracker


def _attach_mock_stringvars(tracker):
    """Set a MagicMock for each StringVar attribute on *tracker*."""
    for name in _STRINGVAR_ATTRS:
        setattr(tracker, name, MagicMock(name=f'MockStringVar:{name}'))


def _has_display() -> bool:
    """Return True if a graphical display is available for tkinter."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.destroy()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Unit tests — no display required
# ---------------------------------------------------------------------------

class TestCleanupVars:
    """_cleanup_vars() must remove all StringVar references on the GUI thread."""

    def test_removes_all_stringvar_attributes(self):
        """Every StringVar attribute is deleted after _cleanup_vars()."""
        tracker = _make_tracker_stub()
        _attach_mock_stringvars(tracker)

        tracker._cleanup_vars()

        for name in _STRINGVAR_ATTRS:
            assert not hasattr(tracker, name), (
                f"StringVar attribute '{name}' still present after _cleanup_vars().\n"
                f"Its __del__ will be invoked from the wrong thread at interpreter "
                f"exit, causing 'main thread is not in main loop'."
            )

    def test_idempotent(self):
        """Calling _cleanup_vars() twice must not raise."""
        tracker = _make_tracker_stub()
        _attach_mock_stringvars(tracker)

        tracker._cleanup_vars()
        tracker._cleanup_vars()  # second call: all attrs already absent

    def test_tolerates_partially_initialised_tracker(self):
        """_cleanup_vars() must not raise if some StringVars were never created.

        This can happen if the GUI thread fails to start before close() is
        called, leaving some attrs unset.
        """
        tracker = _make_tracker_stub()
        # Only set a subset of the expected StringVar attrs
        tracker._src_var = MagicMock()
        tracker._file_lbl = MagicMock()
        # _overall_lbl, _stats_var, _file_stats_var, _count_var are absent

        tracker._cleanup_vars()  # must not raise AttributeError

        assert not hasattr(tracker, '_src_var')
        assert not hasattr(tracker, '_file_lbl')

    def test_unrelated_attributes_are_preserved(self):
        """_cleanup_vars() must not delete attributes outside the StringVar list."""
        tracker = _make_tracker_stub()
        _attach_mock_stringvars(tracker)
        tracker._some_other_attr = "keep me"

        tracker._cleanup_vars()

        assert tracker._some_other_attr == "keep me"


class TestDoClose:
    """_do_close() must clean up StringVars before destroying root."""

    def test_cleanup_runs_before_destroy(self):
        """_do_close() invokes _cleanup_vars() then root.destroy(), in that order."""
        tracker = _make_tracker_stub()
        _attach_mock_stringvars(tracker)

        call_order = []

        def recording_cleanup():
            call_order.append('cleanup')
            for attr in _STRINGVAR_ATTRS:
                if hasattr(tracker, attr):
                    delattr(tracker, attr)

        mock_root = MagicMock()
        mock_root.destroy.side_effect = lambda: call_order.append('destroy')
        tracker._root = mock_root
        tracker._cleanup_vars = recording_cleanup

        tracker._do_close()

        assert call_order == ['cleanup', 'destroy'], (
            f"_do_close() must call cleanup before destroy; got: {call_order}"
        )

    def test_stringvars_gone_after_do_close(self):
        """StringVar attributes are absent after _do_close() completes."""
        tracker = _make_tracker_stub()
        _attach_mock_stringvars(tracker)
        tracker._root = MagicMock()

        tracker._do_close()

        for name in _STRINGVAR_ATTRS:
            assert not hasattr(tracker, name), (
                f"'{name}' still present after _do_close()"
            )


class TestOnClose:
    """_on_close() must set _closed, clean up StringVars, then destroy root."""

    def test_sets_closed_flag(self):
        tracker = _make_tracker_stub()
        tracker._closed = False
        tracker._root = MagicMock()

        tracker._on_close()

        assert tracker._closed is True

    def test_cleanup_runs_before_destroy(self):
        tracker = _make_tracker_stub()
        tracker._closed = False
        _attach_mock_stringvars(tracker)

        call_order = []

        def recording_cleanup():
            call_order.append('cleanup')
            for attr in _STRINGVAR_ATTRS:
                if hasattr(tracker, attr):
                    delattr(tracker, attr)

        mock_root = MagicMock()
        mock_root.destroy.side_effect = lambda: call_order.append('destroy')
        tracker._root = mock_root
        tracker._cleanup_vars = recording_cleanup

        tracker._on_close()

        assert call_order == ['cleanup', 'destroy'], (
            f"_on_close() must call cleanup before destroy; got: {call_order}"
        )


class TestClose:
    """close() must schedule _do_close (not root.destroy) via root.after()."""

    def test_schedules_do_close_not_root_destroy(self):
        """root.after() must be called with _do_close, not _root.destroy.

        Scheduling _root.destroy directly would skip _cleanup_vars(), leaving
        StringVars alive to be collected by the main thread at shutdown.
        """
        tracker = _make_tracker_stub()
        tracker._closed = False
        tracker._root = MagicMock()

        tracker.close()

        tracker._root.after.assert_called_once()
        _, scheduled_fn = tracker._root.after.call_args[0]

        assert scheduled_fn.__name__ == '_do_close', (
            f"close() must schedule '_do_close', got '{scheduled_fn.__name__}'.\n"
            f"Scheduling '_root.destroy' directly bypasses StringVar cleanup."
        )
        assert scheduled_fn.__self__ is tracker

    def test_scheduled_fn_cleans_up_stringvars(self):
        """The function scheduled by close() actually removes StringVar attrs."""
        tracker = _make_tracker_stub()
        tracker._closed = False
        _attach_mock_stringvars(tracker)
        tracker._root = MagicMock()

        tracker.close()

        # Simulate the event-loop calling the scheduled function
        _, scheduled_fn = tracker._root.after.call_args[0]
        scheduled_fn()

        for name in _STRINGVAR_ATTRS:
            assert not hasattr(tracker, name), (
                f"'{name}' still present after the function scheduled by close() ran"
            )

    def test_no_op_when_already_closed(self):
        """close() is a no-op when _closed is already True."""
        tracker = _make_tracker_stub()
        tracker._closed = True
        tracker._root = MagicMock()

        tracker.close()

        tracker._root.after.assert_not_called()

    def test_no_op_when_root_not_set(self):
        """close() is a no-op when _root has not been created yet."""
        tracker = _make_tracker_stub()
        tracker._closed = False
        # _root intentionally absent

        tracker.close()  # must not raise AttributeError


# ---------------------------------------------------------------------------
# Integration test — requires a display (skipped in headless CI without xvfb)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _has_display(),
    reason=(
        "requires a graphical display — run with "
        "'xvfb-run pytest tests/test_gui_tracker.py' in headless CI"
    ),
)
def test_no_deallocator_error_on_close():
    """No 'main thread is not in main loop' in stderr after full tracker lifecycle.

    Runs a subprocess that creates a real GuiProgressTracker, closes it, and
    forces GC from the main thread — exactly the sequence that triggered the
    original bug.  Asserts the error string is absent from stderr.
    """
    script = textwrap.dedent("""
        import sys, gc, time
        sys.path.insert(0, '.')
        from dod_budget_downloader import GuiProgressTracker

        tracker = GuiProgressTracker(total_files=3)
        time.sleep(0.3)   # let the GUI thread start and render
        tracker.close()
        time.sleep(0.3)   # let close() / _do_close() complete on GUI thread
        del tracker
        gc.collect()      # force GC from main thread — this triggered the bug
    """)

    result = subprocess.run(
        [sys.executable, '-c', script],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(PROJECT_ROOT),
    )

    assert "main thread is not in main loop" not in result.stderr, (
        "StringVar deallocator error detected — cleanup on close is broken:\n"
        + result.stderr
    )
