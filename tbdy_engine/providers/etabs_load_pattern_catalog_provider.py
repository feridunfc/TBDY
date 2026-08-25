"""Read-only factual ETABS load-pattern catalog acquisition.

This provider enumerates the full LoadPatterns.GetNameList population and binds
each name to the exact GetLoadType result already decoded by the static-linear
case provider.  It performs no TS500 action-role or direction promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tbdy_engine.providers.etabs_static_linear_case_provider import (
    EtabsLoadPatternTypeEvidence,
    EtabsStaticLinearCaseProviderError,
    capture_etabs_load_pattern_type,
)


@dataclass(frozen=True, slots=True)
class EtabsLoadPatternCatalogEvidence:
    patterns: tuple[EtabsLoadPatternTypeEvidence, ...]
    raw_get_name_list: str
    status: str = "PROVEN_FACTUAL_LOAD_PATTERN_CATALOG"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "patterns": [item.as_dict() for item in self.patterns],
            "raw_api": {"GetNameList": self.raw_get_name_list},
        }


def capture_etabs_load_pattern_catalog(load_patterns: Any) -> EtabsLoadPatternCatalogEvidence:
    raw = load_patterns.GetNameList()
    if not isinstance(raw, (tuple, list)) or len(raw) != 3:
        raise EtabsStaticLinearCaseProviderError(
            f"LoadPatterns.GetNameList returned unexpected result: {raw!r}"
        )
    count_raw, names_raw, ret = tuple(raw)
    if not isinstance(ret, int) or ret != 0:
        raise EtabsStaticLinearCaseProviderError(
            f"LoadPatterns.GetNameList failed/raw={raw!r}"
        )
    try:
        count = int(count_raw)
    except (TypeError, ValueError) as exc:
        raise EtabsStaticLinearCaseProviderError(
            f"LoadPatterns.GetNameList returned non-integer count/raw={raw!r}"
        ) from exc
    if count < 0:
        raise EtabsStaticLinearCaseProviderError("LoadPatterns.GetNameList returned negative count")
    if names_raw is None:
        names = ()
    elif isinstance(names_raw, (tuple, list)):
        names = tuple(names_raw)
    else:
        names = (names_raw,)
    if count != len(names):
        raise EtabsStaticLinearCaseProviderError(
            f"LoadPatterns.GetNameList count mismatch: n={count} names={len(names)}"
        )
    canonical = tuple(str(name) for name in names)
    if not canonical or any(not name.strip() or name != name.strip() for name in canonical):
        raise EtabsStaticLinearCaseProviderError("load-pattern catalog names must be nonblank canonical strings")
    if len(set(canonical)) != len(canonical):
        raise EtabsStaticLinearCaseProviderError("load-pattern catalog names must be unique")
    patterns = tuple(capture_etabs_load_pattern_type(load_patterns, name) for name in canonical)
    return EtabsLoadPatternCatalogEvidence(
        patterns=patterns,
        raw_get_name_list=repr(raw),
    )


__all__ = [
    "EtabsLoadPatternCatalogEvidence",
    "capture_etabs_load_pattern_catalog",
]
