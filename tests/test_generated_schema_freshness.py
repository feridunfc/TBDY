from __future__ import annotations

from pathlib import Path

from tbdy_engine.contracts.export_schema import export_all_schemas


ROOT = Path(__file__).resolve().parents[1]
COMMITTED_SCHEMA_DIR = ROOT / "tbdy_engine" / "contracts" / "generated" / "schema"


def test_generated_schemas_match_pydantic_models(tmp_path):
    exported_paths = export_all_schemas(tmp_path)

    for exported_path in exported_paths:
        committed_path = COMMITTED_SCHEMA_DIR / exported_path.name
        assert committed_path.exists(), f"Missing committed schema: {committed_path}"
        assert exported_path.read_text(encoding="utf-8") == committed_path.read_text(encoding="utf-8")
