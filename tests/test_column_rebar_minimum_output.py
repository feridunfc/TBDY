from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.design.columns.module import ColumnDesignModule


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class FakeContext:
    design_basis: dict[str, Any] = field(
        default_factory=lambda: {
            "fck_mpa": 30.0,
            "fyk_mpa": 420.0,
            "gamma_c": 1.5,
            "gamma_s": 1.15,
        }
    )
    topology: dict[str, Any] = field(
        default_factory=lambda: {
            "columns": [
                {
                    "label": "C1",
                    "story": "S1",
                    "section": "C30x30",
                }
            ],
            "column_beam_map": {},
        }
    )
    geometry: dict[str, Any] = field(
        default_factory=lambda: {
            "section_dims": {
                "C30x30": {
                    "width_m": 0.30,
                    "depth_m": 0.30,
                }
            },
            "column_sections": {
                "C1": "C30x30",
            },
        }
    )
    story_height_map: dict[str, float] = field(default_factory=lambda: {"S1": 3.0})
    envelopes: dict[str, Any] = field(
        default_factory=lambda: {
            "column_forces_map": {
                "C1": {
                    "P_max": 100.0,
                    "M2_max": 20.0,
                    "M3_max": 30.0,
                    "V2_max": 10.0,
                    "V3_max": 12.0,
                    "P_case": "S_E_1",
                    "M2_case": "S_E_2",
                    "M3_case": "S_E_3",
                    "V2_case": "K_E_1",
                    "V3_case": "K_E_2",
                }
            }
        }
    )
    design_metadata: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def _catalog():
    return EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()


def _column_output() -> dict[str, Any]:
    result = ColumnDesignModule(FakeContext()).run()
    assert result["outputs"]
    return result["outputs"][0]


def test_contract_documents_column_rebar_minimum_as_disabled_missing_output():
    catalog = _catalog()
    check = catalog.checks["column_rebar_minimum"]

    assert check.id == "column_rebar_minimum"
    assert check.evaluation == "COLUMN_DESIGN"
    assert check.evaluation_field == "rebar_minimum"
    assert check.implementation_status == "MISSING_OUTPUT"
    assert check.runner_enabled is False
    assert check.experimental is True


def test_column_module_current_output_omits_rebar_minimum_but_emits_traceable_column_checks():
    output = _column_output()
    checks = output["checks"]

    assert "rebar_minimum" not in checks
    assert "column_rebar_minimum" not in checks
    assert set(checks) >= {
        "geometry",
        "axial",
        "pmm",
        "shear",
        "confinement",
        "capacity_hierarchy",
    }

    for check_name in ["geometry", "axial", "pmm", "shear", "confinement"]:
        payload = checks[check_name]
        for field in ["status", "ratio", "value", "limit", "unit", "message", "tbdy_ref"]:
            assert field in payload
        assert payload["status"] not in {"MISSING_OUTPUT", "ERROR"}


def test_serialized_output_preserves_existing_column_evidence_while_rebar_minimum_is_absent():
    output = _column_output()
    checks = output["checks"]

    assert "rebar_minimum" not in checks
    assert "column_rebar_minimum" not in checks

    assert checks["axial"]["evidence"]["force"] == "N_kn"
    assert checks["axial"]["evidence"]["component_case"] == "S_E_1"
    assert checks["pmm"]["evidence"]["source"] == "column_pmm"
    assert checks["shear"]["evidence"]["force"] == "max(abs(Vx_kn), abs(Vy_kn))"
    assert checks["shear"]["evidence"]["Vx_case"] == "K_E_1"
    assert checks["shear"]["evidence"]["Vy_case"] == "K_E_2"


def test_check_adapter_does_not_emit_disabled_column_rebar_minimum_from_contract_first_catalog():
    output = _column_output()
    eval_results = {
        "results": {
            "COLUMN_DESIGN": {
                "outputs": [output],
            }
        },
        "errors": {},
        "skipped": {},
        "execution_order": ["COLUMN_DESIGN"],
        "cache_stats": {},
    }

    rows = CheckAdapter(_catalog()).adapt_all(eval_results)
    by_id = {row.check_id: row for row in rows}

    assert "column_rebar_minimum" not in by_id
    assert {"column_geometry", "column_axial", "column_pmm", "column_shear", "column_confinement"} <= set(by_id)
    assert all(row.status != "MISSING_OUTPUT" for row in rows)


def test_missing_real_rebar_data_still_produces_explicit_existing_check_statuses_not_silent_absence():
    output = _column_output()
    checks = output["checks"]

    assert checks["pmm"]["status"] in {"OK", "WARNING", "FAIL", "NO_DATA"}
    assert checks["confinement"]["status"] in {"OK", "WARNING", "FAIL", "NO_DATA"}
    assert checks["pmm"]["message"]
    assert checks["confinement"]["message"]

    assert "rebar_minimum" not in checks
    assert "column_rebar_minimum" not in checks
