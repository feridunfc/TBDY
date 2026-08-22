from __future__ import annotations

from pathlib import Path

import pytest

import tbdy_engine.product.live_rc_component_f0_product as live_rc_product
from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.population_audit import (
    IN_SCOPE_CONCRETE_RECTANGULAR_BEAM,
    IN_SCOPE_CONCRETE_RECTANGULAR_COLUMN,
    PopulationAudit,
    PopulationAuditRow,
    PopulationDisposition,
)
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.used_rc_material_population import (
    ConcreteStrengthFactStatus,
    MaterialPopulationReadiness,
    UsedMaterialDefinition,
    UsedRcMaterialPopulation,
    canonical_material_population_json,
)
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.integration.live_beam_geometry_f0 import build_live_capture_epoch
from tbdy_engine.integration.live_rc_component_f0 import (
    LOCKED_RECTANGULAR_PROPERTY_TABLE,
    MATERIAL_SOURCE_FINGERPRINT_PREFIX,
    WALL_NOT_EVALUATED_REASON,
    VS2_RC_REGISTRY,
    build_material_live_capture_epoch,
    component_targets,
    material_authorities,
    run_live_rc_component_f0_pack,
)
from tbdy_engine.product.live_rc_component_f0_product import (
    PRODUCT_CONTRACT,
    build_live_rc_component_f0_product,
)
from tbdy_engine.regulatory.b1_geometry_parity import (
    BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
    BEAM_MIN_DEPTH_RULE_ID,
    COLUMN_MIN_DIMENSION_RULE_ID,
)
from tbdy_engine.regulatory.beam_min_width import RULE_ID as BEAM_MIN_WIDTH_RULE_ID
from tbdy_engine.regulatory.concrete_material_min_strength import RULE_ID as MATERIAL_RULE_ID
from tbdy_engine.regulatory.contracts import ApplicabilityState, ClosureExecutionStatus
from tbdy_engine.regulatory.kernel import StructuralAssessmentStatus

MODEL_PATH = r"C:\Projects\TBDY\Kres.edb"


def _evidence(value: float, *, source_table: str = LOCKED_RECTANGULAR_PROPERTY_TABLE) -> FeatureEvidence:
    return FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table=source_table,
        actual_table_name=source_table,
        source_column="Width" if value < 500 else "Depth",
        source_row={"Name": "R1", "source_contract": source_table},
        raw_value=value,
        normalized_value=value,
        unit="mm",
        resolver="c13_5_p6_1_design_type_alias_probe",
    )


def _feature(name: str, value: float | None, *, source_table: str = LOCKED_RECTANGULAR_PROPERTY_TABLE) -> FeatureValue:
    if value is None:
        return FeatureValue(
            feature_name=name,
            value=None,
            unit="mm",
            semantic_role="GEOMETRY",
            status=FeatureValueStatus.MISSING,
            evidence=(),
        )
    return FeatureValue(
        feature_name=name,
        value=value,
        unit="mm",
        semantic_role="GEOMETRY",
        status=FeatureValueStatus.RESOLVED,
        evidence=(_evidence(value, source_table=source_table),),
    )


def _beam(width: float | None = 249.0, depth: float | None = 600.0, *, component_id: str = "B1") -> FeatureSnapshot:
    return FeatureSnapshot(
        component_type="beam",
        component_id=component_id,
        identity={"story": "S1", "section": "B249x600"},
        features={
            "beam_width_mm": _feature("beam_width_mm", width),
            "beam_depth_mm": _feature("beam_depth_mm", depth),
        },
    )


def _column(
    width: float | None = 299.0,
    depth: float | None = 400.0,
    *,
    component_id: str = "C1",
    source_table: str = LOCKED_RECTANGULAR_PROPERTY_TABLE,
) -> FeatureSnapshot:
    return FeatureSnapshot(
        component_type="column",
        component_id=component_id,
        identity={"story": "S1", "section": "C299x400"},
        features={
            "column_width_mm": _feature("column_width_mm", width, source_table=source_table),
            "column_depth_mm": _feature("column_depth_mm", depth, source_table=source_table),
        },
    )


