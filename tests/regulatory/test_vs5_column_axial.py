from __future__ import annotations

import pytest

from tbdy_engine.checks.column_axial_selection import (
    ColumnDemandAvailability,
    ReviewedColumnNdmLoadBinding,
    Ts498ReductionPolicyState,
)
from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.features.etabs_column_axial_evidence import (
    ColumnForceEvidenceBundle,
    ColumnGeometryEvidence,
    LiveColumnAxialEvidenceBundle,
)
from tbdy_engine.regulatory.authority import validate_registry_authority
from tbdy_engine.regulatory.column_axial_dual_code import (
    TBDY_RULE_ID,
    TS500_RULE_ID,
    VS5_COLUMN_AXIAL_REGISTRY,
)
from tbdy_engine.regulatory.sources.vs5_column_axial import (
    build_vs5_column_axial_authority_catalog,
)
from tbdy_engine.regulatory.vs5_column_axial_program import (
    CombinedColumnAxialStatus,
    ReviewedVs5ColumnAxialContext,
    run_vs5_column_axial,
)


def _force_row(
    output_case: str,
    p: float,
    *,
    case_type: str,
    step_type: str | None,
    uid: str = "236",
) -> dict[str, object]:
    return {
        "Story": "+0.00",
        "Column": "C2",
        "UniqueName": uid,
        "OutputCase": output_case,
        "CaseType": case_type,
        "StepType": step_type,
        "StepNumber": None,
        "Station": "0",
        "Element": uid,
        "ElemStation": "0",
        "P": str(p),
    }


def _combo_rows() -> tuple[dict[str, object], ...]:
    base = {
        "LC_DL": 1.0,
        "LC_SDL": 1.0,
        "LC_WDL": 1.0,
        "LC_LL": 1.0,
        "LC_DDL": 1.0,
        "LC_S": 1.0,
        "RSX": 1.0,
        "RSY": 0.3,
        "EDZ": 0.3,
    }
    y = dict(base)
    y["RSX"] = 0.3
    y["RSY"] = 1.0
    out: list[dict[str, object]] = []
    for name, parts in (("Crack_SeisX", base), ("Crack_SeisY", y)):
        first = True
        for load_name, sf in parts.items():
            out.append(
                {
                    "Name": name,
                    "Type": "Linear Add" if first else None,
                    "IsAuto": "No" if first else None,
                    "LoadName": load_name,
                    "SF": str(sf),
                    "GUID": None,
                    "Notes": None,
                }
            )
            first = False
    for load_name, sf in (
        ("LC_DL", 1.4),
        ("LC_SDL", 1.4),
        ("LC_WDL", 1.4),
        ("LC_LL", 1.6),
        ("LC_DDL", 1.6),
    ):
        out.append(
            {
                "Name": "Grav_Ult",
                "Type": "Linear Add" if load_name == "LC_DL" else None,
                "IsAuto": "No" if load_name == "LC_DL" else None,
                "LoadName": load_name,
                "SF": str(sf),
                "GUID": None,
                "Notes": None,
            }
        )
    return tuple(out)


def _binding() -> ReviewedColumnNdmLoadBinding:
    x = {
        "LC_DL": 1.0,
        "LC_SDL": 1.0,
        "LC_WDL": 1.0,
        "LC_LL": 1.0,
        "LC_DDL": 1.0,
        "LC_S": 1.0,
        "RSX": 1.0,
        "RSY": 0.3,
        "EDZ": 0.3,
    }
    y = dict(x)
    y["RSX"] = 0.3
    y["RSY"] = 1.0
    fixed_x = {
        "LC_DL": 1.0,
        "LC_SDL": 1.0,
        "LC_WDL": 1.0,
        "RSX": 1.0,
        "RSY": 0.3,
        "EDZ": 0.3,
    }
    fixed_y = dict(fixed_x)
    fixed_y["RSX"] = 0.3
    fixed_y["RSY"] = 1.0
    return ReviewedColumnNdmLoadBinding(
        binding_id="reviewed:vs5:ndm-binding:test",
        version="v1",
        final_combination_ids=("Crack_SeisX", "Crack_SeisY"),
        g_case_ids=("LC_DL", "LC_SDL", "LC_WDL"),
        q_case_ids=("LC_LL", "LC_DDL"),
        s_case_ids=("LC_S",),
        horizontal_e_case_ids=("RSX", "RSY"),
        vertical_e_case_ids=("EDZ",),
        baseline_coefficients_by_combination={"Crack_SeisX": x, "Crack_SeisY": y},
        required_fixed_coefficients_by_combination={
            "Crack_SeisX": fixed_x,
            "Crack_SeisY": fixed_y,
        },
        review_refs=("review:test:ndm-binding",),
    )


