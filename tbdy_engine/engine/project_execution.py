"""Single production execution authority for bounded live VS-4B-A.

This module owns orchestration only. Factual acquisition remains in the feature
layer and regulatory decisions remain in ``tbdy_engine.regulatory``.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from tbdy_engine.etabs.safety import EtabsSessionIdentity, read_session_identity
from tbdy_engine.features.etabs_com_attach import (
    ATTACH_STATUS_ATTACHED,
    attach_to_running_etabs,
)
from tbdy_engine.features.etabs_mdev_mo_evidence import (
    LiveMdevMoEvidenceBundle,
    MdevMoEvidenceError,
    ReviewedAnalysisMethod,
    ReviewedDirectionalWallPopulation,
    ReviewedRegulatoryBaseContext,
    ReviewedResultPopulationContext,
    capture_live_mdev_mo_evidence,
)
from tbdy_engine.integration.live_beam_geometry_f0 import model_fingerprint_from_path
from tbdy_engine.regulatory.structural_system import (
    DirectionalAnalysisSystemAssumption,
    ReviewedDirectionalRcSystemDeclaration,
    ReviewedSeismicClassificationContext,
)
from tbdy_engine.regulatory.vs4b_program import (
    STATUS_PROVEN_NOT_APPLICABLE,
    STATUS_RESOLVED,
    VS4BA15DirectionRun,
    run_vs4b_a15_direction,
)

STATUS_BLOCKED_BY_LIVE_ETABS_ATTACH = "BLOCKED_BY_LIVE_ETABS_ATTACH"
STATUS_BLOCKED_MODEL_IDENTITY_MISMATCH = "BLOCKED_MODEL_IDENTITY_MISMATCH"
STATUS_BLOCKED_MDEV_MO_FACTUAL_ACQUISITION = "BLOCKED_MDEV_MO_FACTUAL_ACQUISITION"

FACTUAL_NOT_REQUIRED = "NOT_REQUIRED"
FACTUAL_NOT_ACQUIRED = "NOT_ACQUIRED"
FACTUAL_BLOCKED = "BLOCKED"
FACTUAL_PROVEN = "PROVEN"

_SAFETY_PAYLOAD: Mapping[str, object] = {
    "analysis_run": False,
    "design_run": False,
    "model_save": False,
    "model_or_property_mutation": False,
    "present_units_set": False,
    "output_selection_mutation": "REVERSIBLE_TRANSACTION_ONLY",
}


def _nonblank(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _tuple_items(values: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{label} must be a sequence of strings")
    return tuple(values)


@dataclass(frozen=True, slots=True)
class VS4BA15ExecutionRequest:
    expected_model_fingerprint: str
    declaration: ReviewedDirectionalRcSystemDeclaration
    regulatory_base_elevation_m: float
    rigid_basement_above_base: bool
    piers: tuple[str, ...]
    case_names: tuple[str, ...]
    reviewed_analysis_method: str
    scaling_state_id: str
    result_operator_id: str
    wall_to_total_sign_factor: int
    population_mapping_review_refs: tuple[str, ...]
    dts: str
    bys: int
    assumed_row: str
    assumed_r: float
    assumed_d: float
    base_review_refs: tuple[str, ...]
    base_provenance_refs: tuple[str, ...]
    wall_review_refs: tuple[str, ...]
    wall_provenance_refs: tuple[str, ...]
    result_review_refs: tuple[str, ...]
    result_provenance_refs: tuple[str, ...]
    seismic_review_refs: tuple[str, ...]
    seismic_provenance_refs: tuple[str, ...]
    analysis_evidence_refs: tuple[str, ...]
    analysis_provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonblank(self.expected_model_fingerprint, "expected_model_fingerprint")
        if not isinstance(self.declaration, ReviewedDirectionalRcSystemDeclaration):
            raise TypeError("declaration must be ReviewedDirectionalRcSystemDeclaration")
        if not isinstance(self.rigid_basement_above_base, bool):
            raise TypeError("rigid_basement_above_base must be bool")
        for name in (
            "piers",
            "case_names",
            "population_mapping_review_refs",
            "base_review_refs",
            "base_provenance_refs",
            "wall_review_refs",
            "wall_provenance_refs",
            "result_review_refs",
            "result_provenance_refs",
            "seismic_review_refs",
            "seismic_provenance_refs",
            "analysis_evidence_refs",
            "analysis_provenance_refs",
        ):
            object.__setattr__(self, name, _tuple_items(getattr(self, name), name))

    @property
    def direction(self) -> str:
        return self.declaration.direction

    @property
    def declared_row(self) -> str:
        return self.declaration.table_4_1_row


@dataclass(frozen=True, slots=True)
class VS4BA15ExecutionResult:
    status: str
    factual_acquisition_status: str
    direction: str
    reviewed_declared_row: str
    exit_code: int
    attach_attempts: tuple[Mapping[str, object], ...] = ()
    identity: EtabsSessionIdentity | None = None
    expected_model_fingerprint: str | None = None
    observed_model_fingerprint: str | None = None
    observed_model_path: str | None = None
    base_context: ReviewedRegulatoryBaseContext | None = None
    evidence_bundle: LiveMdevMoEvidenceBundle | None = None
    direction_run: VS4BA15DirectionRun | None = None
    message: str | None = None

    @property
    def regulatory_resolved(self) -> bool:
        return self.status == STATUS_RESOLVED

    @property
    def factual_evidence_payload(self) -> dict[str, object] | None:
        if self.evidence_bundle is None:
            return None
        return self.evidence_bundle.as_dict()

    def as_product_dict(self) -> dict[str, object]:
        if self.status == STATUS_PROVEN_NOT_APPLICABLE:
            return {
                "status": STATUS_PROVEN_NOT_APPLICABLE,
                "VS4B_A15_APPLICABILITY": STATUS_PROVEN_NOT_APPLICABLE,
                "FACTUAL_MDEV_MO_ACQUISITION": FACTUAL_NOT_REQUIRED,
                "direction": self.direction,
                "reviewed_declared_row": self.reviewed_declared_row,
                "effective_policy": None,
                "analysis_basis_status": None,
            }
        if self.status == STATUS_BLOCKED_BY_LIVE_ETABS_ATTACH:
            return {
                "status": STATUS_BLOCKED_BY_LIVE_ETABS_ATTACH,
                "attempts": [dict(item) for item in self.attach_attempts],
            }
        if self.status == STATUS_BLOCKED_MODEL_IDENTITY_MISMATCH:
            return {
                "status": STATUS_BLOCKED_MODEL_IDENTITY_MISMATCH,
                "expected_model_fingerprint": self.expected_model_fingerprint,
                "observed_model_fingerprint": self.observed_model_fingerprint,
                "observed_model_path": self.observed_model_path,
            }
        if self.factual_acquisition_status == FACTUAL_BLOCKED:
            return {
                "status": self.status,
                "message": self.message,
                "direction": self.direction,
                "reviewed_declared_row": self.reviewed_declared_row,
                "model_fingerprint": self.observed_model_fingerprint,
                "observed_model_path": self.observed_model_path,
            }
        if (
            self.identity is None
            or self.base_context is None
            or self.evidence_bundle is None
            or self.direction_run is None
        ):
            raise RuntimeError("completed VS-4B execution result is missing required payload")
        run = self.direction_run
        base = self.base_context
        identity = self.identity
        return {
            "status": "OK" if run.regulatory_resolved else "OK_WITH_REGULATORY_BLOCK",
            "FACTUAL_MDEV_MO_ACQUISITION": FACTUAL_PROVEN,
            "REGULATORY_A15_4345": run.status,
            "direction": self.direction,
            "reviewed_declared_row": self.reviewed_declared_row,
            "model_identity": {
                "model_fingerprint": self.observed_model_fingerprint,
                "observed_model_path": identity.model_full_path,
                "program_name": identity.program_name,
                "program_version": identity.program_version,
                "program_api_version": identity.program_api_version,
                "database_units": identity.units.database_units,
                "present_units": identity.units.present_units,
            },
            "reviewed_project_context": {
                "regulatory_base_elevation_m": base.elevation_m,
                "rigid_basement_above_base": base.rigid_basement_above_base,
                "base_review_refs": list(base.review_refs),
                "base_provenance_refs": list(base.provenance_refs),
            },
            "evidence_epoch_id": self.evidence_bundle.evidence_epoch_id,
            "direction_result": run.as_dict(),
            "safety": dict(_SAFETY_PAYLOAD),
        }


def build_vs4b_a15_execution_request(
    *,
    expected_model_fingerprint: str,
    direction: str,
    declared_row: str,
    regulatory_base_elevation_m: float,
    rigid_basement_above_base: bool,
    piers: Sequence[str],
    case_names: Sequence[str],
    reviewed_analysis_method: str,
    scaling_state_id: str,
    result_operator_id: str,
    wall_to_total_sign_factor: int,
    population_mapping_review_refs: Sequence[str],
    dts: str,
    bys: int,
    assumed_row: str,
    assumed_r: float,
    assumed_d: float,
    base_review_refs: Sequence[str],
    base_provenance_refs: Sequence[str],
    wall_review_refs: Sequence[str],
    wall_provenance_refs: Sequence[str],
    result_review_refs: Sequence[str],
    result_provenance_refs: Sequence[str],
    declaration_review_refs: Sequence[str],
    declaration_provenance_refs: Sequence[str],
    seismic_review_refs: Sequence[str],
    seismic_provenance_refs: Sequence[str],
    analysis_evidence_refs: Sequence[str],
    analysis_provenance_refs: Sequence[str],
) -> VS4BA15ExecutionRequest:
    """Build a request while validating only declaration semantics eagerly."""
    declaration = ReviewedDirectionalRcSystemDeclaration(
        direction=direction,
        table_4_1_row=declared_row,
        review_refs=tuple(declaration_review_refs),
        provenance_refs=tuple(declaration_provenance_refs),
    )
    return VS4BA15ExecutionRequest(
        expected_model_fingerprint=expected_model_fingerprint,
        declaration=declaration,
        regulatory_base_elevation_m=regulatory_base_elevation_m,
        rigid_basement_above_base=rigid_basement_above_base,
        piers=tuple(piers),
        case_names=tuple(case_names),
        reviewed_analysis_method=reviewed_analysis_method,
        scaling_state_id=scaling_state_id,
        result_operator_id=result_operator_id,
        wall_to_total_sign_factor=wall_to_total_sign_factor,
        population_mapping_review_refs=tuple(population_mapping_review_refs),
        dts=dts,
        bys=bys,
        assumed_row=assumed_row,
        assumed_r=assumed_r,
        assumed_d=assumed_d,
        base_review_refs=tuple(base_review_refs),
        base_provenance_refs=tuple(base_provenance_refs),
        wall_review_refs=tuple(wall_review_refs),
        wall_provenance_refs=tuple(wall_provenance_refs),
        result_review_refs=tuple(result_review_refs),
        result_provenance_refs=tuple(result_provenance_refs),
        seismic_review_refs=tuple(seismic_review_refs),
        seismic_provenance_refs=tuple(seismic_provenance_refs),
        analysis_evidence_refs=tuple(analysis_evidence_refs),
        analysis_provenance_refs=tuple(analysis_provenance_refs),
    )


def execute_live_vs4b_a15(request: VS4BA15ExecutionRequest) -> VS4BA15ExecutionResult:
    """Execute the accepted bounded live A15 path through one package authority."""
    if not isinstance(request, VS4BA15ExecutionRequest):
        raise TypeError("request must be VS4BA15ExecutionRequest")
    declaration = request.declaration
    direction = request.direction
    if declaration.table_4_1_row != "A15":
        return VS4BA15ExecutionResult(
            status=STATUS_PROVEN_NOT_APPLICABLE,
            factual_acquisition_status=FACTUAL_NOT_REQUIRED,
            direction=direction,
            reviewed_declared_row=declaration.table_4_1_row,
            exit_code=0,
        )
    attach = attach_to_running_etabs()
    if attach.status != ATTACH_STATUS_ATTACHED:
        return VS4BA15ExecutionResult(
            status=STATUS_BLOCKED_BY_LIVE_ETABS_ATTACH,
            factual_acquisition_status=FACTUAL_NOT_ACQUIRED,
            direction=direction,
            reviewed_declared_row=declaration.table_4_1_row,
            exit_code=3,
            attach_attempts=tuple(item.as_dict() for item in attach.attempts),
        )
    identity = read_session_identity(
        attach.etabs_object,
        attach.sap_model,
        attach_strategy=attach.strategy,
    )
    model_fingerprint = model_fingerprint_from_path(identity.model_full_path)
    if model_fingerprint != request.expected_model_fingerprint:
        return VS4BA15ExecutionResult(
            status=STATUS_BLOCKED_MODEL_IDENTITY_MISMATCH,
            factual_acquisition_status=FACTUAL_NOT_ACQUIRED,
            direction=direction,
            reviewed_declared_row=declaration.table_4_1_row,
            exit_code=2,
            identity=identity,
            expected_model_fingerprint=request.expected_model_fingerprint,
            observed_model_fingerprint=model_fingerprint,
            observed_model_path=identity.model_full_path,
        )
    try:
        base = ReviewedRegulatoryBaseContext(
            elevation_m=request.regulatory_base_elevation_m,
            rigid_basement_above_base=request.rigid_basement_above_base,
            review_refs=request.base_review_refs,
            provenance_refs=request.base_provenance_refs,
        )
        wall = ReviewedDirectionalWallPopulation(
            direction=direction,
            pier_refs=request.piers,
            review_refs=request.wall_review_refs,
            provenance_refs=request.wall_provenance_refs,
        )
        result_context = ReviewedResultPopulationContext(
            analysis_method=ReviewedAnalysisMethod(request.reviewed_analysis_method),
            scaling_state_id=request.scaling_state_id,
            result_operator_id=request.result_operator_id,
            wall_to_total_sign_factor=request.wall_to_total_sign_factor,
            review_refs=request.result_review_refs,
            provenance_refs=request.result_provenance_refs,
            population_mapping_review_refs=request.population_mapping_review_refs,
        )
        bundle = capture_live_mdev_mo_evidence(
            database_tables=attach.sap_model.DatabaseTables,
            model_fingerprint=model_fingerprint,
            direction=direction,
            base_context=base,
            wall_population=wall,
            result_context=result_context,
            case_names=request.case_names,
        )
    except (MdevMoEvidenceError, ValueError, TypeError) as exc:
        return VS4BA15ExecutionResult(
            status=getattr(exc, "status", STATUS_BLOCKED_MDEV_MO_FACTUAL_ACQUISITION),
            factual_acquisition_status=FACTUAL_BLOCKED,
            direction=direction,
            reviewed_declared_row=declaration.table_4_1_row,
            exit_code=4,
            identity=identity,
            expected_model_fingerprint=request.expected_model_fingerprint,
            observed_model_fingerprint=model_fingerprint,
            observed_model_path=identity.model_full_path,
            message=str(exc),
        )
    seismic = ReviewedSeismicClassificationContext(
        dts=request.dts,
        bys=request.bys,
        review_refs=request.seismic_review_refs,
        provenance_refs=request.seismic_provenance_refs,
    )
    assumption = DirectionalAnalysisSystemAssumption(
        direction=direction,
        assumed_table_4_1_row=request.assumed_row,
        assumed_r=request.assumed_r,
        assumed_d=request.assumed_d,
        analysis_evidence_refs=request.analysis_evidence_refs,
        provenance_refs=request.analysis_provenance_refs,
    )
    run = run_vs4b_a15_direction(
        declaration=declaration,
        seismic=seismic,
        analysis_assumption=assumption,
        evidence=bundle.direction(direction),
    )
    return VS4BA15ExecutionResult(
        status=run.status,
        factual_acquisition_status=FACTUAL_PROVEN,
        direction=direction,
        reviewed_declared_row=declaration.table_4_1_row,
        exit_code=0,
        identity=identity,
        expected_model_fingerprint=request.expected_model_fingerprint,
        observed_model_fingerprint=model_fingerprint,
        observed_model_path=identity.model_full_path,
        base_context=base,
        evidence_bundle=bundle,
        direction_run=run,
    )


__all__ = [
    "FACTUAL_BLOCKED",
    "FACTUAL_NOT_ACQUIRED",
    "FACTUAL_NOT_REQUIRED",
    "FACTUAL_PROVEN",
    "ReviewedAnalysisMethod",
    "STATUS_BLOCKED_BY_LIVE_ETABS_ATTACH",
    "STATUS_BLOCKED_MDEV_MO_FACTUAL_ACQUISITION",
    "STATUS_BLOCKED_MODEL_IDENTITY_MISMATCH",
    "VS4BA15ExecutionRequest",
    "VS4BA15ExecutionResult",
    "build_vs4b_a15_execution_request",
    "execute_live_vs4b_a15",
]
