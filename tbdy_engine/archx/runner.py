from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .beam_geometry import beam_geometry_package_to_check_results, build_workbench_cell, evaluate_beam_geometry_package
from .column_geometry import column_geometry_package_to_check_results, build_column_workbench_cell, evaluate_column_geometry_package
from .evaluation import EvaluationPackage
from .models import CanonicalSnapshot, CheckResult, WorkbenchCell
from .serialization import archx_run_result_to_dict
from .story_drift import build_story_workbench_cell, evaluate_story_drift_package, story_drift_package_to_check_results
from .workbench_bundle import build_workbench_bundle


SUPPORTED_CHECK_IDS = ["beam_geometry", "column_geometry", "story_drift"]
_STATUS_KEYS = ("OK", "FAIL", "WARNING", "NO_DATA", "ERROR")


@dataclass(frozen=True)
class ArchxRunResult:
    run_id: str
    supported_check_ids: list[str]
    requested_check_ids: list[str] | None
    evaluation_packages: list[EvaluationPackage]
    check_results: list[CheckResult]
    workbench_cells: list[WorkbenchCell]
    workbench_bundle: dict
    summary: dict
    diagnostics: list[str]

    def to_dict(self) -> dict:
        return archx_run_result_to_dict(self)


def run_archx_checks(
    snapshot: CanonicalSnapshot,
    check_ids: list[str] | None = None,
    run_id: str = "archx-run",
) -> ArchxRunResult:
    requested_check_ids = list(check_ids) if check_ids is not None else None
    selected_check_ids = _selected_check_ids(requested_check_ids)
    diagnostics = _unsupported_check_diagnostics(requested_check_ids)
    evaluation_packages: list[EvaluationPackage] = []
    check_results: list[CheckResult] = []

    if "beam_geometry" in selected_check_ids:
        _run_for_ids(
            sorted(snapshot.beams),
            "beam_geometry",
            evaluate_beam_geometry_package,
            beam_geometry_package_to_check_results,
            evaluation_packages,
            check_results,
            diagnostics,
        )
    if "column_geometry" in selected_check_ids:
        _run_for_ids(
            sorted(snapshot.columns),
            "column_geometry",
            evaluate_column_geometry_package,
            column_geometry_package_to_check_results,
            evaluation_packages,
            check_results,
            diagnostics,
        )
    if "story_drift" in selected_check_ids:
        _run_for_ids(
            sorted(snapshot.stories),
            "story_drift",
            evaluate_story_drift_package,
            story_drift_package_to_check_results,
            evaluation_packages,
            check_results,
            diagnostics,
        )

    workbench_cells = [_workbench_cell_for_result(result) for result in check_results]
    workbench_bundle = build_workbench_bundle(check_results, workbench_cells, run_id=run_id)
    summary = _build_summary(check_results, workbench_cells, evaluation_packages)
    diagnostics.extend(_package_diagnostics(evaluation_packages))
    return ArchxRunResult(
        run_id=run_id,
        supported_check_ids=list(SUPPORTED_CHECK_IDS),
        requested_check_ids=requested_check_ids,
        evaluation_packages=evaluation_packages,
        check_results=check_results,
        workbench_cells=workbench_cells,
        workbench_bundle=workbench_bundle,
        summary=summary,
        diagnostics=diagnostics,
    )


def _selected_check_ids(requested_check_ids: list[str] | None) -> set[str]:
    if requested_check_ids is None:
        return set(SUPPORTED_CHECK_IDS)
    requested = set(_expand_check_ids(requested_check_ids))
    return {check_id for check_id in SUPPORTED_CHECK_IDS if check_id in requested}


def _expand_check_ids(check_ids: list[str]) -> list[str]:
    expanded: list[str] = []
    for item in check_ids:
        expanded.extend(part.strip() for part in item.split(",") if part.strip())
    return expanded


