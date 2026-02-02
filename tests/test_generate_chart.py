"""Tests for scripts/generate_chart.py — C1 (frame attach) and m3 (inline imports)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestFrameAttach:
    """C1: Items created by generate_chart must be attached to the frame."""

    def test_generate_chart_attaches_items_to_frame(self, mock_miro, sample_chart_plan_path, tmp_path, monkeypatch):
        """After generate_chart, attach_to_frame must be called at least once."""
        monkeypatch.setattr(
            "scripts.generate_chart.MiroClient", lambda *a, **kw: mock_miro,
        )
        monkeypatch.setattr(
            "scripts.generate_chart.PROJECT_ROOT", tmp_path,
        )
        (tmp_path / "output").mkdir(exist_ok=True)

        from scripts.generate_chart import generate_chart

        generate_chart(sample_chart_plan_path, "test-run-id")
        assert mock_miro.attach_to_frame.called, (
            "C1: attach_to_frame was never called — items are not attached to the frame"
        )

    def test_attach_receives_created_item_ids(self, mock_miro, sample_chart_plan_path, tmp_path, monkeypatch):
        """attach_to_frame should receive the IDs returned by bulk_create."""
        monkeypatch.setattr(
            "scripts.generate_chart.MiroClient", lambda *a, **kw: mock_miro,
        )
        monkeypatch.setattr(
            "scripts.generate_chart.PROJECT_ROOT", tmp_path,
        )
        (tmp_path / "output").mkdir(exist_ok=True)

        from scripts.generate_chart import generate_chart

        generate_chart(sample_chart_plan_path, "test-run-id")
        all_ids = []
        for call in mock_miro.attach_to_frame.call_args_list:
            args, kwargs = call
            all_ids.extend(args[1] if len(args) > 1 else kwargs.get("item_ids", []))
        assert len(all_ids) > 0, "attach_to_frame was called but with no item IDs"


class TestInlineImports:
    """m3: Function-level imports should be at file top."""

    def test_no_function_level_imports(self):
        """generate_chart.py should not have import statements inside functions."""
        source_path = PROJECT_ROOT / "scripts" / "generate_chart.py"
        source = source_path.read_text()
        tree = ast.parse(source)

        function_imports = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if isinstance(child, (ast.Import, ast.ImportFrom)):
                        function_imports.append(
                            f"line {child.lineno}: {ast.dump(child)}"
                        )

        assert function_imports == [], (
            f"m3: Found imports inside functions:\n" + "\n".join(function_imports)
        )
