"""Canonical application composition for the live Column TS500 sway slice.

This module contains no engineering formula.  It binds already-qualified B5
lineage to the existing factual/result and TS500 authorities for one exact
stability-combination candidate:

    qualified B5
    -> qualified signed LINEAR_ADD output state
    -> factual physical-end JointDispl population
    -> uniform-storey relative-translation proof
    -> factual story shear / sum(Ndi) population
    -> source-bound TS500 Eq.7.13 evidence/result

Selection of a governing candidate when more than one exact existing combo maps
to the same TS500 load basis is deliberately outside this bounded seam.  The
application must not invent that policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.design.columns.stability_combo_basis import StabilityComboCandidate
from tbdy_engine.design.columns.stability_output_state import (
    StabilityActionDirectionBinding,
    StabilityConcurrentOutputStateBinding,
    qualify_signed_linear_add_stability_output,
)
from tbdy_engine.design.columns.story_relative_translation import (
    ColumnStoryTranslationEvidence,
    ReviewedStoryTranslationTolerance,
    StoryRelativeTranslationResolution,
    resolve_uniform_story_relative_translation,
)
from tbdy_engine.design.columns.sway_stability import (
    LOAD_BASIS_AUTHORITY,
    STORY_STABILITY_INPUT_AUTHORITY,
    UNCRACKED_SECTION_BASIS_AUTHORITY,
    StoryStabilityIndexEvidence,
    StoryStabilityIndexResult,
    evaluate_ts500_story_stability_index,
)
from tbdy_engine.etabs.safety import EtabsVerifiedSession
from tbdy_engine.features.column_shear_topology import StrictColumnTopologyBundle
from tbdy_engine.integration.etabs_analysis_execution import AnalysisExecutionResult
from tbdy_engine.providers.etabs_column_end_displacement_provider import (
    ColumnEndDisplacementPopulation,
    capture_column_end_displacement_population_from_session,
)
from tbdy_engine.providers.etabs_story_stability_result_provider import (
    EtabsStoryStabilityComboFact,
    capture_story_stability_combo_fact_from_session,
)


class ColumnStabilityRuntimeError(RuntimeError):
    """Raised when the live stability composition cannot retain exact lineage."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnStabilityRuntimeError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(_text(value, label) for value in values)
    if not refs or len(refs) != len(set(refs)):
        raise ColumnStabilityRuntimeError(f"{label} must be nonempty and unique")
    return refs


@dataclass(frozen=True, slots=True)
class ColumnStoryStabilityCandidateRuntime:
    story: str
    global_direction: str
    combo_name: str
    load_basis: str
    output_state: StabilityConcurrentOutputStateBinding
    displacement_population: ColumnEndDisplacementPopulation
    translation: StoryRelativeTranslationResolution
    story_fact: EtabsStoryStabilityComboFact | None
    stability_evidence: StoryStabilityIndexEvidence | None
    stability_result: StoryStabilityIndexResult | None
    status: str
    source_refs: tuple[str, ...]

    @property
    def ready_for_story_sway_resolution(self) -> bool:
        return self.status == "READY_FOR_TS500_STORY_SWAY_RESOLUTION"


def _qualified_b5_refs(analysis_execution: AnalysisExecutionResult) -> tuple[str, str]:
    if not isinstance(analysis_execution, AnalysisExecutionResult):
        raise TypeError("analysis_execution must be AnalysisExecutionResult")
    if not analysis_execution.qualification.qualified:
        raise ColumnStabilityRuntimeError(
            "live stability composition requires qualified B5 analysis lineage"
        )
    qualified = analysis_execution.qualification.require_qualified_result()
    identity = analysis_execution.analysis_result_identity
    if qualified.identity_ref != identity.identity_ref:
        raise ColumnStabilityRuntimeError(
            "qualified B5 result identity differs from AnalysisExecutionResult identity"
        )
    result_ref = _text(identity.identity_ref, "analysis_result_ref")
    proof_ref = _text(analysis_execution.execution_proof_ref, "execution_proof_ref")
    return result_ref, proof_ref


