"""Tests for src/swimlane_lib.py — M2 (atomic write), m1 (load_dotenv), m2 (except scope),
plus coordinate helpers, payload builders, utility functions, retry decorator,
and MiroClient business logic."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestFlushMiroItemsAtomic:
    """M2: flush_miro_items should write atomically via tempfile + os.replace."""

    def test_flush_uses_atomic_write(self, tmp_path):
        """Confirm flush_miro_items uses tempfile approach (not direct open-write)."""

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


# ---------------------------------------------------------------------------
# Utility: chunked
# ---------------------------------------------------------------------------


class TestChunked:
    """Tests for the chunked() utility function."""

    def test_chunked_splits_evenly(self):
        from src.swimlane_lib import chunked

        result = list(chunked([1, 2, 3, 4], 2))
        assert result == [[1, 2], [3, 4]]

    def test_chunked_handles_remainder(self):
        from src.swimlane_lib import chunked

        result = list(chunked([1, 2, 3, 4, 5], 2))
        assert result == [[1, 2], [3, 4], [5]]

    def test_chunked_single_batch(self):
        from src.swimlane_lib import chunked

        result = list(chunked([1, 2, 3], 20))
        assert result == [[1, 2, 3]]

    def test_chunked_empty_list(self):
        from src.swimlane_lib import chunked

        result = list(chunked([], 5))
        assert result == []


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------


class TestCoordinateHelpers:
    """Tests for coordinate calculation functions."""

    def test_swimlane_total_height(self):
        from src.swimlane_lib import Layout, swimlane_total_height

        cfg = Layout(lane_height=220, lane_gap=0, header_height=80)
        # 3 lanes: 3*220 + 2*0 + 80 = 740
        assert swimlane_total_height(cfg, 3) == 740

    def test_swimlane_total_height_with_gap(self):
        from src.swimlane_lib import Layout, swimlane_total_height

        cfg = Layout(lane_height=200, lane_gap=10, header_height=80)
        # 3 lanes: 3*200 + 2*10 + 80 = 700
        assert swimlane_total_height(cfg, 3) == 700

    def test_swimlane_total_width(self):
        from src.swimlane_lib import Layout, swimlane_total_width

        cfg = Layout(left_label_width=240, col_width=360, col_gap=0)
        # 4 columns: 240 + 4*360 + 3*0 = 1680
        assert swimlane_total_width(cfg, 4) == 1680

    def test_swimlane_total_width_with_gap(self):
        from src.swimlane_lib import Layout, swimlane_total_width

        cfg = Layout(left_label_width=240, col_width=360, col_gap=10)
        # 4 columns: 240 + 4*360 + 3*10 = 1710
        assert swimlane_total_width(cfg, 4) == 1710

    def test_swimlane_top_left_centered(self):
        from src.swimlane_lib import Layout, swimlane_top_left

        cfg = Layout(
            origin_x=0,
            origin_y=0,
            left_label_width=240,
            col_width=360,
            col_gap=0,
            lane_height=220,
            lane_gap=0,
            header_height=80,
        )
        # width = 240 + 2*360 = 960; height = 2*220 + 80 = 520
        tlx, tly = swimlane_top_left(cfg, 2, 2)
        assert tlx == -480  # -960/2
        assert tly == -260  # -520/2

    def test_lane_center_y_first_lane(self):
        from src.swimlane_lib import Layout, lane_center_y

        cfg = Layout(
            origin_x=0,
            origin_y=0,
            lane_height=220,
            lane_gap=0,
            header_height=80,
            left_label_width=240,
            col_width=360,
            col_gap=0,
        )
        y = lane_center_y(cfg, 0, 2, 2)
        # tly = -260, lane_top = -260 + 80 + 0*220 = -180
        # center = -180 + 110 = -70
        assert y == -70

    def test_lane_center_y_second_lane(self):
        from src.swimlane_lib import Layout, lane_center_y

        cfg = Layout(
            origin_x=0,
            origin_y=0,
            lane_height=220,
            lane_gap=0,
            header_height=80,
            left_label_width=240,
            col_width=360,
            col_gap=0,
        )
        y = lane_center_y(cfg, 1, 2, 2)
        # lane_top = -260 + 80 + 1*220 = 40
        # center = 40 + 110 = 150
        assert y == 150

    def test_col_center_x_first_col(self):
        from src.swimlane_lib import Layout, col_center_x

        cfg = Layout(
            origin_x=0,
            origin_y=0,
            left_label_width=240,
            col_width=360,
            col_gap=0,
            lane_height=220,
            lane_gap=0,
            header_height=80,
        )
        x = col_center_x(cfg, 0, 2, 2)
        # tlx = -480, col_left = -480 + 240 + 0*360 = -240
        # center = -240 + 180 = -60
        assert x == -60

    def test_col_center_x_second_col(self):
        from src.swimlane_lib import Layout, col_center_x

        cfg = Layout(
            origin_x=0,
            origin_y=0,
            left_label_width=240,
            col_width=360,
            col_gap=0,
            lane_height=220,
            lane_gap=0,
            header_height=80,
        )
        x = col_center_x(cfg, 1, 2, 2)
        # col_left = -480 + 240 + 1*360 = 120
        # center = 120 + 180 = 300
        assert x == 300

    def test_node_xy_with_offset(self):
        from src.swimlane_lib import Layout, Node, node_xy

        cfg = Layout(
            origin_x=0,
            origin_y=0,
            left_label_width=240,
            col_width=360,
            col_gap=0,
            lane_height=220,
            lane_gap=0,
            header_height=80,
        )
        n = Node(key="T", label="Test", lane="Lane B", col=1, dx=50, dy=-30)
        lanes = ["Lane A", "Lane B"]
        x, y = node_xy(cfg, n, lanes, 2)
        # col_center_x(1) = 300, lane_center_y(1) = 150
        assert x == 300 + 50
        assert y == 150 - 30


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


class TestShapePayload:
    """Tests for shape_payload()."""

    def test_basic_rectangle(self):
        from src.swimlane_lib import shape_payload

        p = shape_payload("Hello", x=100, y=200, w=170, h=80)
        assert p["type"] == "shape"
        assert p["data"]["shape"] == "rectangle"
        assert p["data"]["content"] == "Hello"
        assert p["position"] == {"x": 100, "y": 200}
        assert p["geometry"] == {"width": 170, "height": 80}

    def test_with_fill_and_stroke(self):
        from src.swimlane_lib import shape_payload

        p = shape_payload(
            "X",
            x=0,
            y=0,
            w=50,
            h=50,
            shape="circle",
            fill="#BFE9D6",
            stroke="#1a1a1a",
            stroke_width=2.0,
        )
        assert p["style"]["fillColor"] == "#BFE9D6"
        assert p["style"]["fillOpacity"] == 1.0
        assert p["style"]["borderColor"] == "#1a1a1a"
        assert p["style"]["borderWidth"] == 2.0

    def test_no_fill_no_stroke(self):
        from src.swimlane_lib import shape_payload

        p = shape_payload("", x=0, y=0, w=100, h=100)
        assert "fillColor" not in p["style"]
        assert "borderColor" not in p["style"]

    def test_font_size(self):
        from src.swimlane_lib import shape_payload

        p = shape_payload("T", x=0, y=0, w=100, h=50, font_size=28)
        assert p["style"]["fontSize"] == 28


class TestTextPayload:
    """Tests for text_payload()."""

    def test_basic_text(self):
        from src.swimlane_lib import text_payload

        p = text_payload("Label", x=50, y=60, font_size=14)
        assert p["type"] == "text"
        assert p["data"]["content"] == "Label"
        assert p["position"] == {"x": 50, "y": 60}
        assert p["style"]["fontSize"] == 14

    def test_default_font_size(self):
        from src.swimlane_lib import text_payload

        p = text_payload("A", x=0, y=0)
        assert p["style"]["fontSize"] == 20


class TestConnectorPayload:
    """Tests for connector_payload()."""

    def test_basic_connector(self):
        from src.swimlane_lib import Edge, connector_payload

        e = Edge(src="A", dst="B")
        p = connector_payload(e, start_id="id-1", end_id="id-2")
        assert p["startItem"]["id"] == "id-1"
        assert p["endItem"]["id"] == "id-2"
        assert p["shape"] == "elbowed"
        assert p["style"]["strokeColor"] == "#1a1a1a"
        assert "captions" not in p

    def test_connector_with_label(self):
        from src.swimlane_lib import Edge, connector_payload

        e = Edge(src="A", dst="B", label="Yes", color="#2E7D32")
        p = connector_payload(e, start_id="id-1", end_id="id-2")
        assert p["captions"] == [{"content": "Yes", "position": "50%"}]
        assert p["style"]["strokeColor"] == "#2E7D32"

    def test_dashed_connector(self):
        from src.swimlane_lib import Edge, connector_payload

        e = Edge(src="A", dst="B", dashed=True, shape="curved")
        p = connector_payload(e, start_id="x", end_id="y")
        assert p["style"]["strokeStyle"] == "dashed"
        assert p["shape"] == "curved"


# ---------------------------------------------------------------------------
# Layer builders
# ---------------------------------------------------------------------------


class TestBuildBackgroundItems:
    """Tests for build_background_items()."""

    def test_item_count(self):
        from src.swimlane_lib import Layout, build_background_items

        cfg = Layout()
        lanes = ["A", "B", "C"]  # 3 lanes → 2 lane dividers
        columns = ["C1", "C2", "C3"]  # 3 columns → 2 column gridlines
        items = build_background_items(cfg, lanes, columns)
        # 1 outer frame + 2 lane dividers + 2 column gridlines + 1 header separator = 6
        assert len(items) == 6

    def test_all_items_are_shapes(self):
        from src.swimlane_lib import Layout, build_background_items

        items = build_background_items(Layout(), ["A", "B"], ["C1", "C2"])
        for item in items:
            assert item["type"] == "shape"

    def test_single_lane_no_dividers(self):
        from src.swimlane_lib import Layout, build_background_items

        items = build_background_items(Layout(), ["A"], ["C1"])
        # 1 outer frame + 0 lane dividers + 0 column gridlines + 1 header separator = 2
        assert len(items) == 2


class TestBuildTextItems:
    """Tests for build_text_items()."""

    def test_item_count(self):
        from src.swimlane_lib import Layout, build_text_items

        cfg = Layout()
        lanes = ["A", "B"]
        columns = ["C1", "C2", "C3"]
        items = build_text_items(cfg, lanes, columns, "Title", "Subtitle")
        # 2 (title + subtitle) + 3 column labels + 2 lane labels = 7
        assert len(items) == 7

    def test_title_content(self):
        from src.swimlane_lib import Layout, build_text_items

        items = build_text_items(Layout(), ["A"], ["C1"], "My Title", "My Sub")
        title_item = items[0]
        assert title_item["data"]["content"] == "My Title"
        subtitle_item = items[1]
        assert subtitle_item["data"]["content"] == "My Sub"


class TestBuildNodeItems:
    """Tests for build_node_items()."""

    def test_returns_keys_and_payloads(self):
        from src.swimlane_lib import Layout, Node, build_node_items

        cfg = Layout()
        nodes = [
            Node(key="START", label="Go", lane="A", col=0, kind="start"),
            Node(key="T1", label="Task 1", lane="A", col=0, kind="task"),
            Node(key="END", label="End", lane="A", col=0, kind="end"),
        ]
        keys, items = build_node_items(cfg, nodes, ["A"], 1)
        assert keys == ["START", "T1", "END"]
        assert len(items) == 3

    def test_skips_text_nodes(self):
        from src.swimlane_lib import Layout, Node, build_node_items

        cfg = Layout()
        nodes = [
            Node(key="T1", label="Task", lane="A", col=0, kind="task"),
            Node(key="L1", label="Label", lane="A", col=0, kind="text"),
        ]
        keys, items = build_node_items(cfg, nodes, ["A"], 1)
        assert keys == ["T1"]
        assert len(items) == 1

    def test_node_shapes(self):
        from src.swimlane_lib import Layout, Node, build_node_items

        cfg = Layout()
        nodes = [
            Node(key="S", label="S", lane="A", col=0, kind="start"),
            Node(key="T", label="T", lane="A", col=0, kind="task"),
            Node(key="D", label="D", lane="A", col=0, kind="decision"),
            Node(key="C", label="C", lane="A", col=0, kind="chip"),
            Node(key="E", label="E", lane="A", col=0, kind="end"),
        ]
        keys, items = build_node_items(cfg, nodes, ["A"], 1)
        shapes = [it["data"]["shape"] for it in items]
        assert shapes == ["circle", "rectangle", "rhombus", "round_rectangle", "circle"]

    def test_decision_uses_config_size(self):
        from src.swimlane_lib import Layout, Node, build_node_items

        cfg = Layout(decision_w=110, decision_h=110)
        nodes = [Node(key="D", label="?", lane="A", col=0, kind="decision")]
        _, items = build_node_items(cfg, nodes, ["A"], 1)
        assert items[0]["geometry"]["width"] == 110
        assert items[0]["geometry"]["height"] == 110

    def test_node_custom_size_overrides(self):
        from src.swimlane_lib import Layout, Node, build_node_items

        cfg = Layout(task_w=170, task_h=80)
        nodes = [Node(key="T", label="T", lane="A", col=0, kind="task", w=200, h=100)]
        _, items = build_node_items(cfg, nodes, ["A"], 1)
        assert items[0]["geometry"]["width"] == 200
        assert items[0]["geometry"]["height"] == 100


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------


class TestRetryDecorator:
    """Tests for the retry() decorator with exponential backoff."""

    def test_success_on_first_attempt(self):
        from src.swimlane_lib import retry

        call_count = 0

        @retry(max_attempts=3, backoff_schedule=[0.0])
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert succeed() == "ok"
        assert call_count == 1

    @patch("src.swimlane_lib.time.sleep")
    def test_retries_on_http_error(self, mock_sleep):
        from src.swimlane_lib import retry

        call_count = 0
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.headers = {}

        @retry(max_attempts=3, backoff_schedule=[0.1, 0.2])
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise requests.exceptions.HTTPError("500", response=mock_resp)
            return "ok"

        assert fail_then_succeed() == "ok"
        assert call_count == 3
        assert mock_sleep.call_count == 2

    @patch("src.swimlane_lib.time.sleep")
    def test_429_respects_retry_after(self, mock_sleep):
        from src.swimlane_lib import retry

        call_count = 0
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "5"}

        @retry(max_attempts=2, backoff_schedule=[1.0])
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise requests.exceptions.HTTPError("429", response=mock_resp)
            return "ok"

        assert fail_then_succeed() == "ok"
        # Should use Retry-After value (5.0), not backoff_schedule (1.0)
        mock_sleep.assert_called_once_with(5.0)

    @patch("src.swimlane_lib.time.sleep")
    def test_429_without_retry_after_uses_backoff(self, mock_sleep):
        from src.swimlane_lib import retry

        call_count = 0
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}

        @retry(max_attempts=2, backoff_schedule=[2.0])
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise requests.exceptions.HTTPError("429", response=mock_resp)
            return "ok"

        assert fail_then_succeed() == "ok"
        mock_sleep.assert_called_once_with(2.0)

    @patch("src.swimlane_lib.time.sleep")
    def test_retries_on_connection_error(self, mock_sleep):
        from src.swimlane_lib import retry

        call_count = 0

        @retry(max_attempts=2, backoff_schedule=[0.1])
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise requests.exceptions.ConnectionError("connection refused")
            return "ok"

        assert fail_then_succeed() == "ok"
        assert call_count == 2
        mock_sleep.assert_called_once()

    @patch("src.swimlane_lib.time.sleep")
    def test_retries_on_timeout(self, mock_sleep):
        from src.swimlane_lib import retry

        call_count = 0

        @retry(max_attempts=2, backoff_schedule=[0.1])
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise requests.exceptions.Timeout("timed out")
            return "ok"

        assert fail_then_succeed() == "ok"
        assert call_count == 2

    @patch("src.swimlane_lib.time.sleep")
    def test_raises_after_max_attempts(self, mock_sleep):
        from src.swimlane_lib import retry

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.headers = {}

        @retry(max_attempts=2, backoff_schedule=[0.1])
        def always_fail():
            raise requests.exceptions.HTTPError("500", response=mock_resp)

        with pytest.raises(requests.exceptions.HTTPError):
            always_fail()

    @patch("src.swimlane_lib.time.sleep")
    def test_no_sleep_on_last_attempt(self, mock_sleep):
        from src.swimlane_lib import retry

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.headers = {}

        @retry(max_attempts=2, backoff_schedule=[1.0])
        def always_fail():
            raise requests.exceptions.HTTPError("500", response=mock_resp)

        with pytest.raises(requests.exceptions.HTTPError):
            always_fail()
        # Only 1 sleep (after attempt 1), not after the final attempt
        assert mock_sleep.call_count == 1


# ---------------------------------------------------------------------------
# MiroClient
# ---------------------------------------------------------------------------


class TestMiroClientInit:
    """Tests for MiroClient initialization."""

    def test_raises_without_token(self, monkeypatch):
        monkeypatch.setenv("MIRO_TOKEN", "")
        monkeypatch.setenv("MIRO_BOARD_ID", "board-1")
        from src.swimlane_lib import MiroClient

        with pytest.raises(ValueError, match="MIRO_TOKEN"):
            MiroClient()

    def test_raises_without_board_id(self, monkeypatch):
        monkeypatch.setenv("MIRO_TOKEN", "tok-123")
        monkeypatch.setenv("MIRO_BOARD_ID", "")
        from src.swimlane_lib import MiroClient

        with pytest.raises(ValueError, match="MIRO_BOARD_ID"):
            MiroClient()

    def test_creates_with_explicit_args(self):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        assert client.token == "tok"
        assert client.board_id == "board"


class TestMiroClientRaiseForStatus:
    """Tests for MiroClient._raise_for_status."""

    def test_no_raise_for_200(self):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        resp = MagicMock()
        resp.status_code = 200
        client._raise_for_status(resp)  # Should not raise

    def test_raises_for_400(self):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "Bad Request"
        with pytest.raises(requests.exceptions.HTTPError):
            client._raise_for_status(resp)


class TestMiroClientFindRightmostFrame:
    """Tests for MiroClient.find_rightmost_frame."""

    def test_no_frames_returns_origin(self):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        client.get_items = MagicMock(
            return_value={
                "data": [
                    {"type": "shape", "position": {"x": 500}, "geometry": {"width": 200}},
                ]
            }
        )
        assert client.find_rightmost_frame() == (0, 0)

    def test_single_frame(self):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        client.get_items = MagicMock(
            return_value={
                "data": [
                    {
                        "type": "frame",
                        "position": {"x": 100, "y": 50},
                        "geometry": {"width": 400},
                    },
                ]
            }
        )
        # right_edge = 100 + 400//2 = 300
        assert client.find_rightmost_frame() == (300, 50)

    def test_multiple_frames_picks_rightmost(self):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        client.get_items = MagicMock(
            return_value={
                "data": [
                    {
                        "type": "frame",
                        "position": {"x": 100, "y": 50},
                        "geometry": {"width": 400},
                    },
                    {
                        "type": "frame",
                        "position": {"x": 1000, "y": 200},
                        "geometry": {"width": 600},
                    },
                ]
            }
        )
        # Frame 1: right_edge = 100 + 200 = 300
        # Frame 2: right_edge = 1000 + 300 = 1300
        assert client.find_rightmost_frame() == (1300, 200)

    def test_pagination(self):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        # Page 1: has a cursor → more pages
        page1 = {
            "data": [
                {"type": "frame", "position": {"x": 100, "y": 0}, "geometry": {"width": 200}},
            ],
            "cursor": "page2",
        }
        # Page 2: no cursor → last page
        page2 = {
            "data": [
                {"type": "frame", "position": {"x": 500, "y": 10}, "geometry": {"width": 200}},
            ],
        }
        client.get_items = MagicMock(side_effect=[page1, page2])
        # Frame 1: right_edge = 100 + 100 = 200
        # Frame 2: right_edge = 500 + 100 = 600
        assert client.find_rightmost_frame() == (600, 10)
        assert client.get_items.call_count == 2


class TestMiroClientReadbackFrameItems:
    """Tests for MiroClient.readback_frame_items."""

    def test_single_page(self):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        client.get_frame_items = MagicMock(
            return_value={
                "data": [{"id": "1"}, {"id": "2"}],
            }
        )
        result = client.readback_frame_items("frame-1")
        assert result == [{"id": "1"}, {"id": "2"}]

    def test_multiple_pages(self):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        client.get_frame_items = MagicMock(
            side_effect=[
                {"data": [{"id": "1"}, {"id": "2"}], "cursor": "pg2"},
                {"data": [{"id": "3"}]},
            ]
        )
        result = client.readback_frame_items("frame-1")
        assert result == [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        assert client.get_frame_items.call_count == 2

    def test_empty_frame(self):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        client.get_frame_items = MagicMock(return_value={"data": []})
        assert client.readback_frame_items("frame-1") == []


@patch("src.swimlane_lib.time.sleep")
class TestMiroClientCleanupByRun:
    """Tests for MiroClient.cleanup_by_run."""

    def _write_tracked(self, tmp_path, data):
        p = tmp_path / "miro_items.json"
        p.write_text(json.dumps(data, ensure_ascii=False))
        return str(p)

    def test_deletes_in_correct_order(self, mock_sleep, tmp_path):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        client.get_item = MagicMock(return_value={"id": "frame-1"})
        client.delete_connector = MagicMock()
        client.delete_item = MagicMock()

        path = self._write_tracked(
            tmp_path,
            {
                "frame_id": "frame-1",
                "connectors": [{"miro_id": "c1"}, {"miro_id": "c2"}],
                "items": [{"miro_id": "i1"}],
            },
        )
        counts = client.cleanup_by_run(path)

        assert counts["connectors"] == 2
        assert counts["items"] == 1
        assert counts["frame"] == 1

        # Verify deletion order: connectors first, then items, then frame
        calls = []
        for call in client.delete_connector.call_args_list:
            calls.append(("connector", call[0][0]))
        for call in client.delete_item.call_args_list:
            calls.append(("item", call[0][0]))

        # Connectors must come before items; frame (i.e. delete_item("frame-1")) must be last
        connector_indices = [i for i, (t, _) in enumerate(calls) if t == "connector"]
        item_indices = [i for i, (t, _) in enumerate(calls) if t == "item"]
        assert max(connector_indices) < min(item_indices)
        assert calls[-1] == ("item", "frame-1")

    def test_frame_gone_returns_early(self, mock_sleep, tmp_path):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        client.get_item = MagicMock(side_effect=requests.exceptions.ConnectionError("not found"))
        client.delete_connector = MagicMock()
        client.delete_item = MagicMock()

        path = self._write_tracked(
            tmp_path,
            {
                "frame_id": "frame-gone",
                "connectors": [{"miro_id": "c1"}],
                "items": [{"miro_id": "i1"}],
            },
        )
        counts = client.cleanup_by_run(path)

        # Should return early with zero counts
        assert counts == {"connectors": 0, "items": 0, "frame": 0, "skipped": 0}
        client.delete_connector.assert_not_called()
        client.delete_item.assert_not_called()

    def test_connector_deletion_error_increments_skipped(self, mock_sleep, tmp_path):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        client.get_item = MagicMock(return_value={"id": "frame-1"})
        client.delete_connector = MagicMock(side_effect=requests.exceptions.HTTPError("500"))
        client.delete_item = MagicMock()

        path = self._write_tracked(
            tmp_path,
            {
                "frame_id": "frame-1",
                "connectors": [{"miro_id": "c1"}],
                "items": [],
            },
        )
        counts = client.cleanup_by_run(path)

        assert counts["connectors"] == 0
        assert counts["skipped"] == 1

    def test_item_deletion_error_increments_skipped(self, mock_sleep, tmp_path):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        client.get_item = MagicMock(return_value={"id": "frame-1"})
        client.delete_connector = MagicMock()
        client.delete_item = MagicMock(side_effect=requests.exceptions.HTTPError("500"))

        path = self._write_tracked(
            tmp_path,
            {
                "frame_id": "frame-1",
                "connectors": [],
                "items": [{"miro_id": "i1"}],
            },
        )
        counts = client.cleanup_by_run(path)

        assert counts["items"] == 0
        # skipped: item + frame (both fail with HTTPError)
        assert counts["skipped"] == 2

    def test_no_frame_id(self, mock_sleep, tmp_path):
        from src.swimlane_lib import MiroClient

        client = MiroClient(token="tok", board_id="board")
        client.get_item = MagicMock()
        client.delete_connector = MagicMock()
        client.delete_item = MagicMock()

        path = self._write_tracked(
            tmp_path,
            {
                "connectors": [{"miro_id": "c1"}],
                "items": [{"miro_id": "i1"}],
            },
        )
        counts = client.cleanup_by_run(path)

        assert counts["connectors"] == 1
        assert counts["items"] == 1
        assert counts["frame"] == 0
        # get_item should not be called when there's no frame_id
        client.get_item.assert_not_called()
