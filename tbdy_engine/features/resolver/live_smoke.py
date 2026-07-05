"""C8/C8.1 live/probe FeatureResolver smoke.

This module resolves observed table data into FeatureSnapshot objects for a
manual/live smoke or fixture-backed smoke. It does not execute checks, does not
emit CheckResult objects, and never produces OK/FAIL verdicts.

C8.1 hardens live beam identity seeding, frame/section matching, unit-context
capture, and conservative unit normalization. All behavior remains diagnostic
FeatureResolver smoke only.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.features.diagnostics import FeatureDiagnostic, FeatureDiagnosticCode, FeatureDiagnosticSeverity
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus
from tbdy_engine.providers.table_registry import TableRegistry
from tbdy_engine.providers.etabs_display_table_parser import (
    _rows_from_data,
    parse_etabs_display_table_result,
)
from tbdy_engine.json_safe import to_jsonable

RESOLVER_NAME = "c8_3_live_geometry_resolver"

_COMBO_COLUMNS = {
    "OutputCase", "Output Case", "Combo", "DesignCombo", "LoadCombo", "Load Combination",
    "AsTopCombo", "AsBotCombo", "VCombo", "PMMCombo", "VMajCombo", "VMinCombo", "Case",
}
_IGNORED_COMBO_MARKERS = {"max", "combination", "min", "avg"}
_ENGINEERING_NUMERIC_UNITS = {"mm", "mm2", "MPa", "kN"}
_PREVIOUS_LIVE_PARTIAL_FEATURES = (
    "beam_unique_name",
    "beam_label",
    "beam_story",
    "beam_section_name",
    "beam_width_mm",
    "beam_depth_mm",
    "beam_length_mm",
)

_STORY_ALIASES = ("Story", "story")
_OUTPUT_CASE_ALIASES = ("OutputCase", "Output Case", "output_case", "case", "Case")
_DIRECTION_ALIASES = ("Direction", "direction", "dir", "Dir")
_DRIFT_ALIASES = ("Drift", "drift")
_RATIO_ALIASES = ("Ratio", "ratio")
_FX_ALIASES = ("FX", "Fx", "fx", "base_reaction_fx")
_FY_ALIASES = ("FY", "Fy", "fy", "base_reaction_fy")
_STORY_BASE_TABLE_KEYS = ("story_drifts", "story_max_over_avg_drifts", "base_reactions")
_STORY_BASE_TABLE_ALIASES = {
    "story_drifts": "Story Drifts",
    "story_max_over_avg_drifts": "Story Max Over Avg Drifts",
    "base_reactions": "Base Reactions",
}
_STORY_BASE_BAD_PARSER_STATUSES = {
    "",
    "EMPTY",
    "FAILED",
    "PARTIAL",
    "MALFORMED",
    "TABLE_MISSING",
    "TABLE_EMPTY",
    "EMPTY_TABLE",
    "HEADER_ONLY",
    "COM_CALL_FAILED",
    "TABLEDATA_EMPTY_DESPITE_RECORDS",
    "RESOLVER_ONLY_HAS_SAMPLE_ROWS",
}
_STORY_BASE_SAMPLE_SOURCE_FIELDS = {"sample_rows", "sample_rows_limited"}

_ETABS_FORCE_UNITS = {
    1: "lb",
    2: "kip",
    3: "N",
    4: "kN",
    5: "kgf",
    6: "tonf",
}
_ETABS_LENGTH_UNITS = {
    1: "in",
    2: "ft",
    3: "micron",
    4: "mm",
    5: "cm",
    6: "m",
}
_ETABS_TEMPERATURE_UNITS = {1: "F", 2: "C"}
_ETABS_PRESENT_UNIT_SYSTEMS = {
    1: ("lb", "in", "F"),
    2: ("lb", "ft", "F"),
    3: ("kip", "in", "F"),
    4: ("kip", "ft", "F"),
    5: ("kN", "mm", "C"),
    6: ("kN", "m", "C"),
    7: ("kgf", "mm", "C"),
    8: ("kgf", "m", "C"),
    9: ("N", "mm", "C"),
    10: ("N", "m", "C"),
    11: ("tonf", "mm", "C"),
    12: ("tonf", "m", "C"),
    13: ("kN", "cm", "C"),
    14: ("kgf", "cm", "C"),
    15: ("N", "cm", "C"),
    16: ("tonf", "cm", "C"),
}


@dataclass(frozen=True, slots=True)
class UnitContext:
    source: str = "unknown"
    etabs_present_units_raw: Any = None
    etabs_database_units: Any = None
    force_unit: str | None = None
    length_unit: str | None = None
    temperature_unit: str | None = None
    etabs_present_units_return_code: int | None = None
    unit_query_succeeded: bool = False
    run_id: str | None = None
    unit_query_status: str = "MISSING"
    unit_basis_confidence: str = "unknown"
    diagnostics: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    @property
    def resolved(self) -> bool:
        return self.unit_query_status == "RESOLVED" and bool(self.force_unit) and bool(self.length_unit)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "etabs_present_units_raw": self.etabs_present_units_raw,
            "etabs_database_units": self.etabs_database_units,
            "force_unit": self.force_unit,
            "length_unit": self.length_unit,
            "temperature_unit": self.temperature_unit,
            "etabs_present_units_return_code": self.etabs_present_units_return_code,
            "unit_query_succeeded": self.unit_query_succeeded,
            "run_id": self.run_id,
            "unit_query_status": self.unit_query_status,
            "unit_basis_confidence": self.unit_basis_confidence,
            "diagnostics": [dict(item) for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class SmokeOutputs:
    snapshots: tuple[FeatureSnapshot, ...]
    feature_resolution_report: tuple[Mapping[str, Any], ...]
    evidence_report: tuple[Mapping[str, Any], ...]
    missing_features_report: tuple[Mapping[str, Any], ...]
    coverage_preview: tuple[Mapping[str, Any], ...]
    legacy_alias_crosswalk_report: Mapping[str, Any]
    unit_context_report: Mapping[str, Any]
    unit_basis_report: Mapping[str, Any]
    unit_normalization_report: Mapping[str, Any]
    identity_resolution_report: Mapping[str, Any]
    geometry_resolution_report: Mapping[str, Any]
    geometry_source_table_debug_report: Mapping[str, Any]
    geometry_direct_api_report: Mapping[str, Any]
    raw_com_tuple_dump: Mapping[str, Any]
    parser_strategy_report: Mapping[str, Any]
    display_selection_diagnostics: Mapping[str, Any]
    working_vs_failing_table_comparison: Mapping[str, Any]
    story_base_table_debug_report: Mapping[str, Any]
    product_report_source_tables: Mapping[str, Any]
    live_failure_delta_report: Mapping[str, Any]
    boundary_report: Mapping[str, Any]


def _norm(text: Any) -> str:
    return str(text or "").strip()


def _norm_key(text: Any) -> str:
    return re.sub(r"[\s_/-]+", "", str(text or "").strip()).casefold()


def _to_number(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return value


def _to_finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    numeric = _to_number(value)
    if not isinstance(numeric, (int, float)) or isinstance(numeric, bool):
        return None
    parsed = float(numeric)
    return parsed if math.isfinite(parsed) else None


def _norm_story_value(value: Any) -> str:
    text = _norm(value)
    if not text:
        return ""
    compact = text.replace(",", ".")
    try:
        number = float(compact)
    except ValueError:
        return text.casefold()
    normalized = f"{number:.6f}".rstrip("0").rstrip(".")
    if number > 0 and text.lstrip().startswith("+"):
        return f"+{normalized}"
    return normalized


def _story_values_match(left: Any, right: Any) -> bool:
    if left in (None, "") or right in (None, ""):
        return False
    if _norm(left) == _norm(right):
        return True
    left_norm = _norm_story_value(left)
    right_norm = _norm_story_value(right)
    if left_norm == right_norm:
        return True
    # Numeric equivalence should tolerate a missing leading plus sign.
    return left_norm.lstrip("+") == right_norm.lstrip("+")


def _is_numeric(value: Any) -> bool:
    return isinstance(_to_number(value), (int, float))

def _first_present(row: Mapping[str, Any] | None, aliases: Sequence[str]) -> tuple[str | None, Any]:
    if not row:
        return None, None
    direct = {str(k): k for k in row.keys()}
    folded = {_norm_key(k): k for k in row.keys()}
    for alias in aliases:
        if alias in direct:
            key = direct[alias]
            return str(key), row[key]
        key = folded.get(_norm_key(alias))
        if key is not None:
            return str(key), row[key]
    return None, None


def _row_identity(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    identity: dict[str, Any] = {}
    for out, aliases in {
        "component": ("UniqueName", "Frame", "Beam", "Pier"),
        "label": ("Label", "Frame", "Beam"),
        "story": _STORY_ALIASES,
        "section": ("DesignSect", "AnalysisSect", "Section", "Name"),
        "station": ("Station", "Location"),
        "output_case": ("OutputCase", "Output Case", "Case"),
    }.items():
        _, value = _first_present(row, aliases)
        if value not in (None, ""):
            identity[out] = value
    return identity


def build_seed_identity_from_target(
    target_component: str | None,
    target_label: str | None,
    target_story: str | None,
    target_section: str | None,
) -> dict[str, str]:
    """Build ETABS table-keyed identity seed from live target arguments.

    The seed is source/selector data only. It is not used to fake observed
    feature values; identity features are resolved only from observed Frame
    Assignments, concrete design summary rows, or read-only direct ETABS API
    identity evidence.
    """
    seed: dict[str, str] = {}
    if target_component not in (None, ""):
        seed["UniqueName"] = str(target_component)
    if target_label not in (None, ""):
        seed["Label"] = str(target_label)
    if target_story not in (None, ""):
        seed["Story"] = str(target_story)
    if target_section not in (None, ""):
        seed["DesignSect"] = str(target_section)
        seed["AnalysisSect"] = str(target_section)
    return seed


def _canonical_identity_from_seed(seed: Mapping[str, Any] | None) -> dict[str, Any]:
    if not seed:
        return {}
    identity: dict[str, Any] = {}
    for out, aliases in {
        "component": ("component", "UniqueName", "Frame", "Beam", "Pier"),
        "label": ("label", "Label", "Frame", "Beam"),
        "story": ("story", "Story"),
        "section": ("section", "DesignSect", "AnalysisSect", "Section", "Name"),
        "station": ("station", "Station", "Location"),
        "output_case": ("output_case", "OutputCase", "Output Case", "Case"),
    }.items():
        _, value = _first_present(seed, aliases)
        if value not in (None, ""):
            identity[out] = value
    return identity


def _seed_identity_from_row(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    seed: dict[str, Any] = {}
    for out, aliases in {
        "UniqueName": ("UniqueName", "Frame", "Beam"),
        "Label": ("Label", "Frame", "Beam"),
        "Story": _STORY_ALIASES,
        "DesignSect": ("DesignSect", "Section"),
        "AnalysisSect": ("AnalysisSect",),
    }.items():
        _, value = _first_present(row, aliases)
        if value not in (None, ""):
            seed[out] = value
    if "DesignSect" not in seed and "AnalysisSect" in seed:
        seed["DesignSect"] = seed["AnalysisSect"]
    if "AnalysisSect" not in seed and "DesignSect" in seed:
        seed["AnalysisSect"] = seed["DesignSect"]
    return seed


def _json_safe(value: Any) -> Any:
    """Backward-compatible local wrapper for old tests/imports."""
    return to_jsonable(value)


def write_json_payload(path: Path, payload: Any) -> None:
    """Write a JSON report after explicit structural conversion.

    On conversion/write failure, create a minimal failure report and re-raise so
    the caller sees the problem instead of a silent partial smoke success.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        jsonable = to_jsonable(payload)
        path.write_text(json.dumps(jsonable, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        failure_payload = {
            "stage": "write_outputs",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "check_engine_executed": False,
            "check_result_emitted": False,
            "ok_fail_emitted": False,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            (path.parent / "serialization_failure_report.json").write_text(
                json.dumps(to_jsonable(failure_payload), indent=2, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
        finally:
            raise


def _candidate_unit_context(payload: Any) -> Mapping[str, Any] | None:
    if isinstance(payload, Mapping):
        candidate = payload.get("unit_context") or payload.get("fixture_unit_context") or payload.get("unit_basis")
        return candidate if isinstance(candidate, Mapping) else None
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        for item in payload:
            if isinstance(item, Mapping):
                candidate = item.get("unit_context") or item.get("fixture_unit_context")
                if isinstance(candidate, Mapping):
                    return candidate
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def decode_etabs_present_units(raw: Any, *, source: str = "live_etabs_present_units") -> dict[str, Any]:
    """Decode CSI ETABS present-unit return values without mutating the model.

    Handles both GetPresentUnits single enum values and GetPresentUnits_2 tuple
    shapes. The observed live tuple [4, 6, 2, 0] is interpreted as
    force=kN, length=m, temperature=C, return_code=0.
    """
    diagnostics: list[dict[str, Any]] = []
    force_unit = length_unit = temperature_unit = None
    return_code: int | None = None
    decoded = False

    if isinstance(raw, Mapping):
        if raw.get("force_unit") and raw.get("length_unit"):
            return {
                "source": str(raw.get("source") or source),
                "etabs_present_units_raw": raw.get("etabs_present_units_raw", raw),
                "force_unit": raw.get("force_unit"),
                "length_unit": raw.get("length_unit"),
                "temperature_unit": raw.get("temperature_unit"),
                "etabs_present_units_return_code": raw.get("etabs_present_units_return_code"),
                "unit_query_succeeded": bool(raw.get("unit_query_succeeded", True)),
                "unit_query_status": "RESOLVED",
                "unit_basis_confidence": str(raw.get("unit_basis_confidence") or "high"),
                "diagnostics": list(raw.get("diagnostics") or ()),
            }
        nested = raw.get("etabs_present_units_raw") or raw.get("raw") or raw.get("present_units")
        if nested is not None and nested is not raw:
            decoded_nested = decode_etabs_present_units(nested, source=str(raw.get("source") or source))
            decoded_nested["etabs_database_units"] = raw.get("etabs_database_units")
            return decoded_nested

    values = list(raw) if isinstance(raw, (list, tuple)) and not isinstance(raw, (str, bytes)) else None
    if values is not None:
        ints = [_int_or_none(v) for v in values]
        # Preferred GetPresentUnits_2 shape observed manually: [force, length, temp, ret].
        if len(ints) >= 4 and ints[0] in _ETABS_FORCE_UNITS and ints[1] in _ETABS_LENGTH_UNITS and ints[2] in _ETABS_TEMPERATURE_UNITS:
            force_unit = _ETABS_FORCE_UNITS[ints[0]]
            length_unit = _ETABS_LENGTH_UNITS[ints[1]]
            temperature_unit = _ETABS_TEMPERATURE_UNITS[ints[2]]
            return_code = ints[3]
            decoded = True
        # Some COM wrappers may prepend the return code: [ret, force, length, temp].
        elif len(ints) >= 4 and ints[1] in _ETABS_FORCE_UNITS and ints[2] in _ETABS_LENGTH_UNITS and ints[3] in _ETABS_TEMPERATURE_UNITS:
            return_code = ints[0]
            force_unit = _ETABS_FORCE_UNITS[ints[1]]
            length_unit = _ETABS_LENGTH_UNITS[ints[2]]
            temperature_unit = _ETABS_TEMPERATURE_UNITS[ints[3]]
            decoded = True
        else:
            diagnostics.append({"severity": "WARNING", "code": "UNIT_ENUM_DECODE_FAILED", "message": "ETABS present-unit tuple could not be decoded", "details": {"raw": values}})
    else:
        enum_value = _int_or_none(raw)
        if enum_value in _ETABS_PRESENT_UNIT_SYSTEMS:
            force_unit, length_unit, temperature_unit = _ETABS_PRESENT_UNIT_SYSTEMS[enum_value]
            decoded = True
        elif raw is not None:
            diagnostics.append({"severity": "WARNING", "code": "UNIT_ENUM_DECODE_FAILED", "message": "ETABS present-unit enum could not be decoded", "details": {"raw": raw}})

    return {
        "source": source if decoded else "unknown",
        "etabs_present_units_raw": raw,
        "force_unit": force_unit,
        "length_unit": length_unit,
        "temperature_unit": temperature_unit,
        "etabs_present_units_return_code": return_code,
        "unit_query_succeeded": decoded and (return_code in (None, 0)),
        "unit_query_status": "RESOLVED" if decoded and (return_code in (None, 0)) else ("PARTIAL" if raw is not None else "MISSING"),
        "unit_basis_confidence": "high" if decoded and (return_code in (None, 0)) else ("low" if raw is not None else "unknown"),
        "diagnostics": diagnostics,
    }


def unit_context_from_payload(payload: Any) -> UnitContext:
    candidate = _candidate_unit_context(payload)
    if not candidate:
        return UnitContext(
            source="unknown",
            unit_query_status="MISSING",
            unit_basis_confidence="unknown",
            unit_query_succeeded=False,
            diagnostics=(
                {"severity": "WARNING", "code": "UNIT_CONTEXT_MISSING", "message": "No fixture or live ETABS unit context was provided"},
            ),
        )

    decoded = decode_etabs_present_units(candidate.get("etabs_present_units_raw"), source=str(candidate.get("source") or "live_etabs_present_units")) if candidate.get("etabs_present_units_raw") is not None and not (candidate.get("force_unit") and candidate.get("length_unit")) else {}
    force_unit = candidate.get("force_unit") or decoded.get("force_unit")
    length_unit = candidate.get("length_unit") or decoded.get("length_unit")
    temperature_unit = candidate.get("temperature_unit") or decoded.get("temperature_unit")
    status_candidate = candidate.get("unit_query_status") or candidate.get("status")
    status = str(status_candidate or ("RESOLVED" if force_unit and length_unit else decoded.get("unit_query_status") or "MISSING"))
    if status == "RESOLVED" and not (force_unit and length_unit):
        status = "PARTIAL"
    diagnostics = list(candidate.get("diagnostics") or ()) + list(decoded.get("diagnostics") or ())
    return UnitContext(
        source=str(candidate.get("source") or decoded.get("source") or "fixture_declared_units"),
        etabs_present_units_raw=candidate.get("etabs_present_units_raw"),
        etabs_database_units=candidate.get("etabs_database_units"),
        force_unit=force_unit,
        length_unit=length_unit,
        temperature_unit=temperature_unit,
        etabs_present_units_return_code=candidate.get("etabs_present_units_return_code", decoded.get("etabs_present_units_return_code")),
        unit_query_succeeded=bool(candidate.get("unit_query_succeeded", decoded.get("unit_query_succeeded", status == "RESOLVED"))),
        run_id=candidate.get("run_id"),
        unit_query_status=status,
        unit_basis_confidence=str(candidate.get("unit_basis_confidence") or decoded.get("unit_basis_confidence") or ("high" if status == "RESOLVED" else "unknown")),
        diagnostics=tuple(diagnostics),
    )


def _table_items_from_payload(payload: Any) -> Sequence[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        for key in ("tables", "table_headers_report", "items"):
            value = payload.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return value  # type: ignore[return-value]
        return ()
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        return payload  # type: ignore[return-value]
    return ()


def classify_combo(raw_value: Any, *, source_column: str | None, policy: Mapping[str, Any]) -> tuple[str | None, tuple[FeatureDiagnostic, ...]]:
    text = _norm(raw_value)
    diagnostics: list[FeatureDiagnostic] = []
    if not text:
        return None, tuple()
    if source_column and source_column not in _COMBO_COLUMNS:
        return None, tuple()
    if text.casefold() in _IGNORED_COMBO_MARKERS:
        return None, tuple()
    try:
        float(text)
        return None, tuple()
    except ValueError:
        pass
    if source_column == "Case" and text.casefold().startswith("modal"):
        return "MODAL", tuple()
    review = policy.get("project_alias_review", {}).get("cracked_seismic_cases", ()) if isinstance(policy, Mapping) else ()
    for item in review:
        pattern = item.get("pattern")
        if pattern and re.match(pattern, text):
            family = item.get("diagnostic_family")
            diagnostics.append(
                FeatureDiagnostic(
                    severity=FeatureDiagnosticSeverity.WARNING,
                    code=FeatureDiagnosticCode.COMBO_ENGINEERING_REVIEW,
                    message="Project-specific combo/output case matched diagnostic family and requires engineering review",
                    details={"raw_value": text, "combo_family": family, "needs_engineering_review": bool(item.get("needs_engineering_review"))},
                )
            )
            return family, tuple(diagnostics)
    for rule in policy.get("matching_rules", ()) if isinstance(policy, Mapping) else ():
        family = rule.get("family")
        includes = rule.get("include_patterns", ()) or ()
        excludes = rule.get("exclude_patterns", ()) or ()
        if any(re.match(pat, text, flags=re.IGNORECASE) for pat in includes) and not any(re.match(pat, text, flags=re.IGNORECASE) for pat in excludes):
            return family, tuple()
    diagnostics.append(
        FeatureDiagnostic(
            severity=FeatureDiagnosticSeverity.WARNING,
            code=FeatureDiagnosticCode.COMBO_UNKNOWN,
            message="Combo/output case could not be matched to a contract family; evidence preserved as diagnostic metadata",
            details={"raw_value": text},
        )
    )
    return None, tuple(diagnostics)


def _raw_table_diagnostics_from_item(item: Mapping[str, Any], *, headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    raw = item.get("raw_table_diagnostics") or item.get("raw_table_debug") or item.get("debug") or {}
    if not isinstance(raw, Mapping):
        raw = {}
    number_records = raw.get("number_records", item.get("row_count_reported", item.get("number_records", len(rows))))
    number_fields = raw.get("number_fields", item.get("number_fields"))
    header_count = len(headers)
    number_fields_detected = raw.get("number_fields_detected", item.get("number_fields_detected", number_fields))
    number_fields_source = raw.get("number_fields_source", item.get("number_fields_source"))
    if number_fields_source == "ambiguous":
        number_fields = None
        number_fields_detected = None
    elif number_fields is None and header_count:
        number_fields = header_count
        number_fields_detected = header_count
        number_fields_source = number_fields_source or "header_count_fallback"
    return {
        "table_name": item.get("actual_table_name") or item.get("table_name"),
        "return_code": raw.get("return_code", item.get("return_code")),
        "number_fields": number_fields,
        "number_fields_detected": number_fields_detected,
        "number_fields_source": number_fields_source or "header_count_fallback",
        "header_count": header_count,
        "number_records": number_records,
        "fields": list(raw.get("fields") or raw.get("field_keys") or item.get("field_keys") or headers),
        "table_data_length": raw.get("table_data_length", item.get("table_data_length", len(rows) * len(headers))),
        "expected_flat_length": raw.get("expected_flat_length", (int(number_records) * len(headers)) if isinstance(number_records, int) else None),
        "parser_status": raw.get("parser_status", raw.get("row_parse_status", item.get("fetch_status", "UNKNOWN"))),
        "signature_attempts": list(raw.get("signature_attempts") or item.get("signature_attempts") or ()),
        "selected_signature": dict(raw.get("selected_signature") or item.get("selected_signature") or {}),
        "selected_signature_reason": raw.get("selected_signature_reason", item.get("selected_signature_reason")),
        "parser_status_by_signature": dict(raw.get("parser_status_by_signature") or item.get("parser_status_by_signature") or {}),
        "table_data_length_by_signature": dict(raw.get("table_data_length_by_signature") or item.get("table_data_length_by_signature") or {}),
        "number_records_by_signature": dict(raw.get("number_records_by_signature") or item.get("number_records_by_signature") or {}),
        "preferred_output_case": raw.get("preferred_output_case", item.get("preferred_output_case")),
        "preferred_output_kind_detected": raw.get("preferred_output_kind_detected", item.get("preferred_output_kind_detected", "unknown")),
        "attempted_case_fallback": raw.get("attempted_case_fallback", item.get("attempted_case_fallback", False)),
        "skipped_case_selection_because_combo_succeeded": raw.get("skipped_case_selection_because_combo_succeeded", item.get("skipped_case_selection_because_combo_succeeded", False)),
        "display_selection_attempted": raw.get("display_selection_attempted", item.get("display_selection_attempted", False)),
        "display_selection_attempts": list(raw.get("display_selection_attempts") or item.get("display_selection_attempts") or ()),
        "display_selection_selected_method": raw.get("display_selection_selected_method", item.get("display_selection_selected_method")),
        "display_selection_success": raw.get("display_selection_success", item.get("display_selection_success", False)),
        "fetch_after_display_selection": raw.get("fetch_after_display_selection", item.get("fetch_after_display_selection", False)),
    }


def _raw_table_diagnostics_from_table(table: CanonicalTable | None) -> dict[str, Any]:
    if table is None:
        return {
            "table_name": None,
            "return_code": None,
            "number_fields": 0,
            "number_records": 0,
            "fields": [],
            "table_data_length": 0,
            "expected_flat_length": None,
            "parser_status": "TABLE_MISSING",
        }
    raw = table.units.get("raw_table_diagnostics") if isinstance(table.units, Mapping) else None
    if isinstance(raw, Mapping):
        out = dict(raw)
        out.setdefault("header_count", len(table.columns))
        if out.get("number_fields_source") == "ambiguous":
            out["number_fields"] = None
            out["number_fields_detected"] = None
        else:
            out.setdefault("number_fields_detected", out.get("number_fields"))
            out.setdefault("number_fields_source", "raw_table_diagnostics")
        out.setdefault("signature_attempts", [])
        out.setdefault("selected_signature", {})
        out.setdefault("selected_signature_reason", None)
        out.setdefault("parser_status_by_signature", {})
        out.setdefault("table_data_length_by_signature", {})
        out.setdefault("number_records_by_signature", {})
        out.setdefault("preferred_output_kind_detected", "unknown")
        out.setdefault("attempted_case_fallback", False)
        out.setdefault("skipped_case_selection_because_combo_succeeded", False)
        out.setdefault("display_selection_attempted", False)
        out.setdefault("display_selection_attempts", [])
        out.setdefault("display_selection_selected_method", None)
        out.setdefault("display_selection_success", False)
        out.setdefault("fetch_after_display_selection", False)
        return out
    return {
        "table_name": table.actual_table_name,
        "return_code": None,
        "number_fields": len(table.columns),
        "number_records": len(table.rows),
        "fields": list(table.columns),
        "table_data_length": len(table.rows) * len(table.columns),
        "expected_flat_length": len(table.rows) * len(table.columns),
        "parser_status": "FETCHED" if table.rows else "EMPTY",
    }


def _tabledata_empty_despite_records(raw: Mapping[str, Any]) -> bool:
    try:
        records = int(raw.get("number_records") or 0)
    except Exception:
        records = 0
    try:
        length = int(raw.get("table_data_length") or 0)
    except Exception:
        length = 0
    return records > 0 and length == 0


def _classified_parser_status(raw: Mapping[str, Any], *, row_count: int, headers: Sequence[str]) -> str:
    if row_count > 0:
        return "PARSED_ROWS"
    if _tabledata_empty_despite_records(raw):
        return "TABLEDATA_EMPTY_DESPITE_RECORDS"
    if headers:
        return "HEADER_ONLY"
    if str(raw.get("parser_status") or "").casefold() in {"failed", "com_call_failed"}:
        return "COM_CALL_FAILED"
    return str(raw.get("parser_status") or "EMPTY_TABLE")


class C8LiveFeatureResolverSmoke:
    """Resolve a small observed feature subset from canonical ETABS/probe tables."""

    def __init__(
        self,
        contract_bundle: ContractBundle,
        tables: Mapping[str, CanonicalTable] | Sequence[CanonicalTable],
        *,
        unit_context: UnitContext | Mapping[str, Any] | None = None,
        target_component: str | None = None,
        target_label: str | None = None,
        target_story: str | None = None,
        target_section: str | None = None,
        preferred_output_case: str | None = None,
        direct_api_geometry: Mapping[str, Any] | None = None,
        table_extraction_debug: Mapping[str, Any] | None = None,
    ) -> None:
        self.contract_bundle = contract_bundle
        table_registry_catalog = contract_bundle.catalog("table_registry.yaml")
        self.table_registry = table_registry_catalog.get("tables", {})
        self._table_registry_contract = TableRegistry.from_dict(table_registry_catalog)
        self.tables = self._normalize_tables(tables)
        self.feature_catalog = contract_bundle.catalog("feature_catalog.yaml").get("features", {})
        self.load_combo_policy = contract_bundle.catalog("load_combo_policy.yaml")
        if isinstance(unit_context, UnitContext):
            self.unit_context = unit_context
        elif isinstance(unit_context, Mapping):
            self.unit_context = unit_context_from_payload({"unit_context": dict(unit_context)})
        else:
            table_units = next((dict(t.units) for t in self.tables.values() if getattr(t, "units", None) and t.units.get("unit_context_source")), None)
            if table_units:
                self.unit_context = UnitContext(
                    source=table_units.get("unit_context_source", "fixture_declared_units"),
                    etabs_present_units_raw=table_units.get("etabs_present_units_raw"),
                    etabs_database_units=table_units.get("etabs_database_units"),
                    force_unit=table_units.get("force_unit"),
                    length_unit=table_units.get("length_unit"),
                    temperature_unit=table_units.get("temperature_unit"),
                    etabs_present_units_return_code=table_units.get("etabs_present_units_return_code"),
                    unit_query_succeeded=bool(table_units.get("unit_query_succeeded", table_units.get("unit_query_status") == "RESOLVED")),
                    run_id=table_units.get("run_id"),
                    unit_query_status=table_units.get("unit_query_status", "RESOLVED"),
                    unit_basis_confidence=table_units.get("unit_basis_confidence", "high"),
                )
            else:
                self.unit_context = UnitContext(
                    source="unknown",
                    unit_query_status="MISSING",
                    diagnostics=({"severity": "WARNING", "code": "UNIT_CONTEXT_MISSING", "message": "Unit context missing"},),
                )
        self.target = {
            "component": target_component,
            "label": target_label,
            "story": target_story,
            "section": target_section,
        }
        self.preferred_output_case = str(preferred_output_case or "Crack_SeisY_UpSoil")
        self.direct_api_geometry = dict(direct_api_geometry or {})
        self.table_extraction_debug = dict(table_extraction_debug or {})
        self._unit_evidence: dict[str, dict[str, Any]] = {}
        self._identity_report: dict[str, Any] = {}
        self._geometry_debug: dict[str, Any] = {}
        self._geometry_direct_api_report: dict[str, Any] = {"used": False, "diagnostics": []}

    def _normalize_tables(self, tables: Mapping[str, CanonicalTable] | Sequence[CanonicalTable]) -> dict[str, CanonicalTable]:
        """Index one CanonicalTable object under primary, legacy, and observed names.

        Compatibility keys come only from the existing table catalog's
        ``compatibility_alias_for`` relationships.  No CanonicalTable is cloned
        and conflicting objects for the same compatibility family fail closed.
        """
        if isinstance(tables, Mapping):
            base = dict(tables)
        else:
            base = {t.table_key: t for t in tables}
        out: dict[str, CanonicalTable] = {}

        def register(alias: Any, table: CanonicalTable) -> None:
            if alias in (None, ""):
                return
            key = str(alias)
            existing = out.get(key)
            if existing is not None and existing is not table:
                raise ValueError(f"Conflicting CanonicalTable objects for table alias {key!r}")
            out[key] = table

        for input_key, table in base.items():
            direct_keys = (str(input_key), table.table_key)
            for key in direct_keys:
                register(key, table)
                for compatibility_key in self._table_registry_contract.compatibility_keys_for_key(key):
                    register(compatibility_key, table)

            if table.actual_table_name:
                register(table.actual_table_name, table)
                primary_key = self._table_registry_contract.canonical_key_for_alias(table.actual_table_name)
                if primary_key:
                    for compatibility_key in self._table_registry_contract.compatibility_keys_for_key(primary_key):
                        register(compatibility_key, table)
        return out

    def _table(self, table_key: str) -> CanonicalTable | None:
        return self.tables.get(table_key)

    def _first_row(self, table_key: str) -> Mapping[str, Any] | None:
        table = self._table(table_key)
        return table.rows[0] if table and table.rows else None

    def _available_alias_samples(self, rows: Sequence[Mapping[str, Any]], aliases: Sequence[str], *, limit: int = 10) -> list[Any]:
        samples: list[Any] = []
        seen: set[str] = set()
        for row in rows:
            _, value = _first_present(row, aliases)
            if value in (None, ""):
                continue
            key = _norm(value).casefold()
            if key in seen:
                continue
            seen.add(key)
            samples.append(value)
            if len(samples) >= limit:
                break
        return samples

    def _row_has_any_column(self, row: Mapping[str, Any], aliases: Sequence[str]) -> bool:
        column, value = _first_present(row, aliases)
        return column is not None and value not in (None, "")

    def _row_has_all_alias_groups(self, row: Mapping[str, Any], alias_groups: Sequence[Sequence[str]]) -> bool:
        for aliases in alias_groups:
            column, value = _first_present(row, aliases)
            if column is None or value in (None, ""):
                return False
        return True

    def _row_has_numeric_alias(self, row: Mapping[str, Any], aliases: Sequence[str]) -> bool:
        column, value = _first_present(row, aliases)
        return column is not None and _is_numeric(value)

    def _row_has_finite_numeric_alias(self, row: Mapping[str, Any], aliases: Sequence[str]) -> bool:
        column, value = _first_present(row, aliases)
        return column is not None and _to_finite_float(value) is not None

    def _table_row_index(self, table_key: str, row: Mapping[str, Any] | None) -> int | None:
        table = self._table(table_key)
        if table is None or row is None:
            return None
        for index, candidate in enumerate(table.rows):
            if candidate is row or dict(candidate) == dict(row):
                return index
        return None

    def _stable_source_row_reference(self, table_key: str, row: Mapping[str, Any] | None) -> str | None:
        index = self._table_row_index(table_key, row)
        if index is None:
            return None
        table = self._table(table_key)
        actual = table.actual_table_name if table else table_key
        return f"{table_key}|actual={actual}|row_index={index}"

    def _story_base_required_alias_groups(self, table_key: str) -> tuple[tuple[str, tuple[str, ...], bool], ...]:
        if table_key == "story_drifts":
            return (
                ("story", tuple(_STORY_ALIASES), False),
                ("output_case", tuple(_OUTPUT_CASE_ALIASES), False),
                ("direction", tuple(_DIRECTION_ALIASES), False),
                ("drift", tuple(_DRIFT_ALIASES), True),
            )
        if table_key == "story_max_over_avg_drifts":
            return (
                ("story", tuple(_STORY_ALIASES), False),
                ("output_case", tuple(_OUTPUT_CASE_ALIASES), False),
                ("ratio", tuple(_RATIO_ALIASES), True),
            )
        if table_key == "base_reactions":
            return (
                ("output_case", tuple(_OUTPUT_CASE_ALIASES), False),
                ("fx", tuple(_FX_ALIASES), True),
                ("fy", tuple(_FY_ALIASES), True),
            )
        return tuple()

    def _story_base_table_readiness_diagnostics(self, table_key: str) -> tuple[FeatureDiagnostic, ...]:
        table = self._table(table_key)
        if table is None:
            return tuple()
        diagnostics: list[FeatureDiagnostic] = []
        units = table.units if isinstance(table.units, Mapping) else {}
        raw = _raw_table_diagnostics_from_table(table)
        source_field = str(units.get("source_row_storage_field_used") or "")
        parser_status = str(raw.get("parser_status") or units.get("parser_status") or "").strip().upper()
        resolver_row_count = len(table.rows)
        reported_row_count = _int_or_none(raw.get("number_records"))

        ingestion_diagnostics = tuple(
            item for item in units.get("resolver_ingestion_diagnostics", ())
            if isinstance(item, Mapping)
        )
        sample_only = source_field in _STORY_BASE_SAMPLE_SOURCE_FIELDS or any(
            str(item.get("code") or "") == "RESOLVER_ONLY_HAS_SAMPLE_ROWS" for item in ingestion_diagnostics
        )
        if sample_only:
            diagnostics.append(self._diag(
                FeatureDiagnosticCode.STORY_BASE_SOURCE_INCOMPLETE,
                "Story/base resolver source exposes only debug sample rows; complete production rows are required",
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                source_row_storage_field_used=source_field,
                reported_row_count=reported_row_count,
                resolver_row_count=resolver_row_count,
            ))
            for item in ingestion_diagnostics:
                if str(item.get("code") or "") == "RESOLVER_ONLY_HAS_SAMPLE_ROWS":
                    diagnostics.append(self._diag(
                        FeatureDiagnosticCode.RESOLVER_ONLY_HAS_SAMPLE_ROWS,
                        str(item.get("message") or "Resolver only has debug sample rows"),
                        **dict(item.get("details") or {}),
                    ))

        if parser_status in _STORY_BASE_BAD_PARSER_STATUSES:
            diagnostics.append(self._diag(
                FeatureDiagnosticCode.STORY_BASE_SOURCE_INCOMPLETE,
                "Story/base source table parser status is not a complete parsed-row status",
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                parser_status=parser_status,
                reported_row_count=reported_row_count,
                resolver_row_count=resolver_row_count,
            ))
        if resolver_row_count <= 0:
            diagnostics.append(self._diag(
                FeatureDiagnosticCode.STORY_BASE_SOURCE_INCOMPLETE,
                "Story/base source table has no resolver rows",
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                parser_status=parser_status,
                reported_row_count=reported_row_count,
                resolver_row_count=resolver_row_count,
            ))
        if reported_row_count is not None and reported_row_count != resolver_row_count:
            diagnostics.append(self._diag(
                FeatureDiagnosticCode.STORY_BASE_SOURCE_INCOMPLETE,
                "Story/base reported row count does not match resolver row count",
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                reported_row_count=reported_row_count,
                resolver_row_count=resolver_row_count,
            ))

        required_groups = self._story_base_required_alias_groups(table_key)
        headers = tuple(str(h) for h in table.columns)
        missing_columns: list[str] = []
        for name, aliases, _numeric in required_groups:
            header_present = any(_norm_key(header) in {_norm_key(alias) for alias in aliases} for header in headers)
            row_present = any(_first_present(row, aliases)[0] is not None for row in table.rows)
            if not header_present and not row_present:
                missing_columns.append(name)
        if missing_columns:
            diagnostics.append(self._diag(
                FeatureDiagnosticCode.STORY_BASE_REQUIRED_COLUMN_MISSING,
                "Story/base source table is missing required columns",
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                missing_columns=missing_columns,
                headers=list(headers),
            ))

        invalid_rows: list[dict[str, Any]] = []
        for index, row in enumerate(table.rows):
            invalid_fields: list[str] = []
            for name, aliases, numeric in required_groups:
                column, value = _first_present(row, aliases)
                if column is None or value in (None, ""):
                    invalid_fields.append(name)
                elif numeric and _to_finite_float(value) is None:
                    invalid_fields.append(name)
            if invalid_fields:
                invalid_rows.append({"row_index": index, "invalid_fields": invalid_fields})
        if invalid_rows:
            diagnostics.append(self._diag(
                FeatureDiagnosticCode.STORY_BASE_VALUE_INVALID,
                "Every story/base source row must contain finite numeric required values and required identity fields",
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                invalid_row_count=len(invalid_rows),
                invalid_rows=invalid_rows[:20],
                resolver_row_count=resolver_row_count,
            ))

        preferred = _norm(self.preferred_output_case)
        if preferred and table.rows:
            available_cases = [
                _norm(_first_present(row, _OUTPUT_CASE_ALIASES)[1])
                for row in table.rows
                if _norm(_first_present(row, _OUTPUT_CASE_ALIASES)[1])
            ]
            if preferred.casefold() not in {case.casefold() for case in available_cases}:
                diagnostics.append(self._diag(
                    FeatureDiagnosticCode.STORY_BASE_OUTPUT_CASE_UNAVAILABLE,
                    "Preferred story/base output case is unavailable; resolver will not silently fall back to another case",
                    table_key=table_key,
                    actual_table_name=table.actual_table_name,
                    preferred_output_case=preferred,
                    available_output_cases=sorted(set(available_cases), key=str.casefold),
                ))
        return tuple(diagnostics)

    def _story_base_table_ready(self, table_key: str) -> bool:
        return not self._story_base_table_readiness_diagnostics(table_key)

    def _story_base_evidence_source_row(
        self,
        table_key: str,
        row: Mapping[str, Any] | None,
        *,
        selection_reason: str | None = None,
    ) -> Mapping[str, Any]:
        if row is None:
            return {}
        table = self._table(table_key)
        raw = _raw_table_diagnostics_from_table(table)
        index = self._table_row_index(table_key, row)
        _, output_case = _first_present(row, _OUTPUT_CASE_ALIASES)
        _, story = _first_present(row, _STORY_ALIASES)
        _, direction = _first_present(row, _DIRECTION_ALIASES)
        source_row = {
            **_row_identity(row),
            "story": story if story not in (None, "") else _row_identity(row).get("story"),
            "output_case": output_case if output_case not in (None, "") else _row_identity(row).get("output_case"),
            "direction": direction if direction not in (None, "") else None,
            "row_index": index,
            "stable_row_reference": self._stable_source_row_reference(table_key, row),
            "selection_reason": selection_reason or self._story_base_selected_reason(table_key, table, row),
            "preferred_output_case": self.preferred_output_case,
            "reported_row_count": _int_or_none(raw.get("number_records")),
            "resolver_row_count": len(table.rows) if table else None,
            "source_row_storage_field_used": table.units.get("source_row_storage_field_used") if table and isinstance(table.units, Mapping) else None,
            "complete_source_row": _json_safe(dict(row)),
            "complete_source_row_items": tuple((str(key), _json_safe(value)) for key, value in row.items()),
        }
        return {key: value for key, value in source_row.items() if value is not None}

    def _select_row(
        self,
        table_key: str,
        *,
        required_aliases: Sequence[str] = (),
        story_aliases: Sequence[str] = _STORY_ALIASES,
        prefer_target_story: bool = False,
    ) -> Mapping[str, Any] | None:
        """Select a real observed source row, never a placeholder.

        C11.1.3 guard: story/global rows must not depend on smoke component
        placeholders.  When target_story is known, match using normalized story
        comparison; otherwise choose the first row containing required observed
        columns.
        """
        table = self._table(table_key)
        if table is None or not table.rows:
            return None
        candidates: list[Mapping[str, Any]] = []
        target_story = self.target.get("story")
        if prefer_target_story and target_story not in (None, ""):
            for row in table.rows:
                _, story = _first_present(row, story_aliases)
                if _story_values_match(story, target_story):
                    candidates.append(row)
        candidates.extend(row for row in table.rows if row not in candidates)
        if required_aliases:
            return next((row for row in candidates if self._row_has_any_column(row, required_aliases)), candidates[0] if candidates else None)
        return candidates[0] if candidates else None

    def _select_story_drift_row(self) -> Mapping[str, Any] | None:
        table_key = "story_drifts"
        table = self._table(table_key)
        if table is None or not table.rows or not self._story_base_table_ready(table_key):
            return None
        required = (_STORY_ALIASES, _OUTPUT_CASE_ALIASES, _DIRECTION_ALIASES, _DRIFT_ALIASES)
        candidates = list(table.rows)
        target_story = self.target.get("story")
        if target_story not in (None, ""):
            candidates = [row for row in candidates if _story_values_match(_first_present(row, _STORY_ALIASES)[1], target_story)]
        preferred = self.preferred_output_case.casefold()
        if preferred:
            candidates = [row for row in candidates if _norm(_first_present(row, _OUTPUT_CASE_ALIASES)[1]).casefold() == preferred]
        valid = [row for row in candidates if self._row_has_all_alias_groups(row, required) and self._row_has_finite_numeric_alias(row, _DRIFT_ALIASES)]
        max_step = [row for row in valid if _norm(_first_present(row, ("StepType", "Step Type"))[1]).casefold() == "max"]
        valid = max_step or valid
        return max(valid, key=lambda row: _to_finite_float(_first_present(row, _DRIFT_ALIASES)[1]) or float("-inf")) if valid else None

    def _select_story_torsion_row(self) -> Mapping[str, Any] | None:
        table_key = "story_max_over_avg_drifts"
        table = self._table(table_key)
        if table is None or not table.rows or not self._story_base_table_ready(table_key):
            return None
        required = (_STORY_ALIASES, _OUTPUT_CASE_ALIASES, _RATIO_ALIASES)
        candidates = list(table.rows)
        target_story = self.target.get("story")
        if target_story not in (None, ""):
            candidates = [row for row in candidates if _story_values_match(_first_present(row, _STORY_ALIASES)[1], target_story)]
        preferred = self.preferred_output_case.casefold()
        if preferred:
            candidates = [row for row in candidates if _norm(_first_present(row, _OUTPUT_CASE_ALIASES)[1]).casefold() == preferred]
        valid = [row for row in candidates if self._row_has_all_alias_groups(row, required) and self._row_has_finite_numeric_alias(row, _RATIO_ALIASES)]
        max_step = [row for row in valid if _norm(_first_present(row, ("StepType", "Step Type"))[1]).casefold() == "max"]
        return (max_step or valid)[0] if (max_step or valid) else None

    def _select_base_reaction_row(self) -> Mapping[str, Any] | None:
        """Select base reactions for the explicit preferred output case only."""
        table_key = "base_reactions"
        table = self._table(table_key)
        if table is None or not table.rows or not self._story_base_table_ready(table_key):
            return None
        preferred = self.preferred_output_case.casefold()
        valid_rows = [
            row for row in table.rows
            if self._row_has_finite_numeric_alias(row, _FX_ALIASES)
            and self._row_has_finite_numeric_alias(row, _FY_ALIASES)
            and (not preferred or _norm(_first_present(row, _OUTPUT_CASE_ALIASES)[1]).casefold() == preferred)
        ]
        max_step = [row for row in valid_rows if _norm(_first_present(row, ("StepType", "Step Type"))[1]).casefold() == "max"]
        return (max_step or valid_rows)[0] if (max_step or valid_rows) else None

    def _diag(self, code: FeatureDiagnosticCode | str, message: str, **details: Any) -> FeatureDiagnostic:
        return FeatureDiagnostic(severity=FeatureDiagnosticSeverity.WARNING, code=code, message=message, details=details)

    def _semantic_role(self, feature_name: str) -> str:
        return str(self.feature_catalog.get(feature_name, {}).get("semantic_role", "OBSERVED_VALUE"))

    def _unit(self, feature_name: str) -> str:
        return str(self.feature_catalog.get(feature_name, {}).get("unit", ""))

    def _required_unit_context(self, target_unit: str) -> bool:
        return target_unit in _ENGINEERING_NUMERIC_UNITS

    def _raw_unit_for_target(self, target_unit: str) -> str:
        length = (self.unit_context.length_unit or "").strip()
        force = (self.unit_context.force_unit or "").strip()
        if target_unit == "mm":
            return length or "unknown_length"
        if target_unit == "mm2":
            return f"{length}2" if length else "unknown_area"
        if target_unit == "MPa":
            if force and length:
                return f"{force}/{length}2"
            return "unknown_stress"
        if target_unit == "kN":
            return force or "unknown_force"
        return target_unit

    def _unit_diag(self, code: FeatureDiagnosticCode | str, message: str, **details: Any) -> FeatureDiagnostic:
        return FeatureDiagnostic(severity=FeatureDiagnosticSeverity.WARNING, code=code, message=message, details=details)

    def _normalize_value(self, feature_name: str, raw_value: Any, target_unit: str) -> tuple[Any, dict[str, Any], tuple[FeatureDiagnostic, ...], bool]:
        """Return normalized value, unit_evidence, diagnostics, and whether normalized value is safe."""
        numeric = _to_number(raw_value)
        unit_evidence = {
            "raw_value": raw_value,
            "raw_unit": self._raw_unit_for_target(target_unit),
            "normalized_value": numeric,
            "normalized_unit": target_unit,
            "unit_context_source": self.unit_context.source,
            "unit_normalization_status": "NOT_APPLICABLE" if not target_unit else "UNCHANGED",
            "conversion_applied": False,
            "conversion_formula": None,
            "diagnostics": [],
        }
        diagnostics: list[FeatureDiagnostic] = []
        if not target_unit or not isinstance(numeric, (int, float)):
            return numeric, unit_evidence, tuple(), True
        if self._required_unit_context(target_unit) and not self.unit_context.resolved:
            unit_evidence["unit_normalization_status"] = "UNVERIFIED"
            unit_evidence["diagnostics"].extend(["UNIT_CONTEXT_MISSING", "UNIT_NORMALIZATION_UNVERIFIED"])
            diagnostics.extend([
                self._unit_diag(FeatureDiagnosticCode.UNIT_CONTEXT_MISSING, "Unit context missing; numeric engineering feature was not silently normalized", feature_name=feature_name),
                self._unit_diag(FeatureDiagnosticCode.UNIT_NORMALIZATION_UNVERIFIED, "Unit normalization basis is unknown or unverified", feature_name=feature_name, target_unit=target_unit),
            ])
            return None, unit_evidence, tuple(diagnostics), False

        force = (self.unit_context.force_unit or "").strip().lower()
        length = (self.unit_context.length_unit or "").strip().lower()
        normalized = float(numeric)
        formula = None
        converted = False
        status = "RESOLVED"

        if target_unit == "mm":
            if length == "m":
                normalized = float(numeric) * 1000.0
                formula = "value_m * 1000 = value_mm"
                converted = True
            elif length == "cm":
                normalized = float(numeric) * 10.0
                formula = "value_cm * 10 = value_mm"
                converted = True
            elif length == "mm":
                normalized = float(numeric)
            else:
                status = "UNVERIFIED"
        elif target_unit == "mm2":
            if feature_name == "beam_shear_rebar_etabs_required_mm2":
                status = "SEMANTICS_REVIEW"
                diagnostics.append(self._unit_diag(FeatureDiagnosticCode.SHEAR_REBAR_UNIT_SEMANTICS_REVIEW, "VRebar unit semantics require engineering review; value preserved as observed evidence", feature_name=feature_name, raw_unit=unit_evidence["raw_unit"]))
                normalized = float(numeric)
            elif length == "m":
                normalized = float(numeric) * 1_000_000.0
                formula = "value_m2 * 1_000_000 = value_mm2"
                converted = True
            elif length == "cm":
                normalized = float(numeric) * 100.0
                formula = "value_cm2 * 100 = value_mm2"
                converted = True
            elif length == "mm":
                normalized = float(numeric)
            else:
                status = "UNVERIFIED"
        elif target_unit == "MPa":
            if force == "kn" and length == "m":
                normalized = float(numeric) * 0.001
                formula = "value_kN_per_m2 * 0.001 = value_MPa"
                converted = True
            elif force == "n" and length == "mm":
                normalized = float(numeric)
            else:
                status = "UNVERIFIED"
        elif target_unit == "kN":
            if force == "n":
                normalized = float(numeric) / 1000.0
                formula = "value_N / 1000 = value_kN"
                converted = True
            elif force == "kn":
                normalized = float(numeric)
            else:
                status = "UNVERIFIED"

        if status == "UNVERIFIED":
            unit_evidence["unit_normalization_status"] = "UNVERIFIED"
            unit_evidence["diagnostics"].append("UNIT_NORMALIZATION_UNVERIFIED")
            diagnostics.append(self._unit_diag(FeatureDiagnosticCode.UNIT_NORMALIZATION_UNVERIFIED, "Unit normalization basis is unknown or unsupported for target unit", feature_name=feature_name, raw_unit=unit_evidence["raw_unit"], target_unit=target_unit))
            return None, unit_evidence, tuple(diagnostics), False

        unit_evidence.update({
            "normalized_value": normalized,
            "unit_normalization_status": "SEMANTICS_REVIEW" if status == "SEMANTICS_REVIEW" else ("NORMALIZED" if converted else "RESOLVED"),
            "conversion_applied": converted,
            "conversion_formula": formula,
        })
        if converted:
            diagnostics.append(self._unit_diag(FeatureDiagnosticCode.UNIT_NORMALIZED, "Value normalized using explicit unit context", feature_name=feature_name, raw_unit=unit_evidence["raw_unit"], normalized_unit=target_unit, conversion_formula=formula))
        return normalized, unit_evidence, tuple(diagnostics), True

    def _missing(self, feature_name: str, reason: str, *, unit: str = "", table_key: str | None = None, actual_table_name: str | None = None, column: str | None = None, row: Mapping[str, Any] | None = None, diagnostics: Sequence[FeatureDiagnostic] = ()) -> FeatureValue:
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.MISSING,
            source_table=table_key,
            actual_table_name=actual_table_name,
            source_column=column,
            source_row=_row_identity(row),
            unit=unit,
            resolver=RESOLVER_NAME,
            reason=reason,
        )
        return FeatureValue(feature_name=feature_name, value=None, unit=unit, semantic_role=self._semantic_role(feature_name), status=FeatureValueStatus.MISSING, evidence=[evidence], diagnostics=tuple(diagnostics))

    def _partial(self, feature_name: str, reason: str, *, unit: str = "", table_key: str | None = None, actual_table_name: str | None = None, column: str | None = None, row: Mapping[str, Any] | None = None, diagnostics: Sequence[FeatureDiagnostic] = ()) -> FeatureValue:
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.PARTIAL,
            source_table=table_key,
            actual_table_name=actual_table_name,
            source_column=column,
            source_row=_row_identity(row),
            unit=unit,
            resolver=RESOLVER_NAME,
            reason=reason,
        )
        return FeatureValue(feature_name=feature_name, value=None, unit=unit, semantic_role=self._semantic_role(feature_name), status=FeatureValueStatus.PARTIAL, evidence=[evidence], diagnostics=tuple(diagnostics))

    def _resolved(self, feature_name: str, value: Any, *, unit: str, table_key: str, row: Mapping[str, Any], column: str, output_case: Any = None, combo_column: str | None = None, extra_diagnostics: Sequence[FeatureDiagnostic] = (), reason: str | None = None) -> FeatureValue:
        table = self._table(table_key)
        role = self._semantic_role(feature_name).upper()
        if role in {"IDENTITY", "OUTPUT_CASE_NAME", "DIRECTION", "ETABS_DIAGNOSTIC_TEXT", "ETABS_DESIGN_COMBO_NAME", "GEOMETRY_ID"}:
            normalized = value
            unit_evidence = {
                "raw_value": value,
                "raw_unit": unit,
                "normalized_value": value,
                "normalized_unit": unit,
                "unit_context_source": self.unit_context.source,
                "unit_normalization_status": "NOT_APPLICABLE",
                "conversion_applied": False,
                "conversion_formula": None,
                "diagnostics": [],
            }
            unit_diags: tuple[FeatureDiagnostic, ...] = tuple()
            safe = True
        else:
            normalized, unit_evidence, unit_diags, safe = self._normalize_value(feature_name, value, unit)
        self._unit_evidence[feature_name] = unit_evidence
        combo_family, combo_diags = classify_combo(output_case, source_column=combo_column, policy=self.load_combo_policy)
        if not safe:
            diagnostics = tuple(extra_diagnostics) + tuple(unit_diags) + tuple(combo_diags)
            return self._partial(feature_name, "Unit normalization is missing or unverified; feature kept partial rather than silently resolved", unit=unit, table_key=table_key, actual_table_name=table.actual_table_name if table else table_key, column=column, row=row, diagnostics=diagnostics)
        evidence_source_row = (
            self._story_base_evidence_source_row(table_key, row, selection_reason=reason)
            if table_key in _STORY_BASE_TABLE_KEYS
            else _row_identity(row)
        )
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.FULL,
            source_table=table_key,
            actual_table_name=table.actual_table_name if table else table_key,
            source_column=column,
            source_row=evidence_source_row,
            output_case=_norm(output_case) if output_case not in (None, "") else None,
            combo_family=combo_family,
            raw_value=value,
            normalized_value=normalized,
            unit=unit,
            resolver=RESOLVER_NAME,
            reason=reason,
        )
        diagnostics = tuple(extra_diagnostics) + tuple(unit_diags) + tuple(combo_diags)
        return FeatureValue(feature_name=feature_name, value=normalized, unit=unit, semantic_role=self._semantic_role(feature_name), status=FeatureValueStatus.RESOLVED, evidence=[evidence], diagnostics=diagnostics)

    def _resolve_from_row(self, feature_name: str, table_key: str, row: Mapping[str, Any] | None, aliases: Sequence[str], *, output_case_aliases: Sequence[str] = (), combo_column_aliases: Sequence[str] = (), diagnostics: Sequence[FeatureDiagnostic] = (), reason: str | None = None) -> FeatureValue:
        table = self._table(table_key)
        unit = self._unit(feature_name)
        if table is None:
            return self._missing(feature_name, "Source table is not available in smoke input", unit=unit, table_key=table_key, diagnostics=diagnostics)
        if row is None:
            raw_diag = _raw_table_diagnostics_from_table(table)
            extra = list(diagnostics)
            for item in table.units.get("resolver_ingestion_diagnostics", ()) if isinstance(table.units, Mapping) else ():
                if not isinstance(item, Mapping):
                    continue
                code = item.get("code")
                if code == "RESOLVER_ONLY_HAS_SAMPLE_ROWS":
                    extra.append(self._diag(FeatureDiagnosticCode.RESOLVER_ONLY_HAS_SAMPLE_ROWS, item.get("message") or "Resolver only has debug sample rows", **dict(item.get("details") or {})))
            if _tabledata_empty_despite_records(raw_diag):
                extra.append(self._diag(FeatureDiagnosticCode.ETABS_TABLEDATA_EMPTY_DESPITE_RECORDS, "ETABS reported records for source table but returned empty TableData", table_key=table_key, actual_table_name=table.actual_table_name, raw_table_diagnostics=raw_diag))
            if table.rows:
                extra.append(self._diag(FeatureDiagnosticCode.RESOLVER_SELECTOR_NO_MATCH_WITH_ROWS_PRESENT, "Resolver table has rows but selector did not find a matching source row", table_key=table_key, actual_table_name=table.actual_table_name, resolver_row_count=len(table.rows), headers=list(table.columns), target_story=self.target.get("story"), available_story_samples=self._available_alias_samples(table.rows, _STORY_ALIASES), available_output_case_samples=self._available_alias_samples(table.rows, _OUTPUT_CASE_ALIASES)))
                reason = "Resolver selector found no matching row despite rows being present"
            elif any(isinstance(item, Mapping) and item.get("code") == "RESOLVER_ONLY_HAS_SAMPLE_ROWS" for item in (table.units.get("resolver_ingestion_diagnostics", ()) if isinstance(table.units, Mapping) else ())) :
                reason = "Resolver only has debug sample rows; full parsed rows are required before resolving this feature"
            else:
                reason = "Source table exists but no matching source row was found"
            return self._partial(feature_name, reason, unit=unit, table_key=table_key, actual_table_name=table.actual_table_name, diagnostics=tuple(extra))
        column, value = _first_present(row, aliases)
        if column is None:
            return self._partial(feature_name, "Source row exists but expected column alias was not present", unit=unit, table_key=table_key, actual_table_name=table.actual_table_name, row=row, diagnostics=diagnostics)
        combo_col, output_case = _first_present(row, combo_column_aliases or output_case_aliases)
        if output_case is None:
            combo_col, output_case = _first_present(row, output_case_aliases)
        return self._resolved(feature_name, value, unit=unit, table_key=table_key, row=row, column=column, output_case=output_case, combo_column=combo_col, extra_diagnostics=diagnostics, reason=reason)

    def _modal_column_aliases(self, column_name: str) -> tuple[str, ...]:
        registry_row = self.table_registry.get("modal_participating_mass", {}) if isinstance(self.table_registry, Mapping) else {}
        required_columns = registry_row.get("required_columns", {}) if isinstance(registry_row, Mapping) else {}
        column_contract = required_columns.get(column_name, {}) if isinstance(required_columns, Mapping) else {}
        aliases = column_contract.get("aliases", ()) if isinstance(column_contract, Mapping) else ()
        return tuple(dict.fromkeys((column_name, *(str(alias) for alias in aliases or ()))))

    def _resolve_modal_cumulative_feature(self, feature_name: str, source_column: str) -> FeatureValue:
        """Resolve one modal cumulative ratio from the complete display table.

        The display table is the production authority.  Resolution is
        fail-closed for truncated/partial population, missing required columns,
        invalid numeric values, and multiple modal cases because no
        authoritative case-selection policy exists yet.
        """
        table_key = "modal_participating_mass"
        table = self._table(table_key)
        unit = self._unit(feature_name)
        if table is None:
            return self._missing(
                feature_name,
                "Modal participating mass source table is not available",
                unit=unit,
                table_key=table_key,
                diagnostics=(self._diag(FeatureDiagnosticCode.TABLE_MISSING, "Modal participating mass table missing", feature_name=feature_name),),
            )

        raw_table_diagnostics = _raw_table_diagnostics_from_table(table)
        resolver_row_count = len(table.rows)
        reported_row_count = _int_or_none(raw_table_diagnostics.get("number_records"))
        parser_status = str(raw_table_diagnostics.get("parser_status") or "UNKNOWN").strip().upper()
        ingestion_diagnostics = tuple(
            item for item in (table.units.get("resolver_ingestion_diagnostics", ()) if isinstance(table.units, Mapping) else ())
            if isinstance(item, Mapping)
        )
        source_row_storage = str(table.units.get("source_row_storage_field_used") or "") if isinstance(table.units, Mapping) else ""
        sample_only = source_row_storage in {"sample_rows", "sample_rows_limited"} or any(
            str(item.get("code") or "") == "RESOLVER_ONLY_HAS_SAMPLE_ROWS" for item in ingestion_diagnostics
        )
        incomplete_parser_statuses = {
            "EMPTY",
            "FAILED",
            "PARTIAL",
            "ROW_PARSE_PARTIAL",
            "HEADER_ONLY",
            "TABLEDATA_EMPTY_DESPITE_RECORDS",
            "COM_CALL_FAILED",
            "RESOLVER_ONLY_HAS_SAMPLE_ROWS",
            "FIXTURE_SAMPLE_ROWS",
        }

        if sample_only or parser_status in incomplete_parser_statuses:
            return self._partial(
                feature_name,
                "Modal source is incomplete or sample-only; complete display-table rows are required",
                unit=unit,
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                diagnostics=(self._diag(
                    FeatureDiagnosticCode.MODAL_SOURCE_INCOMPLETE,
                    "Modal participating mass source was not a complete parsed table",
                    feature_name=feature_name,
                    parser_status=parser_status,
                    source_row_storage_field_used=source_row_storage or None,
                    resolver_row_count=resolver_row_count,
                    reported_row_count=reported_row_count,
                ),),
            )

        if reported_row_count is not None and reported_row_count != resolver_row_count:
            return self._partial(
                feature_name,
                "Modal reported row count does not equal the complete resolver row population",
                unit=unit,
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                diagnostics=(self._diag(
                    FeatureDiagnosticCode.MODAL_ROW_COUNT_MISMATCH,
                    "Modal participating mass row cardinality mismatch",
                    feature_name=feature_name,
                    reported_row_count=reported_row_count,
                    resolver_row_count=resolver_row_count,
                    parser_status=parser_status,
                ),),
            )

        if not table.rows:
            return self._partial(
                feature_name,
                "Modal participating mass table exists but contains no rows",
                unit=unit,
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                diagnostics=(self._diag(FeatureDiagnosticCode.MODAL_TABLE_EMPTY, "Modal participating mass table has no usable rows", feature_name=feature_name),),
            )

        required_fields = ("Mode", "Period", "UX", "UY", "SumUX", "SumUY")
        aliases_by_field = {name: self._modal_column_aliases(name) for name in required_fields}
        available_columns = {_norm_key(column) for column in table.columns}
        missing_columns = [
            name for name, aliases in aliases_by_field.items()
            if not any(_norm_key(alias) in available_columns for alias in aliases)
        ]
        if missing_columns:
            code = FeatureDiagnosticCode.MODAL_SUM_COLUMN_MISSING if source_column in missing_columns else FeatureDiagnosticCode.MODAL_REQUIRED_COLUMN_MISSING
            return self._partial(
                feature_name,
                "Modal participating mass table is missing required source columns",
                unit=unit,
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                column=source_column,
                diagnostics=(self._diag(
                    code,
                    "Modal participating mass required column set is incomplete",
                    feature_name=feature_name,
                    missing_columns=missing_columns,
                    required_columns=list(required_fields),
                    available_columns=list(table.columns),
                ),),
            )

        case_aliases = ("Case", "OutputCase", "Output Case")
        case_column_present = any(_norm_key(alias) in available_columns for alias in case_aliases)
        parsed_rows: list[dict[str, Any]] = []
        invalid_rows: list[dict[str, Any]] = []
        missing_case_rows: list[int] = []
        case_values: dict[str, str] = {}

        for row_index, row in enumerate(table.rows):
            parsed: dict[str, Any] = {"row": row, "row_index": row_index}
            invalid_fields: list[str] = []
            for field_name, aliases in aliases_by_field.items():
                source_name, raw_value = _first_present(row, aliases)
                numeric_value = _to_finite_float(raw_value)
                if source_name is None or numeric_value is None:
                    invalid_fields.append(field_name)
                    continue
                parsed[field_name] = numeric_value
                parsed[f"{field_name}_raw"] = raw_value
                parsed[f"{field_name}_source_column"] = source_name

            case_column, case_value = _first_present(row, case_aliases)
            case_text = _norm(case_value)
            parsed["case"] = case_text or None
            parsed["case_source_column"] = case_column
            if case_column_present and not case_text:
                missing_case_rows.append(row_index)
            elif case_text:
                case_values.setdefault(case_text.casefold(), case_text)

            if invalid_fields:
                invalid_rows.append({"row_index": row_index, "invalid_fields": invalid_fields})
            else:
                parsed_rows.append(parsed)

        if invalid_rows:
            return self._partial(
                feature_name,
                "Modal required values contain missing, non-numeric, or non-finite data",
                unit=unit,
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                column=source_column,
                diagnostics=(self._diag(
                    FeatureDiagnosticCode.MODAL_CUMULATIVE_VALUE_INVALID,
                    "Every modal row must contain finite numeric required values",
                    feature_name=feature_name,
                    invalid_row_count=len(invalid_rows),
                    invalid_rows=invalid_rows[:20],
                    resolver_row_count=resolver_row_count,
                ),),
            )

        if missing_case_rows:
            return self._partial(
                feature_name,
                "Modal case values are incomplete within the authoritative row population",
                unit=unit,
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                diagnostics=(self._diag(
                    FeatureDiagnosticCode.MODAL_CASE_VALUE_INCOMPLETE,
                    "Case column is present but one or more modal rows have no case value",
                    feature_name=feature_name,
                    missing_case_row_indices=missing_case_rows[:20],
                    missing_case_row_count=len(missing_case_rows),
                ),),
            )

        if len(case_values) > 1:
            return self._partial(
                feature_name,
                "Multiple modal cases are present and no authoritative case-selection policy is locked",
                unit=unit,
                table_key=table_key,
                actual_table_name=table.actual_table_name,
                diagnostics=(self._diag(
                    FeatureDiagnosticCode.MODAL_MULTIPLE_CASES_UNSUPPORTED,
                    "Modal rows from unrelated cases must not be silently aggregated",
                    feature_name=feature_name,
                    modal_cases=sorted(case_values.values(), key=str.casefold),
                    modal_case_count=len(case_values),
                ),),
            )

        selected = parsed_rows[0]
        for candidate in parsed_rows[1:]:
            if candidate[source_column] > selected[source_column]:
                selected = candidate

        selected_mode_value = selected["Mode"]
        selected_mode: int | float = int(selected_mode_value) if selected_mode_value.is_integer() else selected_mode_value
        selected_period = selected["Period"]
        selected_case = next(iter(case_values.values()), None)
        selected_column = str(selected[f"{source_column}_source_column"])
        selected_value = float(selected[source_column])
        selected_raw_value = selected[f"{source_column}_raw"]

        diagnostics = [
            self._diag(
                FeatureDiagnosticCode.MODAL_AGGREGATION_MAX_CUMULATIVE_USED,
                "Modal cumulative participation resolved using max_cumulative over the complete authoritative row population",
                feature_name=feature_name,
                source_column=selected_column,
                selected_mode=selected_mode,
                selected_period=selected_period,
                selected_case=selected_case,
                selected_row_index=selected["row_index"],
                selected_value=selected_value,
                source_rows_considered_count=resolver_row_count,
                reported_row_count=reported_row_count,
                resolver_row_count=resolver_row_count,
            )
        ]

        aggregation_source_row = {
            **_row_identity(selected["row"]),
            "aggregation": "max_cumulative",
            "aggregation_method": "max_cumulative",
            "case": selected_case,
            "governing_mode": selected_mode,
            "governing_period": selected_period,
            "governing_row_index": selected["row_index"],
            "governing_row_reference": (
                f"{table_key}|case={selected_case or '<unspecified>'}|"
                f"mode={selected_mode}|period={selected_period}|row_index={selected['row_index']}"
            ),
            "governing_source_row_items": tuple(
                (str(key), _json_safe(value)) for key, value in selected["row"].items()
            ),
            "full_row_population_count": resolver_row_count,
            "reported_row_count": reported_row_count,
            "resolver_row_count": resolver_row_count,
            "source_rows_considered_count": resolver_row_count,
            "mode_count": resolver_row_count,
            "selected_mode_for_ux" if source_column == "SumUX" else "selected_mode_for_uy": selected_mode,
            "selected_row_index_for_ux" if source_column == "SumUX" else "selected_row_index_for_uy": selected["row_index"],
            "selected_sum_ux" if source_column == "SumUX" else "selected_sum_uy": selected_value,
        }
        output_col = selected.get("case_source_column")
        combo_family, combo_diags = classify_combo(selected_case, source_column=output_col, policy=self.load_combo_policy)
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.FULL,
            source_table=table_key,
            actual_table_name=table.actual_table_name,
            source_column=selected_column,
            source_row=aggregation_source_row,
            output_case=selected_case,
            combo_family=combo_family or "MODAL",
            raw_value=selected_raw_value,
            normalized_value=selected_value,
            unit=unit,
            resolver=RESOLVER_NAME,
            reason="resolved by max_cumulative aggregation over the complete modal participating mass row population",
        )
        self._unit_evidence[feature_name] = {
            "raw_value": selected_raw_value,
            "raw_unit": unit,
            "normalized_value": selected_value,
            "normalized_unit": unit,
            "unit_context_source": self.unit_context.source,
            "unit_normalization_status": "NOT_APPLICABLE",
            "conversion_applied": False,
            "conversion_formula": None,
            "diagnostics": [],
            "aggregation_method": "max_cumulative",
            "reported_row_count": reported_row_count,
            "resolver_row_count": resolver_row_count,
        }
        return FeatureValue(
            feature_name=feature_name,
            value=selected_value,
            unit=unit,
            semantic_role=self._semantic_role(feature_name),
            status=FeatureValueStatus.RESOLVED,
            evidence=[evidence],
            diagnostics=tuple(diagnostics) + tuple(combo_diags),
        )

    def _select_design_row(self, seed: Mapping[str, Any] | None = None) -> tuple[Mapping[str, Any] | None, list[dict[str, Any]]]:
        table = self._table("concrete_beam_design_summary")
        attempts: list[dict[str, Any]] = []
        if not table:
            attempts.append({"attempted_keys": dict(seed or {}), "matched": False, "reason": "TABLE_UNAVAILABLE"})
            return None, attempts
        canonical = _canonical_identity_from_seed(seed)
        component = canonical.get("component") or self.target.get("component")
        label = canonical.get("label") or self.target.get("label")
        story = canonical.get("story") or self.target.get("story")
        section = canonical.get("section") or self.target.get("section")
        has_target = any(value not in (None, "") for value in (component, label, story, section))

        ordered = [
            ("unique_label_story_designsect", {"UniqueName": component, "Label": label, "Story": story, "DesignSect": section}),
            ("unique", {"UniqueName": component}),
            ("label_story", {"Label": label, "Story": story}),
            ("label", {"Label": label}),
            ("designsect", {"DesignSect": section}),
            ("analysissect", {"AnalysisSect": section}),
        ]

        def matches(row: Mapping[str, Any], mode: str) -> bool:
            _, row_unique = _first_present(row, ("UniqueName", "Frame", "Beam"))
            _, row_label = _first_present(row, ("Label", "Frame", "Beam"))
            _, row_story = _first_present(row, _STORY_ALIASES)
            _, row_design = _first_present(row, ("DesignSect", "Section"))
            _, row_analysis = _first_present(row, ("AnalysisSect",))
            if mode == "unique_label_story_designsect":
                return all(v not in (None, "") for v in (component, label, story, section)) and _norm(row_unique) == _norm(component) and _norm(row_label) == _norm(label) and _story_values_match(row_story, story) and _norm(row_design) == _norm(section)
            if mode == "unique":
                return component not in (None, "") and _norm(row_unique) == _norm(component)
            if mode == "label_story":
                return label not in (None, "") and story not in (None, "") and _norm(row_label) == _norm(label) and _story_values_match(row_story, story)
            if mode == "label":
                return label not in (None, "") and _norm(row_label) == _norm(label)
            if mode == "designsect":
                return section not in (None, "") and _norm(row_design) == _norm(section)
            if mode == "analysissect":
                return section not in (None, "") and _norm(row_analysis) == _norm(section)
            return False

        if has_target:
            for mode, keys in ordered:
                for row in table.rows:
                    if matches(row, mode):
                        attempts.append({"attempted_keys": keys, "matched": True, "reason": f"matched_by_{mode}"})
                        return row, attempts
                attempts.append({"attempted_keys": keys, "matched": False, "reason": f"no_match_by_{mode}"})
            return None, attempts

        # Legacy fixture path: no explicit live target was provided, so the first
        # observed concrete design summary row is still the deterministic seed.
        if table.rows:
            attempts.append({"attempted_keys": {}, "matched": True, "reason": "first_design_summary_row_no_target"})
            return table.rows[0], attempts
        attempts.append({"attempted_keys": {}, "matched": False, "reason": "design_summary_table_empty"})
        return None, attempts

    def _frame_assignment_match(self, seed: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, list[dict[str, Any]], list[FeatureDiagnostic], bool]:
        table = self._table("frame_assignments")
        attempts: list[dict[str, Any]] = []
        diagnostics: list[FeatureDiagnostic] = []
        if not table:
            attempts.append({"attempted_keys": {}, "matched": False, "reason": "frame_assignments table missing"})
            return None, attempts, diagnostics, False
        canonical = _canonical_identity_from_seed(seed)
        component = canonical.get("component")
        label = canonical.get("label")
        story = canonical.get("story")
        section = canonical.get("section")

        def check_row(row: Mapping[str, Any], mode: str) -> bool:
            _, row_unique = _first_present(row, ("UniqueName", "Frame", "Beam"))
            _, row_label = _first_present(row, ("Label", "Frame", "Beam"))
            _, row_story = _first_present(row, _STORY_ALIASES)
            _, row_design = _first_present(row, ("DesignSect", "Section"))
            _, row_analysis = _first_present(row, ("AnalysisSect",))
            if mode == "unique_label_story_designsect":
                return all(v not in (None, "") for v in (component, label, story, section)) and _norm(row_unique) == _norm(component) and _norm(row_label) == _norm(label) and _story_values_match(row_story, story) and _norm(row_design) == _norm(section)
            if mode == "unique":
                return component not in (None, "") and _norm(row_unique) == _norm(component)
            if mode == "label_story":
                return label not in (None, "") and story not in (None, "") and _norm(row_label) == _norm(label) and _story_values_match(row_story, story)
            if mode == "label":
                return label not in (None, "") and _norm(row_label) == _norm(label)
            if mode == "designsect":
                return section not in (None, "") and _norm(row_design) == _norm(section)
            if mode == "analysissect":
                return section not in (None, "") and _norm(row_analysis) == _norm(section)
            return False

        ordered = [
            ("unique_label_story_designsect", {"UniqueName": component, "Label": label, "Story": story, "DesignSect": section}),
            ("unique", {"UniqueName": component}),
            ("label_story", {"Label": label, "Story": story}),
            ("label", {"Label": label}),
            ("designsect", {"DesignSect": section}),
            ("analysissect", {"AnalysisSect": section}),
        ]
        for mode, keys in ordered:
            for row in table.rows:
                if check_row(row, mode):
                    attempts.append({"attempted_keys": keys, "matched": True, "reason": f"matched_by_{mode}"})
                    if mode == "analysissect":
                        diagnostics.append(self._diag(FeatureDiagnosticCode.ANALYSIS_SECTION_FALLBACK, "AnalysisSect used because DesignSect was unavailable or unmatched", attempted_keys=keys))
                        return row, attempts, diagnostics, True
                    return row, attempts, diagnostics, False
            attempts.append({"attempted_keys": keys, "matched": False, "reason": f"no_match_by_{mode}"})
        diagnostics.append(self._diag(FeatureDiagnosticCode.ROW_MISSING, "No frame assignment row matched seeded beam identity", attempted_match_keys=attempts))
        return None, attempts, diagnostics, False

    def _section_match(self, section_name: Any) -> tuple[Mapping[str, Any] | None, list[dict[str, Any]]]:
        table = self._table("frame_section_properties")
        attempts: list[dict[str, Any]] = []
        if not table:
            return None, [{"attempted_keys": {"section": section_name}, "matched": False, "reason": "frame_section_properties table missing"}]
        for alias in ("Name", "SectionName", "Section", "DesignSect", "AnalysisSect"):
            for row in table.rows:
                _, value = _first_present(row, (alias,))
                if _norm(value) == _norm(section_name):
                    attempts.append({"attempted_keys": {alias: section_name}, "matched": True, "reason": f"matched_section_by_{alias}"})
                    return row, attempts
            attempts.append({"attempted_keys": {alias: section_name}, "matched": False, "reason": f"no_match_by_{alias}"})
        return None, attempts

    def _section_name_parse_suggestion(self, section_name: Any) -> dict[str, Any] | None:
        text = _norm(section_name)
        match = re.fullmatch(r"[A-Za-z]*\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)", text)
        if not match:
            return None
        width = float(match.group(1).replace(",", ".")) * 10 if float(match.group(1).replace(",", ".")) < 100 else float(match.group(1).replace(",", "."))
        depth = float(match.group(2).replace(",", ".")) * 10 if float(match.group(2).replace(",", ".")) < 100 else float(match.group(2).replace(",", "."))
        return {"section_name": text, "suggested_width_mm": width, "suggested_depth_mm": depth, "used_as_feature_value": False}


    def _direct_api_frame_data(self) -> Mapping[str, Any]:
        return self.direct_api_geometry.get("frame", {}) if isinstance(self.direct_api_geometry, Mapping) else {}

    def _direct_api_section_data(self) -> Mapping[str, Any]:
        return self.direct_api_geometry.get("section", {}) if isinstance(self.direct_api_geometry, Mapping) else {}

    def _direct_api_points_data(self) -> Mapping[str, Any]:
        return self.direct_api_geometry.get("points", {}) if isinstance(self.direct_api_geometry, Mapping) else {}

    def _direct_api_identity_match(self, seed: Mapping[str, Any]) -> Mapping[str, Any] | None:
        frame = self._direct_api_frame_data()
        if not frame:
            return None
        component = _norm(seed.get("component") or self.target.get("component"))
        label = _norm(seed.get("label") or self.target.get("label"))
        story = _norm(seed.get("story") or self.target.get("story"))
        section = _norm(seed.get("section") or self.target.get("section"))
        object_name = _norm(frame.get("object_name") or frame.get("name") or frame.get("UniqueName"))
        frame_label = _norm(frame.get("label") or frame.get("Label"))
        frame_story = _norm(frame.get("story") or frame.get("Story"))
        frame_section = _norm(frame.get("section") or frame.get("section_name") or frame.get("DesignSect"))
        component_ok = not component or component == object_name
        label_ok = not label or label == frame_label
        story_ok = not story or story == frame_story
        section_ok = not section or section == frame_section
        if component_ok and label_ok and story_ok and section_ok:
            return {
                "component": object_name or component,
                "label": frame_label or label,
                "story": frame_story or story,
                "section": frame_section or section,
                "points": list(frame.get("points") or ()),
            }
        return None

    def _direct_geometry_value(self, feature_name: str, raw_value: Any, *, column: str, source_object: Any, api_call: str, api_call_chain: Sequence[str], extra_source_row: Mapping[str, Any] | None = None) -> FeatureValue:
        target_unit = self._unit(feature_name)
        normalized, unit_evidence, unit_diags, safe = self._normalize_value(feature_name, raw_value, target_unit)
        unit_evidence.update({
            "unit_context_source": self.unit_context.source,
            "api_call": api_call,
            "source_kind": "live_etabs_direct_api",
        })
        self._unit_evidence[feature_name] = unit_evidence
        if not safe:
            return self._partial(
                feature_name,
                "Direct API geometry value found but unit context is missing/unverified",
                unit=target_unit,
                table_key="direct_etabs_api",
                actual_table_name="direct_etabs_api",
                column=column,
                row=dict(extra_source_row or {"source_object": source_object, "api_call": api_call}),
                diagnostics=unit_diags,
            )
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.FULL,
            source_table="direct_etabs_api",
            actual_table_name="direct_etabs_api",
            source_column=column,
            source_row={
                "source_kind": "live_etabs_direct_api",
                "api_call": api_call,
                "api_call_chain": list(api_call_chain),
                "source_object": source_object,
                **dict(extra_source_row or {}),
            },
            raw_value=raw_value,
            normalized_value=normalized,
            unit=target_unit,
            resolver=RESOLVER_NAME,
            reason="resolved from verified direct ETABS model API fallback",
        )
        diag = self._diag(FeatureDiagnosticCode.DIRECT_API_FALLBACK_USED, "Geometry resolved from read-only direct ETABS API/provider fallback", feature_name=feature_name, api_call=api_call, source_object=source_object)
        return FeatureValue(feature_name=feature_name, value=normalized, unit=target_unit, semantic_role=self._semantic_role(feature_name), status=FeatureValueStatus.RESOLVED, evidence=[evidence], diagnostics=(diag,) + tuple(unit_diags))

    def _resolve_direct_api_geometry_features(self, section_name: Any) -> tuple[dict[str, FeatureValue], dict[str, Any]]:
        report: dict[str, Any] = {
            "used": False,
            "attempted_frame_identity_resolution": bool(self.direct_api_geometry),
            "resolved_frame_object_name": None,
            "resolved_label": None,
            "resolved_story": None,
            "resolved_section_name": section_name,
            "section_api_call": None,
            "section_api_return_code": None,
            "section_raw_dimensions": None,
            "section_normalized_dimensions": None,
            "frame_points_api_call": None,
            "frame_points_return_code": None,
            "point_coordinates": None,
            "raw_length": None,
            "normalized_length_mm": None,
            "diagnostics": [],
        }
        features: dict[str, FeatureValue] = {}
        section = self._direct_api_section_data()
        points = self._direct_api_points_data()
        frame = self._direct_api_frame_data()
        if frame:
            report.update({
                "resolved_frame_object_name": frame.get("object_name") or frame.get("name") or frame.get("UniqueName"),
                "resolved_label": frame.get("label") or frame.get("Label"),
                "resolved_story": frame.get("story") or frame.get("Story"),
                "resolved_section_name": frame.get("section") or frame.get("section_name") or section_name,
            })
        section_name = report["resolved_section_name"] or section_name
        section_api_call = section.get("api_call") or "PropFrame.GetRectangle"
        report["section_api_call"] = section_api_call
        report["section_api_return_code"] = section.get("return_code")
        section_matches = (not section_name) or _norm(section.get("section") or section.get("section_name") or section.get("Name")) in {_norm(section_name), ""}
        if section and section_matches and section.get("return_code", 0) in (0, None):
            raw_t2 = section.get("t2") if "t2" in section else section.get("width")
            raw_t3 = section.get("t3") if "t3" in section else section.get("depth")
            report["section_raw_dimensions"] = {"t2": raw_t2, "t3": raw_t3}
            if raw_t2 is not None:
                features["beam_width_mm"] = self._direct_geometry_value("beam_width_mm", raw_t2, column=f"{section_api_call}.t2", source_object=section_name, api_call=section_api_call, api_call_chain=[section_api_call], extra_source_row={"raw_section_response": dict(section)})
            if raw_t3 is not None:
                features["beam_depth_mm"] = self._direct_geometry_value("beam_depth_mm", raw_t3, column=f"{section_api_call}.t3", source_object=section_name, api_call=section_api_call, api_call_chain=[section_api_call], extra_source_row={"raw_section_response": dict(section)})
            if "beam_width_mm" in features and "beam_depth_mm" in features:
                report["used"] = True
                report["section_normalized_dimensions"] = {"width_mm": features["beam_width_mm"].value, "depth_mm": features["beam_depth_mm"].value}
        else:
            report["diagnostics"].append({"severity": "WARNING", "code": "DIRECT_SECTION_GEOMETRY_UNAVAILABLE", "message": "Direct section geometry API data unavailable or did not match target section"})

        frame_points_call = "FrameObj.GetPoints + PointObj.GetCoordCartesian"
        report["frame_points_api_call"] = frame_points_call
        report["frame_points_return_code"] = points.get("return_code")
        point_map = points.get("coordinates") if isinstance(points.get("coordinates"), Mapping) else points
        point_names = list(frame.get("points") or points.get("point_names") or ()) if frame or isinstance(points, Mapping) else []
        if len(point_names) >= 2 and isinstance(point_map, Mapping):
            pi, pj = point_names[0], point_names[1]
            c1 = point_map.get(pi)
            c2 = point_map.get(pj)
            if isinstance(c1, Mapping) and isinstance(c2, Mapping) and points.get("return_code", 0) in (0, None):
                try:
                    dx = float(c2.get("x", 0)) - float(c1.get("x", 0))
                    dy = float(c2.get("y", 0)) - float(c1.get("y", 0))
                    dz = float(c2.get("z", 0)) - float(c1.get("z", 0))
                    raw_length = (dx * dx + dy * dy + dz * dz) ** 0.5
                    report["point_coordinates"] = {pi: dict(c1), pj: dict(c2)}
                    report["raw_length"] = raw_length
                    features["beam_length_mm"] = self._direct_geometry_value("beam_length_mm", raw_length, column="computed_length_from_frame_points", source_object=report.get("resolved_frame_object_name"), api_call=frame_points_call, api_call_chain=["FrameObj.GetPoints", f"PointObj.GetCoordCartesian({pi})", f"PointObj.GetCoordCartesian({pj})"], extra_source_row={"source_points": [pi, pj], "raw_coordinates": {pi: dict(c1), pj: dict(c2)}})
                    report["normalized_length_mm"] = features["beam_length_mm"].value
                    report["used"] = True
                except Exception as exc:
                    report["diagnostics"].append({"severity": "WARNING", "code": "DIRECT_FRAME_LENGTH_UNAVAILABLE", "message": f"Could not compute length from direct point coordinates: {exc}"})
        else:
            report["diagnostics"].append({"severity": "WARNING", "code": "DIRECT_FRAME_LENGTH_UNAVAILABLE", "message": "Direct frame endpoint API data unavailable"})
        return features, report

    def _table_debug(self, table_key: str, required_columns: Sequence[str], attempts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        table = self._table(table_key)
        headers = list(table.columns) if table else []
        found = []
        missing = []
        folded = {_norm_key(c): c for c in headers}
        for col in required_columns:
            actual = folded.get(_norm_key(col))
            if actual:
                found.append(actual)
            else:
                missing.append(col)
        raw_diag = _raw_table_diagnostics_from_table(table)
        return {
            "table_key": table_key,
            "actual_table_name": table.actual_table_name if table else None,
            "headers": headers,
            "row_count": len(table.rows) if table else 0,
            "sample_rows": [dict(row) for row in (table.rows[:3] if table else [])],
            "has_required_columns": not missing,
            "required_columns_found": found,
            "required_columns_missing": missing,
            "matching_attempts": [dict(item) for item in attempts],
            "raw_table_diagnostics": raw_diag,
            "row_count_investigation": {
                "headers_present": bool(headers),
                "rows_present": bool(table and table.rows),
                "parser_status": raw_diag.get("parser_status"),
                "number_records": raw_diag.get("number_records"),
                "table_data_length": raw_diag.get("table_data_length"),
                "expected_flat_length": raw_diag.get("expected_flat_length"),
            },
        }

    def _concrete_beam_design_summary_availability_report(self, design_attempts: Sequence[Mapping[str, Any]], *, row_matching_uses_seeded_identity: bool) -> dict[str, Any]:
        table_key = "concrete_beam_design_summary"
        table = self._table(table_key)
        live_debug = dict(self.table_extraction_debug.get("concrete_beam_design_summary_availability") or {})
        registry_info = self.table_registry.get(table_key, {}) if isinstance(self.table_registry, Mapping) else {}
        provider_sources = registry_info.get("provider_sources") if isinstance(registry_info, Mapping) else {}
        catalog_aliases = list((provider_sources or {}).get("etabs") or ()) if isinstance(provider_sources, Mapping) else []
        aliases_attempted = list(dict.fromkeys(list(live_debug.get("aliases_attempted") or ()) + catalog_aliases + ([table.actual_table_name] if table and table.actual_table_name else [])))
        raw = _raw_table_diagnostics_from_table(table)
        available = table is not None and bool(table.rows)
        row_matching_attempted = bool(table and table.rows)
        matched = any(bool(item.get("matched")) for item in design_attempts)
        diagnostic_code = None if available else "TABLE_UNAVAILABLE"
        if table is not None and not table.rows:
            diagnostic_code = "TABLE_EMPTY"
        return {
            "concrete_beam_design_summary_fetch_attempted": bool(live_debug.get("fetch_attempted", True)),
            "concrete_beam_design_summary_aliases_attempted": aliases_attempted,
            "concrete_beam_design_summary_available": available,
            "concrete_beam_design_summary_row_matching_attempted": row_matching_attempted,
            "concrete_beam_design_summary_row_matching_uses_seeded_identity": bool(row_matching_uses_seeded_identity),
            "concrete_beam_design_summary_row_matched": matched,
            "concrete_beam_design_summary_matching_attempts": [dict(item) for item in design_attempts],
            "diagnostic": diagnostic_code,
            "display_selection_attempted": bool(raw.get("display_selection_attempted", live_debug.get("display_selection_attempted", False))),
            "display_selection_success": bool(raw.get("display_selection_success", live_debug.get("display_selection_success", False))),
            "display_selection_selected_method": raw.get("display_selection_selected_method", live_debug.get("display_selection_selected_method")),
            "display_selection_attempts": list(raw.get("display_selection_attempts") or live_debug.get("display_selection_attempts") or ()),
            "preferred_output_case": raw.get("preferred_output_case", live_debug.get("preferred_output_case", self.preferred_output_case)),
            "actual_table_name": table.actual_table_name if table else live_debug.get("actual_table_name"),
            "parser_status": raw.get("parser_status"),
            "row_count": len(table.rows) if table else 0,
            "raw_table_diagnostics": raw,
        }

    def _table_unavailable_diag(self, table_key: str, report: Mapping[str, Any]) -> FeatureDiagnostic:
        return self._diag(
            FeatureDiagnosticCode.TABLE_UNAVAILABLE,
            f"{table_key} table is unavailable in smoke input",
            table_key=table_key,
            aliases_attempted=list(report.get("concrete_beam_design_summary_aliases_attempted") or ()),
            fetch_attempted=bool(report.get("concrete_beam_design_summary_fetch_attempted")),
            display_selection_attempted=bool(report.get("display_selection_attempted")),
        )

    def _direct_identity_value(self, feature_name: str, value: Any, *, column: str, identity: Mapping[str, Any]) -> FeatureValue:
        evidence = FeatureEvidence(
            evidence_status=FeatureEvidenceStatus.FULL,
            source_table="live_etabs_direct_api",
            actual_table_name="live_etabs_direct_api",
            source_column=column,
            source_row={"source_kind": "live_etabs_direct_api", **dict(identity)},
            raw_value=value,
            normalized_value=value,
            unit=self._unit(feature_name),
            resolver=RESOLVER_NAME,
            reason="resolved from observed read-only direct ETABS API identity evidence",
        )
        diag = self._diag(FeatureDiagnosticCode.DIRECT_API_FALLBACK_USED, "Identity feature resolved from read-only direct ETABS API/provider fallback", feature_name=feature_name, source_kind="live_etabs_direct_api")
        return FeatureValue(feature_name=feature_name, value=value, unit=self._unit(feature_name), semantic_role=self._semantic_role(feature_name), status=FeatureValueStatus.RESOLVED, evidence=[evidence], diagnostics=(diag,))

    def _identity_feature_from_observed_source(
        self,
        feature_name: str,
        source_table: str | None,
        source_row: Mapping[str, Any] | None,
        aliases: Sequence[str],
        *,
        direct_identity: Mapping[str, Any] | None = None,
        direct_key: str | None = None,
        diagnostics: Sequence[FeatureDiagnostic] = (),
        reason: str | None = None,
    ) -> FeatureValue:
        if source_table and source_row:
            return self._resolve_from_row(feature_name, source_table, source_row, aliases, diagnostics=diagnostics, reason=reason)
        if direct_identity and direct_key and direct_identity.get(direct_key) not in (None, ""):
            return self._direct_identity_value(feature_name, direct_identity.get(direct_key), column=direct_key, identity=direct_identity)
        return self._missing(feature_name, "Observed identity source is not available", unit=self._unit(feature_name), table_key=source_table or "observed_identity", diagnostics=diagnostics)

    def build_beam_snapshot(self, component_id: str | None = None) -> FeatureSnapshot:
        target_seed = build_seed_identity_from_target(
            self.target.get("component") or component_id,
            self.target.get("label"),
            self.target.get("story"),
            self.target.get("section"),
        )
        design_row, design_attempts = self._select_design_row(target_seed)
        seed_identity = dict(target_seed)
        identity_source = "target_args" if seed_identity else "unknown"
        identity_diags: list[FeatureDiagnostic] = []
        if seed_identity:
            identity_diags.append(self._diag(FeatureDiagnosticCode.TARGET_IDENTITY_SEEDED_FROM_ARGS, "Beam target identity seeded from live target CLI args before frame assignment and concrete design matching", identity_source="target_args", identity_seeded=True))
        elif design_row:
            seed_identity = _seed_identity_from_row(design_row)
            identity_source = "concrete_beam_design_summary"
            identity_diags.append(self._diag(FeatureDiagnosticCode.IDENTITY_SEEDED_FROM_DESIGN_SUMMARY, "Beam target identity seeded from concrete_beam_design_summary before frame assignment matching", identity_source="concrete_beam_design_summary", identity_seeded=True))
        elif component_id:
            seed_identity = {"UniqueName": str(component_id)}
            identity_source = "component_id_arg"

        design_summary_report = self._concrete_beam_design_summary_availability_report(design_attempts, row_matching_uses_seeded_identity=bool(seed_identity))
        assignment, frame_attempts, frame_diags, analysis_fallback = self._frame_assignment_match(seed_identity)
        identity_diags.extend(frame_diags)
        identity_confirmed = assignment is not None
        if not identity_confirmed and identity_source == "concrete_beam_design_summary":
            identity_diags.append(self._diag(FeatureDiagnosticCode.IDENTITY_SEEDED_NOT_FRAME_CONFIRMED, "Design summary identity was not confirmed by Frame Assignments - Summary", identity_source="concrete_beam_design_summary", identity_seeded=True, identity_confirmed_by_frame_assignments=False))
        if design_summary_report.get("concrete_beam_design_summary_row_matching_uses_seeded_identity"):
            identity_diags.append(self._diag(FeatureDiagnosticCode.DESIGN_SUMMARY_ROW_MATCHING_USES_SEEDED_IDENTITY, "Concrete beam design summary row matching used seeded target identity", attempted_match_keys=[dict(item) for item in design_attempts]))

        frame_identity = _row_identity(assignment)
        if assignment is not None:
            design_col, _design_value = _first_present(assignment, ("DesignSect", "Section"))
            analysis_col, _analysis_value = _first_present(assignment, ("AnalysisSect",))
            if design_col is None and analysis_col is not None:
                analysis_fallback = True
                identity_diags.append(self._diag(FeatureDiagnosticCode.ANALYSIS_SECTION_FALLBACK, "AnalysisSect used because DesignSect was unavailable or unmatched", section_column=analysis_col))
        identity = _canonical_identity_from_seed(seed_identity)
        for key, value in frame_identity.items():
            if value not in (None, ""):
                identity[key] = value
        direct_identity = self._direct_api_identity_match(identity)
        if direct_identity and assignment is None:
            for key, value in direct_identity.items():
                if key != "points" and value not in (None, ""):
                    identity[key] = value
            identity_diags.append(self._diag(FeatureDiagnosticCode.DIRECT_API_FALLBACK_USED, "Beam identity confirmed from read-only direct ETABS API/provider fallback", source_kind="live_etabs_direct_api"))
        component = _norm(identity.get("component") or component_id or "UNKNOWN_COMPONENT")
        label = identity.get("label")
        story = identity.get("story")
        section_name = identity.get("section")
        section_row, section_attempts = self._section_match(section_name)
        section_suggestion = None if section_row else self._section_name_parse_suggestion(section_name)
        if section_suggestion:
            identity_diags.append(self._diag(FeatureDiagnosticCode.SECTION_NAME_PARSE_SUGGESTION, "Section name parse is a diagnostic suggestion only and is not used as feature geometry", **section_suggestion))
        self._geometry_debug = {
            "frame_assignments": self._table_debug("frame_assignments", ("UniqueName", "Label", "Story", "DesignSect", "AnalysisSect", "Length"), frame_attempts),
            "frame_section_properties": self._table_debug("frame_section_properties", ("Name", "t2", "t3"), section_attempts),
            "concrete_beam_design_summary": self._table_debug("concrete_beam_design_summary", ("UniqueName", "Label", "Story", "DesignSect", "AnalysisSect", "AsTop", "AsBot", "VRebar"), design_attempts) | dict(design_summary_report),
        }
        confidence = "high" if identity_confirmed else ("medium" if direct_identity or design_row else "low")
        resolved_identity_source = "frame_assignments" if assignment else ("direct_api_plus_frame_assignments" if direct_identity else identity_source)
        self._identity_report = {
            "target_selection_policy": {
                "target_component": self.target.get("component") or component_id,
                "target_label": self.target.get("label"),
                "target_story": self.target.get("story"),
                "target_section": self.target.get("section"),
                "auto_seed_from_design_summary": not any(self.target.values()) and component_id is None,
            },
            "identity_source": resolved_identity_source,
            "identity_seeded": bool(seed_identity),
            "identity_confirmed_by_frame_assignments": identity_confirmed,
            "identity_confidence": confidence,
            "seed_identity": seed_identity,
            "resolved_identity": identity,
            "frame_assignment_matching_attempts": frame_attempts,
            "concrete_beam_design_summary": design_summary_report,
            **{k: v for k, v in design_summary_report.items() if k.startswith("concrete_beam_design_summary_")},
            "diagnostics": [diag.as_dict() for diag in identity_diags],
        }
        seed_reason = "identity seeded from concrete_beam_design_summary" if identity_source == "concrete_beam_design_summary" and not assignment else None
        seed_diag = [d for d in identity_diags if d.code in {FeatureDiagnosticCode.IDENTITY_SEEDED_FROM_DESIGN_SUMMARY, FeatureDiagnosticCode.IDENTITY_SEEDED_NOT_FRAME_CONFIRMED, FeatureDiagnosticCode.TARGET_IDENTITY_SEEDED_FROM_ARGS}]
        source_row_for_identity = assignment or design_row
        source_table_for_identity = "frame_assignments" if assignment else ("concrete_beam_design_summary" if design_row else None)
        design_value_diags: list[FeatureDiagnostic] = []
        if not design_summary_report.get("concrete_beam_design_summary_available"):
            design_value_diags.append(self._table_unavailable_diag("concrete_beam_design_summary", design_summary_report))
        elif design_row is None:
            design_value_diags.append(self._diag(FeatureDiagnosticCode.ROW_MISSING, "No concrete beam design summary row matched seeded identity", attempted_match_keys=[dict(item) for item in design_attempts]))
        direct_geometry_features, direct_geometry_report = self._resolve_direct_api_geometry_features(section_name)
        self._geometry_direct_api_report = direct_geometry_report
        table_width = self._resolve_from_row("beam_width_mm", "frame_section_properties", section_row, ("t2", "Width", "b"))
        table_depth = self._resolve_from_row("beam_depth_mm", "frame_section_properties", section_row, ("t3", "Depth", "h"))
        table_length = self._resolve_from_row("beam_length_mm", "frame_assignments", assignment, ("Length", "ObjectLength", "FrameLength"))
        features = {
            "beam_unique_name": self._identity_feature_from_observed_source("beam_unique_name", source_table_for_identity, source_row_for_identity, ("UniqueName", "Frame", "Beam"), direct_identity=direct_identity, direct_key="component", diagnostics=seed_diag, reason=seed_reason),
            "beam_label": self._identity_feature_from_observed_source("beam_label", source_table_for_identity, source_row_for_identity, ("Label", "Frame", "Beam"), direct_identity=direct_identity, direct_key="label", diagnostics=seed_diag, reason=seed_reason),
            "beam_story": self._identity_feature_from_observed_source("beam_story", source_table_for_identity, source_row_for_identity, _STORY_ALIASES, direct_identity=direct_identity, direct_key="story", diagnostics=seed_diag, reason=seed_reason),
            "beam_section_name": self._identity_feature_from_observed_source("beam_section_name", source_table_for_identity, source_row_for_identity, ("DesignSect", "AnalysisSect", "Section"), direct_identity=direct_identity, direct_key="section", diagnostics=identity_diags if analysis_fallback or not assignment else identity_diags[:1], reason=seed_reason),
            "beam_width_mm": table_width if table_width.status == FeatureValueStatus.RESOLVED else direct_geometry_features.get("beam_width_mm", table_width),
            "beam_depth_mm": table_depth if table_depth.status == FeatureValueStatus.RESOLVED else direct_geometry_features.get("beam_depth_mm", table_depth),
            "beam_length_mm": table_length if table_length.status == FeatureValueStatus.RESOLVED else direct_geometry_features.get("beam_length_mm", table_length),
            "beam_As_top_etabs_required_mm2": self._resolve_from_row("beam_As_top_etabs_required_mm2", "concrete_beam_design_summary", design_row, ("AsTop", "AsMinTop", "totTopRebar", "TopArea"), combo_column_aliases=("AsTopCombo",), diagnostics=design_value_diags),
            "beam_As_bottom_etabs_required_mm2": self._resolve_from_row("beam_As_bottom_etabs_required_mm2", "concrete_beam_design_summary", design_row, ("AsBot", "AsMinBot", "totBotRebar", "BotArea"), combo_column_aliases=("AsBotCombo",), diagnostics=design_value_diags),
            "beam_shear_rebar_etabs_required_mm2": self._resolve_from_row("beam_shear_rebar_etabs_required_mm2", "concrete_beam_design_summary", design_row, ("VRebar",), combo_column_aliases=("VCombo",), diagnostics=design_value_diags),
            "beam_As_top_combo": self._resolve_from_row("beam_As_top_combo", "concrete_beam_design_summary", design_row, ("AsTopCombo",), combo_column_aliases=("AsTopCombo",), diagnostics=design_value_diags),
            "beam_As_bottom_combo": self._resolve_from_row("beam_As_bottom_combo", "concrete_beam_design_summary", design_row, ("AsBotCombo",), combo_column_aliases=("AsBotCombo",), diagnostics=design_value_diags),
            "beam_V_combo": self._resolve_from_row("beam_V_combo", "concrete_beam_design_summary", design_row, ("VCombo",), combo_column_aliases=("VCombo",), diagnostics=design_value_diags),
            "beam_design_warn_msg": self._resolve_from_row("beam_design_warn_msg", "concrete_beam_design_summary", design_row, ("WarnMsg",), diagnostics=design_value_diags),
            "beam_design_err_msg": self._resolve_from_row("beam_design_err_msg", "concrete_beam_design_summary", design_row, ("ErrMsg",), diagnostics=design_value_diags),
        }
        for name, code in (("beam_design_warn_msg", FeatureDiagnosticCode.ETABS_WARNING_MESSAGE), ("beam_design_err_msg", FeatureDiagnosticCode.ETABS_ERROR_MESSAGE)):
            value = features[name].value
            if value not in (None, "", "No Message"):
                features[name] = FeatureValue(
                    feature_name=name,
                    value=value,
                    unit=features[name].unit,
                    semantic_role=features[name].semantic_role,
                    status=features[name].status,
                    evidence=features[name].evidence,
                    diagnostics=features[name].diagnostics + (self._diag(code, "ETABS design diagnostic text preserved as feature evidence only", feature_name=name),),
                )
        return FeatureSnapshot(component_type="beam", component_id=component, identity=identity, features=features, diagnostics=tuple(identity_diags))

    def build_material_snapshot(self) -> FeatureSnapshot:
        concrete_row = self._first_row("material_concrete_data")
        rebar_row = self._first_row("material_rebar_data")
        features = {
            "concrete_fck_mpa": self._resolve_from_row("concrete_fck_mpa", "material_concrete_data", concrete_row, ("Fc", "fc", "Concrete Strength")),
            "rebar_fyk_mpa": self._resolve_from_row("rebar_fyk_mpa", "material_rebar_data", rebar_row, ("Fy", "fy", "Yield Strength")),
        }
        identity = {"component": "MATERIALS", "material_name": _first_present(concrete_row, ("Material", "Name"))[1]}
        return FeatureSnapshot(component_type="material", component_id="MATERIALS", identity=identity, features=features)

    def build_story_snapshot(self) -> FeatureSnapshot:
        drift_row = self._select_story_drift_row()
        torsion_row = self._select_story_torsion_row()
        _, drift_story = _first_present(drift_row, _STORY_ALIASES)
        _, torsion_story = _first_present(torsion_row, _STORY_ALIASES)
        story = self.target.get("story") or drift_story or torsion_story
        story_fallback_diag: tuple[FeatureDiagnostic, ...] = tuple()
        if self.target.get("story") in (None, "") and story not in (None, ""):
            story_fallback_diag = (
                self._diag(
                    FeatureDiagnosticCode.FILTER_NOT_MATCHED,
                    "No target_story was provided; selected deterministic valid story row as smoke fallback",
                    selected_story=story,
                ),
            )
        drift_diag = self._story_base_table_readiness_diagnostics("story_drifts") + story_fallback_diag
        torsion_diag = self._story_base_table_readiness_diagnostics("story_max_over_avg_drifts") + story_fallback_diag
        drift_reason = self._story_base_selected_reason("story_drifts", self._table("story_drifts"), drift_row) if drift_row else None
        torsion_reason = self._story_base_selected_reason("story_max_over_avg_drifts", self._table("story_max_over_avg_drifts"), torsion_row) if torsion_row else None
        features = {
            "story_drift_value": self._resolve_from_row("story_drift_value", "story_drifts", drift_row, _DRIFT_ALIASES, combo_column_aliases=_OUTPUT_CASE_ALIASES, diagnostics=drift_diag, reason=drift_reason),
            "story_drift_max_mm": self._resolve_from_row("story_drift_max_mm", "story_drifts", drift_row, _DRIFT_ALIASES, combo_column_aliases=_OUTPUT_CASE_ALIASES, diagnostics=drift_diag, reason=drift_reason),
            "story_drift_output_case": self._resolve_from_row("story_drift_output_case", "story_drifts", drift_row, _OUTPUT_CASE_ALIASES, combo_column_aliases=_OUTPUT_CASE_ALIASES, diagnostics=drift_diag, reason=drift_reason),
            "story_drift_direction": self._resolve_from_row("story_drift_direction", "story_drifts", drift_row, _DIRECTION_ALIASES, combo_column_aliases=_OUTPUT_CASE_ALIASES, diagnostics=drift_diag, reason=drift_reason),
            "story_torsion_a1_coefficient": self._resolve_from_row("story_torsion_a1_coefficient", "story_max_over_avg_drifts", torsion_row, _RATIO_ALIASES, combo_column_aliases=_OUTPUT_CASE_ALIASES, diagnostics=torsion_diag, reason=torsion_reason),
        }
        story_component = _norm(story or "STORY_SAMPLE")
        identity = {"component": story_component, "story": story}
        return FeatureSnapshot(component_type="story", component_id=story_component, identity=identity, features=features)

    def build_global_snapshot(self) -> FeatureSnapshot:
        base_row = self._select_base_reaction_row()
        base_diag = self._story_base_table_readiness_diagnostics("base_reactions")
        base_reason = self._story_base_selected_reason("base_reactions", self._table("base_reactions"), base_row) if base_row else None
        features = {
            "modal_sum_ux": self._resolve_modal_cumulative_feature("modal_sum_ux", "SumUX"),
            "modal_sum_uy": self._resolve_modal_cumulative_feature("modal_sum_uy", "SumUY"),
            "base_reaction_fx": self._resolve_from_row("base_reaction_fx", "base_reactions", base_row, _FX_ALIASES, combo_column_aliases=_OUTPUT_CASE_ALIASES, diagnostics=base_diag, reason=base_reason),
            "base_reaction_fy": self._resolve_from_row("base_reaction_fy", "base_reactions", base_row, _FY_ALIASES, combo_column_aliases=_OUTPUT_CASE_ALIASES, diagnostics=base_diag, reason=base_reason),
            "base_reaction_x_kN": self._resolve_from_row("base_reaction_x_kN", "base_reactions", base_row, _FX_ALIASES, combo_column_aliases=_OUTPUT_CASE_ALIASES, diagnostics=base_diag, reason=base_reason),
            "base_reaction_y_kN": self._resolve_from_row("base_reaction_y_kN", "base_reactions", base_row, _FY_ALIASES, combo_column_aliases=_OUTPUT_CASE_ALIASES, diagnostics=base_diag, reason=base_reason),
        }
        return FeatureSnapshot(component_type="global", component_id="GLOBAL", identity={"component": "GLOBAL"}, features=features)

    def build_all(self) -> SmokeOutputs:
        snapshots = (self.build_beam_snapshot(), self.build_material_snapshot(), self.build_story_snapshot(), self.build_global_snapshot())
        resolution_report = tuple(self._resolution_report(snapshots))
        evidence_report = tuple(self._evidence_report(snapshots))
        missing_report = tuple(item for item in resolution_report if item["status"] in {"PARTIAL", "MISSING"})
        coverage = tuple(self._coverage_preview(snapshots))
        crosswalk = self._legacy_alias_crosswalk()
        return SmokeOutputs(
            snapshots=snapshots,
            feature_resolution_report=resolution_report,
            evidence_report=evidence_report,
            missing_features_report=missing_report,
            coverage_preview=coverage,
            legacy_alias_crosswalk_report=crosswalk,
            unit_context_report=self._unit_context_report(),
            unit_basis_report=self._unit_basis_report(),
            unit_normalization_report=self._unit_normalization_report(snapshots),
            identity_resolution_report=self._identity_resolution_report(snapshots),
            geometry_resolution_report=self._geometry_resolution_report(snapshots),
            geometry_source_table_debug_report=self._geometry_source_table_debug_report(),
            geometry_direct_api_report=self._geometry_direct_api_report_payload(),
            raw_com_tuple_dump=self._raw_com_tuple_dump_report(),
            parser_strategy_report=self._parser_strategy_report(),
            display_selection_diagnostics=self._display_selection_diagnostics(),
            working_vs_failing_table_comparison=self._working_vs_failing_table_comparison(),
            story_base_table_debug_report=self._story_base_table_debug_report(),
            product_report_source_tables=self._product_report_source_tables(),
            live_failure_delta_report=self._live_failure_delta_report(snapshots),
            boundary_report=self._boundary_report(),
        )


    def _product_report_source_tables(self) -> dict[str, Any]:
        """Expose observed full-row display tables needed by product reporting.

        This is a reporting artifact only. It preserves ETABS observed data for
        all-beam section screening and full modal table rendering without
        changing FeatureSnapshot or CheckResult semantics.
        """
        keys = (
            "frame_assignments",
            "frame_section_properties",
            "modal_participating_mass",
            "story_drifts",
            "story_max_over_avg_drifts",
            "base_reactions",
        )
        tables: dict[str, Any] = {}
        for key in keys:
            table = self._table(key)
            raw = _raw_table_diagnostics_from_table(table)
            if table is None:
                tables[key] = {
                    "table_key": key,
                    "actual_table_name": None,
                    "columns": [],
                    "row_count": 0,
                    "rows": [],
                    "raw_table_diagnostics": raw,
                }
                continue
            tables[key] = {
                "table_key": key,
                "actual_table_name": table.actual_table_name,
                "columns": list(table.columns),
                "row_count": len(table.rows),
                "rows": [dict(row) for row in table.rows],
                "raw_table_diagnostics": raw,
            }
        return {
            "metadata": {
                "artifact": "product_report_source_tables",
                "read_only": True,
                "check_engine_executed": False,
                "engineering_scope_unlocked": False,
                "intended_use": "C13.0/C13.1 product source table reporting plus P1.14 story/base source evidence",
            },
            "tables": tables,
        }

    def _unit_context_report(self) -> dict[str, Any]:
        return {"unit_context": self.unit_context.as_dict()}

    def _unit_basis_report(self) -> dict[str, Any]:
        return {
            "etabs_present_units": self.unit_context.etabs_present_units_raw,
            "etabs_present_units_return_code": self.unit_context.etabs_present_units_return_code,
            "etabs_database_units": self.unit_context.etabs_database_units,
            "source": self.unit_context.source,
            "force_unit": self.unit_context.force_unit,
            "length_unit": self.unit_context.length_unit,
            "temperature_unit": self.unit_context.temperature_unit,
            "unit_query_succeeded": self.unit_context.unit_query_succeeded,
            "unit_basis_confidence": self.unit_context.unit_basis_confidence,
            "unit_query_status": self.unit_context.unit_query_status,
        }

    def _unit_normalization_report(self, snapshots: Sequence[FeatureSnapshot]) -> dict[str, Any]:
        rows = []
        for snapshot in snapshots:
            for name, feature in snapshot.features.items():
                if name in self._unit_evidence:
                    rows.append({"component_type": snapshot.component_type, "component_id": snapshot.component_id, "feature_name": name, **self._unit_evidence[name], "feature_status": feature.status.value})
        return {"unit_context": self.unit_context.as_dict(), "features": rows}

    def _identity_resolution_report(self, snapshots: Sequence[FeatureSnapshot]) -> dict[str, Any]:
        beam = next((s for s in snapshots if s.component_type == "beam"), None)
        features = {}
        if beam:
            for name in _PREVIOUS_LIVE_PARTIAL_FEATURES[:4]:
                value = beam.features.get(name)
                if value:
                    features[name] = {"status": value.status.value, "value": value.value, "evidence_status": value.evidence[0].evidence_status.value if value.evidence else None, "source_table": value.evidence[0].source_table if value.evidence else None, "source_column": value.evidence[0].source_column if value.evidence else None}
        return {**self._identity_report, "identity_features": features}

    def _geometry_resolution_report(self, snapshots: Sequence[FeatureSnapshot]) -> dict[str, Any]:
        beam = next((s for s in snapshots if s.component_type == "beam"), None)
        rows = {}
        if beam:
            for name in ("beam_width_mm", "beam_depth_mm", "beam_length_mm"):
                value = beam.features.get(name)
                if value:
                    rows[name] = {"status": value.status.value, "value": value.value, "unit": value.unit, "evidence_status": value.evidence[0].evidence_status.value if value.evidence else None, "source_table": value.evidence[0].source_table if value.evidence else None, "source_column": value.evidence[0].source_column if value.evidence else None, "unit_evidence": self._unit_evidence.get(name)}
        return {"geometry_features": rows, "section_name_parse_suggestion": next((d.details for d in (beam.diagnostics if beam else ()) if d.code == FeatureDiagnosticCode.SECTION_NAME_PARSE_SUGGESTION), None)}

    def _geometry_source_table_debug_report(self) -> dict[str, Any]:
        return dict(self._geometry_debug)


    def _geometry_direct_api_report_payload(self) -> dict[str, Any]:
        return dict(self._geometry_direct_api_report or {"used": False, "diagnostics": []})

    def _raw_com_tuple_dump_report(self) -> dict[str, Any]:
        return dict(self.table_extraction_debug.get("raw_com_tuple_dump") or {"tables": []})

    def _parser_strategy_report(self) -> dict[str, Any]:
        return dict(self.table_extraction_debug.get("parser_strategy_report") or {"tables": []})

    def _display_selection_diagnostics(self) -> dict[str, Any]:
        return dict(self.table_extraction_debug.get("display_selection_diagnostics") or {
            "metadata": {"read_only": True, "model_mutated": False},
            "diagnostics": [
                {"severity": "INFO", "code": "DISPLAY_SELECTION_NOT_MUTATED", "message": "C8.3 smoke does not call SetLoadCasesSelectedForDisplay, SetLoadCombinationsSelectedForDisplay, or SetLoadPatternsSelectedForDisplay."}
            ],
            "may_require_display_selection": ["analysis result tables"],
            "model_definition_tables_should_not_require_load_case_selection": ["Frame Assignments - Summary", "Frame Section Property Definitions - Concrete Rectangular"],
        })

    def _working_vs_failing_table_comparison(self) -> dict[str, Any]:
        if self.table_extraction_debug.get("working_vs_failing_table_comparison"):
            return dict(self.table_extraction_debug["working_vs_failing_table_comparison"])
        keys = ("concrete_beam_design_summary", "frame_assignments", "frame_section_properties")
        tables = []
        for key in keys:
            table = self._table(key)
            raw = _raw_table_diagnostics_from_table(table)
            tables.append({
                "table_key": key,
                "actual_table_name": table.actual_table_name if table else None,
                "fields_count": len(table.columns) if table else 0,
                "number_records": raw.get("number_records"),
                "table_data_length": raw.get("table_data_length"),
                "parser_status": raw.get("parser_status"),
                "sample_first_row": dict(table.rows[0]) if table and table.rows else None,
            })
        return {"tables": tables}

    def _story_base_required_aliases(self, table_key: str) -> dict[str, Sequence[str]]:
        if table_key == "story_drifts":
            return {"story": _STORY_ALIASES, "output_case": _OUTPUT_CASE_ALIASES, "direction": _DIRECTION_ALIASES, "drift": _DRIFT_ALIASES}
        if table_key == "story_max_over_avg_drifts":
            return {"story": _STORY_ALIASES, "output_case": _OUTPUT_CASE_ALIASES, "ratio": _RATIO_ALIASES}
        if table_key == "base_reactions":
            return {"output_case": _OUTPUT_CASE_ALIASES, "fx": _FX_ALIASES, "fy": _FY_ALIASES}
        return {}

    def _story_base_selected_row(self, table_key: str) -> Mapping[str, Any] | None:
        if table_key == "story_drifts":
            return self._select_story_drift_row()
        if table_key == "story_max_over_avg_drifts":
            return self._select_story_torsion_row()
        if table_key == "base_reactions":
            return self._select_base_reaction_row()
        return None

    def _story_base_selected_reason(self, table_key: str, table: CanonicalTable | None, selected: Mapping[str, Any] | None) -> str:
        if table is None:
            return "table_missing"
        if selected is None and not table.rows:
            sample_only = any(isinstance(d, Mapping) and d.get("code") == "RESOLVER_ONLY_HAS_SAMPLE_ROWS" for d in table.units.get("resolver_ingestion_diagnostics", ()) if isinstance(table.units, Mapping))
            return "only_debug_sample_rows_available" if sample_only else "no_resolver_rows"
        if selected is None:
            return "rows_present_but_required_alias_or_target_match_missing"
        if table_key in {"story_drifts", "story_max_over_avg_drifts"}:
            _, story = _first_present(selected, _STORY_ALIASES)
            _, output_case = _first_present(selected, _OUTPUT_CASE_ALIASES)
            story_matches = self.target.get("story") in (None, "") or _story_values_match(story, self.target.get("story"))
            output_case_matches = _norm(output_case).casefold() == self.preferred_output_case.casefold()
            if story_matches and output_case_matches:
                return "target_story_and_preferred_output_case_match_with_required_columns"
            if story_matches:
                return "target_story_match_with_required_columns"
        if table_key == "base_reactions":
            _, output_case = _first_present(selected, _OUTPUT_CASE_ALIASES)
            if _norm(output_case).casefold() == self.preferred_output_case.casefold():
                return "preferred_output_case_match_with_numeric_fx_fy"
            return "no_silent_fallback_allowed"
        if table_key in {"story_drifts", "story_max_over_avg_drifts"}:
            _, output_case = _first_present(selected, _OUTPUT_CASE_ALIASES)
            if _norm(output_case).casefold() == self.preferred_output_case.casefold():
                return "target_story_and_preferred_output_case_match_with_required_columns"
        return "deterministic_valid_row"

    def _story_base_table_debug_report(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        preferred_output_case = self.preferred_output_case
        for table_key in _STORY_BASE_TABLE_KEYS:
            table = self._table(table_key)
            raw = _raw_table_diagnostics_from_table(table)
            headers = list(table.columns) if table else list(raw.get("fields") or ())
            rows = [dict(row) for row in (table.rows if table else ())]
            units = dict(table.units) if table and isinstance(table.units, Mapping) else {}
            selected = self._story_base_selected_row(table_key)
            required_aliases = self._story_base_required_aliases(table_key)
            required_columns_seen = {}
            required_alias_values_seen = {}
            for name, aliases in required_aliases.items():
                values = self._available_alias_samples(rows, aliases)
                required_columns_seen[name] = any(_first_present(row, aliases)[0] is not None for row in rows) or any(_norm_key(h) in {_norm_key(a) for a in aliases} for h in headers)
                required_alias_values_seen[name] = values
            diagnostics = [dict(d) for d in units.get("resolver_ingestion_diagnostics", ()) if isinstance(d, Mapping)]
            if rows and selected is None:
                diagnostics.append({
                    "severity": "WARNING",
                    "code": "RESOLVER_SELECTOR_NO_MATCH_WITH_ROWS_PRESENT",
                    "message": "Resolver table has rows but selector did not find a matching source row.",
                    "details": {"resolver_row_count": len(rows), "target_story": self.target.get("story")},
                })
            if not rows and raw.get("number_records") and int(raw.get("number_records") or 0) > 0 and raw.get("table_data_length") not in (0, "0", None):
                diagnostics.append({
                    "severity": "WARNING",
                    "code": "RESOLVER_TABLE_PARSE_MISMATCH_WITH_PROBE",
                    "message": "Probe/debug metadata reports rows but resolver has zero production rows.",
                    "details": {"number_records": raw.get("number_records"), "table_data_length": raw.get("table_data_length")},
                })
            why_partial = None
            if not rows:
                why_partial = "resolver_row_count_is_zero"
                if any(d.get("code") == "RESOLVER_ONLY_HAS_SAMPLE_ROWS" for d in diagnostics):
                    why_partial = "only sample rows were available; full parsed rows are required"
            elif selected is None:
                why_partial = "selector found no row matching target story/output case and required numeric aliases"
            out[table_key] = {
                "canonical_table_name": table_key,
                "table_alias": table_key,
                "actual_table_name": table.actual_table_name if table else raw.get("table_name"),
                "resolver_row_count": len(rows),
                "row_count": len(rows),
                "debug_sample_row_count": int(units.get("debug_sample_row_count") or len(units.get("debug_sample_rows") or rows[:5])),
                "headers": headers,
                "normalized_headers": [_norm_key(h) for h in headers],
                "sample_rows": [dict(row) for row in (units.get("debug_sample_rows") or rows[:5])],
                "target_story": self.target.get("story"),
                "preferred_output_case": preferred_output_case,
                "preferred_output_kind_detected": raw.get("preferred_output_kind_detected", "unknown"),
                "attempted_case_fallback": bool(raw.get("attempted_case_fallback")),
                "skipped_case_selection_because_combo_succeeded": bool(raw.get("skipped_case_selection_because_combo_succeeded")),
                "selected_row": dict(selected) if selected else None,
                "selected_row_reason": self._story_base_selected_reason(table_key, table, selected),
                "parser_status": _classified_parser_status(raw, row_count=len(rows), headers=headers),
                "signature_attempts": list(raw.get("signature_attempts") or ()),
                "selected_signature": dict(raw.get("selected_signature") or {}),
                "selected_signature_reason": raw.get("selected_signature_reason"),
                "parser_status_by_signature": dict(raw.get("parser_status_by_signature") or {}),
                "table_data_length_by_signature": dict(raw.get("table_data_length_by_signature") or {}),
                "number_records_by_signature": dict(raw.get("number_records_by_signature") or {}),
                "display_selection_attempted": bool(raw.get("display_selection_attempted")),
                "display_selection_attempts": list(raw.get("display_selection_attempts") or ()),
                "display_selection_selected_method": raw.get("display_selection_selected_method"),
                "display_selection_success": bool(raw.get("display_selection_success")),
                "fetch_after_display_selection": bool(raw.get("fetch_after_display_selection")),
                "header_count": raw.get("header_count", len(headers)),
                "number_fields_detected": raw.get("number_fields_detected"),
                "number_fields_source": raw.get("number_fields_source"),
                "source_row_storage_field_used": units.get("source_row_storage_field_used", "none"),
                "required_columns_seen": required_columns_seen,
                "required_alias_values_seen": required_alias_values_seen,
                "available_story_samples": self._available_alias_samples(rows, _STORY_ALIASES),
                "available_output_case_samples": self._available_alias_samples(rows, _OUTPUT_CASE_ALIASES),
                "why_partial_if_partial": why_partial,
                "raw_table_diagnostics": raw,
                "diagnostics": diagnostics + (
                    [{"severity": "WARNING", "code": "ETABS_TABLEDATA_EMPTY_DESPITE_RECORDS", "message": "ETABS reported records but returned empty TableData", "details": raw}]
                    if _tabledata_empty_despite_records(raw) and not rows else []
                ),
            }
        return out

    def _live_failure_delta_report(self, snapshots: Sequence[FeatureSnapshot]) -> dict[str, Any]:
        beam = next((s for s in snapshots if s.component_type == "beam"), None)
        after = []
        for name in _PREVIOUS_LIVE_PARTIAL_FEATURES:
            feature = beam.features.get(name) if beam else None
            ev = feature.evidence[0] if feature and feature.evidence else None
            after.append({
                "feature_name": name,
                "old_status": "PARTIAL",
                "new_status": feature.status.value if feature else "MISSING",
                "old_reason": "Manual C8 live run used fixture-like BEAM_SMOKE component id and no matching source row was found",
                "new_reason": ev.reason if ev and ev.reason else ("resolved with full evidence" if feature and feature.status == FeatureValueStatus.RESOLVED else "unresolved"),
                "evidence_status": ev.evidence_status.value if ev else None,
                "source_table": ev.source_table if ev else None,
                "source_column": ev.source_column if ev else None,
                "source_row": dict(ev.source_row) if ev else {},
                "value": feature.value if feature else None,
                "unit": feature.unit if feature else None,
                "resolved_by": self._resolved_by(name, feature),
            })
        return {"previous_live_problem": {"partial_identity_geometry_features": list(_PREVIOUS_LIVE_PARTIAL_FEATURES)}, "after_c8_1": after}

    def _resolved_by(self, name: str, feature: FeatureValue | None) -> list[str]:
        if feature is None or not feature.evidence:
            return ["unresolved"]
        source = feature.evidence[0].source_table
        if source == "concrete_beam_design_summary" and name in _PREVIOUS_LIVE_PARTIAL_FEATURES[:4]:
            return ["design_summary_seed"]
        if source == "frame_assignments":
            return ["direct_frame_assignment"]
        if source == "frame_section_properties":
            return ["section_table_match"]
        if source == "direct_etabs_api":
            return ["direct_api"]
        return ["unresolved"] if feature.status != FeatureValueStatus.RESOLVED else ["direct_frame_assignment"]

    def _boundary_report(self) -> dict[str, Any]:
        return {
            "metadata": {
                "sprint": "C8_3_LIVE_MODEL_GEOMETRY_RETRIEVAL",
                "check_engine_executed": False,
                "check_result_emitted": False,
                "live_verdict_emitted": False,
            },
            "live_etabs_required_for_ci": False,
            "provider_check_execution": False,
            "legacy_imports_added": False,
            "runner_v2_runtime_archx_imports": False,
            "excel_production_path_added": False,
            "rebar_flexure_shear_unlocked": False,
            "etabs_live_path_opt_in_only": True,
        }

    def _resolution_report(self, snapshots: Sequence[FeatureSnapshot]) -> list[dict[str, Any]]:
        rows = []
        for snapshot in snapshots:
            for name, feature in snapshot.features.items():
                rows.append({
                    "component_type": snapshot.component_type,
                    "component_id": snapshot.component_id,
                    "feature_name": name,
                    "status": feature.status.value,
                    "value": feature.value,
                    "unit": feature.unit,
                    "source_table": feature.evidence[0].source_table if feature.evidence else None,
                    "source_column": feature.evidence[0].source_column if feature.evidence else None,
                    "diagnostics": [d.as_dict() for d in feature.diagnostics],
                    "unit_evidence": self._unit_evidence.get(name),
                })
        return rows

    def _evidence_report(self, snapshots: Sequence[FeatureSnapshot]) -> list[dict[str, Any]]:
        rows = []
        for snapshot in snapshots:
            for name, evidence_items in snapshot.evidence_by_feature.items():
                for ev in evidence_items:
                    rows.append({"component_type": snapshot.component_type, "component_id": snapshot.component_id, "feature_name": name, **ev.as_dict(), "unit_evidence": self._unit_evidence.get(name)})
        return rows

    def _coverage_preview(self, snapshots: Sequence[FeatureSnapshot]) -> list[dict[str, Any]]:
        builder = CoverageBuilder(self.contract_bundle)
        rows = []
        for snapshot in snapshots:
            try:
                matrix = builder.build_for_snapshot(snapshot)
            except Exception as exc:
                rows.append({"component_type": snapshot.component_type, "component_id": snapshot.component_id, "coverage_status": "PARTIAL", "reason": f"coverage preview diagnostic only: {exc}"})
                continue
            for row in matrix.rows:
                rows.append(row.as_dict())
        return rows

    def _legacy_alias_crosswalk(self) -> dict[str, Any]:
        current_tables = sorted(self.table_registry.keys())
        useful_reference_aliases = {
            "table_aliases": ["Base Reactions", "Story Drifts", "Story Max Over Avg Drifts", "Modal Participating Mass Ratios", "Frame Assignments - Summary", "Frame Section Property Definitions - Concrete Rectangular"],
            "column_aliases": ["OutputCase", "UniqueName", "Label", "Story", "DesignSect", "AnalysisSect", "t2", "t3", "AsTop", "AsBot", "VRebar"],
        }
        return {
            "legacy_policy": "reference_only_no_imports_no_execution",
            "current_table_registry_keys_considered": current_tables,
            "reference_aliases_used_for_c8_1": useful_reference_aliases,
            "direct_import_allowed": False,
        }



def direct_api_geometry_from_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        candidate = payload.get("direct_api_geometry") or payload.get("c8_3_direct_api_geometry") or payload.get("verified_provider_geometry")
        return dict(candidate) if isinstance(candidate, Mapping) else {}
    return {}


def _preview(value: Any, limit: int = 240) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def raw_com_tuple_dump_for_response(raw_response: Any, *, table_name: str) -> dict[str, Any]:
    items = list(raw_response) if isinstance(raw_response, (list, tuple)) and not isinstance(raw_response, (str, bytes)) else [raw_response]
    rows = []
    for index, item in enumerate(items):
        length = len(item) if isinstance(item, (list, tuple, dict, str)) else None
        rows.append({"index": index, "python_type": type(item).__name__, "repr_preview": _preview(item), "length_if_sequence": length})
    return {
        "table_name": table_name,
        "type_raw_response": type(raw_response).__name__,
        "len_raw_response": len(raw_response) if isinstance(raw_response, (list, tuple, dict, str)) else None,
        "items": rows,
    }


def _strategy_rows(fields: Sequence[str], table_data: Any, number_records: int | None, max_rows: int = 3) -> tuple[list[dict[str, Any]], str, int | None]:
    diagnostics: list[dict[str, Any]] = []
    debug: dict[str, Any] = {}
    rows, status = _rows_from_probe_data(table_data, tuple(fields), number_records, max_rows, debug, diagnostics)
    return [dict(r) for r in rows], status, debug.get("table_data_length")


def parser_strategy_report_for_response(raw_response: Any, *, table_name: str, max_rows: int = 3) -> dict[str, Any]:
    strategies: list[dict[str, Any]] = []
    # Use the production parser as the current strategy.
    try:
        parsed = parse_etabs_display_table_result(raw_response, actual_table_name=table_name, max_rows=max_rows)
        strategies.append({
            "strategy_name": "current_parser",
            "fields_detected": list(parsed.field_keys),
            "number_records_detected": parsed.row_count_reported,
            "table_data_detected": bool(parsed.rows),
            "table_data_length": parsed.debug.get("table_data_length"),
            "expected_flat_length": parsed.debug.get("expected_flat_length"),
            "parser_status": parsed.fetch_status,
            "sample_rows": [dict(r) for r in parsed.rows],
        })
    except Exception as exc:
        strategies.append({"strategy_name": "current_parser", "parser_status": "FAILED", "diagnostics": [str(exc)], "sample_rows": []})

    if isinstance(raw_response, Mapping):
        fields = raw_response.get("field_keys") or raw_response.get("fields") or raw_response.get("headers") or []
        table_data = raw_response.get("table_data") or raw_response.get("TableData") or raw_response.get("data") or []
        number_records = _int_or_none(raw_response.get("number_records") or raw_response.get("NumberRecords"))
        rows, status, length = _strategy_rows([str(f) for f in fields], table_data, number_records, max_rows)
        expected = (number_records or 0) * len(fields) if fields and number_records is not None else None
        strategies.append({"strategy_name": "mapping_explicit_keys", "fields_detected": list(fields), "number_records_detected": number_records, "table_data_detected": bool(rows), "table_data_length": length, "expected_flat_length": expected, "parser_status": status, "sample_rows": rows})
    elif isinstance(raw_response, (list, tuple)) and not isinstance(raw_response, (str, bytes)):
        values = list(raw_response)
        for name, f_idx, nr_idx, data_idx in (
            ("tuple-index strategy A", 2, 3, 4),
            ("tuple-index strategy B", 4, 2, 5),
            ("byref/out-param strategy", 1, 3, 5),
        ):
            fields = values[f_idx] if len(values) > f_idx else []
            if isinstance(fields, str):
                fields = _split_probe_field_string(fields)
            number_records = _int_or_none(values[nr_idx] if len(values) > nr_idx else None)
            table_data = values[data_idx] if len(values) > data_idx else []
            fields_tuple = [str(f) for f in fields] if isinstance(fields, (list, tuple)) else []
            rows, status, length = _strategy_rows(fields_tuple, table_data, number_records, max_rows)
            expected = (number_records or 0) * len(fields_tuple) if fields_tuple and number_records is not None else None
            strategies.append({"strategy_name": name, "fields_detected": fields_tuple, "number_records_detected": number_records, "table_data_detected": bool(rows), "table_data_length": length, "expected_flat_length": expected, "parser_status": status, "sample_rows": rows})
        # Scan any sequence with expected flat length.
        int_values = [_int_or_none(v) for v in values]
        string_sequences = [v for v in values if isinstance(v, (list, tuple)) and all(isinstance(x, str) for x in v)]
        fields = string_sequences[0] if string_sequences else []
        records = next((i for i in int_values if isinstance(i, int) and i > 0 and i != len(fields)), None)
        expected = records * len(fields) if fields and records else None
        matched_data = None
        if expected:
            for v in values:
                if isinstance(v, (list, tuple)) and len(v) == expected:
                    matched_data = v
                    break
        rows, status, length = _strategy_rows([str(f) for f in fields], matched_data or [], records, max_rows)
        strategies.append({"strategy_name": "fallback scanning expected_flat_length", "fields_detected": list(fields), "number_records_detected": records, "table_data_detected": bool(rows), "table_data_length": length, "expected_flat_length": expected, "parser_status": status, "sample_rows": rows})
    return {"table_name": table_name, "strategies": strategies}


def _split_probe_field_string(value: str) -> tuple[str, ...]:
    text = value.strip()
    delimiter = "\t" if "\t" in text else "," if "," in text else None
    return tuple(part.strip() for part in text.split(delimiter) if part.strip()) if delimiter else ((text,) if text else tuple())


def _rows_from_probe_data(table_data: Any, field_keys: tuple[str, ...], number_records: int | None, max_rows: int, debug: dict[str, Any], diagnostics: list[dict[str, Any]]) -> tuple[tuple[Mapping[str, Any], ...], str]:
    try:
        return _rows_from_data(table_data, field_keys, number_records, max_rows, debug, diagnostics)
    except Exception:
        return tuple(), "FAILED"


def table_extraction_debug_from_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    direct = payload.get("table_extraction_debug") or payload.get("c8_3_table_extraction_debug")
    if isinstance(direct, Mapping):
        return dict(direct)
    tables = []
    raw_dumps = []
    strategies = []
    for item in _table_items_from_payload(payload):
        if not isinstance(item, Mapping):
            continue
        table_name = str(item.get("actual_table_name") or item.get("table_name") or "UNKNOWN_TABLE")
        if table_name not in {"Frame Assignments - Summary", "Frame Section Property Definitions - Concrete Rectangular", "Concrete Beam Design Summary - TS 500-2000(R2018)", "Story Drifts", "Story Max Over Avg Drifts", "Base Reactions", "Modal Participating Mass Ratios"}:
            continue
        raw = item.get("raw_response") or item.get("raw_com_response") or item.get("raw_table_response")
        if raw is not None:
            raw_dumps.append(raw_com_tuple_dump_for_response(raw, table_name=table_name))
            strategies.append(parser_strategy_report_for_response(raw, table_name=table_name))
        tables.append({"table_name": table_name, "raw_table_diagnostics": item.get("raw_table_diagnostics")})
    comparison = {"tables": tables}
    return {
        "raw_com_tuple_dump": {"tables": raw_dumps},
        "parser_strategy_report": {"tables": strategies},
        "working_vs_failing_table_comparison": comparison,
    }


def _row_tuple_from_field(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return tuple()
    rows: list[Mapping[str, Any]] = []
    for item in value:
        if isinstance(item, Mapping):
            rows.append(dict(item))
    return tuple(rows)


def _int_from_any(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _reported_row_count_from_item(item: Mapping[str, Any], raw: Mapping[str, Any] | None, *, fallback: int) -> int:
    candidates = (
        item.get("row_count"),
        item.get("row_count_reported"),
        item.get("number_records"),
        raw.get("number_records") if raw else None,
        raw.get("NumberRecords") if raw else None,
    )
    for candidate in candidates:
        parsed = _int_from_any(candidate)
        if parsed is not None:
            return parsed
    return fallback


def _resolver_rows_from_item(item: Mapping[str, Any], *, actual_name: str) -> tuple[tuple[Mapping[str, Any], ...], str, tuple[Mapping[str, Any], ...], list[dict[str, Any]], tuple[str, ...], str | None]:
    """Return production resolver rows and debug samples separately.

    Full row fields are accepted first.  Sample fields are debug-only when the
    payload reports more rows than the sample contains.  Legacy tiny fixtures
    that contain only sample rows and no reported larger row count remain usable
    as explicit fixture data.
    """
    diagnostics: list[dict[str, Any]] = []
    raw_diag = item.get("raw_table_diagnostics") or item.get("raw_table_debug") or item.get("debug") or {}
    raw_diag = dict(raw_diag) if isinstance(raw_diag, Mapping) else {}
    headers = tuple(str(h) for h in item.get("headers") or item.get("field_keys") or raw_diag.get("fields") or raw_diag.get("field_keys") or ())

    for field in ("rows", "parsed_rows", "full_rows", "table_rows"):
        if field in item:
            rows = _row_tuple_from_field(item.get(field))
            sample = tuple(dict(row) for row in rows[:5])
            if not headers and rows:
                headers = tuple(str(k) for k in rows[0].keys())
            return rows, field, sample, diagnostics, headers, None

    raw_response = item.get("raw_response") or item.get("raw_com_response") or item.get("raw_table_response")
    if raw_response is not None:
        parsed = parse_etabs_display_table_result(raw_response, actual_table_name=actual_name, max_rows=None)
        rows = tuple(dict(row) for row in parsed.rows)
        if parsed.field_keys:
            headers = tuple(str(h) for h in parsed.field_keys)
        diagnostics.extend(dict(d) for d in parsed.diagnostics)
        sample = tuple(dict(row) for row in rows[:5])
        if rows:
            return rows, "raw_response", sample, diagnostics, headers, parsed.fetch_status

    sample_field = None
    sample_rows: tuple[Mapping[str, Any], ...] = tuple()
    for field in ("sample_rows", "sample_rows_limited"):
        if field in item:
            sample_field = field
            sample_rows = _row_tuple_from_field(item.get(field))
            break
    if sample_field:
        if not headers and sample_rows:
            headers = tuple(str(k) for k in sample_rows[0].keys())
        reported_count = _reported_row_count_from_item(item, raw_diag, fallback=len(sample_rows))
        sample_count = len(sample_rows)
        if reported_count > sample_count:
            diagnostics.append({
                "severity": "WARNING",
                "code": "RESOLVER_ONLY_HAS_SAMPLE_ROWS",
                "message": "Resolver payload exposed only debug sample rows; production CanonicalTable.rows was not populated from the sample.",
                "details": {
                    "actual_table_name": actual_name,
                    "source_row_storage_field_used": sample_field,
                    "reported_row_count": reported_count,
                    "debug_sample_row_count": sample_count,
                },
            })
            return tuple(), sample_field, tuple(dict(row) for row in sample_rows[:5]), diagnostics, headers, "RESOLVER_ONLY_HAS_SAMPLE_ROWS"
        diagnostics.append({
            "severity": "INFO",
            "code": "LEGACY_FIXTURE_SAMPLE_ROWS_USED",
            "message": "Tiny fixture has no separate full-row storage; sample rows are used as fixture resolver rows only.",
            "details": {"actual_table_name": actual_name, "sample_row_count": sample_count},
        })
        return sample_rows, sample_field, tuple(dict(row) for row in sample_rows[:5]), diagnostics, headers, "FIXTURE_SAMPLE_ROWS"

    return tuple(), "none", tuple(), diagnostics, headers, None


def tables_from_probe_report(payload: Any, bundle: ContractBundle) -> tuple[CanonicalTable, ...]:
    registry = TableRegistry.from_dict(bundle.catalog("table_registry.yaml"))
    unit_context = unit_context_from_payload(payload).as_dict()
    base_table_units = {
        "unit_context_source": unit_context.get("source") or "unknown",
        "etabs_present_units_raw": unit_context.get("etabs_present_units_raw"),
        "etabs_database_units": unit_context.get("etabs_database_units"),
        "force_unit": unit_context.get("force_unit"),
        "length_unit": unit_context.get("length_unit"),
        "temperature_unit": unit_context.get("temperature_unit"),
        "etabs_present_units_return_code": unit_context.get("etabs_present_units_return_code"),
        "unit_query_succeeded": bool(unit_context.get("unit_query_succeeded")),
        "run_id": unit_context.get("run_id"),
        "unit_query_status": unit_context.get("unit_query_status") or "MISSING",
        "unit_basis_confidence": unit_context.get("unit_basis_confidence") or "unknown",
    }
    tables: list[CanonicalTable] = []
    for item in _table_items_from_payload(payload):
        if not isinstance(item, Mapping):
            continue
        actual_name = str(item.get("actual_table_name") or item.get("table_name") or "")
        canonical = item.get("canonical_table_key") or registry.canonical_key_for_alias(actual_name) or actual_name
        if not actual_name or not canonical:
            continue
        resolver_rows, source_field, debug_sample_rows, ingestion_diagnostics, headers, parser_status = _resolver_rows_from_item(item, actual_name=actual_name)
        table_units = dict(base_table_units)
        raw_diag = _raw_table_diagnostics_from_item(item, headers=headers, rows=resolver_rows)
        if parser_status and raw_diag.get("parser_status") in {None, "UNKNOWN"}:
            raw_diag["parser_status"] = parser_status
        raw_diag["resolver_row_count"] = len(resolver_rows)
        raw_diag["debug_sample_row_count"] = len(debug_sample_rows)
        table_units["raw_table_diagnostics"] = raw_diag
        table_units["resolver_row_count"] = len(resolver_rows)
        table_units["debug_sample_row_count"] = len(debug_sample_rows)
        table_units["debug_sample_rows"] = [dict(row) for row in debug_sample_rows]
        table_units["source_row_storage_field_used"] = source_field
        table_units["resolver_ingestion_diagnostics"] = ingestion_diagnostics
        table_units["parser_status"] = parser_status or raw_diag.get("parser_status")
        tables.append(
            CanonicalTable(
                table_key=str(canonical),
                actual_table_name=actual_name,
                columns=headers,
                rows=resolver_rows,
                units=table_units,
                source="LIVE_ETABS_DISPLAY_TABLE" if item.get("raw_response") or item.get("raw_com_response") or item.get("raw_table_response") else "C8_1_PROBE_FIXTURE",
            )
        )
    return tuple(tables)


def write_smoke_outputs(out_dir: Path, outputs: SmokeOutputs) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshots_payload = {
        "metadata": {
            "sprint": "C8_3_LIVE_MODEL_GEOMETRY_RETRIEVAL",
            "check_engine_executed": False,
            "check_result_emitted": False,
            "live_verdict_emitted": False,
            "unit_context": outputs.unit_context_report["unit_context"],
        },
        "snapshots": [snapshot.as_dict() for snapshot in outputs.snapshots],
        "feature_status_counts": dict(Counter(row["status"] for row in outputs.feature_resolution_report)),
    }
    files = {
        "feature_snapshot.json": snapshots_payload,
        "feature_resolution_report.json": list(outputs.feature_resolution_report),
        "evidence_report.json": list(outputs.evidence_report),
        "missing_features_report.json": list(outputs.missing_features_report),
        "coverage_preview.json": list(outputs.coverage_preview),
        "legacy_alias_crosswalk_report.json": outputs.legacy_alias_crosswalk_report,
        "identity_resolution_report.json": outputs.identity_resolution_report,
        "geometry_resolution_report.json": outputs.geometry_resolution_report,
        "unit_context_report.json": outputs.unit_context_report,
        "unit_basis_report.json": outputs.unit_basis_report,
        "unit_normalization_report.json": outputs.unit_normalization_report,
        "geometry_source_table_debug_report.json": outputs.geometry_source_table_debug_report,
        "geometry_direct_api_report.json": outputs.geometry_direct_api_report,
        "story_base_table_debug_report.json": outputs.story_base_table_debug_report,
        "story_base_resolver_table_debug_report.json": outputs.story_base_table_debug_report,
        "product_report_source_tables.json": outputs.product_report_source_tables,
        "live_failure_delta_report.json": outputs.live_failure_delta_report,
        "c8_1_boundary_report.json": outputs.boundary_report,
        "c8_3_boundary_report.json": outputs.boundary_report,
        "manual_live_etabs_feedback_report.json": {"metadata": {"reference_only": True}, "manual_live_run_required_elsewhere": True},
    }
    for name, payload in files.items():
        write_json_payload(out_dir / name, payload)
    debug_dir = out_dir.parent / "c8_3_etabs_table_extraction_debug"
    debug_files = {
        "raw_com_tuple_dump.json": outputs.raw_com_tuple_dump,
        "parser_strategy_report.json": outputs.parser_strategy_report,
        "display_selection_diagnostics.json": outputs.display_selection_diagnostics,
        "working_vs_failing_table_comparison.json": outputs.working_vs_failing_table_comparison,
    }
    for name, payload in debug_files.items():
        write_json_payload(debug_dir / name, payload)


__all__ = [
    "C8LiveFeatureResolverSmoke",
    "SmokeOutputs",
    "UnitContext",
    "classify_combo",
    "decode_etabs_present_units",
    "direct_api_geometry_from_payload",
    "parser_strategy_report_for_response",
    "raw_com_tuple_dump_for_response",
    "table_extraction_debug_from_payload",
    "tables_from_probe_report",
    "unit_context_from_payload",
    "to_jsonable",
    "build_seed_identity_from_target",
    "write_json_payload",
    "write_smoke_outputs",
]
