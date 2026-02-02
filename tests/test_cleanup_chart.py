"""Tests for scripts/cleanup_chart.py — C2 (interactive input in non-TTY)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def miro_items_file(tmp_path):
    """Create a sample miro_items.json for testing."""
    data = {
        "run_id": "test-run",
        "board_id": "test-board",
        "frame_id": "frame-001",
        "items": [
            {"key": "ITEM1", "miro_id": "id-1", "type": "shape"},
            {"key": "ITEM2", "miro_id": "id-2", "type": "shape"},
        ],
        "connectors": [
            {"src": "ITEM1", "dst": "ITEM2", "miro_id": "conn-1"},
        ],
        "status": "completed",
    }
    p = tmp_path / "miro_items.json"
    p.write_text(json.dumps(data))
    return str(p)


class TestNonTTYSafety:
    """C2: cleanup_chart must not call input() in non-TTY environments."""

    def test_cleanup_aborts_on_non_tty_without_force(self, miro_items_file, monkeypatch):
        """In non-TTY mode without --force, should NOT call input(); should abort or skip."""
        mock_api = MagicMock()
        mock_api.board_id = "test-board"
        # Mismatch: tracked has 2 items, API returns 3 → triggers confirmation path
        mock_api.get_frame_items.return_value = {
            "data": [{"id": "x"}, {"id": "y"}, {"id": "z"}],
            "cursor": None,
        }

        monkeypatch.setattr("scripts.cleanup_chart.MiroClient", lambda *a, **kw: mock_api)

        # Simulate non-TTY stdin
        fake_stdin = io.StringIO("")
        monkeypatch.setattr("sys.stdin", fake_stdin)

        input_called = False
        original_input = __builtins__["input"] if isinstance(__builtins__, dict) else __builtins__.input

        def trap_input(prompt=""):
            nonlocal input_called
            input_called = True
            raise EOFError("input() called in non-TTY")

        monkeypatch.setattr("builtins.input", trap_input)

        from scripts.cleanup_chart import cleanup

        # Should not raise EOFError (i.e., should not call input)
        try:
            cleanup(miro_items_file, force=False)
        except (EOFError, SystemExit):
            pass

        assert not input_called, (
            "C2: input() was called in non-TTY environment — "
            "cleanup_chart should check sys.stdin.isatty() first"
        )
