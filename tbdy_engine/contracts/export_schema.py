from __future__ import annotations
import json
from pathlib import Path
from typing import List, Tuple
from .models import ChecksContract, CombosContract, DatasetsContract, EvaluationsContract, ReportsContract, RuntimeCatalog, model_json_schema_compat
def export_all_schemas(output_dir: Path) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pairs: List[Tuple[str, object]] = [
        ("datasets.schema.json", DatasetsContract), ("evaluations.schema.json", EvaluationsContract),
        ("checks.schema.json", ChecksContract), ("combos.schema.json", CombosContract),
        ("reports.schema.json", ReportsContract), ("runtime_catalog.schema.json", RuntimeCatalog)]
    written = []
    for name, cls in pairs:
        path = output_dir / name
        with path.open("w", encoding="utf-8") as f:
            json.dump(model_json_schema_compat(cls), f, ensure_ascii=False, indent=2)
        written.append(path)
    return written
