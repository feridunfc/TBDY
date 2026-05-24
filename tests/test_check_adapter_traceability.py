from __future__ import annotations

from pathlib import Path

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.contracts.loader import EngineContractLoader


ROOT = Path(__file__).resolve().parents[1]
DISABLED_KNOWN_MISSING_OUTPUT_CHECKS = {
    "column_rebar_minimum",
    "column_design_full",
    "beam_design_full",
}


def _catalog():
    return EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()


def _adapter():
    return CheckAdapter(_catalog())


def _by_check_id(rows):
    return {row.check_id: row for row in rows}


def _check_payload(status="OK", ratio=0.5, message="ok"):
    return {
        "status": status,
        "ratio": ratio,
        "value": ratio,
        "limit": 1.0,
        "unit": "ratio",
        "message": message,
        "action": "",
        "evaluation_level": "DESIGN_LEVEL",
        "source": "synthetic_fixture",
    }


def _column_eval_results():
    return {
        "results": {
            "COLUMN_DESIGN": {
                "outputs": [
                    {
                        "label": "C1",
                        "story": "S1",
                        "checks": {
                            "geometry": _check_payload(message="column geometry ok"),
                            "axial": _check_payload(message="column axial ok"),
                            "pmm": _check_payload(message="column pmm ok"),
                            "shear": _check_payload(message="column shear ok"),
                            "confinement": _check_payload(message="column confinement ok"),
                        },
                    }
                ]
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["COLUMN_DESIGN"],
        "cache_stats": {},
    }


def _beam_eval_results():
    return {
        "results": {
            "BEAM_DESIGN": {
                "outputs": [
                    {
                        "label": "B1",
                        "story": "S1",
                        "checks": {
                            "geometry": _check_payload(message="beam geometry ok"),
                            "flexure": _check_payload(message="beam flexure ok"),
                            "shear": _check_payload(message="beam shear ok"),
                            "ductility": _check_payload(message="beam ductility ok"),
                        },
                    }
                ]
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["BEAM_DESIGN"],
        "cache_stats": {},
    }


def test_column_traceable_fields_normalize_from_outputs_checks():
    rows = _by_check_id(_adapter().adapt_all(_column_eval_results()))

    for check_id in [
        "column_geometry",
        "column_axial",
        "column_pmm",
        "column_shear",
        "column_confinement",
    ]:
        row = rows[check_id]
        assert row.status == "OK"
        assert row.evaluation == "COLUMN_DESIGN"
        assert row.element_label == "C1"
        assert row.story == "S1"
        assert row.source == "synthetic_fixture"
        assert row.evaluation_level == "DESIGN_LEVEL"


def test_column_known_missing_output_checks_are_not_emitted_when_disabled():
    rows = _by_check_id(_adapter().adapt_all(_column_eval_results()))

    assert "column_rebar_minimum" not in rows
    assert "column_design_full" not in rows


def test_beam_traceable_fields_normalize_from_outputs_checks():
    rows = _by_check_id(_adapter().adapt_all(_beam_eval_results()))

    for check_id in [
        "beam_geometry",
        "beam_flexure",
        "beam_shear",
        "beam_ductility",
    ]:
        row = rows[check_id]
        assert row.status == "OK"
        assert row.evaluation == "BEAM_DESIGN"
        assert row.element_label == "B1"
        assert row.story == "S1"
        assert row.source == "synthetic_fixture"
        assert row.evaluation_level == "DESIGN_LEVEL"


def test_beam_known_missing_output_check_is_not_emitted_when_disabled():
    rows = _by_check_id(_adapter().adapt_all(_beam_eval_results()))

    assert "beam_design_full" not in rows


def test_known_missing_output_checks_are_not_emitted_by_contract_first_catalog():
    rows = []
    rows.extend(_adapter().adapt_all(_column_eval_results()))
    rows.extend(_adapter().adapt_all(_beam_eval_results()))
    emitted = {row.check_id for row in rows}

    assert not (DISABLED_KNOWN_MISSING_OUTPUT_CHECKS & emitted)


def test_scwb_direct_extraction_normalizes_capacity_hierarchy_checks():
    eval_results = {
        "results": {
            "SCWB_CHECK": {
                "column_capacity_hierarchy": [
                    {
                        **_check_payload(message="column capacity hierarchy ok"),
                        "element_label": "J1",
                        "story": "S1",
                    }
                ],
                "beam_capacity_hierarchy": [
                    {
                        **_check_payload(message="beam capacity hierarchy ok"),
                        "element_label": "J1",
                        "story": "S1",
                    }
                ],
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["SCWB_CHECK"],
        "cache_stats": {},
    }

    rows = _by_check_id(_adapter().adapt_all(eval_results))

    assert rows["column_capacity_hierarchy"].status == "OK"
    assert rows["column_capacity_hierarchy"].evaluation == "SCWB_CHECK"
    assert rows["column_capacity_hierarchy"].element_label == "J1"
    assert rows["beam_capacity_hierarchy"].status == "OK"
    assert rows["beam_capacity_hierarchy"].evaluation == "SCWB_CHECK"
    assert rows["beam_capacity_hierarchy"].element_label == "J1"


def test_evaluation_error_creates_error_row_for_each_enabled_column_check():
    eval_results = {
        "results": {},
        "errors": {"COLUMN_DESIGN": "boom"},
        "skipped": {},
        "execution_order": ["COLUMN_DESIGN"],
        "cache_stats": {},
    }

    rows = [row for row in _adapter().adapt_all(eval_results) if row.evaluation == "COLUMN_DESIGN"]

    assert {row.check_id for row in rows} == {
        "column_geometry",
        "column_axial",
        "column_pmm",
        "column_shear",
        "column_confinement",
    }
    assert all(row.status == "ERROR" for row in rows)
    assert all(row.evaluation_level == "ERROR" for row in rows)
    assert all(row.message == "boom" for row in rows)


def test_disabled_wall_checks_are_not_normalized_even_when_wall_output_exists():
    eval_results = {
        "results": {
            "WALL_DESIGN": {
                "outputs": [
                    {
                        "label": "W1",
                        "story": "S1",
                        "checks": {
                            "geometry": _check_payload(message="wall geometry ok"),
                            "axial_flexure": _check_payload(message="wall axial flexure ok"),
                            "shear": _check_payload(message="wall shear ok"),
                            "boundary_zone": _check_payload(message="wall boundary zone ok"),
                            "web_reinforcement": _check_payload(message="wall web reinforcement ok"),
                            "full": _check_payload(message="wall full ok"),
                        },
                    }
                ]
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["WALL_DESIGN"],
        "cache_stats": {},
    }

    rows = _adapter().adapt_all(eval_results)

    assert all(not row.check_id.startswith("wall_") for row in rows)
    assert rows == []


def test_enabled_implemented_column_and_beam_fixture_rows_do_not_normalize_as_no_data():
    column_rows = _adapter().adapt_all(_column_eval_results())
    beam_rows = _adapter().adapt_all(_beam_eval_results())
    implemented_rows = [
        row
        for row in [*column_rows, *beam_rows]
        if row.check_id not in DISABLED_KNOWN_MISSING_OUTPUT_CHECKS
    ]

    assert implemented_rows
    assert all(row.status != "NO_DATA" for row in implemented_rows)
