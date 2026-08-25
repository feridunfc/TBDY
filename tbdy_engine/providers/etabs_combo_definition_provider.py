"""Read-only ETABS response-combination definition acquisition.

This provider owns factual COM decoding only. It does not decide whether a
combination is acceptable for column design, does not reconstruct P-M2-M3
states, and does not emit a regulatory/design verdict. Those decisions belong
to the column design-demand engine.

The module is import-safe without ETABS/comtypes; callers pass an already
attached ``RespCombo`` object.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


COMBO_TYPE_BY_CODE = {
    0: "LINEAR_ADD",
    1: "ENVELOPE",
    2: "ABSOLUTE_ADD",
    3: "SRSS",
    4: "RANGE_ADD",
}

CNAME_TYPE_BY_CODE = {
    0: "LOAD_CASE",
    1: "LOAD_COMBO",
}


class EtabsComboDefinitionProviderError(RuntimeError):
    """Raised when the factual ETABS combo API result is malformed or failed."""


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


def _seq(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (tuple, list)):
        return tuple(value)
    return (value,)


def _api_sequence(raw: Any, *, method: str, name: str, expected_len: int) -> tuple[Any, ...]:
    """Accept tuple/list containers emitted by generated CSI COM bindings."""
    if not isinstance(raw, (tuple, list)):
        raise EtabsComboDefinitionProviderError(
            f"{method}({name!r}) returned unexpected scalar: {raw!r}"
        )
    values = tuple(raw)
    if len(values) != expected_len:
        raise EtabsComboDefinitionProviderError(
            f"{method}({name!r}) returned unexpected sequence length "
            f"{len(values)} (expected {expected_len}): {raw!r}"
        )
    return values


def _get_combo_type(resp_combo: Any, name: str) -> tuple[int, Any]:
    raw = resp_combo.GetTypeCombo(name)
    combo_type_raw, ret = _api_sequence(
        raw,
        method="GetTypeCombo",
        name=name,
        expected_len=2,
    )
    if not isinstance(ret, int) or ret != 0:
        raise EtabsComboDefinitionProviderError(f"GetTypeCombo({name!r}) failed/raw={raw!r}")
    combo_type = int(combo_type_raw)
    if combo_type not in COMBO_TYPE_BY_CODE:
        raise EtabsComboDefinitionProviderError(
            f"GetTypeCombo({name!r}) returned unknown combo type code {combo_type}; raw={raw!r}"
        )
    return combo_type, raw


def _get_case_list(resp_combo: Any, name: str) -> tuple[tuple[EtabsComboConstituentEvidence, ...], Any]:
    raw = resp_combo.GetCaseList(name)
    number_items_raw, cname_type_raw, cname_raw, sf_raw, ret = _api_sequence(
        raw,
        method="GetCaseList",
        name=name,
        expected_len=5,
    )
    if not isinstance(ret, int) or ret != 0:
        raise EtabsComboDefinitionProviderError(f"GetCaseList({name!r}) failed/raw={raw!r}")

    number_items = int(number_items_raw)
    types = _seq(cname_type_raw)
    names = _seq(cname_raw)
    factors = _seq(sf_raw)
    if not (number_items == len(types) == len(names) == len(factors)):
        raise EtabsComboDefinitionProviderError(
            f"GetCaseList({name!r}) count mismatch: n={number_items} "
            f"types={len(types)} names={len(names)} sf={len(factors)} raw={raw!r}"
        )

    rows: list[EtabsComboConstituentEvidence] = []
    for index, (kind_raw, child_name_raw, factor_raw) in enumerate(zip(types, names, factors)):
        kind = int(kind_raw)
        if kind not in CNAME_TYPE_BY_CODE:
            raise EtabsComboDefinitionProviderError(
                f"GetCaseList({name!r}) returned unknown CNameType={kind}"
            )
        child_name = _text(str(child_name_raw), f"GetCaseList({name!r}).name[{index}]")
        rows.append(
            EtabsComboConstituentEvidence(
                index=index,
                cname_type_code=kind,
                cname_type=CNAME_TYPE_BY_CODE[kind],
                name=child_name,
                scale_factor=float(factor_raw),
            )
        )
    return tuple(rows), raw


def capture_etabs_combo_definition(
    resp_combo: Any,
    name: str,
    *,
    stack: Sequence[str] = (),
) -> EtabsComboDefinitionEvidence:
    """Capture one factual ETABS combo definition, recursively including nested combos."""
    combo_name = _text(name, "combo_name")
    lineage = tuple(stack)
    if combo_name in lineage:
        raise EtabsComboDefinitionProviderError(
            "recursive response-combination cycle: " + " -> ".join((*lineage, combo_name))
        )

    combo_type_code, raw_type = _get_combo_type(resp_combo, combo_name)
    constituents, raw_case_list = _get_case_list(resp_combo, combo_name)
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
        name=combo_name,
        combo_type_code=combo_type_code,
        combo_type=COMBO_TYPE_BY_CODE[combo_type_code],
        constituents=constituents,
        nested_combos=nested,
        raw_get_type_combo=repr(raw_type),
        raw_get_case_list=repr(raw_case_list),
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
