from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

if "tbdy_engine" not in sys.modules:
    import types

    tbdy_pkg = types.ModuleType("tbdy_engine")
    tbdy_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "tbdy_engine")]
    sys.modules["tbdy_engine"] = tbdy_pkg

from tbdy_engine.design.beams.beam_core_failure_diagnosis import (
    diagnose_r7b_batch_summary,
    extract_check_records,
    infer_check_category,
    most_critical_checks,
    normalize_check_record,
    normalize_status,
)


def test_extract_check_records_from_nested_engine_report() -> None:
    report = {
        "meta": {"status": "FAIL"},
        "beam": {
            "checks": [
                {"check_type": "beam_shear_vr", "status": "OK", "value": 1},
                {"name": "flexure moment", "passed": False, "utilization": 1.2},
            ]
        },
        "other": {"nested": {"result": {"id": "geometry_cover", "result": "WARN"}}},
    }

    records = extract_check_records(report)

    assert len(records) == 3
    assert {record.get("check_type") or record.get("name") or record.get("id") for record in records} == {
        "beam_shear_vr",
        "flexure moment",
        "geometry_cover",
    }


@pytest.mark.parametrize(
    "record, expected",
    (
        ({"name": "a", "status": "OK"}, "PASS"),
        ({"name": "a", "result": "passed"}, "PASS"),
        ({"name": "a", "passed": True}, "PASS"),
        ({"name": "a", "ok": True}, "PASS"),
        ({"name": "a", "status": "FAIL"}, "FAIL"),
        ({"name": "a", "result": "error"}, "FAIL"),
        ({"name": "a", "passed": False}, "FAIL"),
        ({"name": "a", "ok": False}, "FAIL"),
        ({"name": "a", "status": "WARNING"}, "WARN"),
        ({"name": "a", "status": "MAYBE"}, "UNKNOWN"),
    ),
)
def test_status_normalization(record: dict[str, object], expected: str) -> None:
    assert normalize_status(record) == expected


@pytest.mark.parametrize(
    "check_key, expected",
    (
        ("beam_shear_capacity_design_ve_le_vr", "capacity_design_shear"),
        ("beam_shear_vr", "shear"),
        ("flexure_moment_md", "flexure"),
        ("geometry_effective_depth", "geometry"),
        ("missing_required_input", "input_contract"),
        ("other_check", "unknown"),
    ),
)
def test_category_inference(check_key: str, expected: str) -> None:
    assert infer_check_category(check_key) == expected


def test_utilization_sorting_picks_highest_failed_check() -> None:
    failed = [
        normalize_check_record({"check_type": "beam_shear_vr", "status": "FAIL", "utilization": 0.9}),
        normalize_check_record({"check_type": "beam_flexure_moment", "status": "FAIL", "utilization": 1.3}),
        normalize_check_record({"check_type": "beam_shear_capacity_design_ve_le_vr", "status": "FAIL", "utilization": 1.1}),
    ]

    critical = most_critical_checks(failed)

    assert critical[0]["check_key"] == "beam_flexure_moment"
    assert critical[0]["utilization"] == 1.3


