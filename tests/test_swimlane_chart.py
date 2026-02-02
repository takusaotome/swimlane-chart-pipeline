"""Tests for scripts/swimlane_chart_demo.py — M5 (dead nodes in NODES list)."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestDeadNodes:
    """M5: NODES list should not contain nodes that build_node_items skips."""

    def test_nodes_list_has_no_dead_nodes(self):
        """Every node in NODES should be processed by build_node_items (not skipped)."""
        from scripts.swimlane_chart_demo import COLUMNS, LANES, LAYOUT, NODES
        from src.swimlane_lib import build_node_items

        num_columns = len(COLUMNS)
        keys, items = build_node_items(LAYOUT, NODES, LANES, num_columns)

        # Nodes with kind in ("text", "lane_label", "col_label") are skipped
        # They should not be in the NODES list
        dead_nodes = [n.key for n in NODES if n.kind in ("text", "lane_label", "col_label")]
        assert dead_nodes == [], (
            f"M5: NODES contains dead nodes (skipped by build_node_items): {dead_nodes}. "
            "These should be removed since build_text_items handles titles/labels."
        )
