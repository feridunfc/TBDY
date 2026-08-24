from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.engine.project_execution as pe
from tbdy_engine.etabs.safety import EtabsSessionIdentity, EtabsUnitSnapshot
from tbdy_engine.features.etabs_com_attach import (
    ATTACH_STATUS_ATTACHED,
    ATTACH_STATUS_FAILED,
    EtabsAttachResult,
)
from tbdy_engine.features.etabs_mdev_mo_evidence import (
    BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH,
    BLOCKED_NON_FULL_ETABS_CAPTURE,
    MdevMoEvidenceError,
    ReviewedAnalysisMethod,
    ReviewedDirectionalWallPopulation,
    ReviewedRegulatoryBaseContext,
    ReviewedResultPopulationContext,
    build_directional_mdev_mo_evidence,
)
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus


MODEL_PATH = r"C:\tmp\vs4b_project_execution.edb"
MODEL_FP = pe.model_fingerprint_from_path(MODEL_PATH)
X_CASES = ("~Static+EccRSX", "~Static-EccRSX")
Y_CASES = ("~Static+EccRSY", "~Static-EccRSY")


def _request(
    *,
    direction: str = "X",
    declared_row: str = "A15",
    case_names: tuple[str, ...] | None = None,
    expected_model_fingerprint: str = MODEL_FP,
    population_mapping_review_refs: tuple[str, ...] = (),
) -> pe.VS4BA15ExecutionRequest:
    cases = case_names or (X_CASES if direction == "X" else Y_CASES)
    return pe.build_vs4b_a15_execution_request(
        expected_model_fingerprint=expected_model_fingerprint,
        direction=direction,
        declared_row=declared_row,
        regulatory_base_elevation_m=-5.15,
        rigid_basement_above_base=False,
        piers=("P1", "P2"),
        case_names=cases,
        reviewed_analysis_method=ReviewedAnalysisMethod.MODAL_COMBINATION.value,
        scaling_state_id="reviewed:scaled-final",
        result_operator_id="reviewed:signed-same-realization",
        wall_to_total_sign_factor=1,
        population_mapping_review_refs=population_mapping_review_refs,
        dts="2",
        bys=2,
        assumed_row="A15",
        assumed_r=7.0,
        assumed_d=2.5,
        base_review_refs=("review:base",),
        base_provenance_refs=("project:base",),
        wall_review_refs=(f"review:walls:{direction}",),
        wall_provenance_refs=(f"project:walls:{direction}",),
        result_review_refs=("review:results",),
        result_provenance_refs=("project:results",),
        declaration_review_refs=(f"review:declaration:{direction}",),
        declaration_provenance_refs=(f"project:declaration:{direction}",),
        seismic_review_refs=("review:seismic",),
        seismic_provenance_refs=("project:seismic",),
        analysis_evidence_refs=(f"analysis:basis:{direction}",),
        analysis_provenance_refs=(f"project:analysis:{direction}",),
    )


def _identity(path: str = MODEL_PATH) -> EtabsSessionIdentity:
    return EtabsSessionIdentity(
        process_id=None,
        attach_strategy="comtypes_get_active_object_etabs_api_object",
        program_api_version=2.014,
        program_name="ETABS",
        program_version="23.2.0",
        program_level="UltimateC",
        internal_program_version=None,
        model_full_path=path,
        model_fingerprint=None,
        model_fingerprint_source="UNAVAILABLE_FROM_CONSUMED_API",
        model_locked=True,
        units=EtabsUnitSnapshot(
            present_units=6,
            database_units=6,
            present_units_api="GetPresentUnits",
            database_units_api="GetDatabaseUnits",
        ),
    )


def _patch_attached(monkeypatch: pytest.MonkeyPatch, *, path: str = MODEL_PATH) -> None:
    sap = SimpleNamespace(DatabaseTables=object())
    attach = EtabsAttachResult(
        status=ATTACH_STATUS_ATTACHED,
        strategy="comtypes_get_active_object_etabs_api_object",
        etabs_object=object(),
        sap_model=sap,
        attempts=(),
    )
    monkeypatch.setattr(pe, "attach_to_running_etabs", lambda: attach)
    monkeypatch.setattr(
        pe,
        "read_session_identity",
        lambda *_args, **_kwargs: _identity(path),
    )


