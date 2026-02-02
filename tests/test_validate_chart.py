"""Tests for scripts/validate_chart.py — M4 (check_lane_balance sig), m4 (magic number),
plus functional tests for all heuristic check functions."""

from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pytest

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

    def test_no_findings_when_all_lanes_have_nodes(self):
        """No findings when every lane has at least one flow node."""
        from scripts.validate_chart import check_lane_balance

        chart_plan = {
            "lanes": ["A", "B"],
            "nodes": [
                {"key": "N1", "label": "T", "lane": "A", "col": 0, "kind": "task"},
                {"key": "N2", "label": "T", "lane": "B", "col": 0, "kind": "task"},
            ],
        }
        findings = check_lane_balance(chart_plan)
        assert findings == []


# ---------------------------------------------------------------------------
# estimate_text_width
# ---------------------------------------------------------------------------


class TestEstimateTextWidth:
    """Tests for estimate_text_width()."""

    def test_latin_only(self):
        from scripts.validate_chart import LATIN_CHAR_WIDTH_PX, estimate_text_width

        width = estimate_text_width("Hello", font_size=14)
        assert width == LATIN_CHAR_WIDTH_PX * 5

    def test_japanese_only(self):
        from scripts.validate_chart import JAPANESE_CHAR_WIDTH_PX, estimate_text_width

        width = estimate_text_width("日本語", font_size=14)
        assert width == JAPANESE_CHAR_WIDTH_PX * 3

    def test_mixed_text(self):
        from scripts.validate_chart import (
            JAPANESE_CHAR_WIDTH_PX,
            LATIN_CHAR_WIDTH_PX,
            estimate_text_width,
        )

        # "A日" = 1 latin + 1 japanese
        width = estimate_text_width("A日", font_size=14)
        assert width == LATIN_CHAR_WIDTH_PX + JAPANESE_CHAR_WIDTH_PX

    def test_font_size_scaling(self):
        from scripts.validate_chart import estimate_text_width

        w14 = estimate_text_width("A", font_size=14)
        w28 = estimate_text_width("A", font_size=28)
        assert w28 == pytest.approx(w14 * 2)

    def test_empty_string(self):
        from scripts.validate_chart import estimate_text_width

        assert estimate_text_width("", font_size=14) == 0.0


# ---------------------------------------------------------------------------
# get_bbox
# ---------------------------------------------------------------------------


class TestGetBbox:
    """Tests for get_bbox()."""

    def test_valid_item(self):
        from scripts.validate_chart import get_bbox

        item = {
            "position": {"x": 100, "y": 200},
            "geometry": {"width": 170, "height": 80},
        }
        bbox = get_bbox(item)
        assert bbox == (100 - 85, 200 - 40, 100 + 85, 200 + 40)

    def test_missing_position(self):
        from scripts.validate_chart import get_bbox

        item = {"geometry": {"width": 100, "height": 50}}
        assert get_bbox(item) is None

    def test_missing_geometry(self):
        from scripts.validate_chart import get_bbox

        item = {"position": {"x": 0, "y": 0}}
        assert get_bbox(item) is None

    def test_partial_geometry(self):
        from scripts.validate_chart import get_bbox

        item = {"position": {"x": 0, "y": 0}, "geometry": {"width": 100}}
        assert get_bbox(item) is None


# ---------------------------------------------------------------------------
# boxes_overlap
# ---------------------------------------------------------------------------


class TestBoxesOverlap:
    """Tests for boxes_overlap()."""

    def test_overlapping_boxes(self):
        from scripts.validate_chart import boxes_overlap

        a = (0, 0, 100, 100)
        b = (50, 50, 150, 150)
        assert boxes_overlap(a, b) is True

    def test_non_overlapping_horizontal(self):
        from scripts.validate_chart import boxes_overlap

        a = (0, 0, 100, 100)
        b = (200, 0, 300, 100)
        assert boxes_overlap(a, b) is False

    def test_non_overlapping_vertical(self):
        from scripts.validate_chart import boxes_overlap

        a = (0, 0, 100, 100)
        b = (0, 200, 100, 300)
        assert boxes_overlap(a, b) is False

    def test_adjacent_within_margin(self):
        from scripts.validate_chart import boxes_overlap

        # Boxes are exactly 3px apart, but margin is 5 → overlap
        a = (0, 0, 100, 100)
        b = (103, 0, 200, 100)
        assert boxes_overlap(a, b, margin=5.0) is True

    def test_adjacent_outside_margin(self):
        from scripts.validate_chart import boxes_overlap

        # Boxes are 10px apart, margin is 5 → no overlap
        a = (0, 0, 100, 100)
        b = (115, 0, 200, 100)
        assert boxes_overlap(a, b, margin=5.0) is False


