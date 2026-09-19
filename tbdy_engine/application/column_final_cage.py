# A37 reviewed final physical transverse-cage composition.
#
# This is not a selector and does not reinterpret ETABS design intent as final
# reinforcement. It binds explicit reviewed/project-provided physical cage
# facts (USER_PROVIDED_REBAR role) to the factual project RebarCatalog and the
# already-canonical P7 local-axis result.
#
# Ash and Asw remain distinct. This module materializes only the shear Asw
# projection needed by A37. Confinement Ash remains owned independently by A36.

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Sequence

from tbdy_engine.design.columns.rebar_catalog import RebarCatalog
from tbdy_engine.regulatory.column_shear_limited_program import (
    LimitedColumnShearRun,
)
from tbdy_engine.regulatory.column_transverse_confinement import (
    ColumnTransverseConfinementInput,
    SpecialTieDetailingFacts,
    TransverseDirectionFacts,
)
from tbdy_engine.regulatory.vs6_column_shear_p7_program import (
    VS6P7ColumnShearRun,
)

USER_PROVIDED_REBAR_ROLE = "USER_PROVIDED_REBAR"
FINAL_CAGE_AUTHORITY = "REVIEWED_PROJECT_FINAL_TRANSVERSE_CAGE"
LOCAL_AXIS_SHEAR_MAPPING_REF = (
    "CSI_ETABS_GET_REBAR_COLUMN_LOCAL_TIE_LEGS:"
    "Number2DirTieBars->V2|Number3DirTieBars->V3"
)


class ColumnFinalCageError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ColumnFinalCageError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ColumnFinalCageError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ColumnFinalCageError(
            f"{label} must be finite and > 0"
        )
    return number


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ColumnFinalCageError(
            f"{label} must be an integer > 0"
        )
    return value


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{label} must be a sequence")
    refs = tuple(
        dict.fromkeys(_text(value, label) for value in values)
    )
    if not refs:
        raise ColumnFinalCageError(f"{label} must be nonempty")
    return refs


@dataclass(frozen=True, slots=True)
class ReviewedColumnFinalCageContext:
    component_id: str
    section: str
    tie_size_name: str
    number_2_dir_tie_bars: int
    number_3_dir_tie_bars: int
    confinement_spacing_mm: float
    middle_spacing_mm: float
    shear_spacing_mm: float
    provided_confinement_region_length_mm: float
    horizontal_leg_spacing_dir2_mm: float
    horizontal_leg_spacing_dir3_mm: float
    restrained_longitudinal_bar_spacing_mm: float
    cantilever_column: bool
    arrangement: SpecialTieDetailingFacts | None
    review_refs: tuple[str, ...]
    semantic_role: str = USER_PROVIDED_REBAR_ROLE
    authority: str = FINAL_CAGE_AUTHORITY

    def __post_init__(self) -> None:
        for name in ("component_id", "section", "tie_size_name"):
            object.__setattr__(
                self,
                name,
                _text(getattr(self, name), name),
            )
        for name in (
            "number_2_dir_tie_bars",
            "number_3_dir_tie_bars",
        ):
            object.__setattr__(
                self,
                name,
                _positive_int(getattr(self, name), name),
            )
        for name in (
            "confinement_spacing_mm",
            "middle_spacing_mm",
            "shear_spacing_mm",
            "provided_confinement_region_length_mm",
            "horizontal_leg_spacing_dir2_mm",
            "horizontal_leg_spacing_dir3_mm",
            "restrained_longitudinal_bar_spacing_mm",
        ):
            object.__setattr__(
                self,
                name,
                _positive(getattr(self, name), name),
            )
        if type(self.cantilever_column) is not bool:
            raise TypeError("cantilever_column must be bool")
        if (
            self.arrangement is not None
            and not isinstance(
                self.arrangement,
                SpecialTieDetailingFacts,
            )
        ):
            raise TypeError(
                "arrangement must be SpecialTieDetailingFacts or None"
            )
        if self.semantic_role != USER_PROVIDED_REBAR_ROLE:
            raise ColumnFinalCageError(
                "final cage semantic_role must remain USER_PROVIDED_REBAR"
            )
        if self.authority != FINAL_CAGE_AUTHORITY:
            raise ColumnFinalCageError(
                "unsupported final-cage authority"
            )
        object.__setattr__(
            self,
            "review_refs",
            _refs(self.review_refs, "review_ref"),
        )


