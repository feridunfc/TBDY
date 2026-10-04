"""Typed factual ``PropFrame.GetSectProps`` read boundary for Frame mechanics.

This module records only ETABS section-property facts.  It owns no participation,
Eq.7.13, or engineering-policy semantics and exposes no second ETABS access path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import uuid
from typing import Any

from tbdy_engine.etabs.safety import EtabsVerifiedSession, _execute_verified_read

from .contracts import EtabsOAPIError, SourceUnitProvenance


FRAME_SECTION_MECHANICS_FACT_CONTRACT = "ETABS_FRAME_SECTION_MECHANICS_FACT_V2"
FRAME_SECTION_MECHANICS_EVIDENCE_PREFIX = "etabs-frame-section-mechanics:sha256:"
FRAME_SECTION_MECHANICS_SOURCE_CALL = "SapModel.PropFrame.GetSectProps"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EtabsOAPIError(f"{label} must be a nonblank canonical string")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EtabsOAPIError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EtabsOAPIError(f"{label} must be finite numeric")
    return result


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return FRAME_SECTION_MECHANICS_EVIDENCE_PREFIX + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class FrameSectionMechanicsFact:
    section_name: str
    area: float
    shear_area_2: float
    shear_area_3: float
    torsional_constant: float
    inertia_22: float
    inertia_33: float
    return_code: int
    source_call: str = FRAME_SECTION_MECHANICS_SOURCE_CALL
    evidence_ref: str = field(init=False)
    contract: str = FRAME_SECTION_MECHANICS_FACT_CONTRACT
    raw_response: tuple[object, ...] = ()
    unit_provenance: tuple[SourceUnitProvenance, ...] = ()
    source_model_ref: str | None = None
    session_ref: str | None = None
    capture_ref: str | None = None
    unit_observation: str | None = None
    raw_response_ref: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_response", tuple(self.raw_response))
        object.__setattr__(self, "unit_provenance", tuple(self.unit_provenance))
        if any(not isinstance(item, SourceUnitProvenance) for item in self.unit_provenance):
            raise EtabsOAPIError("UNIT_UNQUALIFIED:INVALID_PROVENANCE_TYPE")
        object.__setattr__(self, "raw_response_ref", _digest({"raw": self.raw_response}))
        object.__setattr__(self, "section_name", _text(self.section_name, "section_name"))
        for attribute in (
            "area",
            "shear_area_2",
            "shear_area_3",
            "torsional_constant",
            "inertia_22",
            "inertia_33",
        ):
            object.__setattr__(self, attribute, _number(getattr(self, attribute), attribute))
        if self.raw_response:
            expected = (self.area, self.shear_area_2, self.shear_area_3,
                        self.torsional_constant, self.inertia_22, self.inertia_33, self.return_code)
            if _decode_get_sect_props(self.raw_response) != expected:
                raise EtabsOAPIError("UNIT_UNQUALIFIED:RAW_PROPERTY_VALUE_MISMATCH")
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be an integer")
        if self.source_call != FRAME_SECTION_MECHANICS_SOURCE_CALL:
            raise EtabsOAPIError("frame section mechanics source_call mismatch")
        if self.contract != FRAME_SECTION_MECHANICS_FACT_CONTRACT:
            raise EtabsOAPIError("frame section mechanics fact contract mismatch")
        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                {
                    "contract": self.contract,
                    "raw_response_ref": self.raw_response_ref,
                    "unit_provenance": [item.evidence_ref for item in self.unit_provenance],
                    "source_model_ref": self.source_model_ref,
                    "session_ref": self.session_ref,
                    "capture_ref": self.capture_ref,
                    "unit_observation": self.unit_observation,
                    "section_name": self.section_name,
                    "area": self.area,
                    "shear_area_2": self.shear_area_2,
                    "shear_area_3": self.shear_area_3,
                    "torsional_constant": self.torsional_constant,
                    "inertia_22": self.inertia_22,
                    "inertia_33": self.inertia_33,
                    "return_code": self.return_code,
                    "source_call": self.source_call,
                }
            ),
        )

    def source_unit_for(self, output_key: str, dimension: str) -> SourceUnitProvenance:
        if not self.success or not self.raw_response:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:MISSING_SUCCESSFUL_RAW_RESPONSE")
        if not all((self.source_model_ref, self.session_ref, self.capture_ref)):
            raise EtabsOAPIError("UNIT_UNQUALIFIED:MISSING_PROPERTY_CONTEXT")
        matches = tuple(item for item in self.unit_provenance if item.output_key == output_key)
        if len(matches) != 1:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:MISSING_OR_DUPLICATE_OUTPUT_BINDING")
        binding = matches[0]
        binding.require(source_call="SapModel.PropFrame.GetSectProps", subject_key=self.section_name,
                        output_key=output_key, dimension=dimension,
                        source_model_ref=self.source_model_ref, session_ref=self.session_ref,
                        capture_ref=self.capture_ref, raw_response_ref=self.raw_response_ref)
        return binding

    @property
    def success(self) -> bool:
        return self.return_code == 0


def _decode_get_sect_props(
    raw: object,
) -> tuple[float, float, float, float, float, float, int]:
    if not isinstance(raw, (tuple, list)) or len(raw) != 13:
        raise EtabsOAPIError(
            f"PropFrame.GetSectProps returned unsupported Python ABI shape: {raw!r}"
        )
    items = tuple(raw)
    return_code = items[-1]
    if type(return_code) is not int:
        raise EtabsOAPIError(
            f"PropFrame.GetSectProps returned unsupported Python ABI shape: {raw!r}"
        )
    try:
        return (
            _number(items[0], "PropFrame.GetSectProps.Area"),
            _number(items[1], "PropFrame.GetSectProps.As2"),
            _number(items[2], "PropFrame.GetSectProps.As3"),
            _number(items[3], "PropFrame.GetSectProps.Torsion"),
            _number(items[4], "PropFrame.GetSectProps.I22"),
            _number(items[5], "PropFrame.GetSectProps.I33"),
            int(return_code),
        )
    except EtabsOAPIError as exc:
        raise EtabsOAPIError(
            f"PropFrame.GetSectProps returned unsupported Python ABI shape: {raw!r}; {exc}"
        ) from exc


def get_frame_section_mechanics_from_session(
    session: EtabsVerifiedSession,
    *,
    section_name: str,
    timeout_seconds: float = 30.0,
) -> FrameSectionMechanicsFact:
    """Retrieve factual Area/As2/As3/J/I22/I33 values for one Frame section."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    name = _text(section_name, "section_name")
    timeout = float(timeout_seconds)
    if not math.isfinite(timeout) or timeout <= 0.0:
        raise ValueError("timeout_seconds must be finite and greater than zero")

    def acquire(_application: object, model_api: Any) -> FrameSectionMechanicsFact:
        # Existing session observations only: no new ETABS unit/identity calls.
        identity = getattr(session, "identity", None)
        units = getattr(identity, "units", None)
        observed = json.dumps(units.as_dict(), sort_keys=True, default=str) if units else None
        raw = model_api.PropFrame.GetSectProps(name)
        area, as2, as3, torsion, i22, i33, return_code = _decode_get_sect_props(raw)
        return FrameSectionMechanicsFact(
            section_name=name,
            area=area,
            shear_area_2=as2,
            shear_area_3=as3,
            torsional_constant=torsion,
            inertia_22=i22,
            inertia_33=i33,
            return_code=return_code,
            raw_response=tuple(raw),
            source_model_ref=getattr(identity, "model_full_path", None),
            session_ref=(f"etabs-session:pid:{identity.process_id}" if identity else None),
            capture_ref=f"property-capture:{uuid.uuid4().hex}",
            unit_observation=observed,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation="oapi_prop_frame_get_sect_props",
        timeout_seconds=timeout,
    )


__all__ = [
    "FRAME_SECTION_MECHANICS_EVIDENCE_PREFIX",
    "FRAME_SECTION_MECHANICS_FACT_CONTRACT",
    "FRAME_SECTION_MECHANICS_SOURCE_CALL",
    "FrameSectionMechanicsFact",
    "get_frame_section_mechanics_from_session",
]
