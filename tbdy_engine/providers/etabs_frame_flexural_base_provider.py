"""Source-bound factual ETABS inputs for one supported RC frame flexural item.

This provider is deliberately non-regulatory. It reads only the existing
verified DatabaseTables source through the session-bound OAPI boundary and
binds one frame object to its assigned rectangular section, material, concrete
Fc and Basic Mechanical Properties E1. No caller can supply Ec or inertia.

Positive factual objects are provider-issued only. Each acquisition carries a
fresh capture-event reference so a PRE fact can be causally committed into a
later AnalysisStateIdentity; deterministic semantic equality is represented by
``semantic_state_ref`` and intentionally excludes acquisition-event provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
import hashlib
import json
import ntpath
from types import MappingProxyType
from typing import Any, Mapping, Sequence
import uuid

from tbdy_engine.etabs.oapi import fetch_display_table_from_session
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError, SourceUnitProvenance
from tbdy_engine.etabs.oapi.database_tables import (
    DisplayTableFetchResult,
    bind_display_table_field_units,
    fetch_table_field_metadata_from_session,
)
from tbdy_engine.etabs.safety import (
    RuntimeCaptureStatus,
    read_verified_unit_snapshot,
    reread_verified_session_identity,
)
from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext
from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
)

TABLE_FRAME_ASSIGNMENTS = "Frame Assignments - Section Properties"
TABLE_RECTANGULAR = "Frame Section Property Definitions - Concrete Rectangular"
TABLE_FRAME_SECTION_SUMMARY = "Frame Section Property Definitions - Summary"
TABLE_BASIC_MATERIAL = "Material Properties - Basic Mechanical Properties"
TABLE_CONCRETE = "Material Properties - Concrete Data"

# Use the same alias selector as factual quantity binding, retaining the exact
# selected display FieldKey rather than substituting an alias as authority.
_DIMENSIONAL_FIELDS = {
    TABLE_RECTANGULAR: ((("t2", "T2", "Width"), "L"),
                        (("t3", "T3", "Depth"), "L")),
    TABLE_BASIC_MATERIAL: ((("E1", "Elastic Modulus", "Modulus of Elasticity", "E"), "F/L2"),
                           (("G12", "Shear Modulus", "G"), "F/L2")),
    TABLE_CONCRETE: ((("Fc", "fck", "Concrete Strength"), "F/L2"),),
}

FRAME_FLEXURAL_BASE_FACT_CONTRACT = "ETABS_FRAME_FLEXURAL_BASE_FACT_V3"
FRAME_FLEXURAL_BASE_EVIDENCE_PREFIX = "etabs-frame-flexural-base:sha256:"
FRAME_FLEXURAL_BASE_SEMANTIC_REF_PREFIX = (
    "etabs-frame-flexural-base-semantic:sha256:"
)
FRAME_FLEXURAL_BASE_CAPTURE_EVENT_PREFIX = (
    "etabs-frame-flexural-base-capture:uuid4:"
)
SUPPORTED_FRAME_SECTION_SEMANTICS = "PRISMATIC_RECTANGULAR_RC_FRAME"

_FRAME_FLEXURAL_BASE_FACT_ISSUANCE_TOKEN = object()
_FRAME_FLEXURAL_BASE_SNAPSHOT_ISSUANCE_TOKEN = object()

# CSI enum factors are conversion primitives only. They are not authority
# for the source unit of a table field or a separately acquired property.
_FORCE_TO_N = {
    1: Decimal("4.4482216152605"),   # lb
    2: Decimal("4448.2216152605"),  # kip
    3: Decimal("1"),                # N
    4: Decimal("1000"),             # kN
    5: Decimal("9.80665"),          # kgf
    6: Decimal("9806.65"),          # tonf
}
_LENGTH_TO_MM = {
    1: Decimal("25.4"),    # inch
    2: Decimal("304.8"),   # ft
    3: Decimal("0.001"),   # micron
    4: Decimal("1"),       # mm
    5: Decimal("10"),      # cm
    6: Decimal("1000"),    # m
}


class FrameFlexuralBaseFactError(RuntimeError):
    """Fail-closed factual acquisition/binding error."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FrameFlexuralBaseFactError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise FrameFlexuralBaseFactError(f"{label} must be numeric")
    try:
        result = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise FrameFlexuralBaseFactError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise FrameFlexuralBaseFactError(f"{label} must be finite")
    return result


def _enum_int(value: object, label: str) -> int:
    candidate = getattr(value, "value", value)
    if isinstance(candidate, bool):
        raise FrameFlexuralBaseFactError(f"{label} unit enum is invalid")
    try:
        return int(candidate)
    except (TypeError, ValueError) as exc:
        raise FrameFlexuralBaseFactError(
            f"{label} unit enum is unavailable"
        ) from exc


def _stress_to_mpa(
    value: object,
    force_unit: object,
    length_unit: object,
    label: str,
) -> Decimal:
    force = _FORCE_TO_N.get(_enum_int(force_unit, "force"))
    length = _LENGTH_TO_MM.get(_enum_int(length_unit, "length"))
    if force is None or length is None:
        raise FrameFlexuralBaseFactError(
            "unsupported/not-applicable ETABS present force/length units"
        )
    # N/mm^2 is MPa.
    return _decimal(value, label) * force / (length * length)


