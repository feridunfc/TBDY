from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from tbdy_engine.analysis_basis.basis_report import (
    AnalysisBasisReport,
    AnalysisBasisReportRow,
    build_analysis_basis_report,
    build_analysis_basis_report_row,
)
from tbdy_engine.analysis_basis.contracts import (
    AnalysisBasisCompatibility,
    AnalysisSystemAssumption,
    ReviewedDirectionalSystemDeclaration,
    build_analysis_basis_snapshot,
)
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.findings import build_finding_from_analysis_basis
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus


ZONE = "SUPERSTRUCTURE"


def _epoch() -> EvidenceEpoch:
    return EvidenceEpoch(
        epoch_id="E17",
        model_fingerprint="fixture:model",
        origin=EvidenceEpochOrigin.FIXTURE_REPLAY,
        source_fingerprint="fixture:source",
        provenance_refs=("fixture:capture",),
    )


def _artifacts(direction: str, status: AnalysisBasisStatus):
    declaration = ReviewedDirectionalSystemDeclaration(
        declaration_id=f"declaration:{direction}",
        structural_zone_ref=ZONE,
        direction=direction,
        declared_basis_ref=f"declared:{direction}",
    )
    assumption = AnalysisSystemAssumption(
        assumption_id=f"assumption:{direction}:E17",
        epoch_ref="epoch:E17",
        structural_zone_ref=ZONE,
        direction=direction,
        observed_basis_ref=f"observed:{direction}",
        analysis_evidence_refs=(f"analysis-evidence:{direction}",),
    )
    compatibility = AnalysisBasisCompatibility(
        compatibility_id=f"compatibility:{direction}",
        epoch_ref="epoch:E17",
        structural_zone_ref=ZONE,
        direction=direction,
        required_basis_ref=f"policy:{direction}",
        analysis_assumption_ref=assumption.assumption_id,
        status=status,
        diagnostic_refs=(f"diag:{direction}",),
    )
    snapshot = build_analysis_basis_snapshot(
        epoch=_epoch(),
        declaration=declaration,
        resolved_policy_ref=f"policy:{direction}",
        assumption=assumption,
        compatibility=compatibility,
        analysis_evidence_refs=(f"analysis-evidence:{direction}",),
        provenance_refs=(f"snapshot-provenance:{direction}",),
    )
    return snapshot, compatibility


def test_basis_report_row_projects_exact_compatibility_status_and_checks_coherence() -> None:
    snapshot, compatibility = _artifacts("X", AnalysisBasisStatus.MATCH)
    row = build_analysis_basis_report_row(snapshot=snapshot, compatibility=compatibility, provenance_refs=("report-row:X",))
    assert row.compatibility_status is AnalysisBasisStatus.MATCH
    assert row.snapshot_ref == snapshot.snapshot_id
    assert row.analysis_evidence_refs == snapshot.analysis_evidence_refs

    wrong = AnalysisBasisCompatibility(
        compatibility_id="compatibility:OTHER",
        epoch_ref=compatibility.epoch_ref,
        structural_zone_ref=compatibility.structural_zone_ref,
        direction=compatibility.direction,
        required_basis_ref=compatibility.required_basis_ref,
        analysis_assumption_ref=compatibility.analysis_assumption_ref,
        status=compatibility.status,
    )
    with pytest.raises(ValueError, match="compatibility_ref"):
        build_analysis_basis_report_row(snapshot=snapshot, compatibility=wrong)


def test_basis_report_row_identity_is_content_bound_and_status_bearing() -> None:
    snapshot, compatibility = _artifacts("X", AnalysisBasisStatus.MATCH)
    first = build_analysis_basis_report_row(snapshot=snapshot, compatibility=compatibility)
    second = build_analysis_basis_report_row(snapshot=snapshot, compatibility=compatibility)
    changed_status = AnalysisBasisCompatibility(
        compatibility_id=compatibility.compatibility_id,
        epoch_ref=compatibility.epoch_ref,
        structural_zone_ref=compatibility.structural_zone_ref,
        direction=compatibility.direction,
        required_basis_ref=compatibility.required_basis_ref,
        analysis_assumption_ref=compatibility.analysis_assumption_ref,
        status=AnalysisBasisStatus.REANALYSIS_REQUIRED,
    )
    changed = build_analysis_basis_report_row(snapshot=snapshot, compatibility=changed_status)
    assert first == second
    assert first.row_id == second.row_id
    assert changed.row_id != first.row_id
    with pytest.raises(ValueError, match="canonical stored semantic fields"):
        replace(first, row_id="analysis-basis-report-row:" + "0" * 64)