def _translation_evidences(
    population: ColumnEndDisplacementPopulation,
    *,
    output_state: StabilityConcurrentOutputStateBinding,
) -> tuple[ColumnStoryTranslationEvidence, ...]:
    rows: list[ColumnStoryTranslationEvidence] = []
    direction_refs = tuple(
        ref for ref in output_state.source_refs if ref.startswith("stability-direction:")
    )
    if not direction_refs:
        raise ColumnStabilityRuntimeError(
            "qualified stability output state lost its factual direction evidence"
        )
    for fact in population.rows:
        boundary_refs = tuple(
            ref
            for ref in fact.source_refs
            if ref.startswith(f"strict-topology:{fact.column_unique_name}:")
        )
        if not boundary_refs:
            raise ColumnStabilityRuntimeError(
                f"{fact.column_unique_name} lost strict-topology boundary evidence"
            )
        rows.append(
            ColumnStoryTranslationEvidence(
                component_id=fact.component_id,
                story=fact.story,
                column_unique_name=fact.column_unique_name,
                output_name=fact.output_name,
                global_direction=fact.global_direction,
                output_state_ref=fact.output_state_ref,
                story_bottom_z_mm=fact.story_bottom_z_mm,
                story_top_z_mm=fact.story_top_z_mm,
                signed_relative_translation_mm=fact.signed_directional_delta_mm,
                analysis_result_ref=fact.analysis_result_ref,
                execution_proof_ref=fact.execution_proof_ref,
                direction_source_refs=direction_refs,
                boundary_source_refs=boundary_refs,
                source_refs=fact.source_refs,
            )
        )
    return tuple(rows)


