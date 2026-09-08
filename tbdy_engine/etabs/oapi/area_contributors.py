"""Typed factual ETABS Area contributor reads for COLUMN-R1 A2.

This module extends the existing ``tbdy_engine.etabs.oapi`` factual layer.  It
captures CSI/runtime facts only: design orientation, local axes,
transformation matrix, material-overwrite token, and ordinary slab/deck
property records.  It deliberately makes no TS500/TBDY participation or gross
stiffness decision.

``AreaObj`` modifier vectors remain owned by :mod:`area_modifiers`; this module
does not assign property-slot semantics to object modifiers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
import hashlib
import json
import math
from typing import Any, Sequence

from tbdy_engine.etabs.safety import EtabsVerifiedSession, _execute_verified_read

from .contracts import EtabsOAPIError


AREA_CONTRIBUTOR_FACT_PREFIX = "etabs-area-contributor-fact:sha256:"


class AreaDesignOrientation(IntEnum):
    WALL = 1
    FLOOR = 2
    RAMP_DO_NOT_USE = 3
    NULL = 4
    OTHER = 5


class AreaShellType(IntEnum):
    SHELL_THIN = 1
    SHELL_THICK = 2
    MEMBRANE = 3
    PLATE_THIN_DO_NOT_USE = 4
    PLATE_THICK_DO_NOT_USE = 5
    LAYERED = 6


def _text(value: object, label: str, *, allow_blank: bool = False) -> str:
    if not isinstance(value, str):
        raise EtabsOAPIError(f"{label} must be a string")
    if value != value.strip():
        raise EtabsOAPIError(f"{label} must be canonical/trimmed")
    if not allow_blank and not value:
        raise EtabsOAPIError(f"{label} must be nonblank")
    return value


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise EtabsOAPIError(f"{label} must be an integer")
    return int(value)


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EtabsOAPIError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EtabsOAPIError(f"{label} must be finite numeric")
    return result


def _sequence(raw: object, *, method: str, expected: int) -> tuple[object, ...]:
    if not isinstance(raw, (tuple, list)):
        raise EtabsOAPIError(
            f"{method} returned unsupported Python ABI shape: {type(raw).__name__}"
        )
    values = tuple(raw)
    if len(values) != expected:
        raise EtabsOAPIError(
            f"{method} returned {len(values)} values; expected {expected}: {raw!r}"
        )
    return values


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return AREA_CONTRIBUTOR_FACT_PREFIX + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class AreaDesignOrientationFact:
    area_name: str
    orientation_code: int
    return_code: int
    evidence_ref: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "area_name", _text(self.area_name, "area_name"))
        code = _integer(self.orientation_code, "orientation_code")
        try:
            AreaDesignOrientation(code)
        except ValueError as exc:
            raise EtabsOAPIError(
                f"unsupported eAreaDesignOrientation code {code}"
            ) from exc
        object.__setattr__(self, "orientation_code", code)
        object.__setattr__(self, "return_code", _integer(self.return_code, "return_code"))
        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                {
                    "api": "AreaObj.GetDesignOrientation",
                    "area_name": self.area_name,
                    "orientation_code": code,
                    "return_code": self.return_code,
                }
            ),
        )

    @property
    def orientation(self) -> AreaDesignOrientation:
        return AreaDesignOrientation(self.orientation_code)

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class AreaLocalAxesFact:
    area_name: str
    angle_degrees: float
    advanced: bool
    return_code: int
    evidence_ref: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "area_name", _text(self.area_name, "area_name"))
        object.__setattr__(
            self, "angle_degrees", _finite(self.angle_degrees, "angle_degrees")
        )
        if type(self.advanced) is not bool:
            raise EtabsOAPIError("advanced must be boolean")
        object.__setattr__(self, "return_code", _integer(self.return_code, "return_code"))
        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                {
                    "api": "AreaObj.GetLocalAxes",
                    "area_name": self.area_name,
                    "angle_degrees": self.angle_degrees,
                    "advanced": self.advanced,
                    "return_code": self.return_code,
                }
            ),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class AreaTransformationMatrixFact:
    area_name: str
    values: tuple[float, ...]
    return_code: int
    evidence_ref: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "area_name", _text(self.area_name, "area_name"))
        if len(tuple(self.values)) != 9:
            raise EtabsOAPIError("Area transformation matrix must contain exactly 9 values")
        normalized = tuple(
            _finite(value, f"transformation_matrix[{index}]")
            for index, value in enumerate(self.values)
        )
        object.__setattr__(self, "values", normalized)
        object.__setattr__(self, "return_code", _integer(self.return_code, "return_code"))
        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                {
                    "api": "AreaObj.GetTransformationMatrix",
                    "area_name": self.area_name,
                    "values": list(normalized),
                    "return_code": self.return_code,
                }
            ),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class AreaMaterialOverwriteFact:
    area_name: str
    raw_material_name: str
    return_code: int
    evidence_ref: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "area_name", _text(self.area_name, "area_name"))
        object.__setattr__(
            self,
            "raw_material_name",
            _text(self.raw_material_name, "raw_material_name", allow_blank=True),
        )
        object.__setattr__(self, "return_code", _integer(self.return_code, "return_code"))
        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                {
                    "api": "AreaObj.GetMaterialOverwrite",
                    "area_name": self.area_name,
                    "raw_material_name": self.raw_material_name,
                    "return_code": self.return_code,
                }
            ),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class AreaPropertyFamilyProbeFact:
    property_name: str
    family: str
    family_type_code: int | None
    shell_type_code: int | None
    material_name: str | None
    thickness: float | None
    return_code: int
    evidence_ref: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "property_name", _text(self.property_name, "property_name")
        )
        if self.family not in {"SLAB", "DECK"}:
            raise EtabsOAPIError("property family probe must be SLAB or DECK")
        object.__setattr__(self, "return_code", _integer(self.return_code, "return_code"))
        if self.return_code == 0:
            if self.family_type_code is None or self.shell_type_code is None:
                raise EtabsOAPIError("successful property family probe requires type codes")
            family_type_code = _integer(self.family_type_code, "family_type_code")
            shell_type_code = _integer(self.shell_type_code, "shell_type_code")
            try:
                AreaShellType(shell_type_code)
            except ValueError as exc:
                raise EtabsOAPIError(
                    f"unsupported eShellType code {shell_type_code}"
                ) from exc
            material = _text(
                self.material_name, "material_name", allow_blank=True
            ) if self.material_name is not None else None
            thickness = (
                _finite(self.thickness, "thickness") if self.thickness is not None else None
            )
            object.__setattr__(self, "family_type_code", family_type_code)
            object.__setattr__(self, "shell_type_code", shell_type_code)
            object.__setattr__(self, "material_name", material)
            object.__setattr__(self, "thickness", thickness)
        else:
            object.__setattr__(self, "family_type_code", None)
            object.__setattr__(self, "shell_type_code", None)
            object.__setattr__(self, "material_name", None)
            object.__setattr__(self, "thickness", None)
        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                {
                    "api": f"PropArea.Get{self.family.title()}",
                    "property_name": self.property_name,
                    "family": self.family,
                    "family_type_code": self.family_type_code,
                    "shell_type_code": self.shell_type_code,
                    "material_name": self.material_name,
                    "thickness": self.thickness,
                    "return_code": self.return_code,
                }
            ),
        )

    @property
    def success(self) -> bool:
        return self.return_code == 0


def read_area_design_orientation(area_obj: Any, area_name: str) -> AreaDesignOrientationFact:
    name = _text(area_name, "area_name")
    raw = area_obj.GetDesignOrientation(name)
    code, ret = _sequence(
        raw, method=f"AreaObj.GetDesignOrientation({name!r})", expected=2
    )
    return AreaDesignOrientationFact(
        area_name=name,
        orientation_code=_integer(code, "orientation_code"),
        return_code=_integer(ret, "return_code"),
    )


def read_area_local_axes(area_obj: Any, area_name: str) -> AreaLocalAxesFact:
    name = _text(area_name, "area_name")
    raw = area_obj.GetLocalAxes(name)
    angle, advanced, ret = _sequence(
        raw, method=f"AreaObj.GetLocalAxes({name!r})", expected=3
    )
    if type(advanced) is not bool:
        raise EtabsOAPIError(
            f"AreaObj.GetLocalAxes({name!r}) returned non-boolean Advanced={advanced!r}"
        )
    return AreaLocalAxesFact(
        area_name=name,
        angle_degrees=_finite(angle, "angle_degrees"),
        advanced=advanced,
        return_code=_integer(ret, "return_code"),
    )


def read_area_transformation_matrix(
    area_obj: Any, area_name: str
) -> AreaTransformationMatrixFact:
    name = _text(area_name, "area_name")
    raw = area_obj.GetTransformationMatrix(name)
    matrix, ret = _sequence(
        raw, method=f"AreaObj.GetTransformationMatrix({name!r})", expected=2
    )
    if isinstance(matrix, (str, bytes)) or not isinstance(matrix, Sequence):
        raise EtabsOAPIError(
            f"AreaObj.GetTransformationMatrix({name!r}) returned no numeric sequence"
        )
    values = tuple(matrix)
    if len(values) != 9:
        raise EtabsOAPIError(
            f"AreaObj.GetTransformationMatrix({name!r}) requires 9 values"
        )
    return AreaTransformationMatrixFact(
        area_name=name,
        values=tuple(_finite(value, f"matrix[{index}]") for index, value in enumerate(values)),
        return_code=_integer(ret, "return_code"),
    )


def read_area_material_overwrite(
    area_obj: Any, area_name: str
) -> AreaMaterialOverwriteFact:
    name = _text(area_name, "area_name")
    raw = area_obj.GetMaterialOverwrite(name)
    material, ret = _sequence(
        raw, method=f"AreaObj.GetMaterialOverwrite({name!r})", expected=2
    )
    return AreaMaterialOverwriteFact(
        area_name=name,
        raw_material_name=_text(
            material, "raw_material_name", allow_blank=True
        ),
        return_code=_integer(ret, "return_code"),
    )


def _read_property_family_probe(
    prop_area: Any,
    property_name: str,
    *,
    family: str,
) -> AreaPropertyFamilyProbeFact:
    name = _text(property_name, "property_name")
    method = getattr(prop_area, f"Get{family.title()}")
    raw = method(name)
    values = _sequence(raw, method=f"PropArea.Get{family.title()}({name!r})", expected=8)
    family_type, shell_type, material, thickness, _color, _notes, _guid, ret = values
    return_code = _integer(ret, "return_code")
    if return_code != 0:
        return AreaPropertyFamilyProbeFact(
            property_name=name,
            family=family,
            family_type_code=None,
            shell_type_code=None,
            material_name=None,
            thickness=None,
            return_code=return_code,
        )
    return AreaPropertyFamilyProbeFact(
        property_name=name,
        family=family,
        family_type_code=_integer(family_type, "family_type_code"),
        shell_type_code=_integer(shell_type, "shell_type_code"),
        material_name=_text(material, "material_name", allow_blank=True),
        thickness=_finite(thickness, "thickness"),
        return_code=return_code,
    )


def read_slab_property_probe(prop_area: Any, property_name: str) -> AreaPropertyFamilyProbeFact:
    return _read_property_family_probe(prop_area, property_name, family="SLAB")


def read_deck_property_probe(prop_area: Any, property_name: str) -> AreaPropertyFamilyProbeFact:
    return _read_property_family_probe(prop_area, property_name, family="DECK")


def _session_read(session: EtabsVerifiedSession, function, *, operation: str):
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    return _execute_verified_read(session, function, operation=operation)


def read_area_design_orientation_from_session(
    session: EtabsVerifiedSession, area_name: str
) -> AreaDesignOrientationFact:
    return _session_read(
        session,
        lambda _app, sap: read_area_design_orientation(sap.AreaObj, area_name),
        operation="oapi_area_obj_get_design_orientation",
    )


def read_area_local_axes_from_session(
    session: EtabsVerifiedSession, area_name: str
) -> AreaLocalAxesFact:
    return _session_read(
        session,
        lambda _app, sap: read_area_local_axes(sap.AreaObj, area_name),
        operation="oapi_area_obj_get_local_axes",
    )


def read_area_transformation_matrix_from_session(
    session: EtabsVerifiedSession, area_name: str
) -> AreaTransformationMatrixFact:
    return _session_read(
        session,
        lambda _app, sap: read_area_transformation_matrix(sap.AreaObj, area_name),
        operation="oapi_area_obj_get_transformation_matrix",
    )


def read_area_material_overwrite_from_session(
    session: EtabsVerifiedSession, area_name: str
) -> AreaMaterialOverwriteFact:
    return _session_read(
        session,
        lambda _app, sap: read_area_material_overwrite(sap.AreaObj, area_name),
        operation="oapi_area_obj_get_material_overwrite",
    )


def read_slab_property_probe_from_session(
    session: EtabsVerifiedSession, property_name: str
) -> AreaPropertyFamilyProbeFact:
    return _session_read(
        session,
        lambda _app, sap: read_slab_property_probe(sap.PropArea, property_name),
        operation="oapi_prop_area_get_slab",
    )


def read_deck_property_probe_from_session(
    session: EtabsVerifiedSession, property_name: str
) -> AreaPropertyFamilyProbeFact:
    return _session_read(
        session,
        lambda _app, sap: read_deck_property_probe(sap.PropArea, property_name),
        operation="oapi_prop_area_get_deck",
    )


__all__ = [
    "AREA_CONTRIBUTOR_FACT_PREFIX",
    "AreaDesignOrientation",
    "AreaDesignOrientationFact",
    "AreaLocalAxesFact",
    "AreaMaterialOverwriteFact",
    "AreaPropertyFamilyProbeFact",
    "AreaShellType",
    "AreaTransformationMatrixFact",
    "read_area_design_orientation",
    "read_area_design_orientation_from_session",
    "read_area_local_axes",
    "read_area_local_axes_from_session",
    "read_area_material_overwrite",
    "read_area_material_overwrite_from_session",
    "read_area_transformation_matrix",
    "read_area_transformation_matrix_from_session",
    "read_deck_property_probe",
    "read_deck_property_probe_from_session",
    "read_slab_property_probe",
    "read_slab_property_probe_from_session",
]