def _population(
    model_fingerprint: str,
    *,
    fck: float | None = 24.0,
    readiness: MaterialPopulationReadiness = MaterialPopulationReadiness.COMPLETE,
    material_id: str = "MAT-1",
) -> UsedRcMaterialPopulation:
    material = UsedMaterialDefinition(
        material_id=material_id,
        model_fingerprint=model_fingerprint,
        material_name="Concrete factual name",
        material_type_code=2,
        is_concrete=True,
        raw_fc=fck,
        canonical_fck_mpa=fck,
        concrete_strength_status=(
            ConcreteStrengthFactStatus.RESOLVED
            if fck is not None
            else ConcreteStrengthFactStatus.UNRESOLVED
        ),
        unit_context=None,
        usage_references=(),
        diagnostics=(),
    )
    return UsedRcMaterialPopulation(
        model_fingerprint=model_fingerprint,
        usages=(),
        used_material_definitions=(material,),
        reconciliations=(),
        readiness=readiness,
        diagnostics=(),
    )


def _epochs(population: UsedRcMaterialPopulation, *, geometry_bytes: bytes = b"geometry"):
    geometry_epoch = build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=geometry_bytes)
    material_bytes = canonical_material_population_json(population).encode("utf-8")
    material_epoch = build_material_live_capture_epoch(
        model_fingerprint=geometry_epoch.model_fingerprint,
        source_bytes=material_bytes,
    )
    return geometry_epoch, material_epoch


def _run(
    *,
    beam: FeatureSnapshot | None = None,
    column: FeatureSnapshot | None = None,
    fck: float | None = 24.0,
    readiness: MaterialPopulationReadiness = MaterialPopulationReadiness.COMPLETE,
    tbdy_7411_applies: bool | None = True,
):
    geometry_epoch = build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=b"geometry")
    population = _population(
        geometry_epoch.model_fingerprint,
        fck=fck,
        readiness=readiness,
    )
    material_epoch = build_material_live_capture_epoch(
        model_fingerprint=geometry_epoch.model_fingerprint,
        source_bytes=canonical_material_population_json(population).encode("utf-8"),
    )
    snapshots = tuple(item for item in (beam or _beam(), column or _column()) if item is not None)
    return run_live_rc_component_f0_pack(
        geometry_epoch=geometry_epoch,
        snapshots=snapshots,
        material_epoch=material_epoch,
        material_population=population,
        tbdy_7411_applies=tbdy_7411_applies,
    )


def _results(run):
    return {
        (item.instance_id.rule_id.value, item.instance_id.scope_ref): item.result
        for item in run.store.formal_results
    }


def _closures(run):
    return {
        (item.compiled_record_ref.rule_id.value, item.compiled_record_ref.scope_ref): item
        for item in run.assessment.closure_outcomes
    }


def test_registry_contains_exactly_five_existing_formal_rules() -> None:
    assert VS2_RC_REGISTRY.rule_count == 5
    assert {item.rule_id for item in VS2_RC_REGISTRY.checks} == {
        BEAM_MIN_WIDTH_RULE_ID,
        BEAM_MIN_DEPTH_RULE_ID,
        BEAM_DEPTH_WIDTH_RATIO_RULE_ID,
        COLUMN_MIN_DIMENSION_RULE_ID,
        MATERIAL_RULE_ID,
    }


def test_material_epoch_has_distinct_exact_source_fingerprint_prefix() -> None:
    geometry_epoch = build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=b"g")
    first = build_material_live_capture_epoch(
        model_fingerprint=geometry_epoch.model_fingerprint,
        source_bytes=b"material",
    )
    second = build_material_live_capture_epoch(
        model_fingerprint=geometry_epoch.model_fingerprint,
        source_bytes=b"material",
    )
    changed = build_material_live_capture_epoch(
        model_fingerprint=geometry_epoch.model_fingerprint,
        source_bytes=b"material-2",
    )
    assert first.source_fingerprint.startswith(MATERIAL_SOURCE_FINGERPRINT_PREFIX)
    assert first == second
    assert changed.epoch_id != first.epoch_id
    assert first.model_fingerprint == geometry_epoch.model_fingerprint


def test_column_rectangular_applicability_is_proven_only_by_locked_source() -> None:
    proven = component_targets(_column(), tbdy_7411_applies=True)[0]
    unknown = component_targets(
        _column(source_table="Some Other Factual Geometry Table"),
        tbdy_7411_applies=True,
    )[0]
    assert proven.applicability_input.is_rectangular_section is True
    assert unknown.applicability_input.is_rectangular_section is None
    assert "rectangular" not in str(_column().identity).casefold()


