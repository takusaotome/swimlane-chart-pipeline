from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Iterable

import requests

from dotenv import load_dotenv
load_dotenv()

# =========================
# 1) CONFIG: lanes + timeline
# =========================

LANES = [
    "各営業拠点",
    "営業企画部",
    "経理部",
    "経営企画部",
    "経営企画部長",
]

COLUMNS = [
    "毎月末日 17:00",
    "翌月1日〜2日",
    "翌月2日〜3日",
    "翌月4日 午前",
    "翌月4日 午後",
    "翌月4日 夕方",
    "翌月5日 10:00",
]

TITLE = "月次売上報告フロー"
SUBTITLE = "月次（毎月末締め、翌月5営業日目報告）"


# =========================
# 2) Layout tuning knobs
# =========================

@dataclass(frozen=True)
class Layout:
    origin_x: int = 0
    origin_y: int = 0

    # Swimlane area geometry
    left_label_width: int = 240      # lane label area on the left
    header_height: int = 80          # timeline header row height
    lane_height: int = 220
    lane_gap: int = 0               # screenshot uses tight lanes with divider lines
    frame_padding: int = 200

    # Timeline columns
    col_width: int = 360
    col_gap: int = 0

    # Lines (Miro minimum shape dimension is 8px)
    divider_thickness: int = 8
    gridline_thickness: int = 8

    # Node sizes
    task_w: int = 170
    task_h: int = 80
    decision_w: int = 90
    decision_h: int = 90
    chip_w: int = 90
    chip_h: int = 26

    # Title placement
    title_y_offset: int = 260        # above swimlane top


LAYOUT = Layout()


# =========================
# 3) Nodes / edges (diagram content)
# =========================

@dataclass(frozen=True)
class Node:
    key: str
    label: str
    lane: str
    col: int
    kind: str = "task"           # task|decision|start|end|chip|lane_band|line|text
    dx: int = 0                  # fine-tune within same column
    dy: int = 0                  # fine-tune within lane
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


# ---- Nodes placed to mimic your screenshot ----
NODES: List[Node] = [
    # Title / subtitle (as text items)
    Node("TXT_TITLE", TITLE, lane=LANES[0], col=0, kind="text", dy=-99999),
    Node("TXT_SUB", SUBTITLE, lane=LANES[0], col=0, kind="text", dy=-99999),

    # Lane labels (text items) - positioned later by builder
    *[Node(f"LANE_LABEL_{i}", lane, lane=lane, col=0, kind="lane_label") for i, lane in enumerate(LANES)],

    # Timeline header labels (text items)
    *[Node(f"COL_LABEL_{i}", COLUMNS[i], lane=LANES[0], col=i, kind="col_label") for i in range(len(COLUMNS))],

    # Flow nodes (shapes)
    Node("START", "開始", lane="各営業拠点", col=0, kind="start", dx=-230, fill="#BFE9D6"),
    Node("SF_INPUT", "売上データ入力", lane="各営業拠点", col=0, kind="task", dx=-50),
    Node("CHIP_SF", "Salesforce", lane="各営業拠点", col=0, kind="chip", dx=-50, dy=70, fill="#D9ECFF"),

    Node("SLACK_DONE", "完了報告", lane="各営業拠点", col=0, kind="task", dx=150),
    Node("CHIP_SLACK", "Slack", lane="各営業拠点", col=0, kind="chip", dx=150, dy=70, fill="#D9ECFF"),

    Node("EXCEL_SUM", "データ集計・\n売上資料作成", lane="営業企画部", col=1, kind="task"),
    Node("CHIP_EXCEL", "Excel", lane="営業企画部", col=1, kind="chip", dy=70, fill="#D9ECFF"),

    Node("RECON", "勘定照合", lane="経営企画部", col=2, kind="task", dx=-60),
    Node("CHIP_ACCT", "会計システム", lane="経営企画部", col=2, kind="chip", dx=-60, dy=70, fill="#D9ECFF"),

    Node("DEC_DIFF", "差異\nある？", lane="経営企画部", col=2, kind="decision", dx=140),

    Node("FIX", "差異確認・修正", lane="経理部", col=3, kind="task", dx=40, fill="#F9D7D7"),
    Node("FINAL", "確定完了？", lane="経営企画部", col=3, kind="task", dx=0),

    Node("PPT", "報告書作成", lane="経営企画部", col=4, kind="task", dx=-20),
    Node("CHIP_PPT", "PowerPoint", lane="経営企画部", col=4, kind="chip", dx=-20, dy=70, fill="#D9ECFF"),

    Node("REVIEW", "レビュー", lane="経営企画部長", col=5, kind="task", dx=-20),

    Node("MEETING", "経営会議で報告", lane="経営企画部", col=6, kind="task", dx=-120),
    Node("UPLOAD", "SharePointに\nアップロード", lane="経営企画部", col=6, kind="task", dx=120),
    Node("CHIP_SP", "SharePoint", lane="経営企画部", col=6, kind="chip", dx=120, dy=70, fill="#D9ECFF"),

    Node("END", "終了", lane="経営企画部", col=6, kind="end", dx=260, fill="#DDDDDD"),
]

