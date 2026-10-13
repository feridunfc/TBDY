"""Editable reference producer: original pure owners, never live issuance.

The longitudinal result remains DESIGN_CANDIDATE_ONLY.  The transverse owner
receives no canonical selected rebar, so its dependent checks stay BLOCKED.
Vc/Ve and direction mapping are explicit numerical example premises; they are
not P7/Vc qualifications, B5/B6 artifacts, or facts about B-BLOK/235.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import math
from typing import Callable

from tbdy_engine.application.column_reference_workspace import (
    ReferenceCalculation, ReferenceColumnInput, REFERENCE_ID, canonical_bytes,
    calculate_reference,
)
from tbdy_engine.regulatory import column_transverse_confinement as transverse_owner

CONTEXT = "REFERENCE-EDITABLE-OWNERS"
SOURCE = "EXPLICIT_NUMERICAL_REFERENCE_NOT_NATIVE_NOT_PROJECT"
UNITS = {"length": "mm", "force": "kN", "moment": "kN.m", "stress": "MPa", "area": "mm2"}


@dataclass(frozen=True)
class ReferenceCageInput:
    gross_area_ac_mm2: float = 400000.0
    confined_core_area_ack_mm2: float = 300000.0
    fywk_mpa: float = 420.0
    fywd_mpa: float = 365.0
    confinement_spacing_mm: float = 100.0
    middle_spacing_mm: float = 150.0
    shear_spacing_mm: float = 100.0
    confinement_region_length_mm: float = 1200.0
    restrained_bar_spacing_mm: float = 250.0
    bk_dir2_mm: float = 420.0
    bk_dir3_mm: float = 720.0
    ash_dir2_mm2: float = 1000.0
    ash_dir3_mm2: float = 1000.0
    asw_dir2_mm2: float = 200.0
    asw_dir3_mm2: float = 200.0
    leg_spacing_dir2_mm: float = 200.0
    leg_spacing_dir3_mm: float = 200.0
    effective_depth_dir2_mm: float = 450.0
    effective_depth_dir3_mm: float = 450.0
    reference_vc_dir2_kn: float = 100.0
    reference_vc_dir3_kn: float = 100.0
    reference_ve_dir2_kn: float = 200.0
    reference_ve_dir3_kn: float = 200.0

    def __post_init__(self):
        for f in fields(self):
            v = getattr(self, f.name)
            zero_allowed = f.name.startswith(("reference_", "ash_", "asw_"))
            if type(v) not in (int, float) or not math.isfinite(v) or v < 0 or (v == 0 and not zero_allowed):
                raise ValueError(f.name + ": açık, sonlu ve uygun işaretli sayı gerekli.")


@dataclass(frozen=True)
class ReferenceOwnerInput:
    longitudinal: ReferenceColumnInput
    cage: ReferenceCageInput

    @classmethod
    def example(cls):
        # Explicit numerical premises, reusing the existing 500x800 reference
        # and regulatory test's Asw=200, d=450, Vc=100, fywd=365, s=100 case.
        return cls(ReferenceColumnInput(), ReferenceCageInput())

    def bundle(self):
        return {"context": CONTEXT, "source": SOURCE, "units": dict(UNITS),
                "values": {**self.longitudinal.bundle()["values"], **asdict(self.cage)}}

    @classmethod
    def from_bundle(cls, bundle):
        if type(bundle) is not dict or set(bundle) != {"context", "source", "units", "values"}:
            raise ValueError("Tam owner referans paketi gerekli.")
        if bundle["context"] != CONTEXT or bundle["source"] != SOURCE or bundle["units"] != UNITS:
            raise ValueError("Owner referansı kaynak/bağlam/birim kimliği farklı.")
        base_keys = {f.name for f in fields(ReferenceColumnInput)}
        cage_keys = {f.name for f in fields(ReferenceCageInput)}
        values = bundle["values"]
        if type(values) is not dict or set(values) != base_keys | cage_keys:
            raise ValueError("Eksik/bilinmeyen owner girdisi; varsayılan kullanılmadı.")
        base_bundle = ReferenceColumnInput().bundle()
        base_bundle["values"] = {k: values[k] for k in base_keys}
        base = ReferenceColumnInput.from_bundle(base_bundle)
        cage = ReferenceCageInput(**{k: values[k] for k in cage_keys})
        if cage.gross_area_ac_mm2 != base.width_mm * base.depth_mm:
            raise ValueError("Açık Ac ile açık b/h uyuşmuyor; otomatik düzeltme yapılmadı.")
        if cage.confined_core_area_ack_mm2 >= cage.gross_area_ac_mm2:
            raise ValueError("Ack, Ac'den küçük olmalı.")
        if cage.effective_depth_dir2_mm > base.depth_mm or cage.effective_depth_dir3_mm > base.width_mm:
            raise ValueError("Referans etkin derinliği ilgili açık kesit boyutunu aşamaz.")
        return cls(base, cage)


@dataclass(frozen=True)
class ReferenceOwnerCalculation:
    inputs: ReferenceOwnerInput
    input_sha256: str
    longitudinal: ReferenceCalculation
    transverse_input: transverse_owner.ColumnTransverseConfinementInput
    transverse: transverse_owner.ColumnTransverseConfinementResult
    invoked_owners: tuple[str, ...]


def calculate_reference_owners(bundle, *, observe: Callable | None = None):
    inputs = ReferenceOwnerInput.from_bundle(bundle)
    digest = sha256(canonical_bytes(inputs.bundle())).hexdigest()
    ref = SOURCE + ":sha256:" + digest
    base, cage = inputs.longitudinal, inputs.cage
    calls = []

    def call(name, function, *args, **kwargs):
        if observe: observe("ENTERED", name, digest, None)
        result = function(*args, **kwargs)
        calls.append(name)
        if observe: observe("RETURNED", name, digest, result)
        return result

    longitudinal = call("tbdy_engine.design.columns.column_design_engine.evaluate_column_design",
                        calculate_reference, base.bundle())
    directions = tuple(transverse_owner.TransverseDirectionFacts(
        direction="DIR" + suffix,
        confined_core_width_bk_mm=getattr(cage, "bk_dir" + suffix + "_mm"),
        provided_ash_mm2=getattr(cage, "ash_dir" + suffix + "_mm2"),
        horizontal_leg_spacing_mm=getattr(cage, "leg_spacing_dir" + suffix + "_mm"),
        source_refs=(ref, "NUMERICAL_REFERENCE_DIRECTION_MAPPING_ASSUMPTION_NOT_NATIVE"),
        provided_asw_mm2=getattr(cage, "asw_dir" + suffix + "_mm2"),
        effective_depth_mm=getattr(cage, "effective_depth_dir" + suffix + "_mm"),
        shear_mapping_proven=True,
        qualified_vc_kn=getattr(cage, "reference_vc_dir" + suffix + "_kn"),
        p7_ve_kn=getattr(cage, "reference_ve_dir" + suffix + "_kn"),
    ) for suffix in ("2", "3"))
    request = transverse_owner.ColumnTransverseConfinementInput(
        component_id=REFERENCE_ID, story="REFERENCE", section="EXPLICIT_REFERENCE_RECTANGLE",
        high_ductility_applies=True, limited_ductility_applies=False,
        ts500_general_applies=True, cantilever_column=False,
        clear_height_mm=base.free_length_mm, width_mm=base.width_mm, depth_mm=base.depth_mm,
        gross_area_ac_mm2=cage.gross_area_ac_mm2, confined_core_area_ack_mm2=cage.confined_core_area_ack_mm2,
        fck_mpa=base.fck_mpa, fywk_mpa=cage.fywk_mpa, axial_design_force_nd_n=base.nd_kn * 1000,
        transverse_diameter_mm=base.tie_diameter_mm, confinement_spacing_mm=cage.confinement_spacing_mm,
        middle_spacing_mm=cage.middle_spacing_mm, provided_confinement_region_length_mm=cage.confinement_region_length_mm,
        directions=directions, arrangement=None, source_refs=(ref,),
        restrained_longitudinal_bar_spacing_mm=cage.restrained_bar_spacing_mm,
        fywd_mpa=cage.fywd_mpa, shear_spacing_mm=cage.shear_spacing_mm,
        model_fingerprint=None, evidence_epoch_id=None, design_result_ref=None,
    )
    transverse = call("tbdy_engine.regulatory.column_transverse_confinement.evaluate_column_transverse_confinement",
                      transverse_owner.evaluate_column_transverse_confinement, request, selected_rebar=None)
    return ReferenceOwnerCalculation(inputs, digest, longitudinal, request, transverse, tuple(calls))