class _Bundle:
    def __init__(self, evidence) -> None:
        self.evidence_epoch_id = evidence.evidence_epoch_id
        self.model_fingerprint = evidence.model_fingerprint
        self._evidence = evidence

    def direction(self, direction: str):
        assert direction == self._evidence.direction
        return self._evidence

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_epoch_id": self.evidence_epoch_id,
            "model_fingerprint": self.model_fingerprint,
            "directions": [self._evidence.as_dict()],
        }


def _evidence(
    *,
    case_type: str = "LinRespSpec",
    wall_each: float = 30.0,
    mapping: tuple[str, ...] = (),
):
    sections = (
        {"Story": "B1", "Pier": "P1", "CGBotZ": -5.15, "AxisAngle": 0.0},
        {"Story": "B1", "Pier": "P2", "CGBotZ": -5.15, "AxisAngle": 0.0},
    )
    pier = {}
    story = {}
    base = {}
    for case in X_CASES:
        pier[case] = (
            {
                "Story": "B1",
                "Pier": "P1",
                "OutputCase": case,
                "CaseType": case_type,
                "Location": "Bottom",
                "M2": 0.0,
                "M3": wall_each,
            },
            {
                "Story": "B1",
                "Pier": "P2",
                "OutputCase": case,
                "CaseType": case_type,
                "Location": "Bottom",
                "M2": 0.0,
                "M3": wall_each,
            },
        )
        story[case] = (
            {
                "Story": "B1",
                "OutputCase": case,
                "CaseType": case_type,
                "Location": "Bottom",
                "MX": 0.0,
                "MY": 100.0,
            },
        )
        base[case] = (
            {
                "OutputCase": case,
                "CaseType": case_type,
                "MX": 0.0,
                "MY": 100.0,
                "X": 0.0,
                "Y": 0.0,
                "Z": -5.15,
            },
        )
    return build_directional_mdev_mo_evidence(
        direction="X",
        evidence_epoch_id="epoch:project-execution",
        model_fingerprint=MODEL_FP,
        case_names=X_CASES,
        base_context=ReviewedRegulatoryBaseContext(
            -5.15,
            False,
            ("review:base",),
            ("project:base",),
        ),
        wall_population=ReviewedDirectionalWallPopulation(
            "X",
            ("P1", "P2"),
            ("review:walls:X",),
            ("project:walls:X",),
        ),
        result_context=ReviewedResultPopulationContext(
            analysis_method=ReviewedAnalysisMethod.MODAL_COMBINATION,
            scaling_state_id="reviewed:scaled-final",
            result_operator_id="reviewed:signed-same-realization",
            wall_to_total_sign_factor=1,
            review_refs=("review:results",),
            provenance_refs=("project:results",),
            population_mapping_review_refs=mapping,
        ),
        pier_sections=sections,
        pier_force_rows_by_case=pier,
        story_force_rows_by_case=story,
        base_reaction_rows_by_case=base,
    )


def test_non_a15_is_pna_before_etabs_attach(monkeypatch: pytest.MonkeyPatch):
    def forbidden_attach():
        raise AssertionError("ETABS attach must not occur for non-A15")

    monkeypatch.setattr(pe, "attach_to_running_etabs", forbidden_attach)
    result = pe.execute_live_vs4b_a15(_request(declared_row="A14"))
    assert result.status == "PROVEN_NOT_APPLICABLE"
    assert result.factual_acquisition_status == pe.FACTUAL_NOT_REQUIRED
    assert result.exit_code == 0
    assert result.as_product_dict()["FACTUAL_MDEV_MO_ACQUISITION"] == "NOT_REQUIRED"


def test_attach_failure_preserves_exact_blocker(monkeypatch: pytest.MonkeyPatch):
    failed = EtabsAttachResult(
        status=ATTACH_STATUS_FAILED,
        strategy=None,
        etabs_object=None,
        sap_model=None,
        attempts=(),
    )
    monkeypatch.setattr(pe, "attach_to_running_etabs", lambda: failed)
    result = pe.execute_live_vs4b_a15(_request())
    assert result.status == pe.STATUS_BLOCKED_BY_LIVE_ETABS_ATTACH
    assert result.exit_code == 3
    assert result.as_product_dict() == {
        "status": pe.STATUS_BLOCKED_BY_LIVE_ETABS_ATTACH,
        "attempts": [],
    }