def test_basis_report_contains_match_and_reanalysis_rows_while_finding_projects_only_adverse() -> None:
    x_snapshot, x_compat = _artifacts("X", AnalysisBasisStatus.MATCH)
    y_snapshot, y_compat = _artifacts("Y", AnalysisBasisStatus.REANALYSIS_REQUIRED)
    x_row = build_analysis_basis_report_row(snapshot=x_snapshot, compatibility=x_compat)
    y_row = build_analysis_basis_report_row(snapshot=y_snapshot, compatibility=y_compat)
    report = build_analysis_basis_report(rows=(y_row, x_row), provenance_refs=("report:E17",))

    assert [(row.direction, row.compatibility_status) for row in report.rows] == [
        ("X", AnalysisBasisStatus.MATCH),
        ("Y", AnalysisBasisStatus.REANALYSIS_REQUIRED),
    ]
    assert build_finding_from_analysis_basis(compatibility=x_compat) is None
    y_finding = build_finding_from_analysis_basis(compatibility=y_compat)
    assert y_finding is not None
    assert y_finding.source_status is AnalysisBasisStatus.REANALYSIS_REQUIRED
    serialized = report.as_dict()
    assert [row["compatibility_status"] for row in serialized["rows"]] == ["MATCH", "REANALYSIS_REQUIRED"]
    assert "reanalysis_required" not in serialized


def test_report_is_order_independent_content_bound_and_rejects_duplicate_scope_direction() -> None:
    x_snapshot, x_compat = _artifacts("X", AnalysisBasisStatus.MATCH)
    y_snapshot, y_compat = _artifacts("Y", AnalysisBasisStatus.UNRESOLVED)
    x_row = build_analysis_basis_report_row(snapshot=x_snapshot, compatibility=x_compat)
    y_row = build_analysis_basis_report_row(snapshot=y_snapshot, compatibility=y_compat)
    first = build_analysis_basis_report(rows=(x_row, y_row), provenance_refs=("p:report",))
    reversed_report = build_analysis_basis_report(rows=(y_row, x_row), provenance_refs=("p:report",))
    assert first == reversed_report
    assert first.report_id == reversed_report.report_id
    with pytest.raises(ValueError, match="canonical stored semantic fields"):
        replace(first, report_id="analysis-basis-report:" + "0" * 64)

    duplicate_row = replace(x_row, row_id=x_row.row_id)
    with pytest.raises(ValueError, match="duplicate snapshot_ref|duplicate structural_zone_ref"):
        build_analysis_basis_report(rows=(x_row, duplicate_row))


def test_report_rejects_duplicate_zone_direction_even_with_distinct_snapshot_ref() -> None:
    snapshot, compatibility = _artifacts("X", AnalysisBasisStatus.MATCH)
    row = build_analysis_basis_report_row(snapshot=snapshot, compatibility=compatibility)
    alternate_compatibility = AnalysisBasisCompatibility(
        compatibility_id="compatibility:X:alternate",
        epoch_ref=compatibility.epoch_ref,
        structural_zone_ref=compatibility.structural_zone_ref,
        direction=compatibility.direction,
        required_basis_ref=compatibility.required_basis_ref,
        analysis_assumption_ref=compatibility.analysis_assumption_ref,
        status=AnalysisBasisStatus.MATCH,
    )
    alternate_snapshot = build_analysis_basis_snapshot(
        epoch=_epoch(),
        declaration=ReviewedDirectionalSystemDeclaration(
            declaration_id="declaration:X:alternate",
            structural_zone_ref=ZONE,
            direction="X",
            declared_basis_ref="declared:X",
        ),
        resolved_policy_ref="policy:X",
        assumption=AnalysisSystemAssumption(
            assumption_id="assumption:X:E17",
            epoch_ref="epoch:E17",
            structural_zone_ref=ZONE,
            direction="X",
            observed_basis_ref="observed:X",
        ),
        compatibility=alternate_compatibility,
    )
    alternate_row = build_analysis_basis_report_row(snapshot=alternate_snapshot, compatibility=alternate_compatibility)
    assert alternate_row.snapshot_ref != row.snapshot_ref
    with pytest.raises(ValueError, match="duplicate structural_zone_ref"):
        build_analysis_basis_report(rows=(row, alternate_row))


def test_basis_report_forbidden_fields_and_imports_are_absent() -> None:
    forbidden_fields = {
        "r", "d", "i", "dts", "bys", "bks", "system_class", "ductility_class",
        "mdev", "mo", "omega", "compatibility_passed", "basis_passed",
        "full_tbdy_compliance_status", "reanalysis_required",
    }
    for cls in (AnalysisBasisReportRow, AnalysisBasisReport):
        assert forbidden_fields.isdisjoint({item.name.casefold() for item in fields(cls)})

    import tbdy_engine.analysis_basis.basis_report as module
    source = Path(module.__file__).read_text(encoding="utf-8")
    for token in ("tbdy_engine.etabs", "etabs_gateway", "product_reports", "RegulatoryEngine", "report_package"):
        assert token not in source
