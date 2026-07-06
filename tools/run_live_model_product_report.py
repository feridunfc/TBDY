#!/usr/bin/env python
"""Run the P2.0 C13.1-like live model product report.

The command has two modes:

* fixture/offline: read a JSON source-table fixture or a directory containing
  product_report_source_tables.json;
* live: attach to an already open ETABS model through the accepted safe
  FeatureResolver smoke path, read display tables, then render the product
  report.

It does not run ETABS analysis/design, does not mutate/save/unlock the model,
does not use Excel as production input, and does not use Streamlit.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tbdy_engine.product_reports.c13_1_report import write_c13_1_product_report


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _safe_manifest(*, live_etabs: bool, fixture_mode: bool) -> dict[str, Any]:
    return {
        "sprint": "P2.0_C13_1_LIVE_PRODUCT_REPORT_PARITY",
        "live_etabs_requested": live_etabs,
        "fixture_mode": fixture_mode,
        "product_slice_passed": True,
        "excel_production_path_used": False,
        "streamlit_ui_used": False,
        "legacy_runtime_used": False,
        "rebar_flexure_shear_capacity_unlocked": False,
        "check_engine_executed": False,
        "check_result_emitted": False,
        "etabs_model_mutated": False,
        "analysis_run": False,
        "design_run": False,
    }


def _prepare_fixture_input(input_path: Path, prepared_dir: Path) -> None:
    prepared_dir.mkdir(parents=True, exist_ok=True)
    if input_path.is_dir():
        source = input_path / "product_report_source_tables.json"
        if not source.is_file():
            raise FileNotFoundError(f"Fixture directory is missing product_report_source_tables.json: {input_path}")
        shutil.copy2(source, prepared_dir / "product_report_source_tables.json")
        manifest = input_path / "product_slice_manifest.json"
        if manifest.is_file():
            shutil.copy2(manifest, prepared_dir / "product_slice_manifest.json")
        else:
            _write_json(prepared_dir / "product_slice_manifest.json", _safe_manifest(live_etabs=False, fixture_mode=True))
        return
    if not input_path.is_file():
        raise FileNotFoundError(f"Fixture input not found: {input_path}")
    payload = _read_json(input_path)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("tables"), Mapping):
        raise ValueError("Fixture JSON must contain a top-level 'tables' mapping in product_report_source_tables shape")
    _write_json(prepared_dir / "product_report_source_tables.json", payload)
    _write_json(prepared_dir / "product_slice_manifest.json", _safe_manifest(live_etabs=False, fixture_mode=True))


def _prepare_live_input(args: argparse.Namespace, out_dir: Path, prepared_dir: Path) -> None:
    from tools.smoke_live_feature_resolver import main as smoke_main

    smoke_out = out_dir / "_pipeline" / "c8_live_feature_resolver"
    smoke_args = [
        "--live-etabs",
        "--out",
        str(smoke_out),
        "--max-rows",
        str(max(1, int(args.max_rows))),
        "--preferred-output-case",
        str(args.preferred_output_case),
    ]
    for option in ("target_component", "target_label", "target_story", "target_section"):
        value = getattr(args, option)
        if value:
            smoke_args.extend(["--" + option.replace("_", "-"), str(value)])
    rc = smoke_main(smoke_args)
    if rc != 0:
        raise RuntimeError(f"Live FeatureResolver source-table collection failed with return code {rc}")
    source = smoke_out / "product_report_source_tables.json"
    if not source.is_file():
        raise FileNotFoundError(f"Live source-table artifact missing: {source}")
    prepared_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, prepared_dir / "product_report_source_tables.json")
    _write_json(prepared_dir / "product_slice_manifest.json", _safe_manifest(live_etabs=True, fixture_mode=False))


def _summary_for_stdout(report: Mapping[str, Any]) -> dict[str, Any]:
    summary = dict(report.get("executive_summary") or {})
    return {
        "checked_scope_status": summary.get("checked_scope_status"),
        "model_scope_status": summary.get("model_scope_status"),
        "full_tbdy_compliance_status": summary.get("full_tbdy_compliance_status"),
        "unsupported_object_count_total": summary.get("unsupported_object_count_total"),
        "excluded_frame_object_count_total": summary.get("excluded_frame_object_count_total"),
        "frame_assignment_type_counts": summary.get("frame_assignment_type_counts"),
        "product_slice_passed": summary.get("product_slice_passed"),
        "report_product_passed": summary.get("report_product_passed"),
        "concrete_beam_section_type_count": summary.get("concrete_beam_section_type_count"),
        "concrete_beam_object_count": summary.get("concrete_beam_object_count"),
        "unsupported_beam_section_type_count": summary.get("unsupported_beam_section_type_count"),
        "unsupported_beam_object_count": summary.get("unsupported_beam_object_count"),
        "concrete_column_section_type_count": summary.get("concrete_column_section_type_count"),
        "concrete_column_object_count": summary.get("concrete_column_object_count"),
        "unsupported_column_section_type_count": summary.get("unsupported_column_section_type_count"),
        "unsupported_column_object_count": summary.get("unsupported_column_object_count"),
        "beam_fail_count": summary.get("beam_fail_count"),
        "column_fail_count": summary.get("column_fail_count"),
        "modal_mass_table_rows": summary.get("modal_mass_table_rows"),
        "modal_threshold": summary.get("modal_threshold"),
        "modal_ux_status": summary.get("modal_ux_status"),
        "modal_uy_status": summary.get("modal_uy_status"),
        "total_fail_count": summary.get("total_fail_count"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the P2.0 C13.1-like model-level product report.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--input", help="Fixture JSON or directory containing product_report_source_tables.json")
    mode.add_argument("--live-etabs", action="store_true", help="Attach to an already open ETABS model and read display tables")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--max-rows", type=int, default=100000, help="Maximum live rows for non-overridden display tables")
    parser.add_argument("--preferred-output-case", default="Crack_SeisY_UpSoil")
    parser.add_argument("--target-component", default=None)
    parser.add_argument("--target-label", default=None)
    parser.add_argument("--target-story", default=None)
    parser.add_argument("--target-section", default=None)
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prepared_dir = out_dir / "_input"
    try:
        if args.live_etabs:
            _prepare_live_input(args, out_dir, prepared_dir)
        else:
            _prepare_fixture_input(Path(str(args.input)), prepared_dir)
        report = write_c13_1_product_report(prepared_dir, out_dir)
        shutil.copy2(prepared_dir / "product_report_source_tables.json", out_dir / "product_report_source_tables.json")
        shutil.copy2(prepared_dir / "product_slice_manifest.json", out_dir / "product_slice_manifest.json")
        print(f"Wrote P2.2 C13.1 product report package to {out_dir}")
        deliverables = [
            "product_report.json",
            "product_report.md",
            "product_summary.json",
            "product_evidence.json",
            "product_report_source_tables.json",
            "product_slice_manifest.json",
            "product_report.html",
            "package_manifest.json",
            "README.md",
            "product_report_package.zip",
        ]
        print(json.dumps({
            "summary": _summary_for_stdout(report),
            "deliverables": [name for name in deliverables if (out_dir / name).is_file()],
        }, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        _write_json(out_dir / "product_report_error.json", {
            "ok": False,
            "error": str(exc),
            "live_etabs_requested": bool(args.live_etabs),
            "excel_production_path_used": False,
            "streamlit_ui_used": False,
            "legacy_runtime_used": False,
            "etabs_model_mutated": False,
            "analysis_run": False,
            "design_run": False,
        })
        print(f"P2.0 C13.1 product report failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
