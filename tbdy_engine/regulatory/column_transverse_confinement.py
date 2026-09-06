"""Source-bound TBDY 2018 column transverse/confinement authority.

Closes the bounded COLUMN-R1 Lane-C regulatory gap. Legacy/default detailing
values are not authority. Shear, longitudinal selection, ETABS acquisition and
final detailing selection remain owned by their existing authorities.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.design.columns.column_longitudinal_selection import (
    CanonicalEngineSelectedRebar,
    ENGINE_SELECTED_REBAR_AUTHORITY,
)
from tbdy_engine.regulatory.authority import (
    RegulatoryClaim,
    RegulatorySourceDocument,
    SourceAnchor,
    regulatory_claim_fingerprint,
)

TBDY_2018_SOURCE_FINGERPRINT = "8d3a959ece2804ed2f37f5c6269566503fa21e86e71ae8e45c4b8a8cce37625c"
TRANSVERSE_CONFINEMENT_AUTHORITY = "TBDY_2018_COLUMN_TRANSVERSE_CONFINEMENT"

_SOURCE = RegulatorySourceDocument(
    source_id="TBDY_2018_OFFICIAL",
    title="Türkiye Bina Deprem Yönetmeliği 2018",
    edition="2018",
    issuer="AFAD",
    jurisdiction="TR",
    source_fingerprint=TBDY_2018_SOURCE_FINGERPRINT,
)
_ANCHORS = (
    SourceAnchor("TBDY_2018_7_3_4_1", _SOURCE.source_id, "§7.3.4.1; PDF pp.136-137"),
    SourceAnchor("TBDY_2018_7_3_4_2", _SOURCE.source_id, "§7.3.4.2; PDF p.137"),
    SourceAnchor("TBDY_2018_7_2_8_1", _SOURCE.source_id, "§7.2.8.1; PDF p.132"),
    SourceAnchor("TBDY_2018_7_2_8_2", _SOURCE.source_id, "§7.2.8.2; PDF p.132"),
)
_CLAIMS = (
    RegulatoryClaim(
        claim_id="COL_TRANSVERSE_CONFINEMENT_REGION",
        claim_version="1.0",
        anchor_refs=("TBDY_2018_7_3_4_1",),
        normalized_statement=(
            "High-ductility column end confinement length is not less than max(clear-height/6, "
            "1.5 times the largest section dimension, 500 mm), or twice the largest section "
            "dimension at the bottom of a cantilever column."
        ),
    ),
    RegulatoryClaim(
        claim_id="COL_TRANSVERSE_CONFINEMENT_REINFORCEMENT",
        claim_version="1.0",
        anchor_refs=("TBDY_2018_7_3_4_1",),
        normalized_statement=(
            "Confinement-region transverse diameter is at least 8 mm; spacing is between 50 mm "
            "and min(one-third minimum section dimension, 150 mm, six longitudinal-bar diameters); "
            "horizontal leg spacing is at most 25 transverse-bar diameters; rectangular tied columns "
            "satisfy both Eq.7.1 Ash bounds, reduced to two-thirds only when Nd <= 0.20 Ac fck."
        ),
    ),
    RegulatoryClaim(
        claim_id="COL_TRANSVERSE_MIDDLE_REINFORCEMENT",
        claim_version="1.0",
        anchor_refs=("TBDY_2018_7_3_4_2",),
        normalized_statement=(
            "Middle-region special hoops/cross-ties have diameter at least 8 mm, spacing at most "
            "min(one-half minimum section dimension, 200 mm), and horizontal leg spacing at most "
            "25 transverse-bar diameters."
        ),
    ),
    RegulatoryClaim(
        claim_id="COL_TRANSVERSE_SPECIAL_TIE_DETAILING",
        claim_version="1.0",
        anchor_refs=("TBDY_2018_7_2_8_1", "TBDY_2018_7_2_8_2"),
        normalized_statement=(
            "Special hoops/cross-ties satisfy documented hook, bend and tail geometry, enclose/engage "
            "longitudinal bars, and cross-tie diameter/spacing equal hoop diameter/spacing."
        ),
    ),
)


def _claim_ref(claim_id: str) -> str:
    claim = next(item for item in _CLAIMS if item.claim_id == claim_id)
    return regulatory_claim_fingerprint(claim=claim, anchors=_ANCHORS, source_documents=(_SOURCE,))


CLAIM_REFS = {item.claim_id: _claim_ref(item.claim_id) for item in _CLAIMS}


class ColumnTransverseConfinementError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnTransverseConfinementError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnTransverseConfinementError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ColumnTransverseConfinementError(f"{label} must be finite and > 0")
    return number


def _nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnTransverseConfinementError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ColumnTransverseConfinementError(f"{label} must be finite and >= 0")
    return number


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{label} must be a sequence")
    refs = tuple(dict.fromkeys(_text(item, label) for item in values))
    if not refs:
        raise ColumnTransverseConfinementError(f"{label} must be nonempty")
    return refs


@dataclass(frozen=True, slots=True)
class TransverseDirectionFacts:
    direction: str
    confined_core_width_bk_mm: float
    provided_ash_mm2: float | None
    horizontal_leg_spacing_mm: float | None
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        direction = _text(self.direction, "direction")
        if direction not in {"DIR2", "DIR3"}:
            raise ColumnTransverseConfinementError("direction must be DIR2 or DIR3")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "confined_core_width_bk_mm", _positive(self.confined_core_width_bk_mm, "confined_core_width_bk_mm"))
        if self.provided_ash_mm2 is not None:
            object.__setattr__(self, "provided_ash_mm2", _nonnegative(self.provided_ash_mm2, "provided_ash_mm2"))
        if self.horizontal_leg_spacing_mm is not None:
            object.__setattr__(self, "horizontal_leg_spacing_mm", _positive(self.horizontal_leg_spacing_mm, "horizontal_leg_spacing_mm"))
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "direction source_ref"))


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
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("hoop_both_ends_135_hooks", "hoops_enclose_longitudinal_bars", "hooks_close_around_longitudinal_bar", "cross_tie_present", "cross_tie_ends_wrap_longitudinal_and_hoop"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise TypeError(f"{name} must be bool or None")
        for name in ("min_inner_bend_diameter_mm", "min_hook_tail_length_mm", "cross_tie_diameter_mm", "cross_tie_spacing_mm"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _positive(value, name))
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "arrangement source_ref"))


@dataclass(frozen=True, slots=True)
class ColumnTransverseConfinementInput:
    component_id: str
    story: str | None
    section: str | None
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        if self.story is not None:
            object.__setattr__(self, "story", _text(self.story, "story"))
        if self.section is not None:
            object.__setattr__(self, "section", _text(self.section, "section"))
        for name in ("high_ductility_applies", "cantilever_column"):
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise TypeError(f"{name} must be bool or None")
        for name in ("clear_height_mm", "width_mm", "depth_mm", "gross_area_ac_mm2", "confined_core_area_ack_mm2", "fck_mpa", "fywk_mpa"):
            object.__setattr__(self, name, _positive(getattr(self, name), name))
        object.__setattr__(self, "axial_design_force_nd_n", _nonnegative(self.axial_design_force_nd_n, "axial_design_force_nd_n"))
        if self.confined_core_area_ack_mm2 > self.gross_area_ac_mm2:
            raise ColumnTransverseConfinementError("confined core area may not exceed gross area")
        for name in ("transverse_diameter_mm", "confinement_spacing_mm", "middle_spacing_mm", "provided_confinement_region_length_mm"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _positive(value, name))
        directions = tuple(self.directions)
        if len(directions) != 2 or {item.direction for item in directions} != {"DIR2", "DIR3"}:
            raise ColumnTransverseConfinementError("directions must contain exactly DIR2 and DIR3")
        object.__setattr__(self, "directions", tuple(sorted(directions, key=lambda item: item.direction)))
        if self.arrangement is not None and not isinstance(self.arrangement, SpecialTieDetailingFacts):
            raise TypeError("arrangement must be SpecialTieDetailingFacts or None")
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "input source_ref"))


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
    authority: str = TRANSVERSE_CONFINEMENT_AUTHORITY

    @property
    def complete(self) -> bool:
        return not self.blockers and all(item.status not in {CheckStatus.NO_DATA, CheckStatus.BLOCKED} for item in self.checks)

    @property
    def failed(self) -> bool:
        return any(item.status is CheckStatus.FAIL for item in self.checks)


def _check(request, *, check_id, status, message, claim_id, value=None, limit=None, ratio=None, ratio_type=None, pass_rule=None, unit=None, extra_refs=()):
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
        evaluation_level=EvaluationLevel.DESIGN_LEVEL if status not in {CheckStatus.BLOCKED, CheckStatus.NO_DATA, CheckStatus.OUT_OF_SCOPE} else EvaluationLevel.NO_DATA,
        evidence=tuple(dict.fromkeys((*request.source_refs, *extra_refs, CLAIM_REFS[claim_id]))),
        messages=(message,),
        code_ref="TBDY 2018 §7.3.4 / §7.2.8",
    )


def _selected_longitudinal_diameter(selected_rebar, component_id):
    if selected_rebar is None:
        return None
    if not isinstance(selected_rebar, CanonicalEngineSelectedRebar):
        raise TypeError("selected_rebar must be CanonicalEngineSelectedRebar or None")
    if selected_rebar.authority != ENGINE_SELECTED_REBAR_AUTHORITY:
        raise ColumnTransverseConfinementError("selected longitudinal rebar lacks canonical ENGINE_SELECTED_REBAR authority")
    if selected_rebar.component_id != component_id:
        raise ColumnTransverseConfinementError("selected longitudinal rebar component identity mismatch")
    if selected_rebar.selected_candidate.candidate_id != selected_rebar.candidate_id:
        raise ColumnTransverseConfinementError("selected longitudinal rebar candidate identity mismatch")
    return _positive(selected_rebar.selected_candidate.bar_diameter_mm, "selected longitudinal bar diameter")


def evaluate_column_transverse_confinement(request: ColumnTransverseConfinementInput, *, selected_rebar: CanonicalEngineSelectedRebar | None) -> ColumnTransverseConfinementResult:
    """Evaluate bounded TBDY 7.3.4/7.2.8 authority fail-closed."""
    if not isinstance(request, ColumnTransverseConfinementInput):
        raise TypeError("request must be ColumnTransverseConfinementInput")
    phi_l = _selected_longitudinal_diameter(selected_rebar, request.component_id)
    checks: list[CheckResult] = []
    blockers: list[str] = []
    if request.high_ductility_applies is None:
        blockers.append("CONFINEMENT_APPLICABILITY_NOT_PROVEN")
        checks.append(_check(request, check_id="COL_CONFINEMENT_APPLICABILITY", status=CheckStatus.BLOCKED, message=blockers[-1], claim_id="COL_TRANSVERSE_CONFINEMENT_REGION"))
        return ColumnTransverseConfinementResult(request.component_id, None, None, None, None, phi_l, tuple(checks), tuple(blockers), request.source_refs)
    if request.high_ductility_applies is False:
        checks.append(_check(request, check_id="COL_CONFINEMENT_APPLICABILITY", status=CheckStatus.OUT_OF_SCOPE, value=False, message="TBDY 7.3.4 high-ductility confinement is proven not applicable.", claim_id="COL_TRANSVERSE_CONFINEMENT_REGION"))
        return ColumnTransverseConfinementResult(request.component_id, False, None, None, None, phi_l, tuple(checks), (), request.source_refs)

    largest = max(request.width_mm, request.depth_mm)
    min_dim = min(request.width_mm, request.depth_mm)
    required_region = None
    if request.cantilever_column is None:
        blockers.append("CANTILEVER_COLUMN_STATUS_NOT_PROVEN")
        checks.append(_check(request, check_id="COL_CONFINEMENT_REGION_LENGTH", status=CheckStatus.BLOCKED, message=blockers[-1], claim_id="COL_TRANSVERSE_CONFINEMENT_REGION"))
    else:
        required_region = 2.0 * largest if request.cantilever_column else max(request.clear_height_mm / 6.0, 1.5 * largest, 500.0)
        actual = request.provided_confinement_region_length_mm
        if actual is None:
            blockers.append("CONFINEMENT_REGION_LENGTH_NOT_AVAILABLE")
            checks.append(_check(request, check_id="COL_CONFINEMENT_REGION_LENGTH", status=CheckStatus.BLOCKED, limit=required_region, unit="mm", message=blockers[-1], claim_id="COL_TRANSVERSE_CONFINEMENT_REGION"))
        else:
            ok = actual + 1e-9 >= required_region
            checks.append(_check(request, check_id="COL_CONFINEMENT_REGION_LENGTH", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=actual, limit=required_region, ratio=actual/required_region, ratio_type="value_over_minimum", pass_rule="value >= minimum", unit="mm", message="Confinement-region length satisfies TBDY." if ok else "Confinement-region length is below TBDY minimum.", claim_id="COL_TRANSVERSE_CONFINEMENT_REGION"))

    phi_w = request.transverse_diameter_mm
    if phi_w is None:
        blockers.append("TRANSVERSE_DIAMETER_NOT_AVAILABLE")
        checks.append(_check(request, check_id="COL_TRANSVERSE_MIN_DIAMETER", status=CheckStatus.BLOCKED, limit=8.0, unit="mm", message=blockers[-1], claim_id="COL_TRANSVERSE_CONFINEMENT_REINFORCEMENT"))
    else:
        ok = phi_w + 1e-9 >= 8.0
        checks.append(_check(request, check_id="COL_TRANSVERSE_MIN_DIAMETER", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=phi_w, limit=8.0, ratio=phi_w/8.0, ratio_type="value_over_minimum", pass_rule="value >= minimum", unit="mm", message="Transverse diameter satisfies 8 mm minimum." if ok else "Transverse diameter is below 8 mm.", claim_id="COL_TRANSVERSE_CONFINEMENT_REINFORCEMENT"))

    confinement_limit = None
    if phi_l is None:
        blockers.append("ENGINE_SELECTED_REBAR_REQUIRED_FOR_CONFINEMENT_SPACING")
        checks.append(_check(request, check_id="COL_CONFINEMENT_SPACING_MAX", status=CheckStatus.BLOCKED, message=blockers[-1], claim_id="COL_TRANSVERSE_CONFINEMENT_REINFORCEMENT"))
    else:
        confinement_limit = min(min_dim/3.0, 150.0, 6.0*phi_l)
        spacing = request.confinement_spacing_mm
        if spacing is None:
            blockers.append("CONFINEMENT_SPACING_NOT_AVAILABLE")
            checks.append(_check(request, check_id="COL_CONFINEMENT_SPACING_MAX", status=CheckStatus.BLOCKED, limit=confinement_limit, unit="mm", message=blockers[-1], claim_id="COL_TRANSVERSE_CONFINEMENT_REINFORCEMENT"))
        else:
            ok = 50.0-1e-9 <= spacing <= confinement_limit+1e-9
            checks.append(_check(request, check_id="COL_CONFINEMENT_SPACING_MAX", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=spacing, limit={"min_mm":50.0,"max_mm":confinement_limit}, pass_rule="50 mm <= spacing <= maximum", unit="mm", message="Confinement spacing satisfies TBDY." if ok else "Confinement spacing violates TBDY bounds.", claim_id="COL_TRANSVERSE_CONFINEMENT_REINFORCEMENT"))

    middle_limit = min(min_dim/2.0, 200.0)
    if request.middle_spacing_mm is None:
        blockers.append("MIDDLE_SPACING_NOT_AVAILABLE")
        checks.append(_check(request, check_id="COL_MIDDLE_TRANSVERSE_SPACING_MAX", status=CheckStatus.BLOCKED, limit=middle_limit, unit="mm", message=blockers[-1], claim_id="COL_TRANSVERSE_MIDDLE_REINFORCEMENT"))
    else:
        actual = request.middle_spacing_mm
        ok = actual <= middle_limit+1e-9
        checks.append(_check(request, check_id="COL_MIDDLE_TRANSVERSE_SPACING_MAX", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=actual, limit=middle_limit, ratio=actual/middle_limit, ratio_type="value_over_maximum", pass_rule="value <= maximum", unit="mm", message="Middle-region spacing satisfies TBDY." if ok else "Middle-region spacing exceeds TBDY maximum.", claim_id="COL_TRANSVERSE_MIDDLE_REINFORCEMENT"))

    factor = 2.0/3.0 if request.axial_design_force_nd_n <= 0.20*request.gross_area_ac_mm2*request.fck_mpa + 1e-9 else 1.0
    for direction in request.directions:
        if request.confinement_spacing_mm is None:
            blockers.append(f"CONFINEMENT_SPACING_REQUIRED_FOR_ASH:{direction.direction}")
            checks.append(_check(request, check_id=f"COL_CONFINEMENT_ASH_{direction.direction}", status=CheckStatus.BLOCKED, message=blockers[-1], claim_id="COL_TRANSVERSE_CONFINEMENT_REINFORCEMENT", extra_refs=direction.source_refs))
        else:
            s = request.confinement_spacing_mm
            req_a = 0.30*s*direction.confined_core_width_bk_mm*(request.gross_area_ac_mm2/request.confined_core_area_ack_mm2-1.0)*request.fck_mpa/request.fywk_mpa
            req_b = 0.075*s*direction.confined_core_width_bk_mm*request.fck_mpa/request.fywk_mpa
            required = factor*max(req_a, req_b)
            actual = direction.provided_ash_mm2
            if actual is None:
                blockers.append(f"PROVIDED_ASH_NOT_AVAILABLE:{direction.direction}")
                checks.append(_check(request, check_id=f"COL_CONFINEMENT_ASH_{direction.direction}", status=CheckStatus.BLOCKED, limit=required, unit="mm2", message=blockers[-1], claim_id="COL_TRANSVERSE_CONFINEMENT_REINFORCEMENT", extra_refs=direction.source_refs))
            else:
                ok = actual+1e-9 >= required
                checks.append(_check(request, check_id=f"COL_CONFINEMENT_ASH_{direction.direction}", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=actual, limit=required, ratio=actual/required if required>0 else None, ratio_type="actual_over_required" if required>0 else None, pass_rule="provided Ash >= required Ash", unit="mm2", message="Provided Ash satisfies governing Eq.7.1." if ok else "Provided Ash is below governing Eq.7.1.", claim_id="COL_TRANSVERSE_CONFINEMENT_REINFORCEMENT", extra_refs=direction.source_refs))
        if phi_w is None or direction.horizontal_leg_spacing_mm is None:
            blockers.append(f"TIE_LEG_GEOMETRY_NOT_AVAILABLE:{direction.direction}")
            checks.append(_check(request, check_id=f"COL_TIE_LEG_SPACING_{direction.direction}", status=CheckStatus.BLOCKED, message=blockers[-1], claim_id="COL_TRANSVERSE_CONFINEMENT_REINFORCEMENT", extra_refs=direction.source_refs))
        else:
            limit = 25.0*phi_w
            actual = direction.horizontal_leg_spacing_mm
            ok = actual <= limit+1e-9
            checks.append(_check(request, check_id=f"COL_TIE_LEG_SPACING_{direction.direction}", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=actual, limit=limit, ratio=actual/limit, ratio_type="value_over_maximum", pass_rule="value <= 25 phi_transverse", unit="mm", message="Tie-leg spacing satisfies TBDY." if ok else "Tie-leg spacing exceeds TBDY maximum.", claim_id="COL_TRANSVERSE_CONFINEMENT_REINFORCEMENT", extra_refs=direction.source_refs))

    arrangement = request.arrangement
    if arrangement is None or phi_w is None:
        blockers.append("SPECIAL_TIE_DETAILING_FACTS_NOT_AVAILABLE")
        checks.append(_check(request, check_id="COL_SPECIAL_TIE_DETAILING", status=CheckStatus.BLOCKED, message=blockers[-1], claim_id="COL_TRANSVERSE_SPECIAL_TIE_DETAILING"))
    else:
        required_bend, required_tail = 5.0*phi_w, max(6.0*phi_w,80.0)
        missing = any(value is None for value in (arrangement.hoop_both_ends_135_hooks, arrangement.hoops_enclose_longitudinal_bars, arrangement.hooks_close_around_longitudinal_bar, arrangement.min_inner_bend_diameter_mm, arrangement.min_hook_tail_length_mm))
        if arrangement.cross_tie_present is True:
            missing = missing or any(value is None for value in (arrangement.cross_tie_diameter_mm, arrangement.cross_tie_spacing_mm, arrangement.cross_tie_ends_wrap_longitudinal_and_hoop, request.confinement_spacing_mm))
        if missing:
            blockers.append("SPECIAL_TIE_DETAILING_FACTS_INCOMPLETE")
            checks.append(_check(request, check_id="COL_SPECIAL_TIE_DETAILING", status=CheckStatus.BLOCKED, message=blockers[-1], claim_id="COL_TRANSVERSE_SPECIAL_TIE_DETAILING", extra_refs=arrangement.source_refs))
        else:
            conditions = [arrangement.hoop_both_ends_135_hooks is True, arrangement.hoops_enclose_longitudinal_bars is True, arrangement.hooks_close_around_longitudinal_bar is True, float(arrangement.min_inner_bend_diameter_mm)+1e-9 >= required_bend, float(arrangement.min_hook_tail_length_mm)+1e-9 >= required_tail]
            if arrangement.cross_tie_present is True:
                conditions += [math.isclose(float(arrangement.cross_tie_diameter_mm),phi_w,rel_tol=0.0,abs_tol=1e-9), math.isclose(float(arrangement.cross_tie_spacing_mm),float(request.confinement_spacing_mm),rel_tol=0.0,abs_tol=1e-9), arrangement.cross_tie_ends_wrap_longitudinal_and_hoop is True]
            ok = all(conditions)
            checks.append(_check(request, check_id="COL_SPECIAL_TIE_DETAILING", status=CheckStatus.OK if ok else CheckStatus.FAIL, value=ok, limit=True, ratio_type="boolean", pass_rule="all documented special tie facts true", message="Special tie detailing satisfies TBDY 7.2.8." if ok else "Special tie detailing violates TBDY 7.2.8.", claim_id="COL_TRANSVERSE_SPECIAL_TIE_DETAILING", extra_refs=arrangement.source_refs))

    return ColumnTransverseConfinementResult(
        component_id=request.component_id,
        applicable=True,
        required_confinement_region_length_mm=required_region,
        confinement_spacing_limit_mm=confinement_limit,
        middle_spacing_limit_mm=middle_limit,
        longitudinal_bar_diameter_mm=phi_l,
        checks=tuple(checks),
        blockers=tuple(dict.fromkeys(blockers)),
        source_refs=tuple(dict.fromkeys((*request.source_refs, *CLAIM_REFS.values()))),
    )


__all__ = [
    "CLAIM_REFS", "TRANSVERSE_CONFINEMENT_AUTHORITY", "TBDY_2018_SOURCE_FINGERPRINT",
    "ColumnTransverseConfinementError", "ColumnTransverseConfinementInput",
    "ColumnTransverseConfinementResult", "SpecialTieDetailingFacts", "TransverseDirectionFacts",
    "evaluate_column_transverse_confinement",
]
