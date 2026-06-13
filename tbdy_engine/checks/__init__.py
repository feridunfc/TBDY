"""C6 minimal check layer.

This package intentionally exposes only canonical C6 DTO/evaluator/engine classes.
Legacy beam, runner_v2, runtime, archx, provider, and ETABS modules are not imported.
"""
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.checks.pass_rules import PassRuleEvaluator, PassRuleEvaluation
from tbdy_engine.checks.formula_evaluator import SafeFormulaEvaluator, FormulaEvaluation
from tbdy_engine.checks.engine import MinimalCheckEngine

__all__ = [
    "CheckResult",
    "CheckStatus",
    "EvaluationLevel",
    "PassRuleEvaluator",
    "PassRuleEvaluation",
    "SafeFormulaEvaluator",
    "FormulaEvaluation",
    "MinimalCheckEngine",
]