# ---------------------------------------------------------------------------
# check_overlaps
# ---------------------------------------------------------------------------


class TestCheckOverlaps:
    """Functional tests for check_overlaps()."""

    def _make_item(self, id_, x, y, w, h):
        return {
            "id": id_,
            "type": "shape",
            "data": {"content": f"Item {id_}"},
            "position": {"x": x, "y": y},
            "geometry": {"width": w, "height": h},
        }

    def test_detects_overlap(self):
        from scripts.validate_chart import check_overlaps

        items = [
            self._make_item("a", 100, 100, 170, 80),
            self._make_item("b", 150, 120, 170, 80),  # overlapping with a
        ]
        findings = check_overlaps(items)
        assert len(findings) == 1
        assert findings[0]["type"] == "overlap"

    def test_no_overlap(self):
        from scripts.validate_chart import check_overlaps

        items = [
            self._make_item("a", 0, 0, 100, 100),
            self._make_item("b", 500, 500, 100, 100),  # far away
        ]
        findings = check_overlaps(items)
        assert findings == []

    def test_skips_background_items(self):
        from scripts.validate_chart import check_overlaps

        items = [
            self._make_item("bg", 0, 0, 2000, 1000),  # large background
            self._make_item("a", 100, 100, 170, 80),
        ]
        findings = check_overlaps(items)
        assert findings == []

    def test_skips_non_shape_items(self):
        from scripts.validate_chart import check_overlaps

        items = [
            {
                "id": "t1",
                "type": "text",
                "data": {"content": "X"},
                "position": {"x": 100, "y": 100},
                "geometry": {"width": 170, "height": 80},
            },
            self._make_item("a", 100, 100, 170, 80),
        ]
        findings = check_overlaps(items)
        assert findings == []


# ---------------------------------------------------------------------------
# check_label_truncation
# ---------------------------------------------------------------------------


class TestCheckLabelTruncation:
    """Functional tests for check_label_truncation()."""

    def test_detects_truncation(self):
        from scripts.validate_chart import check_label_truncation

        items = [
            {
                "type": "shape",
                "data": {"content": "これは非常に長いテキストラベルです"},
                "geometry": {"width": 100, "height": 50},
                "style": {"fontSize": 14},
            },
        ]
        findings = check_label_truncation(items)
        assert len(findings) == 1
        assert findings[0]["type"] == "label_truncation"

    def test_no_truncation_for_short_label(self):
        from scripts.validate_chart import check_label_truncation

        items = [
            {
                "type": "shape",
                "data": {"content": "OK"},
                "geometry": {"width": 170, "height": 80},
                "style": {"fontSize": 14},
            },
        ]
        findings = check_label_truncation(items)
        assert findings == []

    def test_skips_empty_content(self):
        from scripts.validate_chart import check_label_truncation

        items = [
            {
                "type": "shape",
                "data": {"content": ""},
                "geometry": {"width": 50, "height": 50},
                "style": {},
            },
        ]
        findings = check_label_truncation(items)
        assert findings == []

    def test_skips_background_shapes(self):
        from scripts.validate_chart import check_label_truncation

        items = [
            {
                "type": "shape",
                "data": {"content": "Large content"},
                "geometry": {"width": 2000, "height": 1000},
                "style": {"fontSize": 14},
            },
        ]
        findings = check_label_truncation(items)
        assert findings == []


# ---------------------------------------------------------------------------
# check_connector_completeness
# ---------------------------------------------------------------------------


