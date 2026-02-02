"""Tests for chart_plan_schema.json — M1 (schema/Layout dataclass field mismatch)."""

from __future__ import annotations

import json
import sys
from dataclasses import fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SCHEMA_PATH = (
    PROJECT_ROOT / ".claude" / "skills" / "chart-planner" / "assets" / "chart_plan_schema.json"
)


class TestLayoutDefaultsMatchSchema:
    """C-06: Layout dataclass defaults must match schema defaults."""

    def test_layout_defaults_match_schema_defaults(self):
        """Each Layout field's default value should match the schema default."""
        from dataclasses import fields as dc_fields

        from src.swimlane_lib import Layout

        with open(SCHEMA_PATH, "r") as f:
            schema = json.load(f)

        schema_layout = schema["properties"]["layout"]["properties"]
        layout = Layout()

        mismatches = []
        for field in dc_fields(Layout):
            if field.name in schema_layout:
                schema_default = schema_layout[field.name].get("default")
                if schema_default is not None:
                    actual = getattr(layout, field.name)
                    if actual != schema_default:
                        mismatches.append(
                            f"  {field.name}: Layout={actual}, schema={schema_default}"
                        )

        assert mismatches == [], "C-06: Layout defaults differ from schema:\n" + "\n".join(
            mismatches
        )


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
