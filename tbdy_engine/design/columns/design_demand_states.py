"""Pure VS6 design-demand reconstruction for linear ETABS combinations.

This module closes a critical boundary between factual ETABS result rows and
column P-M2-M3 design states.  A response-spectrum result does not preserve a
physical sign correspondence between interacting quantities.  Therefore raw
combination Max/Min rows are never promoted directly to concurrent design
vectors here.

For a LINEAR_ADD combination:

* signed linear-static contributions are summed exactly;
* response-spectrum contributions are reduced to factored component magnitudes;
* the response-spectrum part is expanded into the eight independent sign
  permutations of P, M2 and M3 used for three-dimensional frame design;
* a static-only combination produces one exact linear state per member end.

The module is pure: no ETABS calls, no reinforcement selection, no section
capacity and no compliance verdicts.
"""
from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from typing import Any, Mapping, Sequence

from tbdy_engine.design.columns.rebar_selection import ColumnDemandState


class ColumnDesignDemandError(ValueError):
    """Raised when factual case rows cannot support a design-demand build."""


SUPPORTED_LINEAR_CASE_TYPES = frozenset({"LinStatic", "LinRespSpec"})
DESIGN_AUTHORITY_STATIC = "STATIC_LINEAR_EXACT_DESIGN_STATE"
DESIGN_AUTHORITY_RESPONSE_SPECTRUM = "RESPONSE_SPECTRUM_SIGN_PERMUTATION_DESIGN_STATES"
CSI_SIGN_PERMUTATION_BEHAVIOR_REF = (
    "CSI ETABS Concrete Frame Design manual: response-spectrum modal sign "
    "correspondence is lost; eight P-M2-M3 sign combinations are checked."
)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnDesignDemandError(f"{label} must be a nonblank canonical string")
    return value


def _float(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ColumnDesignDemandError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ColumnDesignDemandError(f"{label} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class LinearComboConstituent:
    name: str
    scale_factor: float
    cname_type: str = "LOAD_CASE"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "constituent.name"))
        object.__setattr__(self, "cname_type", _text(self.cname_type, "constituent.cname_type"))
        factor = _float(self.scale_factor, "constituent.scale_factor")
        if self.cname_type != "LOAD_CASE":
            raise ColumnDesignDemandError(
                "VS6 design-demand reconstruction currently requires flattened LOAD_CASE constituents"
            )
        object.__setattr__(self, "scale_factor", factor)


@dataclass(frozen=True, slots=True)
class ComboEndDemandSummary:
    end_tag: str
    station_m: float
    static_nd_compression_n: float
    static_m2_nmm: float
    static_m3_nmm: float
    spectrum_nd_magnitude_n: float
    spectrum_m2_magnitude_nmm: float
    spectrum_m3_magnitude_nmm: float
    static_case_names: tuple[str, ...]
    response_spectrum_case_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComboDesignDemandBuild:
    component_id: str
    combo_name: str
    status: str
    authority: str
    states: tuple[ColumnDemandState, ...]
    end_summaries: tuple[ComboEndDemandSummary, ...]
    behavior_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComboObservedSubsetVerification:
    component_id: str
    combo_name: str
    status: str
    observed_state_count: int
    matched_state_count: int
    unmatched_observed_state_ids: tuple[str, ...]
    matched_generated_state_ids: tuple[str, ...]


def _constituents_from_mappings(items: Sequence[Mapping[str, Any]]) -> tuple[LinearComboConstituent, ...]:
    return tuple(
        LinearComboConstituent(
            name=_text(item.get("name"), "constituent.name"),
            scale_factor=_float(item.get("scale_factor"), "constituent.scale_factor"),
            cname_type=_text(item.get("cname_type", "LOAD_CASE"), "constituent.cname_type"),
        )
        for item in items
    )


def _single_case_row(
    grouped: Mapping[tuple[str, str], tuple[ColumnDemandState, ...]],
    *,
    end_tag: str,
    case_name: str,
) -> ColumnDemandState:
    rows = grouped.get((end_tag, case_name), ())
    if len(rows) != 1:
        raise ColumnDesignDemandError(
            f"exactly one end row required for case={case_name} end={end_tag}; got {len(rows)}"
        )
    return rows[0]


