#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.features.feature_snapshot_artifact_validator import validate_artifact_file_set  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate C13.3-P3 no-live FeatureSnapshot artifacts")
    parser.add_argument("--artifact-dir", required=True)
    args = parser.parse_args(argv)

    report = validate_artifact_file_set(Path(args.artifact_dir))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["validation_status"] == "VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
