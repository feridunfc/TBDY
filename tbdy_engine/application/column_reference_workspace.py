"""Offline reference-only application boundary for the existing column engine.

The example is not native evidence and cannot be promoted to a project column.
Only unit transport and typed input construction live here; all engineering
decisions remain in the existing pure design engine.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, fields
import hashlib
import json
import math

from tbdy_engine.design.columns.column_design_engine import ColumnDesignEngineResult, evaluate_column_design
from tbdy_engine.design.columns.column_design_demand_engine import ColumnComboDefinition
from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent
from tbdy_engine.design.columns.column_rebar_design_engine import ColumnRebarDesignInputs
from tbdy_engine.design.columns.rebar_catalog import build_rebar_catalog_from_rows
from tbdy_engine.design.columns.rebar_selection import ColumnDemandBasis, ColumnDemandState, ColumnRebarSelectionPolicy
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial
from tbdy_engine.design.columns.slenderness import ColumnSlendernessAxisBasis, ColumnSlendernessBasis, SWAY_PREVENTED

REFERENCE_ID = "REFERENCE-DEMO-COLUMN-V2"
REFERENCE_SOURCE = "EXPLICIT_REFERENCE_INPUT_NOT_ETABS_NOT_PROJECT"
UNITS = {"length": "mm", "force": "kN", "moment": "kN.m", "stress": "MPa"}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class ReferenceColumnInput:
    width_mm: float = 500.0
    depth_mm: float = 800.0
    free_length_mm: float = 3000.0
    k_m2: float = 1.0
    k_m3: float = 1.0
    moment_ratio_m2: float = 0.0
    moment_ratio_m3: float = 0.0
    fck_mpa: float = 35.0
    fcd_mpa: float = 23.333333333333332
    fyd_mpa: float = 434.7826086956522
    nd_kn: float = 1000.0
    m2_knm: float = -10.0
    m3_knm: float = 20.0
    clear_cover_mm: float = 40.0
    tie_diameter_mm: float = 10.0
    aggregate_max_mm: float = 25.0
    bar_diameters_mm: tuple[float, ...] = (14.0, 20.0, 25.0)

    def __post_init__(self) -> None:
        for field in fields(self):
            if field.name == "bar_diameters_mm":
                continue
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError(f"{field.name}: sonlu bir sayı gerekli.")
            if field.name.startswith("moment_ratio"):
                if not -1 <= value <= 1:
                    raise ValueError(f"{field.name}: -1 ile 1 arasında olmalı.")
            elif field.name not in {"m2_knm", "m3_knm"} and value <= 0:
                raise ValueError(f"{field.name}: sıfırdan büyük olmalı.")
        if not 100 <= self.width_mm <= 1500 or not 100 <= self.depth_mm <= 1500:
            raise ValueError("Referans arayüzü kesit boyut aralığı: 100-1500 mm.")
        if not 100 <= self.free_length_mm <= 20000 or not 0.1 <= self.k_m2 <= 4 or not 0.1 <= self.k_m3 <= 4:
            raise ValueError("Referans arayüzü ln/k aralığı dışında.")
        if self.nd_kn > 20000 or abs(self.m2_knm) > 10000 or abs(self.m3_knm) > 10000:
            raise ValueError("Referans arayüzü kuvvet/moment aralığı dışında.")
        bars = self.bar_diameters_mm
        if type(bars) is not tuple or not 1 <= len(bars) <= 6 or any(type(x) not in (int, float) or not math.isfinite(x) or not 14 <= x <= 40 for x in bars) or tuple(sorted(set(bars))) != bars:
            raise ValueError("Çap kataloğu: artan, benzersiz 14-40 mm; en fazla 6 çap.")
        # Material table and layout checks are delegated to their original owners.
        ColumnSectionMaterial(self.fck_mpa, self.fcd_mpa, self.fyd_mpa)

    @classmethod
    def from_bundle(cls, bundle: dict) -> "ReferenceColumnInput":
        if type(bundle) is not dict or set(bundle) != {"context", "source", "units", "values"}:
            raise ValueError("Tam referans girdi paketi gerekli.")
        if bundle["context"] != REFERENCE_ID or bundle["source"] != REFERENCE_SOURCE or bundle["units"] != UNITS:
            raise ValueError("Bağlam, kaynak veya birim kimliği farklı.")
        values = bundle["values"]
        if type(values) is not dict or set(values) != {f.name for f in fields(cls)}:
            raise ValueError("Eksik/bilinmeyen girdi; varsayılan kullanılmadı.")
        values = dict(values)
        if type(values["bar_diameters_mm"]) is not list:
            raise ValueError("Çap kataloğu bir liste olmalı.")
        values["bar_diameters_mm"] = tuple(values["bar_diameters_mm"])
        return cls(**values)

    def bundle(self) -> dict:
        values = asdict(self)
        values["bar_diameters_mm"] = list(self.bar_diameters_mm)
        return {"context": REFERENCE_ID, "source": REFERENCE_SOURCE, "units": dict(UNITS), "values": values}


@dataclass(frozen=True)
class ReferenceCalculation:
    inputs: ReferenceColumnInput
    input_sha256: str
    changed_fields: tuple[str, ...]
    engine_result: ColumnDesignEngineResult


def calculate_reference(bundle: dict) -> ReferenceCalculation:
    inputs = ReferenceColumnInput.from_bundle(bundle)
    digest = hashlib.sha256(canonical_bytes(inputs.bundle())).hexdigest()
    ref = f"{REFERENCE_SOURCE}:sha256:{digest}"
    # These assumptions are explicitly synthetic: both ends have the entered
    # demand, the linear reference combination has factor 1, sway is prevented,
    # and the entered ln/k/moment ratios are reference regulatory bases only.
    demands = tuple(ColumnDemandState(
        state_id=f"REFERENCE_D:{end}", component_id=REFERENCE_ID,
        output_case="REFERENCE_D", case_type="LinStatic", step_type=None,
        step_number=None, station_m=station, end_tag=end,
        nd_compression_n=inputs.nd_kn * 1000.0,
        m2_nmm=inputs.m2_knm * 1000000.0, m3_nmm=inputs.m3_knm * 1000000.0,
        source_identity=ref,
    ) for end, station in (("I_END", 0.0), ("J_END", inputs.free_length_mm / 1000.0)))
    axes = tuple(ColumnSlendernessAxisBasis(
        axis=axis, section_dimension_mm=dimension,
        free_length_ln_mm=inputs.free_length_mm, effective_length_factor_k=k,
        sway_classification=SWAY_PREVENTED, moment_ratio_m1_over_m2=ratio,
        source_refs=(ref,),
    ) for axis, dimension, k, ratio in (
        ("M2", inputs.depth_mm, inputs.k_m2, inputs.moment_ratio_m2),
        ("M3", inputs.width_mm, inputs.k_m3, inputs.moment_ratio_m3)))
    catalog = build_rebar_catalog_from_rows(
        tuple({"Name": str(d), "Diameter": d} for d in inputs.bar_diameters_mm),
        name_field="Name", diameter_field="Diameter", diameter_unit="mm", source_name=ref)
    result = evaluate_column_design(
        component_id=REFERENCE_ID,
        combo_definitions=(ColumnComboDefinition("REFERENCE_ULS", "LINEAR_ADD", (ComboPatternConstituent("REFERENCE_D", 1.0),)),),
        constituent_case_demands=demands, rebar_catalog=catalog,
        rebar_inputs=ColumnRebarDesignInputs(
            component_id=REFERENCE_ID, width_mm=inputs.width_mm, depth_mm=inputs.depth_mm,
            clear_cover_mm=inputs.clear_cover_mm, tie_diameter_mm=inputs.tie_diameter_mm,
            aggregate_max_mm=inputs.aggregate_max_mm,
            material=ColumnSectionMaterial(inputs.fck_mpa, inputs.fcd_mpa, inputs.fyd_mpa),
            demand_basis=ColumnDemandBasis("RESOLVED", "BLOCKED", "BLOCKED", "BLOCKED", (ref,)),
            selection_policy=ColumnRebarSelectionPolicy(angle_count=36, axial_tolerance_n=1000.0)),
        slenderness_basis=ColumnSlendernessBasis(REFERENCE_ID, axes[0], axes[1], (ref,)))
    default = ReferenceColumnInput()
    changed = tuple(f.name for f in fields(inputs) if getattr(inputs, f.name) != getattr(default, f.name))
    return ReferenceCalculation(inputs, digest, changed, result)
