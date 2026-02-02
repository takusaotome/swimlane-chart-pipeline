#!/usr/bin/env python3
"""Generate a Miro swimlane chart from chart_plan.json.

Usage:
    python scripts/generate_chart.py <chart_plan.json> [--run-id <uuid>]

Creates a dedicated Frame on the Miro board and places all chart elements
inside it. Flushes miro_items.json after each successful batch.
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dataclasses import replace  # noqa: E402

from src.chart_plan_loader import load_chart_plan  # noqa: E402
from src.swimlane_lib import (  # noqa: E402
    BULK_BATCH_SIZE,
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

FRAME_GAP = 500  # Gap between existing content and new frame
TITLE_EXTRA_HEIGHT = 200  # Extra space above chart for title/subtitle
ORIGIN_Y_TITLE_OFFSET = 50  # Y offset for origin within frame
FRAME_SIDE_MARGIN = 50  # Left/right margin between background box and frame edge


def generate_chart(chart_plan_path: str, run_id: str, *, api: Optional[MiroClient] = None) -> str:
    """Generate chart on Miro and return the board URL."""
    plan = load_chart_plan(chart_plan_path)
    cfg = plan.layout

    # Prepare output directory
    output_dir = PROJECT_ROOT / "output" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    miro_items_path = str(output_dir / "miro_items.json")

    # Initialize Miro client (use injected instance or create new one)
    api = api or MiroClient()
    assert api.board_id, "MIRO_BOARD_ID is required"

    # Calculate chart dimensions
    num_lanes = len(plan.lanes)
    num_columns = len(plan.columns)
    chart_w = swimlane_total_width(cfg, num_columns) + cfg.frame_padding + 2 * FRAME_SIDE_MARGIN
    chart_h = swimlane_total_height(cfg, num_lanes) + TITLE_EXTRA_HEIGHT

    # Find position for new frame (right of existing content)
    rightmost_x, center_y = api.find_rightmost_frame()
    frame_x = rightmost_x + FRAME_GAP + chart_w // 2 if rightmost_x > 0 else 0
    frame_y = center_y if rightmost_x > 0 else 0

    # Create dedicated frame
    short_id = run_id[:8]
    frame_title = f"[swimlane] {plan.title} ({short_id})"
    logger.info("Creating frame: %s", frame_title)
    frame_resp = api.create_frame(
        title=frame_title,
        x=frame_x,
        y=frame_y,
        w=chart_w,
        h=chart_h,
    )
    frame_id = str(frame_resp.get("id", ""))
    logger.info("Frame created: %s", frame_id)

    # Adjust layout origin for frame-relative coordinates (parent_top_left)
    # Items inside a frame use coordinates relative to the frame's top-left corner.
    # Set origin to the center of the frame dimensions so child items are centered.
    adjusted_cfg = replace(
        cfg, origin_x=chart_w // 2, origin_y=chart_h // 2 + ORIGIN_Y_TITLE_OFFSET
    )

    # Track all created items for miro_items.json
    tracked_items: List[Dict] = []
    tracked_connectors: List[Dict] = []
    batch_num = 0
    board_id: str = api.board_id  # validated non-empty by MiroClient.__init__

    def flush(status: str = "in_progress") -> None:
        flush_miro_items(
            path=miro_items_path,
            run_id=run_id,
            board_id=board_id,
            frame_id=frame_id,
            items=tracked_items,
            connectors=tracked_connectors,
            status=status,
        )

    # Helper to inject parent into each item payload
    parent_ref = {"id": frame_id}

    def inject_parent(items: List[Dict]) -> List[Dict]:
        return [{**item, "parent": parent_ref} for item in items]

    try:
        # 1) Build and create background items
        bg_items = build_background_items(adjusted_cfg, plan.lanes, plan.columns)
        txt_items = build_text_items(
            adjusted_cfg,
            plan.lanes,
            plan.columns,
            plan.title,
            plan.subtitle,
        )
        non_flow_items = bg_items + txt_items

        for batch in chunked(non_flow_items, BULK_BATCH_SIZE):
            batch_num += 1
            created = api.bulk_create(inject_parent(batch))
            for item in created:
                item_id = str(item.get("id", ""))
                tracked_items.append(
                    {
                        "key": "_bg",
                        "miro_id": item_id,
                        "type": item.get("type", "shape"),
                        "batch": batch_num,
                    }
                )
            flush()
        logger.info("Created %d background/text items.", len(non_flow_items))

        # 2) Build and create flow nodes
        node_keys, node_items = build_node_items(
            adjusted_cfg,
            plan.nodes,
            plan.lanes,
            num_columns,
        )
        key_to_id: Dict[str, str] = {}
        offset = 0

        for batch in chunked(node_items, BULK_BATCH_SIZE):
            batch_num += 1
            created = api.bulk_create(inject_parent(batch))
            for i, item in enumerate(created):
                item_id = str(item.get("id", ""))
                idx = offset + i
                if item_id and idx < len(node_keys):
                    key_to_id[node_keys[idx]] = item_id
                    tracked_items.append(
                        {
                            "key": node_keys[idx],
                            "miro_id": item_id,
                            "type": item.get("type", "shape"),
                            "batch": batch_num,
                        }
                    )
            offset += len(created)
            flush()
        logger.info("Created %d flow nodes. Mapped %d IDs.", len(node_items), len(key_to_id))

        # Check for unmapped keys
        missing = sorted([k for k in node_keys if k not in key_to_id])
        if missing:
            logger.warning("Could not map these keys to IDs: %s", missing)

        # 3) Create connectors
        created_connectors = 0
        for e in plan.edges:
            if e.src not in key_to_id or e.dst not in key_to_id:
                logger.warning("SKIP connector %s->%s (missing item id)", e.src, e.dst)
                continue
            body = connector_payload(e, start_id=key_to_id[e.src], end_id=key_to_id[e.dst])
            resp = api.create_connector(body)
            conn_id = str(resp.get("id", ""))
            tracked_connectors.append(
                {
                    "src": e.src,
                    "dst": e.dst,
                    "miro_id": conn_id,
                }
            )
            created_connectors += 1
            flush()

        logger.info("Created %d connectors.", created_connectors)

    except Exception:
        flush(status="failed")
        raise

    # Final flush with completed status
    flush(status="completed")

    board_url = f"https://miro.com/app/board/{board_id}/"
    logger.info("Done. Board URL: %s", board_url)
    return board_url


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Miro swimlane chart from JSON plan")
    parser.add_argument("chart_plan", help="Path to chart_plan.json")
    parser.add_argument("--run-id", default=None, help="Run ID (UUID). Auto-generated if omitted.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    run_id = args.run_id or str(uuid.uuid4())
    logger.info("Run ID: %s", run_id)

    generate_chart(args.chart_plan, run_id)


if __name__ == "__main__":
    main()