def _unsupported_check_diagnostics(requested_check_ids: list[str] | None) -> list[str]:
    if requested_check_ids is None:
        return []
    requested = _expand_check_ids(requested_check_ids)
    return [
        f"Unsupported ARCH-X check_id: {check_id}"
        for check_id in requested
        if check_id not in SUPPORTED_CHECK_IDS
    ]


def _run_for_ids(
    element_ids: list[str],
    check_id: str,
    package_builder: Callable[[CanonicalSnapshot, str], EvaluationPackage],
    adapter: Callable[[EvaluationPackage], list[CheckResult]],
    evaluation_packages: list[EvaluationPackage],
    check_results: list[CheckResult],
    diagnostics: list[str],
) -> None:
    for element_id in element_ids:
        try:
            package = package_builder.__call__(_CURRENT_SNAPSHOT.get(), element_id)
            evaluation_packages.append(package)
            check_results.extend(adapter(package))
        except Exception as exc:
            diagnostics.append(
                f"ARCH-X check execution error check_id={check_id} element_id={element_id} "
                f"exception_type={type(exc).__name__} exception_message={exc}"
            )


def _workbench_cell_for_result(check_result: CheckResult) -> WorkbenchCell:
    if check_result.check_id == "beam_geometry":
        return build_workbench_cell(check_result)
    if check_result.check_id == "column_geometry":
        return build_column_workbench_cell(check_result)
    if check_result.check_id == "story_drift":
        return build_story_workbench_cell(check_result)
    raise ValueError(f"Unsupported ARCH-X check_id for workbench cell: {check_result.check_id}")


def _build_summary(
    check_results: list[CheckResult],
    workbench_cells: list[WorkbenchCell],
    evaluation_packages: list[EvaluationPackage],
) -> dict:
    by_status = {status: 0 for status in _STATUS_KEYS}
    by_check_id: dict[str, int] = {}
    by_report_section: dict[str, int] = {}
    for result in check_results:
        by_status[result.status] = by_status.get(result.status, 0) + 1
        by_check_id[result.check_id] = by_check_id.get(result.check_id, 0) + 1
        by_report_section[result.report_section] = by_report_section.get(result.report_section, 0) + 1
    return {
        "total_packages": len(evaluation_packages),
        "total_check_results": len(check_results),
        "total_workbench_cells": len(workbench_cells),
        "by_status": dict(sorted(by_status.items())),
        "by_check_id": dict(sorted(by_check_id.items())),
        "by_report_section": dict(sorted(by_report_section.items())),
    }


def _package_diagnostics(evaluation_packages: list[EvaluationPackage]) -> list[str]:
    diagnostics: list[str] = []
    for package in evaluation_packages:
        for diagnostic in package.diagnostics:
            diagnostics.append(f"{package.evaluation_id}: {diagnostic}")
        if package.status == "NO_DATA" and not package.diagnostics:
            diagnostics.append(f"{package.evaluation_id}: NO_DATA")
    return diagnostics


class _SnapshotContext:
    def __init__(self) -> None:
        self._snapshot: CanonicalSnapshot | None = None

    def set(self, snapshot: CanonicalSnapshot) -> None:
        self._snapshot = snapshot

    def get(self) -> CanonicalSnapshot:
        if self._snapshot is None:
            raise RuntimeError("ARCH-X snapshot context is not set.")
        return self._snapshot


_CURRENT_SNAPSHOT = _SnapshotContext()


def _run_for_ids_with_snapshot(
    snapshot: CanonicalSnapshot,
    element_ids: list[str],
    check_id: str,
    package_builder: Callable[[CanonicalSnapshot, str], EvaluationPackage],
    adapter: Callable[[EvaluationPackage], list[CheckResult]],
    evaluation_packages: list[EvaluationPackage],
    check_results: list[CheckResult],
    diagnostics: list[str],
) -> None:
    _CURRENT_SNAPSHOT.set(snapshot)
    _run_for_ids(element_ids, check_id, package_builder, adapter, evaluation_packages, check_results, diagnostics)
