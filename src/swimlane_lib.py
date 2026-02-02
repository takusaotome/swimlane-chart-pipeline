"""Swimlane chart core library.

Provides dataclasses, coordinate calculations, Miro payload builders,
and API client with retry logic for generating swimlane charts on Miro.
"""

from __future__ import annotations

import json
import os
import time
import functools
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    TypeVar,
)

import requests
from dotenv import load_dotenv

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# Retry decorator with exponential backoff
# ---------------------------------------------------------------------------

def retry(max_attempts: int = 3, backoff_schedule: Optional[List[float]] = None) -> Callable[[F], F]:
    """Decorator: retry on failure with exponential backoff.

    Respects Retry-After header on 429 responses.
    """
    if backoff_schedule is None:
        backoff_schedule = [1.0, 2.0, 4.0, 8.0, 16.0]

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except requests.exceptions.HTTPError as exc:
                    last_exc = exc
                    resp = exc.response
                    if resp is not None and resp.status_code == 429:
                        retry_after = resp.headers.get("Retry-After")
                        wait = float(retry_after) if retry_after else backoff_schedule[min(attempt, len(backoff_schedule) - 1)]
                    else:
                        wait = backoff_schedule[min(attempt, len(backoff_schedule) - 1)]
                    if attempt < max_attempts - 1:
                        time.sleep(wait)
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                    last_exc = exc
                    wait = backoff_schedule[min(attempt, len(backoff_schedule) - 1)]
                    if attempt < max_attempts - 1:
                        time.sleep(wait)
            raise last_exc  # type: ignore[misc]
        return wrapper  # type: ignore[return-value]
    return decorator


# ---------------------------------------------------------------------------
# Layout dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Layout:
    origin_x: int = 0
    origin_y: int = 0

    left_label_width: int = 240
    header_height: int = 80
    lane_height: int = 220
    lane_gap: int = 0
    frame_padding: int = 200

    col_width: int = 360
    col_gap: int = 0

    divider_thickness: int = 8
    gridline_thickness: int = 8

    task_w: int = 170
    task_h: int = 80
    decision_w: int = 90
    decision_h: int = 90
    chip_w: int = 90
    chip_h: int = 26

    title_y_offset: int = 260


# ---------------------------------------------------------------------------
# Node / Edge dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Node:
    key: str
    label: str
    lane: str
    col: int
    kind: str = "task"           # task|decision|start|end|chip|lane_band|line|text
    dx: int = 0
    dy: int = 0
    w: Optional[int] = None
    h: Optional[int] = None
    fill: Optional[str] = None
    stroke: Optional[str] = None
    stroke_width: Optional[float] = None


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    label: str = ""
    color: Optional[str] = None
    dashed: bool = False
    shape: str = "elbowed"       # straight|elbowed|curved etc.
    end_cap: str = "stealth"     # none|stealth etc.


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def swimlane_total_height(cfg: Layout, num_lanes: int) -> int:
    return num_lanes * cfg.lane_height + (num_lanes - 1) * cfg.lane_gap + cfg.header_height


def swimlane_total_width(cfg: Layout, num_columns: int) -> int:
    return cfg.left_label_width + num_columns * cfg.col_width + (num_columns - 1) * cfg.col_gap


