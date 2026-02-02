"""Tests for scripts/generate_chart.py — C1 (frame attach) and m3 (inline imports)."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest
import requests

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


class TestExceptionHandling:
    """C-01: generate_chart should handle exceptions and mark status as failed."""

    def test_status_set_to_failed_on_bulk_create_error(
        self, mock_miro, sample_chart_plan_path, tmp_path, monkeypatch
    ):
        """When bulk_create fails, miro_items.json should have status='failed'."""
        monkeypatch.setattr("scripts.generate_chart.PROJECT_ROOT", tmp_path)
        (tmp_path / "output").mkdir(exist_ok=True)

        # First bulk_create succeeds (background), second fails (flow nodes)
        call_count = 0

        def failing_bulk_create(items):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise requests.exceptions.HTTPError("500 Server Error")
            return [{"id": f"item-{i}", "type": "shape"} for i, _ in enumerate(items)]

        mock_miro.bulk_create.side_effect = failing_bulk_create

        from scripts.generate_chart import generate_chart

        with pytest.raises(requests.exceptions.HTTPError):
            generate_chart(sample_chart_plan_path, "test-run-id", api=mock_miro)

        miro_items_path = tmp_path / "output" / "test-run-id" / "miro_items.json"
        assert miro_items_path.exists(), "miro_items.json should be written even on failure"
        data = json.loads(miro_items_path.read_text())
        assert data["status"] == "failed"

    def test_frame_id_tracked_on_failure(
        self, mock_miro, sample_chart_plan_path, tmp_path, monkeypatch
    ):
        """On failure, frame_id should still be recorded in miro_items.json."""
        monkeypatch.setattr("scripts.generate_chart.PROJECT_ROOT", tmp_path)
        (tmp_path / "output").mkdir(exist_ok=True)

        mock_miro.bulk_create.side_effect = requests.exceptions.HTTPError("500")

        from scripts.generate_chart import generate_chart

        with pytest.raises(requests.exceptions.HTTPError):
            generate_chart(sample_chart_plan_path, "test-run-id", api=mock_miro)

        miro_items_path = tmp_path / "output" / "test-run-id" / "miro_items.json"
        data = json.loads(miro_items_path.read_text())
        assert data["frame_id"] == "frame-001"


class TestDIParameter:
    """Step 0-A: generate_chart() should accept an api parameter for dependency injection."""

    def test_generate_chart_accepts_api_parameter(
        self, mock_miro, sample_chart_plan_path, tmp_path, monkeypatch
    ):
        """generate_chart(path, run_id, api=mock) should use the injected api."""
        monkeypatch.setattr("scripts.generate_chart.PROJECT_ROOT", tmp_path)
        (tmp_path / "output").mkdir(exist_ok=True)

        from scripts.generate_chart import generate_chart

        generate_chart(sample_chart_plan_path, "test-run-id", api=mock_miro)
        assert mock_miro.bulk_create.called, "Injected api mock was not used"

    def test_generate_chart_uses_injected_api_not_default(
        self, mock_miro, sample_chart_plan_path, tmp_path, monkeypatch
    ):
        """When api is provided, MiroClient() should NOT be called."""
        monkeypatch.setattr("scripts.generate_chart.PROJECT_ROOT", tmp_path)
        (tmp_path / "output").mkdir(exist_ok=True)

        constructor_called = False

        def trap_constructor(*a, **kw):
            nonlocal constructor_called
            constructor_called = True
            raise AssertionError("MiroClient() should not be called when api is injected")

        monkeypatch.setattr("scripts.generate_chart.MiroClient", trap_constructor)

        from scripts.generate_chart import generate_chart

        generate_chart(sample_chart_plan_path, "test-run-id", api=mock_miro)
        assert not constructor_called


class TestInjectParentCopy:
    """M-04: inject_parent should not mutate original items."""

    def test_inject_parent_does_not_mutate_original(
        self, mock_miro, sample_chart_plan_path, tmp_path, monkeypatch
    ):
        """Items built by build_* functions should not be mutated by inject_parent."""
        monkeypatch.setattr("scripts.generate_chart.PROJECT_ROOT", tmp_path)
        (tmp_path / "output").mkdir(exist_ok=True)

        # Track items passed to bulk_create BEFORE inject_parent
        items_before_inject: list = []

        from src.swimlane_lib import build_background_items

        original_build_bg = build_background_items

        def patched_build_bg(*args, **kwargs):
            result = original_build_bg(*args, **kwargs)
            items_before_inject.extend(result)
            return result

        monkeypatch.setattr("scripts.generate_chart.build_background_items", patched_build_bg)

        from scripts.generate_chart import generate_chart

        generate_chart(sample_chart_plan_path, "test-run-id", api=mock_miro)

        # Original items (captured before inject_parent) should not have 'parent'
        for item in items_before_inject:
            assert "parent" not in item, "M-04: inject_parent mutated original item dicts"


class TestLogging:
    """M-01: generate_chart should use logging instead of print."""

    def test_generate_chart_logs_frame_creation(
        self, mock_miro, sample_chart_plan_path, tmp_path, monkeypatch, caplog
    ):
        """generate_chart should log frame creation via logging module."""
        import logging

        monkeypatch.setattr("scripts.generate_chart.PROJECT_ROOT", tmp_path)
        (tmp_path / "output").mkdir(exist_ok=True)

        from scripts.generate_chart import generate_chart

        with caplog.at_level(logging.INFO):
            generate_chart(sample_chart_plan_path, "test-run-id", api=mock_miro)

        assert any("Creating frame" in rec.message for rec in caplog.records), (
            "M-01: 'Creating frame' should be logged via logging module"
        )

    def test_generate_chart_no_print_statements(self):
        """generate_chart.py should not use print() for operational messages."""
        source_path = PROJECT_ROOT / "scripts" / "generate_chart.py"
        source = source_path.read_text()
        tree = ast.parse(source)

        print_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "print":
                    print_calls.append(f"line {node.lineno}")

        assert print_calls == [], f"M-01: generate_chart.py still uses print() at: {print_calls}"


class TestE2EMatrix:
    """C-08: E2E test matrix with multiple configurations."""

    @staticmethod
    def _make_plan(tmp_path, lanes, columns, nodes, edges, layout=None):
        plan = {
            "schema_version": "1.0",
            "title": "Test",
            "subtitle": "E2E",
            "lanes": lanes,
            "columns": columns,
            "layout": layout or {},
            "nodes": nodes,
            "edges": edges,
        }
        p = tmp_path / "plan.json"
        p.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
        return str(p)

    @staticmethod
    def _make_mock():
        from unittest.mock import MagicMock

        from src.swimlane_lib import MiroClient

        mock = MagicMock(spec=MiroClient)
        mock.board_id = "test-board"
        mock.find_rightmost_frame.return_value = (0, 0)
        mock.create_frame.return_value = {"id": "frame-e2e"}
        mock.bulk_create.side_effect = lambda items: [
            {"id": f"item-{i}", "type": it.get("type", "shape")} for i, it in enumerate(items)
        ]
        mock.create_connector.return_value = {"id": "conn-e2e"}
        return mock

    def test_minimal_config(self, tmp_path, monkeypatch):
        """1 lane, 1 column, 1 node, 0 edges."""
        monkeypatch.setattr("scripts.generate_chart.PROJECT_ROOT", tmp_path)
        (tmp_path / "output").mkdir(exist_ok=True)

        plan_path = self._make_plan(
            tmp_path,
            lanes=["A"],
            columns=["C1"],
            nodes=[{"key": "T1", "label": "Task", "lane": "A", "col": 0}],
            edges=[],
        )
        mock = self._make_mock()

        from scripts.generate_chart import generate_chart

        url = generate_chart(plan_path, "e2e-min", api=mock)
        assert "miro.com" in url
        # No connectors should be created
        mock.create_connector.assert_not_called()

    def test_large_config(self, tmp_path, monkeypatch):
        """10 lanes, 10 columns, many nodes."""
        monkeypatch.setattr("scripts.generate_chart.PROJECT_ROOT", tmp_path)
        (tmp_path / "output").mkdir(exist_ok=True)

        lanes = [f"Lane{i}" for i in range(10)]
        columns = [f"Col{i}" for i in range(10)]
        nodes = [
            {"key": f"N{i}", "label": f"Node {i}", "lane": lanes[i % 10], "col": i % 10}
            for i in range(30)
        ]
        edges = [{"src": f"N{i}", "dst": f"N{i + 1}"} for i in range(29)]

        plan_path = self._make_plan(tmp_path, lanes, columns, nodes, edges)
        mock = self._make_mock()

        from scripts.generate_chart import generate_chart

        url = generate_chart(plan_path, "e2e-large", api=mock)
        assert "miro.com" in url
        assert mock.create_connector.call_count == 29

    def test_error_recovery(self, tmp_path, monkeypatch):
        """bulk_create fails on 2nd call → status='failed'."""
        monkeypatch.setattr("scripts.generate_chart.PROJECT_ROOT", tmp_path)
        (tmp_path / "output").mkdir(exist_ok=True)

        plan_path = self._make_plan(
            tmp_path,
            lanes=["A"],
            columns=["C1"],
            nodes=[{"key": "T1", "label": "Task", "lane": "A", "col": 0}],
            edges=[],
        )
        mock = self._make_mock()
        call_count = 0

        def fail_on_second(items):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise requests.exceptions.HTTPError("500")
            return [{"id": f"item-{i}", "type": "shape"} for i, _ in enumerate(items)]

        mock.bulk_create.side_effect = fail_on_second

        from scripts.generate_chart import generate_chart

        with pytest.raises(requests.exceptions.HTTPError):
            generate_chart(plan_path, "e2e-fail", api=mock)

        miro_items = json.loads((tmp_path / "output" / "e2e-fail" / "miro_items.json").read_text())
        assert miro_items["status"] == "failed"

    def test_missing_edge_ref_skipped(self, tmp_path, monkeypatch, caplog):
        """Edge with unmapped node ID → connector skipped with warning."""
        import logging

        monkeypatch.setattr("scripts.generate_chart.PROJECT_ROOT", tmp_path)
        (tmp_path / "output").mkdir(exist_ok=True)

        plan_path = self._make_plan(
            tmp_path,
            lanes=["A"],
            columns=["C1", "C2"],
            nodes=[
                {"key": "T1", "label": "Task 1", "lane": "A", "col": 0},
                {"key": "T2", "label": "Task 2", "lane": "A", "col": 1},
            ],
            edges=[{"src": "T1", "dst": "T2"}],
        )
        mock = self._make_mock()

        # Make bulk_create return empty IDs for flow nodes → key_to_id will be empty
        call_count = 0

        def selective_bulk(items):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Background items — return normally
                return [{"id": f"bg-{i}", "type": "shape"} for i, _ in enumerate(items)]
            # Flow nodes — return items with empty IDs
            return [{"id": "", "type": "shape"} for _ in items]

        mock.bulk_create.side_effect = selective_bulk

        from scripts.generate_chart import generate_chart

        with caplog.at_level(logging.WARNING):
            url = generate_chart(plan_path, "e2e-skip", api=mock)

        assert "miro.com" in url
        mock.create_connector.assert_not_called()
        assert any("SKIP" in rec.message for rec in caplog.records)

    def test_all_node_kinds(self, tmp_path, monkeypatch):
        """All node kinds produce correct Miro shapes."""
        monkeypatch.setattr("scripts.generate_chart.PROJECT_ROOT", tmp_path)
        (tmp_path / "output").mkdir(exist_ok=True)

        plan_path = self._make_plan(
            tmp_path,
            lanes=["A"],
            columns=["C1", "C2", "C3", "C4", "C5"],
            nodes=[
                {"key": "S", "label": "Start", "lane": "A", "col": 0, "kind": "start"},
                {"key": "T", "label": "Task", "lane": "A", "col": 1, "kind": "task"},
                {"key": "D", "label": "?", "lane": "A", "col": 2, "kind": "decision"},
                {"key": "C", "label": "Sys", "lane": "A", "col": 3, "kind": "chip"},
                {"key": "E", "label": "End", "lane": "A", "col": 4, "kind": "end"},
            ],
            edges=[],
        )
        mock = self._make_mock()

        # Capture shapes from bulk_create calls
        all_items = []

        def capture_bulk(items):
            all_items.extend(items)
            return [{"id": f"item-{i}", "type": "shape"} for i, _ in enumerate(items)]

        mock.bulk_create.side_effect = capture_bulk

        from scripts.generate_chart import generate_chart

        generate_chart(plan_path, "e2e-kinds", api=mock)

        # Find flow node shapes (non-background items have specific shapes)
        flow_shapes = [
            it["data"]["shape"]
            for it in all_items
            if it["data"].get("shape") in ("circle", "rhombus", "round_rectangle")
            or (it["data"].get("shape") == "rectangle" and it.get("style", {}).get("borderColor"))
        ]
        assert "circle" in flow_shapes  # start or end
        assert "rhombus" in flow_shapes  # decision
        assert "round_rectangle" in flow_shapes  # chip


class TestFrameSideMargin:
    """Frame should be wider than the background box to create left/right margins."""

    def test_frame_wider_than_background(self, tmp_path, monkeypatch):
        """create_frame should be called with width > background box width."""
        from unittest.mock import MagicMock

        from src.swimlane_lib import Layout, MiroClient, swimlane_total_width

        mock = MagicMock(spec=MiroClient)
        mock.board_id = "test-board"
        mock.find_rightmost_frame.return_value = (0, 0)
        mock.create_frame.return_value = {"id": "frame-margin"}
        mock.bulk_create.side_effect = lambda items: [
            {"id": f"item-{i}", "type": it.get("type", "shape")} for i, it in enumerate(items)
        ]
        mock.create_connector.return_value = {"id": "conn-001"}

        plan_path = TestE2EMatrix._make_plan(
            tmp_path,
            lanes=["A", "B"],
            columns=["C1", "C2", "C3"],
            nodes=[{"key": "T1", "label": "Task", "lane": "A", "col": 0}],
            edges=[],
        )
        monkeypatch.setattr("scripts.generate_chart.PROJECT_ROOT", tmp_path)
        (tmp_path / "output").mkdir(exist_ok=True)

        from scripts.generate_chart import generate_chart

        generate_chart(plan_path, "e2e-margin", api=mock)

        # Extract the width passed to create_frame
        frame_w = mock.create_frame.call_args[1].get("w") or mock.create_frame.call_args[0][3]

        cfg = Layout()
        bg_w = swimlane_total_width(cfg, 3) + cfg.frame_padding

        assert frame_w > bg_w, (
            f"Frame width ({frame_w}) should be wider than background box ({bg_w}) "
            "to create left/right margins"
        )


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
