from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tbdy_engine.features.evidence_contracts import assert_p1_17_evidence_contract
from tools import smoke_live_feature_resolver as smoke

DEFAULT_P1_14_INPUT = Path("tests/fixtures/p1_14_story_base_complete_population.json")
DEFAULT_P1_15_INPUT = Path("tests/fixtures/p1_15_material_design_basis_complete_population.json")
TARGET_ARGS = [
    "--target-component",
    "297",
    "--target-label",
    "B1",
    "--target-story",
    "+14.5",
    "--target-section",
    "B40x70",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify P1.17 frozen evidence contracts from fixture replay outputs.")
    parser.add_argument("--out", required=True, help="Output directory for P1.17 contract verification artifacts.")
    parser.add_argument("--p1-14-input", default=str(DEFAULT_P1_14_INPUT), help="P1.14 story/base fixture input.")
    parser.add_argument("--p1-15-input", default=str(DEFAULT_P1_15_INPUT), help="P1.15 material fixture input.")
    return parser


def _run_fixture_smoke(*, input_path: Path, out_dir: Path, preferred_output_case: str) -> dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    rc = smoke.main(
        [
            "--input",
            str(input_path),
            "--out",
            str(out_dir),
            *TARGET_ARGS,
            "--preferred-output-case",
            preferred_output_case,
        ]
    )
    if rc != 0:
        raise RuntimeError(f"fixture smoke failed for {input_path} with rc={rc}")
    return json.loads((out_dir / "feature_snapshot.json").read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    p1_14_snapshot = _run_fixture_smoke(
        input_path=Path(args.p1_14_input),
        out_dir=out / "p1_14_fixture_replay",
        preferred_output_case="Crack_SeisX_UpSoil",
    )
    p1_15_snapshot = _run_fixture_smoke(
        input_path=Path(args.p1_15_input),
        out_dir=out / "p1_15_fixture_replay",
        preferred_output_case="Crack_SeisY_UpSoil",
    )

    p1_14_report = assert_p1_17_evidence_contract(p1_14_snapshot, require=("story_base",))
    p1_15_report = assert_p1_17_evidence_contract(p1_15_snapshot, require=("material",))

    summary = {
        "contract_version": p1_14_report.contract_version,
        "ok": p1_14_report.ok and p1_15_report.ok,
        "live_etabs_required": False,
        "check_result_emitted": False,
        "engineering_verdict_emitted": False,
        "analysis_run": False,
        "design_run": False,
        "etabs_model_mutated": False,
        "p1_14_story_base": p1_14_report.as_dict(),
        "p1_15_material": p1_15_report.as_dict(),
    }
    (out / "p1_17_evidence_contract_freeze_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print("P1.17 evidence contract fixture verification: PASS")
    print(f"summary: {out / 'p1_17_evidence_contract_freeze_summary.json'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
