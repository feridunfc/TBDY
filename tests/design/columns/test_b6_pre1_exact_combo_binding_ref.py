from __future__ import annotations

from dataclasses import replace

from tbdy_engine.design.columns.column_combo_eligibility_projection import (
    EXACT_COMBO_ANALYSIS_BASIS_BINDING_REF_PREFIX,
    ComboAnalysisBasisBinding,
)
from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    AnalysisBasisEligibilityEvidence,
)


IDENTITY = ("Strength", "ULS")


def _evidence(
    *,
    status: str = "MATCH",
    compatibility_ref: str = "analysis-basis:compatibility:1",
    provenance_refs=("analysis-basis:source:1", "analysis-basis:source:2"),
):
    return AnalysisBasisEligibilityEvidence(
        status_value=status,
        compatibility_ref=compatibility_ref,
        provenance_refs=tuple(provenance_refs),
    )


def _binding(**overrides):
    values = {
        "design_combo_identity": IDENTITY,
        "evidence": _evidence(),
        "normalized_definition_fingerprint": "combo-definition:sha256:abc",
        "model_fingerprint": "model:1",
        "evidence_epoch_id": "epoch:1",
        "provenance_refs": ("binding:source:1", "binding:source:2"),
    }
    values.update(overrides)
    return ComboAnalysisBasisBinding(**values)


def test_exact_combo_binding_ref_is_deterministic_and_not_projection_identity() -> None:
    first = _binding()
    same = _binding()

    assert first.binding_ref == same.binding_ref
    assert first.binding_ref.startswith(EXACT_COMBO_ANALYSIS_BASIS_BINDING_REF_PREFIX)
    assert not first.binding_ref.startswith("column-combo-eligibility:sha256:")


def test_exact_combo_binding_ref_is_independent_of_provenance_iteration_order() -> None:
    first = _binding(
        evidence=_evidence(provenance_refs=("analysis-basis:source:1", "analysis-basis:source:2")),
        provenance_refs=("binding:source:1", "binding:source:2"),
    )
    reordered = _binding(
        evidence=_evidence(provenance_refs=("analysis-basis:source:2", "analysis-basis:source:1")),
        provenance_refs=("binding:source:2", "binding:source:1"),
    )

    assert first.binding_ref == reordered.binding_ref


def test_each_authority_bearing_constituent_changes_exact_binding_ref() -> None:
    original = _binding()
    changed = (
        replace(original, design_combo_identity=("Service", "ULS")),
        replace(original, design_combo_identity=("Strength", "ULS-2")),
        replace(original, normalized_definition_fingerprint="combo-definition:sha256:def"),
        replace(original, model_fingerprint="model:2"),
        replace(original, evidence_epoch_id="epoch:2"),
        replace(original, evidence=_evidence(compatibility_ref="analysis-basis:compatibility:2")),
        replace(original, evidence=_evidence(status="REANALYSIS_REQUIRED")),
        replace(
            original,
            evidence=_evidence(
                provenance_refs=("analysis-basis:source:1", "analysis-basis:source:3")
            ),
        ),
        replace(original, provenance_refs=("binding:source:1", "binding:source:3")),
    )

    assert all(item.binding_ref != original.binding_ref for item in changed)


def test_exact_binding_ref_does_not_promote_component_level_readiness_or_basis() -> None:
    binding = _binding()
    payload_fields = set(binding.__dataclass_fields__)

    assert "component_readiness" not in payload_fields
    assert "component_readiness_status" not in payload_fields
    assert binding.evidence.compatibility_ref == "analysis-basis:compatibility:1"
