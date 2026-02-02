"""Tests for scripts/generate_chart.py — C1 (frame attach) and m3 (inline imports)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestFrameAttach:
    """C1: Items created by generate_chart must be attached to the frame via inject_parent."""

    def test_generate_chart_injects_parent_into_bulk_items(
        self, mock_miro, sample_chart_plan_path, tmp_path, monkeypatch
    ):
        """bulk_create must receive items with parent.id set to the frame ID."""
        monkeypatch.setattr(
            "scripts.generate_chart.MiroClient",
            lambda *a, **kw: mock_miro,
        )
        monkeypatch.setattr(
            "scripts.generate_chart.PROJECT_ROOT",
            tmp_path,
        )
        (tmp_path / "output").mkdir(exist_ok=True)

        from scripts.generate_chart import generate_chart

        generate_chart(sample_chart_plan_path, "test-run-id")
        assert mock_miro.bulk_create.called, "bulk_create was never called"
        for call in mock_miro.bulk_create.call_args_list:
            items = call[0][0]
            for item in items:
                assert "parent" in item, (
                    "C1: inject_parent was not applied — item missing 'parent' field"
                )
                assert item["parent"]["id"] == "frame-001", (
                    f"C1: parent.id should be 'frame-001', got '{item['parent']['id']}'"
                )

    def test_all_bulk_items_have_parent(
        self, mock_miro, sample_chart_plan_path, tmp_path, monkeypatch
    ):
        """Every item passed to bulk_create should have the parent field."""
        monkeypatch.setattr(
            "scripts.generate_chart.MiroClient",
            lambda *a, **kw: mock_miro,
        )
        monkeypatch.setattr(
            "scripts.generate_chart.PROJECT_ROOT",
            tmp_path,
        )
        (tmp_path / "output").mkdir(exist_ok=True)

        from scripts.generate_chart import generate_chart

        generate_chart(sample_chart_plan_path, "test-run-id")
        total_items = 0
        for call in mock_miro.bulk_create.call_args_list:
            items = call[0][0]
            total_items += len(items)
            for item in items:
                assert item.get("parent", {}).get("id") == "frame-001"
        assert total_items > 0, "No items were sent to bulk_create"


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
                        function_imports.append(f"line {child.lineno}: {ast.dump(child)}")

        assert function_imports == [], "m3: Found imports inside functions:\n" + "\n".join(
            function_imports
        )
