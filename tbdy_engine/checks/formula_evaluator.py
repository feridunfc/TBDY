"""Tiny safe arithmetic formula evaluator for C6.

This evaluator intentionally has no ETABS/provider/table access and never uses
Python eval(). It accepts only arithmetic over provided variables and min/max/abs.
"""
from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from typing import Any, Mapping

from tbdy_engine.checks.diagnostics import CheckDiagnostic, CheckDiagnosticCode, CheckDiagnosticSeverity


_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_ALLOWED_FUNCS = {"min": min, "max": max, "abs": abs}
_FORBIDDEN_NAMES = {"eval", "exec", "open", "__import__", "import"}


@dataclass(frozen=True, slots=True)
class FormulaEvaluation:
    value: float | int | None
    diagnostics: tuple[CheckDiagnostic, ...] = ()


class SafeFormulaEvaluator:
    def evaluate(self, expression: str, variables: Mapping[str, Any] | None = None) -> FormulaEvaluation:
        try:
            tree = ast.parse(expression, mode="eval")
            value = self._eval(tree.body, dict(variables or {}))
            return FormulaEvaluation(value=value)
        except Exception as exc:
            return FormulaEvaluation(
                value=None,
                diagnostics=(
                    CheckDiagnostic(
                        CheckDiagnosticSeverity.ERROR,
                        CheckDiagnosticCode.FORMULA_ERROR,
                        f"Formula evaluation rejected: {exc}",
                    ),
                ),
            )

    def _eval(self, node: ast.AST, variables: Mapping[str, Any]) -> float | int:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in _FORBIDDEN_NAMES or node.id.startswith("__"):
                raise ValueError(f"Forbidden name: {node.id}")
            if node.id not in variables:
                raise ValueError(f"Unknown variable: {node.id}")
            value = variables[node.id]
            if not isinstance(value, (int, float)):
                raise ValueError(f"Variable is not numeric: {node.id}")
            return value
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_BINOPS:
                raise ValueError(f"Forbidden operator: {op_type.__name__}")
            return _ALLOWED_BINOPS[op_type](self._eval(node.left, variables), self._eval(node.right, variables))
        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_UNARY:
                raise ValueError(f"Forbidden unary operator: {op_type.__name__}")
            return _ALLOWED_UNARY[op_type](self._eval(node.operand, variables))
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
                raise ValueError("Only min, max, and abs calls are allowed")
            if node.keywords:
                raise ValueError("Keyword arguments are not allowed")
            args = [self._eval(arg, variables) for arg in node.args]
            return _ALLOWED_FUNCS[node.func.id](*args)
        raise ValueError(f"Forbidden expression node: {type(node).__name__}")


__all__ = ["FormulaEvaluation", "SafeFormulaEvaluator"]
