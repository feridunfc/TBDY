"""Semantic factual provider for ETABS response-combination definitions.

Exact CSI invocation and positional ABI decoding live in
``tbdy_engine.etabs.oapi.response_combinations``. This provider retains the
semantic evidence DTO, nested-combination traversal, and authority boundary.
The supported live path consumes typed OAPI facts from a verified session and
never receives raw RespCombo/SapModel capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError, ResponseComboFact
from tbdy_engine.etabs.oapi.response_combinations import (
    read_response_combo,
    read_response_combo_from_session,
)
from tbdy_engine.etabs.safety import EtabsVerifiedSession

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


def _promote_fact(
    fact: ResponseComboFact,
    *,
    read_child: Callable[[str], ResponseComboFact],
    stack: Sequence[str],
) -> EtabsComboDefinitionEvidence:
    combo_name = _text(fact.name, "combo_name")
    lineage = tuple(stack)
    if combo_name in lineage:
        raise EtabsComboDefinitionProviderError(
            "recursive response-combination cycle: " + " -> ".join((*lineage, combo_name))
        )
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
    nested: list[EtabsComboDefinitionEvidence] = []
    for item in constituents:
        if item.cname_type != "LOAD_COMBO":
            continue
        child = read_child(item.name)
        nested.append(
            _promote_fact(
                child,
                read_child=read_child,
                stack=(*lineage, combo_name),
            )
        )
    return EtabsComboDefinitionEvidence(
        name=fact.name,
        combo_type_code=fact.combo_type_code,
        combo_type=COMBO_TYPE_BY_CODE[fact.combo_type_code],
        constituents=constituents,
        nested_combos=tuple(nested),
        raw_get_type_combo=repr(fact.raw_get_type_combo),
        raw_get_case_list=repr(fact.raw_get_case_list),
    )


def capture_etabs_combo_definition(
    resp_combo: Any,
    name: str,
    *,
    stack: Sequence[str] = (),
) -> EtabsComboDefinitionEvidence:
    """Compatibility path for already-bounded raw callers."""
    combo_name = _text(name, "combo_name")
    return _promote_fact(
        _read_fact(resp_combo, combo_name),
        read_child=lambda child: _read_fact(resp_combo, child),
        stack=stack,
    )


def capture_etabs_combo_definitions(
    resp_combo: Any,
    names: Sequence[str],
) -> tuple[EtabsComboDefinitionEvidence, ...]:
    requested = tuple(_text(item, "combo_name") for item in names)
    if not requested or len(requested) != len(set(requested)):
        raise EtabsComboDefinitionProviderError("combo names must be a nonempty unique sequence")
    return tuple(capture_etabs_combo_definition(resp_combo, name) for name in requested)


def capture_etabs_combo_definition_from_session(
    session: EtabsVerifiedSession,
    name: str,
    *,
    stack: Sequence[str] = (),
) -> EtabsComboDefinitionEvidence:
    """Supported live path: verified session -> typed OAPI fact -> semantic evidence."""
    combo_name = _text(name, "combo_name")
    try:
        fact = read_response_combo_from_session(session, combo_name)
    except EtabsOAPIError as exc:
        raise EtabsComboDefinitionProviderError(str(exc)) from exc

    def read_child(child: str) -> ResponseComboFact:
        try:
            return read_response_combo_from_session(session, child)
        except EtabsOAPIError as exc:
            raise EtabsComboDefinitionProviderError(str(exc)) from exc

    return _promote_fact(fact, read_child=read_child, stack=stack)


def capture_etabs_combo_definitions_from_session(
    session: EtabsVerifiedSession,
    names: Sequence[str],
) -> tuple[EtabsComboDefinitionEvidence, ...]:
    requested = tuple(_text(item, "combo_name") for item in names)
    if not requested or len(requested) != len(set(requested)):
        raise EtabsComboDefinitionProviderError("combo names must be a nonempty unique sequence")
    return tuple(capture_etabs_combo_definition_from_session(session, name) for name in requested)


__all__ = [
    "CNAME_TYPE_BY_CODE",
    "COMBO_TYPE_BY_CODE",
    "EtabsComboConstituentEvidence",
    "EtabsComboDefinitionEvidence",
    "EtabsComboDefinitionProviderError",
    "capture_etabs_combo_definition",
    "capture_etabs_combo_definition_from_session",
    "capture_etabs_combo_definitions",
    "capture_etabs_combo_definitions_from_session",
]
