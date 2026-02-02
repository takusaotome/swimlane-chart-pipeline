"""Load and validate chart_plan.json, mapping to swimlane_lib dataclasses."""

from __future__ import annotations

import json
import copy
from typing import Any, Dict, List, NamedTuple, Optional

from src.swimlane_lib import Edge, Layout, Node


SUPPORTED_SCHEMA_VERSIONS = {"1.0"}


class ChartPlan(NamedTuple):
    schema_version: str
    run_id: str
    title: str
    subtitle: str
    lanes: List[str]
    columns: List[str]
    layout: Layout
    nodes: List[Node]
    edges: List[Edge]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class ChartPlanValidationError(Exception):
    pass


def _validate_raw(raw: Dict[str, Any]) -> List[str]:
    """Return a list of validation error messages (empty = valid)."""
    errors: List[str] = []

    # Required top-level fields
    for field in ("title", "lanes", "columns", "nodes", "edges"):
        if field not in raw:
            errors.append(f"Missing required field: {field}")

    sv = raw.get("schema_version", "1.0")
    if sv not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"Unsupported schema_version: {sv} (supported: {SUPPORTED_SCHEMA_VERSIONS})")

    lanes = raw.get("lanes", [])
    if not isinstance(lanes, list) or len(lanes) == 0:
        errors.append("'lanes' must be a non-empty list")

    columns = raw.get("columns", [])
    if not isinstance(columns, list) or len(columns) == 0:
        errors.append("'columns' must be a non-empty list")

    lane_set = set(lanes) if isinstance(lanes, list) else set()
    nodes = raw.get("nodes", [])
    node_keys = set()

    for i, n in enumerate(nodes):
        key = n.get("key")
        if not key:
            errors.append(f"nodes[{i}]: missing 'key'")
        elif key in node_keys:
            errors.append(f"nodes[{i}]: duplicate key '{key}'")
        else:
            node_keys.add(key)

        lane = n.get("lane")
        if lane and lane not in lane_set:
            errors.append(f"nodes[{i}] (key={key}): lane '{lane}' not in lanes list")

        col = n.get("col")
        if col is not None and isinstance(columns, list):
            if col < 0 or col >= len(columns):
                errors.append(f"nodes[{i}] (key={key}): col {col} out of range [0, {len(columns)-1}]")

    edges = raw.get("edges", [])
    for i, e in enumerate(edges):
        src = e.get("src")
        dst = e.get("dst")
        if src and src not in node_keys:
            errors.append(f"edges[{i}]: src '{src}' does not reference a known node key")
        if dst and dst not in node_keys:
            errors.append(f"edges[{i}]: dst '{dst}' does not reference a known node key")

    return errors


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _parse_layout(raw_layout: Optional[Dict[str, Any]]) -> Layout:
    """Parse layout dict into Layout dataclass, falling back to defaults."""
    if not raw_layout:
        return Layout()

    # Only pass known Layout fields
    known_fields = {f.name for f in Layout.__dataclass_fields__.values()}
    kwargs = {k: v for k, v in raw_layout.items() if k in known_fields}
    return Layout(**kwargs)


def _parse_node(raw_node: Dict[str, Any]) -> Node:
    known_fields = {f.name for f in Node.__dataclass_fields__.values()}
    kwargs = {k: v for k, v in raw_node.items() if k in known_fields}
    return Node(**kwargs)


def _parse_edge(raw_edge: Dict[str, Any]) -> Edge:
    known_fields = {f.name for f in Edge.__dataclass_fields__.values()}
    kwargs = {k: v for k, v in raw_edge.items() if k in known_fields}
    return Edge(**kwargs)


def load_chart_plan(json_path: str) -> ChartPlan:
    """Load chart_plan.json and return a validated ChartPlan."""
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    errors = _validate_raw(raw)
    if errors:
        msg = "chart_plan.json validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ChartPlanValidationError(msg)

    layout = _parse_layout(raw.get("layout"))
    nodes = [_parse_node(n) for n in raw["nodes"]]
    edges = [_parse_edge(e) for e in raw["edges"]]

    return ChartPlan(
        schema_version=raw.get("schema_version", "1.0"),
        run_id=raw.get("run_id", ""),
        title=raw["title"],
        subtitle=raw.get("subtitle", ""),
        lanes=raw["lanes"],
        columns=raw["columns"],
        layout=layout,
        nodes=nodes,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# JSON Patch application
# ---------------------------------------------------------------------------

def apply_patch(chart_plan_path: str, patches: List[Dict[str, Any]]) -> None:
    """Apply JSON Patch-style operations to chart_plan.json.

    Supported ops: replace, add, remove.
    Path format: "/nodes/1/dx" or "/layout/col_width".
    """
    with open(chart_plan_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for patch in patches:
        op = patch.get("op")
        path = patch.get("path", "")
        value = patch.get("value")

        parts = [p for p in path.split("/") if p]
        if not parts:
            continue

        # Navigate to parent
        target = data
        for part in parts[:-1]:
            if isinstance(target, list):
                target = target[int(part)]
            elif isinstance(target, dict):
                target = target[part]
            else:
                raise ChartPlanValidationError(f"Cannot navigate path: {path}")

        final_key = parts[-1]

        if op == "replace":
            if isinstance(target, list):
                target[int(final_key)] = value
            else:
                target[final_key] = value
        elif op == "add":
            if isinstance(target, list):
                target.insert(int(final_key), value)
            else:
                target[final_key] = value
        elif op == "remove":
            if isinstance(target, list):
                del target[int(final_key)]
            elif isinstance(target, dict):
                del target[final_key]
        else:
            raise ChartPlanValidationError(f"Unsupported patch op: {op}")

    with open(chart_plan_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