def _length_to_mm(
    value: object,
    length_unit: object,
    label: str,
) -> Decimal:
    factor = _LENGTH_TO_MM.get(_enum_int(length_unit, "length"))
    if factor is None:
        raise FrameFlexuralBaseFactError(
            "unsupported/not-applicable ETABS present length unit"
        )
    return _decimal(value, label) * factor



def _qualified_quantity(value: object, binding: SourceUnitProvenance, dimension: str) -> Decimal:
    if not isinstance(binding, SourceUnitProvenance):
        raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:MISSING_BINDING")
    try:
        unit = binding.require(source_call=binding.source_call, subject_key=binding.subject_key,
                               output_key=binding.output_key, dimension=dimension)
    except EtabsOAPIError as exc:
        raise FrameFlexuralBaseFactError(str(exc)) from exc
    lengths = {"mm": 4, "cm": 5, "m": 6}
    stresses = {"MPa": (3, 4), "N/mm2": (3, 4), "N/mm^2": (3, 4),
                "Pa": (3, 6), "N/m2": (3, 6), "N/m^2": (3, 6),
                "kN/m2": (4, 6), "kN/m^2": (4, 6)}
    if dimension == "L" and unit in lengths:
        return _length_to_mm(value, lengths[unit], binding.output_key)
    if dimension == "F/L2" and unit in stresses:
        return _stress_to_mpa(value, *stresses[unit], binding.output_key)
    raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:UNKNOWN_OR_WRONG_DIMENSION_UNIT")


def _selected_field_key(
    row: Mapping[str, Any], aliases: Sequence[str], *, require_value: bool = True,
) -> str:
    empty_key = None
    for alias in aliases:
        matches = [key for key in row if str(key).strip().casefold() == alias.strip().casefold()]
        if len(matches) > 1:
            raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:AMBIGUOUS_FIELD_KEY")
        if matches and row[matches[0]] not in (None, ""):
            return matches[0]
        if matches and empty_key is None:
            empty_key = matches[0]
    if not require_value and empty_key is not None:
        return empty_key
    raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:MISSING_FIELD_VALUE")


def _table_quantity(
    snapshot: FrameFlexuralBaseCaptureSnapshot, table: str,
    row: Mapping[str, Any], aliases: Sequence[str], dimension: str,
    conversions: list[Mapping[str, Any]] | None = None,
) -> Decimal:
    key = _selected_field_key(row, aliases)
    bindings = getattr(snapshot, "table_unit_provenance", {}).get(table, ())
    if (any(not isinstance(item, SourceUnitProvenance) for item in bindings)
            or len({item.output_key for item in bindings}) != len(bindings)):
        raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:DUPLICATE_OR_INVALID_FIELD_METADATA")
    matches = [item for item in bindings if isinstance(item, SourceUnitProvenance) and item.output_key == key]
    metadata_ref = getattr(snapshot, "table_metadata_refs", {}).get(table)
    if len(matches) != 1 or not metadata_ref:
        raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:MISSING_OR_DUPLICATE_FIELD_METADATA")
    binding = matches[0]
    try:
        binding.require(source_call="SapModel.DatabaseTables.GetAllFieldsInTable",
                        subject_key=table, output_key=key, dimension=dimension,
                        source_model_ref=snapshot.source_model_ref, session_ref=snapshot.session_provenance_ref,
                        capture_ref=snapshot.acquisition_context_ref, raw_response_ref=metadata_ref)
    except EtabsOAPIError as exc:
        raise FrameFlexuralBaseFactError(str(exc)) from exc
    normalized = _qualified_quantity(row[key], binding, dimension)
    if conversions is not None:
        conversions.append({"table": table, "field_key": key, "raw_value": str(row[key]),
                            "source_unit": binding.source_unit,
                            "canonical_unit": "mm" if dimension == "L" else "MPa",
                            "normalized_value": str(normalized),
                            "factor": str(_qualified_quantity(1, binding, dimension)),
                            "unit_evidence_ref": binding.evidence_ref})
    return normalized


def _property_stress_to_mpa(
    material: Any, output_key: str, *, source_model_ref: str | None = None,
    session_ref: str | None = None, conversions: list[Mapping[str, Any]] | None = None,
) -> Decimal:
    if output_key not in {"E", "G"}:
        raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:UNSUPPORTED_MATERIAL_OUTPUT")
    try:
        binding = material.source_unit_for(output_key, "F/L2")
        if source_model_ref is None or session_ref is None:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:MISSING_CONSUMER_CONTEXT")
        binding.require(source_call="SapModel.PropMaterial.GetMPIsotropic",
                        subject_key=material.material_name, output_key=output_key, dimension="F/L2",
                        source_model_ref=source_model_ref, session_ref=session_ref)
    except (EtabsOAPIError, AttributeError) as exc:
        raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:" + str(exc)) from exc
    value = material.modulus_of_elasticity if output_key == "E" else material.shear_modulus
    result = _qualified_quantity(value, binding, "F/L2")
    if conversions is not None:
        conversions.append({"method": binding.source_call, "output_key": output_key,
                            "raw_value": str(value), "source_unit": binding.source_unit,
                            "canonical_unit": "MPa", "normalized_value": str(result),
                            "factor": str(_qualified_quantity(1, binding, "F/L2")),
                            "unit_evidence_ref": binding.evidence_ref})
    return result


