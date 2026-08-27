"""C6 minimal check layer.

This package intentionally exposes only canonical C6 DTO/evaluator/engine classes.
Legacy beam, runner_v2, runtime, archx, provider, and ETABS modules are not imported.

``MinimalCheckEngine`` is loaded lazily so importing the canonical ``CheckResult``
DTO cannot recurse through coverage/findings/analysis-basis back into the F0
regulatory contracts while those contracts are still initializing.  The public
``from tbdy_engine.checks import MinimalCheckEngine`` API is preserved.
"""
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.checks.pass_rules import PassRuleEvaluator, PassRuleEvaluation
from tbdy_engine.checks.formula_evaluator import SafeFormulaEvaluator, FormulaEvaluation


def __getattr__(name: str):
    if name == "MinimalCheckEngine":
        from tbdy_engine.checks.engine import MinimalCheckEngine

        return MinimalCheckEngine
    raise AttributeError(name)


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
