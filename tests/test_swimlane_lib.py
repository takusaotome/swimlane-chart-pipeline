"""Tests for src/swimlane_lib.py — M2 (atomic write), m1 (load_dotenv), m2 (except scope)."""

from __future__ import annotations

import ast
import json
import os
import sys
import threading
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestFlushMiroItemsAtomic:
    """M2: flush_miro_items should write atomically via tempfile + os.replace."""

    def test_flush_uses_atomic_write(self, tmp_path):
        """Confirm flush_miro_items uses tempfile approach (not direct open-write)."""
        from src.swimlane_lib import flush_miro_items

        source_path = PROJECT_ROOT / "src" / "swimlane_lib.py"
        source = source_path.read_text()

        # Check that the implementation uses os.replace or os.rename for atomicity
        assert "os.replace" in source or "os.rename" in source, (
            "M2: flush_miro_items should use os.replace() for atomic writes"
        )

    def test_flush_writes_valid_json(self, tmp_path):
        """Flush should produce a valid, complete JSON file."""
        from src.swimlane_lib import flush_miro_items

        path = str(tmp_path / "miro_items.json")
        flush_miro_items(
            path=path,
            run_id="test-run",
            board_id="board-1",
            frame_id="frame-1",
            items=[{"key": "A", "miro_id": "1"}],
            connectors=[],
            status="completed",
        )

        with open(path, "r") as f:
            data = json.load(f)

        assert data["run_id"] == "test-run"
        assert data["status"] == "completed"
        assert len(data["items"]) == 1


class TestLoadDotenvPlacement:
    """m1: load_dotenv() should be inside MiroClient.__init__, not module-level."""

    def test_no_module_level_load_dotenv(self):
        """load_dotenv() should not be called at module level in swimlane_lib.py."""
        source_path = PROJECT_ROOT / "src" / "swimlane_lib.py"
        source = source_path.read_text()
        tree = ast.parse(source)

        # Find top-level function calls to load_dotenv
        module_level_calls = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Name) and func.id == "load_dotenv":
                    module_level_calls.append(f"line {node.lineno}")

        assert module_level_calls == [], (
            f"m1: load_dotenv() is called at module level: {module_level_calls}. "
            "It should be inside MiroClient.__init__() instead."
        )


class TestExceptionScope:
    """m2: cleanup_by_run should catch requests.exceptions.RequestException, not bare Exception."""

    def test_no_bare_except_exception(self):
        """cleanup_by_run should not use 'except Exception'."""
        source_path = PROJECT_ROOT / "src" / "swimlane_lib.py"
        source = source_path.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "cleanup_by_run":
                    for child in ast.walk(node):
                        if isinstance(child, ast.ExceptHandler):
                            if child.type and isinstance(child.type, ast.Name):
                                assert child.type.id != "Exception", (
                                    f"m2: line {child.lineno}: cleanup_by_run uses "
                                    "'except Exception' — should be "
                                    "'except requests.exceptions.RequestException'"
                                )
