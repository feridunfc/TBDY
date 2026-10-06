"""Typed factual contracts for exact CSI ETABS OAPI decoding.

These values describe only what the ETABS API returned. They contain no TBDY,
TS500, governing-selection, reinforcement-selection, or PASS/FAIL authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any


class EtabsOAPIError(RuntimeError):
    """Raised when an exact CSI call fails or its positional ABI is malformed."""


@dataclass(frozen=True, slots=True)
class SourceUnitProvenance:
    """Unit evidence for one property output or exact table FieldKey.

    This DTO performs no acquisition and supplies no SDK or report defaults.
    QUALIFIED is an explicit reviewed-evidence assertion, never inferred from
    a successful getter or a present-unit observation.
    """

    source_call: str
    subject_key: str
    output_key: str
    dimension: str
    source_unit: str | None = None
    authority_ref: str | None = None
    authority_version: str | None = None
    authority_kind: str = "UNVERIFIED"
    source_model_ref: str | None = None
    session_ref: str | None = None
    capture_ref: str | None = None
    raw_response_ref: str | None = None
    return_code: int | None = None
    unit_state_before: str | None = None
    unit_state_after: str | None = None
    qualification: str = "UNIT_UNQUALIFIED"
    reason: str = "SOURCE_UNIT_AUTHORITY_UNAVAILABLE"
    evidence_ref: str = field(init=False)

    def __post_init__(self) -> None:
        payload = {name: getattr(self, name) for name in self.__dataclass_fields__
                   if name != "evidence_ref"}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()
        object.__setattr__(self, "evidence_ref", "source-unit:sha256:" +
                           hashlib.sha256(encoded).hexdigest())

    def require(
        self, *, source_call: str, subject_key: str, output_key: str,
        dimension: str, source_model_ref: str | None = None,
        session_ref: str | None = None, capture_ref: str | None = None,
        raw_response_ref: str | None = None,
    ) -> str:
        if self.qualification != "QUALIFIED":
            raise EtabsOAPIError(f"UNIT_UNQUALIFIED:{self.reason}")
        expected_kind = ("REVIEWED_FIELD_UNIT_METADATA" if
                         source_call == "SapModel.DatabaseTables.GetAllFieldsInTable"
                         else "REVIEWED_PROPERTY_SOURCE_SEMANTICS")
        if self.authority_kind != expected_kind:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:NON_SOURCE_AUTHORITY")
        for name in ("source_unit", "authority_ref", "authority_version",
                     "source_model_ref", "session_ref", "capture_ref",
                     "raw_response_ref", "unit_state_before", "unit_state_after"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise EtabsOAPIError(f"UNIT_UNQUALIFIED:MISSING_{name.upper()}")
        if type(self.return_code) is not int or self.return_code != 0:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:RETURN_CODE")
        def state_identity(value: str) -> object:
            try:
                payload = json.loads(value)
            except (ValueError, TypeError):
                return value
            if isinstance(payload, dict):
                return {key: item for key, item in payload.items()
                        if key not in {"observed_utc", "observed_at_utc", "capture_utc", "raw_unit_reads"}}
            return payload

        if state_identity(self.unit_state_before) != state_identity(self.unit_state_after):
            raise EtabsOAPIError("UNIT_UNQUALIFIED:UNIT_DRIFT")
        expected = {"source_call": source_call, "subject_key": subject_key,
                    "output_key": output_key, "dimension": dimension,
                    "source_model_ref": source_model_ref, "session_ref": session_ref,
                    "capture_ref": capture_ref, "raw_response_ref": raw_response_ref}
        for name, value in expected.items():
            if value is not None and getattr(self, name) != value:
                raise EtabsOAPIError(f"UNIT_UNQUALIFIED:{name.upper()}_MISMATCH")
        return self.source_unit


@dataclass(frozen=True, slots=True)
class PointRestraintFact:
    point_name: str
    dofs: tuple[bool, bool, bool, bool, bool, bool]
    raw_response: object


@dataclass(frozen=True, slots=True)
class PointConnectivityItemFact:
    object_type: int
    object_name: str
    point_number: int


@dataclass(frozen=True, slots=True)
class PointConnectivityFact:
    point_name: str
    items: tuple[PointConnectivityItemFact, ...]
    raw_response: object

    @property
    def number_items(self) -> int:
        return len(self.items)


@dataclass(frozen=True, slots=True)
class RebarColumnFact:
    section_name: str
    mat_prop_long: str
    mat_prop_confine: str
    pattern: int
    confine_type: int
    cover: float
    number_c_bars: int
    number_r3_bars: int
    number_r2_bars: int
    rebar_size_name: str
    tie_size_name: str
    tie_spacing_longit: float
    number_2_dir_tie_bars: int
    number_3_dir_tie_bars: int
    to_be_designed: bool
    raw_response: object


@dataclass(frozen=True, slots=True)
class ResponseComboConstituentFact:
    index: int
    cname_type_code: int
    name: str
    scale_factor: float


@dataclass(frozen=True, slots=True)
class ResponseComboFact:
    name: str
    combo_type_code: int
    constituents: tuple[ResponseComboConstituentFact, ...]
    raw_get_type_combo: object
    raw_get_case_list: object


@dataclass(frozen=True, slots=True)
class ConcreteDesignSectionFact:
    frame_name: str
    section_name: str
    raw_response: object


@dataclass(frozen=True, slots=True)
class ConcreteColumnSummaryFact:
    frame_name: str
    number_items: int
    frame_names: tuple[str, ...]
    combo_names: tuple[str, ...]
    station_names: tuple[str, ...]
    pmm_area: tuple[float, ...]
    pmm_ratio: tuple[float, ...]
    pmm_combo: tuple[str, ...]
    av_major: tuple[float, ...]
    av_minor: tuple[float, ...]
    error_summary: tuple[str, ...]
    warning_summary: tuple[str, ...]
    raw_response: object


@dataclass(frozen=True, slots=True)
class AreaPropertyAssignmentFact:
    area_name: str
    property_name: str
    raw_response: object


@dataclass(frozen=True, slots=True)
class WallPropertyFact:
    property_name: str
    wall_type: int
    shell_type: int
    material_name: str
    thickness: float
    color: int
    notes: str
    guid: str
    raw_response: object
    return_code: int | None = None
    unit_provenance: tuple[SourceUnitProvenance, ...] = ()
    thickness_applicable: bool = True
    source_model_ref: str | None = None
    session_ref: str | None = None
    capture_ref: str | None = None
    unit_observation: str | None = None
    raw_response_ref: str = field(init=False)
    evidence_ref: str = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.raw_response, (tuple, list)):
            object.__setattr__(self, "raw_response", tuple(self.raw_response))
        if self.return_code is not None:
            if (not isinstance(self.raw_response, tuple) or len(self.raw_response) != 8
                    or type(self.raw_response[-1]) is not int
                    or self.raw_response[-1] != self.return_code
                    or tuple(self.raw_response[:4]) != (self.wall_type, self.shell_type,
                                                        self.material_name, self.thickness)):
                raise EtabsOAPIError("UNIT_UNQUALIFIED:RAW_WALL_PROPERTY_VALUE_MISMATCH")
        object.__setattr__(self, "unit_provenance", tuple(self.unit_provenance))
        raw = json.dumps(self.raw_response, sort_keys=True, default=str).encode()
        object.__setattr__(self, "raw_response_ref", "wall-raw:sha256:" + hashlib.sha256(raw).hexdigest())
        payload = (self.property_name, self.wall_type, self.shell_type, self.material_name,
                   self.thickness, self.raw_response, self.return_code,
                   self.thickness_applicable,
                   self.source_model_ref, self.session_ref, self.capture_ref, self.unit_observation,
                   tuple(item.evidence_ref for item in self.unit_provenance))
        encoded = json.dumps(payload, sort_keys=True, default=str).encode()
        object.__setattr__(self, "evidence_ref", "etabs-wall-property:sha256:" +
                           hashlib.sha256(encoded).hexdigest())

    def source_unit_for(self, output_key: str, dimension: str) -> SourceUnitProvenance:
        if (type(self.return_code) is not int or self.return_code != 0
                or not self.thickness_applicable or self.shell_type not in {1, 2, 3, 4, 5}
                or not self.raw_response):
            raise EtabsOAPIError("UNIT_UNQUALIFIED:WALL_THICKNESS_UNAVAILABLE_OR_INAPPLICABLE")
        if not all((self.source_model_ref, self.session_ref, self.capture_ref)):
            raise EtabsOAPIError("UNIT_UNQUALIFIED:MISSING_PROPERTY_CONTEXT")
        matches = [item for item in self.unit_provenance
                   if isinstance(item, SourceUnitProvenance) and item.output_key == output_key]
        if len(matches) != 1:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:MISSING_OR_DUPLICATE_OUTPUT_BINDING")
        binding = matches[0]
        binding.require(source_call="SapModel.PropArea.GetWall", subject_key=self.property_name,
                        output_key=output_key, dimension=dimension, source_model_ref=self.source_model_ref,
                        session_ref=self.session_ref, capture_ref=self.capture_ref,
                        raw_response_ref=self.raw_response_ref)
        return binding


__all__ = [
    "AreaPropertyAssignmentFact",
    "ConcreteColumnSummaryFact",
    "ConcreteDesignSectionFact",
    "EtabsOAPIError",
    "PointConnectivityFact",
    "PointConnectivityItemFact",
    "PointRestraintFact",
    "RebarColumnFact",
    "ResponseComboConstituentFact",
    "ResponseComboFact",
    "WallPropertyFact",
]