def test_scenario_a_mixed_fail_product(tmp_path: Path) -> None:
    geometry_epoch = build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=b"scenario-a")
    population = _population(geometry_epoch.model_fingerprint, fck=24.0)
    material_epoch = build_material_live_capture_epoch(
        model_fingerprint=geometry_epoch.model_fingerprint,
        source_bytes=canonical_material_population_json(population).encode("utf-8"),
    )
    result = build_live_rc_component_f0_product(
        geometry_epoch=geometry_epoch,
        snapshots=(_beam(249.0, 600.0), _column(299.0, 400.0)),
        material_epoch=material_epoch,
        material_population=population,
        tbdy_7411_applies=True,
        geometry_truncation_applied=False,
        output_path=tmp_path / "product.json",
    )
    product = result.payload
    assert product["contract"] == PRODUCT_CONTRACT
    assert product["population"] == {
        "beam_count": 1,
        "column_count": 1,
        "used_concrete_material_count": 1,
        "geometry_truncation_applied": False,
    }
    assert product["rule_instance_count"] == 5
    assert product["check_result_count"] == 5
    statuses = sorted(
        item["check_result"]["status"]
        for item in product["results"]
        if item["check_result"] is not None
    )
    assert statuses.count(CheckStatus.FAIL.value) == 3
    assert statuses.count(CheckStatus.OK.value) == 2
    assert product["finding_count"] == 3
    assert product["domains"]["wall_geometry"] == {
        "support_status": "NOT_EVALUATED",
        "reason": WALL_NOT_EVALUATED_REASON,
        "rule_instance_count": 0,
        "check_result_count": 0,
        "finding_count": 0,
    }
    assert product["full_tbdy_compliance_status"] == "NOT_EVALUATED"


def test_scenario_b_all_supported_checks_ok_but_full_tbdy_not_evaluated(tmp_path: Path) -> None:
    geometry_epoch = build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=b"scenario-b")
    population = _population(geometry_epoch.model_fingerprint, fck=25.0)
    material_epoch = build_material_live_capture_epoch(
        model_fingerprint=geometry_epoch.model_fingerprint,
        source_bytes=canonical_material_population_json(population).encode("utf-8"),
    )
    result = build_live_rc_component_f0_product(
        geometry_epoch=geometry_epoch,
        snapshots=(_beam(250.0, 600.0), _column(300.0, 400.0)),
        material_epoch=material_epoch,
        material_population=population,
        tbdy_7411_applies=True,
        geometry_truncation_applied=False,
        output_path=tmp_path / "product.json",
    )
    assert result.payload["check_result_count"] == 5
    assert all(
        item["check_result"]["status"] == CheckStatus.OK.value
        for item in result.payload["results"]
        if item["check_result"] is not None
    )
    assert result.payload["finding_count"] == 0
    assert result.payload["full_tbdy_compliance_status"] == "NOT_EVALUATED"


def test_scenario_c_column_width_damage_is_scoped_and_does_not_shutdown_other_domains() -> None:
    run = _run(column=_column(width=None, depth=400.0), fck=25.0)
    results = _results(run)
    closures = _closures(run)
    assert results[(BEAM_MIN_WIDTH_RULE_ID.value, "B1")].status in {CheckStatus.FAIL, CheckStatus.OK}
    assert results[(BEAM_MIN_DEPTH_RULE_ID.value, "B1")].status is CheckStatus.OK
    assert results[(BEAM_DEPTH_WIDTH_RATIO_RULE_ID.value, "B1")].status is CheckStatus.OK
    assert (COLUMN_MIN_DIMENSION_RULE_ID.value, "C1") not in results
    assert closures[(COLUMN_MIN_DIMENSION_RULE_ID.value, "C1")].execution_status is ClosureExecutionStatus.NO_DATA
    assert results[(MATERIAL_RULE_ID.value, "MAT-1")].status is CheckStatus.OK
    assert run.assessment.structural_status is StructuralAssessmentStatus.INCOMPLETE


def test_scenario_d_unknown_beam_regulatory_applicability_blocks_only_beams() -> None:
    run = _run(tbdy_7411_applies=None, fck=25.0, column=_column(300.0, 400.0))
    results = _results(run)
    closures = _closures(run)
    beam_rules = {
        BEAM_MIN_WIDTH_RULE_ID.value,
        BEAM_MIN_DEPTH_RULE_ID.value,
        BEAM_DEPTH_WIDTH_RATIO_RULE_ID.value,
    }
    assert all((rule, "B1") not in results for rule in beam_rules)
    assert all(
        closures[(rule, "B1")].execution_status is ClosureExecutionStatus.BLOCKED
        for rule in beam_rules
    )
    assert results[(COLUMN_MIN_DIMENSION_RULE_ID.value, "C1")].status is CheckStatus.OK
    assert results[(MATERIAL_RULE_ID.value, "MAT-1")].status is CheckStatus.OK