EDGES: List[Edge] = [
    Edge("START", "SF_INPUT"),
    Edge("SF_INPUT", "SLACK_DONE"),
    Edge("SLACK_DONE", "EXCEL_SUM"),         # down
    Edge("EXCEL_SUM", "RECON"),
    Edge("RECON", "DEC_DIFF"),

    # Decision branches: Yes=green, No=red
    Edge("DEC_DIFF", "FIX", label="Yes", color="#2E7D32"),
    Edge("DEC_DIFF", "FINAL", label="No", color="#C62828"),

    # Loop back (dashed red)
    Edge("FIX", "RECON", dashed=True, color="#C62828", shape="curved"),

    Edge("FINAL", "PPT"),
    Edge("PPT", "REVIEW"),
    Edge("REVIEW", "MEETING"),
    Edge("MEETING", "UPLOAD"),
    Edge("UPLOAD", "END"),
]


# =========================
# 4) Coordinate helpers
# =========================

def lane_index(lane: str) -> int:
    return LANES.index(lane)

def swimlane_total_height(cfg: Layout) -> int:
    return len(LANES) * cfg.lane_height + (len(LANES) - 1) * cfg.lane_gap + cfg.header_height

def swimlane_total_width(cfg: Layout) -> int:
    return cfg.left_label_width + len(COLUMNS) * cfg.col_width + (len(COLUMNS) - 1) * cfg.col_gap

