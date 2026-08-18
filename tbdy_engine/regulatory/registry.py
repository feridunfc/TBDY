"""Immutable composition root for F0.0 regulatory rule definitions."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from .contracts import (
    CheckSpec,
    DependencyKey,
    DependencySpec,
    RegulatoryDerivationSpec,
    RuleId,
)

RuleDefinition = RegulatoryDerivationSpec | CheckSpec


def _dependency_payload(dep: DependencySpec) -> dict[str, object]:
    unit = dep.unit_requirement
    return {
        "key": dep.key.value,
        "source_kind": dep.source_kind.value,
        "semantic_type": dep.semantic_type.value,
        "physical_dimension": dep.physical_dimension.value,
        "grain": dep.grain.value,
        "scope_policy": dep.scope_policy.value,
        "direction_policy": dep.direction_policy.value,
        "required_availability": dep.required_availability.value,
        "population_completeness_requirement": dep.population_completeness_requirement.value,
        "unit_requirement": None if unit is None else unit.identifier,
    }


def _definition_payload(spec: RuleDefinition) -> dict[str, object]:
    common: dict[str, object] = {
        "rule_id": spec.rule_id.value,
        "rule_version": spec.rule_version,
        "code_refs": list(spec.code_refs),
        "dependencies": [_dependency_payload(dep) for dep in spec.dependencies],
        "applicability_binding": spec.applicability.binding_id,
        "applicability_input_type": f"{spec.applicability.input_type.__module__}.{spec.applicability.input_type.__qualname__}",
        "evaluator_binding": spec.evaluator.binding_id,
        "evaluator_input_type": f"{spec.evaluator.input_type.__module__}.{spec.evaluator.input_type.__qualname__}",
    }
    if isinstance(spec, RegulatoryDerivationSpec):
        out = spec.output_contract
        common.update(
            {
                "kind": "DERIVATION",
                "output_authority": out.authority_key.value,
                "output_semantic_type": out.semantic_type.value,
                "output_physical_dimension": out.physical_dimension.value,
                "output_grain": out.grain.value,
                "output_unit": out.unit.identifier,
            }
        )
    else:
        common.update(
            {
                "kind": "CHECK",
                "formal_result_type": spec.formal_result_type.__qualname__,
            }
        )
    return common


@dataclass(frozen=True, slots=True)
class RegulatoryRegistry:
    """Deterministic immutable registry; it does not compile or execute rules."""

    derivations: tuple[RegulatoryDerivationSpec, ...]
    checks: tuple[CheckSpec, ...]
    registry_version: str
    _rules_by_id: Mapping[RuleId, RuleDefinition] = field(repr=False, compare=False)
    _derivations_by_output: Mapping[DependencyKey, RegulatoryDerivationSpec] = field(
        repr=False, compare=False
    )

    def __init__(
        self,
        *,
        derivations: tuple[RegulatoryDerivationSpec, ...] | list[RegulatoryDerivationSpec] = (),
        checks: tuple[CheckSpec, ...] | list[CheckSpec] = (),
    ) -> None:
        derivation_items = tuple(derivations)
        check_items = tuple(checks)
        if not all(isinstance(item, RegulatoryDerivationSpec) for item in derivation_items):
            raise TypeError("derivations must contain RegulatoryDerivationSpec")
        if not all(isinstance(item, CheckSpec) for item in check_items):
            raise TypeError("checks must contain CheckSpec")

        all_items: tuple[RuleDefinition, ...] = derivation_items + check_items
        rule_ids = [item.rule_id for item in all_items]
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("duplicate RuleId in RegulatoryRegistry")

        output_keys = [item.output_contract.authority_key for item in derivation_items]
        if len(set(output_keys)) != len(output_keys):
            raise ValueError("duplicate regulatory output authority in RegulatoryRegistry")

        sorted_derivations = tuple(sorted(derivation_items, key=lambda item: item.rule_id.value))
        sorted_checks = tuple(sorted(check_items, key=lambda item: item.rule_id.value))
        sorted_all = tuple(sorted(all_items, key=lambda item: item.rule_id.value))

        payload = [_definition_payload(item) for item in sorted_all]
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        registry_version = f"f0.0:{digest}"

        rules_by_id = MappingProxyType({item.rule_id: item for item in sorted_all})
        derivations_by_output = MappingProxyType(
            {item.output_contract.authority_key: item for item in sorted_derivations}
        )

        object.__setattr__(self, "derivations", sorted_derivations)
        object.__setattr__(self, "checks", sorted_checks)
        object.__setattr__(self, "registry_version", registry_version)
        object.__setattr__(self, "_rules_by_id", rules_by_id)
        object.__setattr__(self, "_derivations_by_output", derivations_by_output)

    def rule(self, rule_id: RuleId) -> RuleDefinition:
        if not isinstance(rule_id, RuleId):
            raise TypeError("rule_id must be RuleId")
        return self._rules_by_id[rule_id]

    @property
    def rule_count(self) -> int:
        return len(self._rules_by_id)


__all__ = ["RegulatoryRegistry"]