def test_model_fingerprint_mismatch_preserves_exact_blocker(monkeypatch: pytest.MonkeyPatch):
    _patch_attached(monkeypatch)
    result = pe.execute_live_vs4b_a15(
        _request(expected_model_fingerprint="etabs:model-identity:sha256:not-the-model")
    )
    assert result.status == pe.STATUS_BLOCKED_MODEL_IDENTITY_MISMATCH
    assert result.exit_code == 2
    assert result.observed_model_fingerprint == MODEL_FP
    assert result.as_product_dict()["observed_model_path"] == MODEL_PATH


def test_factual_acquisition_error_preserves_exact_status(monkeypatch: pytest.MonkeyPatch):
    _patch_attached(monkeypatch)

    def blocked_capture(**_kwargs):
        raise MdevMoEvidenceError(
            "capture is not FULL",
            status=BLOCKED_NON_FULL_ETABS_CAPTURE,
        )

    monkeypatch.setattr(pe, "capture_live_mdev_mo_evidence", blocked_capture)
    result = pe.execute_live_vs4b_a15(_request())
    assert result.status == BLOCKED_NON_FULL_ETABS_CAPTURE
    assert result.factual_acquisition_status == pe.FACTUAL_BLOCKED
    assert result.exit_code == 4
    assert result.as_product_dict()["status"] == BLOCKED_NON_FULL_ETABS_CAPTURE


def test_linstat_modal_without_reviewed_mapping_remains_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_attached(monkeypatch)
    factual = _evidence(case_type="LinStatic")
    assert factual.blocking_status == BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH
    monkeypatch.setattr(
        pe,
        "capture_live_mdev_mo_evidence",
        lambda **_kwargs: _Bundle(factual),
    )
    result = pe.execute_live_vs4b_a15(_request())
    assert result.status == BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH
    assert result.factual_acquisition_status == pe.FACTUAL_PROVEN
    assert result.direction_run is not None
    assert result.direction_run.program is None
    assert result.direction_run.store is None
    product = result.as_product_dict()
    assert product["status"] == "OK_WITH_REGULATORY_BLOCK"
    assert product["REGULATORY_A15_4345"] == BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH


def test_regulatory_ready_evidence_executes_real_existing_regulatory_path(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_attached(monkeypatch)
    factual = _evidence(case_type="LinRespSpec", wall_each=30.0)
    monkeypatch.setattr(
        pe,
        "capture_live_mdev_mo_evidence",
        lambda **_kwargs: _Bundle(factual),
    )
    result = pe.execute_live_vs4b_a15(_request())
    assert result.status == "RESOLVED"
    assert result.direction_run is not None
    assert result.direction_run.program is not None
    assert result.direction_run.store is not None
    assert result.direction_run.effective_policy["qualification_branch"] == "NOMINAL"
    assert result.direction_run.analysis_basis_status is AnalysisBasisStatus.MATCH
    assert result.as_product_dict()["status"] == "OK"


@pytest.mark.parametrize(
    ("direction", "cases"),
    (("X", X_CASES), ("Y", Y_CASES)),
)
def test_execution_forwards_one_direction_and_exact_supplied_case_pair_only(
    monkeypatch: pytest.MonkeyPatch,
    direction: str,
    cases: tuple[str, ...],
):
    _patch_attached(monkeypatch)
    observed = {}

    def capture(**kwargs):
        observed.update(kwargs)
        raise MdevMoEvidenceError("bounded stop", status=BLOCKED_NON_FULL_ETABS_CAPTURE)

    monkeypatch.setattr(pe, "capture_live_mdev_mo_evidence", capture)
    result = pe.execute_live_vs4b_a15(_request(direction=direction, case_names=cases))
    assert result.status == BLOCKED_NON_FULL_ETABS_CAPTURE
    assert observed["direction"] == direction
    assert observed["case_names"] == cases
    assert observed["wall_population"].direction == direction