def swimlane_top_left(cfg: Layout) -> Tuple[int, int]:
    w = swimlane_total_width(cfg)
    h = swimlane_total_height(cfg)
    return (cfg.origin_x - w // 2, cfg.origin_y - h // 2)

def lane_center_y(cfg: Layout, lane_i: int) -> int:
    top_left_x, top_left_y = swimlane_top_left(cfg)
    # Header row at the very top inside the frame
    lane_top = top_left_y + cfg.header_height + lane_i * (cfg.lane_height + cfg.lane_gap)
    return lane_top + cfg.lane_height // 2

def col_center_x(cfg: Layout, col_i: int) -> int:
    top_left_x, top_left_y = swimlane_top_left(cfg)
    col_left = top_left_x + cfg.left_label_width + col_i * (cfg.col_width + cfg.col_gap)
    return col_left + cfg.col_width // 2

def node_xy(cfg: Layout, n: Node) -> Tuple[int, int]:
    x = col_center_x(cfg, n.col) + n.dx
    y = lane_center_y(cfg, lane_index(n.lane)) + n.dy
    return x, y


# =========================
# 5) Miro payload builders
# =========================

def shape_payload(content: str, x: int, y: int, w: int, h: int,
                  shape: str = "rectangle",
                  fill: Optional[str] = None,
                  stroke: Optional[str] = None,
                  stroke_width: Optional[float] = None) -> Dict:
    style: Dict = {}
    if fill:
        style["fillColor"] = fill
        style["fillOpacity"] = 1.0
    if stroke:
        style["borderColor"] = stroke
        style["borderWidth"] = stroke_width or 2.0
        style["borderOpacity"] = 1.0
        style["borderStyle"] = "normal"

    style["textAlign"] = "center"
    style["textAlignVertical"] = "middle"

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
    style: Dict = {
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


# =========================
# 6) Miro API client (bulk + connectors)
# =========================

class MiroClient:
    def __init__(self, token: str, board_id: str, timeout: int = 30):
        self.token = token
        self.board_id = board_id
        self.timeout = timeout
        self.base = "https://api.miro.com/v2"

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def bulk_create(self, items: List[Dict]) -> List[Dict]:
        """Bulk create: up to 20 items/call, transactional. Body is a JSON array."""
        url = f"{self.base}/boards/{self.board_id}/items/bulk"
        resp = requests.post(url, headers=self._headers(), data=json.dumps(items), timeout=self.timeout)
        if resp.status_code >= 300:
            raise RuntimeError(f"Bulk create failed: {resp.status_code} {resp.text}")
        data = resp.json()

        # Response: {"type": "bulk_operation", "data": [...]}
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                return data["data"]
            if "items" in data and isinstance(data["items"], list):
                return data["items"]
        if isinstance(data, list):
            return data
        return []

    def create_connector(self, body: Dict) -> Dict:
        url = f"{self.base}/boards/{self.board_id}/connectors"
        resp = requests.post(url, headers=self._headers(), data=json.dumps(body), timeout=self.timeout)
        if resp.status_code >= 300:
            raise RuntimeError(f"Create connector failed: {resp.status_code} {resp.text}")
        return resp.json()


def chunked(xs: List[Dict], n: int = 20) -> Iterable[List[Dict]]:
    for i in range(0, len(xs), n):
        yield xs[i:i+n]


# =========================
# 7) Build all background + labels + nodes into bulk items
# =========================

def build_background_items(cfg: Layout) -> List[Dict]:
    items: List[Dict] = []

    w = swimlane_total_width(cfg)
    h = swimlane_total_height(cfg)
    tlx, tly = swimlane_top_left(cfg)

    # Frame is wider than the content area to accommodate nodes with dx offsets
    frame_w = w + cfg.frame_padding
    # Frame center shifted right by half the padding (padding only on right side)
    frame_cx = cfg.origin_x + cfg.frame_padding // 2

    # Outer frame as a big rectangle
    items.append(shape_payload(
        content="",
        x=frame_cx,
        y=cfg.origin_y,
        w=frame_w,
        h=h,
        shape="rectangle",
        fill="#FFFFFF",
        stroke="#CFCFCF",
        stroke_width=3.0,
    ))

    # Lane divider lines (horizontal)
    for i in range(1, len(LANES)):
        y = tly + cfg.header_height + i * cfg.lane_height
        items.append(shape_payload(
            content="",
            x=frame_cx,
            y=y,
            w=frame_w,
            h=cfg.divider_thickness,
            shape="rectangle",
            fill="#E5E5E5",
            stroke=None,
        ))

    # Timeline vertical gridlines (between columns)
    for i in range(1, len(COLUMNS)):
        x = tlx + cfg.left_label_width + i * cfg.col_width
        items.append(shape_payload(
            content="",
            x=x,
            y=cfg.origin_y,
            w=cfg.gridline_thickness,
            h=h,
            shape="rectangle",
            fill="#E5E5E5",
            stroke=None,
        ))

    # Header separator line (between header row and lanes)
    header_sep_y = tly + cfg.header_height
    items.append(shape_payload(
        content="",
        x=frame_cx,
        y=header_sep_y,
        w=frame_w,
        h=cfg.divider_thickness,
        shape="rectangle",
        fill="#E5E5E5",
        stroke=None,
    ))

    return items


def build_text_items(cfg: Layout) -> List[Dict]:
    items: List[Dict] = []
    w = swimlane_total_width(cfg)
    h = swimlane_total_height(cfg)
    tlx, tly = swimlane_top_left(cfg)

    # Title / subtitle above swimlane (use shapes for controlled width)
    title_x = tlx + w // 2
    title_y = tly - 80
    items.append({
        "type": "shape",
        "data": {"shape": "rectangle", "content": TITLE},
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
        "data": {"shape": "rectangle", "content": SUBTITLE},
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

    # Column labels (centered in header row above each column)
    header_y = tly + cfg.header_height // 2
    for i, col_name in enumerate(COLUMNS):
        x = col_center_x(cfg, i)
        items.append(text_payload(col_name, x, header_y, font_size=14))

    # Lane labels (left area, centered per lane)
    for i, lane_name in enumerate(LANES):
        x = tlx + cfg.left_label_width // 2
        y = lane_center_y(cfg, i)
        items.append(text_payload(lane_name, x, y, font_size=16))

    return items


def build_node_items(cfg: Layout) -> Tuple[List[str], List[Dict]]:
    """Returns (keys, payloads) so we can map response items by index."""
    keys: List[str] = []
    items: List[Dict] = []

    for n in NODES:
        if n.kind in ("text", "lane_label", "col_label"):
            continue

        x, y = node_xy(cfg, n)
        if n.kind == "start":
            items.append(shape_payload(
                content=n.label, x=x, y=y,
                w=50, h=50, shape="circle",
                fill=n.fill or "#BFE9D6",
                stroke="#1a1a1a", stroke_width=2.0
            ))
        elif n.kind == "end":
            items.append(shape_payload(
                content=n.label, x=x, y=y,
                w=50, h=50, shape="circle",
                fill=n.fill or "#DDDDDD",
                stroke="#1a1a1a", stroke_width=2.0
            ))
        elif n.kind == "decision":
            items.append(shape_payload(
                content=n.label, x=x, y=y,
                w=n.w or cfg.decision_w, h=n.h or cfg.decision_h,
                shape="rhombus",
                fill="#FFF3CD",
                stroke="#1a1a1a", stroke_width=2.0
            ))
        elif n.kind == "chip":
            items.append(shape_payload(
                content=n.label, x=x, y=y,
                w=n.w or cfg.chip_w, h=n.h or cfg.chip_h,
                shape="round_rectangle",
                fill=n.fill or "#D9ECFF",
                stroke="#7AA7D9", stroke_width=1.5
            ))
        else:
            items.append(shape_payload(
                content=n.label, x=x, y=y,
                w=n.w or cfg.task_w, h=n.h or cfg.task_h,
                shape="rectangle",
                fill=n.fill or "#FFFFFF",
                stroke="#1a1a1a", stroke_width=2.0
            ))
        keys.append(n.key)

    return keys, items


def main():
    token = os.environ.get("MIRO_TOKEN")
    board_id = os.environ.get("MIRO_BOARD_ID")
    if not token or not board_id:
        raise SystemExit("Set env vars: MIRO_TOKEN and MIRO_BOARD_ID")

    api = MiroClient(token=token, board_id=board_id)

    # 1) background (frame + dividers) - no ID tracking needed
    bg_items = build_background_items(LAYOUT)
    # 2) texts (title + column headers + lane labels) - no ID tracking needed
    txt_items = build_text_items(LAYOUT)

    # Create background + text items first (order doesn't matter for these)
    non_flow_items = bg_items + txt_items
    for batch in chunked(non_flow_items, 20):
        api.bulk_create(batch)
    print(f"Created {len(non_flow_items)} background/text items.")

    # 3) nodes (flow shapes + chips) - need ID tracking for connectors
    node_keys, node_items = build_node_items(LAYOUT)

    # Create node items and map keys to Miro IDs by order
    key_to_id: Dict[str, str] = {}
    offset = 0
    for batch in chunked(node_items, 20):
        created = api.bulk_create(batch)
        for i, item in enumerate(created):
            item_id = item.get("id")
            if item_id and (offset + i) < len(node_keys):
                key_to_id[node_keys[offset + i]] = str(item_id)
        offset += len(batch)
    print(f"Created {len(node_items)} flow nodes. Mapped {len(key_to_id)} IDs.")

    # Sanity check
    missing = sorted([k for k in node_keys if k not in key_to_id])
    if missing:
        print(f"WARN: could not map these keys to IDs: {missing}")

    # 4) connectors (create after nodes exist)
    created_connectors = 0
    for e in EDGES:
        if e.src not in key_to_id or e.dst not in key_to_id:
            print(f"SKIP connector {e.src}->{e.dst} (missing item id)")
            continue
        body = connector_payload(e, start_id=key_to_id[e.src], end_id=key_to_id[e.dst])
        api.create_connector(body)
        created_connectors += 1

    print(f"Created {created_connectors} connectors.")
    print("Done. Swimlane reproduced.")


if __name__ == "__main__":
    main()
