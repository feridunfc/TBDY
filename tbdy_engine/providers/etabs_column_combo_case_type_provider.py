"""B5-bound factual load-case type semantics for Column combo authority.

This module does not choose combinations or engineering demand semantics. It
projects the exact ``LoadCaseTypeRuntimeFact`` population already captured by
controlled B5 execution into the canonical vocabulary consumed by the existing
Column combo-pattern authority.

CSI ``eLoadCaseType`` values used here are documented API enum identities:
LinearStatic=1 and ResponseSpectrum=4. Unsupported case types fail closed
instead of being inferred from case names.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from tbdy_engine.etabs.oapi.analysis_execution import LoadCaseTypeRuntimeFact


CSI_CASE_TYPE_LINEAR_STATIC = 1
CSI_CASE_TYPE_RESPONSE_SPECTRUM = 4

_COLUMN_COMBO_CASE_TYPE_BY_CSI = {
    CSI_CASE_TYPE_LINEAR_STATIC: "LinStatic",
    CSI_CASE_TYPE_RESPONSE_SPECTRUM: "LinRespSpec",
}


class EtabsColumnComboCaseTypeError(ValueError):
    """Raised when B5 facts cannot prove the case-type semantics required downstream."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsColumnComboCaseTypeError(f"{label} must be a nonblank canonical string")
    return value


@dataclass(frozen=True, slots=True)
class EtabsColumnComboCaseTypePopulation:
    case_types: Mapping[str, str]
    source_refs: tuple[str, ...]
    status: str = "PROVEN_B5_COLUMN_COMBO_CASE_TYPES"

    def __post_init__(self) -> None:
        mapping = dict(self.case_types)
        if not mapping:
            raise EtabsColumnComboCaseTypeError("case_types must be nonempty")
        for name, semantic in mapping.items():
            _text(name, "case_name")
            if semantic not in {"LinStatic", "LinRespSpec"}:
                raise EtabsColumnComboCaseTypeError(
                    f"unsupported canonical Column combo case type: {semantic!r}"
                )
        refs = tuple(sorted({_text(item, "source_ref") for item in self.source_refs}))
        if not refs:
            raise EtabsColumnComboCaseTypeError("case-type population requires source refs")
        object.__setattr__(self, "case_types", MappingProxyType(dict(sorted(mapping.items()))))
        object.__setattr__(self, "source_refs", refs)


def project_b5_column_combo_case_types(
    facts: Sequence[LoadCaseTypeRuntimeFact],
    *,
    required_case_names: Sequence[str],
    analysis_result_identity_ref: str,
    execution_proof_ref: str,
) -> EtabsColumnComboCaseTypePopulation:
    """Project exact B5 case-type facts for the required flattened combo leaves."""
    required = tuple(sorted({_text(item, "required_case_name") for item in required_case_names}))
    if not required:
        raise EtabsColumnComboCaseTypeError("required_case_names must be nonempty")
    if len(required) != len(tuple(required_case_names)):
        raise EtabsColumnComboCaseTypeError("required_case_names must be unique")

    rows = tuple(facts)
    if any(not isinstance(item, LoadCaseTypeRuntimeFact) for item in rows):
        raise TypeError("facts must contain LoadCaseTypeRuntimeFact")
    by_name = {item.case_name: item for item in rows}
    if len(by_name) != len(rows):
        raise EtabsColumnComboCaseTypeError("B5 case-type population contains duplicate case names")

    missing = tuple(name for name in required if name not in by_name)
    if missing:
        raise EtabsColumnComboCaseTypeError(
            "B5 case-type population is missing required combo leaf case(s): " + ", ".join(missing)
        )

    projected: dict[str, str] = {}
    refs = [_text(analysis_result_identity_ref, "analysis_result_identity_ref"),
            _text(execution_proof_ref, "execution_proof_ref")]
    for name in required:
        fact = by_name[name]
        if not fact.success:
            raise EtabsColumnComboCaseTypeError(
                f"B5 load-case type fact for {name!r} has nonzero return code"
            )
        semantic = _COLUMN_COMBO_CASE_TYPE_BY_CSI.get(fact.case_type)
        if semantic is None:
            raise EtabsColumnComboCaseTypeError(
                f"B5 load case {name!r} has unsupported CSI eLoadCaseType={fact.case_type}"
            )
        projected[name] = semantic
        refs.append(fact.evidence_ref)

    return EtabsColumnComboCaseTypePopulation(
        case_types=projected,
        source_refs=tuple(refs),
    )


__all__ = [
    "CSI_CASE_TYPE_LINEAR_STATIC",
    "CSI_CASE_TYPE_RESPONSE_SPECTRUM",
    "EtabsColumnComboCaseTypeError",
    "EtabsColumnComboCaseTypePopulation",
    "project_b5_column_combo_case_types",
]