def compose_story_stability_candidate_runtime(
    session: EtabsVerifiedSession,
    *,
    topology: StrictColumnTopologyBundle,
    analysis_execution: AnalysisExecutionResult,
    candidate: StabilityComboCandidate,
    direction_binding: StabilityActionDirectionBinding,
    story: str,
    reference_component_id: str,
    translation_tolerance: ReviewedStoryTranslationTolerance,
    reviewed_displacement_unit: str,
    reviewed_force_unit: str,
    uncracked_basis_refs: Sequence[str],
    timeout_seconds: float = 30.0,
) -> ColumnStoryStabilityCandidateRuntime:
    """Compose one exact TS500 Eq.7.13 candidate from the qualified B5 generation.

    A nonuniform complete storey translation is returned explicitly as
    ``EXPLICIT_UNRESOLVED_NONUNIFORM_STORY_TRANSLATION``.  It is not averaged,
    maximized or otherwise converted into a regulatory operand.
    """
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    if not isinstance(topology, StrictColumnTopologyBundle):
        raise TypeError("topology must be StrictColumnTopologyBundle")
    if not isinstance(candidate, StabilityComboCandidate):
        raise TypeError("candidate must be StabilityComboCandidate")
    if not isinstance(direction_binding, StabilityActionDirectionBinding):
        raise TypeError("direction_binding must be StabilityActionDirectionBinding")
    if not isinstance(translation_tolerance, ReviewedStoryTranslationTolerance):
        raise TypeError("translation_tolerance must be ReviewedStoryTranslationTolerance")

    story_name = _text(story, "story")
    reference_component = _text(reference_component_id, "reference_component_id")
    basis_refs = _refs(uncracked_basis_refs, "uncracked_basis_ref")
    analysis_ref, proof_ref = _qualified_b5_refs(analysis_execution)

    output_state = qualify_signed_linear_add_stability_output(
        candidate,
        direction_binding=direction_binding,
        analysis_result_ref=analysis_ref,
        execution_proof_ref=proof_ref,
    )
    population = capture_column_end_displacement_population_from_session(
        session,
        topology=topology,
        story=story_name,
        output_state=output_state,
        reviewed_displacement_unit=reviewed_displacement_unit,
        timeout_seconds=timeout_seconds,
    )
    evidences = _translation_evidences(population, output_state=output_state)
    translation = resolve_uniform_story_relative_translation(
        evidences,
        story=story_name,
        output_name=output_state.output_name,
        global_direction=output_state.global_direction,
        expected_column_unique_names=population.expected_column_unique_names,
        reference_component_id=reference_component,
        tolerance=translation_tolerance,
    )

    common_refs = tuple(
        dict.fromkeys(
            (
                analysis_ref,
                proof_ref,
                output_state.binding_ref,
                *output_state.source_refs,
                *population.source_refs,
                *translation.source_refs,
                *basis_refs,
            )
        )
    )
    if not translation.proven:
        return ColumnStoryStabilityCandidateRuntime(
            story=story_name,
            global_direction=output_state.global_direction,
            combo_name=candidate.combo_name,
            load_basis=candidate.load_basis,
            output_state=output_state,
            displacement_population=population,
            translation=translation,
            story_fact=None,
            stability_evidence=None,
            stability_result=None,
            status="EXPLICIT_UNRESOLVED_NONUNIFORM_STORY_TRANSLATION",
            source_refs=common_refs,
        )

    story_fact = capture_story_stability_combo_fact_from_session(
        session,
        output_name=output_state.output_name,
        story=story_name,
        global_direction=output_state.global_direction,
        direction_source_refs=direction_binding.source_refs,
        topology=topology,
        analysis_result_ref=analysis_ref,
        execution_proof_ref=proof_ref,
        reviewed_force_unit=reviewed_force_unit,
        timeout_seconds=timeout_seconds,
    )
    if (
        story_fact.analysis_result_ref != translation.analysis_result_ref
        or story_fact.execution_proof_ref != translation.execution_proof_ref
        or story_fact.output_name != translation.output_name
        or story_fact.story != translation.story
        or story_fact.global_direction != translation.global_direction
    ):
        raise ColumnStabilityRuntimeError(
            "story-stability facts do not share the exact A14/A15/B5 state identity"
        )
    if translation.relative_story_displacement_mm is None:
        raise ColumnStabilityRuntimeError(
            "proven story translation is missing its relative displacement operand"
        )

    evidence_refs = tuple(
        dict.fromkeys(
            (
                *common_refs,
                *story_fact.source_refs,
                *candidate.source_refs,
                *direction_binding.source_refs,
                "TS500 7.6.2.1 Eq.7.13",
            )
        )
    )
    stability_evidence = StoryStabilityIndexEvidence(
        story=story_name,
        direction=output_state.global_direction,
        load_basis=candidate.load_basis,
        story_height_mm=story_fact.story_height_mm,
        relative_story_displacement_mm=translation.relative_story_displacement_mm,
        story_shear_n=story_fact.story_shear_n,
        sum_column_axial_design_force_n=story_fact.sum_column_axial_design_force_n,
        input_authority=STORY_STABILITY_INPUT_AUTHORITY,
        load_basis_authority=LOAD_BASIS_AUTHORITY,
        stiffness_basis="UNCRACKED",
        stiffness_basis_authority=UNCRACKED_SECTION_BASIS_AUTHORITY,
        source_refs=evidence_refs,
    )
    stability_result = evaluate_ts500_story_stability_index(stability_evidence)
    return ColumnStoryStabilityCandidateRuntime(
        story=story_name,
        global_direction=output_state.global_direction,
        combo_name=candidate.combo_name,
        load_basis=candidate.load_basis,
        output_state=output_state,
        displacement_population=population,
        translation=translation,
        story_fact=story_fact,
        stability_evidence=stability_evidence,
        stability_result=stability_result,
        status="READY_FOR_TS500_STORY_SWAY_RESOLUTION",
        source_refs=evidence_refs,
    )


__all__ = [
    "ColumnStabilityRuntimeError",
    "ColumnStoryStabilityCandidateRuntime",
    "compose_story_stability_candidate_runtime",
]
