from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping, Protocol

from tbdy_engine.design.beams.beam_core_runner import run_beam_core_artifact_path
from tbdy_engine.design.beams.canonical_input_bridge import (
    build_canonical_beam_input_from_normalized,
)
from tbdy_engine.design.beams.etabs_input_adapter import (
    build_normalized_beam_input_from_etabs_payload,
)


class EtabsBeamPayloadProvider(Protocol):
    def get_beam_payload(self) -> Mapping[str, object]:
        ...


def is_live_etabs_smoke_enabled() -> bool:
    return os.environ.get("TBDY_RUN_LIVE_ETABS_SMOKE") == "1"


def run_etabs_beamcore_smoke_from_provider(
    *,
    provider: EtabsBeamPayloadProvider,
    output_dir: str | Path,
) -> dict[str, object]:
    raw_payload = provider.get_beam_payload()
    normalized = build_normalized_beam_input_from_etabs_payload(raw_payload)
    canonical = build_canonical_beam_input_from_normalized(normalized)
    artifact_result = run_beam_core_artifact_path(
        beam_input=canonical,
        output_dir=output_dir,
    )

    check_types = _check_types_from_json(artifact_result.json_path)

    return {
        "status": artifact_result.status,
        "package_count": artifact_result.package_count,
        "check_count": artifact_result.check_count,
        "json_path": artifact_result.json_path,
        "xlsx_path": artifact_result.xlsx_path,
        "normalized": normalized,
        "canonical": canonical,
        "beam_core_status": artifact_result.artifact_result.beam_core.status,
        "capacity_design_check_types": tuple(
            check_type
            for check_type in check_types
            if check_type in {
                "beam_shear_capacity_design_ve_le_vr",
                "beam_shear_capacity_design_ve_le_085_vmax",
            }
        ),
        "check_types": check_types,
    }


def _check_types_from_json(json_path: Path) -> tuple[str, ...]:
    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    checks = payload.get("checks") if isinstance(payload, dict) else None
    if not isinstance(checks, list):
        return ()

    return tuple(
        str(check.get("check_type"))
        for check in checks
        if isinstance(check, dict)
    )