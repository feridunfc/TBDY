"""Pure TS500 7.6.2.1 storey stability-index kernel.

This module is regulatory calculation logic, not ETABS acquisition logic.  It
consumes already source-bound storey quantities and evaluates Eq. 7.13:

    phi_i = 1.5 * Delta_i * sum(N_di) / (V_fi * l_i)

The code is deliberately strict about the analysis basis.  TS500 requires the
stability-index route to use uncracked-section assumptions and the unfavorable
result from the prescribed G+Q+E and G+1.3Q+1.3W load bases.  Factual ETABS
story tables are not sufficient authority by themselves.

A value above 0.05 does NOT prove that a storey is sway-permitted; it only means
that sway-prevented behavior has not been proven by this particular criterion.
The caller may still use another TS500-permitted proof route (for example the
first/second-order <=5% moment-difference route).
"""
from __future__ import annotations

from dataclasses import dataclass
import math


TS500_STABILITY_LIMIT = 0.05
TS500_LOAD_GQE = "TS500_FD_1.0G_1.0Q_1.0E"
TS500_LOAD_GQW = "TS500_FD_1.0G_1.3Q_1.3W"
REQUIRED_STABILITY_LOAD_BASES = frozenset({TS500_LOAD_GQE, TS500_LOAD_GQW})

STORY_STABILITY_INPUT_AUTHORITY = "TS500_7.6.2.1_STORY_STABILITY_INPUTS"
UNCRACKED_SECTION_BASIS_AUTHORITY = "TS500_7.6.2.1_UNCRACKED_SECTION_BASIS"
LOAD_BASIS_AUTHORITY = "TS500_7.6.2.1_STABILITY_LOAD_BASIS"
SWAY_STABILITY_AUTHORITY = "TS500_7.6.2.1_STABILITY_INDEX"


class StoryStabilityIndexError(ValueError):
    """Raised when the TS500 stability-index input contract is malformed."""


@dataclass(frozen=True, slots=True)
class StoryStabilityIndexEvidence:
    story: str
    direction: str
    load_basis: str
    story_height_mm: float
    relative_story_displacement_mm: float
    story_shear_n: float
    sum_column_axial_design_force_n: float
    input_authority: str
    load_basis_authority: str
    stiffness_basis: str
    stiffness_basis_authority: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StoryStabilityIndexResult:
    story: str
    direction: str
    load_basis: str
    phi: float
    limit: float
    status: str
    source_refs: tuple[str, ...]
    authority: str = SWAY_STABILITY_AUTHORITY

    @property
    def proves_sway_prevented(self) -> bool:
        return self.status == "PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"


@dataclass(frozen=True, slots=True)
class StorySwayStabilityResolution:
    story: str
    direction: str
    status: str
    governing_phi: float | None
    governing_load_basis: str | None
    load_results: tuple[StoryStabilityIndexResult, ...]
    missing_load_bases: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = SWAY_STABILITY_AUTHORITY

    @property
    def proves_sway_prevented(self) -> bool:
        return self.status == "PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise StoryStabilityIndexError(f"{label} must be a nonblank canonical string")
    return value