def build_linear_combo_design_demands(
    *,
    component_id: str,
    combo_name: str,
    combo_type: str,
    constituents: Sequence[LinearComboConstituent] | Sequence[Mapping[str, Any]],
    case_demands: Sequence[ColumnDemandState],
) -> ComboDesignDemandBuild:
    """Build exact static or eight-way response-spectrum P-M2-M3 design states.

    ``case_demands`` must contain one normalized I/J-end row for every load case
    referenced by the combination.  Standalone response-spectrum case rows are
    treated as component magnitudes; their signs are not taken as concurrent
    physical signs.
    """
    component = _text(component_id, "component_id")
    combo = _text(combo_name, "combo_name")
    if combo_type != "LINEAR_ADD":
        raise ColumnDesignDemandError("VS6 design-demand reconstruction requires combo_type=LINEAR_ADD")

    terms = tuple(constituents)
    if not terms:
        raise ColumnDesignDemandError("combination must contain at least one constituent")
    if isinstance(terms[0], Mapping):
        terms = _constituents_from_mappings(terms)  # type: ignore[arg-type,assignment]
    else:
        terms = tuple(terms)  # type: ignore[assignment]
    if not all(isinstance(item, LinearComboConstituent) for item in terms):
        raise ColumnDesignDemandError("constituents must be LinearComboConstituent or mapping rows")
    typed_terms: tuple[LinearComboConstituent, ...] = tuple(terms)  # type: ignore[arg-type]
    if len({item.name for item in typed_terms}) != len(typed_terms):
        raise ColumnDesignDemandError("duplicate load-case names in combination definition are not allowed")

    demands = tuple(case_demands)
    if not demands:
        raise ColumnDesignDemandError("case_demands must be nonempty")
    if any(item.component_id != component for item in demands):
        raise ColumnDesignDemandError("case_demands contain a different component_id")

    requested = {item.name for item in typed_terms}
    filtered = tuple(item for item in demands if item.output_case in requested)
    if not filtered:
        raise ColumnDesignDemandError("no requested constituent case rows found")
    unsupported = sorted({item.case_type for item in filtered} - SUPPORTED_LINEAR_CASE_TYPES)
    if unsupported:
        raise ColumnDesignDemandError("unsupported constituent case type(s): " + ",".join(unsupported))

    ends = tuple(sorted({item.end_tag for item in filtered}))
    if set(ends) != {"I_END", "J_END"}:
        raise ColumnDesignDemandError(f"exact I_END/J_END coverage required; got {ends!r}")

    grouped: dict[tuple[str, str], tuple[ColumnDemandState, ...]] = {}
    for end_tag in ends:
        for term in typed_terms:
            grouped[(end_tag, term.name)] = tuple(
                item for item in filtered if item.end_tag == end_tag and item.output_case == term.name
            )

    states: list[ColumnDemandState] = []
    summaries: list[ComboEndDemandSummary] = []
    any_spectrum = False

    for end_tag in ends:
        static_n = 0.0
        static_m2 = 0.0
        static_m3 = 0.0
        spectrum_n = 0.0
        spectrum_m2 = 0.0
        spectrum_m3 = 0.0
        static_names: list[str] = []
        spectrum_names: list[str] = []
        stations: set[float] = set()
        source_parts: list[str] = []

        for term in typed_terms:
            row = _single_case_row(grouped, end_tag=end_tag, case_name=term.name)
            stations.add(round(row.station_m, 12))
            source_parts.append(f"{term.name}@{term.scale_factor:g}:{row.source_identity}")

            if row.case_type == "LinStatic":
                static_names.append(term.name)
                static_n += term.scale_factor * row.nd_compression_n
                static_m2 += term.scale_factor * row.m2_nmm
                static_m3 += term.scale_factor * row.m3_nmm
            elif row.case_type == "LinRespSpec":
                any_spectrum = True
                spectrum_names.append(term.name)
                factor = abs(term.scale_factor)
                spectrum_n += factor * abs(row.nd_compression_n)
                spectrum_m2 += factor * abs(row.m2_nmm)
                spectrum_m3 += factor * abs(row.m3_nmm)
            else:  # defensive; unsupported types are rejected above
                raise ColumnDesignDemandError(f"unsupported case type {row.case_type}")

        if len(stations) != 1:
            raise ColumnDesignDemandError(f"constituent station mismatch at {end_tag}: {sorted(stations)}")
        station_m = next(iter(stations))
        summaries.append(
            ComboEndDemandSummary(
                end_tag=end_tag,
                station_m=station_m,
                static_nd_compression_n=static_n,
                static_m2_nmm=static_m2,
                static_m3_nmm=static_m3,
                spectrum_nd_magnitude_n=spectrum_n,
                spectrum_m2_magnitude_nmm=spectrum_m2,
                spectrum_m3_magnitude_nmm=spectrum_m3,
                static_case_names=tuple(static_names),
                response_spectrum_case_names=tuple(spectrum_names),
            )
        )
        source_identity = "||".join(source_parts)

        if spectrum_names:
            for sign_n, sign_m2, sign_m3 in itertools.product((-1, 1), repeat=3):
                sign_code = f"P{sign_n:+d}_M2{sign_m2:+d}_M3{sign_m3:+d}"
                states.append(
                    ColumnDemandState(
                        state_id=f"{component}|{combo}|{end_tag}|RS_SIGN_PERM|{sign_code}",
                        component_id=component,
                        output_case=combo,
                        case_type="DesignResponseSpectrumPermutation",
                        step_type=sign_code,
                        step_number=None,
                        station_m=station_m,
                        end_tag=end_tag,
                        nd_compression_n=static_n + sign_n * spectrum_n,
                        m2_nmm=static_m2 + sign_m2 * spectrum_m2,
                        m3_nmm=static_m3 + sign_m3 * spectrum_m3,
                        source_identity=f"{combo}|{end_tag}|{sign_code}|{source_identity}",
                    )
                )
        else:
            states.append(
                ColumnDemandState(
                    state_id=f"{component}|{combo}|{end_tag}|STATIC_LINEAR_EXACT",
                    component_id=component,
                    output_case=combo,
                    case_type="DesignStaticLinearExact",
                    step_type=None,
                    step_number=None,
                    station_m=station_m,
                    end_tag=end_tag,
                    nd_compression_n=static_n,
                    m2_nmm=static_m2,
                    m3_nmm=static_m3,
                    source_identity=f"{combo}|{end_tag}|STATIC_LINEAR_EXACT|{source_identity}",
                )
            )

    states.sort(key=lambda item: item.state_id)
    authority = DESIGN_AUTHORITY_RESPONSE_SPECTRUM if any_spectrum else DESIGN_AUTHORITY_STATIC
    return ComboDesignDemandBuild(
        component_id=component,
        combo_name=combo,
        status="PROVEN_DESIGN_DEMAND_STATES",
        authority=authority,
        states=tuple(states),
        end_summaries=tuple(summaries),
        behavior_refs=(CSI_SIGN_PERMUTATION_BEHAVIOR_REF,) if any_spectrum else (),
    )


