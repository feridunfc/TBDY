"""Typed factual ETABS Area contributor reads for COLUMN-R1 A2/A3.

This module extends the existing OAPI factual layer only. It captures design
orientation, local axes, transformation matrix, material-overwrite token,
Slab/Deck property-family facts, diaphragm assignment/definition, and exact
pier/spandrel assignment tokens. It owns no Eq.7.13 participation or gross
stiffness policy, and it never assigns PropArea slot semantics to AreaObj
modifier vectors.
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
    if value != value.strip() or (not allow_blank and not value):
        raise EtabsOAPIError(f"{label} must be a canonical string")
    return value


def _int(value: object, label: str) -> int:
    if type(value) is not int:
        raise EtabsOAPIError(f"{label} must be an integer")
    return int(value)


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EtabsOAPIError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EtabsOAPIError(f"{label} must be finite numeric")
    return result


def _items(raw: object, method: str, length: int) -> tuple[object, ...]:
    if not isinstance(raw, (tuple, list)) or len(raw) != length:
        raise EtabsOAPIError(f"{method} returned unsupported Python ABI shape: {raw!r}")
    return tuple(raw)


def _digest(payload: object) -> str:
    data = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return AREA_CONTRIBUTOR_FACT_PREFIX + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class AreaDesignOrientationFact:
    area_name: str
    orientation_code: int
    return_code: int
    evidence_ref: str = field(init=False)

    def __post_init__(self) -> None:
        name = _text(self.area_name, "area_name")
        code = _int(self.orientation_code, "orientation_code")
        try:
            AreaDesignOrientation(code)
        except ValueError as exc:
            raise EtabsOAPIError(f"unsupported eAreaDesignOrientation code {code}") from exc
        ret = _int(self.return_code, "return_code")
        object.__setattr__(self, "area_name", name)
        object.__setattr__(self, "orientation_code", code)
        object.__setattr__(self, "return_code", ret)
        object.__setattr__(self, "evidence_ref", _digest({
            "api": "AreaObj.GetDesignOrientation", "area_name": name,
            "orientation_code": code, "return_code": ret,
        }))

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
        name = _text(self.area_name, "area_name")
        angle = _number(self.angle_degrees, "angle_degrees")
        if type(self.advanced) is not bool:
            raise EtabsOAPIError("advanced must be boolean")
        ret = _int(self.return_code, "return_code")
        object.__setattr__(self, "area_name", name)
        object.__setattr__(self, "angle_degrees", angle)
        object.__setattr__(self, "return_code", ret)
        object.__setattr__(self, "evidence_ref", _digest({
            "api": "AreaObj.GetLocalAxes", "area_name": name,
            "angle_degrees": angle, "advanced": self.advanced, "return_code": ret,
        }))

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
        name = _text(self.area_name, "area_name")
        if len(tuple(self.values)) != 9:
            raise EtabsOAPIError("Area transformation matrix must contain exactly 9 values")
        values = tuple(_number(v, f"matrix[{i}]") for i, v in enumerate(self.values))
        ret = _int(self.return_code, "return_code")
        object.__setattr__(self, "area_name", name)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "return_code", ret)
        object.__setattr__(self, "evidence_ref", _digest({
            "api": "AreaObj.GetTransformationMatrix", "area_name": name,
            "values": list(values), "return_code": ret,
        }))

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
        name = _text(self.area_name, "area_name")
        material = _text(self.raw_material_name, "raw_material_name", allow_blank=True)
        ret = _int(self.return_code, "return_code")
        object.__setattr__(self, "area_name", name)
        object.__setattr__(self, "raw_material_name", material)
        object.__setattr__(self, "return_code", ret)
        object.__setattr__(self, "evidence_ref", _digest({
            "api": "AreaObj.GetMaterialOverwrite", "area_name": name,
            "raw_material_name": material, "return_code": ret,
        }))

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class AreaDiaphragmAssignmentFact:
    area_name: str
    diaphragm_name: str
    return_code: int
    evidence_ref: str = field(init=False)

    def __post_init__(self) -> None:
        name = _text(self.area_name, "area_name")
        diaphragm = _text(self.diaphragm_name, "diaphragm_name", allow_blank=True)
        ret = _int(self.return_code, "return_code")
        object.__setattr__(self, "area_name", name)
        object.__setattr__(self, "diaphragm_name", diaphragm)
        object.__setattr__(self, "return_code", ret)
        object.__setattr__(self, "evidence_ref", _digest({
            "api": "AreaObj.GetDiaphragm", "area_name": name,
            "diaphragm_name": diaphragm, "return_code": ret,
        }))

    @property
    def success(self) -> bool:
        return self.return_code == 0

    @property
    def assigned(self) -> bool:
        return self.success and self.diaphragm_name not in {"", "None"}


@dataclass(frozen=True, slots=True)
class DiaphragmDefinitionFact:
    diaphragm_name: str
    semi_rigid: bool
    return_code: int
    evidence_ref: str = field(init=False)

    def __post_init__(self) -> None:
        name = _text(self.diaphragm_name, "diaphragm_name")
        if type(self.semi_rigid) is not bool:
            raise EtabsOAPIError("semi_rigid must be boolean")
        ret = _int(self.return_code, "return_code")
        object.__setattr__(self, "diaphragm_name", name)
        object.__setattr__(self, "return_code", ret)
        object.__setattr__(self, "evidence_ref", _digest({
            "api": "Diaphragm.GetDiaphragm", "diaphragm_name": name,
            "semi_rigid": self.semi_rigid, "return_code": ret,
        }))

    @property
    def success(self) -> bool:
        return self.return_code == 0


@dataclass(frozen=True, slots=True)
class AreaWallAssignmentFact:
    area_name: str
    pier_name: str
    spandrel_name: str
    pier_return_code: int
    spandrel_return_code: int
    evidence_ref: str = field(init=False)

    def __post_init__(self) -> None:
        name = _text(self.area_name, "area_name")
        pier = _text(self.pier_name, "pier_name", allow_blank=True)
        spandrel = _text(self.spandrel_name, "spandrel_name", allow_blank=True)
        pier_ret = _int(self.pier_return_code, "pier_return_code")
        spandrel_ret = _int(self.spandrel_return_code, "spandrel_return_code")
        object.__setattr__(self, "area_name", name)
        object.__setattr__(self, "pier_name", pier)
        object.__setattr__(self, "spandrel_name", spandrel)
        object.__setattr__(self, "pier_return_code", pier_ret)
        object.__setattr__(self, "spandrel_return_code", spandrel_ret)
        object.__setattr__(self, "evidence_ref", _digest({
            "api": "AreaObj.GetPier+GetSpandrel", "area_name": name,
            "pier_name": pier, "spandrel_name": spandrel,
            "pier_return_code": pier_ret,
            "spandrel_return_code": spandrel_ret,
        }))

    @property
    def success(self) -> bool:
        return self.pier_return_code == 0 and self.spandrel_return_code == 0

    @property
    def pier_assigned(self) -> bool:
        return self.success and self.pier_name not in {"", "None"}

    @property
    def spandrel_assigned(self) -> bool:
        return self.success and self.spandrel_name not in {"", "None"}

    @property
    def assignment_conflict(self) -> bool:
        return self.pier_assigned and self.spandrel_assigned


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
        name = _text(self.property_name, "property_name")
        if self.family not in {"SLAB", "DECK"}:
            raise EtabsOAPIError("property family probe must be SLAB or DECK")
        ret = _int(self.return_code, "return_code")
        family_type = shell_type = material = thickness = None
        if ret == 0:
            if self.family_type_code is None or self.shell_type_code is None:
                raise EtabsOAPIError("successful property family probe requires type codes")
            family_type = _int(self.family_type_code, "family_type_code")
            shell_type = _int(self.shell_type_code, "shell_type_code")
            try:
                AreaShellType(shell_type)
            except ValueError as exc:
                raise EtabsOAPIError(f"unsupported eShellType code {shell_type}") from exc
            material = None if self.material_name is None else _text(
                self.material_name, "material_name", allow_blank=True
            )
            thickness = None if self.thickness is None else _number(
                self.thickness, "thickness"
            )
        object.__setattr__(self, "property_name", name)
        object.__setattr__(self, "return_code", ret)
        object.__setattr__(self, "family_type_code", family_type)
        object.__setattr__(self, "shell_type_code", shell_type)
        object.__setattr__(self, "material_name", material)
        object.__setattr__(self, "thickness", thickness)
        object.__setattr__(self, "evidence_ref", _digest({
            "api": f"PropArea.Get{self.family.title()}", "property_name": name,
            "family": self.family, "family_type_code": family_type,
            "shell_type_code": shell_type, "material_name": material,
            "thickness": thickness, "return_code": ret,
        }))

    @property
    def success(self) -> bool:
        return self.return_code == 0


def read_area_design_orientation(area_obj: Any, area_name: str) -> AreaDesignOrientationFact:
    name = _text(area_name, "area_name")
    code, ret = _items(area_obj.GetDesignOrientation(name), "AreaObj.GetDesignOrientation", 2)
    return AreaDesignOrientationFact(name, _int(code, "orientation_code"), _int(ret, "return_code"))


def read_area_local_axes(area_obj: Any, area_name: str) -> AreaLocalAxesFact:
    name = _text(area_name, "area_name")
    angle, advanced, ret = _items(area_obj.GetLocalAxes(name), "AreaObj.GetLocalAxes", 3)
    if type(advanced) is not bool:
        raise EtabsOAPIError("AreaObj.GetLocalAxes returned non-boolean Advanced")
    return AreaLocalAxesFact(name, _number(angle, "angle_degrees"), advanced, _int(ret, "return_code"))


def read_area_transformation_matrix(area_obj: Any, area_name: str) -> AreaTransformationMatrixFact:
    name = _text(area_name, "area_name")
    matrix, ret = _items(
        area_obj.GetTransformationMatrix(name), "AreaObj.GetTransformationMatrix", 2
    )
    if isinstance(matrix, (str, bytes)) or not isinstance(matrix, Sequence) or len(matrix) != 9:
        raise EtabsOAPIError("AreaObj.GetTransformationMatrix requires one 9-value sequence")
    return AreaTransformationMatrixFact(
        name, tuple(_number(v, f"matrix[{i}]") for i, v in enumerate(matrix)),
        _int(ret, "return_code")
    )


def read_area_material_overwrite(area_obj: Any, area_name: str) -> AreaMaterialOverwriteFact:
    name = _text(area_name, "area_name")
    material, ret = _items(
        area_obj.GetMaterialOverwrite(name), "AreaObj.GetMaterialOverwrite", 2
    )
    return AreaMaterialOverwriteFact(
        name, _text(material, "raw_material_name", allow_blank=True), _int(ret, "return_code")
    )


def read_area_diaphragm_assignment(area_obj: Any, area_name: str) -> AreaDiaphragmAssignmentFact:
    name = _text(area_name, "area_name")
    diaphragm_name, ret = _items(
        area_obj.GetDiaphragm(name), "AreaObj.GetDiaphragm", 2
    )
    return AreaDiaphragmAssignmentFact(
        name,
        _text(diaphragm_name, "diaphragm_name", allow_blank=True),
        _int(ret, "return_code"),
    )


def read_diaphragm_definition(diaphragm: Any, diaphragm_name: str) -> DiaphragmDefinitionFact:
    name = _text(diaphragm_name, "diaphragm_name")
    semi_rigid, ret = _items(
        diaphragm.GetDiaphragm(name), "Diaphragm.GetDiaphragm", 2
    )
    if type(semi_rigid) is not bool:
        raise EtabsOAPIError("Diaphragm.GetDiaphragm returned non-boolean SemiRigid")
    return DiaphragmDefinitionFact(name, semi_rigid, _int(ret, "return_code"))


def read_area_wall_assignments(area_obj: Any, area_name: str) -> AreaWallAssignmentFact:
    name = _text(area_name, "area_name")
    pier_name, pier_ret = _items(area_obj.GetPier(name), "AreaObj.GetPier", 2)
    spandrel_name, spandrel_ret = _items(
        area_obj.GetSpandrel(name), "AreaObj.GetSpandrel", 2
    )
    return AreaWallAssignmentFact(
        name,
        _text(pier_name, "pier_name", allow_blank=True),
        _text(spandrel_name, "spandrel_name", allow_blank=True),
        _int(pier_ret, "pier_return_code"),
        _int(spandrel_ret, "spandrel_return_code"),
    )


def _read_property_family_probe(
    prop_area: Any, property_name: str, *, family: str
) -> AreaPropertyFamilyProbeFact:
    name = _text(property_name, "property_name")
    raw = getattr(prop_area, f"Get{family.title()}")(name)
    family_type, shell_type, material, thickness, _color, _notes, _guid, ret = _items(
        raw, f"PropArea.Get{family.title()}", 8
    )
    return_code = _int(ret, "return_code")
    if return_code != 0:
        return AreaPropertyFamilyProbeFact(name, family, None, None, None, None, return_code)
    return AreaPropertyFamilyProbeFact(
        name,
        family,
        _int(family_type, "family_type_code"),
        _int(shell_type, "shell_type_code"),
        None if material is None else _text(material, "material_name", allow_blank=True),
        None if thickness is None else _number(thickness, "thickness"),
        return_code,
    )


def read_slab_property_probe(prop_area: Any, property_name: str) -> AreaPropertyFamilyProbeFact:
    return _read_property_family_probe(prop_area, property_name, family="SLAB")


def read_deck_property_probe(prop_area: Any, property_name: str) -> AreaPropertyFamilyProbeFact:
    return _read_property_family_probe(prop_area, property_name, family="DECK")


def _session_read(session: EtabsVerifiedSession, function, *, operation: str):
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    return _execute_verified_read(session, function, operation=operation)


def read_area_design_orientation_from_session(session: EtabsVerifiedSession, area_name: str):
    return _session_read(
        session,
        lambda _app, sap: read_area_design_orientation(sap.AreaObj, area_name),
        operation="oapi_area_obj_get_design_orientation",
    )


def read_area_local_axes_from_session(session: EtabsVerifiedSession, area_name: str):
    return _session_read(
        session,
        lambda _app, sap: read_area_local_axes(sap.AreaObj, area_name),
        operation="oapi_area_obj_get_local_axes",
    )


def read_area_transformation_matrix_from_session(session: EtabsVerifiedSession, area_name: str):
    return _session_read(
        session,
        lambda _app, sap: read_area_transformation_matrix(sap.AreaObj, area_name),
        operation="oapi_area_obj_get_transformation_matrix",
    )


def read_area_material_overwrite_from_session(session: EtabsVerifiedSession, area_name: str):
    return _session_read(
        session,
        lambda _app, sap: read_area_material_overwrite(sap.AreaObj, area_name),
        operation="oapi_area_obj_get_material_overwrite",
    )


def read_area_diaphragm_assignment_from_session(session: EtabsVerifiedSession, area_name: str):
    return _session_read(
        session,
        lambda _app, sap: read_area_diaphragm_assignment(sap.AreaObj, area_name),
        operation="oapi_area_obj_get_diaphragm",
    )


def read_diaphragm_definition_from_session(session: EtabsVerifiedSession, diaphragm_name: str):
    return _session_read(
        session,
        lambda _app, sap: read_diaphragm_definition(sap.Diaphragm, diaphragm_name),
        operation="oapi_diaphragm_get_diaphragm",
    )


def read_area_wall_assignments_from_session(session: EtabsVerifiedSession, area_name: str):
    return _session_read(
        session,
        lambda _app, sap: read_area_wall_assignments(sap.AreaObj, area_name),
        operation="oapi_area_obj_get_wall_assignments",
    )


def read_slab_property_probe_from_session(session: EtabsVerifiedSession, property_name: str):
    return _session_read(
        session,
        lambda _app, sap: read_slab_property_probe(sap.PropArea, property_name),
        operation="oapi_prop_area_get_slab",
    )


def read_deck_property_probe_from_session(session: EtabsVerifiedSession, property_name: str):
    return _session_read(
        session,
        lambda _app, sap: read_deck_property_probe(sap.PropArea, property_name),
        operation="oapi_prop_area_get_deck",
    )


__all__ = [
    "AREA_CONTRIBUTOR_FACT_PREFIX",
    "AreaDesignOrientation", "AreaDesignOrientationFact", "AreaDiaphragmAssignmentFact",
    "AreaLocalAxesFact", "AreaMaterialOverwriteFact", "AreaPropertyFamilyProbeFact",
    "AreaShellType", "AreaTransformationMatrixFact", "AreaWallAssignmentFact",
    "DiaphragmDefinitionFact", "read_area_design_orientation",
    "read_area_design_orientation_from_session", "read_area_diaphragm_assignment",
    "read_area_diaphragm_assignment_from_session", "read_area_local_axes",
    "read_area_local_axes_from_session", "read_area_material_overwrite",
    "read_area_material_overwrite_from_session", "read_area_transformation_matrix",
    "read_area_transformation_matrix_from_session", "read_area_wall_assignments",
    "read_area_wall_assignments_from_session", "read_deck_property_probe",
    "read_deck_property_probe_from_session", "read_diaphragm_definition",
    "read_diaphragm_definition_from_session", "read_slab_property_probe",
    "read_slab_property_probe_from_session",
]
