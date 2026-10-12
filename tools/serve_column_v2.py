"""Launch the offline column workspace from a repository checkout."""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO/'packages/etabs_gateway/src')]
from apps.column_v2.server import main

if __name__ == '__main__':
    main(REPO)