def verify_observed_combo_rows_are_generated_subset(
    *,
    generated: ComboDesignDemandBuild,
    observed_combo_demands: Sequence[ColumnDemandState],
    force_tolerance_n: float = 250.0,
    moment_tolerance_nmm: float = 250_000.0,
) -> ComboObservedSubsetVerification:
    """Verify display-table combo rows are contained in the generated design set.

    This is validation only.  Matching an ETABS Max/Min row does not promote
    that row to a concurrent P-M2-M3 vector; it only proves that the factual
    display extreme is represented by the wider design-permutation set.
    """
    ftol = _float(force_tolerance_n, "force_tolerance_n")
    mtol = _float(moment_tolerance_nmm, "moment_tolerance_nmm")
    if ftol < 0.0 or mtol < 0.0:
        raise ColumnDesignDemandError("verification tolerances must be >= 0")

    observed = tuple(
        item
        for item in observed_combo_demands
        if item.component_id == generated.component_id and item.output_case == generated.combo_name
    )
    matched_generated: list[str] = []
    unmatched: list[str] = []
    for item in observed:
        matches = tuple(
            state
            for state in generated.states
            if state.end_tag == item.end_tag
            and abs(state.nd_compression_n - item.nd_compression_n) <= ftol
            and abs(state.m2_nmm - item.m2_nmm) <= mtol
            and abs(state.m3_nmm - item.m3_nmm) <= mtol
        )
        if not matches:
            unmatched.append(item.state_id)
        else:
            matched_generated.append(matches[0].state_id)

    status = (
        "PROVEN_OBSERVED_ROWS_SUBSET_OF_DESIGN_PERMUTATIONS"
        if observed and not unmatched
        else "NOT_PROVEN_OBSERVED_ROWS_SUBSET"
    )
    return ComboObservedSubsetVerification(
        component_id=generated.component_id,
        combo_name=generated.combo_name,
        status=status,
        observed_state_count=len(observed),
        matched_state_count=len(observed) - len(unmatched),
        unmatched_observed_state_ids=tuple(unmatched),
        matched_generated_state_ids=tuple(matched_generated),
    )


__all__ = [
    "CSI_SIGN_PERMUTATION_BEHAVIOR_REF",
    "ColumnDesignDemandError",
    "ComboDesignDemandBuild",
    "ComboEndDemandSummary",
    "ComboObservedSubsetVerification",
    "DESIGN_AUTHORITY_RESPONSE_SPECTRUM",
    "DESIGN_AUTHORITY_STATIC",
    "LinearComboConstituent",
    "build_linear_combo_design_demands",
    "verify_observed_combo_rows_are_generated_subset",
]