def _evidence(
    *,
    crack_x_min: float = -4200.0,
    crack_y_min: float = -4300.0,
    gravity_p: float = -5000.0,
) -> LiveColumnAxialEvidenceBundle:
    column = ColumnGeometryEvidence(
        unique_name="236",
        story="+0.00",
        column_label="C2",
        section="Column_80x80",
        material="C35/45",
        width_m=0.8,
        depth_m=0.8,
        fck_mpa=35.0,
        connectivity_row={"Story": "+0.00", "ColumnBay": "C2", "UniqueName": "236"},
        assignment_row={
            "Story": "+0.00",
            "Label": "C2",
            "UniqueName": "236",
            "Shape": "Concrete Rectangular",
            "SectProp": "Column_80x80",
        },
        section_row={
            "Name": "Column_80x80",
            "Material": "C35/45",
            "t2": "0.8",
            "t3": "0.8",
            "DesignType": "Column",
        },
        material_row={"Material": "C35/45", "Fc": "35000"},
    )
    rows = [
        _force_row("Crack_SeisX", -4000.0, case_type="Combination", step_type="Max"),
        _force_row("Crack_SeisX", crack_x_min, case_type="Combination", step_type="Min"),
        _force_row("Crack_SeisY", -4100.0, case_type="Combination", step_type="Max"),
        _force_row("Crack_SeisY", crack_y_min, case_type="Combination", step_type="Min"),
        _force_row("Grav_Ult", gravity_p, case_type="Combination", step_type=None),
        _force_row("LC_DL", -1800.0, case_type="LinStatic", step_type=None),
        _force_row("LC_SDL", -650.0, case_type="LinStatic", step_type=None),
        _force_row("LC_WDL", -230.0, case_type="LinStatic", step_type=None),
        _force_row("LC_LL", -810.0, case_type="LinStatic", step_type=None),
        _force_row("LC_DDL", 0.0, case_type="LinStatic", step_type=None),
        _force_row("LC_S", -100.0, case_type="LinStatic", step_type=None),
        _force_row("EDZ", -950.0, case_type="LinStatic", step_type=None),
    ]
    forces = ColumnForceEvidenceBundle(
        rows=tuple(rows),
        output_names=(
            "Crack_SeisX",
            "Crack_SeisY",
            "Grav_Ult",
            "LC_DL",
            "LC_SDL",
            "LC_WDL",
            "LC_LL",
            "LC_DDL",
            "LC_S",
            "EDZ",
        ),
        force_unit="kN",
        runtime_capture_status=RuntimeCaptureStatus.FULL,
    )
    return LiveColumnAxialEvidenceBundle(
        model_fingerprint="etabs:model-identity:sha256:test",
        evidence_epoch_id="epoch:vs5-column-axial:sha256:test",
        columns=(column,),
        forces=forces,
        load_pattern_rows=(
            {"Name": "LC_DL", "Type": "Dead"},
            {"Name": "LC_SDL", "Type": "Super Dead"},
            {"Name": "LC_WDL", "Type": "Super Dead"},
            {"Name": "LC_LL", "Type": "Live"},
            {"Name": "LC_DDL", "Type": "Live"},
            {"Name": "LC_S", "Type": "Snow"},
        ),
        load_combination_rows=_combo_rows(),
        column_overwrite_rows=({"Story": "+0.00", "Column": "C2", "LLRF": "0"},),
        review_refs=("review:test:factual",),
        provenance_refs=("provenance:test:factual",),
    )


