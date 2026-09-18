"""Source-bound TS500/TBDY concrete shear contribution for COLUMN-R1 A37.

Owns Vcr/Vc only; no Nd/row selection, no Asw/Vw/Vr, no final verdict.
Units: mm, MPa, N (compression-positive signed axial), kN.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.regulatory.sources.fnd_col_1_longitudinal import (
    SOURCE_DATA,
    TBDY_SOURCE_ID,
    TS500_SOURCE_ID,
)

COLUMN_VC_AUTHORITY = "COLUMN_R1_SOURCE_BOUND_VCR_VC"
TS500_VC_LOCATORS = ("3.3.2 Eq.3.1", "6.2.5 Eq.6.2", "8.1.3 Eq.8.1", "8.1.4 Eq.8.4")
TBDY_HD_VC_ZERO_LOCATOR = "7.3.7.6"


class ColumnShearVcError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnShearVcError(f"{label} must be a nonblank canonical string")
    return value


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnShearVcError(f"{label} must be numeric")
    out = float(value)
    if not math.isfinite(out):
        raise ColumnShearVcError(f"{label} must be finite")
    return out


def _positive(value: object, label: str) -> float:
    out = _finite(value, label)
    if out <= 0.0:
        raise ColumnShearVcError(f"{label} must be > 0")
    return out


def _nonnegative(value: object, label: str) -> float:
    out = _finite(value, label)
    if out < 0.0:
        raise ColumnShearVcError(f"{label} must be >= 0")
    return out


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError("source_refs must be a sequence")
    refs = tuple(dict.fromkeys(_text(x, "source_ref") for x in values))
    if not refs:
        raise ColumnShearVcError("source_refs must be nonempty")
    return refs


def _source_ref(source_id: str, locator: str) -> str:
    return f"regulatory-source:{source_id}:{SOURCE_DATA[source_id][4]}:{locator}"


@dataclass(frozen=True, slots=True)
class QualifiedColumnVc:
    component_id: str
    direction: str
    vc_kn: float
    vcr_kn: float
    fctk_mpa: float
    fctd_mpa: float
    gamma_mc: float
    axial_nd_signed_compression_n: float
    axial_gamma: float
    high_ductility_suppression_applied: bool
    source_refs: tuple[str, ...]
    authority: str = COLUMN_VC_AUTHORITY

    def __post_init__(self) -> None:
        _text(self.component_id, "component_id")
        if self.direction not in {"V2", "V3"}:
            raise ColumnShearVcError("direction must be V2 or V3")
        for name in ("vc_kn", "vcr_kn", "fctk_mpa", "fctd_mpa", "gamma_mc"):
            _nonnegative(getattr(self, name), name)
        _finite(self.axial_nd_signed_compression_n, "axial_nd_signed_compression_n")
        _finite(self.axial_gamma, "axial_gamma")
        if type(self.high_ductility_suppression_applied) is not bool:
            raise TypeError("high_ductility_suppression_applied must be bool")
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


def qualify_column_vc(
    *,
    component_id: str,
    direction: str,
    fck_mpa: float,
    fcd_mpa: float,
    gross_area_ac_mm2: float,
    web_width_bw_mm: float,
    effective_depth_d_mm: float,
    ts500_axial_nd_signed_compression_n: float,
    high_ductility_applies: bool,
    limited_ductility_applies: bool,
    earthquake_only_shear_kn: float | None = None,
    total_seismic_shear_kn: float | None = None,
    suppression_axial_nd_signed_compression_n: float | None = None,
    suppression_concurrency_proven: bool | None = None,
    source_refs: Sequence[str] = (),
) -> QualifiedColumnVc:
    component = _text(component_id, "component_id")
    if direction not in {"V2", "V3"}:
        raise ColumnShearVcError("direction must be V2 or V3")
    if type(high_ductility_applies) is not bool or type(limited_ductility_applies) is not bool:
        raise TypeError("ductility applicability flags must be bool")
    if high_ductility_applies == limited_ductility_applies:
        raise ColumnShearVcError("exactly one of HIGH or LIMITED ductility must apply")

    fck = _positive(fck_mpa, "fck_mpa")
    fcd = _positive(fcd_mpa, "fcd_mpa")
    ac = _positive(gross_area_ac_mm2, "gross_area_ac_mm2")
    bw = _positive(web_width_bw_mm, "web_width_bw_mm")
    d = _positive(effective_depth_d_mm, "effective_depth_d_mm")
    nd_signed = _finite(ts500_axial_nd_signed_compression_n, "ts500_axial_nd_signed_compression_n")

    # TS500 Eq.3.1 + Eq.6.2.
    gamma_mc = fck / fcd
    if gamma_mc < 1.0 - 1e-9:
        raise ColumnShearVcError("reviewed fck/fcd implies gamma_mc < 1.0")
    fctk = 0.35 * math.sqrt(fck)
    fctd = fctk / gamma_mc

    # TS500 Eq.8.1: Nd magnitude positive; sign selects gamma.
    if nd_signed >= 0.0:
        axial_gamma, nd_magnitude = 0.07, nd_signed
    else:
        axial_gamma, nd_magnitude = -0.30, abs(nd_signed)
    axial_factor = 1.0 + axial_gamma * nd_magnitude / ac
    if axial_factor <= 0.0:
        raise ColumnShearVcError("TS500 Eq.8.1 axial factor is nonpositive")

    vcr_kn = 0.65 * fctd * bw * d * axial_factor / 1000.0
    vc_kn = 0.8 * vcr_kn

    refs = list(_refs(source_refs))
    refs.extend(_source_ref(TS500_SOURCE_ID, loc) for loc in TS500_VC_LOCATORS)
    suppressed = False

    if high_ductility_applies:
        if suppression_concurrency_proven is not True:
            raise ColumnShearVcError(
                "HIGH Vc qualification requires proven concurrent "
                "earthquake-only / total-seismic evidence"
            )
        if earthquake_only_shear_kn is None or total_seismic_shear_kn is None or suppression_axial_nd_signed_compression_n is None:
            raise ColumnShearVcError(
                "HIGH Vc qualification requires complete TBDY 7.3.7.6 suppression facts"
            )
        eq_only = _nonnegative(earthquake_only_shear_kn, "earthquake_only_shear_kn")
        total = _nonnegative(total_seismic_shear_kn, "total_seismic_shear_kn")
        suppression_nd = _finite(
            suppression_axial_nd_signed_compression_n,
            "suppression_axial_nd_signed_compression_n",
        )
        shear_condition = eq_only > 0.5 * total
        axial_condition = suppression_nd <= 0.05 * ac * fck + 1e-9
        suppressed = shear_condition and axial_condition
        if suppressed:
            vc_kn = 0.0
        refs.append(_source_ref(TBDY_SOURCE_ID, TBDY_HD_VC_ZERO_LOCATOR))

    return QualifiedColumnVc(
        component_id=component,
        direction=direction,
        vc_kn=vc_kn,
        vcr_kn=vcr_kn,
        fctk_mpa=fctk,
        fctd_mpa=fctd,
        gamma_mc=gamma_mc,
        axial_nd_signed_compression_n=nd_signed,
        axial_gamma=axial_gamma,
        high_ductility_suppression_applied=suppressed,
        source_refs=tuple(dict.fromkeys(refs)),
    )


__all__ = [
    "COLUMN_VC_AUTHORITY",
    "ColumnShearVcError",
    "QualifiedColumnVc",
    "qualify_column_vc",
]
