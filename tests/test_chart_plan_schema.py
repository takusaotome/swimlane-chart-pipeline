"""Tests for chart_plan_schema.json — M1 (schema/Layout dataclass field mismatch)."""

from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SCHEMA_PATH = PROJECT_ROOT / ".claude" / "skills" / "chart-planner" / "assets" / "chart_plan_schema.json"


class TestSchemaLayoutSync:
    """M1: JSON schema layout properties must match Layout dataclass fields."""

    def _load_schema_layout_fields(self):
        with open(SCHEMA_PATH, "r") as f:
            schema = json.load(f)
        return set(schema["properties"]["layout"]["properties"].keys())

    def _get_dataclass_layout_fields(self):
        from src.swimlane_lib import Layout
        return {f.name for f in fields(Layout)}

    def test_schema_accepts_all_layout_fields(self):
        """All Layout dataclass fields must appear in the JSON schema."""
        dc_fields = self._get_dataclass_layout_fields()
        schema_fields = self._load_schema_layout_fields()

        missing_from_schema = dc_fields - schema_fields
        assert missing_from_schema == set(), (
            f"M1: Layout fields missing from schema: {sorted(missing_from_schema)}"
        )

    def test_schema_has_no_extra_fields(self):
        """JSON schema should not define layout fields absent from the dataclass."""
        dc_fields = self._get_dataclass_layout_fields()
        schema_fields = self._load_schema_layout_fields()

        extra_in_schema = schema_fields - dc_fields
        assert extra_in_schema == set(), (
            f"M1: Schema defines extra layout fields not in dataclass: {sorted(extra_in_schema)}"
        )
