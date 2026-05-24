from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from tbdy_engine.design.columns.module import (
    ColumnDesignModule,
    ColumnGeometry,
)


@dataclass
class FakeContext:
    design_metadata: dict[str, Any] = field(default_factory=dict)
    envelopes: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    topology: dict[str, Any] = field(default_factory=dict)
    geometry: dict[str, Any] = field(default_factory=dict)
    story_height_map: dict[str, float] = field(default_factory=dict)
    design_basis: dict[str, Any] = field(default_factory=dict)


def _column(label: str = "C1") -> ColumnGeometry:
    return ColumnGeometry(
        label=label,
        story="S1",
        section_name="Column_80x80",
        width_m=0.8,
        depth_m=0.8,
    )

def _module_with_summary(summary: pd.DataFrame) -> ColumnDesignModule:
    return ColumnDesignModule(
        FakeContext(
            design_metadata={
                "column_design_summary": summary,
            }
        )
    )


def test_pmm_explicit_pmmcombo_is_preserved_structurally():
    module = _module_with_summary(
        pd.DataFrame(
            [
                {
                    "Label": "C1",
                    "PMM Ratio": 0.72,
                    "PMMCombo": "PMM_COMBO_1",
                }
            ]
        )
    )

    result = module.check_pmm(_column("C1"))

    assert result.status == "OK"
    assert result.ratio == 0.72
    assert result.governing_combo == "PMM_COMBO_1"


def test_pmm_explicit_outputcase_is_preserved_structurally():
    module = _module_with_summary(
        pd.DataFrame(
            [
                {
                    "Label": "C1",
                    "PMM Ratio": 0.81,
                    "OutputCase": "OUTPUT_CASE_1",
                }
            ]
        )
    )

    result = module.check_pmm(_column("C1"))

    assert result.status == "OK"
    assert result.ratio == 0.81
    assert result.governing_combo == "OUTPUT_CASE_1"


def test_pmm_without_explicit_combo_remains_none():
    module = _module_with_summary(
        pd.DataFrame(
            [
                {
                    "Label": "C1",
                    "PMM Ratio": 0.88,
                }
            ]
        )
    )

    result = module.check_pmm(_column("C1"))

    assert result.status == "OK"
    assert result.ratio == 0.88
    assert result.governing_combo is None


def test_pmm_output_dict_preserves_structured_governing_combo():
    module = _module_with_summary(
        pd.DataFrame(
            [
                {
                    "Label": "C1",
                    "PMM Ratio": 0.76,
                    "PMMCombo": "PMM_COMBO_2",
                }
            ]
        )
    )

    result = module.check_pmm(_column("C1"))

    output = module._output_to_dict(
        type(
            "FakeOutput",
            (),
            {
                "label": "C1",
                "story": "S1",
                "section": "Column_80x80",
                "status": "OK",
                "geometry": None,
                "forces": None,
                "rebar": None,
                "checks": {"pmm": result},
                "governing_check": "pmm",
                "governing_ratio": result.ratio,
            },
        )()
    )

    pmm = output["checks"]["pmm"]

    assert pmm["governing_combo"] == "PMM_COMBO_2"
    assert pmm["combo_family"] is None
    assert pmm["evidence"]["governing_combo"] == "PMM_COMBO_2"


def test_pmm_message_text_is_not_parsed_for_governing_combo():
    module = _module_with_summary(
        pd.DataFrame(
            [
                {
                    "Label": "C1",
                    "PMM Ratio": 0.91,
                    "WarnMsg": "case=FAKE_MESSAGE_COMBO",
                }
            ]
        )
    )

    result = module.check_pmm(_column("C1"))

    assert result.status == "OK"
    assert result.governing_combo is None


def test_column_shear_still_does_not_use_axial_governing_combo():
    module = ColumnDesignModule(FakeContext())

    shear_check = type(
        "FakeCheck",
        (),
        {
            "status": "OK",
            "ratio": 0.62,
            "value": 310.0,
            "limit": 500.0,
            "unit": "kN",
            "message": "shear ok",
            "tbdy_ref": "TBDY",
        },
    )()

    forces = type(
        "FakeForces",
        (),
        {
            "N_kn": 720.0,
            "Mx_knm": 0.0,
            "My_knm": 0.0,
            "Vx_kn": 310.0,
            "Vy_kn": 280.0,
            "governing_combo": "AXIAL_CASE_SHOULD_NOT_APPEAR_IN_SHEAR",
        },
    )()

    output = module._output_to_dict(
        type(
            "FakeOutput",
            (),
            {
                "label": "C1",
                "story": "S1",
                "section": "Column_80x80",
                "status": "OK",
                "geometry": None,
                "forces": forces,
                "rebar": None,
                "checks": {"shear": shear_check},
                "governing_check": "shear",
                "governing_ratio": shear_check.ratio,
            },
        )()
    )

    shear = output["checks"]["shear"]

    assert shear["governing_combo"] is None
    assert shear["combo_family"] is None