def test_scenario_e_unproven_rectangular_column_blocks_only_column() -> None:
    run = _run(
        column=_column(300.0, 400.0, source_table="Other factual table"),
        fck=25.0,
    )
    results = _results(run)
    closures = _closures(run)
    assert (COLUMN_MIN_DIMENSION_RULE_ID.value, "C1") not in results
    assert closures[(COLUMN_MIN_DIMENSION_RULE_ID.value, "C1")].execution_status is ClosureExecutionStatus.BLOCKED
    compiled = next(
        item
        for item in run.program.plan.compiled_closure_inventory
        if item.rule_id == COLUMN_MIN_DIMENSION_RULE_ID
    )
    assert compiled.applicability is ApplicabilityState.UNRESOLVED
    assert results[(MATERIAL_RULE_ID.value, "MAT-1")].status is CheckStatus.OK


def test_scenario_f_incomplete_material_population_blocks_domain_without_fake_material_result(tmp_path: Path) -> None:
    geometry_epoch = build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=b"scenario-f")
    population = _population(
        geometry_epoch.model_fingerprint,
        fck=None,
        readiness=MaterialPopulationReadiness.PARTIAL,
    )
    material_epoch = build_material_live_capture_epoch(
        model_fingerprint=geometry_epoch.model_fingerprint,
        source_bytes=canonical_material_population_json(population).encode("utf-8"),
    )
    result = build_live_rc_component_f0_product(
        geometry_epoch=geometry_epoch,
        snapshots=(_beam(250.0, 600.0), _column(300.0, 400.0)),
        material_epoch=material_epoch,
        material_population=population,
        tbdy_7411_applies=True,
        geometry_truncation_applied=False,
        output_path=tmp_path / "product.json",
    )
    product = result.payload
    assert product["domains"]["concrete_material"]["support_status"] == "BLOCKED"
    assert product["domains"]["concrete_material"]["rule_instance_count"] == 0
    assert product["domains"]["concrete_material"]["check_result_count"] == 0
    assert product["population"]["used_concrete_material_count"] == 1
    assert product["structural_assessment_status"] == StructuralAssessmentStatus.INCOMPLETE.value
    assert product["full_tbdy_compliance_status"] == "NOT_EVALUATED"


def test_scenario_g_deterministic_order_epochs_authorities_plan_results_findings_and_bytes(tmp_path: Path) -> None:
    geometry_bytes = b"canonical-full-geometry-capture"
    geometry_epoch = build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=geometry_bytes)
    population = _population(geometry_epoch.model_fingerprint, fck=24.0)
    material_bytes = canonical_material_population_json(population).encode("utf-8")
    material_epoch = build_material_live_capture_epoch(
        model_fingerprint=geometry_epoch.model_fingerprint,
        source_bytes=material_bytes,
    )
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = build_live_rc_component_f0_product(
        geometry_epoch=geometry_epoch,
        snapshots=(_beam(), _column()),
        material_epoch=material_epoch,
        material_population=population,
        tbdy_7411_applies=True,
        geometry_truncation_applied=False,
        output_path=first_path,
    )
    second = build_live_rc_component_f0_product(
        geometry_epoch=geometry_epoch,
        snapshots=(_column(), _beam()),
        material_epoch=material_epoch,
        material_population=population,
        tbdy_7411_applies=True,
        geometry_truncation_applied=False,
        output_path=second_path,
    )
    assert first.payload["capture_epochs"] == second.payload["capture_epochs"]
    assert first.payload["registry_version"] == second.payload["registry_version"]
    assert first.payload["plan_identity"] == second.payload["plan_identity"]
    assert first.payload["results"] == second.payload["results"]
    assert [item["finding_id"] for item in first.payload["findings"]] == [
        item["finding_id"] for item in second.payload["findings"]
    ]
    assert first_path.read_bytes() == second_path.read_bytes()


