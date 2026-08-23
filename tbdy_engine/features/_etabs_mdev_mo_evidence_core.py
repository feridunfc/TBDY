"""Read-only factual MDEV/Mo evidence acquisition for bounded VS-4B-A.

This module is deliberately non-regulatory.  It preserves exact ETABS table
populations, proves case identity from factual OutputCase fields, reconciles a
reviewed project base, performs the reviewed local-to-global mechanics
projection, and emits a fail-closed evidence contract.  It never decides the
TBDY §4.3.4.5 alphaM branch.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import json
import math
from typing import Any

from tbdy_engine.etabs.safety import RuntimeCaptureStatus, process_local_acquisition_lock
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.etabs_display_table_fetcher import (
    fetch_display_table,
    fetch_display_table_for_output,
)

BASE_REACTIONS_TABLE = "Base Reactions"
PIER_FORCES_TABLE = "Pier Forces"
STORY_FORCES_TABLE = "Story Forces"
PIER_SECTIONS_TABLE = "Pier Section Properties"
PIER_LABELS_TABLE = "Area Assignments - Pier Labels"

BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH = (
    "BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH"
)
BLOCKED_RESULT_OPERATOR_AMBIGUITY = "BLOCKED_RESULT_OPERATOR_AMBIGUITY"
BLOCKED_MO_RECONCILIATION = "BLOCKED_MO_RECONCILIATION"
BLOCKED_REGULATORY_BASE_RECONCILIATION = "BLOCKED_REGULATORY_BASE_RECONCILIATION"
BLOCKED_REVIEWED_WALL_POPULATION_RECONCILIATION = (
    "BLOCKED_REVIEWED_WALL_POPULATION_RECONCILIATION"
)
BLOCKED_FACTUAL_OUTPUT_CASE_IDENTITY = "BLOCKED_FACTUAL_OUTPUT_CASE_IDENTITY"
BLOCKED_NON_FULL_ETABS_CAPTURE = "BLOCKED_NON_FULL_ETABS_CAPTURE"
BLOCKED_RESULT_POPULATION_IDENTITY = "BLOCKED_RESULT_POPULATION_IDENTITY"
BLOCKED_RIGID_BASEMENT_TREATMENT_OUT_OF_SCOPE = "BLOCKED_RIGID_BASEMENT_TREATMENT_OUT_OF_SCOPE"

DEFAULT_BASE_TOLERANCE_M = 1e-9
DEFAULT_MOMENT_RECONCILIATION_REL_TOL = 1e-8
DEFAULT_MOMENT_RECONCILIATION_ABS_TOL = 1e-8


class ReviewedAnalysisMethod(StrEnum):
    MODAL_COMBINATION = "MODAL_COMBINATION"


class FactualResultPopulationMethod(StrEnum):
    LINEAR_STATIC = "LINEAR_STATIC"
    MODAL_COMBINATION = "MODAL_COMBINATION"
    UNKNOWN = "UNKNOWN"


class MdevMoEvidenceError(RuntimeError):
    status = "BLOCKED_MDEV_MO_EVIDENCE"

    def __init__(self, message: str, *, status: str | None = None) -> None:
        super().__init__(message)
        if status is not None:
            self.status = status


class MdevMoEvidenceBlockedError(MdevMoEvidenceError):
    pass


def _refs(values: Sequence[str], label: str, *, required: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{label} must be a sequence of strings")
    out = tuple(values)
    if required and not out:
        raise ValueError(f"{label} requires at least one reviewed reference")
    if any(not isinstance(item, str) or not item.strip() or item != item.strip() for item in out):
        raise ValueError(f"{label} contains an invalid reference")
    if len(out) != len(set(out)):
        raise ValueError(f"{label} contains duplicate references")
    return tuple(sorted(out))


def _direction(value: str) -> str:
    if value not in {"X", "Y"}:
        raise ValueError("direction must be X or Y")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{label} must be numeric")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value).strip().replace(",", "."))
        except Exception as exc:
            raise ValueError(f"{label} must be finite numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite numeric")
    return number


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank exact string")
    return value


def _capture_status_value(value: object) -> str:
    return value.value if isinstance(value, RuntimeCaptureStatus) else str(value)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            to_jsonable(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ReviewedRegulatoryBaseContext:
    elevation_m: float
    rigid_basement_above_base: bool
    review_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "elevation_m", _finite(self.elevation_m, "elevation_m"))
        if not isinstance(self.rigid_basement_above_base, bool):
            raise TypeError("rigid_basement_above_base must be bool")
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "base review_refs"))
        object.__setattr__(
            self, "provenance_refs", _refs(self.provenance_refs, "base provenance_refs")
        )


@dataclass(frozen=True, slots=True)
class ReviewedDirectionalWallPopulation:
    direction: str
    pier_refs: tuple[str, ...]
    review_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "direction", _direction(self.direction))
        refs = tuple(_nonblank(item, "pier_ref") for item in self.pier_refs)
        if not refs:
            raise ValueError("pier_refs requires at least one reviewed pier")
        if len(refs) != len(set(refs)):
            raise ValueError("pier_refs contains duplicates")
        object.__setattr__(self, "pier_refs", tuple(sorted(refs)))
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "wall review_refs"))
        object.__setattr__(
            self, "provenance_refs", _refs(self.provenance_refs, "wall provenance_refs")
        )


@dataclass(frozen=True, slots=True)
class ReviewedResultPopulationContext:
    analysis_method: ReviewedAnalysisMethod
    scaling_state_id: str
    result_operator_id: str
    wall_to_total_sign_factor: int
    review_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    population_mapping_review_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.analysis_method, ReviewedAnalysisMethod):
            raise TypeError("analysis_method must be ReviewedAnalysisMethod")
        object.__setattr__(self, "scaling_state_id", _nonblank(self.scaling_state_id, "scaling_state_id"))
        object.__setattr__(self, "result_operator_id", _nonblank(self.result_operator_id, "result_operator_id"))
        if self.wall_to_total_sign_factor not in (-1, 1):
            raise ValueError("wall_to_total_sign_factor must be exactly -1 or +1")
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "result review_refs"))
        object.__setattr__(
            self, "provenance_refs", _refs(self.provenance_refs, "result provenance_refs")
        )
        object.__setattr__(
            self,
            "population_mapping_review_refs",
            _refs(
                self.population_mapping_review_refs,
                "population_mapping_review_refs",
                required=False,
            ),
        )


@dataclass(frozen=True, slots=True)
class ExactOutputCaseCapture:
    table_key: str
    actual_table_name: str
    requested_case: str
    return_code: int | None
    reported_row_count: int | None
    captured_row_count: int
    capture_status: str
    fetched_rows: tuple[Mapping[str, object], ...]
    exact_rows: tuple[Mapping[str, object], ...]
    selection_snapshot: Mapping[str, object]
    restore_result: Mapping[str, object]
    restore_exact_equality_result: bool
    state_diagnostics: tuple[Mapping[str, object], ...]

    @property
    def exact_target_row_count(self) -> int:
        return len(self.exact_rows)

    @property
    def excluded_non_target_row_count(self) -> int:
        return self.captured_row_count - self.exact_target_row_count

    def metadata_payload(self) -> dict[str, object]:
        return {
            "table_key": self.table_key,
            "actual_table_name": self.actual_table_name,
            "requested_case": self.requested_case,
            "return_code": self.return_code,
            "reported_row_count": self.reported_row_count,
            "captured_row_count": self.captured_row_count,
            "capture_status": self.capture_status,
            "exact_target_row_count": self.exact_target_row_count,
            "excluded_non_target_row_count": self.excluded_non_target_row_count,
            "output_identity_field": "OutputCase",
            "selection_snapshot": dict(self.selection_snapshot),
            "restore_result": dict(self.restore_result),
            "restore_exact_equality_result": self.restore_exact_equality_result,
            "state_diagnostics": [dict(item) for item in self.state_diagnostics],
        }

    def evidence_payload(self) -> dict[str, object]:
        return {
            **self.metadata_payload(),
            "fetched_full_superset_rows": [dict(item) for item in self.fetched_rows],
            "exact_target_rows": [dict(item) for item in self.exact_rows],
        }


@dataclass(frozen=True, slots=True)
class StaticTableCapture:
    table_key: str
    actual_table_name: str
    return_code: int | None
    reported_row_count: int | None
    captured_row_count: int
    capture_status: str
    rows: tuple[Mapping[str, object], ...]

    def metadata_payload(self) -> dict[str, object]:
        return {
            "table_key": self.table_key,
            "actual_table_name": self.actual_table_name,
            "return_code": self.return_code,
            "reported_row_count": self.reported_row_count,
            "captured_row_count": self.captured_row_count,
            "capture_status": self.capture_status,
        }

    def evidence_payload(self) -> dict[str, object]:
        return {**self.metadata_payload(), "rows": [dict(item) for item in self.rows]}


@dataclass(frozen=True, slots=True)
class WallMomentProjection:
    story: str
    pier: str
    case_name: str
    axis_angle_deg: float
    local_m2: float
    local_m3: float
    global_mx: float
    global_my: float
    selected_component: str
    selected_signed_value: float
    aligned_signed_value: float
    source_refs: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "story": self.story,
            "pier": self.pier,
            "case_name": self.case_name,
            "axis_angle_deg": self.axis_angle_deg,
            "local_m2": self.local_m2,
            "local_m3": self.local_m3,
            "global_mx": self.global_mx,
            "global_my": self.global_my,
            "selected_component": self.selected_component,
            "selected_signed_value": self.selected_signed_value,
            "aligned_signed_value": self.aligned_signed_value,
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True, slots=True)
class CaseMdevMoEvidence:
    direction: str
    case_name: str
    factual_case_type: str
    factual_result_method: FactualResultPopulationMethod
    base_story: str
    selected_mo_component: str
    signed_sum_mdev: float
    story_force_mo: float
    base_reaction_mo: float
    base_reaction_reference_xyz: tuple[float, float, float]
    wall_projections: tuple[WallMomentProjection, ...]
    evidence_refs: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "direction": self.direction,
            "case_name": self.case_name,
            "factual_case_type": self.factual_case_type,
            "factual_result_method": self.factual_result_method.value,
            "base_story": self.base_story,
            "selected_mo_component": self.selected_mo_component,
            "signed_sum_mdev": self.signed_sum_mdev,
            "story_force_mo": self.story_force_mo,
            "base_reaction_mo": self.base_reaction_mo,
            "base_reaction_reference_xyz": list(self.base_reaction_reference_xyz),
            "wall_projections": [item.as_dict() for item in self.wall_projections],
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class DirectionalMdevMoEvidence:
    direction: str
    evidence_epoch_id: str
    model_fingerprint: str
    reviewed_base_elevation_m: float
    rigid_basement_above_base: bool
    reviewed_analysis_method: ReviewedAnalysisMethod
    scaling_state_id: str
    result_operator_id: str
    reviewed_piers: tuple[str, ...]
    cases: tuple[CaseMdevMoEvidence, ...]
    compatibility: Mapping[str, bool]
    regulatory_ready: bool
    blocking_status: str | None
    review_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "direction": self.direction,
            "evidence_epoch_id": self.evidence_epoch_id,
            "model_fingerprint": self.model_fingerprint,
            "reviewed_base_elevation_m": self.reviewed_base_elevation_m,
            "rigid_basement_above_base": self.rigid_basement_above_base,
            "reviewed_analysis_method": self.reviewed_analysis_method.value,
            "scaling_state_id": self.scaling_state_id,
            "result_operator_id": self.result_operator_id,
            "reviewed_piers": list(self.reviewed_piers),
            "cases": [item.as_dict() for item in self.cases],
            "compatibility": dict(self.compatibility),
            "regulatory_ready": self.regulatory_ready,
            "blocking_status": self.blocking_status,
            "review_refs": list(self.review_refs),
            "provenance_refs": list(self.provenance_refs),
        }

    def regulatory_payload(self) -> dict[str, object]:
        if not self.regulatory_ready:
            raise MdevMoEvidenceBlockedError(
                self.blocking_status or "MDEV/Mo evidence is not regulatory-ready",
                status=self.blocking_status or "BLOCKED_MDEV_MO_EVIDENCE",
            )
        return {
            "direction": self.direction,
            "regulatory_ready": True,
            "blocking_status": None,
            "analysis_method": self.reviewed_analysis_method.value,
            "scaling_state_id": self.scaling_state_id,
            "result_operator_id": self.result_operator_id,
            "compatibility": dict(self.compatibility),
            "cases": tuple(
                {
                    "case_name": item.case_name,
                    "sum_mdev": item.signed_sum_mdev,
                    "mo": item.story_force_mo,
                }
                for item in self.cases
            ),
        }


@dataclass(frozen=True, slots=True)
class LiveMdevMoEvidenceBundle:
    evidence_epoch_id: str
    model_fingerprint: str
    directions: tuple[DirectionalMdevMoEvidence, ...]
    base_reaction_captures: tuple[ExactOutputCaseCapture, ...]
    pier_force_captures: tuple[ExactOutputCaseCapture, ...]
    story_force_captures: tuple[ExactOutputCaseCapture, ...]
    pier_sections: StaticTableCapture
    pier_labels: StaticTableCapture | None

    def direction(self, direction: str) -> DirectionalMdevMoEvidence:
        direction = _direction(direction)
        for item in self.directions:
            if item.direction == direction:
                return item
        raise KeyError(direction)

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_epoch_id": self.evidence_epoch_id,
            "model_fingerprint": self.model_fingerprint,
            "directions": [item.as_dict() for item in self.directions],
            "captures": {
                "Base Reactions": [item.evidence_payload() for item in self.base_reaction_captures],
                "Pier Forces": [item.evidence_payload() for item in self.pier_force_captures],
                "Story Forces": [item.evidence_payload() for item in self.story_force_captures],
                "Pier Section Properties": self.pier_sections.evidence_payload(),
                "Area Assignments - Pier Labels": (
                    None if self.pier_labels is None else self.pier_labels.evidence_payload()
                ),
            },
        }


def isolate_exact_output_case_rows(
    rows: Sequence[Mapping[str, object]], requested_case: str
) -> tuple[Mapping[str, object], ...]:
    requested_case = _nonblank(requested_case, "requested_case")
    retained: list[Mapping[str, object]] = []
    for index, source in enumerate(rows):
        row = dict(to_jsonable(source))
        value = row.get("OutputCase")
        if not isinstance(value, str) or not value:
            raise MdevMoEvidenceError(
                f"row {index} has no factual OutputCase identity",
                status=BLOCKED_FACTUAL_OUTPUT_CASE_IDENTITY,
            )
        if value == requested_case:
            retained.append(row)
    retained.sort(
        key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return tuple(retained)


def _restore_metadata(fetched: object) -> tuple[dict[str, object], dict[str, object], bool]:
    diagnostics = tuple(dict(to_jsonable(item)) for item in getattr(fetched, "state_diagnostics", ()) or ())
    snapshot = next((item for item in diagnostics if item.get("phase") == "snapshot"), {})
    restore = next(
        (item for item in reversed(diagnostics) if item.get("phase") == "restore_verify"),
        {},
    )
    exact = bool(restore and restore.get("success") is True)
    return dict(snapshot), dict(restore), exact


def capture_exact_output_case_table(
    database_tables: object, table_key: str, requested_case: str
) -> ExactOutputCaseCapture:
    fetched = fetch_display_table_for_output(
        database_tables,
        table_key,
        preferred_output_case=requested_case,
        max_rows=None,
    )
    status = _capture_status_value(fetched.capture_status)
    if status != RuntimeCaptureStatus.FULL.value:
        raise MdevMoEvidenceError(
            f"{table_key}/{requested_case} capture is {status}, not FULL",
            status=BLOCKED_NON_FULL_ETABS_CAPTURE,
        )
    selection = dict(to_jsonable(fetched.display_selection or {}))
    if not selection.get("display_selection_success") or not selection.get("fetch_after_display_selection"):
        raise MdevMoEvidenceError(
            f"{table_key}/{requested_case} temporary output selection was not verified",
            status=BLOCKED_FACTUAL_OUTPUT_CASE_IDENTITY,
        )
    rows = tuple(dict(to_jsonable(row)) for row in fetched.parsed.rows)
    exact = isolate_exact_output_case_rows(rows, requested_case)
    snapshot, restore, restore_exact = _restore_metadata(fetched)
    if not restore_exact:
        raise MdevMoEvidenceError(
            f"{table_key}/{requested_case} output selection restore did not verify exactly",
            status=BLOCKED_FACTUAL_OUTPUT_CASE_IDENTITY,
        )
    return ExactOutputCaseCapture(
        table_key=table_key,
        actual_table_name=str(fetched.parsed.actual_table_name),
        requested_case=requested_case,
        return_code=fetched.parsed.return_code,
        reported_row_count=fetched.parsed.row_count_reported,
        captured_row_count=len(rows),
        capture_status=status,
        fetched_rows=rows,
        exact_rows=exact,
        selection_snapshot=snapshot,
        restore_result=restore,
        restore_exact_equality_result=restore_exact,
        state_diagnostics=tuple(dict(to_jsonable(item)) for item in fetched.state_diagnostics),
    )


def capture_static_table(database_tables: object, table_key: str) -> StaticTableCapture:
    fetched = fetch_display_table(database_tables, table_key, max_rows=None)
    status = _capture_status_value(fetched.capture_status)
    if status != RuntimeCaptureStatus.FULL.value:
        raise MdevMoEvidenceError(
            f"{table_key} capture is {status}, not FULL",
            status=BLOCKED_NON_FULL_ETABS_CAPTURE,
        )
    rows = tuple(dict(to_jsonable(row)) for row in fetched.parsed.rows)
    return StaticTableCapture(
        table_key=table_key,
        actual_table_name=str(fetched.parsed.actual_table_name),
        return_code=fetched.parsed.return_code,
        reported_row_count=fetched.parsed.row_count_reported,
        captured_row_count=len(rows),
        capture_status=status,
        rows=rows,
    )


def project_pier_moments_to_global(
    *, m2: float, m3: float, axis_angle_deg: float
) -> tuple[float, float]:
    """Reviewed mechanics transform: local pier 2/3 moments -> global MX/MY."""
    m2 = _finite(m2, "M2")
    m3 = _finite(m3, "M3")
    theta = math.radians(_finite(axis_angle_deg, "AxisAngle"))
    mx = m2 * math.cos(theta) - m3 * math.sin(theta)
    my = m2 * math.sin(theta) + m3 * math.cos(theta)
    return mx, my


def factual_result_population_method(case_type: str) -> FactualResultPopulationMethod:
    case_type = _nonblank(case_type, "CaseType")
    exact = {
        "LinStatic": FactualResultPopulationMethod.LINEAR_STATIC,
        "LinRespSpec": FactualResultPopulationMethod.MODAL_COMBINATION,
        "Response Spectrum": FactualResultPopulationMethod.MODAL_COMBINATION,
    }
    return exact.get(case_type, FactualResultPopulationMethod.UNKNOWN)


def _exact_case_type(rows: Sequence[Mapping[str, object]], case_name: str) -> str:
    values = {
        _nonblank(row.get("CaseType"), f"{case_name}.CaseType")
        for row in rows
    }
    if len(values) != 1:
        raise MdevMoEvidenceError(
            f"{case_name} does not expose one exact factual CaseType: {sorted(values)}",
            status=BLOCKED_RESULT_POPULATION_IDENTITY,
        )
    return next(iter(values))


def _base_section_rows(
    *,
    pier_sections: Sequence[Mapping[str, object]],
    wall_population: ReviewedDirectionalWallPopulation,
    base_context: ReviewedRegulatoryBaseContext,
    tolerance_m: float,
) -> tuple[str, dict[str, Mapping[str, object]]]:
    matches: dict[str, list[Mapping[str, object]]] = {pier: [] for pier in wall_population.pier_refs}
    for source in pier_sections:
        pier = source.get("Pier")
        if pier not in matches:
            continue
        cgbotz = _finite(source.get("CGBotZ"), f"{pier}.CGBotZ")
        if math.isclose(cgbotz, base_context.elevation_m, rel_tol=0.0, abs_tol=tolerance_m):
            matches[str(pier)].append(source)
    bad = {pier: len(rows) for pier, rows in matches.items() if len(rows) != 1}
    if bad:
        raise MdevMoEvidenceError(
            f"reviewed wall piers do not reconcile one-to-one at reviewed base: {bad}",
            status=BLOCKED_REVIEWED_WALL_POPULATION_RECONCILIATION,
        )
    by_pier = {pier: rows[0] for pier, rows in matches.items()}
    stories = {_nonblank(row.get("Story"), "Pier Section Properties.Story") for row in by_pier.values()}
    if len(stories) != 1:
        raise MdevMoEvidenceError(
            f"reviewed base piers do not resolve to one factual Story: {sorted(stories)}",
            status=BLOCKED_REGULATORY_BASE_RECONCILIATION,
        )
    return next(iter(stories)), by_pier


def _one(
    rows: Sequence[Mapping[str, object]],
    *,
    label: str,
    predicate,
    status: str,
) -> Mapping[str, object]:
    matches = [row for row in rows if predicate(row)]
    if len(matches) != 1:
        raise MdevMoEvidenceError(
            f"{label} expected exactly one factual row, observed {len(matches)}",
            status=status,
        )
    return matches[0]


def _analysis_method_compatible(
    *,
    reviewed: ReviewedResultPopulationContext,
    factual_methods: Sequence[FactualResultPopulationMethod],
) -> bool:
    methods = set(factual_methods)
    if methods == {FactualResultPopulationMethod.MODAL_COMBINATION}:
        return reviewed.analysis_method is ReviewedAnalysisMethod.MODAL_COMBINATION
    if reviewed.analysis_method is ReviewedAnalysisMethod.MODAL_COMBINATION:
        # A factual LinStatic/unknown result population needs an explicit separately
        # reviewed ETABS decomposition/mapping before modal authority can apply.
        return bool(reviewed.population_mapping_review_refs)
    return False


def build_directional_mdev_mo_evidence(
    *,
    direction: str,
    evidence_epoch_id: str,
    model_fingerprint: str,
    case_names: Sequence[str],
    base_context: ReviewedRegulatoryBaseContext,
    wall_population: ReviewedDirectionalWallPopulation,
    result_context: ReviewedResultPopulationContext,
    pier_sections: Sequence[Mapping[str, object]],
    pier_force_rows_by_case: Mapping[str, Sequence[Mapping[str, object]]],
    story_force_rows_by_case: Mapping[str, Sequence[Mapping[str, object]]],
    base_reaction_rows_by_case: Mapping[str, Sequence[Mapping[str, object]]],
    base_tolerance_m: float = DEFAULT_BASE_TOLERANCE_M,
    moment_rel_tol: float = DEFAULT_MOMENT_RECONCILIATION_REL_TOL,
    moment_abs_tol: float = DEFAULT_MOMENT_RECONCILIATION_ABS_TOL,
) -> DirectionalMdevMoEvidence:
    direction = _direction(direction)
    if base_context.rigid_basement_above_base:
        raise MdevMoEvidenceError(
            "rigid-basement upper/lower-zone treatment is outside the bounded VS-4B-A slice",
            status=BLOCKED_RIGID_BASEMENT_TREATMENT_OUT_OF_SCOPE,
        )
    if wall_population.direction != direction:
        raise ValueError("wall population direction mismatch")
    cases = tuple(_nonblank(case, "case_name") for case in case_names)
    if len(cases) != 2 or len(set(cases)) != 2:
        raise ValueError("first VS-4B-A slice requires exactly two exact eccentricity cases")
    base_story, section_by_pier = _base_section_rows(
        pier_sections=pier_sections,
        wall_population=wall_population,
        base_context=base_context,
        tolerance_m=_finite(base_tolerance_m, "base_tolerance_m"),
    )
    selected_component = "MY" if direction == "X" else "MX"
    case_evidence: list[CaseMdevMoEvidence] = []
    factual_methods: list[FactualResultPopulationMethod] = []
    operator_ok = True

    for case_name in cases:
        pier_rows = tuple(pier_force_rows_by_case.get(case_name, ()))
        story_rows = tuple(story_force_rows_by_case.get(case_name, ()))
        base_rows = tuple(base_reaction_rows_by_case.get(case_name, ()))
        if not pier_rows or not story_rows or not base_rows:
            raise MdevMoEvidenceError(
                f"{case_name} factual result population is incomplete",
                status=BLOCKED_RESULT_POPULATION_IDENTITY,
            )
        for row in (*pier_rows, *story_rows, *base_rows):
            if row.get("OutputCase") != case_name:
                raise MdevMoEvidenceError(
                    f"{case_name} contains a row with different factual OutputCase",
                    status=BLOCKED_FACTUAL_OUTPUT_CASE_IDENTITY,
                )
        case_type = _exact_case_type((*pier_rows, *story_rows, *base_rows), case_name)
        method = factual_result_population_method(case_type)
        factual_methods.append(method)

        story_row = _one(
            story_rows,
            label=f"Story Forces {case_name}/{base_story}/Bottom",
            predicate=lambda row: row.get("Story") == base_story and row.get("Location") == "Bottom",
            status=BLOCKED_REGULATORY_BASE_RECONCILIATION,
        )
        base_row = _one(
            base_rows,
            label=f"Base Reactions {case_name}",
            predicate=lambda row: True,
            status=BLOCKED_REGULATORY_BASE_RECONCILIATION,
        )
        base_z = _finite(base_row.get("Z"), f"{case_name}.BaseReaction.Z")
        if not math.isclose(base_z, base_context.elevation_m, rel_tol=0.0, abs_tol=base_tolerance_m):
            raise MdevMoEvidenceError(
                f"{case_name} Base Reactions Z={base_z} != reviewed base {base_context.elevation_m}",
                status=BLOCKED_REGULATORY_BASE_RECONCILIATION,
            )
        story_mo = _finite(story_row.get(selected_component), f"{case_name}.StoryForces.{selected_component}")
        base_mo = _finite(base_row.get(selected_component), f"{case_name}.BaseReactions.{selected_component}")
        if not math.isclose(story_mo, base_mo, rel_tol=moment_rel_tol, abs_tol=moment_abs_tol):
            raise MdevMoEvidenceError(
                f"{case_name} Story Forces {selected_component} does not reconcile with Base Reactions",
                status=BLOCKED_MO_RECONCILIATION,
            )
        if math.isclose(story_mo, 0.0, rel_tol=0.0, abs_tol=moment_abs_tol):
            raise MdevMoEvidenceError(
                f"{case_name} total overturning moment is zero",
                status=BLOCKED_RESULT_OPERATOR_AMBIGUITY,
            )

        projections: list[WallMomentProjection] = []
        for pier in wall_population.pier_refs:
            section = section_by_pier[pier]
            pier_row = _one(
                pier_rows,
                label=f"Pier Forces {case_name}/{base_story}/{pier}/Bottom",
                predicate=lambda row, p=pier: (
                    row.get("Story") == base_story
                    and row.get("Pier") == p
                    and row.get("Location") == "Bottom"
                ),
                status=BLOCKED_REVIEWED_WALL_POPULATION_RECONCILIATION,
            )
            angle = _finite(section.get("AxisAngle"), f"{pier}.AxisAngle")
            m2 = _finite(pier_row.get("M2"), f"{case_name}/{pier}.M2")
            m3 = _finite(pier_row.get("M3"), f"{case_name}/{pier}.M3")
            mx, my = project_pier_moments_to_global(m2=m2, m3=m3, axis_angle_deg=angle)
            selected = my if direction == "X" else mx
            aligned = selected * result_context.wall_to_total_sign_factor
            if not math.isclose(aligned, 0.0, rel_tol=0.0, abs_tol=moment_abs_tol):
                if aligned * story_mo < 0.0:
                    operator_ok = False
            projections.append(
                WallMomentProjection(
                    story=base_story,
                    pier=pier,
                    case_name=case_name,
                    axis_angle_deg=angle,
                    local_m2=m2,
                    local_m3=m3,
                    global_mx=mx,
                    global_my=my,
                    selected_component=selected_component,
                    selected_signed_value=selected,
                    aligned_signed_value=aligned,
                    source_refs=(
                        f"Pier Forces:{case_name}:{base_story}:{pier}:Bottom",
                        f"Pier Section Properties:{base_story}:{pier}",
                    ),
                )
            )
        projections.sort(key=lambda item: item.pier)
        signed_sum = sum(item.aligned_signed_value for item in projections)
        if math.isclose(signed_sum, 0.0, rel_tol=0.0, abs_tol=moment_abs_tol) or signed_sum * story_mo < 0.0:
            operator_ok = False
        case_evidence.append(
            CaseMdevMoEvidence(
                direction=direction,
                case_name=case_name,
                factual_case_type=case_type,
                factual_result_method=method,
                base_story=base_story,
                selected_mo_component=selected_component,
                signed_sum_mdev=signed_sum,
                story_force_mo=story_mo,
                base_reaction_mo=base_mo,
                base_reaction_reference_xyz=(
                    _finite(base_row.get("X"), f"{case_name}.BaseReaction.X"),
                    _finite(base_row.get("Y"), f"{case_name}.BaseReaction.Y"),
                    base_z,
                ),
                wall_projections=tuple(projections),
                evidence_refs=(
                    f"evidence_epoch:{evidence_epoch_id}",
                    f"OutputCase:{case_name}",
                    f"CaseType:{case_type}",
                    f"reviewed_base:{base_context.elevation_m}",
                ),
            )
        )

    method_ok = _analysis_method_compatible(reviewed=result_context, factual_methods=factual_methods)
    compatibility = {
        "mdev_population_resolved": True,
        "mo_resolved": True,
        "same_direction": True,
        "same_regulatory_base": True,
        "analysis_method_compatible": method_ok,
        "same_result_realization": True,
        "same_scaling_state": True,
        "wall_population_complete": True,
        "result_operator_resolved": operator_ok,
    }
    blocking: str | None = None
    if not operator_ok:
        blocking = BLOCKED_RESULT_OPERATOR_AMBIGUITY
    elif not method_ok:
        blocking = BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH
    regulatory_ready = blocking is None
    review_refs = tuple(
        sorted(
            set(
                (*base_context.review_refs, *wall_population.review_refs, *result_context.review_refs,
                 *result_context.population_mapping_review_refs)
            )
        )
    )
    provenance_refs = tuple(
        sorted(
            set(
                (*base_context.provenance_refs, *wall_population.provenance_refs, *result_context.provenance_refs)
            )
        )
    )
    return DirectionalMdevMoEvidence(
        direction=direction,
        evidence_epoch_id=_nonblank(evidence_epoch_id, "evidence_epoch_id"),
        model_fingerprint=_nonblank(model_fingerprint, "model_fingerprint"),
        reviewed_base_elevation_m=base_context.elevation_m,
        rigid_basement_above_base=base_context.rigid_basement_above_base,
        reviewed_analysis_method=result_context.analysis_method,
        scaling_state_id=result_context.scaling_state_id,
        result_operator_id=result_context.result_operator_id,
        reviewed_piers=wall_population.pier_refs,
        cases=tuple(sorted(case_evidence, key=lambda item: item.case_name)),
        compatibility=compatibility,
        regulatory_ready=regulatory_ready,
        blocking_status=blocking,
        review_refs=review_refs,
        provenance_refs=provenance_refs,
    )


def _capture_epoch_id(*, model_fingerprint: str, raw_payload: Mapping[str, object]) -> str:
    digest = hashlib.sha256(
        _canonical_bytes(
            {
                "contract": "VS4B_A15_MDEV_MO_FACTUAL_EPOCH_V1",
                "model_fingerprint": model_fingerprint,
                "raw": raw_payload,
            }
        )
    ).hexdigest()
    return f"epoch:vs4b-mdev-mo:sha256:{digest}"


def capture_live_mdev_mo_evidence(
    *,
    database_tables: object,
    model_fingerprint: str,
    base_context: ReviewedRegulatoryBaseContext,
    wall_populations: Sequence[ReviewedDirectionalWallPopulation],
    result_context: ReviewedResultPopulationContext,
    x_cases: Sequence[str],
    y_cases: Sequence[str],
    include_pier_labels: bool = True,
) -> LiveMdevMoEvidenceBundle:
    """Capture one process-local coherent read-only evidence epoch.

    Output-selection setters are used only inside the repository's reversible
    DatabaseTables transaction owned by ``fetch_display_table_for_output``.
    No analysis, design, save, unit setter or model/property setter is called.
    """
    model_fingerprint = _nonblank(model_fingerprint, "model_fingerprint")
    pops = tuple(wall_populations)
    if len(pops) != 2 or {item.direction for item in pops} != {"X", "Y"}:
        raise ValueError("wall_populations must contain exactly one X and one Y reviewed population")
    pop_by_direction = {item.direction: item for item in pops}
    cases_by_direction = {
        "X": tuple(_nonblank(item, "x case") for item in x_cases),
        "Y": tuple(_nonblank(item, "y case") for item in y_cases),
    }
    if any(len(items) != 2 or len(set(items)) != 2 for items in cases_by_direction.values()):
        raise ValueError("each direction requires exactly two exact eccentricity cases")

    with process_local_acquisition_lock():
        pier_sections = capture_static_table(database_tables, PIER_SECTIONS_TABLE)
        pier_labels: StaticTableCapture | None = None
        if include_pier_labels:
            try:
                candidate = fetch_display_table(database_tables, PIER_LABELS_TABLE, max_rows=None)
                if _capture_status_value(candidate.capture_status) == RuntimeCaptureStatus.FULL.value:
                    pier_labels = StaticTableCapture(
                        table_key=PIER_LABELS_TABLE,
                        actual_table_name=str(candidate.parsed.actual_table_name),
                        return_code=candidate.parsed.return_code,
                        reported_row_count=candidate.parsed.row_count_reported,
                        captured_row_count=len(candidate.parsed.rows),
                        capture_status=_capture_status_value(candidate.capture_status),
                        rows=tuple(dict(to_jsonable(row)) for row in candidate.parsed.rows),
                    )
            except Exception:
                pier_labels = None

        base_captures: list[ExactOutputCaseCapture] = []
        pier_captures: list[ExactOutputCaseCapture] = []
        story_captures: list[ExactOutputCaseCapture] = []
        for direction in ("X", "Y"):
            for case_name in cases_by_direction[direction]:
                base_captures.append(
                    capture_exact_output_case_table(database_tables, BASE_REACTIONS_TABLE, case_name)
                )
                pier_captures.append(
                    capture_exact_output_case_table(database_tables, PIER_FORCES_TABLE, case_name)
                )
                story_captures.append(
                    capture_exact_output_case_table(database_tables, STORY_FORCES_TABLE, case_name)
                )

    raw_for_epoch = {
        "Pier Section Properties": [dict(row) for row in pier_sections.rows],
        "Base Reactions": {
            item.requested_case: [dict(row) for row in item.exact_rows] for item in base_captures
        },
        "Pier Forces": {
            item.requested_case: [dict(row) for row in item.exact_rows] for item in pier_captures
        },
        "Story Forces": {
            item.requested_case: [dict(row) for row in item.exact_rows] for item in story_captures
        },
    }
    evidence_epoch_id = _capture_epoch_id(
        model_fingerprint=model_fingerprint,
        raw_payload=raw_for_epoch,
    )
    base_by_case = {item.requested_case: item.exact_rows for item in base_captures}
    pier_by_case = {item.requested_case: item.exact_rows for item in pier_captures}
    story_by_case = {item.requested_case: item.exact_rows for item in story_captures}
    directions = tuple(
        build_directional_mdev_mo_evidence(
            direction=direction,
            evidence_epoch_id=evidence_epoch_id,
            model_fingerprint=model_fingerprint,
            case_names=cases_by_direction[direction],
            base_context=base_context,
            wall_population=pop_by_direction[direction],
            result_context=result_context,
            pier_sections=pier_sections.rows,
            pier_force_rows_by_case=pier_by_case,
            story_force_rows_by_case=story_by_case,
            base_reaction_rows_by_case=base_by_case,
        )
        for direction in ("X", "Y")
    )
    return LiveMdevMoEvidenceBundle(
        evidence_epoch_id=evidence_epoch_id,
        model_fingerprint=model_fingerprint,
        directions=directions,
        base_reaction_captures=tuple(base_captures),
        pier_force_captures=tuple(pier_captures),
        story_force_captures=tuple(story_captures),
        pier_sections=pier_sections,
        pier_labels=pier_labels,
    )


__all__ = [
    "ReviewedAnalysisMethod",
    "FactualResultPopulationMethod",
    "ReviewedRegulatoryBaseContext",
    "ReviewedDirectionalWallPopulation",
    "ReviewedResultPopulationContext",
    "ExactOutputCaseCapture",
    "StaticTableCapture",
    "WallMomentProjection",
    "CaseMdevMoEvidence",
    "DirectionalMdevMoEvidence",
    "LiveMdevMoEvidenceBundle",
    "MdevMoEvidenceError",
    "MdevMoEvidenceBlockedError",
    "BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH",
    "BLOCKED_RESULT_OPERATOR_AMBIGUITY",
    "BLOCKED_MO_RECONCILIATION",
    "BLOCKED_REGULATORY_BASE_RECONCILIATION",
    "BLOCKED_REVIEWED_WALL_POPULATION_RECONCILIATION",
    "BLOCKED_FACTUAL_OUTPUT_CASE_IDENTITY",
    "BLOCKED_NON_FULL_ETABS_CAPTURE",
    "BLOCKED_RESULT_POPULATION_IDENTITY",
    "BLOCKED_RIGID_BASEMENT_TREATMENT_OUT_OF_SCOPE",
    "isolate_exact_output_case_rows",
    "capture_exact_output_case_table",
    "capture_static_table",
    "project_pier_moments_to_global",
    "factual_result_population_method",
    "build_directional_mdev_mo_evidence",
    "capture_live_mdev_mo_evidence",
]
