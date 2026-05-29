from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BeamCheckEvaluation:
    check_type: str
    status: str
    demand: float | None
    capacity: float | None
    ratio: float | None
    unit: str | None = None
    code_ref: str | None = None
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class BeamEvaluationPackage:
    component: str
    checks: tuple[BeamCheckEvaluation, ...]
    evidence: Mapping[str, object]
    messages: tuple[str, ...] = ()
    story: str | None = None
    section: str | None = None


class BeamDesignModule:
    def __init__(self, context: Mapping[str, object]) -> None:
        self.context = context

    def run(self) -> tuple[BeamEvaluationPackage, ...]:
        return build_beam_evaluation_packages(self.context)


def build_beam_evaluation_packages(context: Mapping[str, object]) -> tuple[BeamEvaluationPackage, ...]:
    metadata = _mapping(context.get("design_metadata"))
    design_rows = [row for row in _sequence(metadata.get("beam_design_summary_rows")) if _mapping(row).get("label")]
    flexure_grouped = _mapping(metadata.get("beam_flexure_grouped"))
    shear_grouped = _mapping(metadata.get("beam_shear_grouped"))

    packages: list[BeamEvaluationPackage] = []
    for raw_row in design_rows:
        row = _mapping(raw_row)
        component = _text(row.get("label"))
        story = _optional_text(row.get("story"))
        section = _optional_text(row.get("section"))
        key = _text(row.get("key")) or _beam_key(story, component)
        evidence = _package_evidence(row, key)
        checks = (
            _geometry_check(row),
            _flexure_check(_mapping(flexure_grouped.get(key))),
            _shear_check(_mapping(shear_grouped.get(key))),
        )
        packages.append(
            BeamEvaluationPackage(
                component=component,
                checks=checks,
                evidence=evidence,
                messages=(),
                story=story,
                section=section,
            )
        )
    return tuple(packages)


def _geometry_check(row: Mapping[str, object]) -> BeamCheckEvaluation:
    return BeamCheckEvaluation(
        check_type="beam_geometry",
        status="OK",
        demand=None,
        capacity=None,
        ratio=None,
        unit="mm",
        code_ref="TBDY 2018 §7.4.1",
        messages=("geometry package emitted",),
    )


def _flexure_check(grouped: Mapping[str, object]) -> BeamCheckEvaluation:
    row = _first_mapping(
        grouped.get("governing_ratio"),
        grouped.get("governing_positive"),
        grouped.get("governing_negative"),
    )
    if not row:
        return BeamCheckEvaluation(
            check_type="beam_flexure",
            status="NO_DATA",
            demand=None,
            capacity=None,
            ratio=None,
            unit="kNm",
            code_ref="TBDY 2018 §7.4.2",
            messages=("TABLE_FIELD_MISSING: flexure governing row",),
        )
    return BeamCheckEvaluation(
        check_type="beam_flexure",
        status=_status(row),
        demand=_first_number(row.get("moment"), row.get("m_pos"), row.get("m_neg")),
        capacity=None,
        ratio=_number_or_none(row.get("ratio")),
        unit="kNm",
        code_ref="TBDY 2018 §7.4.2",
        messages=_row_messages(row),
    )


def _shear_check(grouped: Mapping[str, object]) -> BeamCheckEvaluation:
    row = _first_mapping(grouped.get("governing_ratio"), grouped.get("governing_shear"))
    if not row:
        return BeamCheckEvaluation(
            check_type="beam_shear",
            status="NO_DATA",
            demand=None,
            capacity=None,
            ratio=None,
            unit="kN",
            code_ref="TBDY 2018 §7.4.5",
            messages=("TABLE_FIELD_MISSING: shear governing row",),
        )
    return BeamCheckEvaluation(
        check_type="beam_shear",
        status=_status(row),
        demand=_first_number(row.get("shear"), row.get("v_support")),
        capacity=None,
        ratio=_number_or_none(row.get("ratio")),
        unit="kN",
        code_ref="TBDY 2018 §7.4.5",
        messages=_row_messages(row),
    )


def _package_evidence(row: Mapping[str, object], key: str) -> Mapping[str, object]:
    return {
        "key": key,
        "source_table": row.get("source_table"),
        "source_row": row.get("source_row"),
        "source_columns": tuple(_sequence(row.get("source_columns"))),
    }


def _row_messages(row: Mapping[str, object]) -> tuple[str, ...]:
    diagnostic = _optional_text(row.get("diagnostic"))
    if diagnostic:
        return (diagnostic,)
    return ()


def _status(row: Mapping[str, object]) -> str:
    status = _optional_text(row.get("status"))
    return status or "OK"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()


def _first_mapping(*values: object) -> Mapping[str, object]:
    for value in values:
        if isinstance(value, Mapping) and value:
            return value
    return {}


def _first_number(*values: object) -> float | None:
    for value in values:
        number = _number_or_none(value)
        if number is not None:
            return number
    return None


def _number_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _optional_text(value: object) -> str | None:
    text = _text(value).strip()
    return text or None


def _beam_key(story: str | None, component: str) -> str:
    return f"{story or ''}|{component}"
