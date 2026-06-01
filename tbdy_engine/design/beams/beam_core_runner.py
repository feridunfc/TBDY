from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from tbdy_engine.design.beams.beam_core_artifacts import (
    BeamCoreArtifactResult,
    generate_beam_core_artifacts,
)


@dataclass(frozen=True)
class BeamCoreRunnerResult:
    artifact_result: BeamCoreArtifactResult
    status: str
    package_count: int
    check_count: int
    json_path: Path
    xlsx_path: Path | None


def run_beam_core_artifact_path(
    *,
    beam_input: Mapping[str, object],
    output_dir: str | Path,
) -> BeamCoreRunnerResult:
    """Run the deterministic BeamCore artifact path from explicit canonical input."""

    artifact_result = generate_beam_core_artifacts(beam_input, Path(output_dir))

    return BeamCoreRunnerResult(
        artifact_result=artifact_result,
        status=artifact_result.status,
        package_count=len(artifact_result.packages),
        check_count=len(artifact_result.checks),
        json_path=artifact_result.json_path,
        xlsx_path=artifact_result.xlsx_path,
    )