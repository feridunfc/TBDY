from pathlib import Path

from tbdy_engine.contracts.loader import ContractConstitutionLoader
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.coverage.models import CoverageStatus
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"


def load_bundle():
    return ContractConstitutionLoader(CATALOG_DIR).load()


def evidence(status=FeatureEvidenceStatus.FULL, reason=None):
    kwargs = dict(
        evidence_status=status,
        source_table="frame_section_properties",
        actual_table_name="Frame Section Properties",
        source_column="Width",
        source_row={"SectionName": "B40x70"},
        raw_value=400,
        normalized_value=400,
        unit="mm",
        resolver="test",
    )
    if status != FeatureEvidenceStatus.FULL:
        kwargs["reason"] = reason or "partial evidence"
        if status == FeatureEvidenceStatus.PARTIAL:
            kwargs["source_column"] = None
    return FeatureEvidence(**kwargs)


def feature(name, status=FeatureValueStatus.RESOLVED, ev_status=FeatureEvidenceStatus.FULL):
    ev = evidence(ev_status, reason="not complete")
    return FeatureValue(
        feature_name=name,
        value=400 if status != FeatureValueStatus.MISSING else None,
        unit="mm",
        semantic_role="GEOMETRY",
        status=status,
        evidence=[ev],
    )


def snapshot(features):
    return FeatureSnapshot(component_type="beam", component_id="B1", identity={"component": "B1"}, features=features)


def test_all_required_features_resolved_is_runnable():
    bundle = load_bundle()
    snap = snapshot({"beam_width_mm": feature("beam_width_mm")})
    row = CoverageBuilder(bundle).build_row(snap, "beam_geometry_min_width", design_context={"ductility_class": "HIGH"})
    assert row.coverage_status == CoverageStatus.RUNNABLE
    assert row.resolved_features == ("beam_width_mm",)
    assert row.missing_features == ()


def test_missing_required_feature_is_blocked():
    bundle = load_bundle()
    row = CoverageBuilder(bundle).build_row(snapshot({}), "beam_geometry_min_width", design_context={"ductility_class": "HIGH"})
    assert row.coverage_status == CoverageStatus.BLOCKED
    assert row.missing_features[0].feature_name == "beam_width_mm"


def test_partial_evidence_is_partial():
    bundle = load_bundle()
    snap = snapshot({"beam_width_mm": feature("beam_width_mm", ev_status=FeatureEvidenceStatus.PARTIAL)})
    row = CoverageBuilder(bundle).build_row(snap, "beam_geometry_min_width", design_context={"ductility_class": "HIGH"})
    assert row.coverage_status == CoverageStatus.PARTIAL
    assert row.evidence_status.value == "PARTIAL"


def test_missing_design_context_is_partial_or_blocked():
    bundle = load_bundle()
    snap = snapshot({"beam_width_mm": feature("beam_width_mm")})
    row = CoverageBuilder(bundle).build_row(snap, "beam_geometry_min_width", design_context={})
    assert row.coverage_status in {CoverageStatus.PARTIAL, CoverageStatus.BLOCKED}
    assert row.missing_design_context[0].context_field == "ductility_class"


def test_unknown_check_id_rejected():
    bundle = load_bundle()
    snap = snapshot({"beam_width_mm": feature("beam_width_mm")})
    try:
        CoverageBuilder(bundle).build_row(snap, "unknown_check", design_context={})
    except ValueError as exc:
        assert "Unknown check_id" in str(exc)
    else:
        raise AssertionError("unknown check_id should be rejected")
