from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from tbdy_engine.contracts.export_schema import export_all_schemas
def main() -> int:
    paths = export_all_schemas(ROOT / "tbdy_engine" / "contracts" / "generated" / "schema")
    print("EXPORTED_SCHEMAS")
    for p in paths: print(p)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
