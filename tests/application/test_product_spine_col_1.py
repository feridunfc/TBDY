"""PRODUCT-SPINE-COL-1 A1-P1 application composition and boundary proofs."""
from __future__ import annotations

import ast
from dataclasses import fields, replace
import importlib.util
import inspect
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_execution as column_subject
import tbdy_engine.application.project_execution as project_subject
from tbdy_engine.application.column_execution import (
    BLOCKER_LIVE_DESIGN_LINEAGE,
    BLOCKER_LIVE_FND2_INPUT_LINEAGE,
    STATUS_APPLICATION_BLOCKED,
    STATUS_FACTUAL_ACQUISITION_BLOCKED,
    STATUS_REANALYSIS_REQUIRED,
    STATUS_SELECTED,
)
from tbdy_engine.application.contracts import ColumnExecutionRequest, ProjectExecutionRequest
from tbdy_engine.application.project_execution import execute_project
from tbdy_engine.design.columns.column_longitudinal_selection import ENGINE_SELECTED_REBAR_AUTHORITY
from tbdy_engine.product_reports.unified_building_report import ReportSourceKind


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load fixture module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FND1 = _load("_a1p1_fnd1_fixture", "tests/regulatory/test_fnd_col_1_longitudinal_authority.py")
FND2 = _load("_a1p1_fnd2_fixture", "tests/regulatory/test_fnd_col_2x_typed_execution_artifact.py")
P8AB = _load("_a1p1_p8ab_fixture", "tests/design/columns/test_p8a_b_column_longitudinal_production_composition.py")
ACQ = _load("_a1p1_acq_fixture", "tests/integration/test_acq_ctx_1_trusted_live_etabs_acquisition_context.py")
FIX = P8AB.FIX
COMP, SECTION, MODEL, EPOCH = FIX.COMP, FIX.SECTION, FIX.MODEL, FIX.EPOCH
FND2.COMP = COMP


def _request() -> ProjectExecutionRequest:
    return ProjectExecutionRequest(
        project_id="PROJECT:A1P1:1",
        report_id="REPORT:A1P1:1",
        title="PRODUCT-SPINE-COL-1 A1-P1",
        column=ColumnExecutionRequest(component_id=COMP),
    )


def _ready_values():
    values = P8AB._composition_fixture()
    layout = FND1._layout_inputs(16.0, 20.0)
    requirement = replace(
        layout.requirement_inputs,
        component_id=COMP,
        section_id=SECTION,
        width_mm=500.0,
        depth_mm=800.0,
        model_identity=MODEL,
        evidence_epoch_id=EPOCH,
        geometry_source_ref="geometry:column:1",
    )
    return {
        "layout_inputs": replace(layout, requirement_inputs=requirement),
        "combo_reconciliation": values["combo_reconciliation"],
        "combo_analysis_basis_bindings": tuple(values["combo_analysis_basis_bindings"].values()),
        "factual_design_results": values["factual_design_results"],
        "material_context": values["material_context"],
    }


def _reanalysis_inputs():
    stiffness = (
        {
            "section_name": "C80",
            "member_kind": "COLUMN",
            "i2_modifier": 0.70,
            "i3_modifier": 0.70,
            "source_refs": ("ETABS:C80",),
        },
    )
    slenderness = FND2._slenderness(
        m2=FND2._axis("M2", 800.0, promote_sway=False, promote_ratio=False),
        m3=FND2._axis("M3", 500.0, promote_sway=False, promote_ratio=False),
    )
    return FND2._inputs(slenderness=slenderness, stiffness=stiffness)


def test_production_request_contracts_contain_only_application_intent():
    assert tuple(item.name for item in fields(ColumnExecutionRequest)) == ("component_id",)
    assert tuple(item.name for item in fields(ProjectExecutionRequest)) == (
        "project_id",
        "report_id",
        "title",
        "column",
    )
    source = (ROOT / "tbdy_engine/application/contracts.py").read_text(encoding="utf-8")
    for forbidden in (
        "ready_fixture_inputs",
        "fixture_model_fingerprint",
        "fixture_evidence_epoch_id",
        "RegulatoryCompileInputs",
        "FactualColumnDesignResultPopulation",
        "ConcreteDesignComboReconciliation",
        "ComboAnalysisBasisBinding",
        "ColumnPmmMaterialContextBinding",
        "EtabsVerifiedSession",
    ):
        assert forbidden not in source


