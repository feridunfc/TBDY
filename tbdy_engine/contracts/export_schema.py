from __future__ import annotations

import json
from pathlib import Path
from typing import List


CANONICAL_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "catalogs" / "schemas"


def export_all_schemas(output_dir: Path) -> List[Path]:
    """Export deterministic copies of the current canonical contract schemas.

    The canonical schema authority lives under ``tbdy_engine/catalogs/schemas``.
    This helper materializes those existing schemas for tooling/tests; it does
    not recreate the retired Pydantic runtime-contract model.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for source in sorted(CANONICAL_SCHEMA_DIR.glob("*.schema.json")):
        payload = json.loads(source.read_text(encoding="utf-8"))
        target = output_dir / source.name
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(target)
    if not written:
        raise FileNotFoundError(f"No canonical schemas found in {CANONICAL_SCHEMA_DIR}")
    return written