def swimlane_top_left(cfg: Layout, num_lanes: int, num_columns: int) -> Tuple[int, int]:
    w = swimlane_total_width(cfg, num_columns)
    h = swimlane_total_height(cfg, num_lanes)
    return (cfg.origin_x - w // 2, cfg.origin_y - h // 2)


def lane_center_y(cfg: Layout, lane_i: int, num_lanes: int, num_columns: int) -> int:
    _tlx, tly = swimlane_top_left(cfg, num_lanes, num_columns)
    lane_top = tly + cfg.header_height + lane_i * (cfg.lane_height + cfg.lane_gap)
    return lane_top + cfg.lane_height // 2


def col_center_x(cfg: Layout, col_i: int, num_lanes: int, num_columns: int) -> int:
    tlx, _tly = swimlane_top_left(cfg, num_lanes, num_columns)
    col_left = tlx + cfg.left_label_width + col_i * (cfg.col_width + cfg.col_gap)
    return col_left + cfg.col_width // 2


def node_xy(
    cfg: Layout, node: Node, lanes: List[str], num_columns: int,
) -> Tuple[int, int]:
    lane_i = lanes.index(node.lane)
    num_lanes = len(lanes)
    x = col_center_x(cfg, node.col, num_lanes, num_columns) + node.dx
    y = lane_center_y(cfg, lane_i, num_lanes, num_columns) + node.dy
    return x, y


# ---------------------------------------------------------------------------
# Miro payload builders
# ---------------------------------------------------------------------------

def shape_payload(
    content: str,
    x: int,
    y: int,
    w: int,
    h: int,
    shape: str = "rectangle",
    fill: Optional[str] = None,
    stroke: Optional[str] = None,
    stroke_width: Optional[float] = None,
    font_size: Optional[int] = None,
    text_align: str = "center",
    text_align_vertical: str = "middle",
) -> Dict:
    style: Dict[str, Any] = {}
    if fill:
        style["fillColor"] = fill
        style["fillOpacity"] = 1.0
    if stroke:
        style["borderColor"] = stroke
        style["borderWidth"] = stroke_width or 2.0
        style["borderOpacity"] = 1.0
        style["borderStyle"] = "normal"

    style["textAlign"] = text_align
    style["textAlignVertical"] = text_align_vertical
    if font_size:
        style["fontSize"] = font_size

    payload: Dict = {
        "type": "shape",
        "data": {"shape": shape, "content": content},
        "position": {"x": x, "y": y},
        "geometry": {"width": w, "height": h},
        "style": style,
    }
    return payload


def text_payload(content: str, x: int, y: int, font_size: int = 20) -> Dict:
    return {
        "type": "text",
        "data": {"content": content},
        "position": {"x": x, "y": y},
        "style": {"fontSize": font_size},
    }


def connector_payload(edge: Edge, start_id: str, end_id: str) -> Dict:
    style: Dict[str, Any] = {
        "strokeColor": edge.color or "#1a1a1a",
        "strokeWidth": 2.0,
        "endStrokeCap": edge.end_cap,
    }
    if edge.dashed:
        style["strokeStyle"] = "dashed"

    body: Dict = {
        "startItem": {"id": start_id, "snapTo": "auto"},
        "endItem": {"id": end_id, "snapTo": "auto"},
        "shape": edge.shape,
        "style": style,
    }
    if edge.label:
        body["captions"] = [{"content": edge.label, "position": "50%"}]
    return body


# ---------------------------------------------------------------------------
# Background and text layer builders (parameterized)
# ---------------------------------------------------------------------------

def build_background_items(
    cfg: Layout,
    lanes: List[str],
    columns: List[str],
) -> List[Dict]:
    items: List[Dict] = []
    num_lanes = len(lanes)
    num_columns = len(columns)

    w = swimlane_total_width(cfg, num_columns)
    h = swimlane_total_height(cfg, num_lanes)
    tlx, tly = swimlane_top_left(cfg, num_lanes, num_columns)

    frame_w = w + cfg.frame_padding
    frame_cx = cfg.origin_x + cfg.frame_padding // 2

    # Outer frame
    items.append(shape_payload(
        content="", x=frame_cx, y=cfg.origin_y,
        w=frame_w, h=h,
        shape="rectangle",
        fill="#FFFFFF", stroke="#CFCFCF", stroke_width=3.0,
    ))

    # Lane divider lines (horizontal)
    for i in range(1, num_lanes):
        y = tly + cfg.header_height + i * cfg.lane_height
        items.append(shape_payload(
            content="", x=frame_cx, y=y,
            w=frame_w, h=cfg.divider_thickness,
            shape="rectangle", fill="#E5E5E5",
        ))

    # Column gridlines (vertical)
    for i in range(1, num_columns):
        x = tlx + cfg.left_label_width + i * cfg.col_width
        items.append(shape_payload(
            content="", x=x, y=cfg.origin_y,
            w=cfg.gridline_thickness, h=h,
            shape="rectangle", fill="#E5E5E5",
        ))

    # Header separator
    header_sep_y = tly + cfg.header_height
    items.append(shape_payload(
        content="", x=frame_cx, y=header_sep_y,
        w=frame_w, h=cfg.divider_thickness,
        shape="rectangle", fill="#E5E5E5",
    ))

    return items


def build_text_items(
    cfg: Layout,
    lanes: List[str],
    columns: List[str],
    title: str,
    subtitle: str,
) -> List[Dict]:
    items: List[Dict] = []
    num_lanes = len(lanes)
    num_columns = len(columns)

    w = swimlane_total_width(cfg, num_columns)
    tlx, tly = swimlane_top_left(cfg, num_lanes, num_columns)

    # Title / subtitle
    title_x = tlx + w // 2
    title_y = tly - 80
    items.append({
        "type": "shape",
        "data": {"shape": "rectangle", "content": title},
        "position": {"x": title_x, "y": title_y},
        "geometry": {"width": 600, "height": 50},
        "style": {
            "fillOpacity": 0.0,
            "borderOpacity": 0.0,
            "fontSize": 28,
            "textAlign": "left",
            "fontFamily": "arial",
        },
    })
    items.append({
        "type": "shape",
        "data": {"shape": "rectangle", "content": subtitle},
        "position": {"x": title_x, "y": title_y + 46},
        "geometry": {"width": 600, "height": 36},
        "style": {
            "fillOpacity": 0.0,
            "borderOpacity": 0.0,
            "fontSize": 16,
            "textAlign": "left",
            "fontFamily": "arial",
            "color": "#666666",
        },
    })

    # Column labels
    header_y = tly + cfg.header_height // 2
    for i, col_name in enumerate(columns):
        x = col_center_x(cfg, i, num_lanes, num_columns)
        items.append(text_payload(col_name, x, header_y, font_size=14))

    # Lane labels
    for i, lane_name in enumerate(lanes):
        x = tlx + cfg.left_label_width // 2
        y = lane_center_y(cfg, i, num_lanes, num_columns)
        items.append(text_payload(lane_name, x, y, font_size=16))

    return items


def build_node_items(
    cfg: Layout,
    nodes: List[Node],
    lanes: List[str],
    num_columns: int,
) -> Tuple[List[str], List[Dict]]:
    """Returns (keys, payloads) for flow nodes (not text/label nodes)."""
    keys: List[str] = []
    items: List[Dict] = []

    for n in nodes:
        if n.kind in ("text", "lane_label", "col_label"):
            continue

        x, y = node_xy(cfg, n, lanes, num_columns)
        if n.kind == "start":
            items.append(shape_payload(
                content=n.label, x=x, y=y,
                w=50, h=50, shape="circle",
                fill=n.fill or "#BFE9D6",
                stroke="#1a1a1a", stroke_width=2.0,
            ))
        elif n.kind == "end":
            items.append(shape_payload(
                content=n.label, x=x, y=y,
                w=50, h=50, shape="circle",
                fill=n.fill or "#DDDDDD",
                stroke="#1a1a1a", stroke_width=2.0,
            ))
        elif n.kind == "decision":
            items.append(shape_payload(
                content=n.label, x=x, y=y,
                w=n.w or cfg.decision_w, h=n.h or cfg.decision_h,
                shape="rhombus",
                fill=n.fill or "#FFF3CD",
                stroke="#1a1a1a", stroke_width=2.0,
            ))
        elif n.kind == "chip":
            items.append(shape_payload(
                content=n.label, x=x, y=y,
                w=n.w or cfg.chip_w, h=n.h or cfg.chip_h,
                shape="round_rectangle",
                fill=n.fill or "#D9ECFF",
                stroke="#7AA7D9", stroke_width=1.5,
            ))
        else:  # task (default)
            items.append(shape_payload(
                content=n.label, x=x, y=y,
                w=n.w or cfg.task_w, h=n.h or cfg.task_h,
                shape="rectangle",
                fill=n.fill or "#FFFFFF",
                stroke="#1a1a1a", stroke_width=2.0,
            ))
        keys.append(n.key)

    return keys, items


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def chunked(xs: List, n: int = 20) -> Iterable[List]:
    for i in range(0, len(xs), n):
        yield xs[i : i + n]


# ---------------------------------------------------------------------------
# Miro API Client
# ---------------------------------------------------------------------------

class MiroClient:
    """Miro REST API client with retry and Frame support."""

    def __init__(
        self,
        token: Optional[str] = None,
        board_id: Optional[str] = None,
        timeout: int = 30,
    ):
        load_dotenv()
        self.token = token or os.environ.get("MIRO_TOKEN", "")
        self.board_id = board_id or os.environ.get("MIRO_BOARD_ID", "")
        self.timeout = timeout
        self.base = "https://api.miro.com/v2"

        if not self.token:
            raise ValueError("MIRO_TOKEN is required")
        if not self.board_id:
            raise ValueError("MIRO_BOARD_ID is required")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _raise_for_status(self, resp: requests.Response) -> None:
        if resp.status_code >= 300:
            exc = requests.exceptions.HTTPError(
                f"{resp.status_code} {resp.text}", response=resp,
            )
            raise exc

    # -- Bulk operations --

    @retry(max_attempts=3, backoff_schedule=[1.0, 2.0, 4.0])
    def bulk_create(self, items: List[Dict]) -> List[Dict]:
        """Bulk create up to 20 items per call (transactional)."""
        url = f"{self.base}/boards/{self.board_id}/items/bulk"
        resp = requests.post(
            url, headers=self._headers(),
            data=json.dumps(items), timeout=self.timeout,
        )
        self._raise_for_status(resp)
        data = resp.json()

        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                return data["data"]
            if "items" in data and isinstance(data["items"], list):
                return data["items"]
        if isinstance(data, list):
            return data
        return []

    @retry(max_attempts=3, backoff_schedule=[1.0, 2.0, 4.0])
    def create_connector(self, body: Dict) -> Dict:
        url = f"{self.base}/boards/{self.board_id}/connectors"
        resp = requests.post(
            url, headers=self._headers(),
            data=json.dumps(body), timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()

    # -- Single item operations --

    @retry(max_attempts=3, backoff_schedule=[1.0, 2.0, 4.0])
    def create_item(self, item: Dict) -> Dict:
        """Create a single item (shape, text, etc.)."""
        item_type = item.get("type", "shape")
        # Use the specific endpoint based on type
        if item_type == "text":
            url = f"{self.base}/boards/{self.board_id}/texts"
        elif item_type == "shape":
            url = f"{self.base}/boards/{self.board_id}/shapes"
        else:
            url = f"{self.base}/boards/{self.board_id}/{item_type}s"

        payload = {k: v for k, v in item.items() if k != "type"}
        resp = requests.post(
            url, headers=self._headers(),
            data=json.dumps(payload), timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()

    @retry(max_attempts=3, backoff_schedule=[1.0, 2.0, 4.0])
    def delete_item(self, item_id: str) -> None:
        """Delete a single item by ID. 404 is treated as already deleted."""
        url = f"{self.base}/boards/{self.board_id}/items/{item_id}"
        resp = requests.delete(url, headers=self._headers(), timeout=self.timeout)
        if resp.status_code == 404:
            return  # Already deleted — not an error
        self._raise_for_status(resp)

    @retry(max_attempts=3, backoff_schedule=[1.0, 2.0, 4.0])
    def delete_connector(self, connector_id: str) -> None:
        """Delete a connector by ID. 404 is treated as already deleted."""
        url = f"{self.base}/boards/{self.board_id}/connectors/{connector_id}"
        resp = requests.delete(url, headers=self._headers(), timeout=self.timeout)
        if resp.status_code == 404:
            return  # Already deleted — not an error
        self._raise_for_status(resp)

    @retry(max_attempts=3, backoff_schedule=[1.0, 2.0, 4.0])
    def get_item(self, item_id: str) -> Dict:
        """Get a single item by ID."""
        url = f"{self.base}/boards/{self.board_id}/items/{item_id}"
        resp = requests.get(url, headers=self._headers(), timeout=self.timeout)
        self._raise_for_status(resp)
        return resp.json()

    @retry(max_attempts=3, backoff_schedule=[1.0, 2.0, 4.0])
    def get_items(self, cursor: Optional[str] = None, limit: int = 50) -> Dict:
        """List board items (paginated)."""
        url = f"{self.base}/boards/{self.board_id}/items"
        params: Dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(
            url, headers=self._headers(),
            params=params, timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()

    @retry(max_attempts=3, backoff_schedule=[1.0, 2.0, 4.0])
    def get_connectors(self, cursor: Optional[str] = None, limit: int = 50) -> Dict:
        """List board connectors (paginated)."""
        url = f"{self.base}/boards/{self.board_id}/connectors"
        params: Dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(
            url, headers=self._headers(),
            params=params, timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()

    # -- Frame operations --

    @retry(max_attempts=3, backoff_schedule=[1.0, 2.0, 4.0])
    def create_frame(
        self,
        title: str,
        x: int,
        y: int,
        w: int,
        h: int,
    ) -> Dict:
        """Create a Frame on the board."""
        url = f"{self.base}/boards/{self.board_id}/frames"
        payload = {
            "data": {"title": title, "type": "freeform"},
            "position": {"x": x, "y": y},
            "geometry": {"width": w, "height": h},
            "style": {"fillColor": "#FFFFFF"},
        }
        resp = requests.post(
            url, headers=self._headers(),
            data=json.dumps(payload), timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()

    @retry(max_attempts=3, backoff_schedule=[1.0, 2.0, 4.0])
    def get_frame_items(self, frame_id: str, cursor: Optional[str] = None, limit: int = 50) -> Dict:
        """Get items inside a specific frame using parent_item_id query param."""
        url = f"{self.base}/boards/{self.board_id}/items"
        params: Dict[str, Any] = {"limit": limit, "parent_item_id": frame_id}
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(
            url, headers=self._headers(),
            params=params, timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()

    def attach_to_frame(self, frame_id: str, item_ids: List[str]) -> None:
        """Attach items to a frame by setting parent on each item."""
        for item_id in item_ids:
            self._attach_single_item(frame_id, item_id)

    @retry(max_attempts=3, backoff_schedule=[1.0, 2.0, 4.0])
    def _attach_single_item(self, frame_id: str, item_id: str) -> None:
        """Set parent frame for a single item via PATCH."""
        url = f"{self.base}/boards/{self.board_id}/items/{item_id}"
        payload = {"parent": {"id": frame_id}}
        resp = requests.patch(
            url, headers=self._headers(),
            data=json.dumps(payload), timeout=self.timeout,
        )
        self._raise_for_status(resp)

    def find_rightmost_frame(self) -> Tuple[int, int]:
        """Find the rightmost frame edge on the board.

        Returns (rightmost_x, center_y) for placing a new frame.
        Falls back to (0, 0) if no frames exist.
        """
        rightmost_x = 0
        center_y = 0
        found = False

        cursor = None
        while True:
            data = self.get_items(cursor=cursor, limit=50)
            items_list = data.get("data", [])
            for item in items_list:
                if item.get("type") == "frame":
                    found = True
                    pos = item.get("position", {})
                    geom = item.get("geometry", {})
                    ix = pos.get("x", 0)
                    iw = geom.get("width", 0)
                    right_edge = ix + iw // 2
                    if right_edge > rightmost_x:
                        rightmost_x = right_edge
                        center_y = pos.get("y", 0)

            next_cursor = data.get("cursor")
            if not next_cursor or not items_list:
                break
            cursor = next_cursor

        if found:
            return (rightmost_x, center_y)
        return (0, 0)

    # -- Readback (frame scope) --

    def readback_frame_items(self, frame_id: str) -> List[Dict]:
        """Read back all items inside a frame (paginated)."""
        all_items: List[Dict] = []
        cursor = None
        while True:
            data = self.get_frame_items(frame_id, cursor=cursor, limit=50)
            items_list = data.get("data", [])
            all_items.extend(items_list)
            next_cursor = data.get("cursor")
            if not next_cursor or not items_list:
                break
            cursor = next_cursor
        return all_items

    # -- Cleanup (run_id scope) --

    def cleanup_by_run(self, miro_items_path: str) -> Dict[str, int]:
        """Delete all items tracked in miro_items.json.

        Deletion order: connectors -> shapes/text -> frame.
        Returns counts of deleted items by type.
        If the frame no longer exists, skips child deletion (already cleaned).
        """
        with open(miro_items_path, "r", encoding="utf-8") as f:
            tracked = json.load(f)

        counts: Dict[str, int] = {"connectors": 0, "items": 0, "frame": 0, "skipped": 0}

        frame_id = tracked.get("frame_id")

        # Quick check: if the frame is gone, everything inside is gone too
        if frame_id:
            try:
                self.get_item(frame_id)
            except requests.exceptions.RequestException:
                print(f"Frame {frame_id} not found — already cleaned up.")
                return counts

        # 1. Delete connectors first
        for conn in tracked.get("connectors", []):
            miro_id = conn.get("miro_id")
            if miro_id:
                try:
                    self.delete_connector(miro_id)
                    counts["connectors"] += 1
                    time.sleep(0.1)
                except requests.exceptions.RequestException as exc:
                    counts["skipped"] += 1
                    print(f"WARN: Failed to delete connector {miro_id}: {exc}")

        # 2. Delete items (shapes, text)
        for item in tracked.get("items", []):
            miro_id = item.get("miro_id")
            if miro_id:
                try:
                    self.delete_item(miro_id)
                    counts["items"] += 1
                    time.sleep(0.1)
                except requests.exceptions.RequestException as exc:
                    counts["skipped"] += 1
                    print(f"WARN: Failed to delete item {miro_id}: {exc}")

        # 3. Delete frame last
        if frame_id:
            try:
                self.delete_item(frame_id)
                counts["frame"] += 1
            except requests.exceptions.RequestException as exc:
                counts["skipped"] += 1
                print(f"WARN: Failed to delete frame {frame_id}: {exc}")

        return counts


# ---------------------------------------------------------------------------
# miro_items.json flush helper
# ---------------------------------------------------------------------------

def flush_miro_items(
    path: str,
    run_id: str,
    board_id: str,
    frame_id: str,
    items: List[Dict],
    connectors: List[Dict],
    status: str = "in_progress",
) -> None:
    """Write/update miro_items.json atomically via tempfile + os.replace."""
    import tempfile
    from datetime import datetime, timezone, timedelta

    jst = timezone(timedelta(hours=9))
    data = {
        "run_id": run_id,
        "board_id": board_id,
        "frame_id": frame_id,
        "created_at": datetime.now(jst).isoformat(),
        "items": items,
        "connectors": connectors,
        "status": status,
    }
    dir_name = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
