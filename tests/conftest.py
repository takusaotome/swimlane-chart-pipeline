"""Shared test fixtures for swimlane-chart tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set dummy env vars before any import touches MiroClient
os.environ.setdefault("MIRO_TOKEN", "test-token")
os.environ.setdefault("MIRO_BOARD_ID", "test-board-id")


@pytest.fixture
def mock_miro(monkeypatch):
    """Return a MagicMock that replaces MiroClient for unit tests."""
    from src.swimlane_lib import MiroClient

    mock = MagicMock(spec=MiroClient)
    mock.board_id = "test-board-id"
    mock.find_rightmost_frame.return_value = (0, 0)
    mock.create_frame.return_value = {"id": "frame-001"}
    mock.bulk_create.side_effect = lambda items: [
        {"id": f"item-{i}", "type": it.get("type", "shape")} for i, it in enumerate(items)
    ]
    mock.create_connector.return_value = {"id": "conn-001"}
    mock.attach_to_frame.return_value = None

    monkeypatch.setattr("src.swimlane_lib.MiroClient", lambda *a, **kw: mock)
    return mock


@pytest.fixture
def sample_chart_plan_path(tmp_path):
    """Write a minimal valid chart_plan.json and return its path."""
    import json

    plan = {
        "schema_version": "1.0",
        "title": "Test Chart",
        "subtitle": "For testing",
        "lanes": ["Lane A", "Lane B"],
        "columns": ["Phase 1", "Phase 2"],
        "layout": {},
        "nodes": [
            {"key": "START", "label": "Start", "lane": "Lane A", "col": 0, "kind": "start"},
            {"key": "TASK1", "label": "Task 1", "lane": "Lane A", "col": 1, "kind": "task"},
            {"key": "END", "label": "End", "lane": "Lane B", "col": 1, "kind": "end"},
        ],
        "edges": [
            {"src": "START", "dst": "TASK1"},
            {"src": "TASK1", "dst": "END"},
        ],
    }
    p = tmp_path / "chart_plan.json"
    p.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    return str(p)