def test_missing_engine_report_is_included_without_crash(tmp_path: Path) -> None:
    summary_path = tmp_path / "story_beam_batch_summary.json"
    missing_report = tmp_path / "B1" / "engine_report.json"
    summary_path.write_text(
        json.dumps(
            {
                "selected_story": "+9.00",
                "selected_combos": ["Grav_Ult", "Cap_SeisX"],
                "actions_source": "etabs_results",
                "beam_count_processed": 1,
                "beam_count_failed": 0,
                "beams": [
                    {
                        "object_name": "1",
                        "label": "B35",
                        "story": "+9.00",
                        "section": "B60x70",
                        "beam_core_status": "FAIL",
                        "actions": {},
                        "governing": {},
                        "artifact_paths": {"json": str(missing_report), "xlsx": "missing.xlsx"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = diagnose_r7b_batch_summary(summary_path=summary_path, output_dir=tmp_path / "diagnosis")

    beam = result["diagnosis"]["beams"][0]
    assert beam["artifact_missing"] is True
    assert beam["failed_check_count"] == 0


def test_r7b_summary_fixture_diagnosis_outputs_json_and_md(tmp_path: Path) -> None:
    summary_path = _make_fake_summary_with_reports(tmp_path)

    result = diagnose_r7b_batch_summary(summary_path=summary_path, output_dir=tmp_path / "diagnosis")

    assert result["status"] == "OK"
    assert result["json_path"].exists()
    assert result["md_path"].exists()
    diagnosis = json.loads(result["json_path"].read_text(encoding="utf-8"))
    assert diagnosis["selected_story"] == "+9.00"
    assert diagnosis["selected_combos"] == ["Grav_Ult", "Cap_SeisX"]
    assert diagnosis["actions_source"] == "etabs_results"
    assert len(diagnosis["beams"]) == 3
    assert diagnosis["beams"][0]["failed_check_count"] == 2
    assert diagnosis["beams"][0]["failure_categories"]["capacity_design_shear"]
    assert diagnosis["beams"][0]["failure_categories"]["flexure"]


def test_report_wording_guard(tmp_path: Path) -> None:
    summary_path = _make_fake_summary_with_reports(tmp_path)

    result = diagnose_r7b_batch_summary(summary_path=summary_path, output_dir=tmp_path / "diagnosis")
    text = result["md_path"].read_text(encoding="utf-8")

    assert "BeamCore checks executed" in text
    assert "failure diagnosis" in text
    assert "observed ETABS actions" in text
    lowered = text.lower()
    assert "beam designed" not in lowered
    assert "etabs validated" not in lowered
    assert "production ready" not in lowered
    assert "code compliance proven" not in lowered


def test_boundary_guard_has_no_forbidden_terms() -> None:
    source = Path("tbdy_engine/design/beams/beam_core_failure_diagnosis.py").read_text(encoding="utf-8-sig")
    test_source = Path("tests/test_beam_core_failure_diagnosis.py").read_text(encoding="utf-8-sig")
    combined = source + "\n" + test_source

    forbidden = (
        "com" + "types",
        "Sap" + "Model",
        "read_" + "etabs" + "_table_on_demand",
        "Reporting" + "Facade",
        "Check" + "Adapter",
        "Beam" + "Evaluation" + "Package",
    )

    for term in forbidden:
        assert term not in combined


def _make_fake_summary_with_reports(tmp_path: Path) -> Path:
    beams = []
    for index in range(1, 4):
        beam_dir = tmp_path / str(index)
        beam_dir.mkdir()
        report_path = beam_dir / "engine_report.json"
        report_path.write_text(
            json.dumps(
                {
                    "checks": [
                        {"check_type": "beam_shear_capacity_design_ve_le_vr", "status": "FAIL", "utilization": 1.45, "message": "Ve > Vr"},
                        {"check_type": "beam_flexure_moment_md", "passed": False, "ratio": 1.2, "reason": "Md demand high"},
                        {"check_type": "beam_shear_vr", "status": "OK", "utilization": 0.7},
                        {"id": "geometry_cover", "result": "WARN", "message": "cover review"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        beams.append(
            {
                "object_name": str(index),
                "label": f"B{index}",
                "story": "+9.00",
                "section": "B60x70",
                "beam_core_status": "FAIL",
                "actions": {
                    "Vd_left_kN": 100 + index,
                    "Ve_left_kN": 120 + index,
                    "Md_left_neg_kNm": 200 + index,
                    "Md_mid_pos_kNm": 150 + index,
                    "Md_right_neg_kNm": 190 + index,
                    "axial_kN": 5,
                },
                "governing": {
                    "Vd_left_kN": {"combo": "Cap_SeisX", "station": 0.0},
                    "Ve_left_kN": {"combo": "Cap_SeisX", "station": 0.0},
                    "Md_left_neg_kNm": {"combo": "Cap_SeisX", "station": 0.0},
                    "Md_mid_pos_kNm": {"combo": "Grav_Ult", "station": 2500.0},
                    "Md_right_neg_kNm": {"combo": "Cap_SeisX", "station": 5000.0},
                    "axial_kN": {"combo": "Grav_Ult", "station": 0.0},
                },
                "artifact_paths": {"json": str(report_path), "xlsx": str(beam_dir / "engine_report.xlsx")},
            }
        )

    summary_path = tmp_path / "story_beam_batch_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "selected_story": "+9.00",
                "selected_combos": ["Grav_Ult", "Cap_SeisX"],
                "actions_source": "etabs_results",
                "beam_count_processed": 3,
                "beam_count_failed": 0,
                "beams": beams,
            }
        ),
        encoding="utf-8",
    )
    return summary_path

def test_repo_relative_r7b_artifact_path_resolves_from_current_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path
    summary_dir = root / "_local" / "live_etabs_story_beam_batch"
    report_dir = summary_dir / "1"
    report_dir.mkdir(parents=True)
    report_path = report_dir / "engine_report.json"
    report_path.write_text(
        json.dumps(
            {
                "checks": [
                    {
                        "check_type": "beam_shear_capacity_design_ve_le_vr",
                        "status": "FAIL",
                        "utilization": 1.25,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    summary_path = summary_dir / "story_beam_batch_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "selected_story": "+9.00",
                "selected_combos": ["Grav_Ult", "Cap_SeisX"],
                "actions_source": "etabs_results",
                "beam_count_processed": 1,
                "beam_count_failed": 0,
                "beams": [
                    {
                        "object_name": "1",
                        "label": "B35",
                        "story": "+9.00",
                        "section": "B60x70",
                        "beam_core_status": "FAIL",
                        "actions": {},
                        "governing": {},
                        "artifact_paths": {
                            "json": "_local/live_etabs_story_beam_batch/1/engine_report.json",
                            "xlsx": "_local/live_etabs_story_beam_batch/1/engine_report.xlsx",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(root)

    result = diagnose_r7b_batch_summary(
        summary_path=summary_path,
        output_dir=root / "_local" / "live_etabs_story_beam_batch_failure_diagnosis",
    )

    beam = result["diagnosis"]["beams"][0]
    assert beam["artifact_missing"] is False
    assert beam["failed_check_count"] == 1
    assert beam["failed_checks"][0]["check_key"] == "beam_shear_capacity_design_ve_le_vr"

