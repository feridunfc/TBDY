"""Typed factual ``PropFrame.GetSectProps`` read boundary for Frame mechanics.

This module records only ETABS section-property facts.  It owns no participation,
Eq.7.13, or engineering-policy semantics and exposes no second ETABS access path.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import math
import ntpath
import uuid
from typing import Any, TYPE_CHECKING

from tbdy_engine.etabs.safety import (
    EtabsVerifiedSession, _execute_verified_read, read_session_identity,
)
from tbdy_engine.etabs.source_units import EtabsSourceUnitError, decode_csi_length_unit

from .contracts import EtabsOAPIError, SourceUnitProvenance

if TYPE_CHECKING:
    from tbdy_engine.integration.live_etabs_acquisition_context import TrustedLiveAcquisitionContext
    from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext


FRAME_SECTION_MECHANICS_FACT_CONTRACT = "ETABS_FRAME_SECTION_MECHANICS_FACT_V2"
FRAME_SECTION_MECHANICS_EVIDENCE_PREFIX = "etabs-frame-section-mechanics:sha256:"
FRAME_SECTION_MECHANICS_SOURCE_CALL = "SapModel.PropFrame.GetSectProps"
FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_REF = "COLUMN_R1_GETSECTPROPS_PRESENT_L4_POLICY_V1"
FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_VERSION = (
    "SOURCE_AUTHORIZED_V1_20261009;CSI_ETABSv1_2024_PRESENT_L4"
)


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
    context: TrustedLiveAcquisitionContext | None = None,
    owned_scratch: OwnedScratchContext | None = None,
) -> FrameSectionMechanicsFact:
    """Retrieve factual Area/As2/As3/J/I22/I33 values for one Frame section."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    name = _text(section_name, "section_name")
    timeout = float(timeout_seconds)
    if not math.isfinite(timeout) or timeout <= 0.0:
        raise ValueError("timeout_seconds must be finite and greater than zero")

    # Reuse Q1N's native-property capture pattern, with independent method and
    # output authority. Present length is observed, never changed or inferred.
    identity = session.identity
    if identity.program_version != "23.2.0" or identity.program_api_version != 2.014:
        raise EtabsOAPIError("UNIT_UNQUALIFIED:UNREVIEWED_COMPATIBILITY_SCOPE")
    pid = identity.process_id
    if type(pid) is not int or pid <= 0:
        raise EtabsOAPIError("UNIT_UNQUALIFIED:MISSING_SESSION_IDENTITY")
    gateway = session._gateway_session
    expected_path = _text(identity.model_full_path, "source_model_ref")
    source_ref = expected_path
    session_ref = f"etabs-session:pid:{pid}"
    bridge: dict[str, object] = {}
    source_identity = None
    if context is not None or owned_scratch is not None:
        from tbdy_engine.integration.live_etabs_acquisition_context import TrustedLiveAcquisitionContext
        from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext
        if not isinstance(context, TrustedLiveAcquisitionContext) or not isinstance(owned_scratch, OwnedScratchContext):
            raise EtabsOAPIError("UNIT_UNQUALIFIED:MISSING_OWNED_CAPTURE_CONTEXT")
        if context.verified_session is not session:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:SESSION_MISMATCH")
        if context.source_model_identity != owned_scratch.source_model_identity:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:SOURCE_MODEL_MISMATCH")
        if ntpath.normcase(ntpath.normpath(identity.model_full_path)) != context.source_model_identity.normalized_model_reference:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:SOURCE_MODEL_MISMATCH")
        source_identity = context.source_model_identity
        expected_path = owned_scratch.scratch_path
        source_ref = context.source_model_identity.source_model_ref
        session_ref = context.session_provenance_ref
        bridge = {"source_model_ref": source_ref, "session_ref": session_ref,
                  "acquisition_context_ref": context.acquisition_context_ref,
                  "ownership_proof_ref": owned_scratch.ownership_proof_ref,
                  "scratch_path": expected_path}
    capture_ref = f"property-capture:{uuid.uuid4().hex}"

    def observe(application: object, model_api: Any) -> tuple[object, str, str]:
        if session.identity != identity or session._gateway_session is not gateway:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:SESSION_MISMATCH")
        if bridge:
            # Factory-issued frozen context must remain the same origin even
            # while the active model is the owned scratch, exactly as in Q1N.
            current_bridge = {
                "source_model_ref": context.source_model_identity.source_model_ref,
                "session_ref": context.session_provenance_ref,
                "acquisition_context_ref": context.acquisition_context_ref,
                "ownership_proof_ref": owned_scratch.ownership_proof_ref,
                "scratch_path": owned_scratch.scratch_path,
            }
            if (context.verified_session is not session
                    or context.source_model_identity != source_identity
                    or context.source_model_identity != owned_scratch.source_model_identity
                    or current_bridge != bridge):
                raise EtabsOAPIError("UNIT_UNQUALIFIED:OWNED_CAPTURE_CONTEXT_DRIFT")
        try:
            current = read_session_identity(application, model_api,
                                            process_id=pid, attach_strategy=identity.attach_strategy)
        except Exception as exc:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:MISSING_FRESH_OBSERVATION") from exc
        if current is None or current.process_id != pid:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:SESSION_MISMATCH")
        if ntpath.normcase(ntpath.normpath(current.model_full_path)) != ntpath.normcase(ntpath.normpath(expected_path)):
            raise EtabsOAPIError("UNIT_UNQUALIFIED:ACTIVE_MODEL_MISMATCH")
        if current.program_version != identity.program_version or current.program_api_version != identity.program_api_version:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:SESSION_MISMATCH")
        units = current.units
        if units is None or units.present_observation_status != "OBSERVED_CONSISTENT":
            raise EtabsOAPIError("UNIT_UNQUALIFIED:MISSING_PRESENT_UNIT_OBSERVATION")
        try:
            source_unit = f"{decode_csi_length_unit(units.present_length_unit).value}4"
        except EtabsSourceUnitError as exc:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:UNSUPPORTED_PRESENT_LENGTH_UNIT") from exc
        state = json.dumps({"active_identity": current.as_dict(),
                            "same_capture_bridge": bridge}, sort_keys=True)
        return current, state, source_unit

    def acquire(application: object, model_api: Any) -> FrameSectionMechanicsFact:
        before, state_before, source_unit = observe(application, model_api)
        raw = model_api.PropFrame.GetSectProps(name)
        after, state_after, unit_after = observe(application, model_api)
        if before != after or source_unit != unit_after:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:CAPTURE_STATE_DRIFT")
        area, as2, as3, torsion, i22, i33, return_code = _decode_get_sect_props(raw)
        fact = FrameSectionMechanicsFact(
            section_name=name,
            area=area,
            shear_area_2=as2,
            shear_area_3=as3,
            torsional_constant=torsion,
            inertia_22=i22,
            inertia_33=i33,
            return_code=return_code,
            raw_response=tuple(raw),
            source_model_ref=source_ref,
            session_ref=session_ref,
            capture_ref=capture_ref,
            unit_observation=json.dumps({"before": json.loads(state_before),
                                         "after": json.loads(state_after)}, sort_keys=True),
        )
        if return_code != 0:
            return fact
        provenance = tuple(SourceUnitProvenance(
            source_call=FRAME_SECTION_MECHANICS_SOURCE_CALL, subject_key=name,
            output_key=key, dimension="L4", source_unit=source_unit,
            authority_ref=FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_REF,
            authority_version=FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_VERSION,
            authority_kind="REVIEWED_PROPERTY_SOURCE_SEMANTICS",
            source_model_ref=source_ref, session_ref=session_ref, capture_ref=capture_ref,
            raw_response_ref=fact.raw_response_ref, return_code=return_code,
            unit_state_before=state_before, unit_state_after=state_after,
            qualification="QUALIFIED", reason="SOURCE_AUTHORIZED_GETSECTPROPS_PRESENT_L4",
        ) for key in ("I22", "I33"))
        qualified = replace(fact, unit_provenance=provenance)
        for key in ("I22", "I33"):
            qualified.source_unit_for(key, "L4")
        return qualified

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
    "FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_REF",
    "FRAME_SECTION_INERTIA_SOURCE_AUTHORITY_VERSION",
    "FrameSectionMechanicsFact",
    "get_frame_section_mechanics_from_session",
]
