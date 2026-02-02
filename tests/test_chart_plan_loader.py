"""Tests for src/chart_plan_loader.py — M3 (unused import), m5 (validation gaps), C2 (apply_patch)."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestUnusedImports:
    """M3: chart_plan_loader.py should have no unused imports."""

    def test_no_unused_imports(self):
        """'import copy' should not be present if copy is never used."""
        source_path = PROJECT_ROOT / "src" / "chart_plan_loader.py"
        source = source_path.read_text()
        tree = ast.parse(source)

        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name)

        # Collect all Name usages (excluding import statements themselves)
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)

        # 'copy' is imported but only appears in its own import statement
        # Check if 'copy' appears as a Name node in non-import context
        if "copy" in imported_names:
            copy_usages = 0
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == "copy":
                    # Check if this is NOT part of an import statement
                    copy_usages += 1

            # Import itself creates 1 usage as ast.Import, not ast.Name
            # So if copy appears in Name nodes, it's used in code; otherwise unused
            # Actually: `import copy` doesn't create ast.Name — it creates ast.Import
            # If "copy" appears as ast.Name, it's used; if only in ast.Import, unused
            # But we need to check ast.Attribute too for copy.deepcopy etc.
            copy_attr_usages = 0
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    if isinstance(node.value, ast.Name) and node.value.id == "copy":
                        copy_attr_usages += 1

            assert copy_usages > 0 or copy_attr_usages > 0, (
                "M3: 'copy' is imported but never used in chart_plan_loader.py"
            )


class TestValidationGaps:
    """m5: _validate_raw should reject nodes missing label or lane."""

    def test_validate_rejects_node_without_label(self):
        """A node missing 'label' should produce a validation error."""
        from src.chart_plan_loader import _validate_raw

        raw = {
            "title": "Test",
            "lanes": ["A"],
            "columns": ["C1"],
            "nodes": [
                {"key": "N1", "lane": "A", "col": 0},  # missing label
            ],
            "edges": [],
        }
        errors = _validate_raw(raw)
        label_errors = [e for e in errors if "label" in e.lower()]
        assert label_errors, (
            f"m5: _validate_raw should reject node without 'label'. Got errors: {errors}"
        )

    def test_validate_rejects_node_with_empty_lane(self):
        """A node with empty string lane should produce a validation error."""
        from src.chart_plan_loader import _validate_raw

        raw = {
            "title": "Test",
            "lanes": ["A"],
            "columns": ["C1"],
            "nodes": [
                {"key": "N1", "label": "Task", "lane": "", "col": 0},  # empty lane
            ],
            "edges": [],
        }
        errors = _validate_raw(raw)
        lane_errors = [e for e in errors if "lane" in e.lower()]
        assert lane_errors, (
            f"m5: _validate_raw should reject node with empty lane. Got errors: {errors}"
        )

    def test_validate_accepts_valid_node(self):
        """A fully valid node should not produce errors."""
        from src.chart_plan_loader import _validate_raw

        raw = {
            "title": "Test",
            "lanes": ["A"],
            "columns": ["C1"],
            "nodes": [
                {"key": "N1", "label": "Task", "lane": "A", "col": 0},
            ],
            "edges": [],
        }
        errors = _validate_raw(raw)
        assert errors == [], f"Valid plan should have no errors, got: {errors}"


class TestApplyPatch:
    """C2: apply_patch should support replace, add, and remove operations."""

    def _write_plan(self, tmp_path, data):
        p = tmp_path / "chart_plan.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return str(p)

    def _read_plan(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_replace_nested_value(self, tmp_path):
        """replace op should update an existing value at the given path."""
        from src.chart_plan_loader import apply_patch

        data = {"layout": {"col_width": 360}, "nodes": [{"key": "A", "dx": 0}]}
        path = self._write_plan(tmp_path, data)

        apply_patch(path, [{"op": "replace", "path": "/layout/col_width", "value": 400}])
        result = self._read_plan(path)
        assert result["layout"]["col_width"] == 400

    def test_replace_list_element(self, tmp_path):
        """replace op should work on list elements by index."""
        from src.chart_plan_loader import apply_patch

        data = {"nodes": [{"key": "A", "dx": 0}, {"key": "B", "dx": 10}]}
        path = self._write_plan(tmp_path, data)

        apply_patch(path, [{"op": "replace", "path": "/nodes/1/dx", "value": 80}])
        result = self._read_plan(path)
        assert result["nodes"][1]["dx"] == 80

    def test_add_new_key(self, tmp_path):
        """add op should insert a new key into a dict."""
        from src.chart_plan_loader import apply_patch

        data = {"layout": {"col_width": 360}}
        path = self._write_plan(tmp_path, data)

        apply_patch(path, [{"op": "add", "path": "/layout/lane_height", "value": 220}])
        result = self._read_plan(path)
        assert result["layout"]["lane_height"] == 220

    def test_add_list_element(self, tmp_path):
        """add op should insert into a list at the given index."""
        from src.chart_plan_loader import apply_patch

        data = {"nodes": [{"key": "A"}, {"key": "C"}]}
        path = self._write_plan(tmp_path, data)

        apply_patch(path, [{"op": "add", "path": "/nodes/1", "value": {"key": "B"}}])
        result = self._read_plan(path)
        assert [n["key"] for n in result["nodes"]] == ["A", "B", "C"]

    def test_remove_dict_key(self, tmp_path):
        """remove op should delete a key from a dict."""
        from src.chart_plan_loader import apply_patch

        data = {"layout": {"col_width": 360, "lane_height": 220}}
        path = self._write_plan(tmp_path, data)

        apply_patch(path, [{"op": "remove", "path": "/layout/lane_height"}])
        result = self._read_plan(path)
        assert "lane_height" not in result["layout"]

    def test_remove_list_element(self, tmp_path):
        """remove op should delete an element from a list by index."""
        from src.chart_plan_loader import apply_patch

        data = {"nodes": [{"key": "A"}, {"key": "B"}, {"key": "C"}]}
        path = self._write_plan(tmp_path, data)

        apply_patch(path, [{"op": "remove", "path": "/nodes/1"}])
        result = self._read_plan(path)
        assert [n["key"] for n in result["nodes"]] == ["A", "C"]
