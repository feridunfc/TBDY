"""Semantic factual provider for ETABS response-combination definitions.

Exact CSI invocation and positional ABI decoding live in
``tbdy_engine.etabs.oapi.response_combinations``. This provider retains the
semantic evidence DTO, nested-combination traversal, and authority boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError, ResponseComboFact
from tbdy_engine.etabs.oapi.response_combinations import read_response_combo

COMBO_TYPE_BY_CODE = {
    0: "LINEAR_ADD",
    1: "ENVELOPE",
    2: "ABSOLUTE_ADD",
    3: "SRSS",
    4: "RANGE_ADD",
}
CNAME_TYPE_BY_CODE = {0: "LOAD_CASE", 1: "LOAD_COMBO"}


class EtabsComboDefinitionProviderError(RuntimeError):
    """Raised when factual ETABS combo evidence cannot be promoted semantically."""


@dataclass(frozen=True, slots=True)
class EtabsComboConstituentEvidence:
    index: int
    cname_type_code: int
    cname_type: str
    name: str
    scale_factor: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "cname_type_code": self.cname_type_code,
            "cname_type": self.cname_type,
            "name": self.name,
            "scale_factor": self.scale_factor,
        }


@dataclass(frozen=True, slots=True)
class EtabsComboDefinitionEvidence:
    name: str
    combo_type_code: int
    combo_type: str
    constituents: tuple[EtabsComboConstituentEvidence, ...]
    nested_combos: tuple["EtabsComboDefinitionEvidence", ...]
    raw_get_type_combo: str
    raw_get_case_list: str
    status: str = "PROVEN_FACTUAL_COMBO_DEFINITION"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "combo_type_code": self.combo_type_code,
            "combo_type": self.combo_type,
            "constituents": [item.as_dict() for item in self.constituents],
            "nested_combos": [item.as_dict() for item in self.nested_combos],
            "raw_api": {
                "GetTypeCombo": self.raw_get_type_combo,
                "GetCaseList": self.raw_get_case_list,
            },
        }


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsComboDefinitionProviderError(f"{label} must be a nonblank canonical string")
    return value


def _read_fact(resp_combo: Any, name: str) -> ResponseComboFact:
    try:
        return read_response_combo(resp_combo, name)
    except EtabsOAPIError as exc:
        raise EtabsComboDefinitionProviderError(str(exc)) from exc


def capture_etabs_combo_definition(
    resp_combo: Any,
    name: str,
    *,
    stack: Sequence[str] = (),
) -> EtabsComboDefinitionEvidence:
    """Promote one OAPI fact into semantic combo evidence, including nesting."""
    combo_name = _text(name, "combo_name")
    lineage = tuple(stack)
    if combo_name in lineage:
        raise EtabsComboDefinitionProviderError(
            "recursive response-combination cycle: " + " -> ".join((*lineage, combo_name))
        )

    fact = _read_fact(resp_combo, combo_name)
    constituents = tuple(
        EtabsComboConstituentEvidence(
            index=item.index,
            cname_type_code=item.cname_type_code,
            cname_type=CNAME_TYPE_BY_CODE[item.cname_type_code],
            name=item.name,
            scale_factor=item.scale_factor,
        )
        for item in fact.constituents
    )
    nested = tuple(
        capture_etabs_combo_definition(
            resp_combo,
            item.name,
            stack=(*lineage, combo_name),
        )
        for item in constituents
        if item.cname_type == "LOAD_COMBO"
    )
    return EtabsComboDefinitionEvidence(
        name=fact.name,
        combo_type_code=fact.combo_type_code,
        combo_type=COMBO_TYPE_BY_CODE[fact.combo_type_code],
        constituents=constituents,
        nested_combos=nested,
        raw_get_type_combo=repr(fact.raw_get_type_combo),
        raw_get_case_list=repr(fact.raw_get_case_list),
    )


def capture_etabs_combo_definitions(
    resp_combo: Any,
    names: Sequence[str],
) -> tuple[EtabsComboDefinitionEvidence, ...]:
    requested = tuple(_text(item, "combo_name") for item in names)
    if not requested or len(requested) != len(set(requested)):
        raise EtabsComboDefinitionProviderError("combo names must be a nonempty unique sequence")
    return tuple(capture_etabs_combo_definition(resp_combo, name) for name in requested)


__all__ = [
    "CNAME_TYPE_BY_CODE",
    "COMBO_TYPE_BY_CODE",
    "EtabsComboConstituentEvidence",
    "EtabsComboDefinitionEvidence",
    "EtabsComboDefinitionProviderError",
    "capture_etabs_combo_definition",
    "capture_etabs_combo_definitions",
]
