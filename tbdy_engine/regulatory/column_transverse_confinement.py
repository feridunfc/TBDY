"""Canonical Column transverse/confinement/final-cage authority for COLUMN-R1.

The module deliberately keeps four things separate:

* TBDY high-ductility confinement;
* TBDY limited-ductility confinement;
* TS500 general column transverse requirements; and
* final cage shear resistance fed by the already-canonical P7 ``Ve`` result.

``Ash`` is confinement reinforcement area and is never renamed to ``Asw``.
``Asw`` is accepted only through an explicit shear-direction mapping proof.  If
that mapping is not proven, final ``Vr`` stays BLOCKED instead of inventing a
rectangular-column interpretation.

The regulatory source identities are the existing runtime canonical identities
(``TBDY2018_AFAD`` and ``TS500_2000_TSE``); this module does not create a second
identity/fingerprint for either official source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import math
from typing import Sequence

from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.design.columns.column_longitudinal_selection import (
    CanonicalEngineSelectedRebar,
    ENGINE_SELECTED_REBAR_AUTHORITY,
)
from tbdy_engine.integration.etabs_design_lineage import DesignLineageQualification
from tbdy_engine.regulatory.sources.fnd_col_1_longitudinal import (
    SOURCE_DATA,
    TBDY_SOURCE_ID,
    TS500_SOURCE_ID,
)


TRANSVERSE_CONFINEMENT_AUTHORITY = "COLUMN_R1_CANONICAL_TRANSVERSE_CONFINEMENT"
TRANSVERSE_CAUSAL_BINDING_AUTHORITY = "COLUMN_R1_TRANSVERSE_CAUSAL_BINDING"

TBDY_2018_SOURCE_FINGERPRINT = SOURCE_DATA[TBDY_SOURCE_ID][4].removeprefix("sha256:")
TS500_SOURCE_FINGERPRINT = SOURCE_DATA[TS500_SOURCE_ID][4].removeprefix("sha256:")


def _claim_ref(source_id: str, locator: str, statement: str) -> str:
    payload = f"{source_id}|{locator}|{statement}".encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


_CLAIM_DATA = {
    "COL_HD_CONFINEMENT_REGION": (
        TBDY_SOURCE_ID,
        "7.3.4.1",
        "High-ductility column confinement-region length is governed by ln/6, 1.5 largest section dimension and 500 mm; cantilever-column base uses 2 times the largest section dimension.",
    ),
    "COL_HD_CONFINEMENT_REINFORCEMENT": (
        TBDY_SOURCE_ID,
        "7.3.4.1 / Eq.7.1",
        "High-ductility rectangular-column confinement uses the documented diameter, spacing, tie-leg and directional Ash requirements, including the 2/3 low-axial-force branch.",
    ),
    "COL_MIDDLE_REINFORCEMENT": (
        TBDY_SOURCE_ID,
        "7.3.4.2",
        "Column middle-region transverse reinforcement uses the documented diameter, spacing and tie-leg requirements.",
    ),
    "COL_LD_CONFINEMENT": (
        TBDY_SOURCE_ID,
        "7.7.4",
        "Limited-ductility column confinement uses the same confinement-region length basis, spacing no greater than bmin/3, 8 times the longitudinal bar diameter and 150 mm, and at least one-half the Eq.7.1/Eq.7.2 confinement quantity.",
    ),
    "COL_SPECIAL_TIE_DETAILING": (
        TBDY_SOURCE_ID,
        "7.2.8",
        "Special seismic hoops and cross-ties satisfy the documented hook, bend, tail and longitudinal-bar enclosure detailing.",
    ),
    "COL_TS500_GENERAL_TRANSVERSE": (
        TS500_SOURCE_ID,
        "7.4.1",
        "TS500 column transverse reinforcement uses stirrup diameter not less than one-third the largest longitudinal diameter, spacing not greater than 12 times the smallest longitudinal diameter nor 200 mm, and restrained longitudinal-bar spacing not greater than 300 mm.",
    ),
    "COL_TS500_SHEAR_CAGE": (
        TS500_SOURCE_ID,
        "8.1.2 / Eq.8.3-Eq.8.5",
        "When a qualified column shear geometry/direction mapping and qualified concrete contribution Vc are supplied, Vr is the sum of Vc and Vw and Vw is Asw/s times fywd times d.",
    ),
}
CLAIM_REFS = {
    claim_id: _claim_ref(source_id, locator, statement)
    for claim_id, (source_id, locator, statement) in _CLAIM_DATA.items()
}


class ColumnDuctility(StrEnum):
    HIGH = "HIGH"
    LIMITED = "LIMITED"


class ColumnTransverseConfinementError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnTransverseConfinementError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnTransverseConfinementError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ColumnTransverseConfinementError(f"{label} must be finite and > 0")
    return result


def _nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnTransverseConfinementError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ColumnTransverseConfinementError(f"{label} must be finite and >= 0")
    return result


def _optional_positive(value: object | None, label: str) -> float | None:
    return None if value is None else _positive(value, label)


def _refs(values: Sequence[str], label: str = "source_ref") -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{label} must be a sequence")
    return tuple(dict.fromkeys(_text(item, label) for item in values))


def _source_evidence(claim_id: str) -> tuple[str, ...]:
    source_id, locator, _statement = _CLAIM_DATA[claim_id]
    fingerprint = (
        TBDY_2018_SOURCE_FINGERPRINT
        if source_id == TBDY_SOURCE_ID
        else TS500_SOURCE_FINGERPRINT
    )
    return (
        f"regulatory-source:{source_id}:sha256:{fingerprint}",
        f"regulatory-anchor:{source_id}:{locator}",
        CLAIM_REFS[claim_id],
    )


@dataclass(frozen=True, slots=True)
class SpecialTieDetailingFacts:
    hoop_both_ends_135_hooks: bool | None
    min_inner_bend_diameter_mm: float | None
    min_hook_tail_length_mm: float | None
    hoops_enclose_longitudinal_bars: bool | None
    hooks_close_around_longitudinal_bar: bool | None
    cross_tie_present: bool | None
    cross_tie_diameter_mm: float | None
    cross_tie_spacing_mm: float | None
    cross_tie_ends_wrap_longitudinal_and_hoop: bool | None
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


@dataclass(frozen=True, slots=True)
class TransverseDirectionFacts:
    """Direction-specific physical transverse facts.

    ``provided_ash_mm2`` is confinement Ash. ``provided_asw_mm2`` is the total
    shear-reinforcement area used by TS500 Vw. They are intentionally distinct.
    """

    direction: str
    confined_core_width_bk_mm: float
    provided_ash_mm2: float | None
    horizontal_leg_spacing_mm: float | None
    source_refs: tuple[str, ...] = ()
    provided_asw_mm2: float | None = None
    effective_depth_mm: float | None = None
    shear_mapping_proven: bool | None = None
    qualified_vc_kn: float | None = None
    p7_ve_kn: float | None = None

    def __post_init__(self) -> None:
        _text(self.direction, "direction")
        _positive(self.confined_core_width_bk_mm, "confined_core_width_bk_mm")
        if self.provided_ash_mm2 is not None:
            _nonnegative(self.provided_ash_mm2, "provided_ash_mm2")
        if self.horizontal_leg_spacing_mm is not None:
            _positive(self.horizontal_leg_spacing_mm, "horizontal_leg_spacing_mm")
        if self.provided_asw_mm2 is not None:
            _nonnegative(self.provided_asw_mm2, "provided_asw_mm2")
        _optional_positive(self.effective_depth_mm, "effective_depth_mm")
        if self.shear_mapping_proven is not None and type(self.shear_mapping_proven) is not bool:
            raise TypeError("shear_mapping_proven must be bool or None")
        if self.qualified_vc_kn is not None:
            _nonnegative(self.qualified_vc_kn, "qualified_vc_kn")
        if self.p7_ve_kn is not None:
            _nonnegative(self.p7_ve_kn, "p7_ve_kn")
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


@dataclass(frozen=True, slots=True)
class ColumnTransverseConfinementInput:
    component_id: str
    story: str
    section: str
    high_ductility_applies: bool | None
    cantilever_column: bool | None
    clear_height_mm: float
    width_mm: float
    depth_mm: float
    gross_area_ac_mm2: float
    confined_core_area_ack_mm2: float
    fck_mpa: float
    fywk_mpa: float
    axial_design_force_nd_n: float
    transverse_diameter_mm: float | None
    confinement_spacing_mm: float | None
    middle_spacing_mm: float | None
    provided_confinement_region_length_mm: float | None
    directions: tuple[TransverseDirectionFacts, ...]
    arrangement: SpecialTieDetailingFacts | None
    source_refs: tuple[str, ...]
    limited_ductility_applies: bool | None = None
    ts500_general_applies: bool | None = True
    restrained_longitudinal_bar_spacing_mm: float | None = None
    fywd_mpa: float | None = None
    shear_spacing_mm: float | None = None
    model_fingerprint: str | None = None
    evidence_epoch_id: str | None = None
    design_result_ref: str | None = None

    def __post_init__(self) -> None:
        _text(self.component_id, "component_id")
        _text(self.story, "story")
        _text(self.section, "section")
        for name in (
            "high_ductility_applies",
            "limited_ductility_applies",
            "ts500_general_applies",
            "cantilever_column",
        ):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise TypeError(f"{name} must be bool or None")
        if self.high_ductility_applies is True and self.limited_ductility_applies is True:
            raise ColumnTransverseConfinementError("HIGH and LIMITED ductility cannot both apply")
        for name in (
            "clear_height_mm", "width_mm", "depth_mm", "gross_area_ac_mm2",
            "confined_core_area_ack_mm2", "fck_mpa", "fywk_mpa",
        ):
            _positive(getattr(self, name), name)
        _nonnegative(self.axial_design_force_nd_n, "axial_design_force_nd_n")
        for name in (
            "transverse_diameter_mm", "confinement_spacing_mm", "middle_spacing_mm",
            "provided_confinement_region_length_mm", "restrained_longitudinal_bar_spacing_mm",
            "fywd_mpa", "shear_spacing_mm",
        ):
            _optional_positive(getattr(self, name), name)
        if self.confined_core_area_ack_mm2 >= self.gross_area_ac_mm2:
            raise ColumnTransverseConfinementError("Ack must be smaller than Ac")
        if not self.directions or len({item.direction for item in self.directions}) != len(self.directions):
            raise ColumnTransverseConfinementError("directions must be a nonempty unique population")
        if any(not isinstance(item, TransverseDirectionFacts) for item in self.directions):
            raise TypeError("directions must contain TransverseDirectionFacts")
        if self.arrangement is not None and not isinstance(self.arrangement, SpecialTieDetailingFacts):
            raise TypeError("arrangement must be SpecialTieDetailingFacts or None")
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


@dataclass(frozen=True, slots=True)
class ColumnTransverseConfinementResult:
    component_id: str
    applicable: bool | None
    required_confinement_region_length_mm: float | None
    confinement_spacing_limit_mm: float | None
    middle_spacing_limit_mm: float | None
    longitudinal_bar_diameter_mm: float | None
    checks: tuple[CheckResult, ...]
    blockers: tuple[str, ...]
    source_refs: tuple[str, ...]
    ductility: ColumnDuctility | None = None
    shear_vr_by_direction_kn: tuple[tuple[str, float], ...] = ()
    authority: str = TRANSVERSE_CONFINEMENT_AUTHORITY

    @property
    def complete(self) -> bool:
        return not self.blockers and all(
            item.status not in {CheckStatus.BLOCKED, CheckStatus.NO_DATA}
            for item in self.checks
        )

    @property
    def failed(self) -> bool:
        return any(item.status is CheckStatus.FAIL for item in self.checks)


def _check(
    request: ColumnTransverseConfinementInput,
    *,
    check_id: str,
    status: CheckStatus,
    message: str,
    claim_id: str,
    value=None,
    limit=None,
    ratio=None,
    ratio_type=None,
    pass_rule=None,
    unit=None,
    extra_refs: Sequence[str] = (),
) -> CheckResult:
    evidence = tuple(dict.fromkeys((
        *request.source_refs,
        *extra_refs,
        *_source_evidence(claim_id),
    )))
    source_id, locator, _statement = _CLAIM_DATA[claim_id]
    return CheckResult(
        check_id=check_id,
        component=request.component_id,
        component_type="COLUMN",
        story=request.story,
        section=request.section,
        status=status,
        value=value,
        limit=limit,
        ratio=ratio,
        ratio_type=ratio_type,
        pass_rule=pass_rule,
        unit=unit,
        evaluation_level=(
            EvaluationLevel.NO_DATA
            if status in {CheckStatus.BLOCKED, CheckStatus.NO_DATA, CheckStatus.OUT_OF_SCOPE}
            else EvaluationLevel.DESIGN_LEVEL
        ),
        evidence=evidence,
        messages=(message,),
        code_ref=f"{source_id} {locator}",
    )


def _selected_longitudinal_diameter(
    selected_rebar: CanonicalEngineSelectedRebar | None,
    component_id: str,
) -> float | None:
    if selected_rebar is None:
        return None
    if not isinstance(selected_rebar, CanonicalEngineSelectedRebar):
        raise TypeError("selected_rebar must be CanonicalEngineSelectedRebar or None")
    if selected_rebar.authority != ENGINE_SELECTED_REBAR_AUTHORITY:
        raise ColumnTransverseConfinementError(
            "selected longitudinal rebar lacks canonical ENGINE_SELECTED_REBAR authority"
        )
    if selected_rebar.component_id != component_id:
        raise ColumnTransverseConfinementError("selected longitudinal rebar component identity mismatch")
    if selected_rebar.selected_candidate.candidate_id != selected_rebar.candidate_id:
        raise ColumnTransverseConfinementError("selected longitudinal rebar candidate identity mismatch")
    return _positive(selected_rebar.selected_candidate.bar_diameter_mm, "selected longitudinal bar diameter")


def _confinement_region(
    request: ColumnTransverseConfinementInput,
    *,
    claim_id: str,
    check_prefix: str,
    checks: list[CheckResult],
    blockers: list[str],
) -> float | None:
    if request.cantilever_column is None:
        blocker = "CANTILEVER_COLUMN_STATUS_NOT_PROVEN"
        blockers.append(blocker)
        checks.append(_check(
            request,
            check_id=f"{check_prefix}_REGION_LENGTH",
            status=CheckStatus.BLOCKED,
            message=blocker,
            claim_id=claim_id,
        ))
        return None
    largest = max(request.width_mm, request.depth_mm)
    required = (
        2.0 * largest
        if request.cantilever_column
        else max(request.clear_height_mm / 6.0, 1.5 * largest, 500.0)
    )
    actual = request.provided_confinement_region_length_mm
    if actual is None:
        blocker = "CONFINEMENT_REGION_LENGTH_NOT_AVAILABLE"
        blockers.append(blocker)
        checks.append(_check(
            request,
            check_id=f"{check_prefix}_REGION_LENGTH",
            status=CheckStatus.BLOCKED,
            message=blocker,
            claim_id=claim_id,
            limit=required,
            unit="mm",
        ))
    else:
        ok = actual + 1e-9 >= required
        checks.append(_check(
            request,
            check_id=f"{check_prefix}_REGION_LENGTH",
            status=CheckStatus.OK if ok else CheckStatus.FAIL,
            value=actual,
            limit=required,
            ratio=actual / required,
            ratio_type="value_over_minimum",
            pass_rule="value >= minimum",
            unit="mm",
            message="Confinement-region length satisfies the applicable TBDY minimum." if ok else "Confinement-region length is below the applicable TBDY minimum.",
            claim_id=claim_id,
        ))
    return required


def _ash_checks(
    request: ColumnTransverseConfinementInput,
    *,
    quantity_factor: float,
    claim_id: str,
    check_prefix: str,
    checks: list[CheckResult],
    blockers: list[str],
) -> None:
    for direction in request.directions:
        if request.confinement_spacing_mm is None:
            blocker = f"CONFINEMENT_SPACING_REQUIRED_FOR_ASH:{direction.direction}"
            blockers.append(blocker)
            checks.append(_check(
                request,
                check_id=f"{check_prefix}_ASH_{direction.direction}",
                status=CheckStatus.BLOCKED,
                message=blocker,
                claim_id=claim_id,
                extra_refs=direction.source_refs,
            ))
            continue
        s = request.confinement_spacing_mm
        req_a = (
            0.30 * s * direction.confined_core_width_bk_mm
            * (request.gross_area_ac_mm2 / request.confined_core_area_ack_mm2 - 1.0)
            * request.fck_mpa / request.fywk_mpa
        )
        req_b = (
            0.075 * s * direction.confined_core_width_bk_mm
            * request.fck_mpa / request.fywk_mpa
        )
        required = quantity_factor * max(req_a, req_b)
        actual = direction.provided_ash_mm2
        if actual is None:
            blocker = f"PROVIDED_ASH_NOT_AVAILABLE:{direction.direction}"
            blockers.append(blocker)
            checks.append(_check(
                request,
                check_id=f"{check_prefix}_ASH_{direction.direction}",
                status=CheckStatus.BLOCKED,
                limit=required,
                unit="mm2",
                message=blocker,
                claim_id=claim_id,
                extra_refs=direction.source_refs,
            ))
        else:
            ok = actual + 1e-9 >= required
            checks.append(_check(
                request,
                check_id=f"{check_prefix}_ASH_{direction.direction}",
                status=CheckStatus.OK if ok else CheckStatus.FAIL,
                value=actual,
                limit=required,
                ratio=actual / required if required > 0 else None,
                ratio_type="actual_over_required" if required > 0 else None,
                pass_rule="provided Ash >= required Ash",
                unit="mm2",
                message="Provided Ash satisfies the applicable confinement quantity." if ok else "Provided Ash is below the applicable confinement quantity.",
                claim_id=claim_id,
                extra_refs=direction.source_refs,
            ))


def _tie_leg_checks(
    request: ColumnTransverseConfinementInput,
    *,
    claim_id: str,
    check_prefix: str,
    checks: list[CheckResult],
    blockers: list[str],
) -> None:
    phi_w = request.transverse_diameter_mm
    for direction in request.directions:
        if phi_w is None or direction.horizontal_leg_spacing_mm is None:
            blocker = f"TIE_LEG_GEOMETRY_NOT_AVAILABLE:{direction.direction}"
            blockers.append(blocker)
            checks.append(_check(
                request,
                check_id=f"{check_prefix}_TIE_LEG_SPACING_{direction.direction}",
                status=CheckStatus.BLOCKED,
                message=blocker,
                claim_id=claim_id,
                extra_refs=direction.source_refs,
            ))
            continue
        limit = 25.0 * phi_w
        actual = direction.horizontal_leg_spacing_mm
        ok = actual <= limit + 1e-9
        checks.append(_check(
            request,
            check_id=f"{check_prefix}_TIE_LEG_SPACING_{direction.direction}",
            status=CheckStatus.OK if ok else CheckStatus.FAIL,
            value=actual,
            limit=limit,
            ratio=actual / limit,
            ratio_type="value_over_maximum",
            pass_rule="value <= 25 phi_transverse",
            unit="mm",
            message="Tie-leg spacing satisfies the applicable TBDY maximum." if ok else "Tie-leg spacing exceeds the applicable TBDY maximum.",
            claim_id=claim_id,
            extra_refs=direction.source_refs,
        ))


def _special_tie_check(
    request: ColumnTransverseConfinementInput,
    *,
    checks: list[CheckResult],
    blockers: list[str],
) -> None:
    arrangement = request.arrangement
    phi_w = request.transverse_diameter_mm
    claim_id = "COL_SPECIAL_TIE_DETAILING"
    if arrangement is None or phi_w is None:
        blocker = "SPECIAL_TIE_DETAILING_FACTS_NOT_AVAILABLE"
        blockers.append(blocker)
        checks.append(_check(
            request,
            check_id="COL_SPECIAL_TIE_DETAILING",
            status=CheckStatus.BLOCKED,
            message=blocker,
            claim_id=claim_id,
        ))
        return
    required_bend = 5.0 * phi_w
    required_tail = max(6.0 * phi_w, 80.0)
    values = (
        arrangement.hoop_both_ends_135_hooks,
        arrangement.hoops_enclose_longitudinal_bars,
        arrangement.hooks_close_around_longitudinal_bar,
        arrangement.min_inner_bend_diameter_mm,
        arrangement.min_hook_tail_length_mm,
    )
    missing = any(value is None for value in values)
    if arrangement.cross_tie_present is True:
        missing = missing or any(value is None for value in (
            arrangement.cross_tie_diameter_mm,
            arrangement.cross_tie_spacing_mm,
            arrangement.cross_tie_ends_wrap_longitudinal_and_hoop,
            request.confinement_spacing_mm,
        ))
    if missing:
        blocker = "SPECIAL_TIE_DETAILING_FACTS_INCOMPLETE"
        blockers.append(blocker)
        checks.append(_check(
            request,
            check_id="COL_SPECIAL_TIE_DETAILING",
            status=CheckStatus.BLOCKED,
            message=blocker,
            claim_id=claim_id,
            extra_refs=arrangement.source_refs,
        ))
        return
    conditions = [
        arrangement.hoop_both_ends_135_hooks is True,
        arrangement.hoops_enclose_longitudinal_bars is True,
        arrangement.hooks_close_around_longitudinal_bar is True,
        float(arrangement.min_inner_bend_diameter_mm) + 1e-9 >= required_bend,
        float(arrangement.min_hook_tail_length_mm) + 1e-9 >= required_tail,
    ]
    if arrangement.cross_tie_present is True:
        conditions.extend((
            math.isclose(float(arrangement.cross_tie_diameter_mm), phi_w, rel_tol=0.0, abs_tol=1e-9),
            math.isclose(float(arrangement.cross_tie_spacing_mm), float(request.confinement_spacing_mm), rel_tol=0.0, abs_tol=1e-9),
            arrangement.cross_tie_ends_wrap_longitudinal_and_hoop is True,
        ))
    ok = all(conditions)
    checks.append(_check(
        request,
        check_id="COL_SPECIAL_TIE_DETAILING",
        status=CheckStatus.OK if ok else CheckStatus.FAIL,
        value=ok,
        limit=True,
        ratio_type="boolean",
        pass_rule="all documented special tie facts true",
        message="Special tie detailing satisfies TBDY 7.2.8." if ok else "Special tie detailing violates TBDY 7.2.8.",
        claim_id=claim_id,
        extra_refs=arrangement.source_refs,
    ))


def _high_ductility_checks(
    request: ColumnTransverseConfinementInput,
    *,
    phi_l: float | None,
    checks: list[CheckResult],
    blockers: list[str],
) -> tuple[float | None, float | None, float | None]:
    region = _confinement_region(
        request,
        claim_id="COL_HD_CONFINEMENT_REGION",
        check_prefix="COL_HD_CONFINEMENT",
        checks=checks,
        blockers=blockers,
    )
    min_dim = min(request.width_mm, request.depth_mm)
    phi_w = request.transverse_diameter_mm
    if phi_w is None:
        blocker = "TRANSVERSE_DIAMETER_NOT_AVAILABLE"
        blockers.append(blocker)
        checks.append(_check(request, check_id="COL_HD_TRANSVERSE_MIN_DIAMETER", status=CheckStatus.BLOCKED, limit=8.0, unit="mm", message=blocker, claim_id="COL_HD_CONFINEMENT_REINFORCEMENT"))
    else:
        ok = phi_w + 1e-9 >= 8.0
        checks.append(_check(request, check_id="COL_HD_TRANSVERSE_MIN_DIAMETER", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=phi_w, limit=8.0, ratio=phi_w / 8.0, ratio_type="value_over_minimum", pass_rule="value >= minimum", unit="mm", message="Transverse diameter satisfies 8 mm minimum." if ok else "Transverse diameter is below 8 mm.", claim_id="COL_HD_CONFINEMENT_REINFORCEMENT"))

    spacing_limit = None
    if phi_l is None:
        blocker = "ENGINE_SELECTED_REBAR_REQUIRED_FOR_HD_SPACING"
        blockers.append(blocker)
        checks.append(_check(request, check_id="COL_HD_CONFINEMENT_SPACING", status=CheckStatus.BLOCKED, message=blocker, claim_id="COL_HD_CONFINEMENT_REINFORCEMENT"))
    else:
        spacing_limit = min(min_dim / 3.0, 6.0 * phi_l, 150.0)
        spacing = request.confinement_spacing_mm
        if spacing is None:
            blocker = "CONFINEMENT_SPACING_NOT_AVAILABLE"
            blockers.append(blocker)
            checks.append(_check(request, check_id="COL_HD_CONFINEMENT_SPACING", status=CheckStatus.BLOCKED, limit=spacing_limit, unit="mm", message=blocker, claim_id="COL_HD_CONFINEMENT_REINFORCEMENT"))
        else:
            ok = 50.0 - 1e-9 <= spacing <= spacing_limit + 1e-9
            checks.append(_check(request, check_id="COL_HD_CONFINEMENT_SPACING", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=spacing, limit={"min_mm": 50.0, "max_mm": spacing_limit}, pass_rule="50 mm <= spacing <= maximum", unit="mm", message="High-ductility confinement spacing satisfies TBDY." if ok else "High-ductility confinement spacing violates TBDY bounds.", claim_id="COL_HD_CONFINEMENT_REINFORCEMENT"))

    low_axial = request.axial_design_force_nd_n <= 0.20 * request.gross_area_ac_mm2 * request.fck_mpa + 1e-9
    _ash_checks(request, quantity_factor=(2.0 / 3.0 if low_axial else 1.0), claim_id="COL_HD_CONFINEMENT_REINFORCEMENT", check_prefix="COL_HD_CONFINEMENT", checks=checks, blockers=blockers)
    _tie_leg_checks(request, claim_id="COL_HD_CONFINEMENT_REINFORCEMENT", check_prefix="COL_HD", checks=checks, blockers=blockers)

    middle_limit = min(min_dim / 2.0, 200.0)
    if request.middle_spacing_mm is None:
        blocker = "MIDDLE_SPACING_NOT_AVAILABLE"
        blockers.append(blocker)
        checks.append(_check(request, check_id="COL_HD_MIDDLE_SPACING", status=CheckStatus.BLOCKED, limit=middle_limit, unit="mm", message=blocker, claim_id="COL_MIDDLE_REINFORCEMENT"))
    else:
        actual = request.middle_spacing_mm
        ok = actual <= middle_limit + 1e-9
        checks.append(_check(request, check_id="COL_HD_MIDDLE_SPACING", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=actual, limit=middle_limit, ratio=actual / middle_limit, ratio_type="value_over_maximum", pass_rule="value <= maximum", unit="mm", message="Middle-region spacing satisfies TBDY." if ok else "Middle-region spacing exceeds TBDY maximum.", claim_id="COL_MIDDLE_REINFORCEMENT"))
    return region, spacing_limit, middle_limit


def _limited_ductility_checks(
    request: ColumnTransverseConfinementInput,
    *,
    phi_l: float | None,
    checks: list[CheckResult],
    blockers: list[str],
) -> tuple[float | None, float | None, float | None]:
    region = _confinement_region(
        request,
        claim_id="COL_LD_CONFINEMENT",
        check_prefix="COL_LD_CONFINEMENT",
        checks=checks,
        blockers=blockers,
    )
    min_dim = min(request.width_mm, request.depth_mm)
    spacing_limit = None
    if phi_l is None:
        blocker = "ENGINE_SELECTED_REBAR_REQUIRED_FOR_LD_SPACING"
        blockers.append(blocker)
        checks.append(_check(request, check_id="COL_LD_CONFINEMENT_SPACING", status=CheckStatus.BLOCKED, message=blocker, claim_id="COL_LD_CONFINEMENT"))
    else:
        spacing_limit = min(min_dim / 3.0, 8.0 * phi_l, 150.0)
        spacing = request.confinement_spacing_mm
        if spacing is None:
            blocker = "CONFINEMENT_SPACING_NOT_AVAILABLE"
            blockers.append(blocker)
            checks.append(_check(request, check_id="COL_LD_CONFINEMENT_SPACING", status=CheckStatus.BLOCKED, limit=spacing_limit, unit="mm", message=blocker, claim_id="COL_LD_CONFINEMENT"))
        else:
            ok = spacing <= spacing_limit + 1e-9
            checks.append(_check(request, check_id="COL_LD_CONFINEMENT_SPACING", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=spacing, limit=spacing_limit, ratio=spacing / spacing_limit, ratio_type="value_over_maximum", pass_rule="spacing <= maximum", unit="mm", message="Limited-ductility confinement spacing satisfies TBDY." if ok else "Limited-ductility confinement spacing exceeds TBDY maximum.", claim_id="COL_LD_CONFINEMENT"))

    # TBDY 7.7.4 states one-half of the Eq.7.1/Eq.7.2 quantities.  Do not
    # import the high-ductility 50 mm lower-spacing bound into this branch.
    _ash_checks(request, quantity_factor=0.5, claim_id="COL_LD_CONFINEMENT", check_prefix="COL_LD_CONFINEMENT", checks=checks, blockers=blockers)

    middle_limit = min(min_dim / 2.0, 200.0)
    phi_w = request.transverse_diameter_mm
    if phi_w is None:
        blocker = "TRANSVERSE_DIAMETER_NOT_AVAILABLE_FOR_LD_MIDDLE_REGION"
        blockers.append(blocker)
        checks.append(_check(request, check_id="COL_LD_MIDDLE_MIN_DIAMETER", status=CheckStatus.BLOCKED, limit=8.0, unit="mm", message=blocker, claim_id="COL_MIDDLE_REINFORCEMENT"))
    else:
        ok = phi_w + 1e-9 >= 8.0
        checks.append(_check(request, check_id="COL_LD_MIDDLE_MIN_DIAMETER", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=phi_w, limit=8.0, ratio=phi_w / 8.0, ratio_type="value_over_minimum", pass_rule="value >= minimum", unit="mm", message="Limited-ductility middle-region transverse diameter satisfies inherited TBDY 7.3.4.2." if ok else "Limited-ductility middle-region transverse diameter violates inherited TBDY 7.3.4.2.", claim_id="COL_MIDDLE_REINFORCEMENT"))
    if request.middle_spacing_mm is None:
        blocker = "MIDDLE_SPACING_NOT_AVAILABLE"
        blockers.append(blocker)
        checks.append(_check(request, check_id="COL_LD_MIDDLE_SPACING", status=CheckStatus.BLOCKED, limit=middle_limit, unit="mm", message=blocker, claim_id="COL_MIDDLE_REINFORCEMENT"))
    else:
        actual = request.middle_spacing_mm
        ok = actual <= middle_limit + 1e-9
        checks.append(_check(request, check_id="COL_LD_MIDDLE_SPACING", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=actual, limit=middle_limit, ratio=actual / middle_limit, ratio_type="value_over_maximum", pass_rule="value <= maximum", unit="mm", message="Limited-ductility middle-region spacing satisfies inherited TBDY 7.3.4.2." if ok else "Limited-ductility middle-region spacing exceeds inherited TBDY 7.3.4.2 maximum.", claim_id="COL_MIDDLE_REINFORCEMENT"))
    _tie_leg_checks(request, claim_id="COL_MIDDLE_REINFORCEMENT", check_prefix="COL_LD_MIDDLE", checks=checks, blockers=blockers)
    return region, spacing_limit, middle_limit


def _ts500_general_checks(
    request: ColumnTransverseConfinementInput,
    *,
    phi_l: float | None,
    checks: list[CheckResult],
    blockers: list[str],
) -> None:
    claim_id = "COL_TS500_GENERAL_TRANSVERSE"
    if request.ts500_general_applies is None:
        blocker = "TS500_GENERAL_TRANSVERSE_APPLICABILITY_NOT_PROVEN"
        blockers.append(blocker)
        checks.append(_check(request, check_id="COL_TS500_GENERAL_APPLICABILITY", status=CheckStatus.BLOCKED, message=blocker, claim_id=claim_id))
        return
    if request.ts500_general_applies is False:
        checks.append(_check(request, check_id="COL_TS500_GENERAL_APPLICABILITY", status=CheckStatus.OUT_OF_SCOPE, value=False, limit=True, ratio_type="boolean", pass_rule="applicability proven false", message="TS500 general column transverse requirements are proven not applicable.", claim_id=claim_id))
        return
    if phi_l is None:
        blocker = "ENGINE_SELECTED_REBAR_REQUIRED_FOR_TS500_TRANSVERSE"
        blockers.append(blocker)
        checks.append(_check(request, check_id="COL_TS500_TRANSVERSE_DIAMETER", status=CheckStatus.BLOCKED, message=blocker, claim_id=claim_id))
        checks.append(_check(request, check_id="COL_TS500_TRANSVERSE_SPACING", status=CheckStatus.BLOCKED, message=blocker, claim_id=claim_id))
    else:
        phi_w = request.transverse_diameter_mm
        diameter_limit = phi_l / 3.0
        if phi_w is None:
            blocker = "TRANSVERSE_DIAMETER_NOT_AVAILABLE"
            blockers.append(blocker)
            checks.append(_check(request, check_id="COL_TS500_TRANSVERSE_DIAMETER", status=CheckStatus.BLOCKED, limit=diameter_limit, unit="mm", message=blocker, claim_id=claim_id))
        else:
            ok = phi_w + 1e-9 >= diameter_limit
            checks.append(_check(request, check_id="COL_TS500_TRANSVERSE_DIAMETER", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=phi_w, limit=diameter_limit, ratio=phi_w / diameter_limit, ratio_type="value_over_minimum", pass_rule="phi_transverse >= phi_longitudinal_max / 3", unit="mm", message="TS500 transverse diameter requirement is satisfied." if ok else "TS500 transverse diameter requirement is not satisfied.", claim_id=claim_id))
        spacing_limit = min(12.0 * phi_l, 200.0)
        if request.confinement_spacing_mm is None:
            blocker = "TRANSVERSE_SPACING_NOT_AVAILABLE"
            blockers.append(blocker)
            checks.append(_check(request, check_id="COL_TS500_TRANSVERSE_SPACING", status=CheckStatus.BLOCKED, limit=spacing_limit, unit="mm", message=blocker, claim_id=claim_id))
        else:
            spacing = request.confinement_spacing_mm
            ok = spacing <= spacing_limit + 1e-9
            checks.append(_check(request, check_id="COL_TS500_TRANSVERSE_SPACING", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=spacing, limit=spacing_limit, ratio=spacing / spacing_limit, ratio_type="value_over_maximum", pass_rule="spacing <= min(12 phi_longitudinal_min, 200 mm)", unit="mm", message="TS500 transverse spacing requirement is satisfied." if ok else "TS500 transverse spacing requirement is not satisfied.", claim_id=claim_id))
    restrained = request.restrained_longitudinal_bar_spacing_mm
    if restrained is None:
        blocker = "RESTRAINED_LONGITUDINAL_BAR_SPACING_NOT_AVAILABLE"
        blockers.append(blocker)
        checks.append(_check(request, check_id="COL_TS500_RESTRAINED_BAR_SPACING", status=CheckStatus.BLOCKED, limit=300.0, unit="mm", message=blocker, claim_id=claim_id))
    else:
        ok = restrained <= 300.0 + 1e-9
        checks.append(_check(request, check_id="COL_TS500_RESTRAINED_BAR_SPACING", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=restrained, limit=300.0, ratio=restrained / 300.0, ratio_type="value_over_maximum", pass_rule="value <= 300 mm", unit="mm", message="TS500 restrained longitudinal-bar spacing is satisfied." if ok else "TS500 restrained longitudinal-bar spacing exceeds 300 mm.", claim_id=claim_id))


def _final_shear_checks(
    request: ColumnTransverseConfinementInput,
    *,
    checks: list[CheckResult],
    blockers: list[str],
) -> tuple[tuple[str, float], ...]:
    """Use P7 Ve; calculate only cage Vw/Vr after explicit mapping proof."""
    outputs: list[tuple[str, float]] = []
    claim_id = "COL_TS500_SHEAR_CAGE"
    for direction in request.directions:
        check_id = f"COL_FINAL_SHEAR_VR_{direction.direction}"
        if direction.shear_mapping_proven is not True:
            blocker = f"TS500_COLUMN_BW_D_ASW_DIRECTION_MAPPING_NOT_PROVEN:{direction.direction}"
            blockers.append(blocker)
            checks.append(_check(request, check_id=check_id, status=CheckStatus.BLOCKED, message=blocker, claim_id=claim_id, extra_refs=direction.source_refs))
            continue
        missing = []
        for name, value in (
            ("provided_asw_mm2", direction.provided_asw_mm2),
            ("effective_depth_mm", direction.effective_depth_mm),
            ("qualified_vc_kn", direction.qualified_vc_kn),
            ("p7_ve_kn", direction.p7_ve_kn),
            ("fywd_mpa", request.fywd_mpa),
            ("shear_spacing_mm", request.shear_spacing_mm),
        ):
            if value is None:
                missing.append(name)
        if missing:
            blocker = f"FINAL_SHEAR_CAGE_FACTS_INCOMPLETE:{direction.direction}:" + ",".join(missing)
            blockers.append(blocker)
            checks.append(_check(request, check_id=check_id, status=CheckStatus.BLOCKED, message=blocker, claim_id=claim_id, extra_refs=direction.source_refs))
            continue
        asw = float(direction.provided_asw_mm2)
        d_mm = float(direction.effective_depth_mm)
        vc_kn = float(direction.qualified_vc_kn)
        ve_kn = float(direction.p7_ve_kn)
        fywd = float(request.fywd_mpa)
        s_mm = float(request.shear_spacing_mm)
        vw_kn = asw / s_mm * fywd * d_mm / 1000.0
        vr_kn = vc_kn + vw_kn
        outputs.append((direction.direction, vr_kn))
        ok = ve_kn <= vr_kn + 1e-9
        checks.append(_check(
            request,
            check_id=check_id,
            status=CheckStatus.OK if ok else CheckStatus.FAIL,
            value=ve_kn,
            limit=vr_kn,
            ratio=ve_kn / vr_kn if vr_kn > 0 else None,
            ratio_type="demand_over_capacity" if vr_kn > 0 else None,
            pass_rule="P7 Ve <= TS500 Vr = qualified Vc + Asw/s*fywd*d",
            unit="kN",
            message="Final cage shear resistance satisfies Ve <= Vr." if ok else "Final cage shear resistance does not satisfy Ve <= Vr.",
            claim_id=claim_id,
            extra_refs=direction.source_refs,
        ))
    return tuple(outputs)


def evaluate_column_transverse_confinement(
    request: ColumnTransverseConfinementInput,
    *,
    selected_rebar: CanonicalEngineSelectedRebar | None,
) -> ColumnTransverseConfinementResult:
    """Evaluate the complete supported Column transverse universe fail-closed."""
    if not isinstance(request, ColumnTransverseConfinementInput):
        raise TypeError("request must be ColumnTransverseConfinementInput")
    phi_l = _selected_longitudinal_diameter(selected_rebar, request.component_id)
    checks: list[CheckResult] = []
    blockers: list[str] = []

    ductility: ColumnDuctility | None = None
    region = spacing_limit = middle_limit = None
    if request.high_ductility_applies is True:
        ductility = ColumnDuctility.HIGH
        checks.append(_check(request, check_id="COL_LD_CONFINEMENT_APPLICABILITY", status=CheckStatus.OUT_OF_SCOPE, value=False, limit=True, ratio_type="boolean", pass_rule="HIGH branch selected", message="Limited-ductility branch is not applicable because HIGH ductility is proven.", claim_id="COL_LD_CONFINEMENT"))
        region, spacing_limit, middle_limit = _high_ductility_checks(request, phi_l=phi_l, checks=checks, blockers=blockers)
    elif request.high_ductility_applies is False:
        checks.append(_check(request, check_id="COL_HD_CONFINEMENT_APPLICABILITY", status=CheckStatus.OUT_OF_SCOPE, value=False, limit=True, ratio_type="boolean", pass_rule="HIGH applicability proven false", message="High-ductility confinement branch is proven not applicable.", claim_id="COL_HD_CONFINEMENT_REGION"))
        if request.limited_ductility_applies is True:
            ductility = ColumnDuctility.LIMITED
            region, spacing_limit, middle_limit = _limited_ductility_checks(request, phi_l=phi_l, checks=checks, blockers=blockers)
        elif request.limited_ductility_applies is False:
            checks.append(_check(request, check_id="COL_LD_CONFINEMENT_APPLICABILITY", status=CheckStatus.OUT_OF_SCOPE, value=False, limit=True, ratio_type="boolean", pass_rule="LIMITED applicability proven false", message="Limited-ductility confinement branch is proven not applicable.", claim_id="COL_LD_CONFINEMENT"))
        else:
            blocker = "LIMITED_DUCTILITY_APPLICABILITY_NOT_PROVEN"
            blockers.append(blocker)
            checks.append(_check(request, check_id="COL_LD_CONFINEMENT_APPLICABILITY", status=CheckStatus.BLOCKED, message=blocker, claim_id="COL_LD_CONFINEMENT"))
    else:
        blocker = "HIGH_DUCTILITY_APPLICABILITY_NOT_PROVEN"
        blockers.append(blocker)
        checks.append(_check(request, check_id="COL_HD_CONFINEMENT_APPLICABILITY", status=CheckStatus.BLOCKED, message=blocker, claim_id="COL_HD_CONFINEMENT_REGION"))
        if request.limited_ductility_applies is True:
            ductility = ColumnDuctility.LIMITED
            region, spacing_limit, middle_limit = _limited_ductility_checks(request, phi_l=phi_l, checks=checks, blockers=blockers)
        elif request.limited_ductility_applies is None:
            blocker = "LIMITED_DUCTILITY_APPLICABILITY_NOT_PROVEN"
            blockers.append(blocker)
            checks.append(_check(request, check_id="COL_LD_CONFINEMENT_APPLICABILITY", status=CheckStatus.BLOCKED, message=blocker, claim_id="COL_LD_CONFINEMENT"))

    # 7.2.8 and TS500 general column requirements are independent of whether the
    # high-ductility family applies; do not collapse them into HD applicability.
    _special_tie_check(request, checks=checks, blockers=blockers)
    _ts500_general_checks(request, phi_l=phi_l, checks=checks, blockers=blockers)
    shear_vr = _final_shear_checks(request, checks=checks, blockers=blockers)

    applicable: bool | None
    if ductility is not None or request.ts500_general_applies is True:
        applicable = True
    elif request.ts500_general_applies is None or (
        request.high_ductility_applies is None and request.limited_ductility_applies is None
    ):
        applicable = None
    else:
        applicable = False

    source_refs = tuple(dict.fromkeys((
        *request.source_refs,
        *(_source_evidence(claim_id)[0] for claim_id in CLAIM_REFS),
        *CLAIM_REFS.values(),
    )))
    return ColumnTransverseConfinementResult(
        component_id=request.component_id,
        applicable=applicable,
        required_confinement_region_length_mm=region,
        confinement_spacing_limit_mm=spacing_limit,
        middle_spacing_limit_mm=middle_limit,
        longitudinal_bar_diameter_mm=phi_l,
        checks=tuple(checks),
        blockers=tuple(dict.fromkeys(blockers)),
        source_refs=source_refs,
        ductility=ductility,
        shear_vr_by_direction_kn=shear_vr,
    )


def evaluate_column_transverse_confinement_bound(
    request: ColumnTransverseConfinementInput,
    *,
    selected_rebar: CanonicalEngineSelectedRebar,
    design_lineage: DesignLineageQualification,
) -> ColumnTransverseConfinementResult:
    """Production binding: require selected rebar and exact qualified B6 lineage."""
    if not isinstance(selected_rebar, CanonicalEngineSelectedRebar):
        raise TypeError("selected_rebar must be CanonicalEngineSelectedRebar")
    if not isinstance(design_lineage, DesignLineageQualification):
        raise TypeError("design_lineage must be DesignLineageQualification")
    if not design_lineage.qualified:
        raise ColumnTransverseConfinementError("transverse design requires QUALIFIED DesignLineage")
    design_result = design_lineage.require_qualified_result()
    if request.model_fingerprint is None or request.evidence_epoch_id is None:
        raise ColumnTransverseConfinementError("production transverse input requires model/epoch identity")
    checks = (
        (selected_rebar.component_id, request.component_id, "selected rebar component"),
        (selected_rebar.model_fingerprint, request.model_fingerprint, "selected rebar model"),
        (selected_rebar.evidence_epoch_id, request.evidence_epoch_id, "selected rebar epoch"),
        (design_lineage.design_state.model_fingerprint, request.model_fingerprint, "design lineage model"),
        (design_lineage.design_state.evidence_epoch_id, request.evidence_epoch_id, "design lineage epoch"),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise ColumnTransverseConfinementError(f"{label} identity mismatch")
    if request.design_result_ref is not None and request.design_result_ref != design_result.identity_ref:
        raise ColumnTransverseConfinementError("transverse input design-result identity mismatch")
    return evaluate_column_transverse_confinement(request, selected_rebar=selected_rebar)


__all__ = [
    "CLAIM_REFS",
    "TBDY_2018_SOURCE_FINGERPRINT",
    "TS500_SOURCE_FINGERPRINT",
    "TRANSVERSE_CAUSAL_BINDING_AUTHORITY",
    "TRANSVERSE_CONFINEMENT_AUTHORITY",
    "ColumnDuctility",
    "ColumnTransverseConfinementError",
    "ColumnTransverseConfinementInput",
    "ColumnTransverseConfinementResult",
    "SpecialTieDetailingFacts",
    "TransverseDirectionFacts",
    "evaluate_column_transverse_confinement",
    "evaluate_column_transverse_confinement_bound",
]
