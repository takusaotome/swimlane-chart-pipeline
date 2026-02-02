"""Tests for scripts/validate_chart.py — M4 (check_lane_balance sig), m4 (magic number)."""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestCheckLaneBalanceSignature:
    """M4: check_lane_balance should accept chart_plan only (not items + chart_plan)."""

    def test_check_lane_balance_accepts_chart_plan_only(self):
        """check_lane_balance should take chart_plan as its sole required argument."""
        from scripts.validate_chart import check_lane_balance

        sig = inspect.signature(check_lane_balance)
        params = list(sig.parameters.keys())

        # Should accept chart_plan as sole parameter (not items as first param)
        assert params[0] == "chart_plan", (
            f"M4: check_lane_balance first param should be 'chart_plan', got '{params[0]}'. "
            "The function only uses chart_plan data, so 'items' param is unnecessary."
        )


class TestBgSizeThresholdConstant:
    """m4: Background size threshold (500) should be a named constant."""

    def test_bg_size_threshold_is_named_constant(self):
        """The value 500 used to skip background shapes should be defined as a constant."""
        source_path = PROJECT_ROOT / "scripts" / "validate_chart.py"
        source = source_path.read_text()

        # Check that a named constant like BG_SIZE_THRESHOLD is defined
        assert "BG_SIZE_THRESHOLD" in source, (
            "m4: Magic number 500 for background size exclusion should be "
            "a named constant 'BG_SIZE_THRESHOLD'"
        )

    def test_check_overlaps_uses_constant(self):
        """check_overlaps should reference BG_SIZE_THRESHOLD, not inline 500."""
        source_path = PROJECT_ROOT / "scripts" / "validate_chart.py"
        source = source_path.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "check_overlaps":
                func_source = ast.get_source_segment(source, node)
                # Should not have raw "500" in comparisons
                assert "BG_SIZE_THRESHOLD" in func_source, (
                    "m4: check_overlaps should use BG_SIZE_THRESHOLD constant"
                )
                break


class TestCheckLaneBalanceFunctionality:
    """Functional tests for check_lane_balance."""

    def test_detects_empty_lane(self):
        """A lane with zero flow nodes should be reported."""
        from scripts.validate_chart import check_lane_balance

        chart_plan = {
            "lanes": ["A", "B"],
            "columns": ["C1"],
            "layout": {},
            "nodes": [
                {"key": "N1", "label": "T", "lane": "A", "col": 0, "kind": "task"},
                # Lane B has no nodes
            ],
        }
        findings = check_lane_balance(chart_plan)

        empty_findings = [f for f in findings if f["type"] == "empty_lane"]
        assert len(empty_findings) == 1
        assert empty_findings[0]["lane"] == "B"
