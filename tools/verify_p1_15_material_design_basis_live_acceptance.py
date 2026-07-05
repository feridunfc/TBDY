#!/usr/bin/env python
"""P1.15 material design-basis source acceptance verifier.

This script validates source/evidence invariants only. It does not run
CheckEngine, does not emit CheckResult objects, does not evaluate TBDY/TS500
material compliance, and never mutates ETABS.

Modes:
* fixture replay: pass --input. Built-in fixture expectations are enforced by
  default.
* live source smoke: omit --input. Current live material values are allowed to
  differ from fixture values unless --strict-expected or --expected-json is used.
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

DEFAULT_EXPECTED: Mapping[str, Any] = {
    "component_section_name": "B40x70",
    "component_section_type": "Beam",
    "section_concrete_material_name": "C30/37",
    "section_rebar_material_name": "B420C",
    "concrete_fck_mpa": 30.0,
    "rebar_fyk_mpa": 500.0,
}

REQUIRED_FEATURES: tuple[str, ...] = (
    "component_section_name",
    "component_section_type",
    "section_concrete_material_name",
    "concrete_fck_mpa",
    "concrete_material_source_reference",
    "material_unit_basis",
)
OPTIONAL_FEATURES: tuple[str, ...] = (
    "section_rebar_material_name",
    "rebar_fyk_mpa",
    "rebar_material_source_reference",
)
NUMERIC_FEATURES: tuple[str, ...] = ("concrete_fck_mpa", "rebar_fyk_mpa")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshots_by_type(snapshot_payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(item.get("component_type")): item for item in snapshot_payload.get("snapshots", []) if isinstance(item, Mapping)}


def _material_snapshot(snapshot_payload: Mapping[str, Any]) -> Mapping[str, Any]:
    snapshots = _snapshots_by_type(snapshot_payload)
    material = snapshots.get("material")
    if not isinstance(material, Mapping):
        raise AssertionError("material snapshot missing")
    return material


def _feature(material_snapshot: Mapping[str, Any], feature_name: str) -> Mapping[str, Any]:
    features = material_snapshot.get("features", {})
    feature = features.get(feature_name) if isinstance(features, Mapping) else None
    if not isinstance(feature, Mapping):
        raise AssertionError(f"material feature missing: {feature_name}")
    return feature


def _first_evidence(feature: Mapping[str, Any], feature_name: str) -> Mapping[str, Any]:
    evidence_list = feature.get("evidence")
    if not isinstance(evidence_list, list) or not evidence_list or not isinstance(evidence_list[0], Mapping):
        raise AssertionError(f"{feature_name}: missing evidence")
    return evidence_list[0]


def _assert_finite_numeric(feature_name: str, value: Any) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise AssertionError(f"{feature_name}: expected finite numeric value, observed {value!r}")


def _assert_close_or_equal(feature_name: str, actual: Any, expected: Any, tolerance: float) -> None:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        _assert_finite_numeric(feature_name, actual)
        if abs(float(actual) - float(expected)) > tolerance:
            raise AssertionError(f"{feature_name}: expected {expected!r}, observed {actual!r}, tolerance={tolerance}")
        return
    if actual != expected:
        raise AssertionError(f"{feature_name}: expected {expected!r}, observed {actual!r}")


def _assert_material_evidence(feature_name: str, feature: Mapping[str, Any], *, require_resolved: bool) -> None:
    status = str(feature.get("status"))
    evidence = _first_evidence(feature, feature_name)
    if require_resolved and status != "RESOLVED":
        raise AssertionError(f"{feature_name}: expected RESOLVED, observed {status}")
    if status == "RESOLVED":
        if evidence.get("evidence_status") != "FULL":
            raise AssertionError(f"{feature_name}: resolved feature lacks FULL evidence")
        if not evidence.get("source_table"):
            raise AssertionError(f"{feature_name}: missing source table")
        if not evidence.get("actual_table_name"):
            raise AssertionError(f"{feature_name}: missing actual table name")
        if not evidence.get("source_column"):
            raise AssertionError(f"{feature_name}: missing source column")
        if "raw_value" not in evidence or evidence.get("raw_value") is None:
            raise AssertionError(f"{feature_name}: missing raw value")
        if "normalized_value" not in evidence or evidence.get("normalized_value") is None:
            raise AssertionError(f"{feature_name}: missing normalized value")
    elif status in {"PARTIAL", "MISSING"}:
        if not evidence.get("reason"):
            raise AssertionError(f"{feature_name}: non-resolved feature requires explicit reason")
        return
    else:
        raise AssertionError(f"{feature_name}: unsupported material feature status {status!r}")

    source_row = evidence.get("source_row")
    if not isinstance(source_row, Mapping):
        raise AssertionError(f"{feature_name}: missing source_row evidence object")
    if not source_row.get("source_reference"):
        raise AssertionError(f"{feature_name}: missing stable source reference")
    if not source_row.get("stable_row_reference"):
        raise AssertionError(f"{feature_name}: missing stable row reference object")
    if not isinstance(source_row.get("selected_component_identity_context"), Mapping):
        raise AssertionError(f"{feature_name}: missing selected component context")
    if not isinstance(source_row.get("selected_section_context"), Mapping):
        raise AssertionError(f"{feature_name}: missing selected section context")
    if not isinstance(source_row.get("complete_source_row"), Mapping) or not source_row.get("complete_source_row"):
        raise AssertionError(f"{feature_name}: missing complete source row payload")
    if not source_row.get("selection_reason"):
        raise AssertionError(f"{feature_name}: missing selection reason")
    resolver_count = source_row.get("resolver_row_count")
    if not isinstance(resolver_count, int) or resolver_count <= 0:
        raise AssertionError(f"{feature_name}: missing positive resolver row count")
    reported = source_row.get("reported_row_count")
    if reported is not None and reported != resolver_count:
        raise AssertionError(f"{feature_name}: reported/resolver row count mismatch: {reported!r} vs {resolver_count!r}")


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
        raise AssertionError("check_results.json must not be emitted by P1.15 source smoke")
    forbidden = ('"engineering_verdict"', '"result_status"', '"pass_rule"', '"utilization"')
    for path in out_dir.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        if "CheckResult" in text or any(token in text for token in forbidden):
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


def _load_expected(args: argparse.Namespace) -> Mapping[str, Any] | None:
    if args.expected_json is not None:
        payload = _load_json(args.expected_json)
        if not isinstance(payload, Mapping):
            raise AssertionError("expected JSON root must be an object keyed by material feature name")
        return payload
    if args.input is not None or args.strict_expected:
        return DEFAULT_EXPECTED
    return None


def _run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = args.out
    if out_dir.exists():
        shutil.rmtree(out_dir)
    smoke_args = [
        "--out", str(out_dir),
        "--target-component", args.target_component,
        "--target-label", args.target_label,
        "--target-story", args.target_story,
        "--target-section", args.target_section,
        "--preferred-output-case", args.preferred_output_case,
        "--max-rows", str(args.max_rows),
    ]
    mode = "fixture_replay" if args.input else "live_source_smoke"
    if args.input:
        smoke_args.extend(["--input", str(args.input)])
    else:
        smoke_args.append("--live-etabs")
    before_state = _etabs_model_state() if not args.input else {"available": False, "fixture_mode": True}
    rc = smoke.main(smoke_args)
    after_state = _etabs_model_state() if not args.input else {"available": False, "fixture_mode": True}
    if rc != 0:
        raise RuntimeError(f"smoke_live_feature_resolver failed with exit code {rc}")
    if before_state.get("available") and after_state.get("available"):
        if before_state.get("model_filename") != after_state.get("model_filename"):
            raise AssertionError("ETABS model filename changed during P1.15 verifier")
        if before_state.get("model_locked") != after_state.get("model_locked"):
            raise AssertionError("ETABS model locked state changed during P1.15 verifier")
    snapshot = _load_json(out_dir / "feature_snapshot.json")
    material = _material_snapshot(snapshot)
    expected = _load_expected(args)
    observed: dict[str, Any] = {}
    for feature_name in REQUIRED_FEATURES:
        feature = _feature(material, feature_name)
        _assert_material_evidence(feature_name, feature, require_resolved=True)
        observed[feature_name] = feature.get("value")
    for feature_name in OPTIONAL_FEATURES:
        feature = _feature(material, feature_name)
        _assert_material_evidence(feature_name, feature, require_resolved=False)
        if feature.get("status") == "RESOLVED":
            observed[feature_name] = feature.get("value")
    for feature_name in NUMERIC_FEATURES:
        feature = _feature(material, feature_name)
        if feature.get("status") == "RESOLVED":
            _assert_finite_numeric(feature_name, feature.get("value"))
    if expected is not None:
        for feature_name, expected_value in expected.items():
            if feature_name not in material.get("features", {}):
                raise AssertionError(f"expected feature not present: {feature_name}")
            observed_value = material["features"][feature_name].get("value")
            _assert_close_or_equal(feature_name, observed_value, expected_value, args.tolerance)
    _assert_no_verdicts(out_dir)
    summary = {
        "mode": mode,
        "strict_expected_enforced": expected is not None,
        "out_dir": str(out_dir),
        "observed": observed,
        "check_result_emitted": False,
        "engineering_verdict_emitted": False,
        "analysis_run": False,
        "design_run": False,
        "etabs_model_mutated": False,
        "model_state_before": before_state,
        "model_state_after": after_state,
    }
    (out_dir / "p1_15_material_acceptance_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "P1.15 material design-basis source acceptance. "
            "Omit --input for live ETABS smoke; pass --input for immutable fixture replay. "
            "No checks, no design, no verdicts."
        )
    )
    parser.add_argument("--out", type=Path, default=Path("local_out/p1_15_live_material_design_basis_acceptance"))
    parser.add_argument("--input", type=Path, default=None, help="Optional fixture input; omit for live ETABS source smoke.")
    parser.add_argument("--strict-expected", action="store_true", help="Enforce built-in immutable fixture expectations even in live mode.")
    parser.add_argument("--expected-json", type=Path, default=None, help="Optional feature-keyed expected values to enforce in any mode.")
    parser.add_argument("--target-component", default="297")
    parser.add_argument("--target-label", default="B1")
    parser.add_argument("--target-story", default="+14.5")
    parser.add_argument("--target-section", default="B40x70")
    parser.add_argument("--preferred-output-case", default="Crack_SeisY_UpSoil")
    parser.add_argument("--max-rows", type=int, default=10)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    summary = _run_smoke(args)
    print("P1.15 material design-basis source acceptance: PASS")
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
