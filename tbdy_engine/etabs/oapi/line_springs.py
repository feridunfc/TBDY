"""Typed factual ETABS line-spring property-universe read boundary.

This module owns only the factual ``PropLineSpring.GetNameList`` read.
It does not infer per-frame assignment from ``FrameObj.GetSpringAssignment``
failure codes and it does not decide TS500 Eq.7.13 applicability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Sequence

from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.safety import (
    EtabsVerifiedSession,
    _execute_verified_read,
)


LINE_SPRING_PROPERTY_UNIVERSE_CONTRACT = (
    "ETABS_LINE_SPRING_PROPERTY_UNIVERSE_V1"
)
LINE_SPRING_PROPERTY_UNIVERSE_EVIDENCE_PREFIX = (
    "etabs-line-spring-property-universe:sha256:"
)


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise EtabsOAPIError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")

    return (
        LINE_SPRING_PROPERTY_UNIVERSE_EVIDENCE_PREFIX
        + hashlib.sha256(encoded).hexdigest()
    )


@dataclass(frozen=True, slots=True)
class LineSpringPropertyUniverseFact:
    property_names: tuple[str, ...]
    reported_count: int
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = LINE_SPRING_PROPERTY_UNIVERSE_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != LINE_SPRING_PROPERTY_UNIVERSE_CONTRACT:
            raise EtabsOAPIError(
                "line-spring property-universe contract mismatch"
            )

        if (
            type(self.reported_count) is not int
            or self.reported_count < 0
        ):
            raise EtabsOAPIError(
                "reported_count must be an integer >= 0"
            )

        if type(self.return_code) is not int:
            raise EtabsOAPIError(
                "return_code must be an integer"
            )

        names = tuple(
            _text(name, "line_spring_property_name")
            for name in self.property_names
        )

        if len(names) != self.reported_count:
            raise EtabsOAPIError(
                "PropLineSpring.GetNameList count/name mismatch"
            )

        if len(names) != len(set(names)):
            raise EtabsOAPIError(
                "PropLineSpring.GetNameList returned duplicate identities"
            )

        object.__setattr__(
            self,
            "property_names",
            names,
        )

        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                {
                    "contract": self.contract,
                    "property_names": names,
                    "reported_count": self.reported_count,
                    "return_code": self.return_code,
                }
            ),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0

    @property
    def proven_empty(self) -> bool:
        return (
            self.success
            and self.reported_count == 0
            and not self.property_names
        )


def _decode_get_name_list(
    raw: object,
) -> tuple[int, tuple[str, ...], int]:
    if (
        not isinstance(raw, (tuple, list))
        or len(raw) != 3
    ):
        raise EtabsOAPIError(
            "PropLineSpring.GetNameList returned "
            f"unsupported Python ABI shape: {raw!r}"
        )

    count_raw, names_raw, return_code = tuple(raw)

    if (
        type(count_raw) is not int
        or count_raw < 0
    ):
        raise EtabsOAPIError(
            "PropLineSpring.GetNameList returned invalid count"
        )

    if type(return_code) is not int:
        raise EtabsOAPIError(
            "PropLineSpring.GetNameList returned invalid return code"
        )

    if names_raw is None:
        names: tuple[object, ...] = ()
    elif isinstance(names_raw, str):
        names = (names_raw,)
    elif (
        isinstance(names_raw, Sequence)
        and not isinstance(names_raw, (str, bytes))
    ):
        names = tuple(names_raw)
    else:
        raise EtabsOAPIError(
            "PropLineSpring.GetNameList returned unsupported "
            "name-list payload"
        )

    canonical = tuple(
        _text(name, "PropLineSpring.GetNameList.name")
        for name in names
    )

    if len(canonical) != count_raw:
        raise EtabsOAPIError(
            "PropLineSpring.GetNameList count/name mismatch"
        )

    if len(canonical) != len(set(canonical)):
        raise EtabsOAPIError(
            "PropLineSpring.GetNameList returned duplicate identities"
        )

    return count_raw, canonical, return_code


def read_line_spring_property_universe_from_session(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> LineSpringPropertyUniverseFact:
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError(
            "session must be EtabsVerifiedSession"
        )

    timeout = float(timeout_seconds)

    if timeout <= 0.0:
        raise ValueError(
            "timeout_seconds must be greater than zero"
        )

    def acquire(
        _application: object,
        model_api: Any,
    ) -> LineSpringPropertyUniverseFact:
        raw = model_api.PropLineSpring.GetNameList()

        (
            count,
            names,
            return_code,
        ) = _decode_get_name_list(raw)

        return LineSpringPropertyUniverseFact(
            property_names=names,
            reported_count=count,
            return_code=return_code,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation="oapi_prop_line_spring_get_name_list",
        timeout_seconds=timeout,
    )


__all__ = [
    "LINE_SPRING_PROPERTY_UNIVERSE_CONTRACT",
    "LINE_SPRING_PROPERTY_UNIVERSE_EVIDENCE_PREFIX",
    "LineSpringPropertyUniverseFact",
    "read_line_spring_property_universe_from_session",
]
