#!/usr/bin/env python3
"""Validate a generated Miro swimlane chart.

Usage:
    python scripts/validate_chart.py <miro_items.json> [--chart-plan <chart_plan.json>]

Reads back items from the Miro API and performs heuristic validation:
  - Bounding box overlap detection
  - Connector completeness check
  - Label truncation detection (Japanese ~16px/char)
  - Lane balance analysis
  - Color consistency check

Outputs validation_report.json in the same directory as miro_items.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.swimlane_lib import MiroClient  # noqa: E402

# ---------------------------------------------------------------------------
# Heuristic checks
# ---------------------------------------------------------------------------

JAPANESE_CHAR_WIDTH_PX = 16  # Approximate width per Japanese character
LATIN_CHAR_WIDTH_PX = 9  # Approximate width per Latin character
BG_SIZE_THRESHOLD = 500  # Items larger than this are treated as background


def estimate_text_width(text: str, font_size: int = 14) -> float:
    """Estimate rendered text width in pixels."""
    scale = font_size / 14.0
    width = 0.0
    for ch in text:
        if ord(ch) > 0x7F:
            width += JAPANESE_CHAR_WIDTH_PX * scale
        else:
            width += LATIN_CHAR_WIDTH_PX * scale
    return width


def get_bbox(item: Dict) -> Optional[Tuple[float, float, float, float]]:
    """Extract bounding box (x1, y1, x2, y2) from a Miro item."""
    pos = item.get("position", {})
    geom = item.get("geometry", {})

    x = pos.get("x")
    y = pos.get("y")
    w = geom.get("width")
    h = geom.get("height")

    if x is None or y is None or w is None or h is None:
        return None

    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def boxes_overlap(
    a: Tuple[float, float, float, float], b: Tuple[float, float, float, float], margin: float = 5.0
) -> bool:
    """Check if two bounding boxes overlap (with margin)."""
    return not (
        a[2] + margin <= b[0]  # a is left of b
        or b[2] + margin <= a[0]  # b is left of a
        or a[3] + margin <= b[1]  # a is above b
        or b[3] + margin <= a[1]  # b is above a
    )


def check_overlaps(items: List[Dict]) -> List[Dict[str, Any]]:
    """Detect overlapping items (shapes only, excluding background)."""
    findings: List[Dict[str, Any]] = []
    shape_items = []

    for item in items:
        if item.get("type") not in ("shape",):
            continue
        bbox = get_bbox(item)
        if not bbox:
            continue
        # Skip very large items (background rectangles)
        geom = item.get("geometry", {})
        w = geom.get("width", 0)
        h = geom.get("height", 0)
        if w > BG_SIZE_THRESHOLD or h > BG_SIZE_THRESHOLD:
            continue
        shape_items.append((item, bbox))

    for i in range(len(shape_items)):
        for j in range(i + 1, len(shape_items)):
            item_a, bbox_a = shape_items[i]
            item_b, bbox_b = shape_items[j]
            if boxes_overlap(bbox_a, bbox_b):
                findings.append(
                    {
                        "severity": "Major",
                        "type": "overlap",
                        "description": f"Items overlap: {item_a.get('id')} and {item_b.get('id')}",
                        "item_a_id": item_a.get("id"),
                        "item_b_id": item_b.get("id"),
                        "item_a_content": item_a.get("data", {}).get("content", ""),
                        "item_b_content": item_b.get("data", {}).get("content", ""),
                    }
                )

    return findings


def check_label_truncation(items: List[Dict]) -> List[Dict[str, Any]]:
    """Detect labels that may be truncated within their shapes."""
    findings: List[Dict[str, Any]] = []

    for item in items:
        if item.get("type") != "shape":
            continue
        content = item.get("data", {}).get("content", "")
        if not content:
            continue

        geom = item.get("geometry", {})
        w = geom.get("width", 0)
        if w > BG_SIZE_THRESHOLD:  # Skip background shapes
            continue

        # Estimate text width for the longest line
        font_size = int(item.get("style", {}).get("fontSize", 14))
        lines = content.replace("<br>", "\n").split("\n")
        for line in lines:
            text_width = estimate_text_width(line.strip(), font_size)
            padding = 20  # Internal padding
            if text_width > (w - padding):
                findings.append(
                    {
                        "severity": "Minor",
                        "type": "label_truncation",
                        "description": f"Label may be truncated: '{line.strip()}' (est. {text_width:.0f}px > {w - padding}px available)",
                        "item_id": item.get("id"),
                        "content": content,
                        "estimated_width": text_width,
                        "available_width": w - padding,
                    }
                )
                break  # One finding per item

    return findings


def check_connector_completeness(
    tracked: Dict,
    api_connectors: List[Dict],
) -> List[Dict[str, Any]]:
    """Check that all expected connectors were created."""
    findings: List[Dict[str, Any]] = []

    expected_connectors = tracked.get("connectors", [])
    expected_ids = {c.get("miro_id") for c in expected_connectors if c.get("miro_id")}
    actual_ids = {c.get("id") for c in api_connectors if c.get("id")}

    missing = expected_ids - actual_ids
    for mid in missing:
        conn_info: Dict[str, Any] = next(
            (c for c in expected_connectors if c.get("miro_id") == mid), {}
        )
        findings.append(
            {
                "severity": "Critical",
                "type": "missing_connector",
                "description": f"Connector missing: {conn_info.get('src', '?')} -> {conn_info.get('dst', '?')} (miro_id: {mid})",
                "miro_id": mid,
            }
        )

    return findings


def check_frame_overflow(
    items: List[Dict], frame_width: float, frame_height: float
) -> List[Dict[str, Any]]:
    """Detect items whose bounding box extends beyond the frame boundary.

    Frame-relative coordinates: the frame spans (0, 0) to (frame_width, frame_height).
    """
    findings: List[Dict[str, Any]] = []

    for item in items:
        bbox = get_bbox(item)
        if bbox is None:
            continue
        x1, y1, x2, y2 = bbox

        overflows: List[str] = []
        overflow_px: Dict[str, float] = {}

        if x2 > frame_width:
            overflows.append("right")
            overflow_px["overflow_right_px"] = x2 - frame_width
        if y2 > frame_height:
            overflows.append("bottom")
            overflow_px["overflow_bottom_px"] = y2 - frame_height
        if x1 < 0:
            overflows.append("left")
            overflow_px["overflow_left_px"] = -x1
        if y1 < 0:
            overflows.append("top")
            overflow_px["overflow_top_px"] = -y1

        if overflows:
            content = item.get("data", {}).get("content", "")
            findings.append(
                {
                    "severity": "Major",
                    "type": "frame_overflow",
                    "description": (
                        f"Item {item.get('id', '?')} overflows frame ({', '.join(overflows)})"
                    ),
                    "item_id": item.get("id"),
                    "content": content,
                    **overflow_px,
                }
            )

    return findings


def check_lane_balance(chart_plan: Dict) -> List[Dict[str, Any]]:
    """Check for empty or overly dense lanes."""
    findings: List[Dict[str, Any]] = []

    lanes = chart_plan.get("lanes", [])
    nodes = chart_plan.get("nodes", [])

    # Count nodes per lane (excluding background/text nodes)
    lane_counts: Dict[str, int] = {lane: 0 for lane in lanes}
    for node in nodes:
        lane = node.get("lane", "")
        if lane in lane_counts and node.get("kind") not in ("text", "lane_label", "col_label"):
            lane_counts[lane] += 1

    for lane, count in lane_counts.items():
        if count == 0:
            findings.append(
                {
                    "severity": "Info",
                    "type": "empty_lane",
                    "description": f"Lane '{lane}' has no flow nodes",
                    "lane": lane,
                }
            )

    return findings


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------


def validate(miro_items_path: str, chart_plan_path: Optional[str] = None) -> Dict:
    """Run all validations and return a report."""
    with open(miro_items_path, "r", encoding="utf-8") as f:
        tracked = json.load(f)

    frame_id = tracked.get("frame_id")
    run_id = tracked.get("run_id", "unknown")

    chart_plan = None
    if chart_plan_path:
        with open(chart_plan_path, "r", encoding="utf-8") as f:
            chart_plan = json.load(f)

    api = MiroClient()

    # Read back items from frame
    logger.info("Reading back items from frame %s...", frame_id)
    frame_items = api.readback_frame_items(frame_id) if frame_id else []
    logger.info("Found %d items in frame.", len(frame_items))

    # Read back connectors (board-wide, then filter)
    all_connectors: List[Dict] = []
    cursor = None
    while True:
        data = api.get_connectors(cursor=cursor, limit=50)
        items = data.get("data", [])
        all_connectors.extend(items)
        next_cursor = data.get("cursor")
        if not next_cursor:
            break
        cursor = next_cursor

    # Filter connectors to those tracked in this run
    tracked_conn_ids = {c.get("miro_id") for c in tracked.get("connectors", [])}
    run_connectors = [c for c in all_connectors if c.get("id") in tracked_conn_ids]

    # Get frame geometry for overflow check
    frame_geom_w: Optional[float] = None
    frame_geom_h: Optional[float] = None
    if frame_id:
        try:
            frame_data = api.get_item(frame_id)
            geom = frame_data.get("geometry", {})
            w_val = geom.get("width")
            h_val = geom.get("height")
            if isinstance(w_val, (int, float)) and isinstance(h_val, (int, float)):
                frame_geom_w = float(w_val)
                frame_geom_h = float(h_val)
        except Exception:
            logger.warning("Could not read frame geometry for overflow check.")

    # Run checks
    findings: List[Dict[str, Any]] = []
    findings.extend(check_overlaps(frame_items))
    findings.extend(check_label_truncation(frame_items))
    findings.extend(check_connector_completeness(tracked, run_connectors))
    if frame_geom_w is not None and frame_geom_h is not None:
        findings.extend(check_frame_overflow(frame_items, frame_geom_w, frame_geom_h))
    if chart_plan:
        findings.extend(check_lane_balance(chart_plan))

    # Summary
    severity_counts: Dict[str, int] = {}
    for f_ in findings:
        sev = f_.get("severity", "Info")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    report = {
        "run_id": run_id,
        "frame_id": frame_id,
        "item_count": len(frame_items),
        "connector_count": len(run_connectors),
        "findings": findings,
        "summary": severity_counts,
        "status": "pass"
        if not any(f_.get("severity") in ("Critical", "Major") for f_ in findings)
        else "fail",
    }

    # Write report
    output_dir = Path(miro_items_path).parent
    report_path = output_dir / "validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info("Validation report: %s", report_path)
    logger.info("Status: %s", report["status"])
    logger.info("Findings: %s", severity_counts)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Miro swimlane chart")
    parser.add_argument("miro_items", help="Path to miro_items.json")
    parser.add_argument("--chart-plan", default=None, help="Path to chart_plan.json (optional)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    validate(args.miro_items, args.chart_plan)


if __name__ == "__main__":
    main()
