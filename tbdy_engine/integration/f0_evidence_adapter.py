"""Explicit factual FeatureSnapshot -> F0 external-authority integration seam.

This adapter maps only reviewed, explicitly declared component-scoped FACT and
CONTEXT bindings. It does not infer semantics, execute rules, select results,
or create regulatory verdicts/quantities.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from collections.abc import Mapping
from typing import Sequence

from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.evidence_epoch import EvidenceEpoch
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    DependencyKey,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    ExternalDependencyAuthority,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.units import Unit


class EvidenceAuthorityAdapterError(ValueError):
    """Fail-closed F0.4 evidence-binding construction error."""


class EvidenceBindingSource(StrEnum):
    FEATURE_VALUE = "FEATURE_VALUE"
    SNAPSHOT_IDENTITY = "SNAPSHOT_IDENTITY"
    EVIDENCE_TRACE = "EVIDENCE_TRACE"


def _canonical_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceAuthorityAdapterError(f"{label} must be a nonblank string")
    if value != value.strip():
        raise EvidenceAuthorityAdapterError(f"{label} must not contain leading or trailing whitespace")
    return value


@dataclass(frozen=True, slots=True)
class F0EvidenceBinding:
    """One explicit reviewed mapping from factual snapshot data to an F0 dependency."""

    source_location: EvidenceBindingSource | str
    source_key: str
    dependency_key: DependencyKey
    source_kind: DependencySourceKind
    semantic_type: SemanticType
    physical_dimension: PhysicalDimension
    grain: Grain
    unit: Unit
    expected_source_unit: str | None = None

    def __post_init__(self) -> None:
        try:
            source_location = EvidenceBindingSource(str(self.source_location))
        except ValueError as exc:
            raise EvidenceAuthorityAdapterError("unsupported evidence binding source") from exc
        object.__setattr__(self, "source_location", source_location)
        _canonical_text(self.source_key, "source_key")
        typed = (
            (self.dependency_key, DependencyKey),
            (self.source_kind, DependencySourceKind),
            (self.semantic_type, SemanticType),
            (self.physical_dimension, PhysicalDimension),
            (self.grain, Grain),
            (self.unit, Unit),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise TypeError("F0EvidenceBinding requires bounded typed metadata")
        if self.source_kind not in {DependencySourceKind.FACT, DependencySourceKind.CONTEXT}:
            raise EvidenceAuthorityAdapterError("F0.4 adapter supports FACT and CONTEXT only")
        if self.grain is not Grain.COMPONENT:
            raise EvidenceAuthorityAdapterError("F0.4 adapter supports Grain.COMPONENT only")
        if self.unit.physical_dimension is not self.physical_dimension:
            raise EvidenceAuthorityAdapterError("binding unit/physical-dimension mismatch")

        if source_location is EvidenceBindingSource.FEATURE_VALUE:
            if self.source_kind is not DependencySourceKind.FACT:
                raise EvidenceAuthorityAdapterError("FEATURE_VALUE binding must declare FACT source kind")
            expected = _canonical_text(self.expected_source_unit or "", "expected_source_unit")
            if expected != self.unit.identifier:
                raise EvidenceAuthorityAdapterError(
                    "F0.4 requires exact source-unit and F0 authority-unit agreement"
                )
            object.__setattr__(self, "expected_source_unit", expected)
        elif source_location is EvidenceBindingSource.SNAPSHOT_IDENTITY:
            if self.source_kind is not DependencySourceKind.CONTEXT:
                raise EvidenceAuthorityAdapterError("SNAPSHOT_IDENTITY binding must declare CONTEXT source kind")
            if self.expected_source_unit is not None:
                raise EvidenceAuthorityAdapterError("SNAPSHOT_IDENTITY does not accept a source-unit label")
        else:
            if self.source_kind is not DependencySourceKind.CONTEXT:
                raise EvidenceAuthorityAdapterError("EVIDENCE_TRACE binding must declare CONTEXT source kind")
            if self.expected_source_unit is not None:
                raise EvidenceAuthorityAdapterError("EVIDENCE_TRACE does not accept a source-unit label")

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        return (
            self.dependency_key.value,
            self.source_kind.value,
            self.source_location.value,
            self.source_key,
        )


def _plain_factual(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        out: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise EvidenceAuthorityAdapterError(
                    "factual evidence mapping keys must be strings"
                )
            out[key] = _plain_factual(item)
        return out
    if isinstance(value, (tuple, list)):
        return [_plain_factual(item) for item in value]
    raise EvidenceAuthorityAdapterError(
        f"unsupported factual evidence payload type: {type(value).__name__}"
    )


def _stable_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceAuthorityAdapterError(
            "factual evidence projection must be deterministic JSON-safe"
        ) from exc


def _evidence_payload(
    *, epoch: EvidenceEpoch, snapshot: FeatureSnapshot, feature_name: str, evidence: FeatureEvidence
) -> dict[str, object]:
    return {
        "epoch_ref": f"epoch:{epoch.epoch_id}",
        "component_type": snapshot.component_type,
        "component_id": snapshot.component_id,
        "feature_name": feature_name,
        "source_table": evidence.source_table,
        "actual_table_name": evidence.actual_table_name,
        "source_column": evidence.source_column,
        "source_row": _plain_factual(evidence.source_row or {}),
        "output_case": evidence.output_case,
        "combo_family": evidence.combo_family,
        "governing_combo": evidence.governing_combo,
        "section_state": evidence.section_state,
        "ductility_class": evidence.ductility_class,
        "raw_value": _plain_factual(evidence.raw_value),
        "normalized_value": _plain_factual(evidence.normalized_value),
        "unit": evidence.unit,
        "resolver": evidence.resolver,
        "reason": evidence.reason,
        "evidence_status": evidence.evidence_status.value,
    }


def _evidence_ref(payload: dict[str, object]) -> str:
    digest = hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()
    return f"evidence:{digest}"


def _base_provenance(epoch: EvidenceEpoch, snapshot: FeatureSnapshot) -> tuple[str, ...]:
    refs = [
        f"epoch:{epoch.epoch_id}",
        f"snapshot:{snapshot.component_type}:{snapshot.component_id}",
        *epoch.provenance_refs,
    ]
    if epoch.source_fingerprint is not None:
        refs.append(f"source:{epoch.source_fingerprint}")
    return tuple(dict.fromkeys(refs))


def _feature_state(feature: FeatureValue) -> tuple[AvailabilityState, PopulationCompleteness]:
    if feature.status is FeatureValueStatus.MISSING:
        return AvailabilityState.NO_DATA, PopulationCompleteness.INCOMPLETE
    if feature.status is FeatureValueStatus.PARTIAL:
        return AvailabilityState.BLOCKED, PopulationCompleteness.INCOMPLETE
    if not feature.evidence or any(
        item.evidence_status is not FeatureEvidenceStatus.FULL for item in feature.evidence
    ):
        return AvailabilityState.BLOCKED, PopulationCompleteness.INCOMPLETE
    return AvailabilityState.RESOLVED, PopulationCompleteness.FULL


def _feature_value(
    epoch: EvidenceEpoch,
    snapshot: FeatureSnapshot,
    binding: F0EvidenceBinding,
) -> tuple[object, AvailabilityState, PopulationCompleteness, tuple[str, ...]]:
    feature = snapshot.features.get(binding.source_key)
    if feature is None:
        return (
            None,
            AvailabilityState.NO_DATA,
            PopulationCompleteness.INCOMPLETE,
            (*_base_provenance(epoch, snapshot), f"feature:{binding.source_key}"),
        )
    if not isinstance(feature, FeatureValue):
        raise EvidenceAuthorityAdapterError("snapshot feature must be FeatureValue")
    availability, completeness = _feature_state(feature)
    if feature.status is not FeatureValueStatus.MISSING:
        expected = binding.expected_source_unit
        assert expected is not None
        if feature.unit != expected:
            raise EvidenceAuthorityAdapterError(
                f"source unit mismatch for {binding.source_key}: {feature.unit!r} != {expected!r}"
            )
    evidence_payloads = tuple(
        _evidence_payload(
            epoch=epoch,
            snapshot=snapshot,
            feature_name=binding.source_key,
            evidence=item,
        )
        for item in feature.evidence
    )
    refs = (
        *_base_provenance(epoch, snapshot),
        f"feature:{binding.source_key}",
        *(_evidence_ref(item) for item in evidence_payloads),
    )
    return feature.value, availability, completeness, tuple(dict.fromkeys(refs))


def _identity_value(
    epoch: EvidenceEpoch,
    snapshot: FeatureSnapshot,
    binding: F0EvidenceBinding,
) -> tuple[object, AvailabilityState, PopulationCompleteness, tuple[str, ...]]:
    marker = object()
    value = snapshot.identity.get(binding.source_key, marker)
    refs = (*_base_provenance(epoch, snapshot), f"identity:{binding.source_key}")
    if value is marker or value is None or (isinstance(value, str) and not value.strip()):
        return None, AvailabilityState.NO_DATA, PopulationCompleteness.INCOMPLETE, refs
    return value, AvailabilityState.RESOLVED, PopulationCompleteness.FULL, refs


def _trace_value(
    epoch: EvidenceEpoch,
    snapshot: FeatureSnapshot,
    binding: F0EvidenceBinding,
) -> tuple[object, AvailabilityState, PopulationCompleteness, tuple[str, ...]]:
    feature = snapshot.features.get(binding.source_key)
    refs = (*_base_provenance(epoch, snapshot), f"feature:{binding.source_key}")
    if feature is None:
        return (), AvailabilityState.NO_DATA, PopulationCompleteness.INCOMPLETE, refs
    if not isinstance(feature, FeatureValue):
        raise EvidenceAuthorityAdapterError("snapshot feature must be FeatureValue")
    availability, completeness = _feature_state(feature)
    payloads = tuple(
        _evidence_payload(
            epoch=epoch,
            snapshot=snapshot,
            feature_name=binding.source_key,
            evidence=item,
        )
        for item in feature.evidence
    )
    evidence_refs = tuple(_evidence_ref(item) for item in payloads)
    return payloads, availability, completeness, (*refs, *evidence_refs)


def _authority_id(
    *,
    epoch: EvidenceEpoch,
    snapshot: FeatureSnapshot,
    binding: F0EvidenceBinding,
    provenance_refs: tuple[str, ...],
) -> str:
    payload = {
        "epoch_id": epoch.epoch_id,
        "model_fingerprint": epoch.model_fingerprint,
        "source_fingerprint": epoch.source_fingerprint,
        "component_type": snapshot.component_type,
        "scope_ref": snapshot.component_id,
        "dependency_key": binding.dependency_key.value,
        "source_kind": binding.source_kind.value,
        "source_location": binding.source_location.value,
        "source_key": binding.source_key,
        "semantic_type": binding.semantic_type.value,
        "physical_dimension": binding.physical_dimension.value,
        "grain": binding.grain.value,
        "unit": binding.unit.identifier,
        "expected_source_unit": binding.expected_source_unit,
        "provenance_refs": list(provenance_refs),
    }
    digest = hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()
    return f"f0.4:{digest}"


def build_component_f0_authorities(
    *,
    epoch: EvidenceEpoch,
    snapshot: FeatureSnapshot,
    bindings: Sequence[F0EvidenceBinding],
) -> tuple[ExternalDependencyAuthority, ...]:
    """Build deterministic component-scoped F0 external authorities from explicit bindings."""
    if not isinstance(epoch, EvidenceEpoch):
        raise TypeError("epoch must be EvidenceEpoch")
    if not isinstance(snapshot, FeatureSnapshot):
        raise TypeError("snapshot must be FeatureSnapshot")
    items = tuple(bindings)
    if any(not isinstance(item, F0EvidenceBinding) for item in items):
        raise TypeError("bindings must contain F0EvidenceBinding")
    keys = [item.dependency_key for item in items]
    if len(keys) != len(set(keys)):
        raise EvidenceAuthorityAdapterError("duplicate DependencyKey binding")

    authorities: list[ExternalDependencyAuthority] = []
    for binding in sorted(items, key=lambda item: item.sort_key):
        if binding.source_location is EvidenceBindingSource.FEATURE_VALUE:
            value, availability, completeness, refs = _feature_value(epoch, snapshot, binding)
        elif binding.source_location is EvidenceBindingSource.SNAPSHOT_IDENTITY:
            value, availability, completeness, refs = _identity_value(epoch, snapshot, binding)
        else:
            value, availability, completeness, refs = _trace_value(epoch, snapshot, binding)

        refs = tuple(dict.fromkeys(refs))
        authority = ExternalDependencyAuthority(
            authority_id=_authority_id(
                epoch=epoch,
                snapshot=snapshot,
                binding=binding,
                provenance_refs=refs,
            ),
            key=binding.dependency_key,
            source_kind=binding.source_kind,
            semantic_type=binding.semantic_type,
            physical_dimension=binding.physical_dimension,
            grain=Grain.COMPONENT,
            scope_ref=snapshot.component_id,
            direction=None,
            unit=binding.unit,
            availability=availability,
            population_completeness=completeness,
            value=value,
            provenance_refs=refs,
        )
        authorities.append(authority)
    return tuple(authorities)


def build_f0_compile_inputs(
    *,
    rule_targets: Sequence[RuleScopeTarget],
    external_authorities: Sequence[ExternalDependencyAuthority],
) -> RegulatoryCompileInputs:
    """Delegate immutable ordering/validation to the canonical F0 constructor."""
    return RegulatoryCompileInputs(
        rule_targets=rule_targets,
        external_authorities=external_authorities,
    )


__all__ = [
    "EvidenceAuthorityAdapterError",
    "EvidenceBindingSource",
    "F0EvidenceBinding",
    "build_component_f0_authorities",
    "build_f0_compile_inputs",
]
