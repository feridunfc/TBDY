"""B5-bound factual evidence adapter for the existing VS5 dual-axial program.

This provider performs read-only factual acquisition only. It does not select
Ndm/Nd, apply TBDY/TS500 limits, or manufacture a new analysis generation.
Final response-combination rows may be read after B5 only when every flattened
leaf of that combination is already inside the exact qualified B5 run scope.
Static correction rows are reused directly from B5 result-population facts.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, Sequence

from tbdy_engine.features.etabs_column_axial_evidence import (
    ColumnForceEvidenceBundle,
    ColumnGeometryEvidence,
    LiveColumnAxialEvidenceBundle,
)
from tbdy_engine.integration.etabs_analysis_execution import AnalysisExecutionResult
from tbdy_engine.providers.etabs_column_force_result_population_provider import (
    ColumnForcePopulationExpectation,
    capture_column_force_result_population_from_session,
)
from tbdy_engine.providers.etabs_load_pattern_catalog_provider import (
    capture_etabs_load_pattern_catalog_from_session,
)


class ColumnAxialB5EvidenceError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnAxialB5EvidenceError(f"{label} must be a nonblank canonical string")
    return value


def _flattened_by_name(flattened_combos) -> dict[str, tuple[tuple[str, float], ...]]:
    rows = tuple(flattened_combos)
    out = {name: tuple(leaves) for name, leaves in rows}
    if len(out) != len(rows):
        raise ColumnAxialB5EvidenceError("duplicate flattened response-combination identity")
    return out


def _combination_rows(
    *,
    required_combo_names: Sequence[str],
    flattened_combos,
    exact_b5_case_scope: frozenset[str],
) -> tuple[Mapping[str, object], ...]:
    flattened = _flattened_by_name(flattened_combos)
    rows: list[Mapping[str, object]] = []
    for combo_name in required_combo_names:
        name = _text(combo_name, "combo_name")
        leaves = flattened.get(name)
        if not leaves:
            raise ColumnAxialB5EvidenceError(
                f"reviewed axial combination {name!r} has no exact factual flattened definition"
            )
        leaf_names = frozenset(case for case, _factor in leaves)
        if not leaf_names.issubset(exact_b5_case_scope):
            missing = tuple(sorted(leaf_names - exact_b5_case_scope))
            raise ColumnAxialB5EvidenceError(
                f"reviewed axial combination {name!r} depends on case(s) outside qualified B5 scope: {missing}"
            )
        rows.extend(
            MappingProxyType({"Name": name, "LoadName": case, "SF": float(factor)})
            for case, factor in leaves
        )
    return tuple(rows)


def _b5_population_rows(
    analysis_execution: AnalysisExecutionResult,
    *,
    required_case_names: Sequence[str],
) -> tuple[Mapping[str, object], ...]:
    populations = {
        item.case_name: item
        for item in analysis_execution.manifest.result_populations
    }
    if len(populations) != len(analysis_execution.manifest.result_populations):
        raise ColumnAxialB5EvidenceError("duplicate B5 result-population case identity")
    out: list[Mapping[str, object]] = []
    for case_name in required_case_names:
        population = populations.get(case_name)
        if population is None:
            raise ColumnAxialB5EvidenceError(
                f"required static axial correction case {case_name!r} has no exact B5 result population"
            )
        out.extend(population.rows)
    return tuple(out)


def capture_b5_bound_column_axial_evidence(
    *,
    session,
    analysis_execution: AnalysisExecutionResult,
    topology,
    target,
    material_context,
    model_fingerprint: str,
    evidence_epoch_id: str,
    reviewed,
    flattened_combos,
) -> LiveColumnAxialEvidenceBundle:
    """Materialize existing VS5 factual bundle without creating a second result generation."""
    if not isinstance(analysis_execution, AnalysisExecutionResult):
        raise TypeError("analysis_execution must be AnalysisExecutionResult")
    if not analysis_execution.qualification.qualified:
        raise ColumnAxialB5EvidenceError("dual axial requires qualified B5 analysis lineage")
    if target.component_id != material_context.component_id:
        raise ColumnAxialB5EvidenceError("dual-axial target/material component mismatch")
    if target.section != material_context.section_id:
        raise ColumnAxialB5EvidenceError("dual-axial target/material section mismatch")
    model = _text(model_fingerprint, "model_fingerprint")
    epoch = _text(evidence_epoch_id, "evidence_epoch_id")
    if material_context.model_fingerprint != model or material_context.evidence_epoch_id != epoch:
        raise ColumnAxialB5EvidenceError("dual-axial material identity generation mismatch")

    # Import here to avoid creating a provider -> regulatory package initialization cycle.
    from tbdy_engine.regulatory.vs5_column_axial_program import ReviewedVs5ColumnAxialContext

    if not isinstance(reviewed, ReviewedVs5ColumnAxialContext):
        raise TypeError("reviewed must be ReviewedVs5ColumnAxialContext")

    exact_scope = frozenset(analysis_execution.manifest.scope.case_names)
    required_combos = tuple(
        dict.fromkeys((*reviewed.ndm_binding.final_combination_ids, *reviewed.ts500_combination_ids))
    )
    combination_rows = _combination_rows(
        required_combo_names=required_combos,
        flattened_combos=flattened_combos,
        exact_b5_case_scope=exact_scope,
    )

    # Ndm Q/S correction sources must be the exact already-executed B5 cases.
    correction_cases = tuple(
        dict.fromkeys((*reviewed.ndm_binding.q_case_ids, *reviewed.ndm_binding.s_case_ids))
    )
    if not set(correction_cases).issubset(exact_scope):
        raise ColumnAxialB5EvidenceError("reviewed Q/S axial correction case lies outside qualified B5 scope")
    static_rows = (
        _b5_population_rows(
            analysis_execution,
            required_case_names=correction_cases,
        )
        if correction_cases
        else ()
    )

    expectation = ColumnForcePopulationExpectation(
        expected_unique_names=tuple(item.unique_name for item in topology.columns),
        source_row_count=len(topology.columns),
    )
    final_rows: list[Mapping[str, object]] = []
    final_refs: list[str] = []
    for combo_name in required_combos:
        fact = capture_column_force_result_population_from_session(
            session,
            case_name=combo_name,
            expectation=expectation,
        )
        final_rows.extend(fact.rows)
        final_refs.append(fact.evidence_ref)

    # Existing VS5 selector expects the factual load-pattern display vocabulary
    # "Live" / "Snow". Translate only exact OAPI enum semantics; no case-name inference.
    catalog = capture_etabs_load_pattern_catalog_from_session(session)
    pattern_rows = tuple(
        MappingProxyType(
            {
                "Name": item.name,
                "Type": {
                    "LIVE": "Live",
                    "SNOW": "Snow",
                }.get(item.type_name, item.type_name),
            }
        )
        for item in catalog.patterns
    )

    geometry = ColumnGeometryEvidence(
        unique_name=target.unique_name,
        story=target.story,
        column_label=target.column_label,
        section=target.section,
        material=material_context.material_name,
        width_m=target.width_t2_m,
        depth_m=target.depth_t3_m,
        fck_mpa=material_context.material.fck_mpa,
        connectivity_row=target.connectivity_row,
        assignment_row=target.assignment_row,
        section_row=target.section_row,
        material_row={
            "Material": material_context.material_name,
            "canonical_fck_mpa": material_context.material.fck_mpa,
            "material_context_ref": material_context.binding_ref,
        },
    )

    all_force_rows = tuple((*static_rows, *final_rows))
    output_names = tuple(dict.fromkeys((*correction_cases, *required_combos)))
    forces = ColumnForceEvidenceBundle(
        rows=all_force_rows,
        output_names=output_names,
        force_unit="kN",
    )
    qualified_result = analysis_execution.qualification.require_qualified_result()
    return LiveColumnAxialEvidenceBundle(
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        columns=(geometry,),
        forces=forces,
        load_pattern_rows=pattern_rows,
        load_combination_rows=combination_rows,
        column_overwrite_rows=(),
        review_refs=tuple(
            dict.fromkeys(
                (
                    *reviewed.ndm_review_refs,
                    *reviewed.ts500_review_refs,
                )
            )
        ),
        provenance_refs=tuple(
            dict.fromkeys(
                (
                    analysis_execution.execution_proof_ref,
                    qualified_result.identity_ref,
                    analysis_execution.qualification.qualification_ref,
                    expectation.evidence_ref,
                    *final_refs,
                )
            )
        ),
    )


__all__ = [
    "ColumnAxialB5EvidenceError",
    "capture_b5_bound_column_axial_evidence",
]
