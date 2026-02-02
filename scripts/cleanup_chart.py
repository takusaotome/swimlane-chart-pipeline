#!/usr/bin/env python3
"""Clean up Miro items created by a specific run.

Usage:
    python scripts/cleanup_chart.py <miro_items.json> [--force]

Reads the miro_items.json file to identify which items to delete.
Deletion order: connectors -> shapes/text -> frame (dependency order).
Performs count verification before deletion unless --force is specified.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.swimlane_lib import MiroClient  # noqa: E402


def count_frame_items(api: MiroClient, frame_id: str) -> int:
    """Count items currently inside the frame via Miro API."""
    count = 0
    cursor = None
    while True:
        data = api.get_frame_items(frame_id, cursor=cursor, limit=50)
        items = data.get("data", [])
        count += len(items)
        next_cursor = data.get("cursor")
        if not next_cursor:
            break
        cursor = next_cursor
    return count


def cleanup(miro_items_path: str, force: bool = False) -> None:
    with open(miro_items_path, "r", encoding="utf-8") as f:
        tracked = json.load(f)

    run_id = tracked.get("run_id", "unknown")
    frame_id = tracked.get("frame_id")
    tracked_item_count = len(tracked.get("items", []))
    tracked_connector_count = len(tracked.get("connectors", []))

    logger.info("Run ID: %s", run_id)
    logger.info("Frame ID: %s", frame_id)
    logger.info("Tracked items: %d, connectors: %d", tracked_item_count, tracked_connector_count)

    api = MiroClient()

    # Verify item count against Miro API
    if frame_id and not force:
        api_count = count_frame_items(api, frame_id)
        if api_count != tracked_item_count:
            logger.warning("Frame item count mismatch!")
            logger.warning("  Tracked: %d items", tracked_item_count)
            logger.warning("  Miro API: %d items in frame", api_count)
            if not sys.stdin.isatty():
                logger.error(
                    "Aborted: non-interactive environment. Use --force to skip verification."
                )
                sys.exit(1)
            response = input("Continue with deletion? (y/N): ").strip().lower()
            if response != "y":
                logger.info("Aborted.")
                return

    # Perform deletion
    counts = api.cleanup_by_run(miro_items_path)

    if counts["connectors"] == 0 and counts["items"] == 0 and counts["frame"] == 0:
        logger.info("Nothing to delete — already clean.")
    else:
        logger.info(
            "Deleted: %d connectors, %d items, %d frame(s)",
            counts["connectors"],
            counts["items"],
            counts["frame"],
        )
    if counts.get("skipped", 0) > 0:
        logger.info("Skipped (already gone): %d", counts["skipped"])
    logger.info("Cleanup complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up Miro items from a run")
    parser.add_argument("miro_items", help="Path to miro_items.json")
    parser.add_argument("--force", action="store_true", help="Skip count verification")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    cleanup(args.miro_items, force=args.force)


if __name__ == "__main__":
    main()
