from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class MemberMomentCapacity:
    element_id: str
    story: str = ""
    member_type: str = ""
    source: str = "unknown"

    m_pos_knm: Optional[float] = None
    m_neg_knm: Optional[float] = None
    m_governing_knm: Optional[float] = None

    status: str = "NO_DATA"
    evaluation_level: str = "NO_DATA"
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScwbJointResult:
    joint_id: str
    story: str
    direction: str

    columns: list[str]
    beams: list[str]

    sum_mrc_knm: float
    sum_mrb_knm: float
    required_mrc_knm: float
    ratio: float

    status: str
    evaluation_level: str
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        v = float(str(value).replace(",", "."))
        if v != v:
            return default
        return v
    except Exception:
        return default


def rectangular_moment_capacity_knm(
    *,
    as_mm2: float,
    b_mm: float,
    d_mm: float,
    fyd_mpa: float,
    fcd_mpa: float,
) -> float:
    """
    TS500 rectangular stress block approximation.

    a = As * fyd / (0.85 * fcd * b)
    Mrd = As * fyd * (d - a/2)

    Units:
    As: mm2
    fyd/fcd: MPa = N/mm2
    b,d,a: mm
    Mrd: Nmm -> kNm
    """
    if as_mm2 <= 0 or b_mm <= 0 or d_mm <= 0 or fyd_mpa <= 0 or fcd_mpa <= 0:
        return 0.0

    a_mm = as_mm2 * fyd_mpa / max(0.85 * fcd_mpa * b_mm, 1e-9)
    a_mm = max(0.0, min(a_mm, 0.85 * d_mm))
    z_mm = max(d_mm - a_mm / 2.0, 0.0)

    return as_mm2 * fyd_mpa * z_mm / 1_000_000.0


def beam_moment_capacity(
    *,
    element_id: str,
    story: str,
    width_mm: float,
    depth_mm: float,
    as_top_mm2: float,
    as_bottom_mm2: float,
    fyd_mpa: float,
    fcd_mpa: float,
    source: str = "unknown",
) -> MemberMomentCapacity:
    cover_mm = 50.0
    d_mm = max(depth_mm - cover_mm, 0.0)

    m_top = rectangular_moment_capacity_knm(
        as_mm2=as_top_mm2,
        b_mm=width_mm,
        d_mm=d_mm,
        fyd_mpa=fyd_mpa,
        fcd_mpa=fcd_mpa,
    )
    m_bot = rectangular_moment_capacity_knm(
        as_mm2=as_bottom_mm2,
        b_mm=width_mm,
        d_mm=d_mm,
        fyd_mpa=fyd_mpa,
        fcd_mpa=fcd_mpa,
    )

    missing = []
    if width_mm <= 0 or depth_mm <= 0:
        missing.append("geometry")
    if as_top_mm2 <= 0:
        missing.append("top rebar")
    if as_bottom_mm2 <= 0:
        missing.append("bottom rebar")

    if missing:
        return MemberMomentCapacity(
            element_id=element_id,
            story=story,
            member_type="BEAM",
            source=source,
            m_pos_knm=m_bot if m_bot > 0 else None,
            m_neg_knm=m_top if m_top > 0 else None,
            m_governing_knm=max(m_top, m_bot) if max(m_top, m_bot) > 0 else None,
            status="NO_DATA",
            evaluation_level="NO_DATA",
            note="missing: " + ", ".join(missing),
        )

    src = str(source or "").lower()
    if "provided" in src or "user" in src or "final" in src:
        level = "DESIGN_LEVEL"
        status = "OK"
        note = "provided beam rebar capacity"
    elif "etabs" in src or "summary" in src:
        level = "ETABS_DESIGN_RESULT"
        status = "WARNING"
        note = "ETABS beam design demand used, not final provided rebar"
    else:
        level = "APPROXIMATE"
        status = "WARNING"
        note = "beam capacity source is not final provided rebar"

    return MemberMomentCapacity(
        element_id=element_id,
        story=story,
        member_type="BEAM",
        source=source,
        m_pos_knm=m_bot,
        m_neg_knm=m_top,
        m_governing_knm=max(m_top, m_bot),
        status=status,
        evaluation_level=level,
        note=note,
    )


