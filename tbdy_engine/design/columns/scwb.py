
"""
tbdy/design_engine/modules/column_design_module.py (GÜNCELLENDİ)

RebarSet ve PMM modüllerini kullanan, JSON-first çıktı üreten
birleşik kolon tasarım modülü.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json
import logging

from .rebar_set import (
    RebarSetBuilder,
    RebarSetResolver,
    RebarSet,
    RebarRequirements,
)
from .pmm_check import PMMChecker, PMMResult
from ..core.materials import MaterialSet

logger = logging.getLogger("column_design")


@dataclass
class ColumnDesignOutputJSON:
    """
    Tek kolon için JSON-first tasarım çıktısı.

    Tüm çıktılar .to_dict() ve .to_json() ile serialize edilebilir.
    """
    column_label: str
    story: str
    section_name: str
    status: str = "NO_DATA"

    # Alt modül çıktıları (hepsi .to_dict() yapabilir)
    geometry: Optional[Dict[str, Any]] = None
    materials: Optional[Dict[str, Any]] = None
    forces: Optional[Dict[str, Any]] = None
    rebar_set: Optional[Dict[str, Any]] = None
    pmm_result: Optional[Dict[str, Any]] = None

    # Check sonuçları
    checks: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Özet
    governing_check: str = ""
    governing_ratio: float = 0.0
    issues: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column_label": self.column_label,
            "story": self.story,
            "section_name": self.section_name,
            "status": self.status,
            "geometry": self.geometry,
            "materials": self.materials,
            "forces": self.forces,
            "rebar_set": self.rebar_set,
            "pmm_result": self.pmm_result,
            "checks": self.checks,
            "governing": {
                "check": self.governing_check,
                "ratio": round(self.governing_ratio, 4),
            },
            "issues": self.issues,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class ColumnPackageOutputJSON:
    """Tüm kolon tasarım paketi JSON çıktısı"""
    package_id: str = "COLUMN_DESIGN_PACKAGE"
    title: str = "Column Design Package"
    package_status: str = "NO_DATA"

    columns: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    issues: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_id": self.package_id,
            "title": self.title,
            "package_status": self.package_status,
            "columns": self.columns,
            "summary": self.summary,
            "issues": self.issues,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class ColumnDesignModuleV2:
    """
    Kolon Tasarım Modülü v2.

    RebarSet modülü + PMM modülü + TBDY 2018 check'leri.
    JSON-first çıktı.
    """

    def __init__(self, ctx: Any):
        self.ctx = ctx
        self._materials: Optional[MaterialSet] = None
        self._rebar_sets: Dict[str, RebarSet] = {}
        self._pmm_checker = PMMChecker()

    def run(self) -> ColumnPackageOutputJSON:
        """Tüm kolon tasarımını çalıştır"""
        logger.info("ColumnDesignModuleV2: başlatılıyor...")

        # 1. Malzemeleri çöz
        self._resolve_materials()

        # 2. Donatı setlerini çöz (RebarSet modülü)
        resolver = RebarSetResolver(self.ctx)
        self._rebar_sets = resolver.resolve_all()

        # 3. Her kolon için tasarım yap
        columns_output = []

        topo_columns = self.ctx.topology.get("columns", [])
        section_dims = self.ctx.geometry.get("section_dims", {})
        frame_sections = self.ctx.geometry.get("column_sections", {})
        forces_map = self.ctx.envelopes.get("column_forces_map", {})
        etabs_design = self.ctx.design_metadata.get("column_design_summary")

        # ETABS PMM index
        etabs_pmm_index = {}
        if etabs_design is not None and not getattr(etabs_design, "empty", True):
            for _, row in etabs_design.iterrows():
                label = str(row.get("label", ""))
                if label:
                    etabs_pmm_index[label] = float(row.get("pm_ratio", row.get("pmm_ratio", 1.0)))

        for col_data in topo_columns:
            label = str(col_data.get("label", ""))
            if not label:
                continue

            # Geometry
            section_name = frame_sections.get(label, str(col_data.get("section", "")))
            dims = section_dims.get(section_name, {})
            width = float(dims.get("width_m", dims.get("b_min_m", 0.3)))
            depth = float(dims.get("depth_m", dims.get("b_max_m", 0.3)))
            story = str(col_data.get("story", ""))

            # Forces
            forces = forces_map.get(label, {})
            Nd = float(forces.get("P_max", 0))
            Mxd = float(forces.get("M3_max", 0))  # major
            Myd = float(forces.get("M2_max", 0))  # minor
            Vx = float(forces.get("V2_max", 0))
            Vy = float(forces.get("V3_max", 0))

            # Rebar
            rebar_set = self._rebar_sets.get(label)

            # PMM
            etabs_ratio = etabs_pmm_index.get(label)

            As_total = rebar_set.As_total_mm2 if rebar_set else 0
            n_bars = rebar_set.longitudinal.n_bars if rebar_set else 8

            pmm_result = self._pmm_checker.check(
                column_label=label,
                Nd_kn=Nd,
                Mxd_knm=Mxd,
                Myd_knm=Myd,
                width_m=width,
                depth_m=depth,
                fcd_mpa=self._materials.fcd if self._materials else 0,
                fyd_mpa=self._materials.fyd if self._materials else 0,
                As_total_mm2=As_total,
                n_bars=n_bars,
                etabs_pmm_ratio=etabs_ratio,
            )

            # Check'ler
            checks = self._run_checks(
                label=label,
                width_m=width,
                depth_m=depth,
                Nd_kn=Nd,
                Vx_kn=Vx,
                Vy_kn=Vy,
                rebar_set=rebar_set,
                pmm_result=pmm_result,
            )

            # Status
            statuses = [c["status"] for c in checks.values()]
            if "FAIL" in statuses:
                status = "FAIL"
            elif "NO_DATA" in statuses and "OK" not in statuses:
                status = "NO_DATA"
            else:
                status = "OK"

            # Governing
            ratios = [(n, c["ratio"]) for n, c in checks.items() if c.get("ratio", 0) > 0]
            gov_check, gov_ratio = max(ratios, key=lambda x: x[1]) if ratios else ("", 0.0)

            # Issues
            issues = []
            if rebar_set and rebar_set.violations:
                for v in rebar_set.violations:
                    issues.append({
                        "severity": "WARNING",
                        "code": "REBAR_MINIMUM",
                        "message": v,
                    })

            col_out = ColumnDesignOutputJSON(
                column_label=label,
                story=story,
                section_name=section_name,
                status=status,
                geometry={
                    "width_m": width,
                    "depth_m": depth,
                    "area_m2": width * depth,
                    "area_mm2": width * depth * 1e6,
                },
                materials={
                    "fck_mpa": self._materials.fck if self._materials else None,
                    "fcd_mpa": self._materials.fcd if self._materials else None,
                    "fyk_mpa": self._materials.fyk if self._materials else None,
                    "fyd_mpa": self._materials.fyd if self._materials else None,
                } if self._materials else None,
                forces={
                    "Nd_kn": Nd,
                    "Mxd_knm": Mxd,
                    "Myd_knm": Myd,
                    "Vx_kn": Vx,
                    "Vy_kn": Vy,
                },
                rebar_set=rebar_set.to_dict() if rebar_set else None,
                pmm_result=pmm_result.to_dict(),
                checks=checks,
                governing_check=gov_check,
                governing_ratio=gov_ratio,
                issues=issues,
            )

            columns_output.append(col_out.to_dict())

        # Package summary
        ok = sum(1 for c in columns_output if c["status"] == "OK")
        fail = sum(1 for c in columns_output if c["status"] == "FAIL")
        warn = sum(1 for c in columns_output if c["status"] == "WARNING")
        nodata = sum(1 for c in columns_output if c["status"] == "NO_DATA")

        if fail > 0:
            pkg_status = "FAIL"
        elif nodata == len(columns_output):
            pkg_status = "NO_DATA"
        else:
            pkg_status = "OK"

        package = ColumnPackageOutputJSON(
            package_status=pkg_status,
            columns=columns_output,
            summary={
                "total_columns": len(columns_output),
                "ok": ok,
                "fail": fail,
                "warning": warn,
                "no_data": nodata,
            },
        )

        logger.info(f"ColumnDesignModuleV2: {len(columns_output)} kolon, {ok} OK, {fail} FAIL")

        return package

    def _resolve_materials(self):
        """Malzeme setini çöz"""
        db = self.ctx.design_basis
        self._materials = MaterialSet(
            fck=float(db.get("fck_mpa", 30)),
            fcd=float(db.get("fcd_mpa", 20)),
            fyk=float(db.get("fyk_mpa", 420)),
            fyd=float(db.get("fyd_mpa", 365)),
            fywd=float(db.get("fywd_mpa", 365)),
            gamma_c=float(db.get("gamma_c", 1.5)),
            gamma_s=float(db.get("gamma_s", 1.15)),
        )

    def _run_checks(
            self,
            label: str,
            width_m: float,
            depth_m: float,
            Nd_kn: float,
            Vx_kn: float,
            Vy_kn: float,
            rebar_set: Optional[RebarSet],
            pmm_result: PMMResult,
    ) -> Dict[str, Dict[str, Any]]:
        """Tüm TBDY 2018 check'lerini çalıştır"""
        checks = {}

        # Geometri
        b_min = int(min(width_m, depth_m) * 1000)
        area_mm2 = width_m * depth_m * 1e6

        checks["geometry"] = {
            "status": "OK" if b_min >= 300 and area_mm2 >= 75000 else "FAIL",
            "ratio": min(b_min / 300, area_mm2 / 75000),
            "value": b_min,
            "limit": 300,
            "unit": "mm",
            "message": f"b_min={b_min}mm, A={area_mm2:.0f}mm²" if b_min >= 300 else f"b_min={b_min}mm < 300mm",
            "tbdy_ref": "TBDY 2018 7.3.1",
        }

        # Eksenel
        if self._materials:
            N_limit = 0.40 * area_mm2 * self._materials.fcd / 1000
            axial_ratio = abs(Nd_kn) / N_limit if N_limit > 0 else 999
            checks["axial"] = {
                "status": "OK" if axial_ratio <= 1.0 else "FAIL",
                "ratio": axial_ratio,
                "value": abs(Nd_kn),
                "limit": N_limit,
                "unit": "kN",
                "message": f"Nd={abs(Nd_kn):.0f}kN, limit={N_limit:.0f}kN",
                "tbdy_ref": "TBDY 2018 7.3.2",
            }
        else:
            checks["axial"] = {"status": "NO_DATA", "message": "Malzeme yok"}

        # PMM (harici modülden)
        checks["pmm"] = {
            "status": pmm_result.status,
            "ratio": pmm_result.governing_ratio,
            "value": pmm_result.governing_ratio,
            "limit": 1.0,
            "unit": "ratio",
            "message": pmm_result.message,
            "source": pmm_result.source,
            "tbdy_ref": "TBDY 2018 7.3.3",
        }

        # Donatı minimum
        if rebar_set:
            checks["rebar_minimum"] = {
                "status": "FAIL" if rebar_set.violations else "OK",
                "ratio": 1.0 if rebar_set.is_minimum_satisfied else 0.0,
                "value": rebar_set.rho_pct,
                "limit": rebar_set.requirements.min_rho_pct,
                "unit": "%",
                "message": "; ".join(
                    rebar_set.violations) if rebar_set.violations else f"ρ={rebar_set.rho_pct:.2f}% OK",
                "tbdy_ref": "TBDY 2018 7.3.2",
            }
        else:
            checks["rebar_minimum"] = {"status": "NO_DATA", "message": "Donatı verisi yok"}

        return checks


def run_column_design_v2(ctx: Any) -> ColumnPackageOutputJSON:
    """Convenience: context'ten kolon tasarımını JSON olarak çalıştır"""
    module = ColumnDesignModuleV2(ctx)
    return module.run()
