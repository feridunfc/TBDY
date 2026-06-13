"""Safe pass-rule evaluator for C6/C6.1 minimal CheckEngine.

C6.1 makes upper-bound and lower-bound ratio semantics explicit.
No rule is allowed to silently produce OK when its inputs or semantics are
unknown.  The deprecated ``value_over_limit`` name is kept only as a
backward-compatible alias of ``value_over_maximum``.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from tbdy_engine.checks.diagnostics import CheckDiagnostic, CheckDiagnosticCode, CheckDiagnosticSeverity
from tbdy_engine.checks.result import CheckStatus


@dataclass(frozen=True, slots=True)
class PassRuleEvaluation:
    status: CheckStatus
    ratio: float | None
    messages: tuple[str, ...]
    diagnostics: tuple[CheckDiagnostic, ...]


_UPPER_BOUND_RULES = {"demand_over_capacity", "required_over_selected", "value_over_maximum", "value_over_limit"}
_LOWER_BOUND_RULES = {"actual_over_minimum", "selected_over_required", "value_over_minimum", "actual_over_required"}
_EXISTENCE_RULES = {"availability", "boolean"}
_KNOWN_RULES = _UPPER_BOUND_RULES | _LOWER_BOUND_RULES | _EXISTENCE_RULES
_DEPRECATED_ALIASES = {"value_over_limit": "value_over_maximum"}


class PassRuleEvaluator:
    """Evaluate explicit pass-rule semantics for the minimal CheckEngine.

    Supported upper-bound rules pass when ``ratio <= 1.0``. Supported
    lower-bound rules pass when ``ratio >= 1.0``. Missing/invalid inputs,
    unknown pass rules, and unknown ratio types are NO_DATA with diagnostics.
    """

    def evaluate(
        self,
        *,
        ratio_type: str | None = None,
        pass_rule: str | None = None,
        value: Any = None,
        ratio: float | None = None,
        demand: float | None = None,
        capacity: float | None = None,
        actual: float | None = None,
        minimum: float | None = None,
        maximum: float | None = None,
        selected: float | None = None,
        required: float | None = None,
        limit: float | None = None,
    ) -> PassRuleEvaluation:
        raw_rule = pass_rule or ratio_type
        if raw_rule is None:
            return self._no_data("Missing pass_rule/ratio_type", CheckDiagnosticCode.UNKNOWN_RATIO_TYPE)
        if pass_rule is not None and pass_rule not in _KNOWN_RULES:
            return self._no_data(f"Unknown pass_rule: {pass_rule}", CheckDiagnosticCode.UNKNOWN_PASS_RULE)
        if ratio_type is not None and ratio_type not in _KNOWN_RULES:
            return self._no_data(f"Unknown ratio_type: {ratio_type}", CheckDiagnosticCode.UNKNOWN_RATIO_TYPE)
        if raw_rule not in _KNOWN_RULES:
            return self._no_data(f"Unknown pass_rule/ratio_type: {raw_rule}", CheckDiagnosticCode.UNKNOWN_PASS_RULE)

        rule = _DEPRECATED_ALIASES.get(raw_rule, raw_rule)
        messages: list[str] = []
        diagnostics: list[CheckDiagnostic] = []
        if raw_rule in _DEPRECATED_ALIASES:
            message = "value_over_limit is deprecated; use value_over_maximum for upper-bound checks"
            messages.append(message)
            diagnostics.append(
                CheckDiagnostic(
                    CheckDiagnosticSeverity.WARNING,
                    CheckDiagnosticCode.PASS_RULE_DEPRECATED,
                    message,
                    {"deprecated": raw_rule, "replacement": rule},
                )
            )

        if rule == "availability":
            return PassRuleEvaluation(CheckStatus.OK if value is not None else CheckStatus.NO_DATA, None, tuple(messages), tuple(diagnostics))
        if rule == "boolean":
            if value is None:
                return self._no_data("Missing boolean value", CheckDiagnosticCode.FEATURE_MISSING, messages, diagnostics)
            return PassRuleEvaluation(CheckStatus.OK if bool(value) else CheckStatus.FAIL, None, tuple(messages), tuple(diagnostics))

        try:
            computed = self._compute_ratio(
                rule=rule,
                value=value,
                ratio=ratio,
                demand=demand,
                capacity=capacity,
                actual=actual,
                minimum=minimum,
                maximum=maximum,
                selected=selected,
                required=required,
                limit=limit,
            )
        except Exception as exc:
            return self._no_data(f"Pass rule cannot be evaluated: {exc}", CheckDiagnosticCode.FEATURE_MISSING, messages, diagnostics)

        if computed is None or not isfinite(computed):
            return self._no_data("Computed ratio is missing or invalid", CheckDiagnosticCode.FEATURE_MISSING, messages, diagnostics)

        ok = self._passes(rule, computed)
        return PassRuleEvaluation(CheckStatus.OK if ok else CheckStatus.FAIL, computed, tuple(messages), tuple(diagnostics))

    def _no_data(
        self,
        message: str,
        code: CheckDiagnosticCode,
        messages: list[str] | None = None,
        diagnostics: list[CheckDiagnostic] | None = None,
    ) -> PassRuleEvaluation:
        msg = list(messages or []) + [message]
        diag = list(diagnostics or []) + [CheckDiagnostic(CheckDiagnosticSeverity.ERROR, code, message)]
        return PassRuleEvaluation(CheckStatus.NO_DATA, None, tuple(msg), tuple(diag))

    @staticmethod
    def _to_float(name: str, value: Any) -> float:
        if value is None:
            raise ValueError(f"Missing {name}")
        number = float(value)
        if not isfinite(number):
            raise ValueError(f"Invalid numeric value for {name}")
        return number

    def _safe_div(self, numerator_name: str, numerator: Any, denominator_name: str, denominator: Any) -> float:
        n = self._to_float(numerator_name, numerator)
        d = self._to_float(denominator_name, denominator)
        if d == 0:
            raise ZeroDivisionError(f"{denominator_name} denominator is zero")
        return n / d

    def _compute_ratio(self, *, rule: str, value: Any, ratio: float | None, **kwargs: Any) -> float | None:
        if ratio is not None:
            return self._to_float("ratio", ratio)
        if rule == "demand_over_capacity":
            return self._safe_div("demand", kwargs.get("demand"), "capacity", kwargs.get("capacity"))
        if rule == "actual_over_minimum":
            return self._safe_div("actual", kwargs.get("actual"), "minimum", kwargs.get("minimum"))
        if rule == "selected_over_required":
            return self._safe_div("selected", kwargs.get("selected"), "required", kwargs.get("required"))
        if rule == "required_over_selected":
            return self._safe_div("required", kwargs.get("required"), "selected", kwargs.get("selected"))
        if rule == "value_over_maximum":
            maximum = kwargs.get("maximum") if kwargs.get("maximum") is not None else kwargs.get("limit")
            return self._safe_div("value", value, "maximum", maximum)
        if rule == "value_over_minimum":
            minimum = kwargs.get("minimum") if kwargs.get("minimum") is not None else kwargs.get("limit")
            return self._safe_div("value", value, "minimum", minimum)
        if rule == "actual_over_required":
            return self._safe_div("actual", kwargs.get("actual"), "required", kwargs.get("required"))
        raise ValueError(f"Unknown pass_rule/ratio_type: {rule}")

    @staticmethod
    def _passes(rule: str, ratio: float | None) -> bool:
        if ratio is None:
            return False
        if rule in {"demand_over_capacity", "required_over_selected", "value_over_maximum"}:
            return ratio <= 1.0
        if rule in {"actual_over_minimum", "selected_over_required", "value_over_minimum", "actual_over_required"}:
            return ratio >= 1.0
        raise ValueError(f"Unknown pass_rule/ratio_type: {rule}")


__all__ = ["PassRuleEvaluation", "PassRuleEvaluator"]