class TestCheckConnectorCompleteness:
    """Functional tests for check_connector_completeness()."""

    def test_all_connectors_present(self):
        from scripts.validate_chart import check_connector_completeness

        tracked = {
            "connectors": [
                {"src": "A", "dst": "B", "miro_id": "c1"},
                {"src": "B", "dst": "C", "miro_id": "c2"},
            ]
        }
        api_connectors = [{"id": "c1"}, {"id": "c2"}]
        findings = check_connector_completeness(tracked, api_connectors)
        assert findings == []

    def test_missing_connector(self):
        from scripts.validate_chart import check_connector_completeness

        tracked = {
            "connectors": [
                {"src": "A", "dst": "B", "miro_id": "c1"},
                {"src": "B", "dst": "C", "miro_id": "c2"},
            ]
        }
        api_connectors = [{"id": "c1"}]  # c2 is missing
        findings = check_connector_completeness(tracked, api_connectors)
        assert len(findings) == 1
        assert findings[0]["type"] == "missing_connector"
        assert findings[0]["severity"] == "Critical"
        assert findings[0]["miro_id"] == "c2"

    def test_empty_tracked(self):
        from scripts.validate_chart import check_connector_completeness

        findings = check_connector_completeness({"connectors": []}, [])
        assert findings == []


# ---------------------------------------------------------------------------
# validate() orchestration
# ---------------------------------------------------------------------------


class TestValidateOrchestration:
    """Tests for the validate() function end-to-end with mocked MiroClient."""

    def _write_miro_items(self, tmp_path, data):
        p = tmp_path / "miro_items.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return str(p)

    def _write_chart_plan(self, tmp_path, data):
        p = tmp_path / "chart_plan.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return str(p)

    def test_produces_report_with_pass_status(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        mock_api = MagicMock()
        mock_api.readback_frame_items.return_value = [
            {
                "id": "i1",
                "type": "shape",
                "data": {"content": "OK"},
                "position": {"x": 100, "y": 100},
                "geometry": {"width": 170, "height": 80},
                "style": {"fontSize": 14},
            },
        ]
        mock_api.get_connectors.return_value = {
            "data": [{"id": "c1"}],
        }

        monkeypatch.setattr("scripts.validate_chart.MiroClient", lambda: mock_api)

        miro_items_path = self._write_miro_items(
            tmp_path,
            {
                "run_id": "test-run",
                "frame_id": "frame-1",
                "items": [{"key": "T1", "miro_id": "i1"}],
                "connectors": [{"src": "A", "dst": "B", "miro_id": "c1"}],
            },
        )

        from scripts.validate_chart import validate

        report = validate(miro_items_path)

        assert report["run_id"] == "test-run"
        assert report["status"] == "pass"
        assert report["item_count"] == 1
        assert (tmp_path / "validation_report.json").exists()

    def test_produces_report_with_fail_status_on_overlap(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        mock_api = MagicMock()
        mock_api.readback_frame_items.return_value = [
            {
                "id": "i1",
                "type": "shape",
                "data": {"content": "A"},
                "position": {"x": 100, "y": 100},
                "geometry": {"width": 170, "height": 80},
                "style": {},
            },
            {
                "id": "i2",
                "type": "shape",
                "data": {"content": "B"},
                "position": {"x": 120, "y": 110},
                "geometry": {"width": 170, "height": 80},
                "style": {},
            },
        ]
        mock_api.get_connectors.return_value = {"data": []}

        monkeypatch.setattr("scripts.validate_chart.MiroClient", lambda: mock_api)

        miro_items_path = self._write_miro_items(
            tmp_path,
            {
                "run_id": "test-run",
                "frame_id": "frame-1",
                "items": [],
                "connectors": [],
            },
        )

        from scripts.validate_chart import validate

        report = validate(miro_items_path)

        assert report["status"] == "fail"
        overlap_findings = [f for f in report["findings"] if f["type"] == "overlap"]
        assert len(overlap_findings) >= 1

    def test_includes_lane_balance_when_chart_plan_provided(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        mock_api = MagicMock()
        mock_api.readback_frame_items.return_value = []
        mock_api.get_connectors.return_value = {"data": []}

        monkeypatch.setattr("scripts.validate_chart.MiroClient", lambda: mock_api)

        miro_items_path = self._write_miro_items(
            tmp_path,
            {
                "run_id": "test-run",
                "frame_id": "frame-1",
                "items": [],
                "connectors": [],
            },
        )
        chart_plan_path = self._write_chart_plan(
            tmp_path,
            {
                "lanes": ["A", "B"],
                "nodes": [
                    {"key": "N1", "label": "T", "lane": "A", "col": 0, "kind": "task"},
                ],
            },
        )

        from scripts.validate_chart import validate

        report = validate(miro_items_path, chart_plan_path)

        empty_lane = [f for f in report["findings"] if f["type"] == "empty_lane"]
        assert len(empty_lane) == 1
        assert empty_lane[0]["lane"] == "B"
