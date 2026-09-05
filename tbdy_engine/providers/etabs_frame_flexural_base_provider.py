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

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import ntpath
from typing import Any, Mapping, Sequence
import uuid

from tbdy_engine.etabs.oapi import fetch_display_table_from_session
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

FRAME_FLEXURAL_BASE_FACT_CONTRACT = "ETABS_FRAME_FLEXURAL_BASE_FACT_V2"
FRAME_FLEXURAL_BASE_EVIDENCE_PREFIX = "etabs-frame-flexural-base:sha256:"
FRAME_FLEXURAL_BASE_SEMANTIC_REF_PREFIX = (
    "etabs-frame-flexural-base-semantic:sha256:"
)
FRAME_FLEXURAL_BASE_CAPTURE_EVENT_PREFIX = (
    "etabs-frame-flexural-base-capture:uuid4:"
)
SUPPORTED_FRAME_SECTION_SEMANTICS = "PRISMATIC_RECTANGULAR_RC_FRAME"

_FRAME_FLEXURAL_BASE_FACT_ISSUANCE_TOKEN = object()

# CSI ETABS v1 eForce/eLength documented integer values. Present units are the
# units used for data transmitted through the API; no unit setter is used here.
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
) -> tuple[Mapping[str, Any], ...]:
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
    if fetched.parsed.return_code not in (None, 0):
        raise FrameFlexuralBaseFactError(
            f"{table} returned nonzero code "
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
    return rows


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
    )


def capture_frame_flexural_base_fact(
    *,
    context: TrustedLiveAcquisitionContext,
    owned_scratch: OwnedScratchContext,
    component_unique_name: str,
) -> FrameFlexuralBaseFact:
    """Read one frame's immutable base-model flexural facts from the owned scratch."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    if not isinstance(owned_scratch, OwnedScratchContext):
        raise TypeError("owned_scratch must be OwnedScratchContext")
    component = _text(component_unique_name, "component_unique_name")
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
            "active ETABS model is not the exact owned scratch"
        )

    units_before = read_verified_unit_snapshot(context.verified_session)
    pf = _enum_int(units_before.present_force_unit, "force")
    pl = _enum_int(units_before.present_length_unit, "length")
    if pf not in _FORCE_TO_N or pl not in _LENGTH_TO_MM:
        raise FrameFlexuralBaseFactError(
            "present API force/length unit provenance is unsupported"
        )

    assignment_rows = _rows(context, TABLE_FRAME_ASSIGNMENTS)
    rectangle_rows = _rows(context, TABLE_RECTANGULAR)
    section_rows = _rows(context, TABLE_FRAME_SECTION_SUMMARY)
    basic_material_rows = _rows(context, TABLE_BASIC_MATERIAL)
    concrete_rows = _rows(context, TABLE_CONCRETE)

    assignment = _one(
        assignment_rows,
        ("UniqueName", "Unique Name"),
        component,
        "frame UniqueName",
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
    rectangle = _one(
        rectangle_rows,
        ("Name", "SectionName", "Section Name", "Property"),
        section,
        "rectangular section",
    )
    section_summary = _one(
        section_rows,
        ("Name", "Section Name", "Property"),
        section,
        "section summary",
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

    basic = _one(
        basic_material_rows,
        ("Material", "Name"),
        material,
        "basic material",
    )
    concrete = _one(
        concrete_rows,
        ("Material", "Name"),
        material,
        "concrete material",
    )
    t2_mm = _length_to_mm(
        _pick(rectangle, ("t2", "T2", "Width"), "t2"),
        pl,
        "t2",
    )
    t3_mm = _length_to_mm(
        _pick(rectangle, ("t3", "T3", "Depth"), "t3"),
        pl,
        "t3",
    )
    ec_mpa = _stress_to_mpa(
        _pick(
            basic,
            ("E1", "Elastic Modulus", "Modulus of Elasticity", "E"),
            "E1",
        ),
        pf,
        pl,
        "E1",
    )
    fck_mpa = _stress_to_mpa(
        _pick(
            concrete,
            ("Fc", "fck", "Concrete Strength"),
            "Fc",
        ),
        pf,
        pl,
        "Fc",
    )

    units_after = read_verified_unit_snapshot(context.verified_session)
    identity_after = reread_verified_session_identity(
        context.verified_session
    )
    if units_after != units_before:
        raise FrameFlexuralBaseFactError(
            "ETABS API unit state changed during factual capture"
        )
    if _canonical_path(identity_after.model_full_path) != _canonical_path(
        owned_scratch.scratch_path
    ):
        raise FrameFlexuralBaseFactError(
            "active ETABS model changed during factual capture"
        )

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
        source_model_ref=context.source_model_identity.source_model_ref,
        ownership_proof_ref=owned_scratch.ownership_proof_ref,
        acquisition_context_ref=context.acquisition_context_ref,
        session_provenance_ref=context.session_provenance_ref,
        capture_event_ref=_capture_event_ref(),
        present_force_unit=pf,
        present_length_unit=pl,
        source_rows=source_rows,
        source_refs=tuple(
            _row_ref(table, row)
            for table, row in source_rows
        ),
    )


__all__ = [
    "FRAME_FLEXURAL_BASE_FACT_CONTRACT",
    "SUPPORTED_FRAME_SECTION_SEMANTICS",
    "FrameFlexuralBaseFact",
    "FrameFlexuralBaseFactError",
    "capture_frame_flexural_base_fact",
]
