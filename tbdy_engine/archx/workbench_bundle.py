from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .models import CheckResult, WorkbenchCell


BUNDLE_VERSION = "ARCH-X-WB-1"
STATUS_KEYS = ("ERROR", "FAIL", "NO_DATA", "OK", "WARNING")


def build_workbench_bundle(
    check_results: list[CheckResult],
    workbench_cells: list[WorkbenchCell],
    run_id: str = "test-run",
) -> dict[str, Any]:
    """Build a deterministic JSON-ready ARCH-X workbench bundle."""

    ordered_results = sorted(check_results, key=_result_sort_key)
    ordered_cells = sorted(workbench_cells, key=lambda cell: cell.cell_id)
    _validate_cells(ordered_results, ordered_cells)

    return {
        "bundle_version": BUNDLE_VERSION,
        "run_id": run_id,
        "check_count": len(ordered_results),
        "cell_count": len(ordered_cells),
        "summary": {
            "total": len(ordered_results),
            "by_status": _summary_by_status(ordered_results),
            "by_check_id": _summary_by_check_id(ordered_results),
            "by_report_section": _summary_by_report_section(ordered_results),
        },
        "check_results": [asdict(result) for result in ordered_results],
        "workbench_cells": [asdict(cell) for cell in ordered_cells],
        "index": {
            "by_check_id": _index_by_check_id(ordered_cells),
            "by_status": _index_by_status(ordered_cells),
            "by_report_section": _index_by_report_section(ordered_results, ordered_cells),
        },
    }


def _result_sort_key(result: CheckResult) -> tuple[str, str, str]:
    return (result.check_id, result.story, result.element_label)


def _result_key(result: CheckResult) -> tuple[str, str, str]:
    return (result.check_id, result.element_label, result.story)


def _cell_key(cell: WorkbenchCell) -> tuple[str, str, str]:
    return (cell.check_id, cell.element_label, cell.story)


def _validate_cells(check_results: list[CheckResult], workbench_cells: list[WorkbenchCell]) -> None:
    cell_keys = {_cell_key(cell) for cell in workbench_cells}
    missing = [result for result in check_results if _result_key(result) not in cell_keys]
    if missing:
        labels = ", ".join(f"{result.check_id}:{result.element_label}:{result.story}" for result in missing)
        raise ValueError(f"Missing WorkbenchCell for CheckResult: {labels}")


def _summary_by_status(check_results: list[CheckResult]) -> dict[str, int]:
    summary = {status: 0 for status in STATUS_KEYS}
    for result in check_results:
        summary[result.status] = summary.get(result.status, 0) + 1
    return dict(sorted(summary.items()))


def _summary_by_check_id(check_results: list[CheckResult]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for result in check_results:
        values = summary.setdefault(result.check_id, {"total": 0})
        values["total"] += 1
        values[result.status] = values.get(result.status, 0) + 1
    return {check_id: dict(sorted(values.items())) for check_id, values in sorted(summary.items())}


def _summary_by_report_section(check_results: list[CheckResult]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for result in check_results:
        summary[result.report_section] = summary.get(result.report_section, 0) + 1
    return dict(sorted(summary.items()))


def _index_by_check_id(workbench_cells: list[WorkbenchCell]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for cell in workbench_cells:
        index.setdefault(cell.check_id, []).append(cell.cell_id)
    return _sorted_index(index)


def _index_by_status(workbench_cells: list[WorkbenchCell]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {status: [] for status in STATUS_KEYS}
    for cell in workbench_cells:
        index.setdefault(cell.status, []).append(cell.cell_id)
    return _sorted_index(index)


def _index_by_report_section(
    check_results: list[CheckResult], workbench_cells: list[WorkbenchCell]
) -> dict[str, list[str]]:
    sections = {_result_key(result): result.report_section for result in check_results}
    index: dict[str, list[str]] = {}
    for cell in workbench_cells:
        section = sections.get(_cell_key(cell))
        if section is not None:
            index.setdefault(section, []).append(cell.cell_id)
    return _sorted_index(index)


def _sorted_index(index: dict[str, list[str]]) -> dict[str, list[str]]:
    return {key: sorted(values) for key, values in sorted(index.items())}
