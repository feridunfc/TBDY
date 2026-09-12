from __future__ import annotations

from pathlib import Path
from typing import List


CANONICAL_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "catalogs" / "schemas"


def export_all_schemas(output_dir: Path) -> List[Path]:
    """Materialize exact copies of the current canonical contract schemas.

    Schema authority remains ``tbdy_engine/catalogs/schemas``.  This helper is
    only an artifact exporter; it does not recreate the retired Pydantic
    runtime-contract model.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for source in sorted(CANONICAL_SCHEMA_DIR.glob("*.schema.json")):
        target = output_dir / source.name
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(target)
    if not written:
        raise FileNotFoundError(f"No canonical schemas found in {CANONICAL_SCHEMA_DIR}")
    return written
