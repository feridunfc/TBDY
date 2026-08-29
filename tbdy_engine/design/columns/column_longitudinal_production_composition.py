"""P8A-B provider-neutral canonical longitudinal production composition.

This module owns orchestration only.  It composes the existing P8A factual
column-design evidence path with the existing FND-COL-4 canonical
longitudinal-selection authority.  It contains no independent engineering
formula, eligibility rule, adequacy rule, ranking rule, or selected-rebar
emitter.
"""
from __future__ import annotations

from typing import Mapping

from tbdy_engine.design.columns.column_combo_eligibility_projection import (
    ComboAnalysisBasisBinding,
    ComponentReadinessBinding,
    project_column_combo_eligibility,
)
from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    ConcreteDesignComboReconciliation,
    DesignComboIdentity,
)
from tbdy_engine.design.columns.column_design_rebar_promotion import (
    promote_etabs_required_rebar,
)
from tbdy_engine.design.columns.column_longitudinal_selection import (
    ColumnLongitudinalCanonicalSelectionResult,
    select_canonical_column_longitudinal_rebar,
)
from tbdy_engine.design.columns.column_longitudinal_selection_contract import (
    ColumnLongitudinalSelectionInputs,
    ColumnLongitudinalSelectionPolicyInput,
)
from tbdy_engine.design.columns.column_pmm_assessment import (
    ColumnPmmMaterialContextBinding,
)
from tbdy_engine.features.column_design_rebar_evidence import (
    FactualColumnDesignResultPopulation,
)
from tbdy_engine.regulatory.column_candidate_adequacy_authority import (
    ValidatedCandidateAdequacyPolicy,
)
from tbdy_engine.regulatory.column_longitudinal_rebar import (
    ColumnLongitudinalLayoutAuthorityResult,
)
from tbdy_engine.regulatory.column_pmm_authority import (
    ValidatedPmmNumericalPolicy,
)


def compose_canonical_column_longitudinal_selection(
    *,
    component_id: str,
    layout_authority: ColumnLongitudinalLayoutAuthorityResult,
    readiness_binding: ComponentReadinessBinding,
    combo_reconciliation: ConcreteDesignComboReconciliation,
    combo_analysis_basis_bindings: Mapping[
        DesignComboIdentity,
        ComboAnalysisBasisBinding,
    ],
    factual_design_results: FactualColumnDesignResultPopulation,
    selection_policy: ColumnLongitudinalSelectionPolicyInput,
    numerical_policy: ValidatedPmmNumericalPolicy,
    material_context: ColumnPmmMaterialContextBinding,
    adequacy_policy: ValidatedCandidateAdequacyPolicy,
) -> ColumnLongitudinalCanonicalSelectionResult:
    """Compose existing P8A and FND-COL-4 authorities in production order.

    Existing authorities retain all engineering and fail-closed decisions:
    exact combo eligibility is projected first, factual ETABS required rebar is
    promoted row-by-row second, and the existing canonical selector receives
    the resulting ``ColumnLongitudinalSelectionInputs`` unchanged.
    """

    projections = project_column_combo_eligibility(
        readiness_binding=readiness_binding,
        reconciliation=combo_reconciliation,
        analysis_basis_bindings=combo_analysis_basis_bindings,
    )

    etabs_required_rebar = promote_etabs_required_rebar(
        factual_design_results,
        combo_eligibility_projections=projections,
    )

    inputs = ColumnLongitudinalSelectionInputs(
        component_id=component_id,
        layout_authority=layout_authority,
        readiness_binding=readiness_binding,
        etabs_required_rebar=etabs_required_rebar,
        combo_eligibility_projections=projections,
        policy=selection_policy,
    )

    return select_canonical_column_longitudinal_rebar(
        inputs=inputs,
        numerical_policy=numerical_policy,
        material_context=material_context,
        adequacy_policy=adequacy_policy,
    )


__all__ = [
    "compose_canonical_column_longitudinal_selection",
]