def _canonical_path(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(_text(value, "model_path")))


def _canonical_row(row: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(row),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def _row_ref(table: str, row: Mapping[str, Any]) -> str:
    payload = f"{table}\x1f{_canonical_row(row)}".encode("utf-8")
    return "etabs-table-row:sha256:" + hashlib.sha256(payload).hexdigest()


def _sha_ref(prefix: str, payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()


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
        raise FrameFlexuralBaseFactError(f"missing {label}")
    return None


def _rows(
    context: TrustedLiveAcquisitionContext,
    table: str,
) -> DisplayTableFetchResult:
    fetched = fetch_display_table_from_session(
        context.verified_session,
        table,
        max_rows=None,
    )
    if fetched.capture_status is not RuntimeCaptureStatus.FULL:
        raise FrameFlexuralBaseFactError(
            f"{table} requires FULL capture; "
            f"got {fetched.capture_status.value}"
        )
    if type(fetched.parsed.return_code) is not int or fetched.parsed.return_code != 0:
        raise FrameFlexuralBaseFactError(
            f"UNIT_UNQUALIFIED:{table} missing/nonzero table return code "
            f"{fetched.parsed.return_code}"
        )
    rows = tuple(fetched.parsed.rows)
    if (
        fetched.parsed.row_count_reported is not None
        and len(rows) != int(fetched.parsed.row_count_reported)
    ):
        raise FrameFlexuralBaseFactError(
            f"{table} captured/reported row count mismatch"
        )
    return fetched


def _one(
    rows: Sequence[Mapping[str, Any]],
    aliases: Sequence[str],
    wanted: str,
    label: str,
) -> Mapping[str, Any]:
    matches = tuple(
        row
        for row in rows
        if str(_pick(row, aliases, label, required=False) or "").strip()
        == wanted
    )
    if len(matches) != 1:
        raise FrameFlexuralBaseFactError(
            f"expected exactly one {label}={wanted!r}; got {len(matches)}"
        )
    return matches[0]


def _capture_event_ref() -> str:
    return FRAME_FLEXURAL_BASE_CAPTURE_EVENT_PREFIX + uuid.uuid4().hex


def _freeze_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    return tuple(MappingProxyType(dict(row)) for row in rows)


def _index_unique_rows(
    rows: Sequence[Mapping[str, Any]],
    aliases: Sequence[str],
    label: str,
) -> Mapping[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        value = _pick(row, aliases, label, required=False)
        if value in (None, ""):
            raise FrameFlexuralBaseFactError(f"missing {label}")
        key = _text(str(value).strip(), label)
        if key in index:
            raise FrameFlexuralBaseFactError(
                f"duplicate {label} identity {key!r}"
            )
        index[key] = row
    return MappingProxyType(index)


@dataclass(frozen=True, slots=True, init=False)
class FrameFlexuralBaseCaptureSnapshot:
    """Provider-issued immutable five-table factual capture for Frame base facts."""

    source_model_ref: str
    ownership_proof_ref: str
    acquisition_context_ref: str
    session_provenance_ref: str
    scratch_path: str
    present_force_unit: int
    present_length_unit: int
    assignment_rows: tuple[Mapping[str, Any], ...]
    rectangular_rows: tuple[Mapping[str, Any], ...]
    section_summary_rows: tuple[Mapping[str, Any], ...]
    basic_material_rows: tuple[Mapping[str, Any], ...]
    concrete_rows: tuple[Mapping[str, Any], ...]
    assignment_by_frame: Mapping[str, Mapping[str, Any]]
    rectangular_by_section: Mapping[str, Mapping[str, Any]]
    section_summary_by_section: Mapping[str, Mapping[str, Any]]
    basic_material_by_name: Mapping[str, Mapping[str, Any]]
    concrete_material_by_name: Mapping[str, Mapping[str, Any]]
    table_unit_provenance: Mapping[str, tuple[SourceUnitProvenance, ...]]
    table_metadata_refs: Mapping[str, str]
    table_metadata_raw: Mapping[str, tuple[object, ...]]

    def __init__(
        self,
        *,
        _issuance_token: object = None,
        source_model_ref: str,
        ownership_proof_ref: str,
        acquisition_context_ref: str,
        session_provenance_ref: str,
        scratch_path: str,
        present_force_unit: int,
        present_length_unit: int,
        assignment_rows: Sequence[Mapping[str, Any]],
        rectangular_rows: Sequence[Mapping[str, Any]],
        section_summary_rows: Sequence[Mapping[str, Any]],
        basic_material_rows: Sequence[Mapping[str, Any]],
        concrete_rows: Sequence[Mapping[str, Any]],
        table_unit_provenance: Mapping[str, tuple[SourceUnitProvenance, ...]] | None = None,
        table_metadata_refs: Mapping[str, str] | None = None,
        table_metadata_raw: Mapping[str, tuple[object, ...]] | None = None,
    ) -> None:
        if _issuance_token is not _FRAME_FLEXURAL_BASE_SNAPSHOT_ISSUANCE_TOKEN:
            raise TypeError(
                "FrameFlexuralBaseCaptureSnapshot is provider-issued only; "
                "use capture_frame_flexural_base_snapshot"
            )
        for name, value in (
            ("source_model_ref", source_model_ref),
            ("ownership_proof_ref", ownership_proof_ref),
            ("acquisition_context_ref", acquisition_context_ref),
            ("session_provenance_ref", session_provenance_ref),
            ("scratch_path", scratch_path),
        ):
            object.__setattr__(self, name, _text(value, name))
        if type(present_force_unit) is not int:
            raise FrameFlexuralBaseFactError(
                "present_force_unit must be an integer enum value"
            )
        if type(present_length_unit) is not int:
            raise FrameFlexuralBaseFactError(
                "present_length_unit must be an integer enum value"
            )
        object.__setattr__(self, "present_force_unit", present_force_unit)
        object.__setattr__(self, "present_length_unit", present_length_unit)

        object.__setattr__(self, "table_unit_provenance", MappingProxyType({
            name: tuple(items) for name, items in (table_unit_provenance or {}).items()}))
        object.__setattr__(self, "table_metadata_refs", MappingProxyType(dict(table_metadata_refs or {})))
        object.__setattr__(self, "table_metadata_raw", MappingProxyType({
            name: tuple(items) for name, items in (table_metadata_raw or {}).items()}))

        frozen = {
            "assignment_rows": _freeze_rows(assignment_rows),
            "rectangular_rows": _freeze_rows(rectangular_rows),
            "section_summary_rows": _freeze_rows(section_summary_rows),
            "basic_material_rows": _freeze_rows(basic_material_rows),
            "concrete_rows": _freeze_rows(concrete_rows),
        }
        for name, value in frozen.items():
            object.__setattr__(self, name, value)

        object.__setattr__(
            self,
            "assignment_by_frame",
            _index_unique_rows(
                frozen["assignment_rows"],
                ("UniqueName", "Unique Name"),
                "frame UniqueName",
            ),
        )
        object.__setattr__(
            self,
            "rectangular_by_section",
            _index_unique_rows(
                frozen["rectangular_rows"],
                ("Name", "SectionName", "Section Name", "Property"),
                "rectangular section",
            ),
        )
        object.__setattr__(
            self,
            "section_summary_by_section",
            _index_unique_rows(
                frozen["section_summary_rows"],
                ("Name", "Section Name", "Property"),
                "section summary",
            ),
        )
        object.__setattr__(
            self,
            "basic_material_by_name",
            _index_unique_rows(
                frozen["basic_material_rows"],
                ("Material", "Name"),
                "basic material",
            ),
        )
        object.__setattr__(
            self,
            "concrete_material_by_name",
            _index_unique_rows(
                frozen["concrete_rows"],
                ("Material", "Name"),
                "concrete material",
            ),
        )


@dataclass(frozen=True, slots=True, init=False)
class FrameFlexuralBaseFact:
    """Factory-issued, source-bound canonical base-model factual snapshot."""

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
    acquisition_context_ref: str
    session_provenance_ref: str
    capture_event_ref: str
    present_force_unit: int
    present_length_unit: int
    source_rows: tuple[tuple[str, Mapping[str, Any]], ...]
    source_refs: tuple[str, ...]
    semantic_state_ref: str
    evidence_ref: str
    contract: str
    unit_conversions: tuple[Mapping[str, Any], ...]

    def __init__(
        self,
        *,
        _issuance_token: object = None,
        component_unique_name: str,
        assigned_section_name: str,
        material_name: str,
        section_semantics: str,
        t2_mm: Decimal,
        t3_mm: Decimal,
        concrete_fck_mpa: Decimal,
        etabs_ec_mpa: Decimal,
        source_model_ref: str,
        ownership_proof_ref: str,
        acquisition_context_ref: str,
        session_provenance_ref: str,
        capture_event_ref: str,
        present_force_unit: int,
        present_length_unit: int,
        source_rows: tuple[tuple[str, Mapping[str, Any]], ...],
        source_refs: tuple[str, ...],
        contract: str = FRAME_FLEXURAL_BASE_FACT_CONTRACT,
        unit_conversions: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        if _issuance_token is not _FRAME_FLEXURAL_BASE_FACT_ISSUANCE_TOKEN:
            raise TypeError(
                "FrameFlexuralBaseFact is provider-issued only; "
                "use capture_frame_flexural_base_fact"
            )
        if contract != FRAME_FLEXURAL_BASE_FACT_CONTRACT:
            raise FrameFlexuralBaseFactError(
                "frame flexural base fact contract mismatch"
            )

        text_fields = {
            "component_unique_name": component_unique_name,
            "assigned_section_name": assigned_section_name,
            "material_name": material_name,
            "source_model_ref": source_model_ref,
            "ownership_proof_ref": ownership_proof_ref,
            "acquisition_context_ref": acquisition_context_ref,
            "session_provenance_ref": session_provenance_ref,
            "capture_event_ref": capture_event_ref,
        }
        for name, value in text_fields.items():
            object.__setattr__(self, name, _text(value, name))

        if section_semantics != SUPPORTED_FRAME_SECTION_SEMANTICS:
            raise FrameFlexuralBaseFactError(
                "frame flexural base fact requires the supported "
                "prismatic rectangular RC section semantics"
            )
        object.__setattr__(
            self,
            "section_semantics",
            SUPPORTED_FRAME_SECTION_SEMANTICS,
        )

        for name, value in (
            ("t2_mm", t2_mm),
            ("t3_mm", t3_mm),
            ("concrete_fck_mpa", concrete_fck_mpa),
            ("etabs_ec_mpa", etabs_ec_mpa),
        ):
            if (
                not isinstance(value, Decimal)
                or not value.is_finite()
                or value <= 0
            ):
                raise FrameFlexuralBaseFactError(
                    f"{name} must be positive finite Decimal"
                )
            object.__setattr__(self, name, value)

        if not capture_event_ref.startswith(
            FRAME_FLEXURAL_BASE_CAPTURE_EVENT_PREFIX
        ):
            raise FrameFlexuralBaseFactError(
                "capture_event_ref does not use the canonical provider prefix"
            )
        event_suffix = capture_event_ref.removeprefix(
            FRAME_FLEXURAL_BASE_CAPTURE_EVENT_PREFIX
        )
        if len(event_suffix) != 32 or any(
            ch not in "0123456789abcdef" for ch in event_suffix
        ):
            raise FrameFlexuralBaseFactError(
                "capture_event_ref must contain a lowercase uuid4 hex token"
            )

        if type(present_force_unit) is not int:
            raise FrameFlexuralBaseFactError(
                "present_force_unit must be an integer enum value"
            )
        if type(present_length_unit) is not int:
            raise FrameFlexuralBaseFactError(
                "present_length_unit must be an integer enum value"
            )
        object.__setattr__(self, "present_force_unit", present_force_unit)
        object.__setattr__(self, "present_length_unit", present_length_unit)

        if type(source_rows) is not tuple or len(source_rows) != 5:
            raise FrameFlexuralBaseFactError(
                "frame flexural base fact requires exactly five source rows"
            )
        if type(source_refs) is not tuple or len(source_refs) != 5:
            raise FrameFlexuralBaseFactError(
                "frame flexural base fact requires exactly five source refs"
            )
        for table_name, row in source_rows:
            _text(table_name, "source table")
            if not isinstance(row, Mapping):
                raise FrameFlexuralBaseFactError(
                    "source rows must contain mappings"
                )
        for ref in source_refs:
            _text(ref, "source_ref")
        object.__setattr__(self, "source_rows", source_rows)
        object.__setattr__(self, "source_refs", source_refs)
        object.__setattr__(self, "contract", contract)
        object.__setattr__(self, "unit_conversions", tuple(MappingProxyType(dict(item)) for item in unit_conversions))

        semantic_payload = self.semantic_payload()
        semantic_state_ref = _sha_ref(
            FRAME_FLEXURAL_BASE_SEMANTIC_REF_PREFIX,
            semantic_payload,
        )
        object.__setattr__(
            self,
            "semantic_state_ref",
            semantic_state_ref,
        )

        evidence_payload = {
            "contract": contract,
            **semantic_payload,
            "acquisition_context_ref": self.acquisition_context_ref,
            "session_provenance_ref": self.session_provenance_ref,
            "capture_event_ref": self.capture_event_ref,
            "present_force_unit": self.present_force_unit,
            "present_length_unit": self.present_length_unit,
            "source_refs": list(self.source_refs),
            "unit_conversions": [dict(item) for item in self.unit_conversions],
        }
        object.__setattr__(
            self,
            "evidence_ref",
            _sha_ref(
                FRAME_FLEXURAL_BASE_EVIDENCE_PREFIX,
                evidence_payload,
            ),
        )

    def semantic_payload(self) -> dict[str, object]:
        """Canonical analysis-basis semantics, excluding event provenance."""
        return {
            "component_unique_name": self.component_unique_name,
            "assigned_section_name": self.assigned_section_name,
            "material_name": self.material_name,
            "section_semantics": self.section_semantics,
            "t2_mm": str(self.t2_mm),
            "t3_mm": str(self.t3_mm),
            "concrete_fck_mpa": str(self.concrete_fck_mpa),
            "etabs_ec_mpa": str(self.etabs_ec_mpa),
            "source_model_ref": self.source_model_ref,
            "ownership_proof_ref": self.ownership_proof_ref,
        }


def _issue_frame_flexural_base_fact(
    *,
    component_unique_name: str,
    assigned_section_name: str,
    material_name: str,
    t2_mm: Decimal,
    t3_mm: Decimal,
    concrete_fck_mpa: Decimal,
    etabs_ec_mpa: Decimal,
    source_model_ref: str,
    ownership_proof_ref: str,
    acquisition_context_ref: str,
    session_provenance_ref: str,
    capture_event_ref: str,
    present_force_unit: int,
    present_length_unit: int,
    source_rows: tuple[tuple[str, Mapping[str, Any]], ...],
    source_refs: tuple[str, ...],
    unit_conversions: Sequence[Mapping[str, Any]] = (),
) -> FrameFlexuralBaseFact:
    """Private issuance seam; tests may use it but production callers must not."""
    return FrameFlexuralBaseFact(
        _issuance_token=_FRAME_FLEXURAL_BASE_FACT_ISSUANCE_TOKEN,
        component_unique_name=component_unique_name,
        assigned_section_name=assigned_section_name,
        material_name=material_name,
        section_semantics=SUPPORTED_FRAME_SECTION_SEMANTICS,
        t2_mm=t2_mm,
        t3_mm=t3_mm,
        concrete_fck_mpa=concrete_fck_mpa,
        etabs_ec_mpa=etabs_ec_mpa,
        source_model_ref=source_model_ref,
        ownership_proof_ref=ownership_proof_ref,
        acquisition_context_ref=acquisition_context_ref,
        session_provenance_ref=session_provenance_ref,
        capture_event_ref=capture_event_ref,
        present_force_unit=present_force_unit,
        present_length_unit=present_length_unit,
        source_rows=source_rows,
        source_refs=source_refs,
        unit_conversions=unit_conversions,
    )


def capture_frame_flexural_base_snapshot(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
) -> FrameFlexuralBaseCaptureSnapshot:
    """Capture the five exact factual tables once for one verified owned scratch."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    if not isinstance(owned_scratch, OwnedScratchContext):
        raise TypeError("owned_scratch must be OwnedScratchContext")
    if context.source_model_identity != owned_scratch.source_model_identity:
        raise FrameFlexuralBaseFactError(
            "owned scratch/context source-model binding mismatch"
        )

    identity_before = reread_verified_session_identity(
        context.verified_session
    )
    if _canonical_path(identity_before.model_full_path) != _canonical_path(
        owned_scratch.scratch_path
    ):
        raise FrameFlexuralBaseFactError(
            "UNIT_UNQUALIFIED:active ETABS model is not the exact owned scratch"
        )
    expected_pid = context.verified_session.identity.process_id
    if type(expected_pid) is not int or expected_pid <= 0 or identity_before.process_id != expected_pid:
        raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:FIELD_METADATA_SESSION_MISMATCH")

    units_before = read_verified_unit_snapshot(context.verified_session)
    pf = _enum_int(units_before.present_force_unit, "force")
    pl = _enum_int(units_before.present_length_unit, "length")
    if pf not in _FORCE_TO_N or pl not in _LENGTH_TO_MM:
        raise FrameFlexuralBaseFactError(
            "present API force/length unit provenance is unsupported"
        )

    tables = {table: _rows(context, table) for table in (
        TABLE_FRAME_ASSIGNMENTS, TABLE_RECTANGULAR, TABLE_FRAME_SECTION_SUMMARY,
        TABLE_BASIC_MATERIAL, TABLE_CONCRETE)}
    # Each metadata read receives a fresh, caller-owned event nonce. Origin
    # path/PID/nonce are checked before bridging into the existing context refs.
    metadata_events = {}
    for table, requirements in _DIMENSIONAL_FIELDS.items():
        event_ref = f"field-metadata-capture:{uuid.uuid4().hex}"
        metadata = fetch_table_field_metadata_from_session(
            context.verified_session, table, capture_ref=event_ref
        )
        identity = context.verified_session.identity
        if (_canonical_path(metadata.source_model_ref or "") != _canonical_path(identity.model_full_path)
                or _canonical_path(identity.model_full_path) !=
                _canonical_path(context.source_model_identity.normalized_model_reference)):
            raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:FIELD_METADATA_MODEL_MISMATCH")
        if metadata.session_ref != f"etabs-session:pid:{identity.process_id}":
            raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:FIELD_METADATA_SESSION_MISMATCH")
        if metadata.capture_ref != event_ref:
            raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:FIELD_METADATA_CAPTURE_MISMATCH")
        dimensions = {}
        for aliases, dimension in requirements:
            if not tables[table].parsed.rows:
                raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:MISSING_FIELD_VALUE")
            for row in tables[table].parsed.rows:
                # G12 can be blank for unrelated materials. Bind its field
                # metadata without accepting a missing material quantity;
                # _table_quantity retains its required-value check.
                require_value = not (table == TABLE_BASIC_MATERIAL and aliases[0] == "G12")
                dimensions[_selected_field_key(row, aliases, require_value=require_value)] = dimension
        # Validate exact metadata and dimensions now, before any later table
        # read. These origin-bound bindings are not issued to a snapshot yet.
        state = json.dumps(units_before.as_dict(), sort_keys=True)
        try:
            bound = bind_display_table_field_units(
                tables[table], metadata, field_dimensions=dimensions,
                source_model_ref=metadata.source_model_ref,
                session_ref=metadata.session_ref, capture_ref=metadata.capture_ref,
                unit_state_before=state, unit_state_after=state,
            )
        except EtabsOAPIError as exc:
            raise FrameFlexuralBaseFactError(str(exc)) from exc
        if bound.field_unit_status != "QUALIFIED":
            reason = bound.field_unit_status
            raise FrameFlexuralBaseFactError(
                reason if reason.startswith("UNIT_UNQUALIFIED:") else "UNIT_UNQUALIFIED:" + reason
            )
        tables[table] = bound
        metadata_events[table] = metadata
    assignment_rows = tables[TABLE_FRAME_ASSIGNMENTS].parsed.rows
    rectangular_rows = tables[TABLE_RECTANGULAR].parsed.rows
    section_summary_rows = tables[TABLE_FRAME_SECTION_SUMMARY].parsed.rows
    basic_material_rows = tables[TABLE_BASIC_MATERIAL].parsed.rows
    concrete_rows = tables[TABLE_CONCRETE].parsed.rows

    units_after = read_verified_unit_snapshot(context.verified_session)
    identity_after = reread_verified_session_identity(
        context.verified_session
    )
    if units_after != units_before:
        raise FrameFlexuralBaseFactError(
            "UNIT_UNQUALIFIED:ETABS API unit state changed during factual capture"
        )
    if _canonical_path(identity_after.model_full_path) != _canonical_path(
        owned_scratch.scratch_path
    ):
        raise FrameFlexuralBaseFactError(
            "UNIT_UNQUALIFIED:active ETABS model changed during factual capture"
        )

    if identity_before.process_id != expected_pid or identity_after.process_id != expected_pid:
        raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:FIELD_METADATA_SESSION_MISMATCH")
    if identity_after != identity_before:
        raise FrameFlexuralBaseFactError("UNIT_UNQUALIFIED:active ETABS model state changed during factual capture")

    # The typed context and owned scratch, fresh session observations and the
    # per-read nonce establish equivalence. Preserve all original references
    # alongside that proof; never replace them without retained origin evidence.
    for table, metadata in metadata_events.items():
        bridge = {
            "metadata_origin": {"source_model_ref": metadata.source_model_ref,
                                "session_ref": metadata.session_ref,
                                "capture_ref": metadata.capture_ref},
            "context": {"source_model_ref": context.source_model_identity.source_model_ref,
                        "session_ref": context.session_provenance_ref,
                        "capture_ref": context.acquisition_context_ref},
            "ownership_proof_ref": owned_scratch.ownership_proof_ref,
            "scratch_path": owned_scratch.scratch_path,
            "active_model_before": identity_before.model_full_path,
            "active_model_after": identity_after.model_full_path,
            "process_id": expected_pid,
        }
        observation_before = json.dumps({**units_before.as_dict(),
                                         "same_capture_bridge": bridge}, sort_keys=True)
        observation_after = json.dumps({**units_after.as_dict(),
                                        "same_capture_bridge": bridge}, sort_keys=True)
        tables[table] = replace(tables[table], field_unit_provenance=tuple(
            replace(binding,
                    source_model_ref=context.source_model_identity.source_model_ref,
                    session_ref=context.session_provenance_ref,
                    capture_ref=context.acquisition_context_ref,
                    unit_state_before=observation_before,
                    unit_state_after=observation_after)
            for binding in tables[table].field_unit_provenance
        ))

    return FrameFlexuralBaseCaptureSnapshot(
        _issuance_token=_FRAME_FLEXURAL_BASE_SNAPSHOT_ISSUANCE_TOKEN,
        source_model_ref=context.source_model_identity.source_model_ref,
        ownership_proof_ref=owned_scratch.ownership_proof_ref,
        acquisition_context_ref=context.acquisition_context_ref,
        session_provenance_ref=context.session_provenance_ref,
        scratch_path=owned_scratch.scratch_path,
        present_force_unit=pf,
        present_length_unit=pl,
        assignment_rows=assignment_rows,
        rectangular_rows=rectangular_rows,
        section_summary_rows=section_summary_rows,
        basic_material_rows=basic_material_rows,
        concrete_rows=concrete_rows,
        table_unit_provenance={name: item.field_unit_provenance for name, item in tables.items()},
        table_metadata_refs={name: item.field_metadata_ref for name, item in tables.items()
                             if item.field_metadata_raw and item.field_unit_status == "QUALIFIED"},
        table_metadata_raw={name: item.field_metadata_raw for name, item in tables.items()},
    )


def bind_frame_flexural_base_fact_from_snapshot(
    snapshot: FrameFlexuralBaseCaptureSnapshot,
    component_unique_name: str,
) -> FrameFlexuralBaseFact:
    """Bind one existing FrameFlexuralBaseFact from one immutable provider snapshot."""
    if not isinstance(snapshot, FrameFlexuralBaseCaptureSnapshot):
        raise TypeError(
            "snapshot must be FrameFlexuralBaseCaptureSnapshot"
        )
    component = _text(component_unique_name, "component_unique_name")

    assignment = snapshot.assignment_by_frame.get(component)
    if assignment is None:
        raise FrameFlexuralBaseFactError(
            f"expected exactly one frame UniqueName={component!r}; got 0"
        )
    section = _text(
        str(
            _pick(
                assignment,
                ("SectProp", "Section Property"),
                "assigned section",
            )
        ).strip(),
        "assigned_section_name",
    )
    rectangle = snapshot.rectangular_by_section.get(section)
    if rectangle is None:
        raise FrameFlexuralBaseFactError(
            f"expected exactly one rectangular section={section!r}; got 0"
        )
    section_summary = snapshot.section_summary_by_section.get(section)
    if section_summary is None:
        raise FrameFlexuralBaseFactError(
            f"expected exactly one section summary={section!r}; got 0"
        )
    shape = str(
        _pick(section_summary, ("Shape",), "section shape")
    ).strip().casefold()
    if (
        "rect" not in shape
        or "nonprismatic" in shape
        or "variable" in shape
    ):
        raise FrameFlexuralBaseFactError(
            f"section {section!r} is not the supported "
            "prismatic rectangular slice"
        )

    material = _text(
        str(
            _pick(
                section_summary,
                ("Material", "Material Name"),
                "section material",
            )
        ).strip(),
        "material_name",
    )
    rectangle_material = _pick(
        rectangle,
        ("Material", "MaterialName", "Material Name"),
        "rectangle material",
        required=False,
    )
    if (
        rectangle_material not in (None, "")
        and str(rectangle_material).strip() != material
    ):
        raise FrameFlexuralBaseFactError(
            "rectangular section material disagrees with "
            "section summary material"
        )

    basic = snapshot.basic_material_by_name.get(material)
    if basic is None:
        raise FrameFlexuralBaseFactError(
            f"expected exactly one basic material={material!r}; got 0"
        )
    concrete = snapshot.concrete_material_by_name.get(material)
    if concrete is None:
        raise FrameFlexuralBaseFactError(
            f"expected exactly one concrete material={material!r}; got 0"
        )

    unit_conversions: list[Mapping[str, Any]] = []
    t2_mm = _table_quantity(snapshot, TABLE_RECTANGULAR, rectangle,
                            ("t2", "T2", "Width"), "L", unit_conversions)
    t3_mm = _table_quantity(snapshot, TABLE_RECTANGULAR, rectangle,
                            ("t3", "T3", "Depth"), "L", unit_conversions)
    ec_mpa = _table_quantity(snapshot, TABLE_BASIC_MATERIAL, basic,
                            ("E1", "Elastic Modulus", "Modulus of Elasticity", "E"),
                            "F/L2", unit_conversions)
    fck_mpa = _table_quantity(snapshot, TABLE_CONCRETE, concrete,
                             ("Fc", "fck", "Concrete Strength"), "F/L2", unit_conversions)

    source_rows = (
        (TABLE_FRAME_ASSIGNMENTS, assignment),
        (TABLE_RECTANGULAR, rectangle),
        (TABLE_FRAME_SECTION_SUMMARY, section_summary),
        (TABLE_BASIC_MATERIAL, basic),
        (TABLE_CONCRETE, concrete),
    )
    return _issue_frame_flexural_base_fact(
        component_unique_name=component,
        assigned_section_name=section,
        material_name=material,
        t2_mm=t2_mm,
        t3_mm=t3_mm,
        concrete_fck_mpa=fck_mpa,
        etabs_ec_mpa=ec_mpa,
        source_model_ref=snapshot.source_model_ref,
        ownership_proof_ref=snapshot.ownership_proof_ref,
        acquisition_context_ref=snapshot.acquisition_context_ref,
        session_provenance_ref=snapshot.session_provenance_ref,
        capture_event_ref=_capture_event_ref(),
        present_force_unit=snapshot.present_force_unit,
        present_length_unit=snapshot.present_length_unit,
        source_rows=source_rows,
        unit_conversions=unit_conversions,
        source_refs=tuple(
            _row_ref(table, row)
            for table, row in source_rows
        ),
    )


def capture_frame_flexural_base_fact(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    component_unique_name: str,
) -> FrameFlexuralBaseFact:
    """Canonical single-item API: capture one snapshot, then bind one fact."""
    snapshot = capture_frame_flexural_base_snapshot(
        context=context,
        owned_scratch=owned_scratch,
    )
    return bind_frame_flexural_base_fact_from_snapshot(
        snapshot,
        component_unique_name,
    )


__all__ = [
    "FRAME_FLEXURAL_BASE_FACT_CONTRACT",
    "SUPPORTED_FRAME_SECTION_SEMANTICS",
    "FrameFlexuralBaseCaptureSnapshot",
    "FrameFlexuralBaseFact",
    "FrameFlexuralBaseFactError",
    "bind_frame_flexural_base_fact_from_snapshot",
    "capture_frame_flexural_base_fact",
    "capture_frame_flexural_base_snapshot",
]