def test_production_full_geometry_capture_is_order_independent_at_raw_provider_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = (
        {
            "actual_table_name": LOCKED_RECTANGULAR_PROPERTY_TABLE,
            "component_id": "B1",
            "component_type": "beam",
            "depth_mm": 600.0,
            "depth_mm_source_column": "t3",
            "depth_mm_unit": "mm",
            "label": "B1",
            "section": "B250x600",
            "source_table": LOCKED_RECTANGULAR_PROPERTY_TABLE,
            "story": "S1",
            "unique_name": "B1",
            "unit": "mm",
            "width_mm": 250.0,
            "width_mm_source_column": "t2",
            "width_mm_unit": "mm",
        },
        {
            "actual_table_name": LOCKED_RECTANGULAR_PROPERTY_TABLE,
            "component_id": "C1",
            "component_type": "column",
            "depth_mm": 400.0,
            "depth_mm_source_column": "t3",
            "depth_mm_unit": "mm",
            "label": "C1",
            "section": "C300x400",
            "source_table": LOCKED_RECTANGULAR_PROPERTY_TABLE,
            "story": "S1",
            "unique_name": "C1",
            "unit": "mm",
            "width_mm": 300.0,
            "width_mm_source_column": "t2",
            "width_mm_unit": "mm",
        },
    )
    audit = PopulationAudit(
        (
            PopulationAuditRow(
                component_id="B1",
                label="B1",
                story="S1",
                raw_component_type="beam",
                assigned_section="B250x600",
                analysis_section="B250x600",
                design_section="B250x600",
                section_shape="Concrete Rectangular",
                disposition=PopulationDisposition.IN_SCOPE,
                reason_code=IN_SCOPE_CONCRETE_RECTANGULAR_BEAM,
                source_table="Frame Assignments - Summary",
            ),
            PopulationAuditRow(
                component_id="C1",
                label="C1",
                story="S1",
                raw_component_type="column",
                assigned_section="C300x400",
                analysis_section="C300x400",
                design_section="C300x400",
                section_shape="Concrete Rectangular",
                disposition=PopulationDisposition.IN_SCOPE,
                reason_code=IN_SCOPE_CONCRETE_RECTANGULAR_COLUMN,
                source_table="Frame Assignments - Summary",
            ),
        )
    )

    class OrderedProvider:
        def __init__(self, provider_rows):
            self.provider_rows = tuple(dict(row) for row in provider_rows)

        def live_geometry_probe_data(self):
            return (
                self.provider_rows,
                (),
                {"resolved_geometry_row_count": len(self.provider_rows)},
                audit,
            )

    provider_orders = (rows, tuple(reversed(rows)))
    assert [row["component_id"] for row in provider_orders[0]] == ["B1", "C1"]
    assert [row["component_id"] for row in provider_orders[1]] == ["C1", "B1"]

    captures = []
    for index, provider_rows in enumerate(provider_orders):
        provider = OrderedProvider(provider_rows)
        monkeypatch.setattr(
            live_rc_product,
            "create_live_etabs_geometry_provider",
            lambda *, attach_result, _provider=provider: _provider,
        )
        probe, summary = live_rc_product._capture_full_geometry(
            attach_result=object(),
            output_dir=tmp_path / f"capture-{index}",
        )
        artifact_bytes = probe.feature_snapshot_path.read_bytes()
        epoch = build_live_capture_epoch(
            model_path=MODEL_PATH,
            source_bytes=artifact_bytes,
        )
        assert summary["truncation_applied"] is False
        assert summary["candidate_row_count"] == 2
        assert summary["selected_row_count"] == 2
        captures.append(
            (
                artifact_bytes,
                epoch.source_fingerprint,
                epoch.epoch_id,
            )
        )

    assert captures[0][0] == captures[1][0]
    assert captures[0][1] == captures[1][1]
    assert captures[0][2] == captures[1][2]


def test_material_authority_ids_are_bound_to_epoch_material_dependency_and_fact() -> None:
    geometry_epoch = build_live_capture_epoch(model_path=MODEL_PATH, source_bytes=b"g")
    population = _population(geometry_epoch.model_fingerprint, fck=25.0)
    material_epoch = build_material_live_capture_epoch(
        model_fingerprint=geometry_epoch.model_fingerprint,
        source_bytes=canonical_material_population_json(population).encode("utf-8"),
    )
    first = material_authorities(
        epoch=material_epoch,
        population=population,
        material=population.used_concrete_material_definitions[0],
    )
    second = material_authorities(
        epoch=material_epoch,
        population=population,
        material=population.used_concrete_material_definitions[0],
    )
    assert [item.authority_id for item in first] == [item.authority_id for item in second]
    assert len({item.authority_id for item in first}) == 2
    assert all(material_epoch.epoch_id in item.provenance_refs[0] for item in first)


def test_production_files_exclude_legacy_and_direct_verdict_authority() -> None:
    root = Path(__file__).resolve().parents[2]
    paths = (
        root / "tbdy_engine/integration/live_rc_component_f0.py",
        root / "tbdy_engine/product/live_rc_component_f0_product.py",
        root / "tools/run_live_rc_component_f0_product.py",
    )
    forbidden = (
        "MinimalCheckEngine",
        "EngineContractLoader",
        "geometry_vertical_slice",
        "geometry_product_smoke",
        "product_reports",
        "import yaml",
        "evaluate_member_rule",
        "evaluate_concrete_material_min_strength",
        "CheckResult(",
        "Finding(",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"forbidden production authority {token!r} in {path}"