def _catalog_entry(
    catalog: RebarCatalog,
    tie_size_name: str,
):
    if not isinstance(catalog, RebarCatalog):
        raise TypeError("catalog must be RebarCatalog")
    name = _text(tie_size_name, "tie_size_name")
    matches = tuple(
        item for item in catalog.entries
        if item.name == name
    )
    if len(matches) != 1:
        raise ColumnFinalCageError(
            f"final cage tie size {name!r} must resolve exactly once "
            "in factual project RebarCatalog"
        )
    return matches[0]


def _asw_mm2(diameter_mm: float, leg_count: int) -> float:
    # Pure physical bar-area materialization, not a regulatory capacity rule.
    return (
        _positive(diameter_mm, "tie_diameter_mm") ** 2
        * math.pi
        / 4.0
        * _positive_int(leg_count, "leg_count")
    )


def _p7_direction(
    run: VS6P7ColumnShearRun | None,
    direction: str,
):
    if run is None:
        return None
    if not isinstance(run, VS6P7ColumnShearRun):
        raise TypeError("p7_run must be VS6P7ColumnShearRun or None")
    matches = tuple(
        item for item in run.directions
        if item.direction == direction
    )
    if len(matches) != 1:
        raise ColumnFinalCageError(
            f"P7 run must expose exactly one {direction} direction"
        )
    return matches[0]



def _limited_direction(
    run: LimitedColumnShearRun | None,
    direction: str,
):
    if run is None:
        return None
    if not isinstance(run, LimitedColumnShearRun):
        raise TypeError(
            "limited_run must be LimitedColumnShearRun or None"
        )
    matches = tuple(
        item
        for item in run.directions
        if item.direction == direction
    )
    if len(matches) != 1:
        raise ColumnFinalCageError(
            f"limited run must expose exactly one {direction} direction"
        )
    return matches[0]


def _direction_fact(
    *,
    base: TransverseDirectionFacts,
    local_direction: str,
    asw_mm2: float,
    horizontal_leg_spacing_mm: float,
    p7_direction,
    limited_direction,
    common_refs: tuple[str, ...],
) -> TransverseDirectionFacts:
    if local_direction not in {"V2", "V3"}:
        raise ColumnFinalCageError(
            "local_direction must be V2 or V3"
        )

    effective_depth_mm = None
    p7_ve_kn = None
    mapping_proven = None
    p7_refs: tuple[str, ...] = ()
    limited_shear = None

    if (
        p7_direction is not None
        and limited_direction is not None
    ):
        raise ColumnFinalCageError(
            "high P7 and limited shear authority are mutually exclusive"
        )

    if p7_direction is not None:
        effective = p7_direction.effective_depth
        if (
            getattr(effective, "resolved", False)
            and effective.effective_depth_d_mm is not None
        ):
            effective_depth_mm = float(
                effective.effective_depth_d_mm
            )
            mapping_proven = True
        p7_ve_kn = p7_direction.ve_kn
        p7_refs = tuple(
            dict.fromkeys(
                (
                    *p7_direction.tbdy_vd.source_refs,
                    *p7_direction.ts500_vd.source_refs,
                    *p7_direction.effective_depth.source_refs,
                )
            )
        )

    if limited_direction is not None:
        effective = limited_direction.effective_depth
        if (
            effective.resolved
            and effective.effective_depth_d_mm is not None
        ):
            effective_depth_mm = float(
                effective.effective_depth_d_mm
            )
            mapping_proven = True
        limited_shear = limited_direction
        p7_refs = tuple(
            dict.fromkeys(
                (
                    *limited_direction.source_refs,
                    *effective.source_refs,
                )
            )
        )

    return replace(
        base,
        provided_asw_mm2=asw_mm2,
        effective_depth_mm=effective_depth_mm,
        shear_mapping_proven=mapping_proven,
        qualified_vc_kn=None,
        p7_ve_kn=p7_ve_kn,
        limited_shear=limited_shear,
        horizontal_leg_spacing_mm=horizontal_leg_spacing_mm,
        source_refs=tuple(
            dict.fromkeys(
                (
                    *base.source_refs,
                    *common_refs,
                    *p7_refs,
                    LOCAL_AXIS_SHEAR_MAPPING_REF,
                    f"LOCAL_SHEAR_DIRECTION:{local_direction}",
                )
            )
        ),
    )


