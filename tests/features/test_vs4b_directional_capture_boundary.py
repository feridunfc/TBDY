from __future__ import annotations

import pytest

from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.features import etabs_mdev_mo_evidence as ev


def _base_context():
    return ev.ReviewedRegulatoryBaseContext(
        elevation_m=-5.15,
        rigid_basement_above_base=False,
        review_refs=("review:base",),
        provenance_refs=("project:base",),
    )


def _result_context():
    return ev.ReviewedResultPopulationContext(
        analysis_method=ev.ReviewedAnalysisMethod.MODAL_COMBINATION,
        scaling_state_id="reviewed:scaled-final",
        result_operator_id="reviewed:signed-same-realization",
        wall_to_total_sign_factor=1,
        review_refs=("review:result-state",),
        provenance_refs=("project:result-state",),
    )


def _static_sections() -> ev.StaticTableCapture:
    return ev.StaticTableCapture(
        table_key=ev.PIER_SECTIONS_TABLE,
        actual_table_name=ev.PIER_SECTIONS_TABLE,
        return_code=0,
        reported_row_count=1,
        captured_row_count=1,
        capture_status=RuntimeCaptureStatus.FULL.value,
        rows=(
            {
                "Story": "B1",
                "Pier": "P1",
                "CGBotZ": -5.15,
                "AxisAngle": 0.0,
            },
        ),
    )


def _exact_capture(table_key: str, case_name: str, row: dict[str, object]):
    rows = (row,)
    return ev.ExactOutputCaseCapture(
        table_key=table_key,
        actual_table_name=table_key,
        requested_case=case_name,
        return_code=0,
        reported_row_count=1,
        captured_row_count=1,
        capture_status=RuntimeCaptureStatus.FULL.value,
        fetched_rows=rows,
        exact_rows=rows,
        selection_snapshot={"cases": ["before"]},
        restore_result={"phase": "restore_verify", "success": True},
        restore_exact_equality_result=True,
        state_diagnostics=(),
    )


@pytest.mark.parametrize(
    ("direction", "cases", "forbidden_fragment"),
    (
        ("X", ("~Static+EccRSX", "~Static-EccRSX"), "RSY"),
        ("Y", ("~Static+EccRSY", "~Static-EccRSY"), "RSX"),
    ),
)
def test_capture_live_mdev_mo_evidence_is_one_direction_independent(
    monkeypatch,
    direction,
    cases,
    forbidden_fragment,
):
    monkeypatch.setattr(ev, "capture_static_table", lambda *_a, **_k: _static_sections())
    calls: list[tuple[str, str]] = []

    def fake_capture(_db, table_key, case_name):
        calls.append((table_key, case_name))
        if table_key == ev.PIER_FORCES_TABLE:
            row = {
                "Story": "B1",
                "Pier": "P1",
                "OutputCase": case_name,
                "CaseType": "LinRespSpec",
                "Location": "Bottom",
                "M2": 30.0 if direction == "Y" else 0.0,
                "M3": 30.0 if direction == "X" else 0.0,
            }
        elif table_key == ev.STORY_FORCES_TABLE:
            row = {
                "Story": "B1",
                "OutputCase": case_name,
                "CaseType": "LinRespSpec",
                "Location": "Bottom",
                "MX": 100.0 if direction == "Y" else 0.0,
                "MY": 100.0 if direction == "X" else 0.0,
            }
        else:
            row = {
                "OutputCase": case_name,
                "CaseType": "LinRespSpec",
                "MX": 100.0 if direction == "Y" else 0.0,
                "MY": 100.0 if direction == "X" else 0.0,
                "X": 0.0,
                "Y": 0.0,
                "Z": -5.15,
            }
        return _exact_capture(table_key, case_name, row)

    monkeypatch.setattr(ev, "capture_exact_output_case_table", fake_capture)
    bundle = ev.capture_live_mdev_mo_evidence(
        database_tables=object(),
        model_fingerprint="etabs:model-identity:sha256:directional",
        direction=direction,
        base_context=_base_context(),
        wall_population=ev.ReviewedDirectionalWallPopulation(
            direction=direction,
            pier_refs=("P1",),
            review_refs=(f"review:walls:{direction}",),
            provenance_refs=(f"project:walls:{direction}",),
        ),
        result_context=_result_context(),
        case_names=cases,
        include_pier_labels=False,
    )

    assert len(bundle.directions) == 1
    assert bundle.directions[0].direction == direction
    assert {item.case_name for item in bundle.directions[0].cases} == set(cases)
    assert {case_name for _table, case_name in calls} == set(cases)
    assert len(calls) == 6
    assert all(forbidden_fragment not in case_name for _table, case_name in calls)


def test_directional_capture_rejects_wall_population_from_other_direction(monkeypatch):
    monkeypatch.setattr(ev, "capture_static_table", lambda *_a, **_k: _static_sections())
    with pytest.raises(ValueError, match="wall population direction mismatch"):
        ev.capture_live_mdev_mo_evidence(
            database_tables=object(),
            model_fingerprint="etabs:model-identity:sha256:directional",
            direction="X",
            base_context=_base_context(),
            wall_population=ev.ReviewedDirectionalWallPopulation(
                direction="Y",
                pier_refs=("P1",),
                review_refs=("review:walls:Y",),
                provenance_refs=("project:walls:Y",),
            ),
            result_context=_result_context(),
            case_names=("~Static+EccRSX", "~Static-EccRSX"),
            include_pier_labels=False,
        )
