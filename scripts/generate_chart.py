#!/usr/bin/env python3
"""Generate a Miro swimlane chart from chart_plan.json.

Usage:
    python scripts/generate_chart.py <chart_plan.json> [--run-id <uuid>]

Creates a dedicated Frame on the Miro board and places all chart elements
inside it. Flushes miro_items.json after each successful batch.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path
from typing import Dict, List

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dataclasses import replace

from src.swimlane_lib import (
    MiroClient,
    build_background_items,
    build_node_items,
    build_text_items,
    chunked,
    connector_payload,
    flush_miro_items,
    swimlane_total_height,
    swimlane_total_width,
)
from src.chart_plan_loader import load_chart_plan


FRAME_GAP = 500  # Gap between existing content and new frame


def generate_chart(chart_plan_path: str, run_id: str) -> str:
    """Generate chart on Miro and return the board URL."""
    plan = load_chart_plan(chart_plan_path)
    cfg = plan.layout

    # Prepare output directory
    output_dir = PROJECT_ROOT / "output" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    miro_items_path = str(output_dir / "miro_items.json")

    # Initialize Miro client
    api = MiroClient()

    # Calculate chart dimensions
    num_lanes = len(plan.lanes)
    num_columns = len(plan.columns)
    chart_w = swimlane_total_width(cfg, num_columns) + cfg.frame_padding
    chart_h = swimlane_total_height(cfg, num_lanes) + 200  # Extra space for title

    # Find position for new frame (right of existing content)
    rightmost_x, center_y = api.find_rightmost_frame()
    frame_x = rightmost_x + FRAME_GAP + chart_w // 2 if rightmost_x > 0 else 0
    frame_y = center_y if rightmost_x > 0 else 0

    # Create dedicated frame
    short_id = run_id[:8]
    frame_title = f"[swimlane] {plan.title} ({short_id})"
    print(f"Creating frame: {frame_title}")
    frame_resp = api.create_frame(
        title=frame_title,
        x=frame_x, y=frame_y,
        w=chart_w, h=chart_h,
    )
    frame_id = str(frame_resp.get("id", ""))
    print(f"Frame created: {frame_id}")

    # Adjust layout origin for frame-relative coordinates (parent_top_left)
    # Items inside a frame use coordinates relative to the frame's top-left corner.
    # Set origin to the center of the frame dimensions so child items are centered.
    adjusted_cfg = replace(cfg, origin_x=chart_w // 2, origin_y=chart_h // 2 + 50)

    # Track all created items for miro_items.json
    tracked_items: List[Dict] = []
    tracked_connectors: List[Dict] = []
    batch_num = 0

    def flush() -> None:
        flush_miro_items(
            path=miro_items_path,
            run_id=run_id,
            board_id=api.board_id,
            frame_id=frame_id,
            items=tracked_items,
            connectors=tracked_connectors,
            status="in_progress",
        )

    # Helper to inject parent into each item payload
    parent_ref = {"id": frame_id}

    def inject_parent(items: List[Dict]) -> List[Dict]:
        for item in items:
            item["parent"] = parent_ref
        return items

    # 1) Build and create background items
    bg_items = build_background_items(adjusted_cfg, plan.lanes, plan.columns)
    txt_items = build_text_items(
        adjusted_cfg, plan.lanes, plan.columns, plan.title, plan.subtitle,
    )
    non_flow_items = bg_items + txt_items

    for batch in chunked(non_flow_items, 20):
        batch_num += 1
        created = api.bulk_create(inject_parent(batch))
        for item in created:
            item_id = str(item.get("id", ""))
            tracked_items.append({
                "key": "_bg",
                "miro_id": item_id,
                "type": item.get("type", "shape"),
                "batch": batch_num,
            })
        flush()
    print(f"Created {len(non_flow_items)} background/text items.")

    # 2) Build and create flow nodes
    node_keys, node_items = build_node_items(
        adjusted_cfg, plan.nodes, plan.lanes, num_columns,
    )
    key_to_id: Dict[str, str] = {}
    offset = 0

    for batch in chunked(node_items, 20):
        batch_num += 1
        created = api.bulk_create(inject_parent(batch))
        for i, item in enumerate(created):
            item_id = str(item.get("id", ""))
            idx = offset + i
            if item_id and idx < len(node_keys):
                key_to_id[node_keys[idx]] = item_id
                tracked_items.append({
                    "key": node_keys[idx],
                    "miro_id": item_id,
                    "type": item.get("type", "shape"),
                    "batch": batch_num,
                })
        offset += len(batch)
        flush()
    print(f"Created {len(node_items)} flow nodes. Mapped {len(key_to_id)} IDs.")

    # Check for unmapped keys
    missing = sorted([k for k in node_keys if k not in key_to_id])
    if missing:
        print(f"WARN: could not map these keys to IDs: {missing}")

    # 3) Create connectors
    created_connectors = 0
    for e in plan.edges:
        if e.src not in key_to_id or e.dst not in key_to_id:
            print(f"SKIP connector {e.src}->{e.dst} (missing item id)")
            continue
        body = connector_payload(e, start_id=key_to_id[e.src], end_id=key_to_id[e.dst])
        resp = api.create_connector(body)
        conn_id = str(resp.get("id", ""))
        tracked_connectors.append({
            "src": e.src,
            "dst": e.dst,
            "miro_id": conn_id,
        })
        created_connectors += 1
        flush()

    print(f"Created {created_connectors} connectors.")

    # Final flush with completed status
    flush_miro_items(
        path=miro_items_path,
        run_id=run_id,
        board_id=api.board_id,
        frame_id=frame_id,
        items=tracked_items,
        connectors=tracked_connectors,
        status="completed",
    )

    board_url = f"https://miro.com/app/board/{api.board_id}/"
    print(f"Done. Board URL: {board_url}")
    return board_url


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Miro swimlane chart from JSON plan")
    parser.add_argument("chart_plan", help="Path to chart_plan.json")
    parser.add_argument("--run-id", default=None, help="Run ID (UUID). Auto-generated if omitted.")
    args = parser.parse_args()

    run_id = args.run_id or str(uuid.uuid4())
    print(f"Run ID: {run_id}")

    generate_chart(args.chart_plan, run_id)


if __name__ == "__main__":
    main()
