"""Typed factual ``PropMaterial.GetMPIsotropic`` read boundary.

The supplied ETABS OAPI documentation directly names the retrieved isotropic
outputs as modulus of elasticity ``E``, Poisson ratio ``U``, thermal
coefficient ``A`` and shear modulus ``G`` at input temperature ``Temp``.
Those names are therefore ``DOCUMENTED FACT`` at this boundary.  No TS500
material qualification or engineering acceptability policy is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any

from tbdy_engine.etabs.safety import EtabsVerifiedSession, _execute_verified_read

from .contracts import EtabsOAPIError


ISOTROPIC_MATERIAL_FACT_CONTRACT = "ETABS_ISOTROPIC_MATERIAL_FACT_V1"
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "material_name", _text(self.material_name, "material_name"))
        for attribute in (
            "modulus_of_elasticity",
            "poisson_ratio",
            "thermal_coefficient",
            "shear_modulus",
            "temperature",
        ):
            object.__setattr__(self, attribute, _number(getattr(self, attribute), attribute))
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
) -> IsotropicMaterialPropertiesFact:
    """Retrieve documented E/U/A/G outputs at the requested temperature."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    name = _text(material_name, "material_name")
    temp = _number(temperature, "temperature")
    timeout = float(timeout_seconds)
    if not math.isfinite(timeout) or timeout <= 0.0:
        raise ValueError("timeout_seconds must be finite and greater than zero")

    def acquire(_application: object, model_api: Any) -> IsotropicMaterialPropertiesFact:
        raw = model_api.PropMaterial.GetMPIsotropic(name, temp)
        e_value, u_value, a_value, g_value, return_code = _decode_get_mp_isotropic(raw)
        return IsotropicMaterialPropertiesFact(
            material_name=name,
            modulus_of_elasticity=e_value,
            poisson_ratio=u_value,
            thermal_coefficient=a_value,
            shear_modulus=g_value,
            temperature=temp,
            return_code=return_code,
        )

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
