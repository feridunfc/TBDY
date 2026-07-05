#!/usr/bin/env python
"""Manual P1.14 live acceptance for story/base source evidence.

This script attaches only through the existing live FeatureResolver smoke path.
It does not run analysis, design, CheckEngine, or emit CheckResult objects.

Modes:
* fixture replay mode: pass --input. The immutable fixture expectations are
  enforced by default.
* live smoke mode: omit --input. Current live ETABS source values are allowed
  to differ from old evidence, but source/evidence/no-mutation invariants are
  still enforced. Use --strict-expected or --expected-json to enforce numeric
  expectations during live mode.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools import smoke_live_feature_resolver as smoke

DEFAULT_EXPECTED: Mapping[str, Mapping[str, float]] = {
    "Crack_SeisX_UpSoil": {
        "story_drift_value": 1.125,
        "story_torsion_a1_coefficient": 1.069,
        "base_reaction_fx": 20396.1433,
        "base_reaction_fy": 5360.3225,
    },
    "Crack_SeisY_UpSoil": {
        "story_drift_value": 0.534,
        "story_torsion_a1_coefficient": 1.157,
        "base_reaction_fx": 12979.0527,
        "base_reaction_fy": 12890.0006,
    },
}

REQUIRED_FEATURES: tuple[str, ...] = (
    "story_drift_value",
    "story_torsion_a1_coefficient",
    "base_reaction_fx",
    "base_reaction_fy",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshots_by_type(snapshot_payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(item.get("component_type")): item for item in snapshot_payload.get("snapshots", []) if isinstance(item, Mapping)}


def _feature_value(snapshot_payload: Mapping[str, Any], component_type: str, feature_name: str) -> tuple[str, Any, Mapping[str, Any]]:
    snapshot = _snapshots_by_type(snapshot_payload)[component_type]
    feature = snapshot["features"][feature_name]
    evidence = feature.get("evidence", [{}])[0]
    return str(feature.get("status")), feature.get("value"), evidence


def _assert_close(name: str, actual: Any, expected: float, tolerance: float) -> None:
    if not isinstance(actual, (int, float)) or isinstance(actual, bool) or not math.isfinite(float(actual)):
        raise AssertionError(f"{name}: expected finite numeric {expected}, observed {actual!r}")
    if abs(float(actual) - expected) > tolerance:
        raise AssertionError(f"{name}: expected {expected}, observed {actual!r}, tolerance {tolerance}")


def _assert_resolved_numeric(name: str, actual: Any) -> None:
    if not isinstance(actual, (int, float)) or isinstance(actual, bool) or not math.isfinite(float(actual)):
        raise AssertionError(f"{name}: expected finite resolved numeric value, observed {actual!r}")


def _assert_source_evidence(case_name: str, feature_name: str, evidence: Mapping[str, Any]) -> None:
    if evidence.get("output_case") != case_name:
        raise AssertionError(f"{case_name}.{feature_name}: evidence output_case mismatch: {evidence.get('output_case')!r}")
    source_row = evidence.get("source_row", {})
    if not isinstance(source_row, Mapping):
        raise AssertionError(f"{case_name}.{feature_name}: missing source-row evidence object")
    row_index = source_row.get("row_index")
    resolver_row_count = source_row.get("resolver_row_count")
    if not isinstance(row_index, int) or row_index < 0:
        raise AssertionError(f"{case_name}.{feature_name}: missing non-negative row-index evidence")
    if not isinstance(resolver_row_count, int) or resolver_row_count <= 0:
        raise AssertionError(f"{case_name}.{feature_name}: missing positive resolver row-count evidence")
    reported = source_row.get("reported_row_count")
    if reported is not None and reported != resolver_row_count:
        raise AssertionError(
            f"{case_name}.{feature_name}: reported/resolver row count mismatch: {reported!r} vs {resolver_row_count!r}"
        )
    complete_source_row = source_row.get("complete_source_row")
    if not isinstance(complete_source_row, Mapping) or not complete_source_row:
        raise AssertionError(f"{case_name}.{feature_name}: missing complete source row evidence")
    if not source_row.get("selection_reason"):
        raise AssertionError(f"{case_name}.{feature_name}: missing selection reason")


def _assert_no_verdicts(out_dir: Path) -> None:
    snapshot = _load_json(out_dir / "feature_snapshot.json")
    metadata = snapshot.get("metadata", {})
    if metadata.get("check_engine_executed") is not False:
        raise AssertionError("CheckEngine executed unexpectedly")
    if metadata.get("check_result_emitted") is not False:
        raise AssertionError("CheckResult emitted unexpectedly")
    if metadata.get("live_verdict_emitted") is not False:
        raise AssertionError("Engineering verdict emitted unexpectedly")
    if (out_dir / "check_results.json").exists():
        raise AssertionError("check_results.json must not be emitted by P1.14 smoke")
    for path in out_dir.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        if "CheckResult" in text or '"engineering_verdict"' in text:
            raise AssertionError(f"Forbidden CheckResult/engineering verdict payload in {path.name}")


def _etabs_model_state() -> dict[str, Any]:
    try:  # pragma: no cover - requires Windows/ETABS/comtypes
        import comtypes.client  # type: ignore[import-not-found]
        etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
        sap_model = etabs_object.SapModel
        filename = None
        locked = None
        if hasattr(sap_model, "GetModelFilename"):
            filename = sap_model.GetModelFilename()
        if hasattr(sap_model, "GetModelIsLocked"):
            locked = sap_model.GetModelIsLocked()
        return {"available": True, "model_filename": filename, "model_locked": locked}
    except Exception as exc:  # pragma: no cover
        return {"available": False, "error": str(exc)}


def _load_expected(args: argparse.Namespace) -> Mapping[str, Mapping[str, float]] | None:
    if args.expected_json is not None:
        payload = _load_json(args.expected_json)
        if not isinstance(payload, Mapping):
            raise AssertionError("expected JSON root must be an object keyed by output case")
        return payload  # type: ignore[return-value]
    if args.input is not None or args.strict_expected:
        return DEFAULT_EXPECTED
    return None


def _run_case(args: argparse.Namespace, case_name: str, expected: Mapping[str, Mapping[str, float]] | None) -> dict[str, Any]:
    out_dir = args.out / case_name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    smoke_args = [
        "--out", str(out_dir),
        "--target-component", args.target_component,
        "--target-label", args.target_label,
        "--target-story", args.target_story,
        "--target-section", args.target_section,
        "--preferred-output-case", case_name,
        "--max-rows", str(args.max_rows),
    ]
    if args.input:
        smoke_args.extend(["--input", str(args.input)])
    else:
        smoke_args.append("--live-etabs")
    rc = smoke.main(smoke_args)
    if rc != 0:
        raise RuntimeError(f"smoke_live_feature_resolver failed for {case_name} with exit code {rc}")
    snapshot = _load_json(out_dir / "feature_snapshot.json")
    expected_for_case = expected.get(case_name, {}) if expected is not None else {}
    observed: dict[str, Any] = {}
    for feature_name in REQUIRED_FEATURES:
        component = "story" if feature_name.startswith("story_") else "global"
        status, value, evidence = _feature_value(snapshot, component, feature_name)
        if status != "RESOLVED":
            raise AssertionError(f"{case_name}.{feature_name}: expected RESOLVED, observed {status}")
        _assert_resolved_numeric(f"{case_name}.{feature_name}", value)
        _assert_source_evidence(case_name, feature_name, evidence)
        if feature_name in expected_for_case:
            _assert_close(f"{case_name}.{feature_name}", value, expected_for_case[feature_name], args.tolerance)
        observed[feature_name] = value
    _assert_no_verdicts(out_dir)
    return observed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "P1.14 story/base source acceptance. "
            "Omit --input for live ETABS smoke; pass --input for immutable fixture replay. "
            "No checks, no design, no verdicts."
        )
    )
    parser.add_argument("--out", type=Path, default=Path("local_out/p1_14_live_story_base_acceptance"))
    parser.add_argument("--input", type=Path, default=None, help="Optional fixture input for offline dry-run; omit for live ETABS.")
    parser.add_argument(
        "--strict-expected",
        action="store_true",
        help="Enforce built-in immutable evidence expectations even in live mode.",
    )
    parser.add_argument(
        "--expected-json",
        type=Path,
        default=None,
        help="Optional case-keyed expected numeric values to enforce in any mode.",
    )
    parser.add_argument("--target-component", default="297")
    parser.add_argument("--target-label", default="B1")
    parser.add_argument("--target-story", default="+14.5")
    parser.add_argument("--target-section", default="B40x70")
    parser.add_argument("--max-rows", type=int, default=10)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    expected = _load_expected(args)
    before = _etabs_model_state() if args.input is None else {"available": False, "offline_fixture": True}
    case_names = tuple(expected.keys()) if expected is not None else tuple(DEFAULT_EXPECTED.keys())
    results = {case_name: _run_case(args, case_name, expected) for case_name in case_names}
    after = _etabs_model_state() if args.input is None else {"available": False, "offline_fixture": True}
    if before.get("available") and after.get("available"):
        if before.get("model_filename") != after.get("model_filename") or before.get("model_locked") != after.get("model_locked"):
            raise AssertionError(f"ETABS model state changed: before={before!r}, after={after!r}")
    summary = {
        "p1_14_live_story_base_acceptance": "PASS",
        "mode": "fixture_replay" if args.input is not None else "live_source_evidence_smoke",
        "strict_expected_enforced": expected is not None,
        "check_result_emitted": False,
        "engineering_verdict_emitted": False,
        "etabs_model_mutated": False,
        "analysis_run": False,
        "design_run": False,
        "model_state_before": before,
        "model_state_after": after,
        "results": results,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "p1_14_live_story_base_acceptance_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