def apply_reviewed_final_cage_to_transverse_input(
    request: ColumnTransverseConfinementInput,
    *,
    reviewed: ReviewedColumnFinalCageContext,
    rebar_catalog: RebarCatalog,
    p7_run: VS6P7ColumnShearRun | None,
    limited_run: LimitedColumnShearRun | None = None,
) -> ColumnTransverseConfinementInput:
    if not isinstance(
        request,
        ColumnTransverseConfinementInput,
    ):
        raise TypeError(
            "request must be ColumnTransverseConfinementInput"
        )
    if not isinstance(
        reviewed,
        ReviewedColumnFinalCageContext,
    ):
        raise TypeError(
            "reviewed must be ReviewedColumnFinalCageContext"
        )
    if (
        p7_run is not None
        and limited_run is not None
    ):
        raise ColumnFinalCageError(
            "high P7 and limited shear run cannot both be supplied"
        )
    if (
        reviewed.component_id != request.component_id
        or reviewed.section != request.section
    ):
        raise ColumnFinalCageError(
            "final cage component/section identity mismatch"
        )
    if (
        p7_run is not None
        and p7_run.component_id != request.component_id
    ):
        raise ColumnFinalCageError(
            "final cage/P7 component identity mismatch"
        )
    if (
        limited_run is not None
        and limited_run.component_id != request.component_id
    ):
        raise ColumnFinalCageError(
            "final cage/limited component identity mismatch"
        )

    entry = _catalog_entry(
        rebar_catalog,
        reviewed.tie_size_name,
    )
    asw_v2 = _asw_mm2(
        entry.diameter_mm,
        reviewed.number_2_dir_tie_bars,
    )
    asw_v3 = _asw_mm2(
        entry.diameter_mm,
        reviewed.number_3_dir_tie_bars,
    )

    by_name = {
        item.direction: item
        for item in request.directions
    }
    if set(by_name) != {"DIR2", "DIR3"}:
        raise ColumnFinalCageError(
            "A37 bounded rectangular mapping requires DIR2 and DIR3"
        )

    refs = tuple(
        dict.fromkeys(
            (
                *reviewed.review_refs,
                entry.source_identity,
                (
                    "FINAL_CAGE:"
                    f"{reviewed.tie_size_name}:"
                    f"n2={reviewed.number_2_dir_tie_bars}:"
                    f"n3={reviewed.number_3_dir_tie_bars}:"
                    f"s={reviewed.shear_spacing_mm:.12g}mm"
                ),
            )
        )
    )

    dir2 = _direction_fact(
        base=by_name["DIR2"],
        local_direction="V2",
        asw_mm2=asw_v2,
        horizontal_leg_spacing_mm=(
            reviewed.horizontal_leg_spacing_dir2_mm
        ),
        p7_direction=_p7_direction(p7_run, "V2"),
        limited_direction=_limited_direction(limited_run, "V2"),
        common_refs=refs,
    )
    dir3 = _direction_fact(
        base=by_name["DIR3"],
        local_direction="V3",
        asw_mm2=asw_v3,
        horizontal_leg_spacing_mm=(
            reviewed.horizontal_leg_spacing_dir3_mm
        ),
        p7_direction=_p7_direction(p7_run, "V3"),
        limited_direction=_limited_direction(limited_run, "V3"),
        common_refs=refs,
    )

    return replace(
        request,
        cantilever_column=reviewed.cantilever_column,
        transverse_diameter_mm=entry.diameter_mm,
        confinement_spacing_mm=(
            reviewed.confinement_spacing_mm
        ),
        middle_spacing_mm=reviewed.middle_spacing_mm,
        provided_confinement_region_length_mm=(
            reviewed.provided_confinement_region_length_mm
        ),
        directions=(dir2, dir3),
        arrangement=reviewed.arrangement,
        restrained_longitudinal_bar_spacing_mm=(
            reviewed.restrained_longitudinal_bar_spacing_mm
        ),
        shear_spacing_mm=reviewed.shear_spacing_mm,
        source_refs=tuple(
            dict.fromkeys(
                (
                    *request.source_refs,
                    *refs,
                    LOCAL_AXIS_SHEAR_MAPPING_REF,
                )
            )
        ),
    )


__all__ = [
    "FINAL_CAGE_AUTHORITY",
    "LOCAL_AXIS_SHEAR_MAPPING_REF",
    "USER_PROVIDED_REBAR_ROLE",
    "ColumnFinalCageError",
    "ReviewedColumnFinalCageContext",
    "apply_reviewed_final_cage_to_transverse_input",
]