def approximate_column_moment_capacity(
    *,
    element_id: str,
    story: str,
    width_mm: float,
    depth_mm: float,
    as_total_mm2: float,
    fyd_mpa: float,
    fcd_mpa: float,
    source: str = "unknown",
) -> MemberMomentCapacity:
    """
    Approximate column flexural capacity.

    This is not a full PMM interaction solver.
    It uses half of total longitudinal rebar as tension steel.
    Full SCWB should later use PMM interaction with axial load.
    """
    if width_mm <= 0 or depth_mm <= 0 or as_total_mm2 <= 0:
        return MemberMomentCapacity(
            element_id=element_id,
            story=story,
            member_type="COLUMN",
            source=source,
            status="NO_DATA",
            evaluation_level="NO_DATA",
            note="missing column geometry or longitudinal rebar",
        )

    as_tension = as_total_mm2 / 2.0
    d_mm = max(depth_mm - 50.0, 0.0)
    b_eff = min(width_mm, depth_mm)

    mrd = rectangular_moment_capacity_knm(
        as_mm2=as_tension,
        b_mm=b_eff,
        d_mm=d_mm,
        fyd_mpa=fyd_mpa,
        fcd_mpa=fcd_mpa,
    )

    src = str(source or "").lower()
    if "provided" in src or "user" in src or "final" in src:
        note = "provided column rebar used with approximate Mrd; PMM solver pending"
    elif "etabs" in src or "summary" in src:
        note = "ETABS/design-summary column rebar used with approximate Mrd; PMM solver pending"
    else:
        note = "column Mrd approximate; PMM solver pending"

    return MemberMomentCapacity(
        element_id=element_id,
        story=story,
        member_type="COLUMN",
        source=source,
        m_pos_knm=mrd,
        m_neg_knm=mrd,
        m_governing_knm=mrd,
        status="WARNING",
        evaluation_level="APPROXIMATE",
        note=note,
    )


def compute_scwb_joint_result(
    *,
    joint_id: str,
    story: str,
    direction: str,
    columns: list[str],
    beams: list[str],
    column_capacities: list[MemberMomentCapacity],
    beam_capacities: list[MemberMomentCapacity],
    factor: float = 1.20,
) -> ScwbJointResult:
    valid_cols = [c for c in column_capacities if c.m_governing_knm and c.m_governing_knm > 0]
    valid_beams = [b for b in beam_capacities if b.m_governing_knm and b.m_governing_knm > 0]

    sum_mrc = sum(c.m_governing_knm or 0.0 for c in valid_cols)
    sum_mrb = sum(b.m_governing_knm or 0.0 for b in valid_beams)
    required = factor * sum_mrb

    ratio = sum_mrc / required if required > 0 else 0.0

    notes = []

    if not valid_cols:
        notes.append("no valid column moment capacity")
    if not valid_beams:
        notes.append("no valid beam moment capacity")

    all_levels = {c.evaluation_level for c in valid_cols} | {b.evaluation_level for b in valid_beams}

    if not valid_cols or not valid_beams:
        status = "NO_DATA"
        level = "NO_DATA"
    elif all_levels == {"DESIGN_LEVEL"}:
        level = "DESIGN_LEVEL"
        status = "OK" if ratio >= 1.0 else "FAIL"
    else:
        level = "APPROXIMATE"
        status = "WARNING"
        notes.append("SCWB ratio computed with non-final or approximate capacities")

    if ratio < 1.0 and status == "WARNING":
        notes.append("approximate ratio below 1.0; verify with final rebar and PMM")
    elif ratio >= 1.0 and status == "WARNING":
        notes.append("approximate ratio satisfies 1.20 factor, but final design data required")

    return ScwbJointResult(
        joint_id=joint_id,
        story=story,
        direction=direction,
        columns=columns,
        beams=beams,
        sum_mrc_knm=sum_mrc,
        sum_mrb_knm=sum_mrb,
        required_mrc_knm=required,
        ratio=ratio,
        status=status,
        evaluation_level=level,
        note="; ".join(notes) if notes else "SCWB OK",
    )
