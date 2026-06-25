"""CoverageBuilder to authoritative geometry CheckInput orchestration.

This module owns only the boundary between contract-derived coverage and the
existing typed geometry input adapter. It does not invoke CheckEngine,
compute engineering quantities, or emit CheckResult objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from tbdy_engine.checks.input_adapter import (
    CheckInputBuildResult,
    build_geometry_check_inputs_from_feature_snapshot_and_coverage,
    geometry_check_ids_for_component_type,
)
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.coverage.models import CoverageRow
from tbdy_engine.features.snapshot import FeatureSnapshot

_COLUMN_GEOMETRY_OVERLAY = (
    "check_catalog_c13_5_p1_column_geometry.yaml"
)


@dataclass(frozen=True, slots=True)
class CoverageAuthoritativeGeometryAssembly:
    snapshot: FeatureSnapshot
    coverage_rows: tuple[CoverageRow, ...]
    build_result: CheckInputBuildResult

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, FeatureSnapshot):
            raise TypeError("snapshot must be FeatureSnapshot")
        rows = tuple(self.coverage_rows)
        if any(not isinstance(row, CoverageRow) for row in rows):
            raise TypeError(
                "coverage_rows must contain CoverageRow objects"
            )
        if not isinstance(self.build_result, CheckInputBuildResult):
            raise TypeError(
                "build_result must be CheckInputBuildResult"
            )
        object.__setattr__(self, "coverage_rows", rows)


def load_geometry_contract_bundle(
    catalog_dir: str | Path,
) -> ContractBundle:
    """Load base contracts and merge the committed column overlay."""

    root = Path(catalog_dir)
    base = load_contracts(root)
    overlay_path = root / _COLUMN_GEOMETRY_OVERLAY
    if not overlay_path.is_file():
        raise FileNotFoundError(
            f"Required geometry check overlay is missing: "
            f"{overlay_path}"
        )

    overlay_payload = yaml.safe_load(
        overlay_path.read_text(encoding="utf-8")
    )
    if not isinstance(overlay_payload, Mapping):
        raise ValueError(
            f"{_COLUMN_GEOMETRY_OVERLAY} must contain a YAML object"
        )
    overlay_checks = overlay_payload.get("checks")
    if not isinstance(overlay_checks, Mapping):
        raise ValueError(
            f"{_COLUMN_GEOMETRY_OVERLAY} must contain a checks mapping"
        )

    catalogs: dict[str, Any] = dict(base.catalogs)
    check_catalog = dict(base.catalog("check_catalog.yaml"))
    base_checks = check_catalog.get("checks")
    if not isinstance(base_checks, Mapping):
        raise ValueError(
            "check_catalog.yaml must contain a checks mapping"
        )

    merged_checks = dict(base_checks)
    duplicate_ids = sorted(
        set(merged_checks).intersection(overlay_checks)
    )
    if duplicate_ids:
        raise ValueError(
            "Geometry overlay duplicates base check ids: "
            + ", ".join(str(item) for item in duplicate_ids)
        )
    merged_checks.update(
        {
            str(key): value
            for key, value in overlay_checks.items()
        }
    )
    check_catalog["checks"] = merged_checks
    catalogs["check_catalog.yaml"] = check_catalog

    return ContractBundle.from_raw(
        catalog_dir=str(root),
        catalogs=catalogs,
        schemas=base.schemas,
        examples=base.examples,
    )


def assemble_geometry_check_inputs(
    *,
    snapshot: FeatureSnapshot,
    contract_bundle: ContractBundle,
) -> CoverageAuthoritativeGeometryAssembly:
    """Build coverage first and preserve its rows through the adapter."""

    if not isinstance(snapshot, FeatureSnapshot):
        raise TypeError("snapshot must be FeatureSnapshot")
    if not isinstance(contract_bundle, ContractBundle):
        raise TypeError("contract_bundle must be ContractBundle")

    check_ids = geometry_check_ids_for_component_type(
        snapshot.component_type
    )
    if not check_ids:
        build_result = (
            build_geometry_check_inputs_from_feature_snapshot_and_coverage(
                snapshot,
                (),
            )
        )
        return CoverageAuthoritativeGeometryAssembly(
            snapshot=snapshot,
            coverage_rows=(),
            build_result=build_result,
        )

    coverage_builder = CoverageBuilder(contract_bundle)
    coverage_rows = tuple(
        coverage_builder.build_row(
            snapshot,
            check_id,
            design_context=snapshot.identity,
        )
        for check_id in check_ids
    )
    build_result = (
        build_geometry_check_inputs_from_feature_snapshot_and_coverage(
            snapshot,
            coverage_rows,
        )
    )
    return CoverageAuthoritativeGeometryAssembly(
        snapshot=snapshot,
        coverage_rows=coverage_rows,
        build_result=build_result,
    )


__all__ = [
    "CoverageAuthoritativeGeometryAssembly",
    "assemble_geometry_check_inputs",
    "load_geometry_contract_bundle",
]
