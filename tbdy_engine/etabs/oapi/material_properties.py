"""Typed factual ``PropMaterial.GetMPIsotropic`` read boundary.

The supplied ETABS OAPI documentation directly names the retrieved isotropic
outputs as modulus of elasticity ``E``, Poisson ratio ``U``, thermal
coefficient ``A`` and shear modulus ``G`` at input temperature ``Temp``.
Those names are therefore ``DOCUMENTED FACT`` at this boundary.  No TS500
material qualification or engineering acceptability policy is performed here.
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
from tbdy_engine.etabs.source_units import (
    EtabsSourceUnitError, decode_csi_force_unit, decode_csi_length_unit,
)

from .contracts import EtabsOAPIError, SourceUnitProvenance

if TYPE_CHECKING:
    from tbdy_engine.integration.live_etabs_acquisition_context import TrustedLiveAcquisitionContext
    from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext

# CSI primary dimensions and display-unit rule, applied through the explicit
# project-reviewed compatibility policy accepted in the Q1N supervisor brief.
# This is NOT a claim that CSI supplied a literal v23/OAPI version mapping.
ISOTROPIC_SOURCE_AUTHORITY_REF = "COLUMN_R1_P1A_Q1N_PRESENT_EG_COMPATIBILITY_POLICY_V1"
ISOTROPIC_SOURCE_AUTHORITY_VERSION = "PROJECT_REVIEWED_V1_20261006;CSI_ETABSv1_PRESENT_F_L2"


ISOTROPIC_MATERIAL_FACT_CONTRACT = "ETABS_ISOTROPIC_MATERIAL_FACT_V2"
ISOTROPIC_MATERIAL_EVIDENCE_PREFIX = "etabs-isotropic-material:sha256:"

MATERIAL_TYPE_FACT_CONTRACT = "ETABS_MATERIAL_TYPE_FACT_V1"
MATERIAL_TYPE_EVIDENCE_PREFIX = "etabs-material-type:sha256:"

# CSI ETABS eMatType documented enum values.
CSI_MATERIAL_TYPE_STEEL = 1
CSI_MATERIAL_TYPE_CONCRETE = 2


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
    return ISOTROPIC_MATERIAL_EVIDENCE_PREFIX + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class IsotropicMaterialPropertiesFact:
    material_name: str
    modulus_of_elasticity: float
    poisson_ratio: float
    thermal_coefficient: float
    shear_modulus: float
    temperature: float
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = ISOTROPIC_MATERIAL_FACT_CONTRACT
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
        object.__setattr__(self, "material_name", _text(self.material_name, "material_name"))
        for attribute in (
            "modulus_of_elasticity",
            "poisson_ratio",
            "thermal_coefficient",
            "shear_modulus",
            "temperature",
        ):
            object.__setattr__(self, attribute, _number(getattr(self, attribute), attribute))
        if self.raw_response:
            expected = (self.modulus_of_elasticity, self.poisson_ratio,
                        self.thermal_coefficient, self.shear_modulus, self.return_code)
            if _decode_get_mp_isotropic(self.raw_response) != expected:
                raise EtabsOAPIError("UNIT_UNQUALIFIED:RAW_PROPERTY_VALUE_MISMATCH")
        if type(self.return_code) is not int:
            raise EtabsOAPIError("return_code must be an integer")
        if self.contract != ISOTROPIC_MATERIAL_FACT_CONTRACT:
            raise EtabsOAPIError("isotropic material fact contract mismatch")
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
                    "material_name": self.material_name,
                    "modulus_of_elasticity": self.modulus_of_elasticity,
                    "poisson_ratio": self.poisson_ratio,
                    "thermal_coefficient": self.thermal_coefficient,
                    "shear_modulus": self.shear_modulus,
                    "temperature": self.temperature,
                    "return_code": self.return_code,
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
        binding.require(source_call="SapModel.PropMaterial.GetMPIsotropic", subject_key=self.material_name,
                        output_key=output_key, dimension=dimension,
                        source_model_ref=self.source_model_ref, session_ref=self.session_ref,
                        capture_ref=self.capture_ref, raw_response_ref=self.raw_response_ref)
        return binding

    @property
    def success(self) -> bool:
        return self.return_code == 0


def _material_type_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")

    return (
        MATERIAL_TYPE_EVIDENCE_PREFIX
        + hashlib.sha256(encoded).hexdigest()
    )


@dataclass(frozen=True, slots=True)
class MaterialTypeFact:
    """Factual PropMaterial.GetTypeOAPI result.

    No TS500 applicability decision is made at this boundary.
    """

    material_name: str
    material_type_code: int
    symmetry_type_code: int
    return_code: int
    evidence_ref: str = field(init=False)
    contract: str = MATERIAL_TYPE_FACT_CONTRACT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "material_name",
            _text(
                self.material_name,
                "material_name",
            ),
        )

        for field_name in (
            "material_type_code",
            "symmetry_type_code",
            "return_code",
        ):
            if type(getattr(self, field_name)) is not int:
                raise EtabsOAPIError(
                    f"{field_name} must be an integer"
                )

        if self.contract != MATERIAL_TYPE_FACT_CONTRACT:
            raise EtabsOAPIError(
                "material type fact contract mismatch"
            )

        object.__setattr__(
            self,
            "evidence_ref",
            _material_type_digest(
                {
                    "contract": self.contract,
                    "material_name":
                        self.material_name,
                    "material_type_code":
                        self.material_type_code,
                    "symmetry_type_code":
                        self.symmetry_type_code,
                    "return_code":
                        self.return_code,
                }
            ),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0

    @property
    def is_steel(self) -> bool:
        return (
            self.success
            and self.material_type_code
            == CSI_MATERIAL_TYPE_STEEL
        )

    @property
    def is_concrete(self) -> bool:
        return (
            self.success
            and self.material_type_code
            == CSI_MATERIAL_TYPE_CONCRETE
        )


def _decode_get_type_oapi(
    raw: object,
) -> tuple[int, int, int]:
    if (
        not isinstance(raw, (tuple, list))
        or len(raw) != 3
    ):
        raise EtabsOAPIError(
            "PropMaterial.GetTypeOAPI returned "
            f"unsupported Python ABI shape: {raw!r}"
        )

    material_type, symmetry_type, return_code = tuple(raw)

    if not all(
        type(value) is int
        for value in (
            material_type,
            symmetry_type,
            return_code,
        )
    ):
        raise EtabsOAPIError(
            "PropMaterial.GetTypeOAPI returned "
            f"unsupported Python ABI shape: {raw!r}"
        )

    return (
        material_type,
        symmetry_type,
        return_code,
    )


def get_material_type_from_session(
    session: EtabsVerifiedSession,
    *,
    material_name: str,
    timeout_seconds: float = 30.0,
) -> MaterialTypeFact:
    """Retrieve exact CSI material type/symmetry factual outputs."""
    if not isinstance(
        session,
        EtabsVerifiedSession,
    ):
        raise TypeError(
            "session must be EtabsVerifiedSession"
        )

    name = _text(
        material_name,
        "material_name",
    )

    timeout = float(timeout_seconds)

    if (
        not math.isfinite(timeout)
        or timeout <= 0.0
    ):
        raise ValueError(
            "timeout_seconds must be finite "
            "and greater than zero"
        )

    def acquire(
        _application: object,
        model_api: Any,
    ) -> MaterialTypeFact:
        raw = (
            model_api.PropMaterial.GetTypeOAPI(
                name
            )
        )

        (
            material_type,
            symmetry_type,
            return_code,
        ) = _decode_get_type_oapi(raw)

        return MaterialTypeFact(
            material_name=name,
            material_type_code=material_type,
            symmetry_type_code=symmetry_type,
            return_code=return_code,
        )

    return _execute_verified_read(
        session,
        acquire,
        operation=(
            "oapi_prop_material_get_type_oapi"
        ),
        timeout_seconds=timeout,
    )


def _decode_get_mp_isotropic(
    raw: object,
) -> tuple[float, float, float, float, int]:
    if not isinstance(raw, (tuple, list)) or len(raw) != 5:
        raise EtabsOAPIError(
            f"PropMaterial.GetMPIsotropic returned unsupported Python ABI shape: {raw!r}"
        )
    e_value, u_value, a_value, g_value, return_code = tuple(raw)
    if type(return_code) is not int:
        raise EtabsOAPIError(
            f"PropMaterial.GetMPIsotropic returned unsupported Python ABI shape: {raw!r}"
        )
    try:
        return (
            _number(e_value, "PropMaterial.GetMPIsotropic.E"),
            _number(u_value, "PropMaterial.GetMPIsotropic.U"),
            _number(a_value, "PropMaterial.GetMPIsotropic.A"),
            _number(g_value, "PropMaterial.GetMPIsotropic.G"),
            int(return_code),
        )
    except EtabsOAPIError as exc:
        raise EtabsOAPIError(
            f"PropMaterial.GetMPIsotropic returned unsupported Python ABI shape: {raw!r}; {exc}"
        ) from exc


def get_isotropic_material_properties_from_session(
    session: EtabsVerifiedSession,
    *,
    material_name: str,
    temperature: float = 0.0,
    timeout_seconds: float = 30.0,
    context: TrustedLiveAcquisitionContext | None = None,
    owned_scratch: OwnedScratchContext | None = None,
) -> IsotropicMaterialPropertiesFact:
    """Retrieve documented E/U/A/G outputs at the requested temperature."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    name = _text(material_name, "material_name")
    temp = _number(temperature, "temperature")
    timeout = float(timeout_seconds)
    if not math.isfinite(timeout) or timeout <= 0.0:
        raise ValueError("timeout_seconds must be finite and greater than zero")

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
    if context is not None or owned_scratch is not None:
        # Reuse factory-issued context/ownership; arbitrary caller refs cannot
        # qualify a foreign source. No acquisition/lifecycle is created here.
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
            force = decode_csi_force_unit(units.present_force_unit).value
            length = decode_csi_length_unit(units.present_length_unit).value
        except EtabsSourceUnitError as exc:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:UNSUPPORTED_PRESENT_STRESS_UNIT") from exc
        unit = f"{force}/{length}2"
        # Restrict issuance to the existing downstream stress converter's scope.
        if unit not in {"N/m2", "kN/m2", "N/mm2"}:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:UNSUPPORTED_PRESENT_STRESS_UNIT")
        state = json.dumps({"active_identity": current.as_dict(),
                            "same_capture_bridge": bridge}, sort_keys=True)
        return current, state, unit

    def acquire(application: object, model_api: Any) -> IsotropicMaterialPropertiesFact:
        before, state_before, source_unit = observe(application, model_api)
        raw = model_api.PropMaterial.GetMPIsotropic(name, Temp=temp)
        after, state_after, unit_after = observe(application, model_api)
        if before != after or source_unit != unit_after:
            raise EtabsOAPIError("UNIT_UNQUALIFIED:CAPTURE_STATE_DRIFT")
        e_value, u_value, a_value, g_value, return_code = _decode_get_mp_isotropic(raw)
        fact = IsotropicMaterialPropertiesFact(
            material_name=name,
            modulus_of_elasticity=e_value,
            poisson_ratio=u_value,
            thermal_coefficient=a_value,
            shear_modulus=g_value,
            temperature=temp,
            return_code=return_code,
            raw_response=tuple(raw),
            source_model_ref=source_ref,
            session_ref=session_ref,
            capture_ref=capture_ref,
            unit_observation=json.dumps({"before": json.loads(state_before),
                                         "after": json.loads(state_after)}, sort_keys=True),
        )
        # Retain unsuccessful raw getters as factual failures, never qualified.
        if return_code != 0:
            return fact
        provenance = tuple(SourceUnitProvenance(
            source_call="SapModel.PropMaterial.GetMPIsotropic", subject_key=name,
            output_key=key, dimension="F/L2", source_unit=source_unit,
            authority_ref=ISOTROPIC_SOURCE_AUTHORITY_REF,
            authority_version=ISOTROPIC_SOURCE_AUTHORITY_VERSION,
            authority_kind="REVIEWED_PROPERTY_SOURCE_SEMANTICS",
            source_model_ref=source_ref, session_ref=session_ref, capture_ref=capture_ref,
            raw_response_ref=fact.raw_response_ref, return_code=return_code,
            unit_state_before=state_before, unit_state_after=state_after,
            qualification="QUALIFIED", reason="CSI_PRESENT_SEMANTICS_WITH_REVIEWED_PROJECT_COMPATIBILITY_POLICY",
        ) for key in ("E", "G"))
        qualified = replace(fact, unit_provenance=provenance)
        for key in ("E", "G"):
            qualified.source_unit_for(key, "F/L2")
        return qualified

    return _execute_verified_read(
        session,
        acquire,
        operation="oapi_prop_material_get_mp_isotropic",
        timeout_seconds=timeout,
    )


__all__ = [
    "CSI_MATERIAL_TYPE_CONCRETE",
    "CSI_MATERIAL_TYPE_STEEL",
    "ISOTROPIC_MATERIAL_EVIDENCE_PREFIX",
    "ISOTROPIC_MATERIAL_FACT_CONTRACT",
    "MATERIAL_TYPE_EVIDENCE_PREFIX",
    "MATERIAL_TYPE_FACT_CONTRACT",
    "IsotropicMaterialPropertiesFact",
    "MaterialTypeFact",
    "get_isotropic_material_properties_from_session",
    "get_material_type_from_session",
]
