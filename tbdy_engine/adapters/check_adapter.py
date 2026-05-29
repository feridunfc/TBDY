from __future__ import annotations

import re
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Dict, List, Mapping


_SOURCE_RE = re.compile(r"(?:^|[|,;\s])source\s*=\s*([A-Za-z0-9_:\-./]+)")


def _model_to_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except TypeError:
            pass
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        try:
            return obj.to_dict()
        except TypeError:
            pass
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "__dict__"):
        return dict(vars(obj))
    return {}


@dataclass(frozen=True)
class CheckResult:
    id: str
    component: str
    check_type: str
    status: str
    demand: float | None
    capacity: float | None
    ratio: float | None
    evidence: Mapping[str, object]
    messages: tuple[str, ...]
    story: str | None = None
    section: str | None = None
    unit: str | None = None
    code_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CheckAdapter:
    def __init__(self, runtime_catalog: Any):
        self.runtime_catalog = runtime_catalog
        self.checks_by_eval = self._index_enabled_checks(runtime_catalog)

    def _index_enabled_checks(self, runtime_catalog: Any) -> Dict[str, List[Dict[str, Any]]]:
        out: Dict[str, List[Dict[str, Any]]] = {}
        catalog = _model_to_dict(runtime_catalog)
        checks = catalog.get("checks", {}) or {}
        for check_id, check_obj in checks.items():
            check = _model_to_dict(check_obj)
            check.setdefault("id", check_id)
            if not check.get("runner_enabled", True):
                continue
            ev = check.get("evaluation")
            if ev:
                out.setdefault(ev, []).append(check)
        return out

    def adapt_all(self, evaluation_results: Dict[str, Any]) -> List[CheckResult]:
        results: List[CheckResult] = []
        eval_payloads = evaluation_results.get("results", {}) or {}

        for evaluation_name, evaluation_result in eval_payloads.items():
            results.extend(self.adapt(evaluation_name, evaluation_result))

        for evaluation_name, error in (evaluation_results.get("errors", {}) or {}).items():
            for check_def in self.checks_by_eval.get(evaluation_name, []):
                results.append(self._error_result(check_def, error))

        return results

    def adapt(self, evaluation_name: str, evaluation_result: Any) -> List[CheckResult]:
        eval_dict = _model_to_dict(evaluation_result)
        if eval_dict.get("status") == "ERROR":
            return []

        out: List[CheckResult] = []
        for check_def in self.checks_by_eval.get(evaluation_name, []):
            fields = [check_def.get("evaluation_field")] + list(check_def.get("fallback_fields", []) or [])
            fields = [f for f in fields if f]
            extracted = None
            used = ""
            for field in fields:
                extracted = self._extract_field(evaluation_result, field)
                if extracted not in (None, []):
                    used = field
                    break

            if extracted in (None, []):
                out.append(self._no_data_result(check_def, f"No data found for evaluation field(s): {fields}"))
                continue

            if isinstance(extracted, list):
                out.extend(self._to_check_result(check_def, item, used) for item in extracted)
            else:
                out.append(self._to_check_result(check_def, extracted, used))
        return out

    def _extract_field(self, evaluation_result: Any, field: str):
        data = _model_to_dict(evaluation_result)
        if field in data:
            return data[field]
        for container_key in ("checks", "results", "summary", "report_tables"):
            container = data.get(container_key)
            if isinstance(container, dict) and field in container:
                return container[field]

        outputs = data.get("outputs")
        if outputs is None and hasattr(evaluation_result, "outputs"):
            outputs = getattr(evaluation_result, "outputs")

        if outputs is not None:
            found = []
            for item in outputs or []:
                item_d = _model_to_dict(item)
                checks = item_d.get("checks")
                if checks is None and hasattr(item, "checks"):
                    checks = getattr(item, "checks")
                checks_d = _model_to_dict(checks)
                if field in checks_d:
                    val = _model_to_dict(checks_d[field])
                    val.setdefault("element_label", item_d.get("label") or item_d.get("element_label") or "")
                    val.setdefault("label", item_d.get("label") or item_d.get("element_label") or "")
                    val.setdefault("story", item_d.get("story", ""))
                    found.append(val)
                elif field in item_d:
                    val = _model_to_dict(item_d[field])
                    val.setdefault("element_label", item_d.get("label") or item_d.get("element_label") or "")
                    val.setdefault("label", item_d.get("label") or item_d.get("element_label") or "")
                    val.setdefault("story", item_d.get("story", ""))
                    found.append(val)
            return found
        return None

    def _to_check_result(self, check_def: Dict[str, Any], raw: Any, used_field: str) -> CheckResult:
        data = _model_to_dict(raw)
        status = str(data.get("status", "NO_DATA") or "NO_DATA")
        message = str(data.get("message", "") or data.get("description", "") or "")
        source = self._infer_source(data, message)
        evaluation_level = self._infer_evaluation_level(data, message, source, status)

        if status == "OK" and evaluation_level in {"SCREENING", "APPROXIMATE"}:
            status = "WARNING"
            message = (message + " | Approximate/screening OK downgraded to WARNING.").strip()

        check_type = str(check_def.get("id", "") or "")
        component = str(data.get("element_label") or data.get("label") or data.get("member") or "")
        story = _optional_string(data.get("story"))
        return CheckResult(
            id=self._result_id(check_type, component, story, used_field),
            component=component,
            check_type=check_type,
            status=status,
            demand=self._optional_float(data.get("value")),
            capacity=self._optional_float(data.get("limit")),
            ratio=self._optional_float(data.get("ratio")),
            evidence=self._evidence_mapping(data),
            messages=self._messages(message, data.get("action")),
            story=story,
            section=_optional_string(data.get("section")),
            unit=_optional_string(data.get("unit")),
            code_ref=str(check_def.get("tbdy_ref", "N/A") or "N/A"),
        )

    def _infer_source(self, data: Dict[str, Any], message: str) -> str:
        source = str(data.get("source", "") or "").strip()
        if source:
            return source

        for key in ("data_source", "rebar_source", "evaluation_source"):
            value = str(data.get(key, "") or "").strip()
            if value:
                return value

        match = _SOURCE_RE.search(message or "")
        if match:
            return match.group(1).strip()

        low = (message or "").lower()
        if "etabs" in low:
            return "etabs"
        if "provided" in low or "user" in low:
            return "provided_rebar"
        if "simplified" in low:
            return "simplified"
        if "screening" in low:
            return "screening_fallback"
        if "fallback" in low or "default" in low or "minimum" in low:
            return "fallback"
        return ""

    def _infer_evaluation_level(self, data: Dict[str, Any], message: str, source: str, status: str) -> str:
        raw = str(data.get("evaluation_level", "") or "").strip()
        if raw and raw != "NOT_EVALUATED":
            return raw

        if status == "NO_DATA":
            return "NO_DATA"
        if status == "ERROR":
            return "ERROR"

        blob = " ".join([message or "", source or "", str(data.get("note", "") or "")]).lower()

        if "etabs_design_result" in blob or source.lower().startswith("etabs") or "etabs:" in blob:
            return "ETABS_DESIGN_RESULT"
        if "screening" in blob or "screening_fallback" in blob:
            return "SCREENING"
        if "approx" in blob or "simplified" in blob:
            return "APPROXIMATE"
        if "fallback" in blob or "default" in blob or "minimum" in blob:
            return "SCREENING"
        if "provided" in blob or "user" in blob or "real_rebar" in blob or "design_level" in blob:
            # If the message explicitly says DESIGN_LEVEL could not be done, prefer SCREENING.
            if "design_level yapilamadi" in blob or "design_level yapılamadı" in blob or "cannot be design_level" in blob:
                return "SCREENING"
            return "DESIGN_LEVEL"
        return "NOT_EVALUATED"

    def _no_data_result(self, check_def: Dict[str, Any], message: str) -> CheckResult:
        check_type = str(check_def.get("id", "") or "")
        field = str(check_def.get("evaluation_field", "") or "")
        return CheckResult(
            id=self._result_id(check_type, "", None, field),
            component="",
            check_type=check_type,
            status="NO_DATA",
            demand=None,
            capacity=None,
            ratio=None,
            evidence={},
            messages=(message,),
            story=None,
            section=None,
            unit=None,
            code_ref=str(check_def.get("tbdy_ref", "N/A") or "N/A"),
        )

    def _error_result(self, check_def: Dict[str, Any], error: str) -> CheckResult:
        check_type = str(check_def.get("id", "") or "")
        field = str(check_def.get("evaluation_field", "") or "")
        return CheckResult(
            id=self._result_id(check_type, "", None, field),
            component="",
            check_type=check_type,
            status="ERROR",
            demand=None,
            capacity=None,
            ratio=None,
            evidence={},
            messages=(str(error),),
            story=None,
            section=None,
            unit=None,
            code_ref=str(check_def.get("tbdy_ref", "N/A") or "N/A"),
        )

    def _optional_float(self, value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None

    def _messages(self, *values: Any) -> tuple[str, ...]:
        messages = tuple(str(value).strip() for value in values if str(value or "").strip())
        return messages

    def _evidence_mapping(self, data: Dict[str, Any]) -> Mapping[str, object]:
        evidence = data.get("evidence")
        if isinstance(evidence, Mapping):
            return evidence
        return {}

    def _result_id(self, check_type: str, component: str, story: str | None, field: str) -> str:
        parts = [check_type, component, story or "", field]
        return ":".join(part for part in parts if part)


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
