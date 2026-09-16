"""Causal provenance guards for the canonical Column longitudinal product path.

This module performs no engineering calculation and owns no selection rule.  It
only verifies that the qualified B6 design generation remains source-bound while
existing owners promote ETABS_REQUIRED_REBAR and, when selection succeeds,
emit ENGINE_SELECTED_REBAR.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.design.columns.column_design_rebar_promotion import (
    ETABS_REQUIRED_REBAR,
    EtabsRequiredRebarPopulation,
)
from tbdy_engine.design.columns.column_longitudinal_selection import (
    ENGINE_SELECTED_REBAR_AUTHORITY,
    ColumnLongitudinalCanonicalSelectionResult,
)
from tbdy_engine.features.column_design_rebar_evidence import (
    FactualColumnDesignResultPopulation,
)
from tbdy_engine.integration.etabs_design_lineage import (
    DESIGN_LINEAGE_REF_PREFIX,
    DESIGN_RESULT_REF_PREFIX,
)


class ColumnLongitudinalCausalProvenanceError(ValueError):
    """Raised when an existing longitudinal owner loses qualified B6 lineage."""


def _single_ref(values: Sequence[str], *, prefix: str, label: str) -> str:
    matches = tuple(sorted({value for value in values if value.startswith(prefix)}))
    if len(matches) != 1:
        raise ColumnLongitudinalCausalProvenanceError(
            f"{label} requires exactly one {prefix}<sha256> ref; got {len(matches)}"
        )
    return matches[0]


@dataclass(frozen=True, slots=True)
class QualifiedB6DesignRefs:
    design_result_identity_ref: str
    design_lineage_qualification_ref: str
    model_fingerprint: str
    evidence_epoch_id: str


def resolve_qualified_b6_design_refs(
    results: FactualColumnDesignResultPopulation,
) -> QualifiedB6DesignRefs:
    """Resolve the exact B6 identity refs retained by the component projection."""
    if not isinstance(results, FactualColumnDesignResultPopulation):
        raise TypeError("results must be FactualColumnDesignResultPopulation")
    if not results.capture_complete:
        raise ColumnLongitudinalCausalProvenanceError(
            "qualified B6 factual design-result population must be complete"
        )
    return QualifiedB6DesignRefs(
        design_result_identity_ref=_single_ref(
            results.source_refs,
            prefix=DESIGN_RESULT_REF_PREFIX,
            label="factual B6 result population",
        ),
        design_lineage_qualification_ref=_single_ref(
            results.source_refs,
            prefix=DESIGN_LINEAGE_REF_PREFIX,
            label="factual B6 result population",
        ),
        model_fingerprint=results.model_fingerprint,
        evidence_epoch_id=results.evidence_epoch_id,
    )


def require_etabs_required_rebar_design_refs(
    population: EtabsRequiredRebarPopulation,
    *,
    b6: QualifiedB6DesignRefs,
) -> None:
    """Fail closed unless ETABS_REQUIRED_REBAR retains the exact B6 generation."""
    if not isinstance(population, EtabsRequiredRebarPopulation):
        raise TypeError("population must be EtabsRequiredRebarPopulation")
    if population.model_fingerprint != b6.model_fingerprint:
        raise ColumnLongitudinalCausalProvenanceError(
            "ETABS_REQUIRED_REBAR model fingerprint differs from qualified B6"
        )
    if population.evidence_epoch_id != b6.evidence_epoch_id:
        raise ColumnLongitudinalCausalProvenanceError(
            "ETABS_REQUIRED_REBAR EvidenceEpoch differs from qualified B6"
        )
    required_refs = {
        b6.design_result_identity_ref,
        b6.design_lineage_qualification_ref,
    }
    if not required_refs.issubset(set(population.source_refs)):
        raise ColumnLongitudinalCausalProvenanceError(
            "ETABS_REQUIRED_REBAR population lost DesignResultIdentity/DesignLineage provenance"
        )
    for component in population.components:
        if not required_refs.issubset(set(component.source_refs)):
            raise ColumnLongitudinalCausalProvenanceError(
                f"ETABS_REQUIRED_REBAR component {component.component_id!r} lost B6 lineage provenance"
            )
        if any(item.authority != ETABS_REQUIRED_REBAR for item in component.requirements):
            raise ColumnLongitudinalCausalProvenanceError(
                "factual required-rebar role was collapsed into another authority"
            )


def require_engine_selected_rebar_design_refs(
    selection: ColumnLongitudinalCanonicalSelectionResult,
    *,
    b6: QualifiedB6DesignRefs,
) -> None:
    """Require exact B6 provenance whenever canonical selection emits a cage."""
    if not isinstance(selection, ColumnLongitudinalCanonicalSelectionResult):
        raise TypeError("selection must be ColumnLongitudinalCanonicalSelectionResult")
    if not selection.selected:
        return
    selected = selection.selected_rebar
    if selected is None or selected.authority != ENGINE_SELECTED_REBAR_AUTHORITY:
        raise ColumnLongitudinalCausalProvenanceError(
            "selected longitudinal reinforcement does not carry ENGINE_SELECTED_REBAR authority"
        )
    if selected.model_fingerprint != b6.model_fingerprint:
        raise ColumnLongitudinalCausalProvenanceError(
            "ENGINE_SELECTED_REBAR model fingerprint differs from qualified B6"
        )
    if selected.evidence_epoch_id != b6.evidence_epoch_id:
        raise ColumnLongitudinalCausalProvenanceError(
            "ENGINE_SELECTED_REBAR EvidenceEpoch differs from qualified B6"
        )
    required_refs = {
        b6.design_result_identity_ref,
        b6.design_lineage_qualification_ref,
    }
    if not required_refs.issubset(set(selected.provenance_refs)):
        raise ColumnLongitudinalCausalProvenanceError(
            "ENGINE_SELECTED_REBAR lost DesignResultIdentity/DesignLineage provenance"
        )


__all__ = [
    "ColumnLongitudinalCausalProvenanceError",
    "QualifiedB6DesignRefs",
    "require_engine_selected_rebar_design_refs",
    "require_etabs_required_rebar_design_refs",
    "resolve_qualified_b6_design_refs",
]
