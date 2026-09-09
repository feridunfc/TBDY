"""COLUMN-R1 PUBLIC-A5 production composer.

This module owns composition only.  Engineering semantics stay in the existing
Eq7.13 and FND-COL-2 authorities; ETABS mutation and RunAnalysis stay in the
existing B4B/B5 owners.  The composer binds one trusted acquisition generation
to those authorities and fails closed at an exact causal edge.
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Callable, Mapping, Sequence

from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    AreaCategory,
    AreaFormulation,
    AreaGrossBasePropertyEvidence,
    Eq713PopulationDisposition,
    FrameStiffnessMode,
    WallRole,
    audit_frame_eq713_modes,
    build_area_eq713_target,
    build_concrete_uncracked_material_basis,
)
from tbdy_engine.analysis_basis.frame_gross_flexural_basis import (
    capture_frame_flexural_base_continuity_evidence,
)
from tbdy_engine.application.contracts import ColumnExecutionRequest
from tbdy_engine.design.columns.free_length_basis import resolve_ts500_column_free_length
from tbdy_engine.design.columns.rebar_selection import (
    ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
    normalize_etabs_column_end_demands,
)
from tbdy_engine.etabs.oapi.area_contributors import AreaDesignOrientation
from tbdy_engine.etabs.oapi.area_modifiers import AreaModifierSurface, AreaModifierVector
from tbdy_engine.etabs.oapi.frame_modifiers import FrameModifierSurface, FrameModifierVector
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence, StrictColumnTopologyBundle
from tbdy_engine.integration.etabs_analysis_execution import execute_controlled_analysis
from tbdy_engine.integration.etabs_analysis_state_mutation import (
    AreaModifierTargetRequest,
    FrameModifierTargetRequest,
    build_requested_section_modifier_manifest,
    establish_section_modifier_analysis_state,
)
from tbdy_engine.integration.etabs_scratch_lifecycle import create_owned_scratch_context
from tbdy_engine.integration.live_etabs_acquisition_context import TrustedLiveAcquisitionContext
from tbdy_engine.providers.column_slenderness_evidence_provider import (
    build_factual_slenderness_evidence_from_topology,
)
from tbdy_engine.providers.etabs_area_contributor_provider import (
    AreaContributorFact,
    AreaContributorPopulation,
    AreaPropertyFamily,
    capture_area_contributor_population_from_session,
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
from tbdy_engine.providers.etabs_frame_eq713_population_provider import (
    FrameEq713FactualFact,
    FrameEq713FactualPopulation,
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
BLOCKER_A4_B4B = "LIVE_A4_B4B_STATE_NOT_QUALIFIED"
BLOCKER_A4_B5 = "LIVE_A4_B5_RESULT_NOT_QUALIFIED"
BLOCKER_A4_POST_CONTINUITY = "LIVE_A4_POST_CONTINUITY_NOT_QUALIFIED"
BLOCKER_A5_INPUT_MATERIALIZATION = "LIVE_A5_FND2_INPUT_MATERIALIZATION_NOT_QUALIFIED"

# The accepted COLUMN-R1 Area slice is the in-plane displacement-response slice.
# These values are inputs to the existing Eq713 authority, which remains the
# sole owner of the resulting mode dispositions.
_AREA_RESPONSE_SCOPE_REF = "COLUMN_R1_EQ713_IN_PLANE_DISPLACEMENT_RESPONSE_SCOPE"
_FRAME_MECHANICS_REF_PREFIX = "COLUMN_R1_STRICT_FRAME_MECHANICS"


class PublicA5CompositionError(RuntimeError):
    def __init__(self, blocker: str, message: str) -> None:
        super().__init__(message)
        self.blocker = blocker


def _blocked(request: ColumnExecutionRequest, context: TrustedLiveAcquisitionContext, blocker: str):
    from tbdy_engine.application.column_execution import (
        ColumnDomainArtifact,
        STATUS_FACTUAL_ACQUISITION_BLOCKED,
    )

    return ColumnDomainArtifact(
        component_id=request.component_id,
        model_fingerprint=context.model_fingerprint,
        evidence_epoch_id=context.evidence_epoch_id,
        status=STATUS_FACTUAL_ACQUISITION_BLOCKED,
        blockers=(blocker,),
    )


def _target_column(topology: StrictColumnTopologyBundle, component_id: str) -> ColumnTopologyEvidence:
    matches = tuple(item for item in topology.columns if item.component_id == component_id)
    if len(matches) != 1:
        raise PublicA5CompositionError(
            BLOCKER_A3_FACTUAL_ACQUISITION,
            f"expected exactly one strict-topology column for component_id={component_id!r}; got {len(matches)}",
        )
    return matches[0]


def _frame_mechanics_ref(
    row: FrameEq713FactualFact,
    topology: StrictColumnTopologyBundle,
) -> str:
    """Prove the supported 3D RC Frame mechanism slice independently of releases."""
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
        return (
            f"{_FRAME_MECHANICS_REF_PREFIX}:COLUMN:{row.frame_name}:"
            f"LOCAL_AXIS_EXPLICIT={item.local_axis_explicit}:ANGLE={item.local_axis_angle_deg}"
        )

    beams = {}
    for column in topology.columns:
        for beam in (*column.beams_at_bottom, *column.beams_at_top):
            beams.setdefault(beam.beam_unique_name, beam)
    beam = beams.get(row.frame_name)
    if beam is None or not beam.is_supported_rc_beam:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            f"BEAM Frame {row.frame_name!r} lacks supported strict-topology mechanics",
        )
    if (
        beam.width_t2_m is None
        or beam.depth_t3_m is None
        or beam.width_t2_m <= 0.0
        or beam.depth_t3_m <= 0.0
        or not any(abs(value) > 0.0 for value in beam.vector_from_joint_m)
    ):
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            f"BEAM Frame {row.frame_name!r} has unresolved/non-positive strict geometry",
        )
    return f"{_FRAME_MECHANICS_REF_PREFIX}:BEAM:{row.frame_name}:CONNECTED_3D_FRAME"


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

    # The accepted Area provider carries exact simple-property thickness and no
    # separate object-thickness authority.  COLUMN-R1 therefore retains that
    # reviewed simple-property slice; no new thickness-composition rule is made
    # here.  Out-of-plane plate/transverse response is positively excluded from
    # the accepted in-plane Eq7.13 Delta_i response scope and is still disposed
    # by the existing Eq713 authority.
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
        plate_participation=False,
        transverse_shear_participation=False,
        source_refs=(*fact.source_refs, _AREA_RESPONSE_SCOPE_REF),
    )


def _qualify_a3(
    *,
    frame_population: FrameEq713FactualPopulation,
    area_population: AreaContributorPopulation,
    topology: StrictColumnTopologyBundle,
):
    material_bases = _material_bases(frame_population)
    frame_rows = []
    for fact in frame_population.rows:
        if not fact.supported_end_condition:
            raise PublicA5CompositionError(
                BLOCKER_A3_EQ713_POPULATION,
                f"Frame {fact.frame_name!r} is outside supported no-release/no-partial-fixity end-condition slice",
            )
        mechanics_ref = _frame_mechanics_ref(fact, topology)
        basis = material_bases[fact.base_fact.material_name]
        # Participation is not inferred from the release state.  Strict member
        # role/connectivity/geometry establish the supported active 3D Frame
        # mechanism input; the existing Eq713 authority owns the six resulting
        # mode dispositions.
        participation = {mode: True for mode in FrameStiffnessMode}
        frame_rows.append(
            audit_frame_eq713_modes(
                component_uid=fact.frame_name,
                property_modifiers=fact.property_modifiers.modifiers.as_tuple(),
                object_modifiers=fact.object_modifiers.modifiers.as_tuple(),
                participation=participation,
                material_basis=basis,
                source_refs=(*fact.source_refs, mechanics_ref),
            )
        )

    area_evidence = tuple(
        _area_evidence(fact, material_bases)
        for fact in area_population.rows
    )
    area_rows = tuple(build_area_eq713_target(fact) for fact in area_evidence)
    whole = Eq713PopulationDisposition(
        area_rows=area_rows,
        frame_rows=tuple(frame_rows),
    )
    if not whole.positive:
        blocked = tuple(
            reason
            for row in (*whole.area_rows, *whole.frame_rows)
            for reason in row.blocked_reasons
        )
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            "Eq713 whole-system population did not qualify: " + "; ".join(dict.fromkeys(blocked)),
        )
    return whole, area_evidence


def _frame_target(current: FrameModifierVector) -> FrameModifierVector:
    return FrameModifierVector.from_sequence(
        (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, current.mass, current.weight)
    )


def _b4b_targets(frame_population, area_population, area_rows):
    targets = []
    property_targets: dict[str, FrameModifierVector] = {}
    for fact in frame_population.rows:
        section_target = _frame_target(fact.property_modifiers.modifiers)
        previous = property_targets.get(fact.base_fact.assigned_section_name)
        if previous is not None and previous.as_tuple() != section_target.as_tuple():
            raise PublicA5CompositionError(
                BLOCKER_A4_B4B,
                f"shared Frame section {fact.base_fact.assigned_section_name!r} has contradictory gross target",
            )
        property_targets[fact.base_fact.assigned_section_name] = section_target
        targets.append(
            FrameModifierTargetRequest(
                surface=FrameModifierSurface.FRAME_OBJECT,
                target_name=fact.frame_name,
                modifiers=_frame_target(fact.object_modifiers.modifiers),
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

    area_by_name = {row.area_name: row for row in area_population.rows}
    area_property_targets: dict[str, AreaModifierVector] = {}
    for disposition in area_rows:
        if disposition.target_property_modifiers is None:
            continue
        factual = area_by_name[disposition.area_name]
        if factual.property_state is None:
            raise PublicA5CompositionError(BLOCKER_A4_B4B, "Area target lost factual property identity")
        vector = AreaModifierVector.from_sequence(disposition.target_property_modifiers)
        property_name = factual.property_name
        previous = area_property_targets.get(property_name)
        if previous is not None and previous.as_tuple() != vector.as_tuple():
            raise PublicA5CompositionError(
                BLOCKER_A4_B4B,
                f"shared Area property {property_name!r} has contradictory Eq713 target",
            )
        area_property_targets[property_name] = vector
    for property_name, vector in area_property_targets.items():
        targets.append(
            AreaModifierTargetRequest(
                surface=AreaModifierSurface.AREA_PROPERTY,
                target_name=property_name,
                modifiers=vector,
            )
        )
    if not targets:
        raise PublicA5CompositionError(BLOCKER_A4_B4B, "Eq713 positive population produced no B4B target")
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
    definitions = capture_etabs_combo_definitions_from_session(
        context.verified_session,
        names,
    )
    flattened = tuple(_flatten_combo(item) for item in definitions)
    cases = tuple(sorted({name for _combo, leaves in flattened for name, _scale in leaves}))
    if not cases:
        raise PublicA5CompositionError(BLOCKER_A5_INPUT_MATERIALIZATION, "no exact analysis case scope from selected combos")
    return selection, definitions, flattened, cases


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
):
    # Existing prior-evidence helper proves PRE/POST base semantics for the
    # requested column and exact B4B/B5 causal lineage without reusing its old
    # exact-TS500-Ec gross-basis gate.
    capture_frame_flexural_base_continuity_evidence(
        context=context,
        owned_scratch=owned_scratch,
        pre_fact=next(row.base_fact for row in frame_pre.rows if row.frame_name == target_column.unique_name),
        established_state=established_state,
        execution_result=execution_result,
    )

    topology_post = capture_etabs_strict_column_topology_from_session(context.verified_session)
    target_post = _target_column(topology_post, target_column.component_id)
    if target_post.as_dict() != target_column.as_dict():
        raise PublicA5CompositionError(
            BLOCKER_A4_POST_CONTINUITY,
            "target column strict topology changed across A3/B4B/B5 generation",
        )

    frame_post = capture_frame_eq713_factual_population(context, owned_scratch, topology_post)
    if frame_post.expected_frame_names != frame_pre.expected_frame_names:
        raise PublicA5CompositionError(BLOCKER_A4_POST_CONTINUITY, "Frame population changed after B5")
    pre_by_name = {row.frame_name: row for row in frame_pre.rows}
    for post in frame_post.rows:
        pre = pre_by_name[post.frame_name]
        if (
            post.base_fact.semantic_state_ref != pre.base_fact.semantic_state_ref
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


def _axis_payload(axis) -> dict[str, object]:
    return asdict(axis)


def _slenderness_payload(evidence) -> dict[str, object]:
    return {
        "component_id": evidence.component_id,
        "m2": _axis_payload(evidence.m2),
        "m3": _axis_payload(evidence.m3),
        "source_refs": tuple(evidence.source_refs),
    }


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


def _materialize_fnd2_inputs(
    *,
    request,
    context,
    target_column,
    topology_post,
    flattened_combos,
    selection,
    definitions,
    execution_result,
):
    demand_states = []
    demand_refs = []
    target_uid = target_column.unique_name
    for population in execution_result.manifest.result_populations:
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

    restraints = capture_etabs_column_endpoint_restraints_from_session(
        context.verified_session,
        target_column,
    )
    try:
        free_length = resolve_ts500_column_free_length(
            target_column,
            bottom_restraint_dofs=restraints.bottom.dofs,
            top_restraint_dofs=restraints.top.dofs,
            bottom_restraint_source_ref=restraints.bottom_source_ref,
            top_restraint_source_ref=restraints.top_source_ref,
        )
    except Exception:
        free_length = None
    slenderness = build_factual_slenderness_evidence_from_topology(
        target_column,
        free_length_resolution=free_length,
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
            value=_slenderness_payload(slenderness),
            refs=(*common_refs, *slenderness.source_refs),
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
    return RegulatoryCompileInputs(
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


def execute_public_a5_column(
    request: ColumnExecutionRequest,
    *,
    acquisition_context: TrustedLiveAcquisitionContext,
    execute_fnd2: Callable[..., object],
):
    """Compose the supported production path through REAL existing FND-COL-2."""
    if not isinstance(request, ColumnExecutionRequest):
        raise TypeError("request must be ColumnExecutionRequest")
    if not isinstance(acquisition_context, TrustedLiveAcquisitionContext):
        raise TypeError("acquisition_context must be TrustedLiveAcquisitionContext")
    if not callable(execute_fnd2):
        raise TypeError("execute_fnd2 must be callable")
    context = acquisition_context

    try:
        owned_scratch = create_owned_scratch_context(context)
        topology_pre = capture_etabs_strict_column_topology_from_session(context.verified_session)
        target_column = _target_column(topology_pre, request.component_id)
        frame_pre = capture_frame_eq713_factual_population(context, owned_scratch, topology_pre)
        area_pre = capture_area_contributor_population_from_session(
            context.verified_session,
            model_fingerprint=context.model_fingerprint,
            evidence_epoch_id=context.evidence_epoch_id,
            session_provenance_ref=context.session_provenance_ref,
        )
    except PublicA5CompositionError as exc:
        return _blocked(request, context, exc.blocker)
    except Exception:
        return _blocked(request, context, BLOCKER_A3_FACTUAL_ACQUISITION)

    try:
        a3, _area_evidence_rows = _qualify_a3(
            frame_population=frame_pre,
            area_population=area_pre,
            topology=topology_pre,
        )
    except PublicA5CompositionError as exc:
        return _blocked(request, context, exc.blocker)
    except Exception:
        return _blocked(request, context, BLOCKER_A3_EQ713_POPULATION)

    try:
        selection, definitions, flattened_combos, requested_cases = _combo_scope(context)
        targets = _b4b_targets(frame_pre, area_pre, a3.area_rows)
        basis_refs = tuple(
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
    except PublicA5CompositionError as exc:
        return _blocked(request, context, exc.blocker)
    except Exception:
        return _blocked(request, context, BLOCKER_A4_B4B)

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
    except PublicA5CompositionError as exc:
        return _blocked(request, context, exc.blocker)
    except Exception:
        return _blocked(request, context, BLOCKER_A4_B5)

    try:
        topology_post, target_post, _frame_post, _area_post = _prove_post_continuity(
            context=context,
            owned_scratch=owned_scratch,
            topology_pre=topology_pre,
            target_column=target_column,
            frame_pre=frame_pre,
            area_pre=area_pre,
            established_state=established_state,
            execution_result=execution_result,
        )
    except PublicA5CompositionError as exc:
        return _blocked(request, context, exc.blocker)
    except Exception:
        return _blocked(request, context, BLOCKER_A4_POST_CONTINUITY)

    try:
        inputs = _materialize_fnd2_inputs(
            request=request,
            context=context,
            target_column=target_post,
            topology_post=topology_post,
            flattened_combos=flattened_combos,
            selection=selection,
            definitions=definitions,
            execution_result=execution_result,
        )
        return execute_fnd2(
            request,
            model_fingerprint=context.model_fingerprint,
            evidence_epoch_id=context.evidence_epoch_id,
            fnd_col_2_inputs=inputs,
        )
    except PublicA5CompositionError as exc:
        return _blocked(request, context, exc.blocker)
    except Exception:
        return _blocked(request, context, BLOCKER_A5_INPUT_MATERIALIZATION)


__all__ = [
    "BLOCKER_A3_EQ713_POPULATION",
    "BLOCKER_A3_FACTUAL_ACQUISITION",
    "BLOCKER_A4_B4B",
    "BLOCKER_A4_B5",
    "BLOCKER_A4_POST_CONTINUITY",
    "BLOCKER_A5_INPUT_MATERIALIZATION",
    "PublicA5CompositionError",
    "execute_public_a5_column",
]