def test_runtime_capability_is_keyword_dependency_not_request_state():
    signature = inspect.signature(execute_project)
    assert tuple(signature.parameters) == ("request", "verified_session")
    assert signature.parameters["verified_session"].kind is inspect.Parameter.KEYWORD_ONLY
    assert "verified_session" not in {item.name for item in fields(ProjectExecutionRequest)}


def test_live_public_root_creates_one_context_then_fails_before_fnd2(monkeypatch):
    _, session = ACQ._verified_session()
    calls = []
    original = project_subject.create_trusted_live_acquisition_context

    def spy(verified_session):
        context = original(verified_session)
        calls.append(context)
        return context

    monkeypatch.setattr(project_subject, "create_trusted_live_acquisition_context", spy)
    artifact = execute_project(_request(), verified_session=session)

    assert len(calls) == 1
    context = calls[0]
    assert artifact.acquisition_context_ref == context.acquisition_context_ref
    assert artifact.status == STATUS_FACTUAL_ACQUISITION_BLOCKED
    assert artifact.column.blockers == (BLOCKER_LIVE_FND2_INPUT_LINEAGE,)
    assert artifact.column.fnd_col_2_program is None
    assert artifact.column.fnd_col_2_execution is None
    assert artifact.column.readiness_binding is None
    assert artifact.column.selected_rebar is None
    assert artifact.structural_assessment is None
    assert artifact.reconciliation is None
    assert artifact.building_report_model is None


def test_public_live_block_does_not_execute_fnd2(monkeypatch):
    _, session = ACQ._verified_session()

    def forbidden(*args, **kwargs):
        raise AssertionError("public LIVE A1 must stop before FND-COL-2X")

    monkeypatch.setattr(column_subject, "execute_source_bound_fnd_col_2_with_artifact", forbidden)
    monkeypatch.setattr(column_subject, "compile_source_bound_fnd_col_2_program", forbidden)
    artifact = execute_project(_request(), verified_session=session)
    assert artifact.status == STATUS_FACTUAL_ACQUISITION_BLOCKED


