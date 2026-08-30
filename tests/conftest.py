from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SRC = ROOT / "packages" / "etabs_gateway" / "src"

for path in (ROOT, GATEWAY_SRC):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)
