"""Bounded factual Frame population for COLUMN-R1 PUBLIC-A5.

This provider composes existing factual owners only.  It does not decide
TS500 Eq.7.13 participation.  In particular ``FrameObj.GetReleases`` is used
only to prove the supported end-condition slice; absence of releases is never
promoted here to participation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from tbdy_engine.etabs.oapi import fetch_display_table_from_session
from tbdy_engine.etabs.oapi.frame_modifiers import (
    FrameModifierReadFact,
    FrameModifierSurface,
    get_frame_modifiers_from_session,
)
from tbdy_engine.etabs.oapi.frame_releases import (
    FrameReleaseFact,
    get_frame_releases_from_session,
)
from tbdy_engine.etabs.oapi.line_springs import (
    LineSpringPropertyUniverseFact,
    read_line_spring_property_universe_from_session,
)
from tbdy_engine.etabs.oapi.frame_section_mechanics import (
    FrameSectionMechanicsFact,
    get_frame_section_mechanics_from_session,
)
from tbdy_engine.etabs.oapi.material_properties import (
    IsotropicMaterialPropertiesFact,
    MaterialTypeFact,
    get_isotropic_material_properties_from_session,
    get_material_type_from_session,
)
from tbdy_engine.etabs.oapi.object_model import read_frame_names_from_session
from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.features.column_shear_topology import StrictColumnTopologyBundle
from tbdy_engine.providers.etabs_strict_column_topology_provider import (
    TABLE_BEAMS,
    TABLE_COLUMNS,
    TABLE_LOCAL_AXES,
    TABLE_POINT,
)
from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext
from tbdy_engine.integration.live_etabs_acquisition_context import TrustedLiveAcquisitionContext
from tbdy_engine.providers.etabs_frame_flexural_base_provider import (
    TABLE_CONCRETE,
    TABLE_FRAME_ASSIGNMENTS,
    TABLE_FRAME_SECTION_SUMMARY,
    TABLE_RECTANGULAR,
    FrameFlexuralBaseCaptureSnapshot,
    FrameFlexuralBaseFact,
    _stress_to_mpa,
    bind_frame_flexural_base_fact_from_snapshot,
    capture_frame_flexural_base_snapshot,
)

NO_RELEASE_OR_PARTIAL_FIXITY_EFFECT = "NO_RELEASE_OR_PARTIAL_FIXITY_EFFECT"
FRAME_END_CONDITION_UNSUPPORTED = "FRAME_END_CONDITION_UNSUPPORTED"
FRAME_EQ713_SCOPE_ROW_REF_PREFIX = "etabs-frame-eq713-scope-row:sha256:"
FRAME_EQ713_DEFAULT_LOCAL_AXIS_REF_PREFIX = (
    "etabs-frame-eq713-default-local-axis:"
)
TABLE_FRAME_ASSIGNMENTS_SUMMARY = "Frame Assignments - Summary"
FRAME_EQ713_OBJECT_TYPE_ROW_REF_PREFIX = "etabs-frame-eq713-object-type-row:sha256:"


class EtabsFrameEq713PopulationError(RuntimeError):
    """Raised when the supported exact Frame factual population cannot be bound."""


class FrameEq713ScopeStatus(StrEnum):
    OUT_OF_SLICE_FACTUAL_SCOPE_UNRESOLVED = (
        "OUT_OF_SLICE_FACTUAL_SCOPE_UNRESOLVED"
    )
    OUT_OF_SLICE_ROLE_UNRESOLVED = "OUT_OF_SLICE_ROLE_UNRESOLVED"
    OUT_OF_SLICE_MECHANICS_SCOPE_UNRESOLVED = (
        "OUT_OF_SLICE_MECHANICS_SCOPE_UNRESOLVED"
    )
    OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL = (
        "OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL"
    )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsFrameEq713PopulationError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    refs = tuple(dict.fromkeys(_text(value, "source_ref") for value in values))
    if not refs:
        raise EtabsFrameEq713PopulationError("source_refs must not be empty")
    return refs


def _pick(
    row: Mapping[str, Any],
    aliases: Sequence[str],
    label: str,
    *,
    required: bool = True,
) -> Any:
    normalized = {
        " ".join(str(key).strip().casefold().split()): value
        for key, value in row.items()
    }
    for alias in aliases:
        key = " ".join(alias.strip().casefold().split())
        if key in normalized and normalized[key] not in (None, ""):
            return normalized[key]
    if required:
        raise EtabsFrameEq713PopulationError(f"missing {label}")
    return None


def _row_ref(table: str, row: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(row),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    payload = table.encode("utf-8") + b"\x1f" + encoded
    return FRAME_EQ713_SCOPE_ROW_REF_PREFIX + hashlib.sha256(payload).hexdigest()


def _capture_full_rows(
    session,
    table: str,
) -> tuple[Mapping[str, Any], ...]:
    fetched = fetch_display_table_from_session(
        session,
        table,
        max_rows=None,
    )
    if fetched.capture_status is not RuntimeCaptureStatus.FULL:
        raise EtabsFrameEq713PopulationError(
            f"{table} requires FULL capture; got {fetched.capture_status.value}"
        )
    if fetched.parsed.return_code not in (None, 0):
        raise EtabsFrameEq713PopulationError(
            f"{table} returned nonzero code {fetched.parsed.return_code}"
        )
    rows = tuple(dict(row) for row in fetched.parsed.rows)
    if (
        fetched.parsed.row_count_reported is not None
        and len(rows) != int(fetched.parsed.row_count_reported)
    ):
        raise EtabsFrameEq713PopulationError(
            f"{table} captured/reported row count mismatch"
        )
    return rows


def _index_unique(
    rows: Sequence[Mapping[str, Any]],
    aliases: Sequence[str],
    label: str,
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        key = _text(
            str(_pick(row, aliases, f"{label}[{index}] identity")).strip(),
            f"{label}[{index}] identity",
        )
        if key in result:
            raise EtabsFrameEq713PopulationError(
                f"duplicate {label} identity {key!r}"
            )
        result[key] = row
    return result


class FrameEq713ObjectTypeResolution(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class FrameEq713ObjectTypeFact:
    frame_name: str
    raw_frame_type: str | None
    normalized_frame_type: str | None
    resolution: FrameEq713ObjectTypeResolution
    source_table: str
    source_column: str | None
    source_row: Mapping[str, Any] | None
    join_identity: str
    resolution_reason: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        name = _text(self.frame_name, "frame_name")
        object.__setattr__(self, "frame_name", name)
        if self.join_identity != name:
            raise EtabsFrameEq713PopulationError(
                "Frame object-type join identity must equal FrameObj UniqueName"
            )
        if self.source_table != TABLE_FRAME_ASSIGNMENTS_SUMMARY:
            raise EtabsFrameEq713PopulationError(
                "Frame object-type fact source table mismatch"
            )
        if not isinstance(self.resolution, FrameEq713ObjectTypeResolution):
            raise TypeError("resolution must be FrameEq713ObjectTypeResolution")
        if self.raw_frame_type is None:
            if self.resolution is not FrameEq713ObjectTypeResolution.UNRESOLVED:
                raise EtabsFrameEq713PopulationError(
                    "missing raw Frame type must be explicitly UNRESOLVED"
                )
            if self.normalized_frame_type is not None:
                raise EtabsFrameEq713PopulationError(
                    "unresolved raw Frame type cannot have normalized type"
                )
        else:
            if self.resolution is not FrameEq713ObjectTypeResolution.RESOLVED:
                raise EtabsFrameEq713PopulationError(
                    "present raw Frame type must be explicitly RESOLVED"
                )
            raw = _text(self.raw_frame_type, "raw_frame_type")
            normalized = _text(
                self.normalized_frame_type,
                "normalized_frame_type",
            )
            if normalized != raw.upper():
                raise EtabsFrameEq713PopulationError(
                    "normalized Frame type must be the uppercase raw factual type"
                )
            object.__setattr__(self, "raw_frame_type", raw)
            object.__setattr__(self, "normalized_frame_type", normalized)
        if self.source_column is not None:
            object.__setattr__(
                self,
                "source_column",
                _text(self.source_column, "source_column"),
            )
        if self.source_row is not None:
            object.__setattr__(self, "source_row", dict(self.source_row))
        object.__setattr__(
            self,
            "resolution_reason",
            _text(self.resolution_reason, "resolution_reason"),
        )
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


def _pick_with_source_column(
    row: Mapping[str, Any],
    aliases: Sequence[str],
) -> tuple[str | None, Any]:
    normalized = {
        " ".join(str(key).strip().casefold().split()): (str(key), value)
        for key, value in row.items()
    }
    for alias in aliases:
        key = " ".join(alias.strip().casefold().split())
        hit = normalized.get(key)
        if hit is not None and hit[1] not in (None, ""):
            return hit
    return None, None


def _object_type_row_ref(row: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(row),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    payload = TABLE_FRAME_ASSIGNMENTS_SUMMARY.encode("utf-8") + b"\x1f" + encoded
    return (
        FRAME_EQ713_OBJECT_TYPE_ROW_REF_PREFIX
        + hashlib.sha256(payload).hexdigest()
    )


def _build_frame_object_type_facts(
    *,
    expected_frame_names: Sequence[str],
    summary_rows: Sequence[Mapping[str, Any]],
    source_refs: Sequence[str],
) -> tuple[FrameEq713ObjectTypeFact, ...]:
    expected = tuple(
        sorted(_text(name, "expected_frame_name") for name in expected_frame_names)
    )
    if len(expected) != len(set(expected)):
        raise EtabsFrameEq713PopulationError(
            "duplicate expected Frame identity for object-type denominator"
        )
    by_name = _index_unique(
        summary_rows,
        ("UniqueName", "Unique Name"),
        TABLE_FRAME_ASSIGNMENTS_SUMMARY,
    )
    orphans = tuple(sorted(set(by_name) - set(expected)))
    if orphans:
        raise EtabsFrameEq713PopulationError(
            "Frame Assignments - Summary contains identities absent from "
            f"FrameObj.GetNameList: {orphans!r}"
        )
    base_refs = _refs(source_refs)
    result: list[FrameEq713ObjectTypeFact] = []
    type_aliases = (
        "FrameType",
        "Frame Type",
        "Type",
        "DesignType",
        "Design Type",
        "ObjectType",
        "Object Type",
    )
    for name in expected:
        row = by_name.get(name)
        if row is None:
            result.append(
                FrameEq713ObjectTypeFact(
                    frame_name=name,
                    raw_frame_type=None,
                    normalized_frame_type=None,
                    resolution=FrameEq713ObjectTypeResolution.UNRESOLVED,
                    source_table=TABLE_FRAME_ASSIGNMENTS_SUMMARY,
                    source_column=None,
                    source_row=None,
                    join_identity=name,
                    resolution_reason=(
                        "expected FrameObj identity has no exact "
                        "Frame Assignments - Summary row"
                    ),
                    source_refs=(
                        *base_refs,
                        f"CSI:FrameObj.GetNameList:FRAME:{name}",
                    ),
                )
            )
            continue
        source_column, raw = _pick_with_source_column(row, type_aliases)
        row_ref = _object_type_row_ref(row)
        if raw in (None, ""):
            result.append(
                FrameEq713ObjectTypeFact(
                    frame_name=name,
                    raw_frame_type=None,
                    normalized_frame_type=None,
                    resolution=FrameEq713ObjectTypeResolution.UNRESOLVED,
                    source_table=TABLE_FRAME_ASSIGNMENTS_SUMMARY,
                    source_column=None,
                    source_row=row,
                    join_identity=name,
                    resolution_reason=(
                        "exact Frame Assignments - Summary row contains no "
                        "recognized factual Frame-type field"
                    ),
                    source_refs=(*base_refs, row_ref),
                )
            )
            continue
        raw_text = _text(str(raw).strip(), "raw_frame_type")
        result.append(
            FrameEq713ObjectTypeFact(
                frame_name=name,
                raw_frame_type=raw_text,
                normalized_frame_type=raw_text.upper(),
                resolution=FrameEq713ObjectTypeResolution.RESOLVED,
                source_table=TABLE_FRAME_ASSIGNMENTS_SUMMARY,
                source_column=source_column,
                source_row=row,
                join_identity=name,
                resolution_reason="exact Frame-type field resolved by UniqueName join",
                source_refs=(*base_refs, row_ref),
            )
        )
    facts = tuple(result)
    if tuple(fact.frame_name for fact in facts) != expected:
        raise EtabsFrameEq713PopulationError(
            "Frame object-type facts do not exactly cover expected Frame denominator"
        )
    return facts


def _capture_frame_object_type_facts(
    context: TrustedLiveAcquisitionContext,
    expected_frame_names: Sequence[str],
) -> tuple[FrameEq713ObjectTypeFact, ...]:
    return _build_frame_object_type_facts(
        expected_frame_names=expected_frame_names,
        summary_rows=_capture_full_rows(
            context.verified_session,
            TABLE_FRAME_ASSIGNMENTS_SUMMARY,
        ),
        source_refs=(context.session_provenance_ref,),
    )


def _supported_rectangular_shape(shape: str) -> bool:
    normalized = shape.strip().casefold()
    return (
        "rect" in normalized
        and "nonprismatic" not in normalized
        and "variable" not in normalized
    )



def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool) or value is None:
        raise EtabsFrameEq713PopulationError(
            f"{label} must be finite numeric"
        )
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EtabsFrameEq713PopulationError(
            f"{label} must be finite numeric"
        ) from exc
    if not math.isfinite(result):
        raise EtabsFrameEq713PopulationError(
            f"{label} must be finite numeric"
        )
    return result


@dataclass(frozen=True, slots=True)
class FrameEq713BeamMechanicsFact:
    frame_name: str
    member_role: str
    story: str
    label: str
    point_i_unique_name: str
    point_j_unique_name: str
    point_i_coord_m: tuple[float, float, float]
    point_j_coord_m: tuple[float, float, float]
    member_axis_vector: tuple[float, float, float]
    local_axis_explicit: bool
    local_axis_angle_degrees: float | None
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "frame_name",
            _text(self.frame_name, "frame_name"),
        )
        if self.member_role != "BEAM":
            raise EtabsFrameEq713PopulationError(
                "FrameEq713BeamMechanicsFact member_role must be BEAM"
            )
        object.__setattr__(self, "story", _text(self.story, "story"))
        object.__setattr__(self, "label", _text(self.label, "label"))
        object.__setattr__(
            self,
            "point_i_unique_name",
            _text(self.point_i_unique_name, "point_i_unique_name"),
        )
        object.__setattr__(
            self,
            "point_j_unique_name",
            _text(self.point_j_unique_name, "point_j_unique_name"),
        )
        for name in ("point_i_coord_m", "point_j_coord_m", "member_axis_vector"):
            values = tuple(
                _finite_float(value, f"{name}[{index}]")
                for index, value in enumerate(getattr(self, name))
            )
            if len(values) != 3:
                raise EtabsFrameEq713PopulationError(
                    f"{name} must contain exactly three coordinates"
                )
            object.__setattr__(self, name, values)
        if math.sqrt(
            sum(value * value for value in self.member_axis_vector)
        ) <= 0.0:
            raise EtabsFrameEq713PopulationError(
                "BEAM member_axis_vector must be nonzero"
            )
        if type(self.local_axis_explicit) is not bool:
            raise EtabsFrameEq713PopulationError(
                "local_axis_explicit must be bool"
            )
        if self.local_axis_explicit:
            if self.local_axis_angle_degrees is None:
                raise EtabsFrameEq713PopulationError(
                    "explicit BEAM local axis requires factual angle"
                )
            object.__setattr__(
                self,
                "local_axis_angle_degrees",
                _finite_float(
                    self.local_axis_angle_degrees,
                    "local_axis_angle_degrees",
                ),
            )
        elif self.local_axis_angle_degrees is not None:
            raise EtabsFrameEq713PopulationError(
                "default BEAM local axis must not manufacture an angle"
            )
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


@dataclass(frozen=True, slots=True)
class FrameEq713ResidualStructuralFact:
    # Generic non-concrete-safe structural facts for an out-of-slice Frame.
    frame_name: str
    assigned_section_name: str
    shape: str
    material_name: str
    member_role: str | None
    section_mechanics: FrameSectionMechanicsFact
    property_modifiers: FrameModifierReadFact
    object_modifiers: FrameModifierReadFact
    releases: FrameReleaseFact
    isotropic_material: IsotropicMaterialPropertiesFact
    beam_mechanics: FrameEq713BeamMechanicsFact | None
    source_refs: tuple[str, ...]
    material_type: MaterialTypeFact | None = None

    def __post_init__(self) -> None:
        name = _text(self.frame_name, "frame_name")
        section = _text(self.assigned_section_name, "assigned_section_name")
        material = _text(self.material_name, "material_name")
        object.__setattr__(self, "frame_name", name)
        object.__setattr__(self, "assigned_section_name", section)
        object.__setattr__(self, "shape", _text(self.shape, "shape"))
        object.__setattr__(self, "material_name", material)
        if self.member_role not in {"COLUMN", "BEAM", None}:
            raise EtabsFrameEq713PopulationError(
                "residual member_role must be COLUMN, BEAM, or None"
            )
        if not isinstance(self.section_mechanics, FrameSectionMechanicsFact):
            raise TypeError("section_mechanics must be FrameSectionMechanicsFact")
        if (
            not self.section_mechanics.success
            or self.section_mechanics.section_name != section
        ):
            raise EtabsFrameEq713PopulationError(
                "residual Frame section mechanics fact is not exact/successful"
            )
        if not isinstance(self.property_modifiers, FrameModifierReadFact):
            raise TypeError("property_modifiers must be FrameModifierReadFact")
        if (
            not self.property_modifiers.success
            or self.property_modifiers.surface
            is not FrameModifierSurface.FRAME_SECTION_PROPERTY
            or self.property_modifiers.target_name != section
        ):
            raise EtabsFrameEq713PopulationError(
                "residual Frame property modifier fact is not exact/successful"
            )
        if not isinstance(self.object_modifiers, FrameModifierReadFact):
            raise TypeError("object_modifiers must be FrameModifierReadFact")
        if (
            not self.object_modifiers.success
            or self.object_modifiers.surface is not FrameModifierSurface.FRAME_OBJECT
            or self.object_modifiers.target_name != name
        ):
            raise EtabsFrameEq713PopulationError(
                "residual Frame object modifier fact is not exact/successful"
            )
        if not isinstance(self.releases, FrameReleaseFact):
            raise TypeError("releases must be FrameReleaseFact")
        if not self.releases.success or self.releases.frame_name != name:
            raise EtabsFrameEq713PopulationError(
                "residual Frame release fact is not exact/successful"
            )
        if not isinstance(self.isotropic_material, IsotropicMaterialPropertiesFact):
            raise TypeError(
                "isotropic_material must be IsotropicMaterialPropertiesFact"
            )
        if (
            not self.isotropic_material.success
            or self.isotropic_material.material_name != material
        ):
            raise EtabsFrameEq713PopulationError(
                "residual Frame isotropic material fact is not exact/successful"
            )

        if self.material_type is not None:
            if not isinstance(
                self.material_type,
                MaterialTypeFact,
            ):
                raise TypeError(
                    "material_type must be "
                    "MaterialTypeFact or None"
                )

            if (
                not self.material_type.success
                or self.material_type.material_name
                != material
            ):
                raise EtabsFrameEq713PopulationError(
                    "residual Frame material-type fact "
                    "is not exact/successful"
                )

            if (
                self.material_type.evidence_ref
                not in tuple(self.source_refs)
            ):
                raise EtabsFrameEq713PopulationError(
                    "residual Frame material-type "
                    "provenance is not bound to "
                    "source_refs"
                )

        if self.member_role == "BEAM":
            if self.beam_mechanics is not None and (
                not isinstance(self.beam_mechanics, FrameEq713BeamMechanicsFact)
                or self.beam_mechanics.frame_name != name
            ):
                raise EtabsFrameEq713PopulationError(
                    "residual BEAM mechanics fact identity mismatch"
                )
        elif self.beam_mechanics is not None:
            raise EtabsFrameEq713PopulationError(
                "non-BEAM residual Frame cannot carry BEAM mechanics"
            )
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


def _point_coord(
    row: Mapping[str, Any],
    *,
    point_name: str,
) -> tuple[float, float, float]:
    return (
        _finite_float(
            _pick(row, ("X",), f"Point {point_name} X"),
            f"Point {point_name} X",
        ),
        _finite_float(
            _pick(row, ("Y",), f"Point {point_name} Y"),
            f"Point {point_name} Y",
        ),
        _finite_float(
            _pick(row, ("Z",), f"Point {point_name} Z"),
            f"Point {point_name} Z",
        ),
    )


def _build_supported_beam_mechanics(
    *,
    supported_frame_names: Sequence[str],
    beam_connectivity_rows: Sequence[Mapping[str, Any]],
    point_rows: Sequence[Mapping[str, Any]],
    local_axis_rows: Sequence[Mapping[str, Any]],
    source_refs: Sequence[str],
) -> Mapping[str, FrameEq713BeamMechanicsFact]:
    supported = set(
        _text(name, "supported_frame_name")
        for name in supported_frame_names
    )
    beams = _index_unique(
        beam_connectivity_rows,
        ("UniqueName", "Unique Name"),
        TABLE_BEAMS,
    )
    points = _index_unique(
        point_rows,
        ("UniqueName", "Unique Name"),
        TABLE_POINT,
    )
    local_axes = _index_unique(
        local_axis_rows,
        ("UniqueName", "Unique Name"),
        TABLE_LOCAL_AXES,
    )
    base_refs = _refs(source_refs)
    result: dict[str, FrameEq713BeamMechanicsFact] = {}

    for name in sorted(supported & set(beams)):
        beam = beams[name]
        point_i_name = _text(
            str(
                _pick(
                    beam,
                    ("UniquePtI", "Unique Pt I"),
                    f"BEAM {name} UniquePtI",
                )
            ).strip(),
            "point_i_unique_name",
        )
        point_j_name = _text(
            str(
                _pick(
                    beam,
                    ("UniquePtJ", "Unique Pt J"),
                    f"BEAM {name} UniquePtJ",
                )
            ).strip(),
            "point_j_unique_name",
        )
        point_i = points.get(point_i_name)
        point_j = points.get(point_j_name)
        if point_i is None or point_j is None:
            raise EtabsFrameEq713PopulationError(
                f"BEAM Frame {name!r} endpoint point missing: "
                f"I={point_i_name in points} J={point_j_name in points}"
            )
        coord_i = _point_coord(point_i, point_name=point_i_name)
        coord_j = _point_coord(point_j, point_name=point_j_name)
        vector = tuple(
            coord_j[index] - coord_i[index]
            for index in range(3)
        )
        if math.sqrt(sum(value * value for value in vector)) <= 0.0:
            raise EtabsFrameEq713PopulationError(
                f"BEAM Frame {name!r} has zero-length endpoint vector"
            )

        axis = local_axes.get(name)
        axis_explicit = axis is not None
        axis_angle = (
            None
            if axis is None
            else _finite_float(
                _pick(axis, ("Angle",), f"BEAM {name} local-axis Angle"),
                f"BEAM {name} local-axis Angle",
            )
        )
        refs = [
            *base_refs,
            _row_ref(TABLE_BEAMS, beam),
            _row_ref(TABLE_POINT, point_i),
            _row_ref(TABLE_POINT, point_j),
        ]
        if axis is None:
            refs.append(
                f"{FRAME_EQ713_DEFAULT_LOCAL_AXIS_REF_PREFIX}"
                f"FULL_TABLE_NO_EXPLICIT_ROW:{name}"
            )
        else:
            refs.append(_row_ref(TABLE_LOCAL_AXES, axis))

        result[name] = FrameEq713BeamMechanicsFact(
            frame_name=name,
            member_role="BEAM",
            story=_text(
                str(_pick(beam, ("Story",), f"BEAM {name} Story")).strip(),
                "story",
            ),
            label=_text(
                str(
                    _pick(
                        beam,
                        ("BeamBay", "Label"),
                        f"BEAM {name} label",
                    )
                ).strip(),
                "label",
            ),
            point_i_unique_name=point_i_name,
            point_j_unique_name=point_j_name,
            point_i_coord_m=coord_i,
            point_j_coord_m=coord_j,
            member_axis_vector=vector,
            local_axis_explicit=axis_explicit,
            local_axis_angle_degrees=axis_angle,
            source_refs=tuple(refs),
        )

    return result


def _capture_supported_beam_mechanics(
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    supported_frame_names: Sequence[str],
) -> Mapping[str, FrameEq713BeamMechanicsFact]:
    return _build_supported_beam_mechanics(
        supported_frame_names=supported_frame_names,
        beam_connectivity_rows=_capture_full_rows(
            context.verified_session,
            TABLE_BEAMS,
        ),
        point_rows=_capture_full_rows(
            context.verified_session,
            TABLE_POINT,
        ),
        local_axis_rows=_capture_full_rows(
            context.verified_session,
            TABLE_LOCAL_AXES,
        ),
        source_refs=(
            context.session_provenance_ref,
            owned_scratch.ownership_proof_ref,
        ),
    )


def _capture_residual_structural_facts(
    context: TrustedLiveAcquisitionContext,
    out_of_slice_rows: Sequence[FrameEq713ScopeFact],
    beam_mechanics_by_name: Mapping[str, FrameEq713BeamMechanicsFact],
) -> tuple[FrameEq713ResidualStructuralFact, ...]:
    # Capture generic elastic facts without manufacturing concrete authority.
    section_cache: dict[str, FrameSectionMechanicsFact] = {}
    property_modifier_cache: dict[str, FrameModifierReadFact] = {}
    material_cache: dict[str, IsotropicMaterialPropertiesFact] = {}
    material_type_cache: dict[str, MaterialTypeFact] = {}
    result: list[FrameEq713ResidualStructuralFact] = []

    for scope in sorted(out_of_slice_rows, key=lambda item: item.frame_name):
        if (
            scope.assigned_section_name is None
            or scope.shape is None
            or scope.material_name is None
        ):
            continue
        section = scope.assigned_section_name
        material_name = scope.material_name

        section_mechanics = section_cache.get(section)
        if section_mechanics is None:
            section_mechanics = get_frame_section_mechanics_from_session(
                context.verified_session,
                section_name=section,
            )
            section_cache[section] = section_mechanics

        property_modifiers = property_modifier_cache.get(section)
        if property_modifiers is None:
            property_modifiers = get_frame_modifiers_from_session(
                context.verified_session,
                surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
                target_name=section,
            )
            property_modifier_cache[section] = property_modifiers

        object_modifiers = get_frame_modifiers_from_session(
            context.verified_session,
            surface=FrameModifierSurface.FRAME_OBJECT,
            target_name=scope.frame_name,
        )
        releases = get_frame_releases_from_session(
            context.verified_session,
            frame_name=scope.frame_name,
        )
        isotropic = material_cache.get(material_name)
        if isotropic is None:
            isotropic = get_isotropic_material_properties_from_session(
                context.verified_session,
                material_name=material_name,
            )
            material_cache[material_name] = isotropic

        material_type = material_type_cache.get(
            material_name
        )
        if material_type is None:
            material_type = (
                get_material_type_from_session(
                    context.verified_session,
                    material_name=material_name,
                )
            )
            material_type_cache[
                material_name
            ] = material_type

        beam_mechanics = beam_mechanics_by_name.get(scope.frame_name)
        fact = FrameEq713ResidualStructuralFact(
            frame_name=scope.frame_name,
            assigned_section_name=section,
            shape=scope.shape,
            material_name=material_name,
            member_role=scope.member_role,
            section_mechanics=section_mechanics,
            property_modifiers=property_modifiers,
            object_modifiers=object_modifiers,
            releases=releases,
            isotropic_material=isotropic,
            beam_mechanics=beam_mechanics,
            source_refs=(
                *scope.source_refs,
                section_mechanics.evidence_ref,
                property_modifiers.evidence_ref,
                object_modifiers.evidence_ref,
                releases.evidence_ref,
                isotropic.evidence_ref,
                material_type.evidence_ref,
                *(
                    beam_mechanics.source_refs
                    if beam_mechanics is not None
                    else ()
                ),
            ),
            material_type=material_type,
        )
        result.append(fact)

    return tuple(result)


def _no_release_or_partial_fixity(fact: FrameReleaseFact) -> bool:
    return (
        fact.success
        and not any(fact.i_end_released)
        and not any(fact.j_end_released)
        and all(value == 0.0 for value in fact.i_end_partial_fixity)
        and all(value == 0.0 for value in fact.j_end_partial_fixity)
    )


def _role_map(topology: StrictColumnTopologyBundle) -> dict[str, str]:
    if not isinstance(topology, StrictColumnTopologyBundle):
        raise TypeError("topology must be StrictColumnTopologyBundle")
    roles: dict[str, str] = {}

    def bind(name: str, role: str) -> None:
        previous = roles.get(name)
        if previous is not None and previous != role:
            raise EtabsFrameEq713PopulationError(
                f"Frame {name!r} has contradictory strict-topology member roles: {previous}/{role}"
            )
        roles[name] = role

    for column in topology.columns:
        bind(column.unique_name, "COLUMN")
        for beam in (*column.beams_at_bottom, *column.beams_at_top):
            bind(beam.beam_unique_name, "BEAM")
    return roles


@dataclass(frozen=True, slots=True)
class FrameEq713ScopeFact:
    frame_name: str
    assigned_section_name: str | None
    shape: str | None
    material_name: str | None
    member_role: str | None
    scope_status: FrameEq713ScopeStatus
    reason: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_name", _text(self.frame_name, "frame_name"))
        for field_name in ("assigned_section_name", "shape", "material_name"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _text(value, field_name),
                )
        if self.member_role is not None and self.member_role not in {"COLUMN", "BEAM"}:
            raise EtabsFrameEq713PopulationError(
                "member_role must be COLUMN, BEAM, or None"
            )
        if not isinstance(self.scope_status, FrameEq713ScopeStatus):
            raise TypeError("scope_status must be FrameEq713ScopeStatus")
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        object.__setattr__(self, "source_refs", _refs(self.source_refs))


def _normalize_frame_section_assignment(
    value: object,
) -> str | None:
    """Normalize the exact ETABS section-assignment table sentinel.

    ``Frame Assignments - Section Properties`` represents an unassigned
    Frame section with the literal canonical token ``None``.  Normalize
    that factual table sentinel to Python ``None`` at the acquisition
    boundary.  Do not generalize other tokens or infer applicability here.
    """
    if value is None:
        return None

    token = str(value).strip()

    if token in {"", "None"}:
        return None

    return _text(
        token,
        "assigned_section_name",
    )


def _build_frame_scope_partition(
    *,
    expected_frame_names: Sequence[str],
    topology: StrictColumnTopologyBundle,
    column_connectivity_rows: Sequence[Mapping[str, Any]],
    beam_connectivity_rows: Sequence[Mapping[str, Any]],
    assignment_rows: Sequence[Mapping[str, Any]],
    section_summary_rows: Sequence[Mapping[str, Any]],
    rectangular_rows: Sequence[Mapping[str, Any]],
    concrete_rows: Sequence[Mapping[str, Any]],
    source_refs: Sequence[str],
) -> tuple[tuple[str, ...], tuple[FrameEq713ScopeFact, ...]]:
    if not isinstance(topology, StrictColumnTopologyBundle):
        raise TypeError("topology must be StrictColumnTopologyBundle")

    expected = tuple(
        sorted(_text(name, "expected_frame_name") for name in expected_frame_names)
    )
    if len(expected) != len(set(expected)):
        raise EtabsFrameEq713PopulationError("duplicate expected Frame identity")

    topology_roles = _role_map(topology)
    role_orphans = tuple(sorted(set(topology_roles) - set(expected)))
    if role_orphans:
        raise EtabsFrameEq713PopulationError(
            "strict topology contains Frame identities absent from FrameObj.GetNameList: "
            f"{role_orphans!r}"
        )

    column_connectivity = _index_unique(
        column_connectivity_rows,
        ("UniqueName", "Unique Name"),
        TABLE_COLUMNS,
    )
    beam_connectivity = _index_unique(
        beam_connectivity_rows,
        ("UniqueName", "Unique Name"),
        TABLE_BEAMS,
    )
    role_overlap = tuple(
        sorted(set(column_connectivity) & set(beam_connectivity))
    )
    if role_overlap:
        raise EtabsFrameEq713PopulationError(
            f"Frame identities have contradictory COLUMN/BEAM connectivity roles: {role_overlap!r}"
        )
    exact_roles = {
        **{name: "COLUMN" for name in column_connectivity},
        **{name: "BEAM" for name in beam_connectivity},
    }
    connectivity_orphans = tuple(sorted(set(exact_roles) - set(expected)))
    if connectivity_orphans:
        raise EtabsFrameEq713PopulationError(
            "Column/Beam connectivity contains identities absent from FrameObj.GetNameList: "
            f"{connectivity_orphans!r}"
        )
    for name, topology_role in topology_roles.items():
        if exact_roles.get(name) != topology_role:
            raise EtabsFrameEq713PopulationError(
                f"strict-topology role for Frame {name!r} disagrees with exact "
                f"Column/Beam connectivity role {exact_roles.get(name)!r}"
            )

    assignments = _index_unique(
        assignment_rows,
        ("UniqueName", "Unique Name"),
        TABLE_FRAME_ASSIGNMENTS,
    )
    summaries = _index_unique(
        section_summary_rows,
        ("Name", "Section Name", "Property"),
        TABLE_FRAME_SECTION_SUMMARY,
    )
    rectangles = _index_unique(
        rectangular_rows,
        ("Name", "SectionName", "Section Name", "Property"),
        TABLE_RECTANGULAR,
    )
    concrete_materials = _index_unique(
        concrete_rows,
        ("Material", "Name"),
        TABLE_CONCRETE,
    )

    supported: list[str] = []
    out_of_slice: list[FrameEq713ScopeFact] = []
    base_refs = _refs(source_refs)

    for name in expected:
        assignment = assignments.get(name)
        member_role = exact_roles.get(name)
        if assignment is None:
            out_of_slice.append(
                FrameEq713ScopeFact(
                    frame_name=name,
                    assigned_section_name=None,
                    shape=None,
                    material_name=None,
                    member_role=member_role,
                    scope_status=(
                        FrameEq713ScopeStatus.OUT_OF_SLICE_FACTUAL_SCOPE_UNRESOLVED
                    ),
                    reason=f"Frame {name!r} has no exact section assignment row",
                    source_refs=(
                        *base_refs,
                        f"CSI:FrameObj.GetNameList:FRAME:{name}",
                    ),
                )
            )
            continue

        section_raw = _pick(
            assignment,
            ("SectProp", "Section Property"),
            f"Frame {name} assigned section",
            required=False,
        )
        section = _normalize_frame_section_assignment(
            section_raw,
        )
        if section is None:
            out_of_slice.append(
                FrameEq713ScopeFact(
                    frame_name=name,
                    assigned_section_name=None,
                    shape=None,
                    material_name=None,
                    member_role=member_role,
                    scope_status=(
                        FrameEq713ScopeStatus.OUT_OF_SLICE_FACTUAL_SCOPE_UNRESOLVED
                    ),
                    reason=f"Frame {name!r} section assignment has no factual section identity",
                    source_refs=(
                        *base_refs,
                        f"CSI:FrameObj.GetNameList:FRAME:{name}",
                        _row_ref(TABLE_FRAME_ASSIGNMENTS, assignment),
                    ),
                )
            )
            continue

        section_summary = summaries.get(section)
        if section_summary is None:
            out_of_slice.append(
                FrameEq713ScopeFact(
                    frame_name=name,
                    assigned_section_name=section,
                    shape=None,
                    material_name=None,
                    member_role=member_role,
                    scope_status=(
                        FrameEq713ScopeStatus.OUT_OF_SLICE_FACTUAL_SCOPE_UNRESOLVED
                    ),
                    reason=(
                        f"Frame {name!r} section {section!r} has no exact section summary row"
                    ),
                    source_refs=(
                        *base_refs,
                        f"CSI:FrameObj.GetNameList:FRAME:{name}",
                        _row_ref(TABLE_FRAME_ASSIGNMENTS, assignment),
                    ),
                )
            )
            continue

        shape_raw = _pick(
            section_summary,
            ("Shape",),
            f"Frame {name} section shape",
            required=False,
        )
        material_raw = _pick(
            section_summary,
            ("Material", "Material Name"),
            f"Frame {name} section material",
            required=False,
        )
        shape = (
            None
            if shape_raw in (None, "")
            else _text(str(shape_raw).strip(), "shape")
        )
        material = (
            None
            if material_raw in (None, "")
            else _text(str(material_raw).strip(), "material_name")
        )
        rectangle = rectangles.get(section)
        concrete = (
            None
            if material is None
            else concrete_materials.get(material)
        )
        connectivity_row = (
            column_connectivity.get(name)
            if member_role == "COLUMN"
            else beam_connectivity.get(name)
            if member_role == "BEAM"
            else None
        )

        exact_refs = [
            *base_refs,
            f"CSI:FrameObj.GetNameList:FRAME:{name}",
            _row_ref(TABLE_FRAME_ASSIGNMENTS, assignment),
            _row_ref(TABLE_FRAME_SECTION_SUMMARY, section_summary),
        ]
        if connectivity_row is not None:
            exact_refs.append(
                _row_ref(
                    TABLE_COLUMNS if member_role == "COLUMN" else TABLE_BEAMS,
                    connectivity_row,
                )
            )
        if rectangle is not None:
            exact_refs.append(_row_ref(TABLE_RECTANGULAR, rectangle))
        if concrete is not None:
            exact_refs.append(_row_ref(TABLE_CONCRETE, concrete))

        if shape is None or material is None:
            out_of_slice.append(
                FrameEq713ScopeFact(
                    frame_name=name,
                    assigned_section_name=section,
                    shape=shape,
                    material_name=material,
                    member_role=member_role,
                    scope_status=(
                        FrameEq713ScopeStatus.OUT_OF_SLICE_FACTUAL_SCOPE_UNRESOLVED
                    ),
                    reason=(
                        f"Frame {name!r} section {section!r} lacks factual "
                        f"shape/material identity (shape={shape!r}; material={material!r})"
                    ),
                    source_refs=tuple(exact_refs),
                )
            )
            continue

        if member_role is None:
            out_of_slice.append(
                FrameEq713ScopeFact(
                    frame_name=name,
                    assigned_section_name=section,
                    shape=shape,
                    material_name=material,
                    member_role=None,
                    scope_status=FrameEq713ScopeStatus.OUT_OF_SLICE_ROLE_UNRESOLVED,
                    reason=(
                        f"Frame {name!r} exact COLUMN/BEAM role and mechanics are not "
                        "established by the current strict Column/joint topology scope"
                    ),
                    source_refs=tuple(exact_refs),
                )
            )
            continue

        if (
            not _supported_rectangular_shape(shape)
            or rectangle is None
            or concrete is None
        ):
            out_of_slice.append(
                FrameEq713ScopeFact(
                    frame_name=name,
                    assigned_section_name=section,
                    shape=shape,
                    material_name=material,
                    member_role=member_role,
                    scope_status=(
                        FrameEq713ScopeStatus.OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL
                    ),
                    reason=(
                        f"Frame {name!r} assigned section {section!r} shape={shape!r} "
                        f"material={material!r} is outside the supported prismatic "
                        "rectangular RC factual slice "
                        f"(rectangular_definition={rectangle is not None}; "
                        f"concrete_material={concrete is not None})"
                    ),
                    source_refs=tuple(exact_refs),
                )
            )
            continue

        if member_role == "BEAM":
            supported.append(name)
            continue

        if name not in topology_roles:
            out_of_slice.append(
                FrameEq713ScopeFact(
                    frame_name=name,
                    assigned_section_name=section,
                    shape=shape,
                    material_name=material,
                    member_role=member_role,
                    scope_status=(
                        FrameEq713ScopeStatus.OUT_OF_SLICE_MECHANICS_SCOPE_UNRESOLVED
                    ),
                    reason=(
                        f"Frame {name!r} exact {member_role} role is established, but "
                        "the current strict Column/joint topology does not bind the "
                        "mechanics evidence required by the supported Eq7.13 Frame slice"
                    ),
                    source_refs=tuple(exact_refs),
                )
            )
            continue

        supported.append(name)

    return tuple(supported), tuple(sorted(out_of_slice, key=lambda item: item.frame_name))


def _capture_frame_scope_partition(
    context: TrustedLiveAcquisitionContext,
    base_snapshot: FrameFlexuralBaseCaptureSnapshot,
    topology: StrictColumnTopologyBundle,
    expected_frame_names: Sequence[str],
) -> tuple[tuple[str, ...], tuple[FrameEq713ScopeFact, ...]]:
    if not isinstance(base_snapshot, FrameFlexuralBaseCaptureSnapshot):
        raise TypeError(
            "base_snapshot must be FrameFlexuralBaseCaptureSnapshot"
        )
    return _build_frame_scope_partition(
        expected_frame_names=expected_frame_names,
        topology=topology,
        column_connectivity_rows=_capture_full_rows(
            context.verified_session,
            TABLE_COLUMNS,
        ),
        beam_connectivity_rows=_capture_full_rows(
            context.verified_session,
            TABLE_BEAMS,
        ),
        assignment_rows=base_snapshot.assignment_rows,
        section_summary_rows=base_snapshot.section_summary_rows,
        rectangular_rows=base_snapshot.rectangular_rows,
        concrete_rows=base_snapshot.concrete_rows,
        source_refs=(
            base_snapshot.session_provenance_ref,
            base_snapshot.ownership_proof_ref,
        ),
    )


@dataclass(frozen=True, slots=True)
class FrameEq713FactualFact:
    frame_name: str
    member_role: str
    base_fact: FrameFlexuralBaseFact
    section_mechanics: FrameSectionMechanicsFact
    property_modifiers: FrameModifierReadFact
    object_modifiers: FrameModifierReadFact
    releases: FrameReleaseFact
    isotropic_material: IsotropicMaterialPropertiesFact
    factual_ec_mpa: Decimal
    factual_gc_mpa: Decimal
    beam_mechanics: FrameEq713BeamMechanicsFact | None
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        name = _text(self.frame_name, "frame_name")
        object.__setattr__(self, "frame_name", name)
        if self.member_role not in {"COLUMN", "BEAM"}:
            raise EtabsFrameEq713PopulationError("member_role must be COLUMN or BEAM")
        if not isinstance(self.base_fact, FrameFlexuralBaseFact):
            raise TypeError("base_fact must be FrameFlexuralBaseFact")
        if self.base_fact.component_unique_name != name:
            raise EtabsFrameEq713PopulationError("Frame base fact identity mismatch")
        if not isinstance(self.section_mechanics, FrameSectionMechanicsFact):
            raise TypeError("section_mechanics must be FrameSectionMechanicsFact")
        if (
            self.section_mechanics.section_name != self.base_fact.assigned_section_name
            or not self.section_mechanics.success
        ):
            raise EtabsFrameEq713PopulationError("Frame section mechanics fact is not exact/successful")
        if not isinstance(self.property_modifiers, FrameModifierReadFact):
            raise TypeError("property_modifiers must be FrameModifierReadFact")
        if (
            self.property_modifiers.surface is not FrameModifierSurface.FRAME_SECTION_PROPERTY
            or self.property_modifiers.target_name != self.base_fact.assigned_section_name
            or not self.property_modifiers.success
        ):
            raise EtabsFrameEq713PopulationError("Frame property modifier fact is not exact/successful")
        if not isinstance(self.object_modifiers, FrameModifierReadFact):
            raise TypeError("object_modifiers must be FrameModifierReadFact")
        if (
            self.object_modifiers.surface is not FrameModifierSurface.FRAME_OBJECT
            or self.object_modifiers.target_name != name
            or not self.object_modifiers.success
        ):
            raise EtabsFrameEq713PopulationError("Frame object modifier fact is not exact/successful")
        if not isinstance(self.releases, FrameReleaseFact):
            raise TypeError("releases must be FrameReleaseFact")
        if self.releases.frame_name != name or not self.releases.success:
            raise EtabsFrameEq713PopulationError("Frame release fact is not exact/successful")
        if not isinstance(self.isotropic_material, IsotropicMaterialPropertiesFact):
            raise TypeError("isotropic_material must be IsotropicMaterialPropertiesFact")
        if (
            self.isotropic_material.material_name != self.base_fact.material_name
            or not self.isotropic_material.success
        ):
            raise EtabsFrameEq713PopulationError("Frame isotropic material fact is not exact/successful")
        if self.factual_ec_mpa <= 0 or self.factual_gc_mpa <= 0:
            raise EtabsFrameEq713PopulationError("GetMPIsotropic E/G must be positive in MPa")
        if self.member_role == "BEAM":
            if not isinstance(
                self.beam_mechanics,
                FrameEq713BeamMechanicsFact,
            ):
                raise EtabsFrameEq713PopulationError(
                    "supported BEAM requires exact FrameEq713BeamMechanicsFact"
                )
            if self.beam_mechanics.frame_name != name:
                raise EtabsFrameEq713PopulationError(
                    "BEAM mechanics identity mismatch"
                )
        elif self.beam_mechanics is not None:
            raise EtabsFrameEq713PopulationError(
                "COLUMN Frame must not carry BEAM mechanics fact"
            )
        object.__setattr__(self, "source_refs", _refs(self.source_refs))

    @property
    def end_condition_status(self) -> str:
        return (
            NO_RELEASE_OR_PARTIAL_FIXITY_EFFECT
            if _no_release_or_partial_fixity(self.releases)
            else FRAME_END_CONDITION_UNSUPPORTED
        )

    @property
    def supported_end_condition(self) -> bool:
        return self.end_condition_status == NO_RELEASE_OR_PARTIAL_FIXITY_EFFECT


@dataclass(frozen=True, slots=True)
class FrameEq713FactualPopulation:
    expected_frame_names: tuple[str, ...]
    rows: tuple[FrameEq713FactualFact, ...]
    source_refs: tuple[str, ...]
    out_of_slice_rows: tuple[FrameEq713ScopeFact, ...] = ()
    object_type_facts: tuple[FrameEq713ObjectTypeFact, ...] = ()
    residual_structural_facts: tuple[FrameEq713ResidualStructuralFact, ...] = ()
    line_spring_property_universe: LineSpringPropertyUniverseFact | None = None
    material_snapshot: FrameFlexuralBaseCaptureSnapshot | None = None

    def __post_init__(self) -> None:
        expected = tuple(
            sorted(
                _text(name, "expected_frame_name")
                for name in self.expected_frame_names
            )
        )
        if len(expected) != len(set(expected)):
            raise EtabsFrameEq713PopulationError("duplicate expected Frame identity")
        rows = tuple(sorted(self.rows, key=lambda item: item.frame_name))
        supported_names = tuple(row.frame_name for row in rows)
        if len(supported_names) != len(set(supported_names)):
            raise EtabsFrameEq713PopulationError(
                "duplicate supported Frame factual identity"
            )
        out_of_slice = tuple(
            sorted(self.out_of_slice_rows, key=lambda item: item.frame_name)
        )
        out_of_slice_names = tuple(row.frame_name for row in out_of_slice)
        if len(out_of_slice_names) != len(set(out_of_slice_names)):
            raise EtabsFrameEq713PopulationError(
                "duplicate out-of-slice Frame factual identity"
            )
        overlap = tuple(sorted(set(supported_names) & set(out_of_slice_names)))
        if overlap:
            raise EtabsFrameEq713PopulationError(
                f"Frame identities cannot be both supported and out-of-slice: {overlap!r}"
            )
        observed = tuple(sorted((*supported_names, *out_of_slice_names)))
        if observed != expected:
            missing = tuple(sorted(set(expected) - set(observed)))
            orphan = tuple(sorted(set(observed) - set(expected)))
            raise EtabsFrameEq713PopulationError(
                "captured Frame scope does not exactly partition FrameObj.GetNameList; "
                f"missing={missing!r}; orphan={orphan!r}"
            )

        object_types = tuple(
            sorted(self.object_type_facts, key=lambda item: item.frame_name)
        )
        if object_types:
            object_type_names = tuple(item.frame_name for item in object_types)
            if len(object_type_names) != len(set(object_type_names)):
                raise EtabsFrameEq713PopulationError(
                    "duplicate Frame object-type factual identity"
                )
            if object_type_names != expected:
                missing = tuple(sorted(set(expected) - set(object_type_names)))
                orphan = tuple(sorted(set(object_type_names) - set(expected)))
                raise EtabsFrameEq713PopulationError(
                    "Frame object-type denominator is not exact; "
                    f"missing={missing!r}; orphan={orphan!r}"
                )

        residual = tuple(
            sorted(
                self.residual_structural_facts,
                key=lambda item: item.frame_name,
            )
        )
        residual_names = tuple(item.frame_name for item in residual)
        if len(residual_names) != len(set(residual_names)):
            raise EtabsFrameEq713PopulationError(
                "duplicate residual structural factual identity"
            )
        invalid_residual = tuple(
            sorted(set(residual_names) - set(out_of_slice_names))
        )
        if invalid_residual:
            raise EtabsFrameEq713PopulationError(
                "residual structural facts must belong to out-of-slice Frames: "
                f"{invalid_residual!r}"
            )

        object.__setattr__(self, "expected_frame_names", expected)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "out_of_slice_rows", out_of_slice)
        object.__setattr__(self, "object_type_facts", object_types)
        material_snapshot = self.material_snapshot
        if material_snapshot is not None:
            if not isinstance(
                material_snapshot,
                FrameFlexuralBaseCaptureSnapshot,
            ):
                raise TypeError(
                    "material_snapshot must be FrameFlexuralBaseCaptureSnapshot or None"
                )
            if (
                material_snapshot.session_provenance_ref
                not in tuple(self.source_refs)
            ):
                raise EtabsFrameEq713PopulationError(
                    "material snapshot provenance is not bound to Frame population"
                )

        line_spring_universe = self.line_spring_property_universe
        if line_spring_universe is not None:
            if not isinstance(
                line_spring_universe,
                LineSpringPropertyUniverseFact,
            ):
                raise TypeError(
                    "line_spring_property_universe must be "
                    "LineSpringPropertyUniverseFact or None"
                )
            if (
                line_spring_universe.evidence_ref
                not in tuple(self.source_refs)
            ):
                raise EtabsFrameEq713PopulationError(
                    "line-spring property universe provenance "
                    "is not bound to Frame population"
                )

        object.__setattr__(self, "residual_structural_facts", residual)
        object.__setattr__(
            self,
            "line_spring_property_universe",
            line_spring_universe,
        )
        object.__setattr__(self, "material_snapshot", material_snapshot)
        object.__setattr__(self, "source_refs", _refs(self.source_refs))

    @property
    def supported_rows(self) -> tuple[FrameEq713FactualFact, ...]:
        return self.rows

    @property
    def object_type_by_name(self) -> Mapping[str, FrameEq713ObjectTypeFact]:
        return {item.frame_name: item for item in self.object_type_facts}

    @property
    def residual_structural_by_name(
        self,
    ) -> Mapping[str, FrameEq713ResidualStructuralFact]:
        return {
            item.frame_name: item
            for item in self.residual_structural_facts
        }


def _capture_line_spring_property_universe_if_needed(
    context: TrustedLiveAcquisitionContext,
    object_type_facts: Sequence[FrameEq713ObjectTypeFact],
) -> LineSpringPropertyUniverseFact | None:
    has_null_frame = any(
        item.resolution is FrameEq713ObjectTypeResolution.RESOLVED
        and item.normalized_frame_type == "NULL"
        for item in object_type_facts
    )

    if not has_null_frame:
        return None

    return read_line_spring_property_universe_from_session(
        context.verified_session,
    )


def capture_frame_eq713_factual_population(
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    topology: StrictColumnTopologyBundle,
) -> FrameEq713FactualPopulation:
    """Capture the exact FrameObj universe and partition the supported RC factual slice."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    if not isinstance(owned_scratch, OwnedScratchContext):
        raise TypeError("owned_scratch must be OwnedScratchContext")
    if owned_scratch.source_model_identity != context.source_model_identity:
        raise EtabsFrameEq713PopulationError("owned scratch/context source identity mismatch")

    names, _raw_names = read_frame_names_from_session(context.verified_session)
    expected = tuple(sorted(names))
    roles = _role_map(topology)
    object_type_facts = _capture_frame_object_type_facts(
        context,
        expected,
    )
    line_spring_property_universe = (
        _capture_line_spring_property_universe_if_needed(
            context,
            object_type_facts,
        )
    )
    base_snapshot = capture_frame_flexural_base_snapshot(
        context=context,
        owned_scratch=owned_scratch,
    )
    supported_names, out_of_slice_rows = _capture_frame_scope_partition(
        context,
        base_snapshot,
        topology,
        expected,
    )
    residual_beam_names = tuple(
        scope.frame_name
        for scope in out_of_slice_rows
        if (
            scope.member_role == "BEAM"
            and scope.assigned_section_name is not None
            and scope.material_name is not None
        )
    )
    beam_mechanics_by_name = _capture_supported_beam_mechanics(
        context,
        owned_scratch,
        tuple(dict.fromkeys((*supported_names, *residual_beam_names))),
    )
    residual_structural_facts = _capture_residual_structural_facts(
        context,
        out_of_slice_rows,
        beam_mechanics_by_name,
    )

    material_cache: dict[str, IsotropicMaterialPropertiesFact] = {}
    property_modifier_cache: dict[str, FrameModifierReadFact] = {}
    section_mechanics_cache: dict[str, FrameSectionMechanicsFact] = {}
    rows: list[FrameEq713FactualFact] = []
    population_refs: list[str] = [
        f"CSI:FrameObj.GetNameList:COUNT:{len(expected)}",
        context.session_provenance_ref,
        owned_scratch.ownership_proof_ref,
    ]

    if line_spring_property_universe is not None:
        population_refs.append(
            line_spring_property_universe.evidence_ref
        )

    for scope in out_of_slice_rows:
        population_refs.extend(scope.source_refs)
    for object_type in object_type_facts:
        population_refs.extend(object_type.source_refs)
    for residual in residual_structural_facts:
        population_refs.extend(residual.source_refs)

    for name in supported_names:
        beam_mechanics = beam_mechanics_by_name.get(name)
        member_role = (
            "BEAM"
            if beam_mechanics is not None
            else roles.get(name)
        )
        if member_role is None:
            raise EtabsFrameEq713PopulationError(
                f"supported Frame {name!r} has no exact factual COLUMN/BEAM role"
            )
        base = bind_frame_flexural_base_fact_from_snapshot(
            base_snapshot,
            name,
        )
        section = base.assigned_section_name
        section_mechanics = section_mechanics_cache.get(section)
        if section_mechanics is None:
            section_mechanics = get_frame_section_mechanics_from_session(
                context.verified_session,
                section_name=section,
            )
            section_mechanics_cache[section] = section_mechanics
        if not section_mechanics.success or section_mechanics.section_name != section:
            raise EtabsFrameEq713PopulationError(
                f"PropFrame.GetSectProps failed or lost section identity for {section!r}"
            )
        prop = property_modifier_cache.get(section)
        if prop is None:
            prop = get_frame_modifiers_from_session(
                context.verified_session,
                surface=FrameModifierSurface.FRAME_SECTION_PROPERTY,
                target_name=section,
            )
            property_modifier_cache[section] = prop
        obj = get_frame_modifiers_from_session(
            context.verified_session,
            surface=FrameModifierSurface.FRAME_OBJECT,
            target_name=name,
        )
        releases = get_frame_releases_from_session(
            context.verified_session,
            frame_name=name,
        )
        material = material_cache.get(base.material_name)
        if material is None:
            material = get_isotropic_material_properties_from_session(
                context.verified_session,
                material_name=base.material_name,
            )
            material_cache[base.material_name] = material
        if not material.success:
            raise EtabsFrameEq713PopulationError(
                f"PropMaterial.GetMPIsotropic failed for {base.material_name!r}"
            )
        ec_mpa = _stress_to_mpa(
            material.modulus_of_elasticity,
            base.present_force_unit,
            base.present_length_unit,
            "PropMaterial.GetMPIsotropic.E",
        )
        gc_mpa = _stress_to_mpa(
            material.shear_modulus,
            base.present_force_unit,
            base.present_length_unit,
            "PropMaterial.GetMPIsotropic.G",
        )
        refs = (
            *base.source_refs,
            base.evidence_ref,
            section_mechanics.evidence_ref,
            prop.evidence_ref,
            obj.evidence_ref,
            releases.evidence_ref,
            material.evidence_ref,
        )
        row = FrameEq713FactualFact(
            frame_name=name,
            member_role=member_role,
            base_fact=base,
            section_mechanics=section_mechanics,
            property_modifiers=prop,
            object_modifiers=obj,
            releases=releases,
            isotropic_material=material,
            factual_ec_mpa=ec_mpa,
            factual_gc_mpa=gc_mpa,
            beam_mechanics=beam_mechanics,
            source_refs=tuple(
                (*refs, *(beam_mechanics.source_refs if beam_mechanics is not None else ()))
            ),
        )
        rows.append(row)
        population_refs.extend(row.source_refs)

    return FrameEq713FactualPopulation(
        expected_frame_names=expected,
        rows=tuple(rows),
        source_refs=tuple(dict.fromkeys(population_refs)),
        out_of_slice_rows=out_of_slice_rows,
        object_type_facts=object_type_facts,
        residual_structural_facts=residual_structural_facts,
        line_spring_property_universe=line_spring_property_universe,
        material_snapshot=(
            base_snapshot
            if isinstance(
                base_snapshot,
                FrameFlexuralBaseCaptureSnapshot,
            )
            else None
        ),
    )


__all__ = [
    "EtabsFrameEq713PopulationError",
    "FRAME_END_CONDITION_UNSUPPORTED",
    "FrameEq713BeamMechanicsFact",
    "FrameEq713ObjectTypeFact",
    "FrameEq713ObjectTypeResolution",
    "FrameEq713ResidualStructuralFact",
    "FrameEq713ScopeFact",
    "FrameEq713ScopeStatus",
    "FrameEq713FactualFact",
    "FrameEq713FactualPopulation",
    "NO_RELEASE_OR_PARTIAL_FIXITY_EFFECT",
    "TABLE_FRAME_ASSIGNMENTS_SUMMARY",
    "capture_frame_eq713_factual_population",
]
