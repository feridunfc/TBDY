#!/usr/bin/env python3
"""Build the deterministic UR-2 representative DEMO DATA package.

The demo fixture is intentionally fictional. It exercises only the accepted
BuildingReportModel -> projection -> renderer/artifact path. No ETABS query or
engineering calculation is performed here, and no reference-report numeric
example is copied into the fixture.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.coverage.project_reconciliation import AnalysisBasisRef, ProjectCoverageReconciler, ReportBindingRef, ReportContributionRef, canonical_closure_report_source_ref
from tbdy_engine.product_reports.building_report_package import build_building_report_package, build_report_delivery_artifacts, verify_building_report_package
from tbdy_engine.product_reports.slice_report_contribution import ReportCalculation, ReportField, ReportTable, SliceReportContribution
from tbdy_engine.product_reports.unified_building_report import BuildingReportModel, ProjectBasisEntry, ProjectBasisLedger, ReportSourceKind, SourceManifest, SourceManifestEntry
from tbdy_engine.regulatory.contracts import ApplicabilityBinding, ApplicabilityState, CheckEvaluatorBinding, CheckSpec, ClosureExecutionStatus, Grain, RuleClosureOutcome, RuleId
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus, FormalResultRecord, RegulatoryCompileInputs, RegulatoryCompiler, RegulatoryStoreSnapshot, RuleScopeTarget
from tbdy_engine.regulatory.registry import RegulatoryRegistry


@dataclass(frozen=True, slots=True)
class _DemoApplicability:
    state: ApplicabilityState = ApplicabilityState.APPLIES


def _app(value: _DemoApplicability) -> ApplicabilityState:
    return value.state


def _spec(rule: str) -> CheckSpec:
    return CheckSpec(
        rule_id=RuleId(rule),
        code_refs=("DEMO_AUTHORITY_ONLY",),
        rule_version="ur2-demo-v1",
        formal_result_type=CheckResult,
        dependencies=(),
        applicability=ApplicabilityBinding(f"demo-app:{rule}", _DemoApplicability, _app),
        evaluator=CheckEvaluatorBinding(f"demo-eval:{rule}", object, lambda _: None),
    )


def _field(key: str, label: str, value: object, unit: str | None = None, role: str = "RESULT", note: str | None = None) -> ReportField:
    return ReportField(key=key, label=label, value=value, unit=unit, role=role, note=note)  # type: ignore[arg-type]


# Fictional values created only for product demonstration. They are not copied
# from the reporting reference documents and are not live engineering truth.
_DEMO_ROWS = (
    ("MODEL_INVENTORY", "PROVEN", "MODEL_INVENTORY", None, "Model inventory snapshot", CheckStatus.OK, ClosureExecutionStatus.EXECUTED, None, None, 184, None, None, "DEMO_MODEL_SNAPSHOT"),
    ("LOAD_COMBINATIONS", "PROVEN", "DESIGN_COMBINATION", None, "Load / mass / case / combination inventory", CheckStatus.OK, ClosureExecutionStatus.EXECUTED, None, None, 27, None, None, "DEMO_COMBO_LEDGER"),
    ("MODAL_MASS", "PASS", "GLOBAL_ANALYSIS", "MODEL", "Modal participating mass review", CheckStatus.OK, ClosureExecutionStatus.EXECUTED, None, "X/Y", 0.972, 0.950, 1.023, "DEMO_MODE_09"),
    ("DRIFT_Y", "FAIL", "GLOBAL_ANALYSIS", "STORY-04-Y", "Relative storey drift", CheckStatus.FAIL, ClosureExecutionStatus.EXECUTED, "Story 4", "Y", 0.0087, 0.0080, 1.0875, "DEMO_RS_Y_NEG"),
    ("BEAM_B12", "PASS", "BEAM", "B12", "Beam design review", CheckStatus.OK, ClosureExecutionStatus.EXECUTED, "Story 2", None, 0.71, 1.0, 0.71, "DEMO_CMB_BEAM_07"),
    ("COLUMN_C42", "FAIL", "COLUMN", "C42", "Column design review", CheckStatus.FAIL, ClosureExecutionStatus.EXECUTED, "Story 1", None, 1.08, 1.0, 1.08, "DEMO_CMB_COLUMN_11"),
    ("SCWB_J101", "BLOCKED", "SCWB_JOINT", "J101", "SCWB / joint review", None, ClosureExecutionStatus.BLOCKED, "Story 1", "X", None, None, None, "DEMO_JOINT_CONTEXT"),
    ("WALL_W3", "PASS", "WALL", "W3", "Wall review", CheckStatus.OK, ClosureExecutionStatus.EXECUTED, "Story 1", "X", 0.64, 1.0, 0.64, "DEMO_CMB_WALL_03"),
    ("FOUNDATION_F1", "NO_DATA", "FOUNDATION", "F1", "Foundation / geotechnical review", None, ClosureExecutionStatus.NO_DATA, None, None, None, None, None, "DEMO_FOUNDATION_CONTEXT"),
)


def _contribution(row: tuple[object, ...]) -> SliceReportContribution:
    rule, status, component_type, component_id, title, _formal_status, closure, story, direction, demand, limit, ratio, governing = row
    fields = (
        _field("demo_marker", "Data classification", "DEMO DATA", role="NOTE", note="Illustrative product fixture - not live engineering truth."),
        _field("story", "Story", story, role="IDENTITY"),
        _field("direction", "Direction", direction, role="IDENTITY"),
        _field("demand", "Demand / resolved value", demand, "demo-unit", "RESULT"),
        _field("limit", "Limit / capacity", limit, "demo-unit", "LIMIT"),
        _field("ratio", "Canonical ratio", ratio, None, "RESULT"),
        _field("governing_case", "Governing case / combo", governing, role="IDENTITY"),
        _field("code_authority", "Code authority", "DEMO AUTHORITY REF - NOT LIVE", role="AUTHORITY"),
    )
    calculations = ()
    if closure is ClosureExecutionStatus.EXECUTED:
        calculations = (
            ReportCalculation(
                calculation_id=f"DEMO_CALC:{rule}",
                title=f"{title} - canonical demo calculation trace",
                formula="DEMO_UPSTREAM_EXPRESSION - DISPLAY ONLY - NOT EVALUATED BY RENDERER",
                inputs=(_field("canonical_input", "Canonical demo input", demand, "demo-unit", "INPUT"),),
                outputs=(_field("canonical_output", "Canonical demo output", ratio, None, "RESULT"),),
                authority_refs=(f"DEMO_AUTH:{rule}",),
                evidence_refs=(f"DEMO_EVID:{rule}",),
                governing_ref=str(governing),
            ),
        )
    table = ReportTable(
        table_id=f"DEMO_TABLE:{rule}",
        title=f"{title} - detailed demo population",
        columns=("story", "direction", "demand", "limit", "ratio", "governing_case", "data_classification"),
        rows=({"story": story, "direction": direction, "demand": demand, "limit": limit, "ratio": ratio, "governing_case": governing, "data_classification": "DEMO DATA"},),
        purpose="DETAIL",
    )
    warnings: tuple[str, ...] = ()
    if status == "FAIL":
        warnings = ("DEMO canonical finding requiring engineer review; no renderer remediation is generated.",)
    elif status in {"BLOCKED", "NO_DATA"}:
        warnings = ("DEMO canonical evidence gap; reporting preserves the upstream status exactly.",)
    return SliceReportContribution(
        slice_id=f"demo:{rule}", title=str(title), contribution_kind="FACTUAL" if status == "PROVEN" else "CHECK", status=str(status),
        component_type=str(component_type), component_id=None if component_id is None else str(component_id), summary_fields=fields,
        tables=(table,), calculations=calculations, authority_refs=(f"DEMO_AUTH:{rule}",), evidence_refs=(f"DEMO_EVID:{rule}",), warnings=warnings,
        render_views=("EXECUTIVE", "ENGINEERING", "AUDIT"),
    )


def build_demo_model() -> BuildingReportModel:
    rules = tuple(str(row[0]) for row in _DEMO_ROWS)
    registry = RegulatoryRegistry(checks=tuple(_spec(rule) for rule in rules))
    program = RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(rule_targets=tuple(RuleScopeTarget(rule_id=RuleId(rule), grain=Grain.COMPONENT, scope_ref=f"DEMO_SCOPE:{rule}", applicability_input=_DemoApplicability()) for rule in rules)),
    )
    by_rule = {item.rule_id.value: item for item in program.plan.compiled_rule_instances}
    formal_results: list[FormalResultRecord] = []
    closure_outcomes: list[RuleClosureOutcome] = []
    source_refs: list[str] = []
    contributions: list[SliceReportContribution] = []
    bindings: list[ReportBindingRef] = []
    basis_refs: list[AnalysisBasisRef] = []

    for row in _DEMO_ROWS:
        rule = str(row[0]); formal_status = row[5]; closure = row[6]; instance_id = by_rule[rule]; contribution = _contribution(row)
        contributions.append(contribution)
        if closure is ClosureExecutionStatus.EXECUTED:
            if not isinstance(formal_status, CheckStatus):
                raise RuntimeError("executed demo row requires CheckStatus")
            formal_ref = f"{instance_id.value}:CheckResult"
            formal_results.append(FormalResultRecord(instance_id=instance_id, result=CheckResult(check_id=rule, component=instance_id.scope_ref, component_type=str(row[2]), status=formal_status, story=None if row[7] is None else str(row[7]), section=None, value=row[9], limit=row[10], ratio=None if row[11] is None else float(row[11]), ratio_type=None, unit="demo-unit", code_ref="DEMO_AUTHORITY_ONLY", messages=("DEMO DATA - not live engineering truth",))))
            closure_outcomes.append(RuleClosureOutcome(compiled_record_ref=instance_id, execution_status=ClosureExecutionStatus.EXECUTED, formal_result_ref=formal_ref))
            source_ref = formal_ref
        else:
            if closure not in {ClosureExecutionStatus.BLOCKED, ClosureExecutionStatus.NO_DATA}:
                raise RuntimeError("unsupported demo closure state")
            closure_outcomes.append(RuleClosureOutcome(compiled_record_ref=instance_id, execution_status=closure))
            source_ref = canonical_closure_report_source_ref(instance_id)
        source_refs.append(source_ref)
        bindings.append(ReportBindingRef(source_ref, ReportContributionRef.from_contribution(contribution)))
        basis_refs.append(AnalysisBasisRef(instance_id=instance_id, status=AnalysisBasisStatus.REANALYSIS_REQUIRED if rule == "DRIFT_Y" else AnalysisBasisStatus.MATCH, source_ref=f"DEMO_ANALYSIS_BASIS:{rule}"))

    snapshot = RegulatoryStoreSnapshot(plan_identity=program.plan.plan_identity, regulatory_quantities=(), formal_results=tuple(formal_results), closure_outcomes=tuple(closure_outcomes), diagnostics=())
    reconciliation = ProjectCoverageReconciler.reconcile(compiled_program=program, store_snapshot=snapshot, report_contributions=tuple(contributions), report_bindings=tuple(bindings), required_report_source_refs=tuple(source_refs), analysis_basis_refs=tuple(basis_refs))
    project_basis = ProjectBasisLedger((
        ProjectBasisEntry(key="report_data_classification", label="Data classification", value="DEMO DATA", source_ids=("SRC:UR2_DEMO",), note="Illustrative product package; not live engineering truth."),
        ProjectBasisEntry(key="report_phase", label="Report phase", value="PRODUCT_DEMO", source_ids=("SRC:UR2_DEMO",)),
        ProjectBasisEntry(key="project_name", label="Project", value="Illustrative Unified Engineering Review", source_ids=("SRC:UR2_DEMO",)),
        ProjectBasisEntry(key="design_basis", label="Design basis", value="DEMO ONLY - canonical fixture authority refs", source_ids=("SRC:UR2_DEMO",)),
        ProjectBasisEntry(key="analysis_model", label="Analysis model", value="DEMO-MODEL-UR2", source_ids=("SRC:UR2_DEMO",)),
    ))
    source_manifest = SourceManifest((SourceManifestEntry(source_id="SRC:UR2_DEMO", source_kind=ReportSourceKind.REVIEWED_DECLARATION, title="UR-2 deterministic fictional demo declaration", fingerprint="demo:not-live:ur2:v1", locator="tools/build_ur2_demo_report.py", authority_refs=("DEMO_AUTHORITY_ONLY",), evidence_refs=("DEMO_DATA_ONLY",)),))
    return BuildingReportModel(report_id="UR2-DEMO-REPORT", project_id="UR2-DEMO-PROJECT", title="Unified Engineering Review - DEMO DATA", reconciliation=reconciliation, project_basis=project_basis, source_manifest=source_manifest, contributions=tuple(contributions), report_bindings=tuple(bindings))


def write_demo_package(output_dir: Path) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    model = build_demo_model()
    members_1 = build_report_delivery_artifacts(model); members_2 = build_report_delivery_artifacts(model)
    first = {item.filename: item for item in members_1}; second = {item.filename: item for item in members_2}
    if set(first) != set(second):
        raise RuntimeError("deterministic delivery member population mismatch")
    for name in sorted(first):
        if first[name].content != second[name].content:
            raise RuntimeError(f"non-deterministic delivery artifact: {name}")
    package_1 = build_building_report_package(model); package_2 = build_building_report_package(model)
    if package_1.content != package_2.content:
        raise RuntimeError("non-deterministic building_report_package.zip")
    verify_building_report_package(package_1)
    paths: list[Path] = []
    for artifact in members_1:
        path = output_dir / artifact.filename; path.write_bytes(artifact.content); paths.append(path)
    package_path = output_dir / package_1.filename; package_path.write_bytes(package_1.content); paths.append(package_path)
    expected = {"engineering.html", "engineering.pdf", "engineering.xlsx", "audit.html", "audit.pdf", "audit.xlsx", "building_report_model.json", "manifest.json", "building_report_package.zip"}
    actual = {path.name for path in output_dir.iterdir() if path.is_file()}
    if actual != expected:
        raise RuntimeError(f"UR-2 visible artifact population mismatch: expected={sorted(expected)} actual={sorted(actual)}")
    for html_name in ("engineering.html", "audit.html"):
        text = (output_dir / html_name).read_text(encoding="utf-8")
        for marker in ("DEMO DATA - ILLUSTRATIVE PRODUCT PACKAGE - NOT LIVE ENGINEERING TRUTH", "Engineering executive summary", "Critical findings / blockers / reanalysis", "REPORT_INPUT_GAP register"):
            if marker not in text:
                raise RuntimeError(f"{html_name} missing required visible marker: {marker}")
    return tuple(sorted(paths))


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--output-dir", type=Path, default=Path("ur2_demo")); args = parser.parse_args()
    paths = write_demo_package(args.output_dir)
    print("UR-2 DEMO DATA package generated:")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
