"""COLUMN-R1 PUBLIC-A5 production composer.

This module owns composition only. Engineering semantics stay in the existing
Eq7.13 and FND-COL-2 authorities; ETABS mutation and RunAnalysis stay in the
existing B4B/B5 owners. The composer binds one trusted acquisition generation
to those authorities and fails closed at an exact causal edge.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Callable, Mapping, Sequence

from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    AreaCategory,
    AreaEq713TargetDisposition,
    AreaFormulation,
    AreaGrossBasePropertyEvidence,
    AreaStiffnessMode,
    ContributorDisposition,
    Eq713PopulationDisposition,
    FrameModeAuditDisposition,
    FrameStiffnessMode,
    ModeDisposition,
    TS500_EQ713_SOURCE_REF,
    WallRole,
    audit_frame_eq713_modes,
    build_area_eq713_target,
    build_concrete_uncracked_material_basis,
)
from tbdy_engine.analysis_basis.eq713_frame_mechanics import (
    FrameMechanicsEvidence,
    FrameModeParticipationClassification,
    build_frame_eq713_modifier_target,
    classify_frame_eq713_participation,
)
from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    AreaShellThickResponseGeneration,
    classify_frame_response_participation,
    resolve_area_response_modes,
)
from tbdy_engine.analysis_basis.frame_gross_flexural_basis import (
    capture_frame_flexural_base_continuity_evidence,
)
from tbdy_engine.application.column_a18_end_restraint import (
    A18FrameLocalAxisEvidence,
    A18_READY,
    materialize_ts500_column_end_restraint_ratios,
)
from tbdy_engine.application.column_design_basis import (
    BoundColumnActionFamilyApplicability,
)
from tbdy_engine.application.column_public_a5_second_order import (
    build_public_a5_canonical_second_order_payload,
)
from tbdy_engine.application.contracts import ColumnExecutionRequest
from tbdy_engine.application.column_execution import ColumnPopulationState
from tbdy_engine.design.columns.free_length_basis import resolve_ts500_column_free_length
from tbdy_engine.design.columns.rebar_selection import (
    ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
    normalize_etabs_column_end_demands,
)
from tbdy_engine.design.columns.story_relative_translation import ReviewedStoryTranslationTolerance
from tbdy_engine.etabs.oapi.analysis_execution import (
    get_defined_analysis_cases_from_session,
)
from tbdy_engine.etabs.oapi.area_contributors import AreaDesignOrientation
from tbdy_engine.etabs.oapi.area_modifiers import (
    AreaModifierSurface,
    AreaModifierVector,
    get_area_modifiers_from_session,
)
from tbdy_engine.etabs.oapi.eq713_response_cases import (
    qualify_eq713_horizontal_case_scope_from_session,
)
from tbdy_engine.etabs.oapi.frame_modifiers import FrameModifierSurface, FrameModifierVector
from tbdy_engine.etabs.oapi.object_model import (
    read_frame_local_axes_from_session,
)
from tbdy_engine.etabs.oapi.line_springs import LineSpringPropertyUniverseFact
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence, StrictColumnTopologyBundle
from tbdy_engine.integration.etabs_analysis_execution import execute_controlled_analysis
from tbdy_engine.integration.etabs_analysis_state_mutation import (
    AreaModifierMutationFact,
    AreaModifierTargetRequest,
    FrameModifierMutationFact,
    FrameModifierTargetRequest,
    build_requested_section_modifier_manifest,
    establish_section_modifier_analysis_state,
)
from tbdy_engine.integration.etabs_scratch_lifecycle import create_owned_scratch_context
from tbdy_engine.integration.live_etabs_acquisition_context import TrustedLiveAcquisitionContext
from tbdy_engine.providers.etabs_area_contributor_provider import (
    AreaContributorFact,
    AreaContributorPopulation,
    AreaContributorScopeFact,
    AreaContributorScopeStatus,
    AreaMaterialFactualFact,
    AreaMaterialResolution,
    AreaPropertyFamily,
    capture_area_contributor_population_from_session,
)
from tbdy_engine.providers.etabs_auto_seismic_direction_provider import (
    DIRECTION_AUTHORITY,
    TABLE_AUTO_SEISMIC_TSC2018,
    capture_etabs_auto_seismic_direction_evidence_from_session,
    tsc2018_horizontal_pattern_directions,
)
from tbdy_engine.providers.etabs_column_endpoint_restraint_provider import (
    capture_etabs_column_endpoint_restraints_from_session,
)
from tbdy_engine.providers.etabs_combo_definition_provider import (
    EtabsComboDefinitionEvidence,
    capture_etabs_combo_definitions_from_session,
)
from tbdy_engine.providers.etabs_concrete_design_combo_selection_probe import (
    acquire_actual_concrete_design_combo_selection_from_session,
)
from tbdy_engine.providers.etabs_eq713_response_provider import (
    Eq713ResponsePopulationFact,
    capture_eq713_response_population_from_session,
    probe_eq713_response_population_capability,
)
from tbdy_engine.providers.etabs_frame_eq713_population_provider import (
    FrameEq713FactualFact,
    FrameEq713FactualPopulation,
    FrameEq713ObjectTypeFact,
    FrameEq713ObjectTypeResolution,
    FrameEq713ResidualStructuralFact,
    FrameEq713ScopeFact,
    capture_frame_eq713_factual_population,
)
from tbdy_engine.providers.etabs_strict_column_topology_provider import (
    capture_etabs_strict_column_topology_from_session,
)
from tbdy_engine.providers.strict_topology_stiffness_evidence_provider import (
    build_assigned_rc_frame_bending_modifier_evidence,
)
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.fnd_col_2 import (
    CASE_DEMANDS_KEY,
    COMBO_DEFINITIONS_KEY,
    DEPTH_MM_KEY,
    RULE_ID,
    SLENDERNESS_EVIDENCE_KEY,
    STIFFNESS_EVIDENCE_KEY,
    WIDTH_MM_KEY,
    ColumnDesignReadinessApplicabilityInput,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    ExternalDependencyAuthority,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_MM

BLOCKER_A3_FACTUAL_ACQUISITION = "LIVE_A3_FACTUAL_ACQUISITION_NOT_QUALIFIED"
BLOCKER_A3_EQ713_POPULATION = "LIVE_A3_EQ713_POPULATION_NOT_QUALIFIED"
BLOCKER_A3_MEMBER_RESPONSE = "CURRENT_A3_MEMBER_LEVEL_RESPONSE_KINEMATIC_BASIS_NOT_BOUND"
BLOCKER_A4_B4B = "LIVE_A4_B4B_STATE_NOT_QUALIFIED"
BLOCKER_A4_B5 = "LIVE_A4_B5_RESULT_NOT_QUALIFIED"
BLOCKER_A4_POST_CONTINUITY = "LIVE_A4_POST_CONTINUITY_NOT_QUALIFIED"
BLOCKER_A5_INPUT_MATERIALIZATION = "LIVE_A5_FND2_INPUT_MATERIALIZATION_NOT_QUALIFIED"
BLOCKER_A5_POPULATION_UNKNOWN = "LIVE_A5_COLUMN_POPULATION_NOT_PROVEN"
BLOCKER_A5_DUPLICATE_COMPONENT = "LIVE_A5_DUPLICATE_FACTUAL_COLUMN_COMPONENT_IDENTITY"
BLOCKER_A5_REQUESTED_FOCUS_ABSENT = "LIVE_A5_REQUESTED_COLUMN_NOT_IN_FACTUAL_POPULATION"


_AREA_RESPONSE_SCOPE_REF = "COLUMN_R1_EQ713_IN_PLANE_DISPLACEMENT_RESPONSE_SCOPE"
_FRAME_MECHANICS_REF_PREFIX = "COLUMN_R1_STRICT_FRAME_MECHANICS"
_CSI_ETABS_OBJECT_TYPE_REF = (
    "CSI_ETABS_HELP:https://docs.csiamerica.com/help-files/etabs/"
    "Menus/Select/Select/Object_Type.htm"
)
_CSI_ETABS_FRAME_SECTION_NONE_REF = (
    "CSI_ETABS_HELP:https://docs.csiamerica.com/help-files/etabs/"
    "Menus/Assign/Frame/Frame_Section_Property.htm"
)
_CSI_ETABS_LINE_SPRING_REF = (
    "CSI_ETABS_HELP:https://docs.csiamerica.com/help-files/etabs/"
    "Menus/Assign/Frame/Line_Springs.htm"
)
_CSI_ETABS_NULL_LINE_SPRING_RELEASE_REF = (
    "CSI_ETABS_ENHANCEMENT:19.1.0_ETA_analysis_null_line"
)
_CSI_ETABS_FRAME_LOCAL_AXES_REF = (
    "CSI_ETABS_HELP:https://docs.csiamerica.com/help-files/etabs/"
    "Menus/Assign/Frame/Local_Axes_Frames.htm"
)
_RESPONSE_AREA_MODES = {
    AreaStiffnessMode.F11,
    AreaStiffnessMode.F22,
    AreaStiffnessMode.F12,
    AreaStiffnessMode.M11,
    AreaStiffnessMode.M22,
    AreaStiffnessMode.M12,
    AreaStiffnessMode.V13,
    AreaStiffnessMode.V23,
}
_AREA_SLOT = {
    AreaStiffnessMode.F11: 0,
    AreaStiffnessMode.F22: 1,
    AreaStiffnessMode.F12: 2,
    AreaStiffnessMode.M11: 3,
    AreaStiffnessMode.M22: 4,
    AreaStiffnessMode.M12: 5,
    AreaStiffnessMode.V13: 6,
    AreaStiffnessMode.V23: 7,
}


class PublicA5CompositionError(RuntimeError):
    def __init__(self, blocker: str, message: str) -> None:
        super().__init__(message)
        self.blocker = blocker


@dataclass(frozen=True, slots=True)
class PublicA5ColumnMaterialization:
    request: ColumnExecutionRequest
    column: object
    free_length: object | None
    canonical_second_order: Mapping[str, object] | None


@dataclass(frozen=True, slots=True)
class PublicA5PopulationExecution:
    """Exact factual Column population after one shared PUBLIC-A5 generation."""

    population_state: ColumnPopulationState
    acquisition_context: TrustedLiveAcquisitionContext
    focus_component_id: str
    focus_present: bool
    topology: object | None
    owned_scratch: object | None
    analysis_execution: object | None
    selected_combo_population: object | None
    combo_definitions: tuple[object, ...]
    flattened_combos: tuple[object, ...]
    columns: tuple[PublicA5ColumnMaterialization, ...]
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.population_state, ColumnPopulationState):
            raise PublicA5CompositionError(
                BLOCKER_A5_POPULATION_UNKNOWN,
                "unsupported PUBLIC-A5 population state",
            )
        if self.population_state is ColumnPopulationState.UNKNOWN:
            if self.topology is not None or self.columns or self.focus_present:
                raise PublicA5CompositionError(
                    BLOCKER_A5_POPULATION_UNKNOWN,
                    "POPULATION_UNKNOWN cannot expose inferred factual components",
                )
            return

        if self.topology is None:
            raise PublicA5CompositionError(
                BLOCKER_A5_POPULATION_UNKNOWN,
                "POPULATION_KNOWN requires strict factual topology",
            )
        expected = tuple(item.component_id for item in self.topology.columns)
        if not expected:
            raise PublicA5CompositionError(
                BLOCKER_A5_POPULATION_UNKNOWN,
                "strict factual topology contains no Columns",
            )
        if len(expected) != len(set(expected)):
            raise PublicA5CompositionError(
                BLOCKER_A5_DUPLICATE_COMPONENT,
                "strict factual topology contains duplicate Column component identity",
            )
        observed = tuple(item.request.component_id for item in self.columns)
        if observed != expected or len(observed) != len(set(observed)):
            raise PublicA5CompositionError(
                BLOCKER_A5_INPUT_MATERIALIZATION,
                "PUBLIC-A5 materialized Column population is not exact",
            )
        if self.focus_present is not (self.focus_component_id in expected):
            raise PublicA5CompositionError(
                BLOCKER_A5_INPUT_MATERIALIZATION,
                "PUBLIC-A5 focus-presence flag differs from strict topology",
            )


def _blocked_component(
    component_id: str,
    context: TrustedLiveAcquisitionContext,
    blocker: str,
):
    from tbdy_engine.application.column_execution import (
        ColumnDomainArtifact,
        STATUS_FACTUAL_ACQUISITION_BLOCKED,
    )

    return ColumnDomainArtifact(
        component_id=component_id,
        model_fingerprint=context.model_fingerprint,
        evidence_epoch_id=context.evidence_epoch_id,
        status=STATUS_FACTUAL_ACQUISITION_BLOCKED,
        blockers=(blocker,),
    )


def _blocked(request: ColumnExecutionRequest, context: TrustedLiveAcquisitionContext, blocker: str):
    return _blocked_component(
        request.component_id,
        context,
        blocker,
    )


def _unknown_population(
    request: ColumnExecutionRequest,
    context: TrustedLiveAcquisitionContext,
    blocker: str,
) -> PublicA5PopulationExecution:
    return PublicA5PopulationExecution(
        population_state=ColumnPopulationState.UNKNOWN,
        acquisition_context=context,
        focus_component_id=request.component_id,
        focus_present=False,
        topology=None,
        owned_scratch=None,
        analysis_execution=None,
        selected_combo_population=None,
        combo_definitions=(),
        flattened_combos=(),
        columns=(),
        blockers=(blocker,),
    )


def _known_blocked_population(
    request: ColumnExecutionRequest,
    context: TrustedLiveAcquisitionContext,
    topology,
    blocker: str,
    *,
    owned_scratch=None,
) -> PublicA5PopulationExecution:
    targets = tuple(topology.columns)
    component_ids = tuple(item.component_id for item in targets)
    if not component_ids:
        return _unknown_population(
            request,
            context,
            BLOCKER_A5_POPULATION_UNKNOWN,
        )
    if len(component_ids) != len(set(component_ids)):
        return _unknown_population(
            request,
            context,
            BLOCKER_A5_DUPLICATE_COMPONENT,
        )
    materializations = tuple(
        PublicA5ColumnMaterialization(
            request=ColumnExecutionRequest(target.component_id),
            column=_blocked_component(target.component_id, context, blocker),
            free_length=None,
            canonical_second_order=None,
        )
        for target in targets
    )
    return PublicA5PopulationExecution(
        population_state=ColumnPopulationState.KNOWN,
        acquisition_context=context,
        focus_component_id=request.component_id,
        focus_present=request.component_id in component_ids,
        topology=topology,
        owned_scratch=owned_scratch,
        analysis_execution=None,
        selected_combo_population=None,
        combo_definitions=(),
        flattened_combos=(),
        columns=materializations,
        blockers=(blocker,),
    )


def _population_failure(
    request: ColumnExecutionRequest,
    context: TrustedLiveAcquisitionContext,
    topology,
    blocker: str,
    *,
    owned_scratch=None,
) -> PublicA5PopulationExecution:
    if topology is None:
        return _unknown_population(request, context, blocker)
    return _known_blocked_population(
        request,
        context,
        topology,
        blocker,
        owned_scratch=owned_scratch,
    )


def _target_column(topology: StrictColumnTopologyBundle, component_id: str) -> ColumnTopologyEvidence:
    matches = tuple(item for item in topology.columns if item.component_id == component_id)
    if len(matches) != 1:
        raise PublicA5CompositionError(
            BLOCKER_A3_FACTUAL_ACQUISITION,
            f"expected exactly one strict-topology column for component_id={component_id!r}; got {len(matches)}",
        )
    return matches[0]


def _frame_mechanics_evidence(
    row: FrameEq713FactualFact,
    topology: StrictColumnTopologyBundle,
) -> FrameMechanicsEvidence:
    """Bind factual topology/axis/end-condition mechanics for Eq713 authority."""
    if row.member_role == "COLUMN":
        matches = tuple(item for item in topology.columns if item.unique_name == row.frame_name)
        if len(matches) != 1:
            raise PublicA5CompositionError(
                BLOCKER_A3_EQ713_POPULATION,
                f"COLUMN Frame {row.frame_name!r} is absent/ambiguous in strict topology",
            )
        item = matches[0]
        if (
            item.width_t2_m <= 0.0
            or item.depth_t3_m <= 0.0
            or item.object_length_m <= 0.0
            or item.coordinate_length_m <= 0.0
        ):
            raise PublicA5CompositionError(
                BLOCKER_A3_EQ713_POPULATION,
                f"COLUMN Frame {row.frame_name!r} has non-positive strict geometry",
            )
        vector = tuple(
            float(item.top_coord_m[index] - item.bottom_coord_m[index])
            for index in range(3)
        )
        mechanics_ref = (
            f"{_FRAME_MECHANICS_REF_PREFIX}:COLUMN:{row.frame_name}:"
            f"LOCAL_AXIS_EXPLICIT={item.local_axis_explicit}:ANGLE={item.local_axis_angle_deg}"
        )
        return FrameMechanicsEvidence(
            component_uid=row.frame_name,
            member_role=row.member_role,
            member_axis_vector=vector,
            supported_end_condition=row.supported_end_condition,
            local_axis_explicit=bool(item.local_axis_explicit),
            local_axis_angle_degrees=item.local_axis_angle_deg,
            source_refs=(*row.source_refs, mechanics_ref),
        )

    beam = row.beam_mechanics
    if beam is None:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            f"BEAM Frame {row.frame_name!r} lacks exact full-model factual mechanics",
        )
    mechanics_ref = (
        f"{_FRAME_MECHANICS_REF_PREFIX}:BEAM:{row.frame_name}:"
        f"FULL_MODEL_ENDPOINT_VECTOR:"
        f"LOCAL_AXIS_EXPLICIT={beam.local_axis_explicit}:"
        f"ANGLE={beam.local_axis_angle_degrees}"
    )
    return FrameMechanicsEvidence(
        component_uid=row.frame_name,
        member_role=row.member_role,
        member_axis_vector=tuple(
            float(value)
            for value in beam.member_axis_vector
        ),
        supported_end_condition=row.supported_end_condition,
        local_axis_explicit=beam.local_axis_explicit,
        local_axis_angle_degrees=beam.local_axis_angle_degrees,
        source_refs=(
            *row.source_refs,
            *beam.source_refs,
            mechanics_ref,
        ),
    )


def _material_bases(frame_population: FrameEq713FactualPopulation):
    by_material = {}
    for row in frame_population.rows:
        basis = build_concrete_uncracked_material_basis(
            material_name=row.base_fact.material_name,
            fck_mpa=row.base_fact.concrete_fck_mpa,
            factual_ec_mpa=row.factual_ec_mpa,
            factual_gc_mpa=row.factual_gc_mpa,
            source_refs=row.source_refs,
        )
        prior = by_material.get(basis.material_name)
        if prior is not None and (
            prior.fck_mpa != basis.fck_mpa
            or prior.factual_ec_mpa != basis.factual_ec_mpa
            or prior.factual_gc_mpa != basis.factual_gc_mpa
        ):
            raise PublicA5CompositionError(
                BLOCKER_A3_EQ713_POPULATION,
                f"material {basis.material_name!r} has contradictory same-epoch factual E/G/fck evidence",
            )
        by_material[basis.material_name] = basis
    return by_material


def _typed_out_of_slice_frame_disposition(
    scope: FrameEq713ScopeFact,
    object_type: FrameEq713ObjectTypeFact,
    residual_structural: FrameEq713ResidualStructuralFact | None,
    line_spring_property_universe: LineSpringPropertyUniverseFact | None = None,
) -> FrameModeAuditDisposition:
    # Source-bound fail-closed disposition for one residual Frame.
    if not isinstance(scope, FrameEq713ScopeFact):
        raise TypeError("scope must be FrameEq713ScopeFact")
    if not isinstance(object_type, FrameEq713ObjectTypeFact):
        raise TypeError("object_type must be FrameEq713ObjectTypeFact")
    if object_type.frame_name != scope.frame_name:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            "Frame scope/object-type identity mismatch",
        )
    if residual_structural is not None and (
        not isinstance(residual_structural, FrameEq713ResidualStructuralFact)
        or residual_structural.frame_name != scope.frame_name
    ):
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            "Frame residual structural identity mismatch",
        )

    refs = list(
        dict.fromkeys(
            (
                *scope.source_refs,
                *object_type.source_refs,
                TS500_EQ713_SOURCE_REF,
                _CSI_ETABS_OBJECT_TYPE_REF,
            )
        )
    )
    normalized = object_type.normalized_frame_type

    if object_type.resolution is FrameEq713ObjectTypeResolution.UNRESOLVED:
        reason = (
            f"Frame {scope.frame_name!r} factual Frame type is unresolved: "
            f"{object_type.resolution_reason}; Eq7.13 applicability remains blocked"
        )
    elif normalized == "NULL":
        refs.extend(
            (
                _CSI_ETABS_FRAME_SECTION_NONE_REF,
                _CSI_ETABS_LINE_SPRING_REF,
                _CSI_ETABS_NULL_LINE_SPRING_RELEASE_REF,
            )
        )

        if line_spring_property_universe is not None:
            if not isinstance(
                line_spring_property_universe,
                LineSpringPropertyUniverseFact,
            ):
                raise TypeError(
                    "line_spring_property_universe must be "
                    "LineSpringPropertyUniverseFact or None"
                )
            refs.append(
                line_spring_property_universe.evidence_ref
            )

        if (
            scope.assigned_section_name is None
            and line_spring_property_universe is not None
            and line_spring_property_universe.proven_empty
        ):
            reason = (
                f"Frame {scope.frame_name!r} has exact ETABS "
                f"FrameType={object_type.raw_frame_type!r}, has no "
                "frame-section assignment, and the exact model-wide "
                "PropLineSpring property universe is successfully proven "
                "empty; no Frame-section or named line-spring stiffness "
                "mechanism exists for this Null Frame"
            )
            exact_refs = tuple(dict.fromkeys(refs))
            rows = tuple(
                ModeDisposition(
                    mode,
                    ContributorDisposition.PROVEN_NOT_APPLICABLE,
                    reason,
                    exact_refs,
                )
                for mode in FrameStiffnessMode
            )
            return FrameModeAuditDisposition(
                component_uid=scope.frame_name,
                mode_dispositions=rows,
                blocked_reasons=(),
                source_refs=exact_refs,
            )

        reason = (
            f"Frame {scope.frame_name!r} has exact ETABS "
            f"FrameType={object_type.raw_frame_type!r}; a Null line/"
            "no frame-section assignment does not by itself prove "
            "absence of all analysis stiffness because ETABS supports "
            "line-spring assignments on frame objects and explicitly "
            "supports line springs on Null line objects; this exact "
            "object's complete stiffness-mechanism absence is not proven"
        )
    elif (
        normalized in {"BEAM", "BRACE"}
        and residual_structural is not None
        and getattr(
            residual_structural,
            "material_type",
            None,
        )
        is not None
        and residual_structural.material_type.success
        and residual_structural.material_type.is_steel
        and residual_structural.material_type.material_name
        == residual_structural.material_name
    ):
        refs.extend(
            residual_structural.source_refs
        )
        refs.append(
            residual_structural
            .material_type
            .evidence_ref
        )

        property_modifiers = tuple(
            float(value)
            for value
            in residual_structural
            .property_modifiers
            .modifiers
            .as_tuple()
        )

        object_modifiers = tuple(
            float(value)
            for value
            in residual_structural
            .object_modifiers
            .modifiers
            .as_tuple()
        )

        if (
            all(
                value == 1.0
                for value in property_modifiers
            )
            and all(
                value == 1.0
                for value in object_modifiers
            )
        ):
            reason = (
                f"Frame {scope.frame_name!r} has exact "
                f"ETABS FrameType="
                f"{object_type.raw_frame_type!r}, "
                f"material="
                f"{residual_structural.material_name!r}, "
                "and source-proven CSI "
                "eMatType=Steel; TS500 concrete "
                "cracking normalization is not applied "
                "to this source-proven steel Frame. "
                "Exact Frame property and object "
                "modifier vectors are unity. End "
                "releases and partial-fixity facts "
                "remain preserved physical boundary "
                "conditions and are not reclassified "
                "as non-participation."
            )

            exact_refs = tuple(
                dict.fromkeys(refs)
            )

            rows = tuple(
                ModeDisposition(
                    mode,
                    ContributorDisposition
                    .PROVEN_NOT_APPLICABLE,
                    reason,
                    exact_refs,
                )
                for mode in FrameStiffnessMode
            )

            return FrameModeAuditDisposition(
                component_uid=scope.frame_name,
                mode_dispositions=rows,
                blocked_reasons=(),
                source_refs=exact_refs,
            )

        reason = (
            f"Frame {scope.frame_name!r} is "
            "source-proven steel, but exact Frame "
            "property/object modifiers are not both "
            "unity; no bounded steel residual "
            "normalization rule is established "
            "for this state"
        )

    elif normalized == "BRACE":
        refs.append(_CSI_ETABS_FRAME_LOCAL_AXES_REF)
        if residual_structural is None:
            reason = (
                f"Frame {scope.frame_name!r} has exact ETABS FrameType={object_type.raw_frame_type!r}; "
                "BRACE is a factual frame type, not a not-applicable label, and exact "
                "source-bound structural mechanics/material evidence is incomplete"
            )
        else:
            refs.extend(residual_structural.source_refs)
            reason = (
                f"Frame {scope.frame_name!r} has exact ETABS FrameType={object_type.raw_frame_type!r} "
                "and generic structural section/material/modifier/release facts, but the "
                "current Eq7.13 member-role authority does not truthfully represent BRACE "
                "without inferring BRACE as BEAM; participation remains unresolved"
            )
    elif residual_structural is not None:
        refs.extend(residual_structural.source_refs)
        reason = (
            f"Frame {scope.frame_name!r} has exact ETABS FrameType={object_type.raw_frame_type!r}, "
            f"section={residual_structural.assigned_section_name!r}, "
            f"shape={residual_structural.shape!r}, material={residual_structural.material_name!r}, "
            "and generic elastic section/material/modifier/release facts; the active "
            "Eq7.13 Frame audit uses a concrete-only uncracked material basis and no "
            "source-proven material-neutral normalization contract has been established "
            "for this residual structural Frame"
        )
    else:
        reason = (
            f"Frame {scope.frame_name!r} has exact ETABS FrameType={object_type.raw_frame_type!r}; "
            f"current source-bound residual evidence is insufficient for a truthful "
            f"Eq7.13 applicability/participation disposition ({scope.reason})"
        )

    exact_refs = tuple(dict.fromkeys(refs))
    rows = tuple(
        ModeDisposition(
            mode,
            ContributorDisposition.BLOCKED_UNSUPPORTED,
            reason,
            exact_refs,
        )
        for mode in FrameStiffnessMode
    )
    return FrameModeAuditDisposition(
        component_uid=scope.frame_name,
        mode_dispositions=rows,
        blocked_reasons=(reason,),
        source_refs=exact_refs,
    )


def _out_of_slice_frame_disposition(
    scope: FrameEq713ScopeFact,
) -> FrameModeAuditDisposition:
    if not isinstance(scope, FrameEq713ScopeFact):
        raise TypeError("scope must be FrameEq713ScopeFact")
    refs = tuple(
        dict.fromkeys((*scope.source_refs, TS500_EQ713_SOURCE_REF))
    )
    rows = tuple(
        ModeDisposition(
            mode,
            ContributorDisposition.BLOCKED_UNSUPPORTED,
            scope.reason,
            refs,
        )
        for mode in FrameStiffnessMode
    )
    return FrameModeAuditDisposition(
        component_uid=scope.frame_name,
        mode_dispositions=rows,
        blocked_reasons=(scope.reason,),
        source_refs=refs,
    )




def _same_decimal_at_observed_precision(
    prior: object,
    observed: object,
) -> bool:
    left = Decimal(str(prior))
    right = Decimal(str(observed))
    quantum = Decimal(1).scaleb(right.as_tuple().exponent)
    return left.quantize(quantum) == right.quantize(quantum)


def _extend_material_bases_from_area(
    material_bases: Mapping[str, object],
    area_population: AreaContributorPopulation,
):
    result = dict(material_bases)
    for fact in tuple(
        getattr(area_population, "material_facts", ()) or ()
    ):
        if fact.resolution is not AreaMaterialResolution.CONCRETE_PROVEN:
            continue
        basis = build_concrete_uncracked_material_basis(
            material_name=fact.material_name,
            fck_mpa=fact.concrete_fck_mpa,
            factual_ec_mpa=fact.factual_ec_mpa,
            factual_gc_mpa=fact.factual_gc_mpa,
            source_refs=fact.source_refs,
        )
        prior = result.get(basis.material_name)
        if prior is not None:
            if (
                not _same_decimal_at_observed_precision(
                    prior.fck_mpa,
                    basis.fck_mpa,
                )
                or not _same_decimal_at_observed_precision(
                    prior.factual_ec_mpa,
                    basis.factual_ec_mpa,
                )
                or not _same_decimal_at_observed_precision(
                    prior.factual_gc_mpa,
                    basis.factual_gc_mpa,
                )
            ):
                raise PublicA5CompositionError(
                    BLOCKER_A3_EQ713_POPULATION,
                    f"material {basis.material_name!r} has contradictory "
                    "same-epoch Frame/Area E/G/fck evidence",
                )
            # Preserve the already-accepted Frame material basis for shared
            # materials. Area-only materials are added below. The comparison
            # above reconciles only representation precision from the
            # same-epoch Basic Mechanical table; it is not an engineering
            # tolerance.
            continue
        result[basis.material_name] = basis
    return result


def _typed_out_of_slice_area_disposition(
    scope: AreaContributorScopeFact,
    factual: AreaContributorFact | None = None,
    material_fact: AreaMaterialFactualFact | None = None,
) -> AreaEq713TargetDisposition:
    if not isinstance(scope, AreaContributorScopeFact):
        raise TypeError("scope must be AreaContributorScopeFact")
    if scope.supported:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            "supported Area scope cannot enter typed-out-of-slice disposition",
        )
    refs_list = list(
        dict.fromkeys(
            (
                *scope.source_refs,
                TS500_EQ713_SOURCE_REF,
            )
        )
    )

    if factual is not None:
        if not isinstance(
            factual,
            AreaContributorFact,
        ):
            raise TypeError(
                "factual must be "
                "AreaContributorFact or None"
            )

        if factual.area_name != scope.area_name:
            raise PublicA5CompositionError(
                BLOCKER_A3_EQ713_POPULATION,
                "typed Area factual identity mismatch",
            )

        refs_list.extend(
            factual.source_refs
        )

    if material_fact is not None:
        if not isinstance(
            material_fact,
            AreaMaterialFactualFact,
        ):
            raise TypeError(
                "material_fact must be "
                "AreaMaterialFactualFact or None"
            )

        if (
            scope.material_name is None
            or material_fact.material_name
            != scope.material_name
        ):
            raise PublicA5CompositionError(
                BLOCKER_A3_EQ713_POPULATION,
                "typed Area material identity mismatch",
            )

        refs_list.extend(
            material_fact.source_refs
        )

    if (
        scope.status
        is AreaContributorScopeStatus
        .DECK_APPLICABILITY_UNRESOLVED
        and factual is not None
        and factual.property_state is not None
        and factual.property_state.family
        is AreaPropertyFamily.DECK
        and material_fact is not None
        and material_fact.material_type is not None
        and material_fact.material_type.success
        and material_fact.material_type.is_steel
        and material_fact.material_type.material_name
        == factual.property_state.material_name
    ):
        property_modifiers = tuple(
            float(value)
            for value
            in factual
            .property_state
            .property_modifiers
            .modifiers
            .as_tuple()
        )

        object_modifiers = tuple(
            float(value)
            for value
            in factual
            .object_modifiers
            .modifiers
            .as_tuple()
        )

        if (
            all(
                value == 1.0
                for value in property_modifiers
            )
            and all(
                value == 1.0
                for value in object_modifiers
            )
        ):
            refs_list.append(
                material_fact
                .material_type
                .evidence_ref
            )

            exact_refs = tuple(
                dict.fromkeys(
                    refs_list
                )
            )

            reason = (
                f"Area {scope.area_name!r} has exact "
                f"DECK property {scope.property_name!r}, "
                f"material={scope.material_name!r}, "
                "and source-proven CSI "
                "eMatType=Steel; TS500 concrete "
                "cracking normalization is not applied "
                "to this source-proven steel DECK "
                "Area. Exact Area property and object "
                "modifier vectors are unity. This "
                "disposition does not classify the "
                "DECK as structurally non-participating."
            )

            modes = tuple(
                ModeDisposition(
                    mode,
                    ContributorDisposition
                    .PROVEN_NOT_APPLICABLE,
                    reason,
                    exact_refs,
                )
                for mode
                in AreaStiffnessMode
            )

            return AreaEq713TargetDisposition(
                area_name=scope.area_name,
                mode_dispositions=modes,
                target_property_modifiers=None,
                blocked_reasons=(),
                source_refs=exact_refs,
            )

    refs = tuple(
        dict.fromkeys(
            refs_list
        )
    )

    reason = scope.reason

    modes = tuple(
        ModeDisposition(
            mode,
            ContributorDisposition.BLOCKED_UNSUPPORTED,
            reason,
            refs,
        )
        for mode in AreaStiffnessMode
    )
    return AreaEq713TargetDisposition(
        area_name=scope.area_name,
        mode_dispositions=modes,
        target_property_modifiers=None,
        blocked_reasons=(reason,),
        source_refs=refs,
    )

def _area_evidence(
    fact: AreaContributorFact,
    material_bases: Mapping[str, object],
) -> AreaGrossBasePropertyEvidence:
    if fact.orientation is AreaDesignOrientation.NULL or fact.property_name == "None":
        return AreaGrossBasePropertyEvidence.build(
            area_name=fact.area_name,
            property_name=fact.property_name,
            category=AreaCategory.NULL,
            formulation=AreaFormulation.OTHER,
            is_concrete=False,
            gross_geometry_proven=True,
            thickness_proven=True,
            homogeneous_simple_property=True,
            material_overwrite_qualified=True,
            thickness_overwrite_qualified=True,
            property_modifiers=(1.0,) * 10,
            object_modifiers=fact.object_modifiers.modifiers.as_tuple(),
            material_basis=None,
            source_refs=(*fact.source_refs, _AREA_RESPONSE_SCOPE_REF),
        )

    state = fact.property_state
    if state is None:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            f"Area {fact.area_name!r} has no exact property factual state",
        )
    if state.family not in {AreaPropertyFamily.WALL, AreaPropertyFamily.SLAB}:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            f"Area {fact.area_name!r} property family {state.family.value} is outside supported simple RC slice",
        )
    if state.shell_type_code == 2:
        formulation = AreaFormulation.SHELL_THICK
    elif state.shell_type_code == 3:
        formulation = AreaFormulation.MEMBRANE
    else:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            f"Area {fact.area_name!r} shell type {state.shell_type_code!r} is outside supported Eq713 slice",
        )
    if not state.material_name or state.material_name not in material_bases:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            f"Area {fact.area_name!r} material {state.material_name!r} has no same-epoch factual concrete material basis",
        )
    if state.thickness is None or float(state.thickness) <= 0.0:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            f"Area {fact.area_name!r} has no positive simple-property thickness",
        )
    overwrite_ok = fact.raw_material_overwrite_name in {"", "None", state.material_name}
    category = (
        AreaCategory.FLOOR
        if fact.orientation is AreaDesignOrientation.FLOOR
        else AreaCategory.WALL
        if fact.orientation is AreaDesignOrientation.WALL
        else None
    )
    if category is None:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            f"Area {fact.area_name!r} design orientation is outside supported Floor/Wall/Null slice",
        )
    wall_role = None
    if category is AreaCategory.WALL:
        wall_role = {
            "PIER": WallRole.PIER,
            "SPANDREL": WallRole.SPANDREL,
        }.get(fact.wall_assignment_role, WallRole.OTHER)

    return AreaGrossBasePropertyEvidence.build(
        area_name=fact.area_name,
        property_name=fact.property_name,
        category=category,
        formulation=formulation,
        is_concrete=True,
        gross_geometry_proven=True,
        thickness_proven=True,
        homogeneous_simple_property=True,
        material_overwrite_qualified=overwrite_ok,
        thickness_overwrite_qualified=True,
        property_modifiers=state.property_modifiers.modifiers.as_tuple(),
        object_modifiers=fact.object_modifiers.modifiers.as_tuple(),
        material_basis=material_bases[state.material_name],
        semi_rigid_diaphragm_participation=(
            fact.semi_rigid_diaphragm_assigned
            if category is AreaCategory.FLOOR
            else None
        ),
        wall_role=wall_role,
        default_wall_local_axes_proven=(
            fact.default_local_axes_assignment_proven
            if category is AreaCategory.WALL
            else None
        ),
        plate_participation=None,
        transverse_shear_participation=None,
        source_refs=(*fact.source_refs, _AREA_RESPONSE_SCOPE_REF),
    )


def _response_refs(populations: Sequence[Eq713ResponsePopulationFact]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            ref
            for population in populations
            for ref in (*population.source_refs, population.evidence_ref)
        )
    )


def _frame_response_values(
    populations: Sequence[Eq713ResponsePopulationFact],
    frame_name: str,
):
    results = tuple(
        result
        for population in populations
        for result in population.frame_results
        if result.frame_name == frame_name
    )
    rows = tuple(row for result in results for row in result.rows)
    return {
        FrameStiffnessMode.AXIAL: tuple(row.p for row in rows),
        FrameStiffnessMode.SHEAR_2: tuple(row.v2 for row in rows),
        FrameStiffnessMode.SHEAR_3: tuple(row.v3 for row in rows),
        FrameStiffnessMode.TORSION: tuple(row.t for row in rows),
        FrameStiffnessMode.FLEXURE_2: tuple(row.m2 for row in rows),
        FrameStiffnessMode.FLEXURE_3: tuple(row.m3 for row in rows),
    }


def _area_response_values(
    populations: Sequence[Eq713ResponsePopulationFact],
    area_name: str,
):
    results = tuple(
        result
        for population in populations
        for result in population.area_results
        if result.area_name == area_name
    )
    rows = tuple(row for result in results for row in result.rows)
    return {
        AreaStiffnessMode.F11: tuple(row.f11 for row in rows),
        AreaStiffnessMode.F22: tuple(row.f22 for row in rows),
        AreaStiffnessMode.F12: tuple(row.f12 for row in rows),
        AreaStiffnessMode.M11: tuple(row.m11 for row in rows),
        AreaStiffnessMode.M22: tuple(row.m22 for row in rows),
        AreaStiffnessMode.M12: tuple(row.m12 for row in rows),
        AreaStiffnessMode.V13: tuple(row.v13 for row in rows),
        AreaStiffnessMode.V23: tuple(row.v23 for row in rows),
    }


def _area_effective_modifiers(fact: AreaContributorFact):
    if fact.property_state is None:
        return {}
    prop = fact.property_state.property_modifiers.modifiers.as_tuple()
    obj = fact.object_modifiers.modifiers.as_tuple()
    return {
        mode: Decimal(str(prop[index])) * Decimal(str(obj[index]))
        for mode, index in _AREA_SLOT.items()
    }


def _build_a3(
    *,
    frame_population: FrameEq713FactualPopulation,
    area_population: AreaContributorPopulation,
    topology: StrictColumnTopologyBundle,
    frame_classifications: Mapping[str, FrameModeParticipationClassification] | None = None,
    response_populations: Sequence[Eq713ResponsePopulationFact] = (),
    area_response_generations: Mapping[
        str, Sequence[AreaShellThickResponseGeneration]
    ] | None = None,
):
    material_bases = _material_bases(frame_population)
    material_bases = _extend_material_bases_from_area(
        material_bases,
        area_population,
    )
    response_refs = _response_refs(response_populations) if response_populations else ()
    area_generation_map = {
        name: tuple(generations)
        for name, generations in (area_response_generations or {}).items()
    }
    supplied = dict(frame_classifications or {})
    frame_rows = []
    for fact in frame_population.rows:
        mechanics = _frame_mechanics_evidence(fact, topology)
        classification = supplied.get(fact.frame_name)
        if classification is None:
            classification = classify_frame_eq713_participation(mechanics)
        elif classification.component_uid != fact.frame_name:
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                f"Frame response classification identity mismatch for {fact.frame_name!r}",
            )
        basis = material_bases[fact.base_fact.material_name]
        frame_rows.append(
            audit_frame_eq713_modes(
                component_uid=fact.frame_name,
                property_modifiers=fact.property_modifiers.modifiers.as_tuple(),
                object_modifiers=fact.object_modifiers.modifiers.as_tuple(),
                participation=classification.as_mapping(),
                material_basis=basis,
                source_refs=(*fact.source_refs, *classification.source_refs),
            )
        )
    object_type_facts = tuple(
        getattr(frame_population, "object_type_facts", ()) or ()
    )
    if object_type_facts:
        type_by_name = frame_population.object_type_by_name
        residual_by_name = frame_population.residual_structural_by_name
        frame_rows.extend(
            _typed_out_of_slice_frame_disposition(
                scope,
                type_by_name[scope.frame_name],
                residual_by_name.get(scope.frame_name),
                getattr(
                    frame_population,
                    "line_spring_property_universe",
                    None,
                ),
            )
            for scope in frame_population.out_of_slice_rows
        )
    else:
        # Compatibility-only path for bounded legacy synthetic fixtures.
        # Production capture always emits the exact object-type denominator.
        frame_rows.extend(
            _out_of_slice_frame_disposition(scope)
            for scope in frame_population.out_of_slice_rows
        )
    observed_frame_scope = tuple(
        sorted(row.component_uid for row in frame_rows)
    )
    if observed_frame_scope != frame_population.expected_frame_names:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            "A3 Frame disposition population does not exactly reconcile to "
            "the factual FrameObj universe",
        )

    exact_area_partition = bool(
        getattr(area_population, "scope_facts", ()) or ()
    )
    supported_area_rows = (
        tuple(area_population.supported_rows)
        if exact_area_partition
        else tuple(area_population.rows)
    )
    typed_area_rows = (
        tuple(area_population.typed_out_of_slice_rows)
        if exact_area_partition
        else ()
    )
    area_evidence = tuple(
        _area_evidence(fact, material_bases)
        for fact in supported_area_rows
    )
    area_by_name = {
        fact.area_name: fact for fact in area_population.rows
    }
    area_rows = []
    for evidence in area_evidence:
        row = build_area_eq713_target(evidence)
        generations = area_generation_map.get(evidence.area_name, ())
        if generations:
            factual = area_by_name[evidence.area_name]
            if factual.property_state is None or factual.property_state.thickness is None:
                raise PublicA5CompositionError(
                    BLOCKER_A3_MEMBER_RESPONSE,
                    f"Area {evidence.area_name!r} lost simple ShellThick thickness identity",
                )
            generation_refs = tuple(
                dict.fromkeys(ref for generation in generations for ref in generation.source_refs)
            )
            row = resolve_area_response_modes(
                base=row,
                gross_evidence=evidence,
                shell_thickness=factual.property_state.thickness,
                response_generations=generations,
                source_refs=(*response_refs, *generation_refs),
            )
        elif response_populations and evidence.formulation is AreaFormulation.SHELL_THICK:
            factual = area_by_name[evidence.area_name]
            row = resolve_area_response_modes(
                base=row,
                values_by_mode=_area_response_values(response_populations, evidence.area_name),
                effective_modifiers=_area_effective_modifiers(factual),
                source_refs=response_refs,
            )
        area_rows.append(row)
    area_material_by_name = {
        fact.material_name: fact
        for fact in tuple(
            getattr(
                area_population,
                "material_facts",
                (),
            )
            or ()
        )
    }

    area_rows.extend(
        _typed_out_of_slice_area_disposition(
            scope,
            area_by_name.get(
                scope.area_name
            ),
            (
                area_material_by_name.get(
                    scope.material_name
                )
                if scope.material_name
                is not None
                else None
            ),
        )
        for scope in typed_area_rows
    )
    observed_area_scope = tuple(
        sorted(row.area_name for row in area_rows)
    )
    if observed_area_scope != area_population.expected_area_names:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            "A3 Area disposition population does not exactly reconcile to "
            "the factual AreaObj universe",
        )

    return Eq713PopulationDisposition(
        area_rows=tuple(area_rows),
        frame_rows=tuple(frame_rows),
    ), area_evidence


def _raise_unqualified_a3(whole: Eq713PopulationDisposition, blocker: str = BLOCKER_A3_EQ713_POPULATION):
    blocked = tuple(
        reason
        for row in (*whole.area_rows, *whole.frame_rows)
        for reason in row.blocked_reasons
    )
    raise PublicA5CompositionError(
        blocker,
        "Eq713 whole-system population did not qualify: " + "; ".join(dict.fromkeys(blocked)),
    )


@dataclass(frozen=True, slots=True)
class _ResponseBlockerPartition:
    response_frame_names: tuple[str, ...]
    response_area_names: tuple[str, ...]
    response_eligible_modes: tuple[tuple[str, str, str, str], ...]
    persistent_non_response_blockers: tuple[tuple[str, str, str, str], ...]

    @property
    def unresolved_count(self) -> int:
        return len(self.response_eligible_modes)


def _partition_response_blockers(
    whole: Eq713PopulationDisposition,
    frame_population: FrameEq713FactualPopulation,
    area_evidence: Sequence[AreaGrossBasePropertyEvidence],
) -> _ResponseBlockerPartition:
    """Partition response-owned blockers from unrelated fail-closed A3 blockers.

    This is orchestration classification only. It does not decide engineering
    applicability and does not mutate any disposition.
    """
    roles = {
        fact.frame_name: fact.member_role
        for fact in frame_population.rows
    }
    area_by_name = {
        fact.area_name: fact
        for fact in area_evidence
    }
    frame_names: set[str] = set()
    area_names: set[str] = set()
    eligible: list[tuple[str, str, str, str]] = []
    persistent: list[tuple[str, str, str, str]] = []

    for row in whole.frame_rows:
        for mode in row.mode_dispositions:
            if (
                mode.disposition
                is not ContributorDisposition.BLOCKED_UNSUPPORTED
            ):
                continue
            identity = (
                "FRAME",
                row.component_uid,
                mode.mode.value,
                mode.reason,
            )
            if (
                roles.get(row.component_uid) == "BEAM"
                and "participation in Eq7.13 Delta_i is unresolved"
                in mode.reason
            ):
                frame_names.add(row.component_uid)
                eligible.append(identity)
            else:
                persistent.append(identity)

    for row in whole.area_rows:
        evidence = area_by_name.get(row.area_name)
        for mode in row.mode_dispositions:
            if (
                mode.disposition
                is not ContributorDisposition.BLOCKED_UNSUPPORTED
            ):
                continue
            identity = (
                "AREA",
                row.area_name,
                mode.mode.value,
                mode.reason,
            )
            if isinstance(evidence, AreaGrossBasePropertyEvidence):
                response_eligible = (
                    evidence.category
                    in {
                        AreaCategory.FLOOR,
                        AreaCategory.WALL,
                    }
                    and evidence.formulation
                    is AreaFormulation.SHELL_THICK
                    and evidence.is_concrete
                    and evidence.gross_base_qualified
                    and evidence.homogeneous_simple_property
                    and evidence.object_modifiers_unity
                    and (
                        evidence.category
                        is not AreaCategory.WALL
                        or (
                            evidence
                            .default_wall_local_axes_proven
                            is True
                        )
                    )
                    and mode.mode
                    in _RESPONSE_AREA_MODES
                )
            else:
                # Compatibility-only seam for bounded legacy synthetic tests.
                # Production _build_a3 emits AreaGrossBasePropertyEvidence and
                # therefore always uses the strict branch above.
                response_eligible = (
                    evidence is not None
                    and getattr(
                        evidence,
                        "formulation",
                        None,
                    )
                    is AreaFormulation.SHELL_THICK
                    and bool(
                        getattr(
                            evidence,
                            "homogeneous_simple_property",
                            False,
                        )
                    )
                    and bool(
                        getattr(
                            evidence,
                            "object_modifiers_unity",
                            True,
                        )
                    )
                    and (
                        getattr(
                            evidence,
                            "category",
                            None,
                        )
                        is not AreaCategory.WALL
                        or getattr(
                            evidence,
                            "default_wall_local_axes_proven",
                            True,
                        )
                        is True
                    )
                    and mode.mode
                    in _RESPONSE_AREA_MODES
                )
            if response_eligible:
                area_names.add(row.area_name)
                eligible.append(identity)
            else:
                persistent.append(identity)

    return _ResponseBlockerPartition(
        response_frame_names=tuple(sorted(frame_names)),
        response_area_names=tuple(sorted(area_names)),
        response_eligible_modes=tuple(eligible),
        persistent_non_response_blockers=tuple(persistent),
    )


def _response_probe_scope(
    whole: Eq713PopulationDisposition,
    frame_population: FrameEq713FactualPopulation,
    area_evidence: Sequence[AreaGrossBasePropertyEvidence],
):
    partition = _partition_response_blockers(
        whole,
        frame_population,
        area_evidence,
    )
    if partition.unresolved_count == 0:
        return None
    return (
        partition.response_frame_names,
        partition.response_area_names,
        partition.unresolved_count,
    )


def _response_scope_still_blocked(
    whole: Eq713PopulationDisposition,
    *,
    frame_names: Sequence[str],
    area_names: Sequence[str],
) -> tuple[tuple[str, str, str, str], ...]:
    """Return unresolved blockers that remain inside the chosen response subset."""
    wanted_frames = set(frame_names)
    wanted_areas = set(area_names)
    blocked: list[tuple[str, str, str, str]] = []

    for row in whole.frame_rows:
        if row.component_uid not in wanted_frames:
            continue
        for mode in row.mode_dispositions:
            if (
                mode.disposition
                is ContributorDisposition.BLOCKED_UNSUPPORTED
            ):
                blocked.append(
                    (
                        "FRAME",
                        row.component_uid,
                        mode.mode.value,
                        mode.reason,
                    )
                )

    for row in whole.area_rows:
        if row.area_name not in wanted_areas:
            continue
        for mode in row.mode_dispositions:
            if (
                mode.mode in _RESPONSE_AREA_MODES
                and mode.disposition
                is ContributorDisposition.BLOCKED_UNSUPPORTED
            ):
                blocked.append(
                    (
                        "AREA",
                        row.area_name,
                        mode.mode.value,
                        mode.reason,
                    )
                )
    return tuple(blocked)


def _b4b_targets(frame_population, area_population, frame_rows, area_rows):
    targets = []
    frame_dispositions = {row.component_uid: row for row in frame_rows}
    if len(frame_dispositions) != len(tuple(frame_rows)):
        raise PublicA5CompositionError(BLOCKER_A4_B4B, "duplicate Frame Eq713 disposition identity")

    property_targets: dict[str, FrameModifierVector] = {}
    for fact in frame_population.rows:
        disposition = frame_dispositions.get(fact.frame_name)
        if disposition is None:
            raise PublicA5CompositionError(
                BLOCKER_A4_B4B,
                f"Frame {fact.frame_name!r} has no accepted Eq713 mode disposition",
            )
        section_projection = build_frame_eq713_modifier_target(
            current_modifiers=fact.property_modifiers.modifiers.as_tuple(),
            disposition=disposition,
        )
        section_target = FrameModifierVector.from_sequence(
            tuple(float(value) for value in section_projection.target_modifiers)
        )
        previous = property_targets.get(fact.base_fact.assigned_section_name)
        if previous is not None and previous.as_tuple() != section_target.as_tuple():
            raise PublicA5CompositionError(
                BLOCKER_A4_B4B,
                f"shared Frame section {fact.base_fact.assigned_section_name!r} has contradictory Eq713 target",
            )
        property_targets[fact.base_fact.assigned_section_name] = section_target

        object_projection = build_frame_eq713_modifier_target(
            current_modifiers=fact.object_modifiers.modifiers.as_tuple(),
            disposition=disposition,
        )
        targets.append(
            FrameModifierTargetRequest(
                surface=FrameModifierSurface.FRAME_OBJECT,
                target_name=fact.frame_name,
                modifiers=FrameModifierVector.from_sequence(
                    tuple(float(value) for value in object_projection.target_modifiers)
                ),
            )
        )
    for section, vector in property_targets.items():
        targets.append(
            FrameModifierTargetRequest(
                surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
                target_name=section,
                modifiers=vector,
            )
        )

    area_by_name = {
        row.area_name: row
        for row in area_population.rows
    }

    area_property_candidates: dict[
        str,
        list[tuple[object, AreaModifierVector]],
    ] = {}

    for disposition in area_rows:
        if disposition.target_property_modifiers is None:
            continue

        factual = area_by_name[
            disposition.area_name
        ]

        if factual.property_state is None:
            raise PublicA5CompositionError(
                BLOCKER_A4_B4B,
                "Area target lost factual property identity",
            )

        vector = AreaModifierVector.from_sequence(
            tuple(
                float(value)
                for value
                in disposition.target_property_modifiers
            )
        )

        area_property_candidates.setdefault(
            factual.property_name,
            [],
        ).append(
            (
                disposition,
                vector,
            )
        )

    inverse_area_slot = {
        slot: mode
        for mode, slot in _AREA_SLOT.items()
    }

    area_property_targets: dict[
        str,
        AreaModifierVector,
    ] = {}

    for (
        property_name,
        candidates,
    ) in area_property_candidates.items():
        vectors = tuple(
            vector.as_tuple()
            for _row, vector
            in candidates
        )

        merged = list(
            vectors[0]
        )

        for slot in range(
            len(merged)
        ):
            values = {
                vector[slot]
                for vector in vectors
            }

            if len(values) == 1:
                continue

            mode = inverse_area_slot.get(
                slot
            )

            if mode is None:
                raise PublicA5CompositionError(
                    BLOCKER_A4_B4B,
                    f"shared Area property "
                    f"{property_name!r} has "
                    "contradictory non-Eq713 modifier target",
                )

            mode_rows = []

            for disposition, vector in candidates:
                matches = tuple(
                    item
                    for item
                    in disposition.mode_dispositions
                    if item.mode is mode
                )

                if len(matches) != 1:
                    raise PublicA5CompositionError(
                        BLOCKER_A4_B4B,
                        f"shared Area property "
                        f"{property_name!r} has "
                        f"incomplete {mode.value} "
                        "disposition evidence",
                    )

                mode_rows.append(
                    (
                        matches[0],
                        vector.as_tuple()[slot],
                    )
                )

            dispositions = {
                item.disposition
                for item, _value
                in mode_rows
            }

            if (
                ContributorDisposition
                .BLOCKED_UNSUPPORTED
                in dispositions
            ):
                raise PublicA5CompositionError(
                    BLOCKER_A4_B4B,
                    f"shared Area property "
                    f"{property_name!r} has "
                    f"unresolved {mode.value} "
                    "target conflict",
                )

            permitted = {
                ContributorDisposition
                .TARGETED_UNCRACKED,
                ContributorDisposition
                .PROVEN_NON_PARTICIPATING_MODE,
                ContributorDisposition
                .PROVEN_NOT_APPLICABLE,
            }

            if not dispositions.issubset(
                permitted
            ):
                raise PublicA5CompositionError(
                    BLOCKER_A4_B4B,
                    f"shared Area property "
                    f"{property_name!r} has "
                    f"unsupported {mode.value} "
                    "target disposition mixture",
                )

            targeted_values = tuple(
                value
                for item, value
                in mode_rows
                if (
                    item.disposition
                    is ContributorDisposition
                    .TARGETED_UNCRACKED
                )
            )

            if not targeted_values:
                raise PublicA5CompositionError(
                    BLOCKER_A4_B4B,
                    f"shared Area property "
                    f"{property_name!r} has "
                    f"contradictory {mode.value} "
                    "target without a participating user",
                )

            if any(
                value != 1.0
                for value
                in targeted_values
            ):
                raise PublicA5CompositionError(
                    BLOCKER_A4_B4B,
                    f"shared Area property "
                    f"{property_name!r} has "
                    f"non-unity targeted "
                    f"{mode.value} modifier",
                )

            # Property-level normalization is required by at
            # least one positively participating user. Other
            # represented users are already positively proven
            # non-participating / not-applicable in this slot,
            # therefore they impose no competing Eq7.13 target.
            merged[slot] = 1.0

        area_property_targets[
            property_name
        ] = (
            AreaModifierVector.from_sequence(
                tuple(merged)
            )
        )

    for (
        property_name,
        vector,
    ) in area_property_targets.items():
        targets.append(
            AreaModifierTargetRequest(
                surface=(
                    AreaModifierSurface
                    .AREA_PROPERTY
                ),
                target_name=property_name,
                modifiers=vector,
            )
        )
    if not targets:
        raise PublicA5CompositionError(BLOCKER_A4_B4B, "Eq713 population produced no B4B target")
    return tuple(targets)


def _flatten_combo(definition: EtabsComboDefinitionEvidence):
    if definition.combo_type != "LINEAR_ADD":
        raise PublicA5CompositionError(
            BLOCKER_A5_INPUT_MATERIALIZATION,
            f"selected response combo {definition.name!r} has unsupported type {definition.combo_type!r}",
        )
    children = {item.name: item for item in definition.nested_combos}
    leaves = []
    for item in definition.constituents:
        if item.cname_type == "LOAD_CASE":
            leaves.append((item.name, float(item.scale_factor)))
        elif item.cname_type == "LOAD_COMBO":
            child = children.get(item.name)
            if child is None:
                raise PublicA5CompositionError(
                    BLOCKER_A5_INPUT_MATERIALIZATION,
                    f"nested response combo {item.name!r} is not captured",
                )
            for name, scale in _flatten_combo(child)[1]:
                leaves.append((name, float(item.scale_factor) * scale))
        else:
            raise PublicA5CompositionError(
                BLOCKER_A5_INPUT_MATERIALIZATION,
                f"selected response combo {definition.name!r} has unsupported constituent type {item.cname_type!r}",
            )
    if not leaves:
        raise PublicA5CompositionError(
            BLOCKER_A5_INPUT_MATERIALIZATION,
            f"selected response combo {definition.name!r} has no LOAD_CASE leaves",
        )
    return definition.name, tuple(leaves)


def _combo_scope(context: TrustedLiveAcquisitionContext):
    selection = acquire_actual_concrete_design_combo_selection_from_session(
        context.verified_session,
        model_fingerprint=context.model_fingerprint,
        evidence_epoch_id=context.evidence_epoch_id,
        session_provenance_ref=context.session_provenance_ref,
    )
    if not selection.capture_complete or not selection.rows:
        raise PublicA5CompositionError(
            BLOCKER_A5_INPUT_MATERIALIZATION,
            "actual Concrete Frame Design selected-combo population is empty/incomplete",
        )
    names = tuple(sorted(set(selection.names)))
    if len(names) != len(selection.names):
        raise PublicA5CompositionError(
            BLOCKER_A5_INPUT_MATERIALIZATION,
            "selected design-combo population contains duplicate combo names across factual rows",
        )
    definitions = capture_etabs_combo_definitions_from_session(context.verified_session, names)
    flattened = tuple(_flatten_combo(item) for item in definitions)
    cases = tuple(sorted({name for _combo, leaves in flattened for name, _scale in leaves}))
    if not cases:
        raise PublicA5CompositionError(BLOCKER_A5_INPUT_MATERIALIZATION, "no exact analysis case scope from selected combos")
    return selection, definitions, flattened, cases


def _rank_xy(vectors: Sequence[tuple[float, float]]) -> int:
    if not vectors:
        return 0
    for index, left in enumerate(vectors):
        for right in vectors[index + 1 :]:
            if abs(left[0] * right[1] - left[1] * right[0]) > 1.0e-10:
                return 2
    return 1


def _qualified_linear_static_response_scope(
    context: TrustedLiveAcquisitionContext,
    candidate_case_names: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    auto = capture_etabs_auto_seismic_direction_evidence_from_session(context.verified_session)
    direction_map = tsc2018_horizontal_pattern_directions(auto)
    table_ref = f"ETABS:{TABLE_AUTO_SEISMIC_TSC2018}:FULL"
    broad = qualify_eq713_horizontal_case_scope_from_session(
        context.verified_session,
        candidate_case_names=candidate_case_names,
        tsc2018_pattern_directions=direction_map,
        direction_source_refs=(context.session_provenance_ref, DIRECTION_AUTHORITY, table_ref),
    )
    static = tuple(fact for fact in broad.cases if fact.case_type == "LINEAR_STATIC")
    if not static:
        raise PublicA5CompositionError(
            BLOCKER_A3_MEMBER_RESPONSE,
            "qualified Eq713 response scope contains no LINEAR_STATIC horizontal earthquake case",
        )
    vectors = tuple(vector for fact in static for vector in fact.direction_vectors_xy)
    if _rank_xy(vectors) != 2:
        raise PublicA5CompositionError(
            BLOCKER_A3_MEMBER_RESPONSE,
            "qualified LINEAR_STATIC Eq713 response scope does not span independent global X/Y directions",
        )
    names = tuple(fact.case_name for fact in static)
    refs = tuple(
        dict.fromkeys(
            (
                context.session_provenance_ref,
                DIRECTION_AUTHORITY,
                table_ref,
                *(ref for fact in static for ref in fact.source_refs),
            )
        )
    )
    return names, refs


@dataclass(frozen=True, slots=True)
class _QualifiedResponseCaseAvailability:
    """A3.9B separation of design-demand cases from response-evidence cases."""

    model_case_names: tuple[str, ...]
    design_required_case_names: tuple[str, ...]
    qualified_linear_static_case_names: tuple[str, ...]
    response_evidence_only_case_names: tuple[str, ...]
    b5_requested_case_names: tuple[str, ...]
    direction_rank: int
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "model_case_names",
            "design_required_case_names",
            "qualified_linear_static_case_names",
            "response_evidence_only_case_names",
            "b5_requested_case_names",
            "source_refs",
        ):
            values = tuple(getattr(self, field_name))
            if any(
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
                for value in values
            ):
                raise PublicA5CompositionError(
                    BLOCKER_A3_MEMBER_RESPONSE,
                    f"A3.9B {field_name} contains non-canonical identity",
                )
            if len(values) != len(set(values)):
                raise PublicA5CompositionError(
                    BLOCKER_A3_MEMBER_RESPONSE,
                    f"A3.9B {field_name} contains duplicate identity",
                )
        if self.direction_rank != 2:
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                "A3.9B qualified LINEAR_STATIC response cases must span global X/Y",
            )
        model = set(self.model_case_names)
        design = set(self.design_required_case_names)
        response = set(self.qualified_linear_static_case_names)
        response_only = set(self.response_evidence_only_case_names)
        b5 = set(self.b5_requested_case_names)
        if not design or not response:
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                "A3.9B requires nonempty design and response case populations",
            )
        if not design.issubset(model) or not response.issubset(model):
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                "A3.9B case population is not contained in the factual model universe",
            )
        if response_only != response - design:
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                "A3.9B response-evidence-only population is not exact",
            )
        if b5 != design | response:
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                "A3.9B B5 requested case union is not exact",
            )


def _discover_qualified_response_case_availability(
    context: TrustedLiveAcquisitionContext,
    design_required_case_names: Sequence[str],
) -> _QualifiedResponseCaseAvailability:
    """Discover response evidence independently of design-combo membership."""
    design = tuple(sorted(tuple(design_required_case_names)))
    if not design or len(design) != len(set(design)):
        raise PublicA5CompositionError(
            BLOCKER_A3_MEMBER_RESPONSE,
            "A3.9B design-required case population must be nonempty and duplicate-free",
        )
    try:
        defined = get_defined_analysis_cases_from_session(context.verified_session)
    except Exception as exc:
        raise PublicA5CompositionError(
            BLOCKER_A3_MEMBER_RESPONSE,
            f"A3.9B full factual LoadCases population is unavailable: {exc}",
        ) from exc
    if not defined.success or not defined.case_names:
        raise PublicA5CompositionError(
            BLOCKER_A3_MEMBER_RESPONSE,
            "A3.9B full factual LoadCases population is empty or non-successful",
        )
    model_cases = tuple(defined.case_names)
    missing_design = tuple(sorted(set(design) - set(model_cases)))
    if missing_design:
        raise PublicA5CompositionError(
            BLOCKER_A3_MEMBER_RESPONSE,
            "A3.9B design-required case(s) are absent from the factual model universe: "
            + ", ".join(missing_design),
        )
    qualified, qualification_refs = _qualified_linear_static_response_scope(
        context,
        model_cases,
    )
    qualified = tuple(qualified)
    if not qualified or len(qualified) != len(set(qualified)):
        raise PublicA5CompositionError(
            BLOCKER_A3_MEMBER_RESPONSE,
            "A3.9B qualified LINEAR_STATIC response population is empty or duplicate",
        )
    missing_qualified = tuple(sorted(set(qualified) - set(model_cases)))
    if missing_qualified:
        raise PublicA5CompositionError(
            BLOCKER_A3_MEMBER_RESPONSE,
            "A3.9B qualified response case(s) are absent from the factual model universe: "
            + ", ".join(missing_qualified),
        )
    response_only = tuple(sorted(set(qualified) - set(design)))
    b5_requested = tuple(sorted(set(design) | set(qualified)))
    refs = tuple(
        dict.fromkeys(
            (
                context.session_provenance_ref,
                defined.evidence_ref,
                *qualification_refs,
            )
        )
    )
    return _QualifiedResponseCaseAvailability(
        model_case_names=model_cases,
        design_required_case_names=design,
        qualified_linear_static_case_names=qualified,
        response_evidence_only_case_names=response_only,
        b5_requested_case_names=b5_requested,
        direction_rank=2,
        source_refs=refs,
    )


def _design_required_case_names(
    flattened_combos: Sequence[tuple[str, Sequence[tuple[str, float]]]],
) -> tuple[str, ...]:
    names = tuple(
        sorted(
            {
                case_name
                for _combo_name, leaves in flattened_combos
                for case_name, _scale in leaves
            }
        )
    )
    if not names:
        raise PublicA5CompositionError(
            BLOCKER_A5_INPUT_MATERIALIZATION,
            "selected design combos contain no exact LOAD_CASE leaves",
        )
    return names


def _design_result_populations(execution_result, flattened_combos):
    """Project B5 union results back to immutable design-demand case scope."""
    required = _design_required_case_names(flattened_combos)
    populations = tuple(execution_result.manifest.result_populations)
    by_name = {}
    for population in populations:
        case_name = population.case_name
        if case_name in by_name:
            raise PublicA5CompositionError(
                BLOCKER_A5_INPUT_MATERIALIZATION,
                f"B5 result population contains duplicate case {case_name!r}",
            )
        by_name[case_name] = population
    missing = tuple(name for name in required if name not in by_name)
    if missing:
        raise PublicA5CompositionError(
            BLOCKER_A5_INPUT_MATERIALIZATION,
            "B5 union result population is missing design-required case(s): "
            + ", ".join(missing),
        )
    return tuple(by_name[name] for name in required)


def _analysis_basis_refs(context, owned_scratch, frame_pre, area_pre, a3):
    return tuple(
        dict.fromkeys(
            (
                context.acquisition_context_ref,
                owned_scratch.ownership_proof_ref,
                *frame_pre.source_refs,
                *area_pre.source_refs,
                *(ref for row in a3.frame_rows for ref in row.source_refs),
                *(ref for row in a3.area_rows for ref in row.source_refs),
            )
        )
    )


def _run_a3_generation(
    *,
    context,
    owned_scratch,
    frame_pre,
    area_pre,
    a3,
    requested_cases,
):
    try:
        targets = _b4b_targets(frame_pre, area_pre, a3.frame_rows, a3.area_rows)
        basis_refs = _analysis_basis_refs(context, owned_scratch, frame_pre, area_pre, a3)
        requested_manifest = build_requested_section_modifier_manifest(
            source_model_ref=context.source_model_identity.source_model_ref,
            targets=targets,
            provenance_refs=basis_refs,
        )
        established_state = establish_section_modifier_analysis_state(
            context=context,
            owned_scratch=owned_scratch,
            requested_manifest=requested_manifest,
            additional_state_basis_refs=basis_refs,
        )
    except PublicA5CompositionError:
        raise
    except Exception as exc:
        raise PublicA5CompositionError(BLOCKER_A4_B4B, str(exc)) from exc

    try:
        execution_result = execute_controlled_analysis(
            context=context,
            owned_scratch=owned_scratch,
            established_state=established_state,
            requested_case_names=requested_cases,
        )
        if (
            not execution_result.qualification.qualified
            or execution_result.analysis_result_identity.parent_analysis_state_ref
            != established_state.analysis_state_identity.identity_ref
            or execution_result.manifest.run_analysis.return_code != 0
        ):
            raise PublicA5CompositionError(
                BLOCKER_A4_B5,
                "B5 did not issue exact qualified child AnalysisResultIdentity",
            )
    except PublicA5CompositionError:
        raise
    except Exception as exc:
        raise PublicA5CompositionError(BLOCKER_A4_B5, str(exc)) from exc
    return targets, established_state, execution_result


def _initial_beam_classifications(frame_population, topology, frame_names):
    wanted = set(frame_names)
    return {
        fact.frame_name: classify_frame_eq713_participation(_frame_mechanics_evidence(fact, topology))
        for fact in frame_population.rows
        if fact.member_role == "BEAM" and fact.frame_name in wanted
    }


def _response_true_count(classifications: Mapping[str, FrameModeParticipationClassification]) -> int:
    return sum(
        row.participates is True
        for classification in classifications.values()
        for row in classification.mode_evidence
    )


def _classify_beam_generation(
    *,
    frame_population: FrameEq713FactualPopulation,
    topology: StrictColumnTopologyBundle,
    response: Eq713ResponsePopulationFact,
    established_state,
    previous: Mapping[str, FrameModeParticipationClassification],
) -> dict[str, FrameModeParticipationClassification]:
    mutations = {
        (item.surface, item.target_name): item
        for item in established_state.mutation_manifest.mutations
        if isinstance(item, FrameModifierMutationFact)
    }
    by_name = {fact.frame_name: fact for fact in frame_population.rows}
    result = dict(previous)
    for frame_name in response.frame_names:
        fact = by_name.get(frame_name)
        if fact is None or fact.member_role != "BEAM":
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                f"response Frame {frame_name!r} is not an exact BEAM factual-population member",
            )
        if fact.section_mechanics.section_name != fact.base_fact.assigned_section_name:
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                f"BEAM {frame_name!r} section mechanics identity mismatch",
            )
        if fact.isotropic_material.material_name != fact.base_fact.material_name:
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                f"BEAM {frame_name!r} material identity mismatch",
            )
        section_mutation = mutations.get(
            (FrameModifierSurface.FRAME_SECTION_PROPERTY, fact.base_fact.assigned_section_name)
        )
        object_mutation = mutations.get((FrameModifierSurface.FRAME_OBJECT, frame_name))
        if section_mutation is None or object_mutation is None:
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                f"BEAM {frame_name!r} lacks exact B4B generation modifier readback",
            )
        base = result.get(frame_name)
        if base is None:
            base = classify_frame_eq713_participation(_frame_mechanics_evidence(fact, topology))
        result[frame_name] = classify_frame_response_participation(
            base=base,
            values_by_mode=_frame_response_values((response,), frame_name),
            member_role="BEAM",
            section_mechanics=fact.section_mechanics,
            material_properties=fact.isotropic_material,
            property_modifiers=section_mutation.after,
            object_modifiers=object_mutation.after,
            source_refs=(
                *response.source_refs,
                response.evidence_ref,
                established_state.analysis_state_identity.identity_ref,
                section_mutation.mutation_ref,
                object_mutation.mutation_ref,
            ),
        )
    return result


def _area_shell_thick_generations_from_response(
    *,
    session,
    area_population: AreaContributorPopulation,
    response: Eq713ResponsePopulationFact,
    established_state,
) -> dict[str, AreaShellThickResponseGeneration]:
    mutations = {
        (item.surface, item.target_name): item
        for item in established_state.mutation_manifest.mutations
        if isinstance(item, AreaModifierMutationFact)
    }
    by_name = {fact.area_name: fact for fact in area_population.rows}
    result: dict[str, AreaShellThickResponseGeneration] = {}
    for area_name in response.area_names:
        fact = by_name.get(area_name)
        if fact is None or fact.property_state is None:
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                f"response Area {area_name!r} lost exact factual property identity",
            )
        state = fact.property_state
        if (
            state.family not in {AreaPropertyFamily.WALL, AreaPropertyFamily.SLAB}
            or state.shell_type_code != 2
            or state.thickness is None
            or float(state.thickness) <= 0.0
        ):
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                f"response Area {area_name!r} is outside homogeneous simple SHELL_THICK slice",
            )
        mutation = mutations.get(
            (
                AreaModifierSurface.AREA_PROPERTY,
                fact.property_name,
            )
        )

        if mutation is None:
            try:
                property_readback = (
                    get_area_modifiers_from_session(
                        session,
                        surface=(
                            AreaModifierSurface
                            .AREA_PROPERTY
                        ),
                        target_name=(
                            fact.property_name
                        ),
                    )
                )
            except Exception as exc:
                raise PublicA5CompositionError(
                    BLOCKER_A3_MEMBER_RESPONSE,
                    f"Area {area_name!r} "
                    "post-B5 PropArea modifier "
                    f"readback failed: {exc}",
                ) from exc

            if not property_readback.success:
                raise PublicA5CompositionError(
                    BLOCKER_A3_MEMBER_RESPONSE,
                    f"Area {area_name!r} "
                    "post-B5 PropArea modifier "
                    "readback was non-successful",
                )

            property_readback_refs = (
                "COLUMN_R1_A3_POST_B5_"
                "PROPAREA_READBACK",
                property_readback.evidence_ref,
            )

        else:
            property_readback = (
                mutation.after
            )

            property_readback_refs = (
                mutation.mutation_ref,
                mutation.after.evidence_ref,
            )

        facts = tuple(
            item for item in response.area_strain_results if item.area_name == area_name
        )
        expected = {(area_name, case_name) for case_name in response.case_names}
        actual = {(item.area_name, item.case_name) for item in facts}
        if actual != expected:
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                f"Area {area_name!r} strain population lost exact qualified case binding",
            )
        rows = tuple(row for item in facts for row in item.rows)
        if not rows:
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                f"Area {area_name!r} AreaStrainShell population is empty",
            )
        result[area_name] = (
            AreaShellThickResponseGeneration(
                strain_rows=rows,
                property_modifiers=(
                    property_readback
                ),
                source_refs=(
                    *response.source_refs,
                    response.evidence_ref,
                    established_state
                    .analysis_state_identity
                    .identity_ref,
                    *property_readback_refs,
                ),
            )
        )
    return result


def _area_continuity_key(fact: AreaContributorFact):
    state = fact.property_state
    return (
        fact.area_name,
        fact.orientation,
        fact.property_name,
        None if state is None else state.family,
        None if state is None else state.family_type_code,
        None if state is None else state.shell_type_code,
        None if state is None else state.material_name,
        None if state is None else state.thickness,
        fact.local_axes_angle_degrees,
        fact.advanced_local_axes,
        fact.transformation_matrix,
        fact.raw_material_overwrite_name,
        None if fact.diaphragm_assignment is None else fact.diaphragm_assignment.diaphragm_name,
        None if fact.diaphragm_definition is None else fact.diaphragm_definition.semi_rigid,
        None if fact.wall_assignment is None else fact.wall_assignment.pier_name,
        None if fact.wall_assignment is None else fact.wall_assignment.spandrel_name,
    )


def _strict_topology_semantic_projection(value):
    """Remove provenance-only source rows from topology identity.

    Strict topology ``as_dict()`` intentionally carries the exact ETABS
    display-table rows used to derive each factual topology object. Those
    rows are provenance, not the topology identity itself.

    B4B legitimately changes stiffness-modifier fields such as I2Mod/I3Mod
    in section-definition rows. Modifier continuity is independently owned
    by the B4B/B5 and frame-continuity evidence. Therefore A4 must compare
    the derived topology semantics while preserving the raw source rows
    on the evidence objects for traceability.

    Every non-source-row field remains part of the equality contract.
    """
    if isinstance(value, Mapping):
        return {
            key: _strict_topology_semantic_projection(item)
            for key, item in value.items()
            if key != "source_rows"
        }

    if isinstance(value, (tuple, list)):
        return tuple(
            _strict_topology_semantic_projection(item)
            for item in value
        )

    return value


def _strict_column_topology_semantic_state(column):
    payload = column.as_dict()

    if not isinstance(payload, Mapping):
        raise TypeError(
            "Column topology as_dict() must return a mapping"
        )

    return _strict_topology_semantic_projection(
        payload
    )


def _prove_post_continuity(
    *,
    context,
    owned_scratch,
    topology_pre,
    target_column,
    frame_pre,
    area_pre,
    established_state,
    execution_result,
    verify_full_population: bool = False,
):
    if verify_full_population:
        pre_columns = tuple(topology_pre.columns)
        pre_by_component = {item.component_id: item for item in pre_columns}
        if not pre_columns or len(pre_by_component) != len(pre_columns):
            raise PublicA5CompositionError(
                BLOCKER_A4_POST_CONTINUITY,
                "pre-B5 strict Column population is empty or duplicate",
            )
        frame_by_name = {row.frame_name: row for row in frame_pre.rows}
        for pre_column in pre_columns:
            frame = frame_by_name.get(pre_column.unique_name)
            if frame is None:
                raise PublicA5CompositionError(
                    BLOCKER_A4_POST_CONTINUITY,
                    f"Column {pre_column.component_id!r} is absent from factual Frame population",
                )
            capture_frame_flexural_base_continuity_evidence(
                context=context,
                owned_scratch=owned_scratch,
                pre_fact=frame.base_fact,
                established_state=established_state,
                execution_result=execution_result,
            )
    else:
        capture_frame_flexural_base_continuity_evidence(
            context=context,
            owned_scratch=owned_scratch,
            pre_fact=next(
                row.base_fact
                for row in frame_pre.rows
                if row.frame_name == target_column.unique_name
            ),
            established_state=established_state,
            execution_result=execution_result,
        )

    topology_post_evidence = capture_etabs_strict_column_topology_from_session(
        context.verified_session,
        reviewed_length_unit="m",
    )
    topology_post = topology_post_evidence.topology
    target_post = _target_column(topology_post, target_column.component_id)
    if verify_full_population:
        pre_columns = tuple(topology_pre.columns)
        post_columns = tuple(topology_post.columns)
        pre_by_component = {item.component_id: item for item in pre_columns}
        post_by_component = {item.component_id: item for item in post_columns}
        if (
            len(pre_by_component) != len(pre_columns)
            or len(post_by_component) != len(post_columns)
            or tuple(sorted(pre_by_component)) != tuple(sorted(post_by_component))
        ):
            raise PublicA5CompositionError(
                BLOCKER_A4_POST_CONTINUITY,
                "strict Column population identity changed across A3/B4B/B5 generation",
            )
        for component_id in sorted(pre_by_component):
            if (
                _strict_column_topology_semantic_state(
                    pre_by_component[
                        component_id
                    ]
                )
                !=
                _strict_column_topology_semantic_state(
                    post_by_component[
                        component_id
                    ]
                )
            ):
                raise PublicA5CompositionError(
                    BLOCKER_A4_POST_CONTINUITY,
                    f"Column {component_id!r} strict topology "
                    "changed across A3/B4B/B5 generation",
                )
    elif (
        _strict_column_topology_semantic_state(
            target_post
        )
        !=
        _strict_column_topology_semantic_state(
            target_column
        )
    ):
        raise PublicA5CompositionError(
            BLOCKER_A4_POST_CONTINUITY,
            "target column strict topology changed "
            "across A3/B4B/B5 generation",
        )

    frame_post = capture_frame_eq713_factual_population(context, owned_scratch, topology_post)
    if frame_post.expected_frame_names != frame_pre.expected_frame_names:
        raise PublicA5CompositionError(BLOCKER_A4_POST_CONTINUITY, "Frame population changed after B5")

    pre_line_springs = getattr(
        frame_pre,
        "line_spring_property_universe",
        None,
    )
    post_line_springs = getattr(
        frame_post,
        "line_spring_property_universe",
        None,
    )

    if (pre_line_springs is None) != (post_line_springs is None):
        raise PublicA5CompositionError(
            BLOCKER_A4_POST_CONTINUITY,
            "line-spring property universe availability changed after B5",
        )

    if (
        pre_line_springs is not None
        and post_line_springs is not None
        and pre_line_springs.evidence_ref
        != post_line_springs.evidence_ref
    ):
        raise PublicA5CompositionError(
            BLOCKER_A4_POST_CONTINUITY,
            "line-spring property universe changed after B5",
        )

    pre_by_name = {row.frame_name: row for row in frame_pre.rows}
    for post in frame_post.rows:
        pre = pre_by_name[post.frame_name]
        if (
            post.base_fact.semantic_state_ref != pre.base_fact.semantic_state_ref
            or post.section_mechanics.evidence_ref != pre.section_mechanics.evidence_ref
            or post.releases.evidence_ref != pre.releases.evidence_ref
            or post.isotropic_material.evidence_ref != pre.isotropic_material.evidence_ref
        ):
            raise PublicA5CompositionError(
                BLOCKER_A4_POST_CONTINUITY,
                f"Frame {post.frame_name!r} immutable factual state changed after B5",
            )

    area_post = capture_area_contributor_population_from_session(
        context.verified_session,
        model_fingerprint=context.model_fingerprint,
        evidence_epoch_id=context.evidence_epoch_id,
        session_provenance_ref=context.session_provenance_ref,
        material_snapshot=getattr(
            frame_post,
            "material_snapshot",
            None,
        ),
    )
    if area_post.expected_area_names != area_pre.expected_area_names:
        raise PublicA5CompositionError(BLOCKER_A4_POST_CONTINUITY, "Area population changed after B5")
    pre_area = {row.area_name: row for row in area_pre.rows}
    for post in area_post.rows:
        if _area_continuity_key(post) != _area_continuity_key(pre_area[post.area_name]):
            raise PublicA5CompositionError(
                BLOCKER_A4_POST_CONTINUITY,
                f"Area {post.area_name!r} immutable factual state changed after B5",
            )
    return topology_post, target_post, frame_post, area_post


def _authority(
    *,
    request,
    authority_id,
    key,
    source_kind,
    semantic_type,
    dimension,
    unit,
    value,
    refs,
):
    return ExternalDependencyAuthority(
        authority_id=authority_id,
        key=key,
        source_kind=source_kind,
        semantic_type=semantic_type,
        physical_dimension=dimension,
        grain=Grain.COMPONENT,
        scope_ref=request.component_id,
        direction=None,
        unit=unit,
        availability=AvailabilityState.RESOLVED,
        population_completeness=PopulationCompleteness.FULL,
        value=value,
        provenance_refs=tuple(dict.fromkeys(refs)),
    )


def _a18_required_members(
    *,
    target_column,
    topology,
) -> tuple[tuple[str, object], ...]:
    """Return exact A18 target/connected Frame denominator."""

    members: dict[
        str,
        object,
    ] = {}

    def bind(
        name,
        member,
    ) -> None:
        if (
            not isinstance(name, str)
            or not name.strip()
        ):
            raise PublicA5CompositionError(
                BLOCKER_A5_INPUT_MATERIALIZATION,
                "A18 local-axis denominator "
                "contains invalid Frame identity",
            )

        existing = members.get(
            name
        )

        if (
            existing is not None
            and existing is not member
        ):
            # Same Frame may be represented by two connection objects only
            # if the topology itself duplicated its A18 denominator.
            raise PublicA5CompositionError(
                BLOCKER_A5_INPUT_MATERIALIZATION,
                f"A18 local-axis denominator "
                f"duplicates Frame {name!r}",
            )

        members[
            name
        ] = member

    bind(
        target_column.unique_name,
        target_column,
    )

    end_joints = {
        target_column.joint_bottom,
        target_column.joint_top,
    }

    for column in topology.columns:
        if (
            column.joint_bottom
            in end_joints
            or column.joint_top
            in end_joints
        ):
            bind(
                column.unique_name,
                column,
            )

    for beam in (
        *tuple(
            target_column.beams_at_bottom
            or ()
        ),
        *tuple(
            target_column.beams_at_top
            or ()
        ),
    ):
        bind(
            beam.beam_unique_name,
            beam,
        )

    return tuple(
        sorted(
            members.items(),
            key=lambda item: item[0],
        )
    )


def _capture_a18_frame_local_axis_supplements(
    *,
    context,
    target_column,
    topology,
    cache: dict[
        str,
        A18FrameLocalAxisEvidence | None,
    ],
) -> Mapping[
    str,
    A18FrameLocalAxisEvidence,
]:
    """Acquire only local-axis facts absent from strict topology.

    Explicit display-table local-axis facts remain on their existing
    authority path.  Missing table rows are supplemented from the same
    verified ETABS session through FrameObj.GetLocalAxes.

    Failed reads are not converted into guessed/default axes; the A18
    materializer remains explicitly unresolved for that member.
    """

    supplements: dict[
        str,
        A18FrameLocalAxisEvidence,
    ] = {}

    for (
        frame_name,
        member,
    ) in _a18_required_members(
        target_column=target_column,
        topology=topology,
    ):
        explicit = (
            getattr(
                member,
                "local_axis_explicit",
                False,
            )
            is True
        )

        row = getattr(
            member,
            "local_axis_row",
            None,
        )

        angle = getattr(
            member,
            "local_axis_angle_deg",
            None,
        )

        # Preserve the existing supported table path unchanged.
        if (
            explicit
            and row is not None
            and angle is not None
            and not isinstance(
                angle,
                bool,
            )
        ):
            continue

        if frame_name not in cache:
            try:
                (
                    oapi_angle,
                    advanced,
                    _raw,
                ) = (
                    read_frame_local_axes_from_session(
                        context.verified_session,
                        frame_name,
                    )
                )

                cache[
                    frame_name
                ] = (
                    A18FrameLocalAxisEvidence(
                        frame_name=frame_name,
                        angle_degrees=(
                            oapi_angle
                        ),
                        advanced=advanced,
                        source_refs=(
                            context
                            .session_provenance_ref,

                            _CSI_ETABS_FRAME_LOCAL_AXES_REF,

                            "ETABS:"
                            "FrameObj.GetLocalAxes:"
                            f"{frame_name}:"
                            f"Angle={float(oapi_angle):g}:"
                            f"Advanced={advanced}",
                        ),
                    )
                )

            except Exception:
                # Fail closed at the typed A18 factual edge.  Synthetic
                # compatibility sessions and genuine live read failures
                # do not manufacture a default local axis.
                cache[
                    frame_name
                ] = None

        fact = cache[
            frame_name
        ]

        if fact is not None:
            supplements[
                frame_name
            ] = fact

    return supplements


def _materialize_fnd2_inputs(
    *,
    request,
    context,
    target_column,
    topology_post,
    frame_population,
    flattened_combos,
    selection,
    definitions,
    execution_result,
    reviewed_story_translation_tolerance,
    route_c_w_applicability=None,
    qualified_response_static_case_names=(),
    qualified_response_static_source_refs=(),
    a18_local_axis_cache: dict[
        str,
        A18FrameLocalAxisEvidence | None,
    ] | None = None,
):
    demand_states = []
    demand_refs = []
    target_uid = target_column.unique_name
    design_result_populations = _design_result_populations(
        execution_result,
        flattened_combos,
    )
    for population in design_result_populations:
        states = normalize_etabs_column_end_demands(
            population.rows,
            unique_name=target_uid,
            component_id=request.component_id,
            reviewed_force_unit="kN",
            reviewed_moment_unit="kN-m",
            axial_sign_policy=ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
        )
        demand_states.extend(states)
        demand_refs.append(population.evidence_ref)
    if not demand_states:
        raise PublicA5CompositionError(BLOCKER_A5_INPUT_MATERIALIZATION, "B5 produced no target-column demand state")
    demand_payload = tuple(asdict(state) for state in demand_states)

    combo_payload = tuple(
        {
            "name": combo_name,
            "combo_type": "LINEAR_ADD",
            "constituents": tuple(
                {
                    "name": case_name,
                    "scale_factor": scale,
                    "cname_type": "LOAD_CASE",
                }
                for case_name, scale in leaves
            ),
        }
        for combo_name, leaves in flattened_combos
    )

    if a18_local_axis_cache is None:
        a18_local_axis_cache = {}

    a18_local_axes = (
        _capture_a18_frame_local_axis_supplements(
            context=context,
            target_column=target_column,
            topology=topology_post,
            cache=a18_local_axis_cache,
        )
    )

    a18 = materialize_ts500_column_end_restraint_ratios(
        target_column=target_column,
        topology=topology_post,
        frame_population=frame_population,
        frame_local_axes=a18_local_axes,
    )
    expected_a18_keys = (
        ("BOTTOM", "M2"),
        ("BOTTOM", "M3"),
        ("TOP", "M2"),
        ("TOP", "M3"),
    )
    actual_a18_keys = tuple((item.end_tag, item.local_bending_axis) for item in a18)
    if actual_a18_keys != expected_a18_keys:
        raise PublicA5CompositionError(
            BLOCKER_A5_INPUT_MATERIALIZATION,
            f"A18 materialization returned unexpected end/axis population {actual_a18_keys!r}",
        )
    a18_refs = tuple(dict.fromkeys(ref for item in a18 for ref in item.source_refs))

    try:
        restraints = capture_etabs_column_endpoint_restraints_from_session(
            context.verified_session,
            target_column,
        )
        free_length = resolve_ts500_column_free_length(
            target_column,
            bottom_restraint_dofs=restraints.bottom.dofs,
            top_restraint_dofs=restraints.top.dofs,
            bottom_restraint_source_ref=restraints.bottom.source_ref,
            top_restraint_source_ref=restraints.top.source_ref,
        )
    except Exception:
        free_length = None

    canonical_second_order = build_public_a5_canonical_second_order_payload(
        component_id=request.component_id,
        session=context.verified_session,
        topology=topology_post,
        target_column=target_column,
        frame_population=frame_population,
        flattened_combos=flattened_combos,
        constituent_case_demands=tuple(demand_states),
        a18_rows=a18,
        free_length=free_length,
        analysis_execution=execution_result,
        route_c_w_applicability=route_c_w_applicability,
        qualified_response_static_case_names=qualified_response_static_case_names,
        qualified_response_static_source_refs=qualified_response_static_source_refs,
        reviewed_story_translation_tolerance=reviewed_story_translation_tolerance,
    )

    stiffness = build_assigned_rc_frame_bending_modifier_evidence(topology_post)
    stiffness_payload = tuple(
        {
            "section_name": item.section_name,
            "member_kind": item.member_kind,
            "i2_modifier": item.i2_modifier,
            "i3_modifier": item.i3_modifier,
            "source_refs": tuple(item.source_refs),
        }
        for item in stiffness
    )

    analysis_result_ref = execution_result.analysis_result_identity.identity_ref
    combo_refs = (*selection.source_refs, *(f"ETABS:RespCombo:{item.name}" for item in definitions))
    common_refs = (
        context.acquisition_context_ref,
        context.session_provenance_ref,
        analysis_result_ref,
        execution_result.execution_proof_ref,
    )
    authorities = (
        _authority(
            request=request,
            authority_id=f"public-a5:{request.component_id}:width",
            key=WIDTH_MM_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.COLUMN_WIDTH,
            dimension=PhysicalDimension.LENGTH,
            unit=UNIT_MM,
            value=float(target_column.width_t2_m * 1000.0),
            refs=(*common_refs, f"strict-topology:{target_uid}:t2"),
        ),
        _authority(
            request=request,
            authority_id=f"public-a5:{request.component_id}:depth",
            key=DEPTH_MM_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.COLUMN_DEPTH,
            dimension=PhysicalDimension.LENGTH,
            unit=UNIT_MM,
            value=float(target_column.depth_t3_m * 1000.0),
            refs=(*common_refs, f"strict-topology:{target_uid}:t3"),
        ),
        _authority(
            request=request,
            authority_id=f"public-a5:{request.component_id}:combos",
            key=COMBO_DEFINITIONS_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.DIMENSIONLESS,
            unit=UNIT_DIMENSIONLESS,
            value=combo_payload,
            refs=(*common_refs, *combo_refs),
        ),
        _authority(
            request=request,
            authority_id=f"public-a5:{request.component_id}:demands",
            key=CASE_DEMANDS_KEY,
            source_kind=DependencySourceKind.SOURCE_POPULATION,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.DIMENSIONLESS,
            unit=UNIT_DIMENSIONLESS,
            value=demand_payload,
            refs=(*common_refs, *demand_refs),
        ),
        _authority(
            request=request,
            authority_id=f"public-a5:{request.component_id}:slenderness",
            key=SLENDERNESS_EVIDENCE_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.DIMENSIONLESS,
            unit=UNIT_DIMENSIONLESS,
            value=canonical_second_order,
            refs=(
                *common_refs,
                *tuple(canonical_second_order.get("source_refs", ())),
                *a18_refs,
            ),
        ),
        _authority(
            request=request,
            authority_id=f"public-a5:{request.component_id}:stiffness",
            key=STIFFNESS_EVIDENCE_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.DIMENSIONLESS,
            unit=UNIT_DIMENSIONLESS,
            value=stiffness_payload,
            refs=(*common_refs, *(ref for item in stiffness for ref in item.source_refs)),
        ),
    )
    inputs = RegulatoryCompileInputs(
        rule_targets=(
            RuleScopeTarget(
                rule_id=RULE_ID,
                grain=Grain.COMPONENT,
                scope_ref=request.component_id,
                applicability_input=ColumnDesignReadinessApplicabilityInput(True),
                analysis_basis_status=AnalysisBasisStatus.MATCH,
            ),
        ),
        external_authorities=authorities,
    )
    return inputs, free_length, canonical_second_order


def _new_positive_response_participation_facts(
    previous: Eq713PopulationDisposition,
    resolved: Eq713PopulationDisposition,
    *,
    frame_names: Sequence[str],
    area_names: Sequence[str],
) -> frozenset[tuple[str, str, str]] | None:
    """Return exact response-scope BLOCKED->TARGETED facts learned this generation.

    ``None`` is retained only for legacy synthetic bounded tests that do not
    construct the production ``Eq713PopulationDisposition`` type. Production
    PUBLIC-A5 always supplies the typed whole-system population.
    """
    if not isinstance(previous, Eq713PopulationDisposition) or not isinstance(
        resolved, Eq713PopulationDisposition
    ):
        return None

    wanted_frames = set(frame_names)
    wanted_areas = set(area_names)
    before: dict[tuple[str, str, str], ContributorDisposition] = {}
    after: dict[tuple[str, str, str], ContributorDisposition] = {}

    for whole, target in ((previous, before), (resolved, after)):
        for row in whole.frame_rows:
            if row.component_uid not in wanted_frames:
                continue
            for mode in row.mode_dispositions:
                target[("FRAME", row.component_uid, mode.mode.value)] = mode.disposition
        for row in whole.area_rows:
            if row.area_name not in wanted_areas:
                continue
            for mode in row.mode_dispositions:
                target[("AREA", row.area_name, mode.mode.value)] = mode.disposition

    return frozenset(
        identity
        for identity, disposition in after.items()
        if disposition is ContributorDisposition.TARGETED_UNCRACKED
        and before.get(identity) is ContributorDisposition.BLOCKED_UNSUPPORTED
    )


def _legacy_area_response_closure(
    *,
    context,
    owned_scratch,
    frame_pre,
    area_pre,
    topology_pre,
    provisional_a3,
    frame_names,
    area_names,
    unresolved_count,
    requested_cases,
    qualified_static_cases,
    qualified_static_refs,
):
    """Existing bounded A3 fixed point extended to ShellThick AreaStrainShell facts."""
    current_a3 = provisional_a3
    classifications = _initial_beam_classifications(frame_pre, topology_pre, frame_names)
    area_history: dict[str, list[AreaShellThickResponseGeneration]] = {
        area_name: [] for area_name in area_names
    }
    response_populations: list[Eq713ResponsePopulationFact] = []
    established_state = None
    execution_result = None

    for _generation_index in range(unresolved_count + 1):
        current_targets, established_state, execution_result = _run_a3_generation(
            context=context,
            owned_scratch=owned_scratch,
            frame_pre=frame_pre,
            area_pre=area_pre,
            a3=current_a3,
            requested_cases=requested_cases,
        )
        try:
            response = capture_eq713_response_population_from_session(
                context.verified_session,
                model_fingerprint=context.model_fingerprint,
                evidence_epoch_id=context.evidence_epoch_id,
                analysis_result_ref=execution_result.analysis_result_identity.identity_ref,
                execution_proof_ref=execution_result.execution_proof_ref,
                case_names=qualified_static_cases,
                frame_names=frame_names,
                area_names=area_names,
                case_scope_refs=qualified_static_refs,
            )
        except Exception as exc:
            raise PublicA5CompositionError(BLOCKER_A3_MEMBER_RESPONSE, str(exc)) from exc
        if (
            response.model_fingerprint != context.model_fingerprint
            or response.evidence_epoch_id != context.evidence_epoch_id
            or response.analysis_result_ref != execution_result.analysis_result_identity.identity_ref
            or response.execution_proof_ref != execution_result.execution_proof_ref
            or response.case_names != tuple(qualified_static_cases)
            or response.frame_names != tuple(frame_names)
            or response.area_names != tuple(area_names)
        ):
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                "Eq713 Shell/Frame response population lost exact model/epoch/B5/qualified-static binding",
            )
        response_populations.append(response)

        if frame_names:
            classifications = _classify_beam_generation(
                frame_population=frame_pre,
                topology=topology_pre,
                response=response,
                established_state=established_state,
                previous=classifications,
            )
        if area_names:
            generation_facts = (
                _area_shell_thick_generations_from_response(
                    session=(
                        context.verified_session
                    ),
                    area_population=area_pre,
                    response=response,
                    established_state=(
                        established_state
                    ),
                )
            )
            for area_name, generation in generation_facts.items():
                area_history[area_name].append(generation)

        resolved_a3, _ = _build_a3(
            frame_population=frame_pre,
            area_population=area_pre,
            topology=topology_pre,
            frame_classifications=classifications,
            response_populations=tuple(response_populations),
            area_response_generations=area_history,
        )
        next_targets = _b4b_targets(
            frame_pre,
            area_pre,
            resolved_a3.frame_rows,
            resolved_a3.area_rows,
        )
        if next_targets == current_targets:
            still_blocked = _response_scope_still_blocked(
                resolved_a3,
                frame_names=frame_names,
                area_names=area_names,
            )
            if still_blocked:
                detail = "; ".join(
                    f"{kind}:{name}:{mode}:{reason}"
                    for kind, name, mode, reason in still_blocked
                )
                raise PublicA5CompositionError(
                    BLOCKER_A3_MEMBER_RESPONSE,
                    "A3 response-eligible subset remains unresolved at "
                    f"stable target: {detail}",
                )
            return resolved_a3, established_state, execution_result
        new_positive = _new_positive_response_participation_facts(
            current_a3,
            resolved_a3,
            frame_names=frame_names,
            area_names=area_names,
        )
        if new_positive is not None and not new_positive:
            raise PublicA5CompositionError(
                BLOCKER_A3_MEMBER_RESPONSE,
                "A3 mixed target changed without learning a new positive Frame/Area response participation mode",
            )
        current_a3 = resolved_a3

    raise PublicA5CompositionError(
        BLOCKER_A3_MEMBER_RESPONSE,
        "bounded ShellThick response-mode closure did not reach a stable Eq713 target",
    )


def _materialize_public_a5_column(
    *,
    request: ColumnExecutionRequest,
    context: TrustedLiveAcquisitionContext,
    target_column,
    topology_post,
    frame_post,
    flattened_combos,
    selection,
    definitions,
    execution_result,
    execute_fnd2: Callable[..., object],
    reviewed_story_translation_tolerance: ReviewedStoryTranslationTolerance | None,
    route_c_w_applicability: BoundColumnActionFamilyApplicability | None = None,
    qualified_response_static_case_names=(),
    qualified_response_static_source_refs=(),
    a18_local_axis_cache: dict[
        str,
        A18FrameLocalAxisEvidence | None,
    ] | None = None,
) -> PublicA5ColumnMaterialization:
    inputs, free_length, canonical_second_order = _materialize_fnd2_inputs(
        request=request,
        context=context,
        target_column=target_column,
        topology_post=topology_post,
        frame_population=frame_post,
        flattened_combos=flattened_combos,
        selection=selection,
        definitions=definitions,
        execution_result=execution_result,
        reviewed_story_translation_tolerance=reviewed_story_translation_tolerance,
        route_c_w_applicability=route_c_w_applicability,
        qualified_response_static_case_names=qualified_response_static_case_names,
        qualified_response_static_source_refs=qualified_response_static_source_refs,
        a18_local_axis_cache=a18_local_axis_cache,
    )
    column = execute_fnd2(
        request,
        model_fingerprint=context.model_fingerprint,
        evidence_epoch_id=context.evidence_epoch_id,
        fnd_col_2_inputs=inputs,
    )
    return PublicA5ColumnMaterialization(
        request=request,
        column=column,
        free_length=free_length,
        canonical_second_order=canonical_second_order,
    )


def execute_public_a5_column(
    request: ColumnExecutionRequest,
    *,
    acquisition_context: TrustedLiveAcquisitionContext,
    execute_fnd2: Callable[..., object],
    route_c_w_applicability: BoundColumnActionFamilyApplicability | None = None,
    reviewed_story_translation_tolerance: ReviewedStoryTranslationTolerance | None = None,
    complete_after_fnd2: Callable[..., object] | None = None,
    materialize_full_population: bool = False,
):
    """Compose the supported production path through REAL existing FND-COL-2."""
    if not isinstance(request, ColumnExecutionRequest):
        raise TypeError("request must be ColumnExecutionRequest")
    if not isinstance(acquisition_context, TrustedLiveAcquisitionContext):
        raise TypeError("acquisition_context must be TrustedLiveAcquisitionContext")
    if not callable(execute_fnd2):
        raise TypeError("execute_fnd2 must be callable")
    if (
        route_c_w_applicability is not None
        and not isinstance(
            route_c_w_applicability,
            BoundColumnActionFamilyApplicability,
        )
    ):
        raise TypeError(
            "route_c_w_applicability must be "
            "BoundColumnActionFamilyApplicability or None"
        )

    if reviewed_story_translation_tolerance is not None and not isinstance(
        reviewed_story_translation_tolerance, ReviewedStoryTranslationTolerance
    ):
        raise TypeError(
            "reviewed_story_translation_tolerance must be ReviewedStoryTranslationTolerance or None"
        )
    if complete_after_fnd2 is not None and not callable(complete_after_fnd2):
        raise TypeError("complete_after_fnd2 must be callable when provided")
    if type(materialize_full_population) is not bool:
        raise TypeError("materialize_full_population must be bool")
    if materialize_full_population and complete_after_fnd2 is not None:
        raise TypeError(
            "full-population PUBLIC-A5 must defer B6 to the population composer"
        )
    context = acquisition_context

    owned_scratch = None
    topology_pre = None
    try:
        owned_scratch = create_owned_scratch_context(context)
        topology_pre_evidence = capture_etabs_strict_column_topology_from_session(
            context.verified_session,
            reviewed_length_unit="m",
        )
        topology_pre = topology_pre_evidence.topology
        if materialize_full_population:
            factual_component_ids = tuple(
                item.component_id for item in topology_pre.columns
            )
            if not factual_component_ids:
                return _unknown_population(
                    request,
                    context,
                    BLOCKER_A5_POPULATION_UNKNOWN,
                )
            if len(factual_component_ids) != len(set(factual_component_ids)):
                return _unknown_population(
                    request,
                    context,
                    BLOCKER_A5_DUPLICATE_COMPONENT,
                )
            if request.component_id not in factual_component_ids:
                return _known_blocked_population(
                    request,
                    context,
                    topology_pre,
                    BLOCKER_A5_REQUESTED_FOCUS_ABSENT,
                    owned_scratch=owned_scratch,
                )
        target_column = _target_column(topology_pre, request.component_id)
        frame_pre = capture_frame_eq713_factual_population(context, owned_scratch, topology_pre)
        area_pre = capture_area_contributor_population_from_session(
            context.verified_session,
            model_fingerprint=context.model_fingerprint,
            evidence_epoch_id=context.evidence_epoch_id,
            session_provenance_ref=context.session_provenance_ref,
            material_snapshot=getattr(
                frame_pre,
                "material_snapshot",
                None,
            ),
        )
    except PublicA5CompositionError as exc:
        if materialize_full_population:
            return _population_failure(
                request,
                context,
                topology_pre,
                exc.blocker,
                owned_scratch=owned_scratch,
            )
        return _blocked(request, context, exc.blocker)
    except Exception:
        if materialize_full_population:
            return _population_failure(
                request,
                context,
                topology_pre,
                BLOCKER_A3_FACTUAL_ACQUISITION,
                owned_scratch=owned_scratch,
            )
        return _blocked(request, context, BLOCKER_A3_FACTUAL_ACQUISITION)

    try:
        provisional_a3, area_evidence = _build_a3(
            frame_population=frame_pre,
            area_population=area_pre,
            topology=topology_pre,
        )
        probe_scope = None if provisional_a3.positive else _response_probe_scope(
            provisional_a3,
            frame_pre,
            area_evidence,
        )
        if not provisional_a3.positive and probe_scope is None:
            _raise_unqualified_a3(provisional_a3)
        if probe_scope is not None:
            frame_names, area_names, _unresolved_count = probe_scope
            try:
                probe_eq713_response_population_capability(
                    context.verified_session,
                    require_frame=bool(frame_names),
                    require_area=bool(area_names),
                )
            except TypeError:
                _raise_unqualified_a3(provisional_a3)
            except Exception as exc:
                raise PublicA5CompositionError(BLOCKER_A3_MEMBER_RESPONSE, str(exc)) from exc
        selection, definitions, flattened_combos, design_requested_cases = _combo_scope(context)
        qualified_static_cases = ()
        qualified_static_refs = ()
        b5_requested_cases = design_requested_cases
        response_case_availability = None
        if probe_scope is not None:
            response_case_availability = _discover_qualified_response_case_availability(
                context,
                design_requested_cases,
            )
            qualified_static_cases = response_case_availability.qualified_linear_static_case_names
            qualified_static_refs = response_case_availability.source_refs
            b5_requested_cases = response_case_availability.b5_requested_case_names
    except PublicA5CompositionError as exc:
        if materialize_full_population:
            return _known_blocked_population(
                request,
                context,
                topology_pre,
                exc.blocker,
                owned_scratch=owned_scratch,
            )
        return _blocked(request, context, exc.blocker)
    except Exception:
        if materialize_full_population:
            return _known_blocked_population(
                request,
                context,
                topology_pre,
                BLOCKER_A3_EQ713_POPULATION,
                owned_scratch=owned_scratch,
            )
        return _blocked(request, context, BLOCKER_A3_EQ713_POPULATION)

    try:
        if provisional_a3.positive:
            a3 = provisional_a3
            _targets, established_state, execution_result = _run_a3_generation(
                context=context,
                owned_scratch=owned_scratch,
                frame_pre=frame_pre,
                area_pre=area_pre,
                a3=a3,
                requested_cases=b5_requested_cases,
            )
        else:
            frame_names, area_names, unresolved_count = probe_scope
            if area_names:
                a3, established_state, execution_result = _legacy_area_response_closure(
                    context=context,
                    owned_scratch=owned_scratch,
                    frame_pre=frame_pre,
                    area_pre=area_pre,
                    topology_pre=topology_pre,
                    provisional_a3=provisional_a3,
                    frame_names=frame_names,
                    area_names=area_names,
                    unresolved_count=unresolved_count,
                    requested_cases=b5_requested_cases,
                    qualified_static_cases=qualified_static_cases,
                    qualified_static_refs=qualified_static_refs,
                )
            else:
                current_a3 = provisional_a3
                classifications = _initial_beam_classifications(frame_pre, topology_pre, frame_names)
                established_state = None
                execution_result = None
                for _generation_index in range(unresolved_count + 1):
                    current_targets, established_state, execution_result = _run_a3_generation(
                        context=context,
                        owned_scratch=owned_scratch,
                        frame_pre=frame_pre,
                        area_pre=area_pre,
                        a3=current_a3,
                        requested_cases=b5_requested_cases,
                    )
                    try:
                        response = capture_eq713_response_population_from_session(
                            context.verified_session,
                            model_fingerprint=context.model_fingerprint,
                            evidence_epoch_id=context.evidence_epoch_id,
                            analysis_result_ref=execution_result.analysis_result_identity.identity_ref,
                            execution_proof_ref=execution_result.execution_proof_ref,
                            case_names=qualified_static_cases,
                            frame_names=frame_names,
                            area_names=(),
                            case_scope_refs=qualified_static_refs,
                        )
                    except Exception as exc:
                        raise PublicA5CompositionError(BLOCKER_A3_MEMBER_RESPONSE, str(exc)) from exc
                    if (
                        response.model_fingerprint != context.model_fingerprint
                        or response.evidence_epoch_id != context.evidence_epoch_id
                        or response.analysis_result_ref != execution_result.analysis_result_identity.identity_ref
                        or response.execution_proof_ref != execution_result.execution_proof_ref
                        or response.case_names != tuple(qualified_static_cases)
                    ):
                        raise PublicA5CompositionError(
                            BLOCKER_A3_MEMBER_RESPONSE,
                            "Eq713 Frame response population lost exact model/epoch/B5/qualified-static binding",
                        )
                    before_true = _response_true_count(classifications)
                    classifications = _classify_beam_generation(
                        frame_population=frame_pre,
                        topology=topology_pre,
                        response=response,
                        established_state=established_state,
                        previous=classifications,
                    )
                    after_true = _response_true_count(classifications)
                    resolved_a3, _ = _build_a3(
                        frame_population=frame_pre,
                        area_population=area_pre,
                        topology=topology_pre,
                        frame_classifications=classifications,
                    )
                    next_targets = _b4b_targets(
                        frame_pre,
                        area_pre,
                        resolved_a3.frame_rows,
                        resolved_a3.area_rows,
                    )
                    if next_targets == current_targets:
                        still_blocked = _response_scope_still_blocked(
                            resolved_a3,
                            frame_names=frame_names,
                            area_names=(),
                        )
                        if still_blocked:
                            detail = "; ".join(
                                f"{kind}:{name}:{mode}:{reason}"
                                for kind, name, mode, reason in still_blocked
                            )
                            raise PublicA5CompositionError(
                                BLOCKER_A3_MEMBER_RESPONSE,
                                "A3 response-eligible subset remains unresolved "
                                f"at stable target: {detail}",
                            )
                        a3 = resolved_a3
                        break
                    if after_true <= before_true:
                        raise PublicA5CompositionError(
                            BLOCKER_A3_MEMBER_RESPONSE,
                            "A3 Frame target changed without learning a new positive response participation mode",
                        )
                    current_a3 = resolved_a3
                else:
                    raise PublicA5CompositionError(
                        BLOCKER_A3_MEMBER_RESPONSE,
                        "bounded Frame response-mode closure did not reach a stable Eq713 target",
                    )
                if established_state is None or execution_result is None:
                    raise PublicA5CompositionError(
                        BLOCKER_A3_MEMBER_RESPONSE,
                        "Frame response-mode closure produced no qualified final B5 generation",
                    )

        # Response-subset convergence is intentionally independent of whole-A3
        # qualification. Once the response-owned subset is closed, let the
        # normal whole-A3 authority surface any persistent unrelated blocker.
        if not a3.positive:
            _raise_unqualified_a3(a3)
    except PublicA5CompositionError as exc:
        if materialize_full_population:
            return _known_blocked_population(
                request,
                context,
                topology_pre,
                exc.blocker,
                owned_scratch=owned_scratch,
            )
        return _blocked(request, context, exc.blocker)
    except Exception:
        if materialize_full_population:
            return _known_blocked_population(
                request,
                context,
                topology_pre,
                BLOCKER_A4_B5,
                owned_scratch=owned_scratch,
            )
        return _blocked(request, context, BLOCKER_A4_B5)

    try:
        topology_post, target_post, frame_post, _area_post = _prove_post_continuity(
            context=context,
            owned_scratch=owned_scratch,
            topology_pre=topology_pre,
            target_column=target_column,
            frame_pre=frame_pre,
            area_pre=area_pre,
            established_state=established_state,
            execution_result=execution_result,
            verify_full_population=materialize_full_population,
        )
    except PublicA5CompositionError as exc:
        if materialize_full_population:
            return _known_blocked_population(
                request,
                context,
                topology_pre,
                exc.blocker,
                owned_scratch=owned_scratch,
            )
        return _blocked(request, context, exc.blocker)
    except Exception:
        if materialize_full_population:
            return _known_blocked_population(
                request,
                context,
                topology_pre,
                BLOCKER_A4_POST_CONTINUITY,
                owned_scratch=owned_scratch,
            )
        return _blocked(request, context, BLOCKER_A4_POST_CONTINUITY)

    a18_local_axis_cache: dict[
        str,
        A18FrameLocalAxisEvidence | None,
    ] = {}

    if materialize_full_population:
        materializations: list[PublicA5ColumnMaterialization] = []
        for target in tuple(topology_post.columns):
            component_request = (
                request
                if target.component_id == request.component_id
                else ColumnExecutionRequest(target.component_id)
            )
            try:
                materialized = _materialize_public_a5_column(
                    request=component_request,
                    context=context,
                    target_column=target,
                    topology_post=topology_post,
                    frame_post=frame_post,
                    flattened_combos=flattened_combos,
                    selection=selection,
                    definitions=definitions,
                    execution_result=execution_result,
                    execute_fnd2=execute_fnd2,
                    reviewed_story_translation_tolerance=reviewed_story_translation_tolerance,
                    route_c_w_applicability=route_c_w_applicability,
                    qualified_response_static_case_names=qualified_static_cases,
                    qualified_response_static_source_refs=qualified_static_refs,
                    a18_local_axis_cache=a18_local_axis_cache,
                )
            except PublicA5CompositionError as exc:
                materialized = PublicA5ColumnMaterialization(
                    request=component_request,
                    column=_blocked_component(
                        target.component_id,
                        context,
                        exc.blocker,
                    ),
                    free_length=None,
                    canonical_second_order=None,
                )
            except Exception:
                materialized = PublicA5ColumnMaterialization(
                    request=component_request,
                    column=_blocked_component(
                        target.component_id,
                        context,
                        BLOCKER_A5_INPUT_MATERIALIZATION,
                    ),
                    free_length=None,
                    canonical_second_order=None,
                )
            materializations.append(materialized)

        return PublicA5PopulationExecution(
            population_state=ColumnPopulationState.KNOWN,
            acquisition_context=context,
            focus_component_id=request.component_id,
            focus_present=True,
            topology=topology_post,
            owned_scratch=owned_scratch,
            analysis_execution=execution_result,
            selected_combo_population=selection,
            combo_definitions=tuple(definitions),
            flattened_combos=tuple(flattened_combos),
            columns=tuple(materializations),
        )

    try:
        materialized = _materialize_public_a5_column(
            request=request,
            context=context,
            target_column=target_post,
            topology_post=topology_post,
            frame_post=frame_post,
            flattened_combos=flattened_combos,
            selection=selection,
            definitions=definitions,
            execution_result=execution_result,
            execute_fnd2=execute_fnd2,
            reviewed_story_translation_tolerance=reviewed_story_translation_tolerance,
            route_c_w_applicability=route_c_w_applicability,
            qualified_response_static_case_names=qualified_static_cases,
            qualified_response_static_source_refs=qualified_static_refs,
            a18_local_axis_cache=a18_local_axis_cache,
        )
        column = materialized.column
    except PublicA5CompositionError as exc:
        return _blocked(request, context, exc.blocker)
    except Exception:
        return _blocked(request, context, BLOCKER_A5_INPUT_MATERIALIZATION)

    if complete_after_fnd2 is None or getattr(column, "status", None) != "READY":
        return column
    return complete_after_fnd2(
        column,
        acquisition_context=context,
        owned_scratch=owned_scratch,
        analysis_execution=execution_result,
        topology=topology_post,
        selected_combo_population=selection,
        combo_definitions=definitions,
        flattened_combos=flattened_combos,
        free_length=materialized.free_length,
        canonical_second_order=materialized.canonical_second_order,
    )


__all__ = [
    "BLOCKER_A3_EQ713_POPULATION",
    "BLOCKER_A3_FACTUAL_ACQUISITION",
    "BLOCKER_A3_MEMBER_RESPONSE",
    "BLOCKER_A4_B4B",
    "BLOCKER_A4_B5",
    "BLOCKER_A4_POST_CONTINUITY",
    "BLOCKER_A5_INPUT_MATERIALIZATION",
    "BLOCKER_A5_POPULATION_UNKNOWN",
    "BLOCKER_A5_DUPLICATE_COMPONENT",
    "BLOCKER_A5_REQUESTED_FOCUS_ABSENT",
    "PublicA5ColumnMaterialization",
    "PublicA5PopulationExecution",
    "PublicA5CompositionError",
    "execute_public_a5_column",
]