def _positive(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise StoryStabilityIndexError(f"{label} must be finite and > 0")
    return result


def _nonnegative(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise StoryStabilityIndexError(f"{label} must be finite and >= 0")
    return result


def evaluate_ts500_story_stability_index(
    evidence: StoryStabilityIndexEvidence,
) -> StoryStabilityIndexResult:
    """Evaluate TS500 Eq. 7.13 for one story/direction/load basis."""
    story = _text(evidence.story, "story")
    direction = _text(evidence.direction, "direction")
    if direction not in {"X", "Y"}:
        raise StoryStabilityIndexError("direction must be X or Y")
    load_basis = _text(evidence.load_basis, "load_basis")
    if load_basis not in REQUIRED_STABILITY_LOAD_BASES:
        raise StoryStabilityIndexError(f"unsupported TS500 stability load basis: {load_basis}")
    if evidence.input_authority != STORY_STABILITY_INPUT_AUTHORITY:
        raise StoryStabilityIndexError("story quantities are not promoted to TS500 stability-input authority")
    if evidence.load_basis_authority != LOAD_BASIS_AUTHORITY:
        raise StoryStabilityIndexError("load basis is not promoted to TS500 stability-load authority")
    if evidence.stiffness_basis != "UNCRACKED":
        raise StoryStabilityIndexError("TS500 Eq.7.13 stability route requires UNCRACKED section basis")
    if evidence.stiffness_basis_authority != UNCRACKED_SECTION_BASIS_AUTHORITY:
        raise StoryStabilityIndexError("uncracked section basis lacks TS500 authority")
    if not evidence.source_refs or len(set(evidence.source_refs)) != len(evidence.source_refs):
        raise StoryStabilityIndexError("source_refs must be nonempty and unique")
    refs = tuple(_text(ref, "source_ref") for ref in evidence.source_refs)

    height = _positive(evidence.story_height_mm, "story_height_mm")
    drift = _nonnegative(evidence.relative_story_displacement_mm, "relative_story_displacement_mm")
    shear = _positive(abs(float(evidence.story_shear_n)), "abs(story_shear_n)")
    axial = _positive(evidence.sum_column_axial_design_force_n, "sum_column_axial_design_force_n")

    phi = 1.5 * drift * axial / (shear * height)
    if not math.isfinite(phi) or phi < 0.0:
        raise StoryStabilityIndexError("computed phi must be finite and >= 0")
    status = (
        "PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"
        if phi <= TS500_STABILITY_LIMIT + 1e-12
        else "NOT_PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"
    )
    return StoryStabilityIndexResult(
        story=story,
        direction=direction,
        load_basis=load_basis,
        phi=phi,
        limit=TS500_STABILITY_LIMIT,
        status=status,
        source_refs=refs,
    )


def resolve_ts500_story_sway_from_stability_indices(
    evidences: tuple[StoryStabilityIndexEvidence, ...],
    *,
    story: str,
    direction: str,
) -> StorySwayStabilityResolution:
    """Use the unfavorable prescribed load basis to prove sway-prevented behavior.

    Both TS500 load bases must be present.  Missing evidence blocks this proof
    route rather than being interpreted as zero demand.
    """
    story_name = _text(story, "story")
    direction_name = _text(direction, "direction")
    if direction_name not in {"X", "Y"}:
        raise StoryStabilityIndexError("direction must be X or Y")

    selected = tuple(
        item for item in evidences
        if item.story == story_name and item.direction == direction_name
    )
    bases = tuple(item.load_basis for item in selected)
    if len(bases) != len(set(bases)):
        raise StoryStabilityIndexError("duplicate story/direction/load_basis stability evidence")
    missing = tuple(sorted(REQUIRED_STABILITY_LOAD_BASES - set(bases)))
    if missing:
        return StorySwayStabilityResolution(
            story=story_name,
            direction=direction_name,
            status="BLOCKED_TS500_SWAY_STABILITY_INDEX_EVIDENCE",
            governing_phi=None,
            governing_load_basis=None,
            load_results=(),
            missing_load_bases=missing,
            source_refs=("TS500 7.6.2.1 Eq.7.13 requires unfavorable prescribed load basis",),
        )

    results = tuple(evaluate_ts500_story_stability_index(item) for item in selected)
    governing = max(results, key=lambda item: (item.phi, item.load_basis))
    status = (
        "PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"
        if governing.proves_sway_prevented
        else "NOT_PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"
    )
    refs = tuple(dict.fromkeys(ref for result in results for ref in result.source_refs))
    return StorySwayStabilityResolution(
        story=story_name,
        direction=direction_name,
        status=status,
        governing_phi=governing.phi,
        governing_load_basis=governing.load_basis,
        load_results=results,
        missing_load_bases=(),
        source_refs=refs,
    )


__all__ = [
    "LOAD_BASIS_AUTHORITY",
    "REQUIRED_STABILITY_LOAD_BASES",
    "STORY_STABILITY_INPUT_AUTHORITY",
    "SWAY_STABILITY_AUTHORITY",
    "StoryStabilityIndexError",
    "StoryStabilityIndexEvidence",
    "StoryStabilityIndexResult",
    "StorySwayStabilityResolution",
    "TS500_LOAD_GQE",
    "TS500_LOAD_GQW",
    "TS500_STABILITY_LIMIT",
    "UNCRACKED_SECTION_BASIS_AUTHORITY",
    "evaluate_ts500_story_stability_index",
    "resolve_ts500_story_sway_from_stability_indices",
]
