"""Reviewed TS 500 Table 3.2 concrete elastic-modulus authority.

Bounded to normal-weight 28-day concrete classes listed in TS 500:2000
Table 3.2.  Values are represented in canonical MPa decimals and compared
exactly; this module owns no ETABS mutation or factual acquisition.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

TS500_TABLE_3_2_SOURCE_REF = "TS500_2000_TABLE_3_2"
TS500_3_3_3_1_SOURCE_REF = "TS500_2000_3_3_3_1"
TS500_EC_NUMERICAL_POLICY = "EXACT_CANONICAL_MPA_DECIMAL"

# TS 500:2000 Table 3.2: characteristic cylinder strength fck -> 28-day Ec.
_TS500_EC_MPA_BY_FCK: dict[Decimal, Decimal] = {
    Decimal("16"): Decimal("27000"),
    Decimal("18"): Decimal("27500"),
    Decimal("20"): Decimal("28000"),
    Decimal("25"): Decimal("30000"),
    Decimal("30"): Decimal("32000"),
    Decimal("35"): Decimal("33000"),
    Decimal("40"): Decimal("34000"),
    Decimal("45"): Decimal("36000"),
    Decimal("50"): Decimal("37000"),
}


class Ts500EcComparisonStatus(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNRESOLVED = "UNRESOLVED"


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be numeric")
    try:
        result = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class Ts500ConcreteEcComparison:
    fck_mpa: Decimal
    factual_etabs_ec_mpa: Decimal
    required_ts500_ec_mpa: Decimal | None
    status: Ts500EcComparisonStatus
    numerical_policy: str = TS500_EC_NUMERICAL_POLICY
    source_refs: tuple[str, ...] = (
        TS500_TABLE_3_2_SOURCE_REF,
        TS500_3_3_3_1_SOURCE_REF,
    )

    @property
    def positive(self) -> bool:
        return self.status is Ts500EcComparisonStatus.MATCH

    def require_match(self) -> None:
        if not self.positive:
            raise ValueError(
                f"TS500 Ec comparison is not positive: {self.status.value}; "
                f"fck={self.fck_mpa} MPa factual_Ec={self.factual_etabs_ec_mpa} MPa "
                f"required_Ec={self.required_ts500_ec_mpa!r}"
            )


def compare_etabs_ec_to_ts500_table_3_2(
    *,
    concrete_fck_mpa: object,
    factual_etabs_ec_mpa: object,
) -> Ts500ConcreteEcComparison:
    """Compare exact canonical MPa facts; no tolerance and no interpolation."""
    fck = _decimal(concrete_fck_mpa, "concrete_fck_mpa")
    factual = _decimal(factual_etabs_ec_mpa, "factual_etabs_ec_mpa")
    required = _TS500_EC_MPA_BY_FCK.get(fck)
    if required is None:
        status = Ts500EcComparisonStatus.UNRESOLVED
    elif factual == required:
        status = Ts500EcComparisonStatus.MATCH
    else:
        status = Ts500EcComparisonStatus.MISMATCH
    return Ts500ConcreteEcComparison(
        fck_mpa=fck,
        factual_etabs_ec_mpa=factual,
        required_ts500_ec_mpa=required,
        status=status,
    )


__all__ = [
    "TS500_3_3_3_1_SOURCE_REF",
    "TS500_EC_NUMERICAL_POLICY",
    "TS500_TABLE_3_2_SOURCE_REF",
    "Ts500ConcreteEcComparison",
    "Ts500EcComparisonStatus",
    "compare_etabs_ec_to_ts500_table_3_2",
]
