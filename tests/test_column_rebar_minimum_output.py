from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tbdy_engine.adapters.check_adapter import CheckAdapter
from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.design.columns.module import (
    ColumnDesignModule,
    ColumnGeometry,
    ColumnRebar,
)


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


def _column() -> ColumnGeometry:
    return ColumnGeometry(
        label="C1",
        story="S1",
        section_name="C30x30",
        width_m=0.30,
        depth_m=0.30,
        clear_height_m=3.0,
    )


def _rebar(
    *,
    As_total_mm2: float = 1200.0,
    rho: float = 1.3333333333,
    n_bars_total: int = 6,
    bar_diameter_mm: float = 16.0,
    source: str = "real_rebar",
) -> ColumnRebar:
    rebar = ColumnRebar(
        label="C1",
        n_bars_total=n_bars_total,
        bar_diameter_mm=bar_diameter_mm,
        As_total_mm2=As_total_mm2,
        rho=rho,
    )
    setattr(rebar, "source", source)
    return rebar


def test_contract_marks_column_rebar_minimum_as_implemented_and_enabled():
    catalog = _catalog()
    check = catalog.checks["column_rebar_minimum"]

    assert check.id == "column_rebar_minimum"
    assert check.evaluation == "COLUMN_DESIGN"
    assert check.evaluation_field == "rebar_minimum"
    assert check.implementation_status == "IMPLEMENTED"
    assert check.runner_enabled is True
    assert check.experimental is False


def test_column_module_emits_rebar_minimum_check_with_existing_column_checks():
    output = _column_output()
    checks = output["checks"]

    assert "rebar_minimum" in checks
    assert "column_rebar_minimum" not in checks

    assert set(checks) >= {
        "geometry",
        "axial",
        "rebar_minimum",
        "pmm",
        "shear",
        "confinement",
        "capacity_hierarchy",
    }

    payload = checks["rebar_minimum"]
    for field in ["status", "ratio", "value", "limit", "unit", "message", "tbdy_ref"]:
        assert field in payload

    assert payload["status"] in {"OK", "WARNING", "FAIL", "NO_DATA"}
    assert payload["unit"] == "%"
    assert payload["limit"] == 1.0


def test_rebar_minimum_ok_for_adequate_real_rebar():
    module = ColumnDesignModule(FakeContext())
    check = module.check_rebar_minimum(_column(), _rebar(source="real_rebar"))

    assert check.check_name == "rebar_minimum"
    assert check.status == "OK"
    assert check.ratio <= 1.0
    assert check.value == _rebar().rho
    assert check.limit == 1.0
    assert check.unit == "%"
    assert "source=real_rebar" in check.message


def test_rebar_minimum_warning_for_default_auto_proposal_when_minimums_pass():
    module = ColumnDesignModule(FakeContext())
    check = module.check_rebar_minimum(_column(), _rebar(source="default"))

    assert check.status == "WARNING"
    assert check.ratio <= 1.0
    assert "source=default" in check.message
    assert "default/auto proposal" in check.message


def test_rebar_minimum_fail_for_inadequate_provided_rebar():
    module = ColumnDesignModule(FakeContext())
    check = module.check_rebar_minimum(
        _column(),
        _rebar(
            As_total_mm2=500.0,
            rho=0.55,
            n_bars_total=4,
            bar_diameter_mm=12.0,
            source="real_rebar",
        ),
    )

    assert check.status == "FAIL"
    assert check.ratio > 1.0
    assert check.value == 0.55
    assert check.limit == 1.0
    assert "As=" in check.message
    assert "rho=" in check.message
    assert "n_bars=4" in check.message
    assert "dia=12mm" in check.message


def test_rebar_minimum_no_data_for_missing_rebar():
    module = ColumnDesignModule(FakeContext())
    check = module.check_rebar_minimum(_column(), None)

    assert check.status in {"NO_DATA", "WARNING"}
    assert check.check_name == "rebar_minimum"

    if check.status == "NO_DATA":
        assert "rebar" in check.message.lower()
    else:
        assert "source=default" in check.message


def test_serialized_rebar_minimum_output_includes_evidence_and_existing_column_evidence():
    output = _column_output()
    checks = output["checks"]

    assert "rebar_minimum" in checks

    rebar_min = checks["rebar_minimum"]
    evidence = rebar_min["evidence"]

    assert evidence["As_total_mm2"] is not None
    assert evidence["As_min_mm2"] == 0.01 * 90000.0
    assert evidence["rho_pct"] is not None
    assert evidence["rho_min_pct"] == 1.0
    assert evidence["n_bars_total"] is not None
    assert evidence["n_bars_min"] == 6
    assert evidence["bar_diameter_mm"] is not None
    assert evidence["bar_diameter_min_mm"] == 14.0
    assert evidence["source"] in {"default", "real_rebar", "section_rebar_defs", "etabs_design_summary", "unknown"}

    assert checks["axial"]["evidence"]["force"] == "N_kn"
    assert checks["axial"]["evidence"]["component_case"] == "S_E_1"
    assert checks["pmm"]["evidence"]["source"] == "column_pmm"
    assert checks["shear"]["evidence"]["force"] == "max(abs(Vx_kn), abs(Vy_kn))"
    assert checks["shear"]["evidence"]["Vx_case"] == "K_E_1"
    assert checks["shear"]["evidence"]["Vy_case"] == "K_E_2"


def test_check_adapter_emits_enabled_column_rebar_minimum_from_contract_first_catalog():
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

    assert "column_rebar_minimum" in by_id
    assert by_id["column_rebar_minimum"].status == output["checks"]["rebar_minimum"]["status"]
    assert by_id["column_rebar_minimum"].status != "MISSING_OUTPUT"

    assert {
        "column_geometry",
        "column_axial",
        "column_pmm",
        "column_shear",
        "column_confinement",
        "column_rebar_minimum",
    } <= set(by_id)


def test_missing_real_rebar_data_still_produces_explicit_existing_and_rebar_minimum_statuses():
    output = _column_output()
    checks = output["checks"]

    assert checks["pmm"]["status"] in {"OK", "WARNING", "FAIL", "NO_DATA"}
    assert checks["confinement"]["status"] in {"OK", "WARNING", "FAIL", "NO_DATA"}
    assert checks["rebar_minimum"]["status"] in {"OK", "WARNING", "FAIL", "NO_DATA"}

    assert checks["pmm"]["message"]
    assert checks["confinement"]["message"]
    assert checks["rebar_minimum"]["message"]