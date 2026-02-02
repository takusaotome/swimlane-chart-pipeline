"""Swimlane chart generator for Miro — backward-compatible entry point.

This script uses hardcoded data for the monthly sales report flow.
For JSON-driven generation, use: python scripts/generate_chart.py <chart_plan.json>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List

# Ensure project root is on sys.path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.swimlane_lib import (
    Edge,
    Layout,
    MiroClient,
    Node,
    build_background_items,
    build_node_items,
    build_text_items,
    chunked,
    connector_payload,
)


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
# 2) Layout
# =========================

LAYOUT = Layout()


# =========================
# 3) Nodes / edges (diagram content)
# =========================

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
# 4) Coordinate helpers (backward compat wrappers)
# =========================

def lane_index(lane: str) -> int:
    return LANES.index(lane)

def swimlane_total_height_compat(cfg: Layout) -> int:
    from src.swimlane_lib import swimlane_total_height
    return swimlane_total_height(cfg, len(LANES))

def swimlane_total_width_compat(cfg: Layout) -> int:
    from src.swimlane_lib import swimlane_total_width
    return swimlane_total_width(cfg, len(COLUMNS))


# =========================
# Main
# =========================

def main():
    api = MiroClient()

    num_columns = len(COLUMNS)

    # 1) background (frame + dividers)
    bg_items = build_background_items(LAYOUT, LANES, COLUMNS)
    # 2) texts (title + column headers + lane labels)
    txt_items = build_text_items(LAYOUT, LANES, COLUMNS, TITLE, SUBTITLE)

    non_flow_items = bg_items + txt_items
    for batch in chunked(non_flow_items, 20):
        api.bulk_create(batch)
    print(f"Created {len(non_flow_items)} background/text items.")

    # 3) nodes (flow shapes + chips)
    node_keys, node_items = build_node_items(LAYOUT, NODES, LANES, num_columns)

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

    missing = sorted([k for k in node_keys if k not in key_to_id])
    if missing:
        print(f"WARN: could not map these keys to IDs: {missing}")

    # 4) connectors
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
