from __future__ import annotations

from pathlib import Path

from tbdy_engine.contracts.export_schema import CANONICAL_SCHEMA_DIR, export_all_schemas


def test_generated_schemas_match_current_canonical_schema_artifacts(tmp_path):
    exported_paths = export_all_schemas(tmp_path)
    assert exported_paths

    canonical_names = {path.name for path in CANONICAL_SCHEMA_DIR.glob("*.schema.json")}
    assert {path.name for path in exported_paths} == canonical_names

    for exported_path in exported_paths:
        canonical_path = CANONICAL_SCHEMA_DIR / exported_path.name
        assert canonical_path.exists(), f"Missing canonical schema: {canonical_path}"
        assert exported_path.read_text(encoding="utf-8") == canonical_path.read_text(encoding="utf-8")
