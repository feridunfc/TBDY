"""Semantic factual ETABS load-pattern catalog provider.

Exact ``LoadPatterns.GetNameList`` and ``GetLoadType`` ABI ownership lives in
``tbdy_engine.etabs.oapi.load_definitions``. Supported live acquisition consumes
only a verified session; raw LoadPatterns does not escape.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.oapi.load_definitions import (
    read_load_pattern_names,
    read_load_pattern_names_from_session,
)
from tbdy_engine.etabs.safety import EtabsVerifiedSession
from tbdy_engine.providers.etabs_static_linear_case_provider import (
    EtabsLoadPatternTypeEvidence,
    EtabsStaticLinearCaseProviderError,
    capture_etabs_load_pattern_type,
    capture_etabs_load_pattern_type_from_session,
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
    """Compatibility path for an already-bounded raw LoadPatterns interface."""
    try:
        names, raw = read_load_pattern_names(load_patterns)
    except EtabsOAPIError as exc:
        raise EtabsStaticLinearCaseProviderError(str(exc)) from exc
    if not names:
        raise EtabsStaticLinearCaseProviderError("load-pattern catalog must not be empty")
    patterns = tuple(capture_etabs_load_pattern_type(load_patterns, name) for name in names)
    return EtabsLoadPatternCatalogEvidence(patterns=patterns, raw_get_name_list=repr(raw))


def capture_etabs_load_pattern_catalog_from_session(
    session: EtabsVerifiedSession,
) -> EtabsLoadPatternCatalogEvidence:
    """Supported live path through OAPI -> safety -> gateway."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    try:
        names, raw = read_load_pattern_names_from_session(session)
    except EtabsOAPIError as exc:
        raise EtabsStaticLinearCaseProviderError(str(exc)) from exc
    if not names:
        raise EtabsStaticLinearCaseProviderError("load-pattern catalog must not be empty")
    patterns = tuple(
        capture_etabs_load_pattern_type_from_session(session, name)
        for name in names
    )
    return EtabsLoadPatternCatalogEvidence(patterns=patterns, raw_get_name_list=repr(raw))


__all__ = [
    "EtabsLoadPatternCatalogEvidence",
    "capture_etabs_load_pattern_catalog",
    "capture_etabs_load_pattern_catalog_from_session",
]
