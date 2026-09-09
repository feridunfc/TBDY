from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_between(path: Path, start_token: str, end_token: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.index(start_token)
    end = text.index(end_token, start)
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


# ---------------------------------------------------------------------------
# Existing Eq713 family: tightly subordinate Frame mechanics classifier/target.
# ---------------------------------------------------------------------------
eq713_mechanics = r'''"""Bounded Frame mechanics projection for the existing TS500 Eq.7.13 authority.

This module is a tightly subordinate part of the existing Eq713 analysis-basis
family.  It owns no ETABS acquisition or mutation.  Factual callers supply
member geometry/axis/end-condition evidence; this module classifies only the
narrow horizontal story-translation mechanism that can be proven from those
facts.  Unknown mode participation remains ``None`` and therefore fails closed
when passed to ``audit_frame_eq713_modes``.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
from typing import Mapping, Sequence

from .eq713_uncracked_analysis_state import (
    ContributorDisposition,
    FrameModeAuditDisposition,
    FrameStiffnessMode,
    _FRAME_SLOT,
)

FRAME_EQ713_MECHANICS_CONTRACT = "TS500_EQ713_FRAME_MECHANICS_CLASSIFICATION_V1"
FRAME_EQ713_TARGET_CONTRACT = "TS500_EQ713_FRAME_MODIFIER_TARGET_V1"
FRAME_HORIZONTAL_TRANSLATIONAL_RESPONSE_SCOPE_REF = (
    "TS500_EQ713_HORIZONTAL_STORY_TRANSLATION_RESPONSE_SCOPE"
)


class FrameEq713MechanicsError(RuntimeError):
    """Fail-closed error for malformed/unsupported Frame mechanics evidence."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FrameEq713MechanicsError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    refs = tuple(dict.fromkeys(_text(value, "source_ref") for value in values))
    if not refs:
        raise FrameEq713MechanicsError("source_refs must not be empty")
    return refs


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FrameEq713MechanicsError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise FrameEq713MechanicsError(f"{label} must be finite numeric")
    return result


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise FrameEq713MechanicsError(f"{label} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FrameEq713MechanicsError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise FrameEq713MechanicsError(f"{label} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class FrameMechanicsEvidence:
    component_uid: str
    member_role: str
    member_axis_vector: tuple[float, float, float]
    supported_end_condition: bool
    local_axis_explicit: bool
    local_axis_angle_degrees: float | None
    source_refs: tuple[str, ...]
    contract: str = FRAME_EQ713_MECHANICS_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_uid", _text(self.component_uid, "component_uid"))
        if self.member_role not in {"COLUMN", "BEAM"}:
            raise FrameEq713MechanicsError("member_role must be COLUMN or BEAM")
        vector = tuple(_number(value, f"member_axis_vector[{index}]") for index, value in enumerate(self.member_axis_vector))
        if len(vector) != 3 or math.sqrt(sum(value * value for value in vector)) <= 0.0:
            raise FrameEq713MechanicsError("member_axis_vector must be a nonzero three-vector")
        object.__setattr__(self, "member_axis_vector", vector)
        if type(self.supported_end_condition) is not bool:
            raise FrameEq713MechanicsError("supported_end_condition must be bool")
        if type(self.local_axis_explicit) is not bool:
            raise FrameEq713MechanicsError("local_axis_explicit must be bool")
        if self.local_axis_angle_degrees is not None:
            object.__setattr__(
                self,
                "local_axis_angle_degrees",
                _number(self.local_axis_angle_degrees, "local_axis_angle_degrees"),
            )
        object.__setattr__(self, "source_refs", _refs(self.source_refs))
        if self.contract != FRAME_EQ713_MECHANICS_CONTRACT:
            raise FrameEq713MechanicsError("Frame mechanics contract mismatch")

    @property
    def strictly_vertical(self) -> bool:
        dx, dy, dz = self.member_axis_vector
        scale = max(abs(dz), 1.0)
        return abs(dz) > 0.0 and abs(dx) <= 1e-9 * scale and abs(dy) <= 1e-9 * scale


@dataclass(frozen=True, slots=True)
class FrameModeParticipationEvidence:
    mode: FrameStiffnessMode
    participates: bool | None
    reason: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.mode, FrameStiffnessMode):
            raise TypeError("mode must be FrameStiffnessMode")
        if self.participates is not None and type(self.participates) is not bool:
            raise FrameEq713MechanicsError("participates must be bool or None")
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


@dataclass(frozen=True, slots=True)
class FrameModeParticipationClassification:
    component_uid: str
    mode_evidence: tuple[FrameModeParticipationEvidence, ...]
    source_refs: tuple[str, ...]
    contract: str = FRAME_EQ713_MECHANICS_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_uid", _text(self.component_uid, "component_uid"))
        rows = tuple(self.mode_evidence)
        if tuple(row.mode for row in rows) != tuple(FrameStiffnessMode):
            raise FrameEq713MechanicsError("classification must account for every Frame stiffness mode exactly once")
        object.__setattr__(self, "mode_evidence", rows)
        object.__setattr__(self, "source_refs", _refs(self.source_refs))
        if self.contract != FRAME_EQ713_MECHANICS_CONTRACT:
            raise FrameEq713MechanicsError("Frame participation classification contract mismatch")

    def as_mapping(self) -> Mapping[FrameStiffnessMode, bool | None]:
        return {row.mode: row.participates for row in self.mode_evidence}

    @property
    def resolved(self) -> bool:
        return all(row.participates is not None for row in self.mode_evidence)


def classify_frame_eq713_participation(
    evidence: FrameMechanicsEvidence,
) -> FrameModeParticipationClassification:
    """Classify only source-proven mode participation for the bounded slice.

    A straight vertical COLUMN has local-1 aligned with the vertical member axis.
    For the bounded horizontal story-translation response, the two transverse
    shear/flexure families are the translational resistance mechanisms; local-1
    axial deformation and local-1 torsional rotation are orthogonal/non-
    translational mechanisms for this slice.  A BEAM/nonvertical member needs a
    response-direction-to-local-axis projection not present in this bounded
    evidence and therefore remains unresolved.
    """
    if not isinstance(evidence, FrameMechanicsEvidence):
        raise TypeError("evidence must be FrameMechanicsEvidence")
    refs = _refs((*evidence.source_refs, FRAME_HORIZONTAL_TRANSLATIONAL_RESPONSE_SCOPE_REF))

    if not evidence.supported_end_condition:
        reason = "Frame end condition is outside the supported no-release/no-partial-fixity slice"
        rows = tuple(FrameModeParticipationEvidence(mode, None, reason, refs) for mode in FrameStiffnessMode)
        return FrameModeParticipationClassification(evidence.component_uid, rows, refs)

    if evidence.member_role != "COLUMN" or not evidence.strictly_vertical:
        reason = (
            "Frame local-mode participation requires a response-direction/local-axis projection; "
            "the bounded mechanics evidence resolves only strictly vertical COLUMN members"
        )
        rows = tuple(FrameModeParticipationEvidence(mode, None, reason, refs) for mode in FrameStiffnessMode)
        return FrameModeParticipationClassification(evidence.component_uid, rows, refs)

    resolved = {
        FrameStiffnessMode.AXIAL: (
            False,
            "strictly vertical local-1 axial deformation is orthogonal to the bounded horizontal story-translation mechanism",
        ),
        FrameStiffnessMode.SHEAR_2: (
            True,
            "local-2 transverse shear is a horizontal translation resistance mechanism for a strictly vertical Frame member",
        ),
        FrameStiffnessMode.SHEAR_3: (
            True,
            "local-3 transverse shear is a horizontal translation resistance mechanism for a strictly vertical Frame member",
        ),
        FrameStiffnessMode.TORSION: (
            False,
            "local-1 torsional rotation is not a translational stiffness mode in the bounded horizontal story-translation mechanism",
        ),
        FrameStiffnessMode.FLEXURE_2: (
            True,
            "local-2 flexural stiffness participates in horizontal translation resistance for a strictly vertical Frame member",
        ),
        FrameStiffnessMode.FLEXURE_3: (
            True,
            "local-3 flexural stiffness participates in horizontal translation resistance for a strictly vertical Frame member",
        ),
    }
    rows = tuple(
        FrameModeParticipationEvidence(mode, resolved[mode][0], resolved[mode][1], refs)
        for mode in FrameStiffnessMode
    )
    return FrameModeParticipationClassification(evidence.component_uid, rows, refs)


@dataclass(frozen=True, slots=True)
class FrameEq713ModifierTarget:
    component_uid: str
    current_modifiers: tuple[Decimal, ...]
    target_modifiers: tuple[Decimal, ...]
    targeted_modes: tuple[FrameStiffnessMode, ...]
    preserved_modes: tuple[FrameStiffnessMode, ...]
    source_refs: tuple[str, ...]
    contract: str = FRAME_EQ713_TARGET_CONTRACT


def build_frame_eq713_modifier_target(
    *,
    current_modifiers: Sequence[object],
    disposition: FrameModeAuditDisposition,
) -> FrameEq713ModifierTarget:
    """Normalize TARGETED_UNCRACKED slots only; preserve every other slot.

    Mass and weight slots are never Eq713 stiffness targets and are always
    copied byte-for-value from the current observed vector representation.
    """
    if not isinstance(disposition, FrameModeAuditDisposition):
        raise TypeError("disposition must be FrameModeAuditDisposition")
    current = tuple(_decimal(value, f"current_modifiers[{index}]") for index, value in enumerate(current_modifiers))
    if len(current) != 8:
        raise FrameEq713MechanicsError("Frame modifier vector must contain exactly 8 values")
    by_mode = {row.mode: row for row in disposition.mode_dispositions}
    if set(by_mode) != set(FrameStiffnessMode) or len(by_mode) != len(disposition.mode_dispositions):
        raise FrameEq713MechanicsError("Frame disposition must account for every mode exactly once")

    target = list(current)
    targeted: list[FrameStiffnessMode] = []
    preserved: list[FrameStiffnessMode] = []
    for mode in FrameStiffnessMode:
        row = by_mode[mode]
        if row.disposition is ContributorDisposition.TARGETED_UNCRACKED:
            target[_FRAME_SLOT[mode]] = Decimal("1")
            targeted.append(mode)
        else:
            preserved.append(mode)
    # slots 6/7 (mass/weight) are intentionally untouched.
    return FrameEq713ModifierTarget(
        component_uid=disposition.component_uid,
        current_modifiers=current,
        target_modifiers=tuple(target),
        targeted_modes=tuple(targeted),
        preserved_modes=tuple(preserved),
        source_refs=_refs((*disposition.source_refs, FRAME_EQ713_TARGET_CONTRACT)),
    )


__all__ = [
    "FRAME_EQ713_MECHANICS_CONTRACT",
    "FRAME_EQ713_TARGET_CONTRACT",
    "FRAME_HORIZONTAL_TRANSLATIONAL_RESPONSE_SCOPE_REF",
    "FrameEq713MechanicsError",
    "FrameEq713ModifierTarget",
    "FrameMechanicsEvidence",
    "FrameModeParticipationClassification",
    "FrameModeParticipationEvidence",
    "build_frame_eq713_modifier_target",
    "classify_frame_eq713_participation",
]
'''
(ROOT / "tbdy_engine/analysis_basis/eq713_frame_mechanics.py").write_text(eq713_mechanics, encoding="utf-8")


# ---------------------------------------------------------------------------
# PUBLIC-A5 composer: remove application participation/exclusion authority and
# derive Frame targets from existing Eq713 dispositions.
# ---------------------------------------------------------------------------
composer_path = ROOT / "tbdy_engine/application/column_public_a5.py"
composer = composer_path.read_text(encoding="utf-8")
composer = composer.replace(
'''from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (\n    AreaCategory,\n    AreaFormulation,\n    AreaGrossBasePropertyEvidence,\n    Eq713PopulationDisposition,\n    FrameStiffnessMode,\n    WallRole,\n    audit_frame_eq713_modes,\n    build_area_eq713_target,\n    build_concrete_uncracked_material_basis,\n)\n''',
'''from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (\n    AreaCategory,\n    AreaFormulation,\n    AreaGrossBasePropertyEvidence,\n    Eq713PopulationDisposition,\n    WallRole,\n    audit_frame_eq713_modes,\n    build_area_eq713_target,\n    build_concrete_uncracked_material_basis,\n)\nfrom tbdy_engine.analysis_basis.eq713_frame_mechanics import (\n    FrameMechanicsEvidence,\n    build_frame_eq713_modifier_target,\n    classify_frame_eq713_participation,\n)\n''')
if "classify_frame_eq713_participation" not in composer:
    raise RuntimeError("composer import patch failed")
composer_path.write_text(composer, encoding="utf-8")

replace_between(
    composer_path,
    "def _frame_mechanics_ref(",
    "\ndef _material_bases",
    r'''def _frame_mechanics_evidence(
    row: FrameEq713FactualFact,
    topology: StrictColumnTopologyBundle,
) -> FrameMechanicsEvidence:
    """Bind factual topology/axis/end-condition mechanics for Eq713 authority."""
    if row.member_role == "COLUMN":
        matches = tuple(item for item in topology.columns if item.unique_name == row.frame_name)
        if len(matches) != 1:
            raise PublicA5CompositionError(
                BLOCKER_A3_EQ713_POPULATION,
                f"COLUMN Frame {row.frame_name!r} is absent/ambiguous in strict topology",
            )
        item = matches[0]
        if (
            item.width_t2_m <= 0.0
            or item.depth_t3_m <= 0.0
            or item.object_length_m <= 0.0
            or item.coordinate_length_m <= 0.0
        ):
            raise PublicA5CompositionError(
                BLOCKER_A3_EQ713_POPULATION,
                f"COLUMN Frame {row.frame_name!r} has non-positive strict geometry",
            )
        vector = tuple(
            float(item.top_coord_m[index] - item.bottom_coord_m[index])
            for index in range(3)
        )
        mechanics_ref = (
            f"{_FRAME_MECHANICS_REF_PREFIX}:COLUMN:{row.frame_name}:"
            f"LOCAL_AXIS_EXPLICIT={item.local_axis_explicit}:ANGLE={item.local_axis_angle_deg}"
        )
        return FrameMechanicsEvidence(
            component_uid=row.frame_name,
            member_role=row.member_role,
            member_axis_vector=vector,
            supported_end_condition=row.supported_end_condition,
            local_axis_explicit=bool(item.local_axis_explicit),
            local_axis_angle_degrees=item.local_axis_angle_deg,
            source_refs=(*row.source_refs, mechanics_ref),
        )

    beams = {}
    for column in topology.columns:
        for beam in (*column.beams_at_bottom, *column.beams_at_top):
            beams.setdefault(beam.beam_unique_name, beam)
    beam = beams.get(row.frame_name)
    if beam is None or not beam.is_supported_rc_beam:
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            f"BEAM Frame {row.frame_name!r} lacks supported strict-topology mechanics",
        )
    if (
        beam.width_t2_m is None
        or beam.depth_t3_m is None
        or beam.width_t2_m <= 0.0
        or beam.depth_t3_m <= 0.0
        or not any(abs(value) > 0.0 for value in beam.vector_from_joint_m)
    ):
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            f"BEAM Frame {row.frame_name!r} has unresolved/non-positive strict geometry",
        )
    mechanics_ref = f"{_FRAME_MECHANICS_REF_PREFIX}:BEAM:{row.frame_name}:CONNECTED_3D_FRAME"
    return FrameMechanicsEvidence(
        component_uid=row.frame_name,
        member_role=row.member_role,
        member_axis_vector=tuple(float(value) for value in beam.vector_from_joint_m),
        supported_end_condition=row.supported_end_condition,
        local_axis_explicit=False,
        local_axis_angle_degrees=None,
        source_refs=(*row.source_refs, mechanics_ref),
    )

''')

composer = composer_path.read_text(encoding="utf-8")
composer = composer.replace(
'''    # The accepted Area provider carries exact simple-property thickness and no\n    # separate object-thickness authority.  COLUMN-R1 therefore retains that\n    # reviewed simple-property slice; no new thickness-composition rule is made\n    # here.  Out-of-plane plate/transverse response is positively excluded from\n    # the accepted in-plane Eq7.13 Delta_i response scope and is still disposed\n    # by the existing Eq713 authority.\n''',
'''    # The accepted Area provider carries exact simple-property thickness and no\n    # separate object-thickness authority.  COLUMN-R1 retains that factual slice.\n    # Application scope intent is not mechanical exclusion evidence: plate and\n    # transverse-shear participation stay unresolved here.  The existing Eq713\n    # authority alone may prove them not applicable (for example MEMBRANE) or\n    # fail closed when a SHELL_THICK mechanism is not independently classified.\n''')
composer = composer.replace("        plate_participation=False,\n        transverse_shear_participation=False,\n", "        plate_participation=None,\n        transverse_shear_participation=None,\n")
if "plate_participation=False" in composer or "transverse_shear_participation=False" in composer:
    raise RuntimeError("Area exclusion patch failed")
composer_path.write_text(composer, encoding="utf-8")

replace_between(
    composer_path,
    "def _qualify_a3(",
    "\ndef _frame_target",
    r'''def _qualify_a3(
    *,
    frame_population: FrameEq713FactualPopulation,
    area_population: AreaContributorPopulation,
    topology: StrictColumnTopologyBundle,
):
    material_bases = _material_bases(frame_population)
    frame_rows = []
    for fact in frame_population.rows:
        mechanics = _frame_mechanics_evidence(fact, topology)
        classification = classify_frame_eq713_participation(mechanics)
        basis = material_bases[fact.base_fact.material_name]
        frame_rows.append(
            audit_frame_eq713_modes(
                component_uid=fact.frame_name,
                property_modifiers=fact.property_modifiers.modifiers.as_tuple(),
                object_modifiers=fact.object_modifiers.modifiers.as_tuple(),
                participation=classification.as_mapping(),
                material_basis=basis,
                source_refs=(*fact.source_refs, *classification.source_refs),
            )
        )

    area_evidence = tuple(
        _area_evidence(fact, material_bases)
        for fact in area_population.rows
    )
    area_rows = tuple(build_area_eq713_target(fact) for fact in area_evidence)
    whole = Eq713PopulationDisposition(
        area_rows=area_rows,
        frame_rows=tuple(frame_rows),
    )
    if not whole.positive:
        blocked = tuple(
            reason
            for row in (*whole.area_rows, *whole.frame_rows)
            for reason in row.blocked_reasons
        )
        raise PublicA5CompositionError(
            BLOCKER_A3_EQ713_POPULATION,
            "Eq713 whole-system population did not qualify: " + "; ".join(dict.fromkeys(blocked)),
        )
    return whole, area_evidence

''')

replace_between(
    composer_path,
    "def _frame_target(",
    "\ndef _flatten_combo",
    r'''def _b4b_targets(frame_population, area_population, frame_rows, area_rows):
    targets = []
    frame_dispositions = {row.component_uid: row for row in frame_rows}
    if len(frame_dispositions) != len(tuple(frame_rows)):
        raise PublicA5CompositionError(BLOCKER_A4_B4B, "duplicate Frame Eq713 disposition identity")

    property_targets: dict[str, FrameModifierVector] = {}
    for fact in frame_population.rows:
        disposition = frame_dispositions.get(fact.frame_name)
        if disposition is None:
            raise PublicA5CompositionError(
                BLOCKER_A4_B4B,
                f"Frame {fact.frame_name!r} has no accepted Eq713 mode disposition",
            )
        section_projection = build_frame_eq713_modifier_target(
            current_modifiers=fact.property_modifiers.modifiers.as_tuple(),
            disposition=disposition,
        )
        section_target = FrameModifierVector.from_sequence(
            tuple(float(value) for value in section_projection.target_modifiers)
        )
        previous = property_targets.get(fact.base_fact.assigned_section_name)
        if previous is not None and previous.as_tuple() != section_target.as_tuple():
            raise PublicA5CompositionError(
                BLOCKER_A4_B4B,
                f"shared Frame section {fact.base_fact.assigned_section_name!r} has contradictory Eq713 target",
            )
        property_targets[fact.base_fact.assigned_section_name] = section_target

        object_projection = build_frame_eq713_modifier_target(
            current_modifiers=fact.object_modifiers.modifiers.as_tuple(),
            disposition=disposition,
        )
        targets.append(
            FrameModifierTargetRequest(
                surface=FrameModifierSurface.FRAME_OBJECT,
                target_name=fact.frame_name,
                modifiers=FrameModifierVector.from_sequence(
                    tuple(float(value) for value in object_projection.target_modifiers)
                ),
            )
        )
    for section, vector in property_targets.items():
        targets.append(
            FrameModifierTargetRequest(
                surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
                target_name=section,
                modifiers=vector,
            )
        )

    area_by_name = {row.area_name: row for row in area_population.rows}
    area_property_targets: dict[str, AreaModifierVector] = {}
    for disposition in area_rows:
        if disposition.target_property_modifiers is None:
            continue
        factual = area_by_name[disposition.area_name]
        if factual.property_state is None:
            raise PublicA5CompositionError(BLOCKER_A4_B4B, "Area target lost factual property identity")
        vector = AreaModifierVector.from_sequence(disposition.target_property_modifiers)
        property_name = factual.property_name
        previous = area_property_targets.get(property_name)
        if previous is not None and previous.as_tuple() != vector.as_tuple():
            raise PublicA5CompositionError(
                BLOCKER_A4_B4B,
                f"shared Area property {property_name!r} has contradictory Eq713 target",
            )
        area_property_targets[property_name] = vector
    for property_name, vector in area_property_targets.items():
        targets.append(
            AreaModifierTargetRequest(
                surface=AreaModifierSurface.AREA_PROPERTY,
                target_name=property_name,
                modifiers=vector,
            )
        )
    if not targets:
        raise PublicA5CompositionError(BLOCKER_A4_B4B, "Eq713 positive population produced no B4B target")
    return tuple(targets)

''')

composer = composer_path.read_text(encoding="utf-8")
old_call = "targets = _b4b_targets(frame_pre, area_pre, a3.area_rows)"
new_call = "targets = _b4b_targets(frame_pre, area_pre, a3.frame_rows, a3.area_rows)"
if old_call not in composer:
    raise RuntimeError("B4B target call patch anchor missing")
composer = composer.replace(old_call, new_call)
if "participation = {mode: True" in composer or "def _frame_target(" in composer:
    raise RuntimeError("application-owned Frame authority still present")
composer_path.write_text(composer, encoding="utf-8")


# ---------------------------------------------------------------------------
# Architecture guard: allow the already-canonical B5 RunAnalysis owner only.
# ---------------------------------------------------------------------------
arch_path = ROOT / "tests/architecture/test_g1_arch_drift_guards.py"
arch = arch_path.read_text(encoding="utf-8")
old_guard = '''def test_supported_product_has_zero_uncontrolled_mutation_calls() -> None:\n    index, _ = graph()\n    violations: list[str] = []\n    for module in closure(*SUPPORTED_ROOTS):\n        path = index.get(module)\n        if path:\n            violations.extend(f"{module}|{name}" for name in call_names(path) if name.rsplit(".", 1)[-1] in MUTATION)\n    assert violations == []\n'''
new_guard = '''def test_supported_product_has_zero_uncontrolled_mutation_calls() -> None:\n    index, _ = graph()\n    violations: list[str] = []\n    for module in closure(*SUPPORTED_ROOTS):\n        path = index.get(module)\n        if not path:\n            continue\n        rel = path.relative_to(ROOT).as_posix()\n        for name in call_names(path):\n            final = name.rsplit(".", 1)[-1]\n            if final in MUTATION and (rel, final) not in CANONICAL_MUTATION_CALLS:\n                violations.append(f"{module}|{name}")\n    assert violations == []\n'''
if old_guard not in arch:
    raise RuntimeError("architecture guard patch anchor missing")
arch_path.write_text(arch.replace(old_guard, new_guard), encoding="utf-8")


# ---------------------------------------------------------------------------
# Analysis-basis tests: authority placement + unknown fail-closed + target.
# ---------------------------------------------------------------------------
mechanics_test = r'''from tbdy_engine.analysis_basis.eq713_frame_mechanics import (
    FrameMechanicsEvidence,
    build_frame_eq713_modifier_target,
    classify_frame_eq713_participation,
)
from tbdy_engine.analysis_basis.eq713_uncracked_analysis_state import (
    ContributorDisposition,
    FrameStiffnessMode,
    audit_frame_eq713_modes,
    build_concrete_uncracked_material_basis,
)


def _material():
    return build_concrete_uncracked_material_basis(
        material_name="C35",
        fck_mpa=35,
        factual_ec_mpa=33000,
        factual_gc_mpa=13200,
        source_refs=("material:C35",),
    )


def _vertical():
    return FrameMechanicsEvidence(
        component_uid="C1",
        member_role="COLUMN",
        member_axis_vector=(0.0, 0.0, 3.0),
        supported_end_condition=True,
        local_axis_explicit=True,
        local_axis_angle_degrees=0.0,
        source_refs=("strict-topology:C1", "release:C1:none"),
    )


def test_vertical_column_classifier_is_mode_specific_not_all_true():
    result = classify_frame_eq713_participation(_vertical())
    mapping = result.as_mapping()
    assert mapping == {
        FrameStiffnessMode.AXIAL: False,
        FrameStiffnessMode.SHEAR_2: True,
        FrameStiffnessMode.SHEAR_3: True,
        FrameStiffnessMode.TORSION: False,
        FrameStiffnessMode.FLEXURE_2: True,
        FrameStiffnessMode.FLEXURE_3: True,
    }
    assert result.resolved is True
    assert all(row.reason for row in result.mode_evidence)


def test_nonvertical_or_beam_mechanics_remain_unknown_and_audit_fails_closed():
    evidence = FrameMechanicsEvidence(
        component_uid="B1",
        member_role="BEAM",
        member_axis_vector=(3.0, 0.0, 0.0),
        supported_end_condition=True,
        local_axis_explicit=False,
        local_axis_angle_degrees=None,
        source_refs=("strict-topology:B1", "release:B1:none"),
    )
    classification = classify_frame_eq713_participation(evidence)
    assert all(value is None for value in classification.as_mapping().values())
    audit = audit_frame_eq713_modes(
        component_uid="B1",
        property_modifiers=(0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.0),
        object_modifiers=(1.0,) * 8,
        participation=classification.as_mapping(),
        material_basis=_material(),
        source_refs=classification.source_refs,
    )
    assert audit.qualified is False
    assert all(row.disposition is ContributorDisposition.BLOCKED_UNSUPPORTED for row in audit.mode_dispositions)


def test_target_normalizes_only_targeted_modes_and_preserves_mass_weight():
    classification = classify_frame_eq713_participation(_vertical())
    audit = audit_frame_eq713_modes(
        component_uid="C1",
        property_modifiers=(0.41, 0.52, 0.63, 0.74, 0.85, 0.96, 1.2, 1.3),
        object_modifiers=(1.0,) * 8,
        participation=classification.as_mapping(),
        material_basis=_material(),
        source_refs=classification.source_refs,
    )
    target = build_frame_eq713_modifier_target(
        current_modifiers=(0.41, 0.52, 0.63, 0.74, 0.85, 0.96, 1.2, 1.3),
        disposition=audit,
    )
    assert tuple(float(value) for value in target.target_modifiers) == (
        0.41, 1.0, 1.0, 0.74, 1.0, 1.0, 1.2, 1.3
    )
    assert target.preserved_modes == (FrameStiffnessMode.AXIAL, FrameStiffnessMode.TORSION)
'''
(ROOT / "tests/analysis_basis/test_eq713_frame_mechanics.py").write_text(mechanics_test, encoding="utf-8")


# ---------------------------------------------------------------------------
# Mandatory PUBLIC execute_project A5 product-path tests.
# ---------------------------------------------------------------------------
product_test = r'''from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_public_a5 as a5
import tbdy_engine.application.project_execution as project_execution
import tbdy_engine.analysis_basis.frame_gross_flexural_basis as continuity
import tbdy_engine.integration.etabs_analysis_execution as b5
import tbdy_engine.integration.etabs_analysis_state_mutation as b4b
import tbdy_engine.integration.etabs_analysis_state_revalidation as revalidation
from tbdy_engine.application.column_execution import BLOCKER_LIVE_FND2_INPUT_LINEAGE
from tbdy_engine.application.contracts import ColumnExecutionRequest, ProjectExecutionRequest
from tbdy_engine.design.columns.slenderness import SWAY_PREVENTED
from tbdy_engine.design.columns.slenderness_basis import (
    FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
    MOMENT_RATIO_AUTHORITY,
    REGULATORY_FREE_LENGTH_AUTHORITY,
    SWAY_CLASSIFICATION_AUTHORITY,
    ColumnSlendernessAxisEvidence,
    ColumnSlendernessEvidence,
)
from tbdy_engine.etabs.oapi.analysis_execution import (
    CaseStatusPopulationFact,
    DefinedAnalysisCasePopulationFact,
    DeleteAnalysisResultsFact,
    EtabsRuntimeVersionFact,
    LoadCaseTypeRuntimeFact,
    RunAnalysisFact,
    RunCaseFlagSetFact,
    RunCaseFlagSnapshotFact,
)
from tbdy_engine.etabs.oapi.area_contributors import AreaDesignOrientation
from tbdy_engine.etabs.oapi.area_modifiers import AreaModifierVector
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierReadFact,
    FrameModifierSetFact,
    FrameModifierSurface,
    FrameModifierVector,
)
from tbdy_engine.etabs.safety import AnalysisReadiness
from tbdy_engine.integration.etabs_scratch_lifecycle import PhysicalFileSnapshot
from tbdy_engine.providers.etabs_area_contributor_provider import AreaPropertyFamily
from tbdy_engine.providers.etabs_column_force_result_population_provider import (
    ColumnForcePopulationExpectation,
    ColumnForceResultPopulationFact,
)


COMPONENT = "Story1:C1:1"


class _FakeSession:
    pass


@dataclass(frozen=True)
class _SourceIdentity:
    source_model_ref: str = "source-model-ref:public-a5"
    normalized_model_reference: str = r"C:\tmp\public-a5-source.edb"


class _FakeContext:
    def __init__(self, session):
        self.verified_session = session
        self.source_model_identity = _SourceIdentity()
        self.acquisition_context_ref = "acquisition-context:public-a5"
        self.session_provenance_ref = "session-provenance:public-a5"
        self.model_fingerprint = "model-fingerprint:public-a5"
        self.evidence_epoch_id = "evidence-epoch:public-a5"


class _FakeOwnedScratch:
    def __init__(self, source_identity, snapshot):
        self.source_model_identity = source_identity
        self.scratch_path = r"C:\tmp\public-a5-scratch.edb"
        self.active_model_path = self.scratch_path
        self.ownership_proof_ref = "owned-scratch:public-a5"
        self.source_pre = snapshot
        self.source_post = snapshot


@dataclass(frozen=True)
class _Column:
    component_id: str = COMPONENT
    unique_name: str = "1"
    column_label: str = "C1"
    story: str = "Story1"
    section: str = "C50x80"
    width_t2_m: float = 0.5
    depth_t3_m: float = 0.8
    object_length_m: float = 3.0
    coordinate_length_m: float = 3.0
    bottom_coord_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    top_coord_m: tuple[float, float, float] = (0.0, 0.0, 3.0)
    local_axis_angle_deg: float | None = 0.0
    local_axis_explicit: bool = True
    beams_at_bottom: tuple[object, ...] = ()
    beams_at_top: tuple[object, ...] = ()

    def as_dict(self):
        return {
            "component_id": self.component_id,
            "unique_name": self.unique_name,
            "section": self.section,
            "bottom_coord_m": self.bottom_coord_m,
            "top_coord_m": self.top_coord_m,
            "local_axis_angle_deg": self.local_axis_angle_deg,
            "local_axis_explicit": self.local_axis_explicit,
        }


@dataclass(frozen=True)
class _BaseFact:
    component_unique_name: str
    assigned_section_name: str
    material_name: str
    section_semantics: str
    t2_mm: Decimal
    t3_mm: Decimal
    concrete_fck_mpa: Decimal
    etabs_ec_mpa: Decimal
    source_model_ref: str
    ownership_proof_ref: str
    semantic_state_ref: str
    evidence_ref: str
    capture_event_ref: str
    source_refs: tuple[str, ...]


class _Topology:
    def __init__(self, column):
        self.columns = (column,)


def _force_rows(case_name="EX"):
    return (
        {
            "Story": "Story1", "Column": "C1", "UniqueName": "1",
            "OutputCase": case_name, "CaseType": "LinStatic", "StepType": "",
            "StepNumber": None, "Station": 0.0, "Element": "1", "ElemStation": 0.0,
            "P": -1000.0, "V2": 0.0, "V3": 0.0, "T": 0.0,
            "M2": 100.0, "M3": 80.0,
        },
        {
            "Story": "Story1", "Column": "C1", "UniqueName": "1",
            "OutputCase": case_name, "CaseType": "LinStatic", "StepType": "",
            "StepNumber": None, "Station": 3.0, "Element": "1", "ElemStation": 3.0,
            "P": -900.0, "V2": 0.0, "V3": 0.0, "T": 0.0,
            "M2": 70.0, "M3": 60.0,
        },
    )


def _slenderness():
    def axis(name, dimension):
        return ColumnSlendernessAxisEvidence(
            axis=name,
            section_dimension_mm=dimension,
            factual_clear_length_candidate_mm=3000.0,
            factual_clear_length_source_ref=f"topology:{name}:clear",
            factual_clear_length_authority=FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
            regulatory_free_length_ln_mm=3000.0,
            regulatory_free_length_source_ref=f"reviewed:{name}:ln",
            regulatory_free_length_authority=REGULATORY_FREE_LENGTH_AUTHORITY,
            sway_classification=SWAY_PREVENTED,
            sway_source_ref=f"reviewed:{name}:sway",
            sway_authority=SWAY_CLASSIFICATION_AUTHORITY,
            effective_length_factor_k=None,
            effective_length_source_ref=None,
            effective_length_authority=None,
            moment_ratio_m1_over_m2=0.0,
            moment_ratio_source_ref=f"reviewed:{name}:ratio",
            moment_ratio_authority=MOMENT_RATIO_AUTHORITY,
            allow_conservative_braced_ratio=False,
        )
    return ColumnSlendernessEvidence(
        component_id=COMPONENT,
        m2=axis("M2", 800.0),
        m3=axis("M3", 500.0),
        source_refs=("slenderness:public-a5",),
    )


@pytest.fixture
def product_harness(monkeypatch):
    session = _FakeSession()
    context = _FakeContext(session)
    snapshot = PhysicalFileSnapshot(
        canonical_absolute_path="/tmp/public-a5-source.edb",
        exists=True,
        file_size_bytes=100,
        sha256_content_digest="a" * 64,
        mtime_ns=1,
    )
    owned = _FakeOwnedScratch(context.source_model_identity, snapshot)
    column = _Column()
    topology = _Topology(column)

    base = _BaseFact(
        component_unique_name="1",
        assigned_section_name="C50x80",
        material_name="C35",
        section_semantics="PRISMATIC_RECTANGULAR_RC_FRAME",
        t2_mm=Decimal("500"),
        t3_mm=Decimal("800"),
        concrete_fck_mpa=Decimal("35"),
        etabs_ec_mpa=Decimal("33000"),
        source_model_ref=context.source_model_identity.source_model_ref,
        ownership_proof_ref=owned.ownership_proof_ref,
        semantic_state_ref="frame-semantic:1",
        evidence_ref="frame-base-pre:1",
        capture_event_ref="frame-capture:pre",
        source_refs=("frame-base-row:1",),
    )
    post_base = _BaseFact(**{
        **base.__dict__,
        "evidence_ref": "frame-base-post:1",
        "capture_event_ref": "frame-capture:post",
    })

    section_initial = FrameModifierVector.from_sequence((0.41, 0.52, 0.63, 0.74, 0.85, 0.96, 1.2, 1.3))
    object_initial = FrameModifierVector.from_sequence((0.31, 0.42, 0.53, 0.64, 0.75, 0.86, 0.9, 0.8))
    modifier_values = {
        (FrameModifierSurface.FRAME_SECTION_PROPERTY.value, "C50x80"): section_initial,
        (FrameModifierSurface.FRAME_OBJECT.value, "1"): object_initial,
    }
    property_fact = FrameModifierReadFact(
        surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
        target_name="C50x80",
        modifiers=section_initial,
        return_code=0,
    )
    object_fact = FrameModifierReadFact(
        surface=FrameModifierSurface.FRAME_OBJECT,
        target_name="1",
        modifiers=object_initial,
        return_code=0,
    )
    frame_fact = SimpleNamespace(
        frame_name="1",
        member_role="COLUMN",
        base_fact=base,
        property_modifiers=property_fact,
        object_modifiers=object_fact,
        releases=SimpleNamespace(evidence_ref="release:1"),
        isotropic_material=SimpleNamespace(evidence_ref="isotropic:C35"),
        factual_ec_mpa=Decimal("33000"),
        factual_gc_mpa=Decimal("13200"),
        source_refs=(
            "frame-fact:1", base.evidence_ref, property_fact.evidence_ref,
            object_fact.evidence_ref, "release:1", "isotropic:C35",
        ),
        supported_end_condition=True,
    )
    frame_population = SimpleNamespace(
        expected_frame_names=("1",),
        rows=(frame_fact,),
        source_refs=("frame-population:1", base.evidence_ref),
    )
    area_population = SimpleNamespace(
        expected_area_names=(),
        rows=(),
        source_refs=("area-population:empty",),
    )

    # Public root + trusted context boundary.
    monkeypatch.setattr(project_execution, "EtabsVerifiedSession", _FakeSession)
    monkeypatch.setattr(project_execution, "create_trusted_live_acquisition_context", lambda verified_session: context)
    monkeypatch.setattr(a5, "TrustedLiveAcquisitionContext", _FakeContext)
    monkeypatch.setattr(a5, "create_owned_scratch_context", lambda _context: owned)
    monkeypatch.setattr(a5, "capture_etabs_strict_column_topology_from_session", lambda _session: topology)
    monkeypatch.setattr(a5, "capture_frame_eq713_factual_population", lambda *_args, **_kwargs: frame_population)
    monkeypatch.setattr(a5, "capture_area_contributor_population_from_session", lambda *_args, **_kwargs: area_population)

    selection = SimpleNamespace(
        capture_complete=True,
        rows=(SimpleNamespace(combo_name="ULS"),),
        names=("ULS",),
        source_refs=("selected-combos:ULS",),
    )
    combo = SimpleNamespace(
        name="ULS",
        combo_type="LINEAR_ADD",
        constituents=(SimpleNamespace(cname_type="LOAD_CASE", name="EX", scale_factor=1.0),),
        nested_combos=(),
    )
    monkeypatch.setattr(a5, "acquire_actual_concrete_design_combo_selection_from_session", lambda *_args, **_kwargs: selection)
    monkeypatch.setattr(a5, "capture_etabs_combo_definitions_from_session", lambda *_args, **_kwargs: (combo,))

    monkeypatch.setattr(
        a5,
        "capture_etabs_column_endpoint_restraints_from_session",
        lambda *_args, **_kwargs: SimpleNamespace(
            bottom=SimpleNamespace(dofs=(True,) * 6),
            top=SimpleNamespace(dofs=(False,) * 6),
            bottom_source_ref="restraint:bottom",
            top_source_ref="restraint:top",
        ),
    )
    monkeypatch.setattr(a5, "resolve_ts500_column_free_length", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bounded test uses reviewed slenderness evidence")))
    monkeypatch.setattr(a5, "build_factual_slenderness_evidence_from_topology", lambda *_args, **_kwargs: _slenderness())
    monkeypatch.setattr(a5, "build_assigned_rc_frame_bending_modifier_evidence", lambda *_args, **_kwargs: ())

    # B4B exact mixed mutation with mocked OAPI boundary.
    for module in (b4b, revalidation, b5):
        monkeypatch.setattr(module, "TrustedLiveAcquisitionContext", _FakeContext)
        monkeypatch.setattr(module, "OwnedScratchContext", _FakeOwnedScratch)

    def identity(_session, *, timeout_seconds=30.0):
        return SimpleNamespace(model_full_path=owned.scratch_path, model_locked=False)

    monkeypatch.setattr(b4b, "reread_verified_session_identity", identity)
    monkeypatch.setattr(b4b, "capture_physical_file_snapshot", lambda _path: snapshot)
    monkeypatch.setattr(revalidation, "reread_verified_session_identity", identity)
    monkeypatch.setattr(revalidation, "capture_physical_file_snapshot", lambda _path: snapshot)
    monkeypatch.setattr(b5, "reread_verified_session_identity", identity)
    monkeypatch.setattr(b5, "capture_physical_file_snapshot", lambda _path: snapshot)

    mutation_calls = []

    def get_frame(_session, *, surface, target_name, timeout_seconds=30.0):
        vector = modifier_values[(surface.value, target_name)]
        return FrameModifierReadFact(surface=surface, target_name=target_name, modifiers=vector, return_code=0)

    def set_frame(_session, *, surface, target_name, modifiers, timeout_seconds=30.0):
        mutation_calls.append((surface.value, target_name, modifiers.as_tuple()))
        modifier_values[(surface.value, target_name)] = modifiers
        return FrameModifierSetFact(surface=surface, target_name=target_name, requested_modifiers=modifiers, return_code=0)

    monkeypatch.setattr(b4b, "get_frame_modifiers_from_session", get_frame)
    monkeypatch.setattr(b4b, "set_frame_modifiers_from_session", set_frame)

    # B5 canonical execution: one case, one exact RunAnalysis call.
    runtime = {
        "run_flags": {"EX": False},
        "statuses": {"EX": 4},
        "run_calls": 0,
        "delete_calls": 0,
    }
    monkeypatch.setattr(
        b5,
        "get_defined_analysis_cases_from_session",
        lambda *_args, **_kwargs: DefinedAnalysisCasePopulationFact(case_names=tuple(runtime["run_flags"]), return_code=0),
    )
    monkeypatch.setattr(
        b5,
        "get_etabs_runtime_version_fact_from_session",
        lambda *_args, **_kwargs: EtabsRuntimeVersionFact(program_version="23.2.0", internal_version_number=0.0, return_code=0),
    )
    monkeypatch.setattr(
        b5,
        "get_load_case_type_runtime_fact_from_session",
        lambda _session, *, case_name, timeout_seconds=30.0: LoadCaseTypeRuntimeFact(
            case_name=case_name,
            case_type=1,
            sub_type=0,
            design_type=1,
            design_type_option=0,
            runtime_auto_slot_value=0,
            return_code=0,
        ),
    )
    monkeypatch.setattr(
        b5,
        "get_run_case_flags_from_session",
        lambda *_args, **_kwargs: RunCaseFlagSnapshotFact(case_flags=tuple(runtime["run_flags"].items()), return_code=0),
    )

    def set_flag(_session, *, case_name, run, all_cases=False, timeout_seconds=30.0):
        if all_cases:
            for name in tuple(runtime["run_flags"]):
                runtime["run_flags"][name] = run
        else:
            runtime["run_flags"][case_name] = run
        return RunCaseFlagSetFact(case_name=case_name, run=run, all_cases=all_cases, return_code=0)

    def delete_results(_session, *, case_name, all_cases=False, timeout_seconds=30.0):
        runtime["delete_calls"] += 1
        if all_cases:
            for name in tuple(runtime["statuses"]):
                runtime["statuses"][name] = 1
        else:
            runtime["statuses"][case_name] = 1
        return DeleteAnalysisResultsFact(case_name=case_name, all_cases=all_cases, return_code=0)

    def run_analysis(_session, *, timeout_seconds=300.0):
        runtime["run_calls"] += 1
        for name, enabled in runtime["run_flags"].items():
            if enabled:
                runtime["statuses"][name] = 4
        return RunAnalysisFact(return_code=0)

    monkeypatch.setattr(b5, "set_run_case_flag_from_session", set_flag)
    monkeypatch.setattr(b5, "delete_analysis_results_from_session", delete_results)
    monkeypatch.setattr(
        b5,
        "get_case_status_population_from_session",
        lambda *_args, **_kwargs: CaseStatusPopulationFact(case_statuses=tuple(runtime["statuses"].items()), return_code=0),
    )
    monkeypatch.setattr(
        b5,
        "read_verified_analysis_readiness",
        lambda _session, case_name, *, timeout_seconds=30.0: SimpleNamespace(
            case_name=case_name,
            readiness={1: AnalysisReadiness.ANALYSIS_NOT_RUN, 4: AnalysisReadiness.ANALYSIS_FINISHED}[runtime["statuses"][case_name]],
            etabs_status_code=runtime["statuses"][case_name],
        ),
    )
    monkeypatch.setattr(b5, "run_analysis_from_session", run_analysis)
    expectation = ColumnForcePopulationExpectation(expected_unique_names=("1",), source_row_count=1)
    monkeypatch.setattr(b5, "capture_column_force_population_expectation_from_session", lambda *_args, **_kwargs: expectation)
    monkeypatch.setattr(
        b5,
        "capture_column_force_result_population_from_session",
        lambda _session, *, case_name, expectation, timeout_seconds=30.0: ColumnForceResultPopulationFact(
            case_name=case_name,
            expectation_ref=expectation.evidence_ref,
            expected_unique_names=expectation.expected_unique_names,
            observed_unique_names=expectation.expected_unique_names,
            rows=_force_rows(case_name),
        ),
    )

    # Existing POST continuity runs with the real helper against mocked factual recapture.
    monkeypatch.setattr(continuity, "TrustedLiveAcquisitionContext", _FakeContext)
    monkeypatch.setattr(continuity, "OwnedScratchContext", _FakeOwnedScratch)
    monkeypatch.setattr(continuity, "FrameFlexuralBaseFact", _BaseFact)
    monkeypatch.setattr(continuity, "capture_frame_flexural_base_fact", lambda **_kwargs: post_base)

    request = ProjectExecutionRequest(
        project_id="project:public-a5",
        report_id="report:public-a5",
        title="PUBLIC A5 product path",
        column=ColumnExecutionRequest(COMPONENT),
    )
    return SimpleNamespace(
        request=request,
        runtime=runtime,
        modifier_values=modifier_values,
        mutation_calls=mutation_calls,
        column=column,
        topology=topology,
        frame_population=frame_population,
        area_population=area_population,
        section_initial=section_initial,
        object_initial=object_initial,
    )


def test_execute_project_reaches_real_fnd2_and_preserves_non_target_frame_slots(product_harness):
    result = project_execution.execute_project(product_harness.request, verified_session=_FakeSession())

    assert result.column.fnd_col_2_execution is not None
    assert BLOCKER_LIVE_FND2_INPUT_LINEAGE not in result.column.blockers
    assert product_harness.runtime["run_calls"] == 1
    assert product_harness.runtime["delete_calls"] == 1

    section = product_harness.modifier_values[(FrameModifierSurface.FRAME_SECTION_PROPERTY.value, "C50x80")].as_tuple()
    obj = product_harness.modifier_values[(FrameModifierSurface.FRAME_OBJECT.value, "1")].as_tuple()
    assert section == (0.41, 1.0, 1.0, 0.74, 1.0, 1.0, 1.2, 1.3)
    assert obj == (0.31, 1.0, 1.0, 0.64, 1.0, 1.0, 0.9, 0.8)


def test_unresolved_required_frame_mode_fails_closed_before_b4b(product_harness, monkeypatch):
    bad_column = _Column(top_coord_m=(1.0, 0.0, 3.0), coordinate_length_m=(10.0 ** 0.5))
    bad_topology = _Topology(bad_column)
    monkeypatch.setattr(a5, "capture_etabs_strict_column_topology_from_session", lambda _session: bad_topology)

    result = project_execution.execute_project(product_harness.request, verified_session=_FakeSession())

    assert result.column.blockers == (a5.BLOCKER_A3_EQ713_POPULATION,)
    assert result.column.fnd_col_2_execution is None
    assert product_harness.runtime["run_calls"] == 0


def test_unproven_shell_thick_area_plate_and_transverse_modes_fail_closed(product_harness, monkeypatch):
    area = SimpleNamespace(
        area_name="A1",
        orientation=AreaDesignOrientation.FLOOR,
        property_name="Slab15",
        property_state=SimpleNamespace(
            family=AreaPropertyFamily.SLAB,
            shell_type_code=2,
            material_name="C35",
            thickness=0.15,
            property_modifiers=SimpleNamespace(modifiers=AreaModifierVector.from_sequence((0.25,) * 6 + (1.0,) * 4)),
        ),
        raw_material_overwrite_name="None",
        object_modifiers=SimpleNamespace(modifiers=AreaModifierVector.from_sequence((1.0,) * 10)),
        semi_rigid_diaphragm_assigned=True,
        wall_assignment_role=None,
        default_local_axes_assignment_proven=True,
        source_refs=("area:A1",),
    )
    area_population = SimpleNamespace(
        expected_area_names=("A1",),
        rows=(area,),
        source_refs=("area-population:A1",),
    )
    monkeypatch.setattr(a5, "capture_area_contributor_population_from_session", lambda *_args, **_kwargs: area_population)

    result = project_execution.execute_project(product_harness.request, verified_session=_FakeSession())

    assert result.column.blockers == (a5.BLOCKER_A3_EQ713_POPULATION,)
    assert result.column.fnd_col_2_execution is None
    assert product_harness.runtime["run_calls"] == 0
'''
# dataclass(slots) has no __dict__; fix post fact construction explicitly.
product_test = product_test.replace(
'''    post_base = _BaseFact(**{\n        **base.__dict__,\n        "evidence_ref": "frame-base-post:1",\n        "capture_event_ref": "frame-capture:post",\n    })\n''',
'''    post_base = _BaseFact(\n        component_unique_name=base.component_unique_name,\n        assigned_section_name=base.assigned_section_name,\n        material_name=base.material_name,\n        section_semantics=base.section_semantics,\n        t2_mm=base.t2_mm,\n        t3_mm=base.t3_mm,\n        concrete_fck_mpa=base.concrete_fck_mpa,\n        etabs_ec_mpa=base.etabs_ec_mpa,\n        source_model_ref=base.source_model_ref,\n        ownership_proof_ref=base.ownership_proof_ref,\n        semantic_state_ref=base.semantic_state_ref,\n        evidence_ref="frame-base-post:1",\n        capture_event_ref="frame-capture:post",\n        source_refs=base.source_refs,\n    )\n''')
(ROOT / "tests/application/test_column_public_a5_product_path.py").write_text(product_test, encoding="utf-8")


# Final exact-checkout workflow after this one-shot patch commit.  Keep the
# inherited gates and add explicit PUBLIC-A5 product path proof.
final_workflow = r'''name: COLUMN-R1 Reconciled Exact Validation

on:
  push:
    branches:
      - sprint/column-r1-reconciled-closure
  workflow_dispatch:

permissions:
  contents: read

env:
  PYTHONPATH: ${{ github.workspace }}:${{ github.workspace }}/packages/etabs_gateway/src

jobs:
  validate-reconciled-head:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout exact reconciled branch commit
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          ref: ${{ github.sha }}

      - name: Verify exact checkout
        shell: bash
        run: |
          test "$(git rev-parse HEAD)" = "$GITHUB_SHA"
          echo "HEAD=$(git rev-parse HEAD)"
          echo "TREE=$(git rev-parse HEAD^{tree})"

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install offline test dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install pytest pyyaml jsonschema openpyxl et_xmlfile

      - name: Compile and import
        run: |
          python -m compileall -q tbdy_engine tests packages/etabs_gateway/src
          python -c "import etabs_gateway; import tbdy_engine; import tbdy_engine.application.project_execution; import tbdy_engine.application.column_execution; import tbdy_engine.application.column_public_a5; import tbdy_engine.analysis_basis.eq713_uncracked_analysis_state; import tbdy_engine.analysis_basis.eq713_frame_mechanics"

      - name: A3 authority and Area provider
        run: |
          python -m pytest -q \
            tests/analysis_basis/test_eq713_uncracked_analysis_state.py \
            tests/analysis_basis/test_eq713_frame_mechanics.py \
            tests/etabs/test_oapi_area_contributors.py \
            tests/providers/test_etabs_area_contributor_provider.py

      - name: Frame OAPI and factual providers
        run: |
          python -m pytest -q \
            tests/etabs/test_oapi_frame_releases.py \
            tests/etabs/test_oapi_material_properties.py \
            tests/providers

      - name: B4B and B5 focused
        run: |
          python -m pytest -q \
            tests/integration/test_b4b_analysis_state_mutation.py \
            tests/integration/test_b4b_analysis_state_revalidation.py \
            tests/integration/test_b5_analysis_execution.py \
            tests/integration/test_b5_analysis_lineage_issuer.py \
            tests/providers/test_b5_column_force_result_population_provider.py

      - name: PUBLIC A5 execute_project product path
        run: python -m pytest -q tests/application/test_column_public_a5_product_path.py

      - name: B6 focused regression
        run: |
          python -m pytest -q \
            tests/etabs/test_oapi_concrete_design.py \
            tests/etabs/test_oapi_concrete_design_start.py \
            tests/integration/test_b6_controlled_design_execution.py \
            tests/integration/test_b6_p0_design_preflight.py \
            tests/architecture/test_b6_p0_design_preflight_architecture.py

      - name: C focused regression
        run: |
          python -m pytest -q \
            tests/regulatory/test_column_transverse_confinement.py \
            tests/application/test_column_r1_lane_c_bound_join.py

      - name: Architecture negative reachability
        run: python -m pytest -q tests/architecture
'''
(ROOT / ".github/workflows/column_r1_reconciled_exact_validation.yml").write_text(final_workflow, encoding="utf-8")

# One-shot transport is not product code; remove it from the resulting candidate.
Path(__file__).unlink()
