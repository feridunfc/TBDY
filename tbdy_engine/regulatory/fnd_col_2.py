"""F0.9 source-bound seam for FND-COL-2 column demand readiness.

Accepted VS6 engineering kernels remain the calculation authority. This module
only adapts immutable F0 external authorities into those kernels and emits one
canonical ``RegulatoryQuantity``. It does not acquire ETABS data, implement a
second stability engine, perform PMM mechanics, or select reinforcement.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Mapping, Sequence

from tbdy_engine.design.columns.column_design_demand_engine import ColumnComboDefinition
from tbdy_engine.design.columns.column_design_readiness import (
    ColumnDesignDemandReadiness,
    ColumnStateSlendernessBasis,
    resolve_column_design_demand_readiness,
)
from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent
from tbdy_engine.design.columns.moment_magnification import ColumnMomentMagnificationAxisBasis
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.slenderness import ColumnSlendernessAxisBasis, ColumnSlendernessBasis
from tbdy_engine.design.columns.slenderness_basis import (
    ColumnSlendernessAxisEvidence,
    ColumnSlendernessEvidence,
)
from tbdy_engine.design.columns.stability_stiffness_basis import (
    AssignedFrameBendingModifierEvidence,
    assess_ts500_eq713_stiffness_basis,
)
from tbdy_engine.regulatory.contracts import (
    ApplicabilityBinding,
    ApplicabilityState,
    AvailabilityState,
    DependencyKey,
    DependencySourceKind,
    DependencySpec,
    DerivationEvaluatorBinding,
    DirectionPolicy,
    Grain,
    PhysicalDimension,
    PopulationRequirement,
    RegulatoryDerivationSpec,
    RegulatoryOutputContract,
    RegulatoryQuantity,
    RuleId,
    ScopePolicy,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import MaterializedDependency, RuleExecutionEnvelope
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_MM

RULE_ID = RuleId("FND_COL_2_COLUMN_DESIGN_DEMAND_READINESS")
RULE_VERSION = "fnd-col-2-v1"
CODE_REFS = (
    "TS 500 6.3.10 Eq.6.16",
    "TS 500 7.6.1",
    "TS 500 7.6.2.1 Eq.7.13",
    "TS 500 7.6.2.2 Eq.7.14-7.16",
    "TS 500 7.6.2.3 Eq.7.17-7.18",
    "TS 500 7.6.2.4-7.6.2.6 Eq.7.19-7.29",
)

WIDTH_MM_KEY = DependencyKey("fnd_col_2_column_width_mm")
DEPTH_MM_KEY = DependencyKey("fnd_col_2_column_depth_mm")
COMBO_DEFINITIONS_KEY = DependencyKey("fnd_col_2_combo_definitions")
CASE_DEMANDS_KEY = DependencyKey("fnd_col_2_case_demand_population")
SLENDERNESS_EVIDENCE_KEY = DependencyKey("fnd_col_2_slenderness_evidence")
STIFFNESS_EVIDENCE_KEY = DependencyKey("fnd_col_2_stability_stiffness_evidence")
READINESS_KEY = DependencyKey("fnd_col_2_column_design_demand_readiness")


@dataclass(frozen=True, slots=True)
class ColumnDesignReadinessApplicabilityInput:
    reinforced_concrete_column: bool | None


def _applicability(value: ColumnDesignReadinessApplicabilityInput) -> ApplicabilityState:
    if not isinstance(value, ColumnDesignReadinessApplicabilityInput):
        raise TypeError("FND-COL-2 applicability requires ColumnDesignReadinessApplicabilityInput")
    if value.reinforced_concrete_column is None:
        return ApplicabilityState.UNRESOLVED
    return ApplicabilityState.APPLIES if value.reinforced_concrete_column else ApplicabilityState.PROVEN_NOT_APPLICABLE


_TypedReadinessCapture = list[tuple[RuleExecutionEnvelope, ColumnDesignDemandReadiness, tuple[str, ...]]]
_TYPED_READINESS_CAPTURE: ContextVar[_TypedReadinessCapture | None] = ContextVar(
    "fnd_col_2_typed_readiness_capture", default=None
)


@contextmanager
def _capture_typed_readiness_execution() -> Iterator[_TypedReadinessCapture]:
    captured: _TypedReadinessCapture = []
    token = _TYPED_READINESS_CAPTURE.set(captured)
    try:
        yield captured
    finally:
        _TYPED_READINESS_CAPTURE.reset(token)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _sequence(value: object, label: str) -> tuple[object, ...]:
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{label} must be a sequence")
    return tuple(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TypeError(f"{label} must be a nonblank canonical string")
    return value


def _optional_text(value: object, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    return float(value)


def _optional_number(value: object, label: str) -> float | None:
    return None if value is None else _number(value, label)


def _optional_bool(value: object, label: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if type(value) is not bool:
        raise TypeError(f"{label} must be bool")
    return value


def _required_bool(row: Mapping[str, object], key: str) -> bool:
    if key not in row:
        raise TypeError(f"{key} must be explicitly source-bound; missing values cannot default")
    value = row[key]
    if type(value) is not bool:
        raise TypeError(f"{key} must be bool")
    return value


def _decode_combo_definitions(value: object) -> tuple[ColumnComboDefinition, ...]:
    definitions: list[ColumnComboDefinition] = []
    for index, raw in enumerate(_sequence(value, "combo definitions")):
        row = _mapping(raw, f"combo[{index}]")
        terms = tuple(
            ComboPatternConstituent(
                name=_text(term.get("name"), "constituent.name"),
                scale_factor=_number(term.get("scale_factor"), "constituent.scale_factor"),
                cname_type=_text(term.get("cname_type", "LOAD_CASE"), "constituent.cname_type"),
            )
            for term in (
                _mapping(item, f"combo[{index}].constituent")
                for item in _sequence(row.get("constituents"), f"combo[{index}].constituents")
            )
        )
        definitions.append(
            ColumnComboDefinition(
                name=_text(row.get("name"), "combo.name"),
                combo_type=_text(row.get("combo_type"), "combo.combo_type"),
                constituents=terms,
            )
        )
    return tuple(definitions)


def _decode_demand_states(value: object, *, component_id: str, label: str = "case demand population") -> tuple[ColumnDemandState, ...]:
    states: list[ColumnDemandState] = []
    for index, raw in enumerate(_sequence(value, label)):
        row = _mapping(raw, f"{label}[{index}]")
        state = ColumnDemandState(
            state_id=_text(row.get("state_id"), "state_id"),
            component_id=_text(row.get("component_id"), "component_id"),
            output_case=_text(row.get("output_case"), "output_case"),
            case_type=_text(row.get("case_type"), "case_type"),
            step_type=_optional_text(row.get("step_type"), "step_type"),
            step_number=_optional_text(row.get("step_number"), "step_number"),
            station_m=_number(row.get("station_m"), "station_m"),
            end_tag=_text(row.get("end_tag"), "end_tag"),
            nd_compression_n=_number(row.get("nd_compression_n"), "nd_compression_n"),
            m2_nmm=_number(row.get("m2_nmm"), "m2_nmm"),
            m3_nmm=_number(row.get("m3_nmm"), "m3_nmm"),
            source_identity=_text(row.get("source_identity"), "source_identity"),
        )
        if state.component_id != component_id:
            raise ValueError(f"{label} component_id differs from F0 scope_ref")
        states.append(state)
    return tuple(states)


def _decode_axis(value: object, expected_axis: str) -> ColumnSlendernessAxisEvidence:
    row = _mapping(value, f"slenderness.{expected_axis}")
    axis = _text(row.get("axis"), "slenderness.axis")
    if axis != expected_axis:
        raise ValueError(f"expected slenderness axis {expected_axis}")
    return ColumnSlendernessAxisEvidence(
        axis=axis,
        section_dimension_mm=_number(row.get("section_dimension_mm"), "section_dimension_mm"),
        factual_clear_length_candidate_mm=_optional_number(row.get("factual_clear_length_candidate_mm"), "factual_clear_length_candidate_mm"),
        factual_clear_length_source_ref=_optional_text(row.get("factual_clear_length_source_ref"), "factual_clear_length_source_ref"),
        factual_clear_length_authority=_optional_text(row.get("factual_clear_length_authority"), "factual_clear_length_authority"),
        regulatory_free_length_ln_mm=_optional_number(row.get("regulatory_free_length_ln_mm"), "regulatory_free_length_ln_mm"),
        regulatory_free_length_source_ref=_optional_text(row.get("regulatory_free_length_source_ref"), "regulatory_free_length_source_ref"),
        regulatory_free_length_authority=_optional_text(row.get("regulatory_free_length_authority"), "regulatory_free_length_authority"),
        sway_classification=_optional_text(row.get("sway_classification"), "sway_classification"),
        sway_source_ref=_optional_text(row.get("sway_source_ref"), "sway_source_ref"),
        sway_authority=_optional_text(row.get("sway_authority"), "sway_authority"),
        effective_length_factor_k=_optional_number(row.get("effective_length_factor_k"), "effective_length_factor_k"),
        effective_length_source_ref=_optional_text(row.get("effective_length_source_ref"), "effective_length_source_ref"),
        effective_length_authority=_optional_text(row.get("effective_length_authority"), "effective_length_authority"),
        moment_ratio_m1_over_m2=_optional_number(row.get("moment_ratio_m1_over_m2"), "moment_ratio_m1_over_m2"),
        moment_ratio_source_ref=_optional_text(row.get("moment_ratio_source_ref"), "moment_ratio_source_ref"),
        moment_ratio_authority=_optional_text(row.get("moment_ratio_authority"), "moment_ratio_authority"),
        allow_conservative_braced_ratio=bool(row.get("allow_conservative_braced_ratio", True)),
    )


def _canonical_second_order_root(value: object) -> Mapping[str, object] | None:
    if value is None:
        return None
    root = _mapping(value, "slenderness evidence")
    raw = root.get("canonical_second_order")
    return None if raw is None else _mapping(raw, "canonical_second_order")


def _decode_slenderness(value: object, *, component_id: str) -> ColumnSlendernessEvidence | None:
    if value is None:
        return None
    row = _mapping(value, "slenderness evidence")
    encoded_component = _text(row.get("component_id"), "slenderness.component_id")
    if encoded_component != component_id:
        raise ValueError("slenderness evidence component_id differs from F0 scope_ref")
    if row.get("canonical_second_order") is not None:
        return None
    return ColumnSlendernessEvidence(
        component_id=encoded_component,
        m2=_decode_axis(row.get("m2"), "M2"),
        m3=_decode_axis(row.get("m3"), "M3"),
        source_refs=tuple(
            _text(item, "slenderness.source_ref")
            for item in _sequence(row.get("source_refs"), "slenderness.source_refs")
        ),
    )


def _decode_axis_basis(value: object, expected_axis: str) -> ColumnSlendernessAxisBasis:
    row = _mapping(value, f"state_slenderness.{expected_axis}")
    axis = _text(row.get("axis"), "state_slenderness.axis")
    if axis != expected_axis:
        raise ValueError(f"expected state slenderness axis {expected_axis}")
    return ColumnSlendernessAxisBasis(
        axis=axis,
        section_dimension_mm=_number(row.get("section_dimension_mm"), "section_dimension_mm"),
        free_length_ln_mm=_number(row.get("free_length_ln_mm"), "free_length_ln_mm"),
        effective_length_factor_k=_number(row.get("effective_length_factor_k"), "effective_length_factor_k"),
        sway_classification=_text(row.get("sway_classification"), "sway_classification"),
        moment_ratio_m1_over_m2=_optional_number(row.get("moment_ratio_m1_over_m2"), "moment_ratio_m1_over_m2"),
        source_refs=tuple(
            _text(item, "state_slenderness.axis.source_ref")
            for item in _sequence(row.get("source_refs"), "state_slenderness.axis.source_refs")
        ),
        free_length_authority=_text(row.get("free_length_authority", "TS500_REGULATORY_FREE_LENGTH"), "free_length_authority"),
        effective_length_authority=_text(row.get("effective_length_authority", "TS500_EFFECTIVE_LENGTH_FACTOR"), "effective_length_authority"),
        sway_authority=_text(row.get("sway_authority", "TS500_SWAY_CLASSIFICATION"), "sway_authority"),
        moment_ratio_authority=_text(row.get("moment_ratio_authority", "TS500_END_MOMENT_RATIO"), "moment_ratio_authority"),
    )


def _decode_state_slenderness_bases(value: object, *, component_id: str) -> tuple[ColumnStateSlendernessBasis, ...]:
    root = _canonical_second_order_root(value)
    if root is None:
        return ()
    raw_rows = root.get("state_slenderness_bases")
    if raw_rows is None:
        return ()
    result: list[ColumnStateSlendernessBasis] = []
    for index, raw in enumerate(_sequence(raw_rows, "state_slenderness_bases")):
        row = _mapping(raw, f"state_slenderness_bases[{index}]")
        encoded_component = _text(row.get("component_id"), "state_slenderness.component_id")
        if encoded_component != component_id:
            raise ValueError("state slenderness component_id differs from F0 scope_ref")
        basis = ColumnSlendernessBasis(
            component_id=encoded_component,
            m2=_decode_axis_basis(row.get("m2"), "M2"),
            m3=_decode_axis_basis(row.get("m3"), "M3"),
            source_refs=tuple(
                _text(item, "state_slenderness.source_ref")
                for item in _sequence(row.get("source_refs"), "state_slenderness.source_refs")
            ),
        )
        result.append(
            ColumnStateSlendernessBasis(
                output_case=_text(row.get("output_case"), "state_slenderness.output_case"),
                basis=basis,
                source_refs=tuple(
                    _text(item, "state_slenderness.materialization_source_ref")
                    for item in _sequence(
                        row.get("materialization_source_refs", row.get("source_refs")),
                        "state_slenderness.materialization_source_refs",
                    )
                ),
            )
        )
    return tuple(result)


def _decode_moment_magnification_bases(value: object) -> tuple[ColumnMomentMagnificationAxisBasis, ...]:
    if value is None:
        return ()
    root = _mapping(value, "slenderness evidence")
    canonical = _canonical_second_order_root(value)
    raw_bases = (canonical if canonical is not None else root).get("moment_magnification_bases")
    if raw_bases is None:
        return ()
    bases: list[ColumnMomentMagnificationAxisBasis] = []
    for index, raw in enumerate(_sequence(raw_bases, "moment_magnification_bases")):
        row = _mapping(raw, f"moment_magnification_bases[{index}]")
        bases.append(
            ColumnMomentMagnificationAxisBasis(
                demand_state_id=_text(row.get("demand_state_id"), "demand_state_id"),
                axis=_text(row.get("axis"), "axis"),
                sway_classification=_text(row.get("sway_classification"), "sway_classification"),
                nd_compression_n=_number(row.get("nd_compression_n"), "nd_compression_n"),
                m1_over_m2=_number(row.get("m1_over_m2"), "m1_over_m2"),
                effective_length_lk_mm=_number(row.get("effective_length_lk_mm"), "effective_length_lk_mm"),
                radius_i_mm=_number(row.get("radius_i_mm"), "radius_i_mm"),
                ec_mpa=_number(row.get("ec_mpa"), "ec_mpa"),
                ic_mm4=_number(row.get("ic_mm4"), "ic_mm4"),
                creep_ratio_rm=_number(row.get("creep_ratio_rm"), "creep_ratio_rm"),
                stiffness_method=_text(row.get("stiffness_method"), "stiffness_method"),
                source_refs=tuple(
                    _text(ref, "moment_magnification.source_ref")
                    for ref in _sequence(row.get("source_refs"), "moment_magnification.source_refs")
                ),
                es_mpa=_optional_number(row.get("es_mpa"), "es_mpa"),
                is_mm4=_optional_number(row.get("is_mm4"), "is_mm4"),
                horizontal_load_between_ends=_required_bool(row, "horizontal_load_between_ends"),
                story_sum_nd_n=_optional_number(row.get("story_sum_nd_n"), "story_sum_nd_n"),
                story_sum_nk_n=_optional_number(row.get("story_sum_nk_n"), "story_sum_nk_n"),
                fck_mpa=_optional_number(row.get("fck_mpa"), "fck_mpa"),
                concrete_area_mm2=_optional_number(row.get("concrete_area_mm2"), "concrete_area_mm2"),
            )
        )
    return tuple(bases)


def _decode_canonical_items(value: object, key: str) -> tuple[str, ...]:
    root = _canonical_second_order_root(value)
    if root is None:
        return ()
    raw = root.get(key, ())
    return tuple(_text(item, key) for item in _sequence(raw, key))


def _decode_expected_final_states(value: object, *, component_id: str) -> tuple[ColumnDemandState, ...]:
    root = _canonical_second_order_root(value)
    if root is None:
        return ()
    raw = root.get("expected_final_states")
    if raw is None:
        return ()
    return _decode_demand_states(raw, component_id=component_id, label="expected_final_states")


def _decode_stiffness_evidence(value: object) -> tuple[AssignedFrameBendingModifierEvidence, ...]:
    if value is None:
        return ()
    evidence: list[AssignedFrameBendingModifierEvidence] = []
    for index, raw in enumerate(_sequence(value, "stability stiffness evidence")):
        row = _mapping(raw, f"stiffness[{index}]")
        evidence.append(
            AssignedFrameBendingModifierEvidence(
                section_name=_text(row.get("section_name"), "section_name"),
                member_kind=_text(row.get("member_kind"), "member_kind"),
                i2_modifier=_number(row.get("i2_modifier"), "i2_modifier"),
                i3_modifier=_number(row.get("i3_modifier"), "i3_modifier"),
                source_refs=tuple(
                    _text(ref, "stiffness.source_ref")
                    for ref in _sequence(row.get("source_refs"), "stiffness.source_refs")
                ),
            )
        )
    return tuple(evidence)


def _state_payload(state: ColumnDemandState) -> dict[str, object]:
    return {
        "state_id": state.state_id,
        "component_id": state.component_id,
        "output_case": state.output_case,
        "case_type": state.case_type,
        "step_type": state.step_type,
        "step_number": state.step_number,
        "station_m": state.station_m,
        "end_tag": state.end_tag,
        "nd_compression_n": state.nd_compression_n,
        "m2_nmm": state.m2_nmm,
        "m3_nmm": state.m3_nmm,
        "source_identity": state.source_identity,
    }


def _magnification_payload(result) -> dict[str, object]:
    return {
        "demand_state_id": result.demand_state_id,
        "axis": result.axis,
        "status": result.status,
        "effective_ei_nmm2": result.effective_ei_nmm2,
        "critical_load_nk_n": result.critical_load_nk_n,
        "cm": result.cm,
        "beta_individual": result.beta_individual,
        "beta_story": result.beta_story,
        "final_magnification_factor": result.final_magnification_factor,
        "slenderness_lk_over_i": result.slenderness_lk_over_i,
        "eq729_product_required": result.eq729_product_required,
        "blockers": result.blockers,
        "authority": result.authority,
    }


def _state_slenderness_payload(item) -> dict[str, object]:
    return {
        "output_case": item.output_case,
        "status": item.result.status,
        "m2_status": item.result.m2.status,
        "m3_status": item.result.m3.status,
        "source_refs": item.source_refs,
    }


@dataclass(frozen=True, slots=True)
class ColumnDesignReadinessExecutionInput:
    envelope: RuleExecutionEnvelope
    width_mm: float
    depth_mm: float
    combo_definitions: tuple[ColumnComboDefinition, ...]
    case_demands: tuple[ColumnDemandState, ...]
    slenderness_evidence: ColumnSlendernessEvidence | None
    stiffness_evidence: tuple[AssignedFrameBendingModifierEvidence, ...]
    moment_magnification_bases: tuple[ColumnMomentMagnificationAxisBasis, ...]
    state_slenderness_bases: tuple[ColumnStateSlendernessBasis, ...]
    canonical_second_order_blockers: tuple[str, ...]
    canonical_second_order_reanalysis_items: tuple[str, ...]
    expected_final_states: tuple[ColumnDemandState, ...]
    evidence_refs: tuple[str, ...]

    @classmethod
    def from_declared_dependencies(
        cls,
        envelope: RuleExecutionEnvelope,
        dependencies: Sequence[MaterializedDependency],
    ) -> "ColumnDesignReadinessExecutionInput":
        deps = tuple(dependencies)
        by_key = {item.key: item for item in deps}
        expected = {
            WIDTH_MM_KEY,
            DEPTH_MM_KEY,
            COMBO_DEFINITIONS_KEY,
            CASE_DEMANDS_KEY,
            SLENDERNESS_EVIDENCE_KEY,
            STIFFNESS_EVIDENCE_KEY,
        }
        if len(by_key) != len(deps) or set(by_key) != expected:
            raise ValueError("FND-COL-2 received unexpected dependency keys")
        component = envelope.instance_id.scope_ref
        slenderness_payload = by_key[SLENDERNESS_EVIDENCE_KEY].value
        return cls(
            envelope=envelope,
            width_mm=_number(by_key[WIDTH_MM_KEY].value, "width_mm"),
            depth_mm=_number(by_key[DEPTH_MM_KEY].value, "depth_mm"),
            combo_definitions=_decode_combo_definitions(by_key[COMBO_DEFINITIONS_KEY].value),
            case_demands=_decode_demand_states(by_key[CASE_DEMANDS_KEY].value, component_id=component),
            slenderness_evidence=_decode_slenderness(slenderness_payload, component_id=component),
            stiffness_evidence=_decode_stiffness_evidence(by_key[STIFFNESS_EVIDENCE_KEY].value),
            moment_magnification_bases=_decode_moment_magnification_bases(slenderness_payload),
            state_slenderness_bases=_decode_state_slenderness_bases(slenderness_payload, component_id=component),
            canonical_second_order_blockers=_decode_canonical_items(slenderness_payload, "blockers"),
            canonical_second_order_reanalysis_items=_decode_canonical_items(slenderness_payload, "reanalysis_items"),
            expected_final_states=_decode_expected_final_states(slenderness_payload, component_id=component),
            evidence_refs=tuple(dict.fromkeys(ref for item in deps for ref in item.evidence_refs)),
        )


def _regulatory_quantity_from_readiness(
    inp: ColumnDesignReadinessExecutionInput,
    result: ColumnDesignDemandReadiness,
) -> RegulatoryQuantity:
    component = inp.envelope.instance_id.scope_ref
    payload = {
        "authority": result.authority,
        "status": result.status,
        "analysis_basis_status": result.analysis_basis_status,
        "second_order_treatment": result.second_order_treatment,
        "stability_sway_status": result.stability_sway_status,
        "minimum_eccentricity_status": result.minimum_eccentricity.status,
        "slenderness_basis_status": None if result.slenderness_basis is None else result.slenderness_basis.status,
        "slenderness_status": None if result.slenderness is None else result.slenderness.status,
        "state_slenderness": tuple(_state_slenderness_payload(item) for item in result.state_slenderness),
        "blocked_items": result.blocked_items,
        "moment_magnification_results": tuple(
            _magnification_payload(item) for item in result.moment_magnification_results
        ),
        "demand_states": tuple(_state_payload(state) for state in result.demand_states),
    }
    return RegulatoryQuantity(
        quantity_key=READINESS_KEY,
        producer_instance_id=inp.envelope.instance_id,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.COMPONENT,
        scope_ref=component,
        direction=None,
        value=payload,
        unit=UNIT_DIMENSIONLESS,
        availability=AvailabilityState.RESOLVED,
        rule_version=RULE_VERSION,
        code_refs=CODE_REFS,
        dependency_refs=(
            WIDTH_MM_KEY,
            DEPTH_MM_KEY,
            COMBO_DEFINITIONS_KEY,
            CASE_DEMANDS_KEY,
            SLENDERNESS_EVIDENCE_KEY,
            STIFFNESS_EVIDENCE_KEY,
        ),
        evidence_refs=inp.evidence_refs,
        provenance=("FND-COL-2 canonical readiness authority", result.authority, *result.source_refs),
        derivation_trace=(
            "column design demand reconstruction",
            "TS500 minimum eccentricity demand transformation",
            "TS500 slenderness basis resolution",
            "TS500 slenderness/second-order classification",
            "conditional axis-specific TS500 moment magnification",
            "analysis-basis/reanalysis classification",
        ),
        governing_trace=result.blocked_items,
    )


def evaluate_column_design_readiness(inp: ColumnDesignReadinessExecutionInput) -> RegulatoryQuantity:
    if not isinstance(inp, ColumnDesignReadinessExecutionInput):
        raise TypeError("FND-COL-2 evaluator requires ColumnDesignReadinessExecutionInput")
    component = inp.envelope.instance_id.scope_ref
    stiffness = assess_ts500_eq713_stiffness_basis(inp.stiffness_evidence) if inp.stiffness_evidence else None
    result = resolve_column_design_demand_readiness(
        component_id=component,
        combo_definitions=inp.combo_definitions,
        constituent_case_demands=inp.case_demands,
        width_mm=inp.width_mm,
        depth_mm=inp.depth_mm,
        slenderness_evidence=inp.slenderness_evidence,
        stability_stiffness_basis=stiffness,
        moment_magnification_bases=inp.moment_magnification_bases,
        state_slenderness_bases=inp.state_slenderness_bases,
        canonical_second_order_blockers=inp.canonical_second_order_blockers,
        canonical_second_order_reanalysis_items=inp.canonical_second_order_reanalysis_items,
        expected_final_states=inp.expected_final_states,
    )
    quantity = _regulatory_quantity_from_readiness(inp, result)
    captured = _TYPED_READINESS_CAPTURE.get()
    if captured is not None:
        captured.append((inp.envelope, result, inp.evidence_refs))
    return quantity


def _dep(*, key, source_kind, semantic_type, dimension, unit, population=PopulationRequirement.ANY_RESOLVED):
    return DependencySpec(
        key=key,
        source_kind=source_kind,
        semantic_type=semantic_type,
        physical_dimension=dimension,
        grain=Grain.COMPONENT,
        scope_policy=ScopePolicy.SAME_SCOPE,
        direction_policy=DirectionPolicy.NO_DIRECTION,
        unit_requirement=unit,
        required_availability=AvailabilityState.RESOLVED,
        population_completeness_requirement=population,
    )


DEPENDENCIES = (
    _dep(key=WIDTH_MM_KEY, source_kind=DependencySourceKind.FACT, semantic_type=SemanticType.COLUMN_WIDTH, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
    _dep(key=DEPTH_MM_KEY, source_kind=DependencySourceKind.FACT, semantic_type=SemanticType.COLUMN_DEPTH, dimension=PhysicalDimension.LENGTH, unit=UNIT_MM),
    _dep(key=COMBO_DEFINITIONS_KEY, source_kind=DependencySourceKind.CONTEXT, semantic_type=SemanticType.CHECK_EVIDENCE_TRACE, dimension=PhysicalDimension.DIMENSIONLESS, unit=UNIT_DIMENSIONLESS, population=PopulationRequirement.FULL),
    _dep(key=CASE_DEMANDS_KEY, source_kind=DependencySourceKind.SOURCE_POPULATION, semantic_type=SemanticType.CHECK_EVIDENCE_TRACE, dimension=PhysicalDimension.DIMENSIONLESS, unit=UNIT_DIMENSIONLESS, population=PopulationRequirement.FULL),
    _dep(key=SLENDERNESS_EVIDENCE_KEY, source_kind=DependencySourceKind.CONTEXT, semantic_type=SemanticType.CHECK_EVIDENCE_TRACE, dimension=PhysicalDimension.DIMENSIONLESS, unit=UNIT_DIMENSIONLESS, population=PopulationRequirement.FULL),
    _dep(key=STIFFNESS_EVIDENCE_KEY, source_kind=DependencySourceKind.CONTEXT, semantic_type=SemanticType.CHECK_EVIDENCE_TRACE, dimension=PhysicalDimension.DIMENSIONLESS, unit=UNIT_DIMENSIONLESS, population=PopulationRequirement.FULL),
)

APPLICABILITY = ApplicabilityBinding(
    "fnd-col-2:column-design-readiness:applicability",
    ColumnDesignReadinessApplicabilityInput,
    _applicability,
)
EVALUATOR = DerivationEvaluatorBinding(
    "fnd-col-2:column-design-readiness:evaluator",
    ColumnDesignReadinessExecutionInput,
    evaluate_column_design_readiness,
)
SPEC = RegulatoryDerivationSpec(
    rule_id=RULE_ID,
    code_refs=CODE_REFS,
    rule_version=RULE_VERSION,
    output_contract=RegulatoryOutputContract(
        authority_key=READINESS_KEY,
        semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
        physical_dimension=PhysicalDimension.DIMENSIONLESS,
        grain=Grain.COMPONENT,
        unit=UNIT_DIMENSIONLESS,
    ),
    dependencies=DEPENDENCIES,
    applicability=APPLICABILITY,
    evaluator=EVALUATOR,
)
REGISTRY = RegulatoryRegistry(derivations=(SPEC,))

__all__ = [
    "APPLICABILITY",
    "CASE_DEMANDS_KEY",
    "CODE_REFS",
    "COMBO_DEFINITIONS_KEY",
    "ColumnDesignReadinessApplicabilityInput",
    "ColumnDesignReadinessExecutionInput",
    "DEPENDENCIES",
    "DEPTH_MM_KEY",
    "EVALUATOR",
    "READINESS_KEY",
    "REGISTRY",
    "RULE_ID",
    "RULE_VERSION",
    "SLENDERNESS_EVIDENCE_KEY",
    "SPEC",
    "STIFFNESS_EVIDENCE_KEY",
    "WIDTH_MM_KEY",
    "_capture_typed_readiness_execution",
    "evaluate_column_design_readiness",
]