def _reviewed(
    *,
    ts498_state: Ts498ReductionPolicyState = Ts498ReductionPolicyState.NO_REDUCTION,
    high_ductility: bool | None = True,
) -> ReviewedVs5ColumnAxialContext:
    return ReviewedVs5ColumnAxialContext(
        ndm_binding=_binding(),
        tbdy_7312_high_ductility_applies=high_ductility,
        ts498_reduction_state=ts498_state,
        q_target_coefficients={"LC_LL": 1.0, "LC_DDL": 1.0},
        s_target_coefficients={"LC_S": 0.2},
        linear_superposition_reviewed=True,
        compression_sign=-1,
        ndm_regulatory_authority_ids=("authority:TBDY2018:7.3.1.2",),
        ndm_review_refs=("review:test:ndm",),
        ts500_combination_ids=("Grav_Ult", "Crack_SeisX", "Crack_SeisY"),
        ts500_gamma_mc=1.5,
        ts500_review_refs=("review:test:ts500",),
    )


def test_vs5_source_authority_catalog_validates_exactly_both_rules():
    validated = validate_registry_authority(
        VS5_COLUMN_AXIAL_REGISTRY,
        build_vs5_column_axial_authority_catalog(),
    )
    assert {item.rule_id for item in validated} == {TBDY_RULE_ID, TS500_RULE_ID}


def test_vs5_nominal_dual_code_path_passes_both_formal_checks():
    run = run_vs5_column_axial(
        evidence=_evidence(),
        reviewed=_reviewed(),
        unique_name="236",
    )
    assert run.tbdy_demand.availability is ColumnDemandAvailability.RESOLVED
    assert run.ts500_demand.availability is ColumnDemandAvailability.RESOLVED
    # Snow baseline is 1.0 and target is 0.2. P_s=-100 kN therefore
    # each seismic candidate becomes 80 kN less compressive.
    assert run.tbdy_demand.demand_kn == 4220.0
    assert run.ts500_demand.demand_kn == 5000.0
    assert run.tbdy_result is not None
    assert run.ts500_result is not None
    assert run.tbdy_result.status is CheckStatus.OK
    assert run.ts500_result.status is CheckStatus.OK
    assert run.tbdy_result.limit == pytest.approx(8960.0)
    assert run.ts500_result.limit == pytest.approx(13440.0)
    assert run.combined_status is CombinedColumnAxialStatus.PASS


def test_vs5_tbdy_failure_does_not_require_ts500_failure():
    run = run_vs5_column_axial(
        evidence=_evidence(crack_x_min=-10000.0, crack_y_min=-9500.0, gravity_p=-5000.0),
        reviewed=_reviewed(),
        unique_name="236",
    )
    assert run.tbdy_result is not None and run.tbdy_result.status is CheckStatus.FAIL
    assert run.ts500_result is not None and run.ts500_result.status is CheckStatus.OK
    assert run.combined_status is CombinedColumnAxialStatus.FAIL


def test_vs5_ts500_failure_is_independent_of_tbdy_ndm_population():
    run = run_vs5_column_axial(
        evidence=_evidence(gravity_p=-14000.0),
        reviewed=_reviewed(),
        unique_name="236",
    )
    assert run.tbdy_result is not None and run.tbdy_result.status is CheckStatus.OK
    assert run.ts500_result is not None and run.ts500_result.status is CheckStatus.FAIL
    assert run.combined_status is CombinedColumnAxialStatus.FAIL


def test_vs5_unresolved_ts498_policy_blocks_tbdy_without_fake_fail():
    run = run_vs5_column_axial(
        evidence=_evidence(),
        reviewed=_reviewed(ts498_state=Ts498ReductionPolicyState.UNRESOLVED),
        unique_name="236",
    )
    assert run.tbdy_demand.availability is ColumnDemandAvailability.BLOCKED
    assert run.tbdy_result is None
    assert run.ts500_result is not None and run.ts500_result.status is CheckStatus.OK
    assert run.combined_status is CombinedColumnAxialStatus.BLOCKED


def test_vs5_tbdy_high_ductility_nonapplicability_is_not_promoted_to_pass():
    run = run_vs5_column_axial(
        evidence=_evidence(),
        reviewed=_reviewed(high_ductility=False),
        unique_name="236",
    )
    assert run.tbdy_result is None
    assert run.ts500_result is not None and run.ts500_result.status is CheckStatus.OK
    assert run.combined_status is CombinedColumnAxialStatus.INCOMPLETE