def test_qualified_fnd2_preserves_same_readiness_object_then_live_ready_stops_before_p8a(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("LIVE READY A1 must not reach P8A-B/FND-COL-4")

    monkeypatch.setattr(column_subject, "compose_canonical_column_longitudinal_selection", forbidden)
    column = column_subject._execute_column_domain_with_qualified_live_fnd2_for_test(
        _request().column,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        fnd_col_2_inputs=FND2._inputs(),
    )

    assert column.fnd_col_2_execution is not None
    assert column.fnd_col_2_execution.readiness.status == "READY"
    assert column.readiness_binding is not None
    assert column.readiness_binding.readiness is column.fnd_col_2_execution.readiness
    assert column.status == STATUS_APPLICATION_BLOCKED
    assert column.blockers == (BLOCKER_LIVE_DESIGN_LINEAGE,)
    assert column.selected_rebar is None


def test_qualified_nonready_fnd2_preserves_regulatory_stop_without_design_composition(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("non-READY FND-COL-2 must not reach P8A-B/FND-COL-4")

    monkeypatch.setattr(column_subject, "compose_canonical_column_longitudinal_selection", forbidden)
    column = column_subject._execute_column_domain_with_qualified_live_fnd2_for_test(
        _request().column,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        fnd_col_2_inputs=_reanalysis_inputs(),
    )

    assert column.status == STATUS_REANALYSIS_REQUIRED
    assert column.fnd_col_2_execution.readiness.status == "REANALYSIS_REQUIRED"
    assert column.readiness_binding.readiness is column.fnd_col_2_execution.readiness
    assert column.selected_rebar is None


def test_ready_fixture_is_test_only_and_reaches_existing_engine_selected_rebar(monkeypatch):
    P8AB._patch_all_pmm_rows_proven(monkeypatch)
    values = _ready_values()
    column = column_subject._execute_column_domain_with_ready_fixture_for_test(
        _request().column,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        fnd_col_2_inputs=FND2._inputs(),
        **values,
    )

    assert column.status == STATUS_SELECTED
    assert column.fnd_col_2_execution.readiness.status == "READY"
    assert column.readiness_binding.readiness is column.fnd_col_2_execution.readiness
    assert column.layout_authority is not None
    assert column.longitudinal_selection is not None
    assert column.selected_rebar is not None
    assert column.selected_rebar.authority == ENGINE_SELECTED_REBAR_AUTHORITY


def test_ready_fixture_can_reuse_existing_fcr_and_building_report_without_new_verdict(monkeypatch):
    P8AB._patch_all_pmm_rows_proven(monkeypatch)
    column = column_subject._execute_column_domain_with_ready_fixture_for_test(
        _request().column,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        fnd_col_2_inputs=FND2._inputs(),
        **_ready_values(),
    )
    artifact = project_subject._complete_project_from_canonical_column(
        _request(),
        column,
        acquisition_context_ref="test-only:acquisition-context",
        source_id="test-only:engine-artifact",
        source_kind=ReportSourceKind.ENGINE_ARTIFACT,
        source_title="Test-only PRODUCT-SPINE-COL-1 fixture",
        source_locator=None,
        execution_mode_label="TEST_FIXTURE",
    )

    assert artifact.reconciliation is not None
    assert artifact.reconciliation.expected_mandatory_instance_count == 1
    assert artifact.reconciliation.accounted_instance_count == 1
    assert artifact.reconciliation.report_reconciled is True
    assert artifact.building_report_model is not None
    assert artifact.building_report_model.report_integrity_status == "RECONCILED"
    payload = artifact.building_report_model.as_dict()
    assert payload["presentation_contract"]["global_compliance_verdict_emitted"] is False


def test_ready_fixture_composition_is_deterministic(monkeypatch):
    P8AB._patch_all_pmm_rows_proven(monkeypatch)
    kwargs = dict(
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        fnd_col_2_inputs=FND2._inputs(),
        **_ready_values(),
    )
    one = column_subject._execute_column_domain_with_ready_fixture_for_test(_request().column, **kwargs)
    two = column_subject._execute_column_domain_with_ready_fixture_for_test(_request().column, **kwargs)
    assert one == two


def test_application_ast_has_no_raw_etabs_or_tools_edges():
    banned_identifiers = {
        "SapModel",
        "DatabaseTables",
        "DesignConcrete",
        "FrameObj",
        "AreaObj",
        "PropFrame",
        "RunAnalysis",
        "StartDesign",
        "SetPresentUnits",
        "SetModifiers",
    }
    violations = []
    for path in sorted((ROOT / "tbdy_engine/application").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "tools" or alias.name.startswith("tools."):
                        violations.append((path.name, node.lineno, f"import:{alias.name}"))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "tools" or module.startswith("tools."):
                    violations.append((path.name, node.lineno, f"from:{module}"))
            elif isinstance(node, ast.Name) and node.id in banned_identifiers:
                violations.append((path.name, node.lineno, f"name:{node.id}"))
            elif isinstance(node, ast.Attribute):
                if node.attr in banned_identifiers:
                    violations.append((path.name, node.lineno, f"attr:{node.attr}"))
                if (
                    node.attr == "Setup"
                    and isinstance(node.value, ast.Attribute)
                    and node.value.attr == "Results"
                ):
                    violations.append((path.name, node.lineno, "attr:Results.Setup"))
    assert violations == []


def test_application_exports_do_not_publish_test_fixture_seams():
    import tbdy_engine.application as application

    exported = set(application.__all__)
    assert not any("fixture" in item.lower() for item in exported)
    assert not any(item.startswith("_") for item in exported)
