from tbdy_engine.checks.formula_evaluator import SafeFormulaEvaluator


def test_safe_formula_allowed_arithmetic():
    ev = SafeFormulaEvaluator()
    assert ev.evaluate("a + b * 2", {"a": 3, "b": 4}).value == 11
    assert ev.evaluate("max(a, b) - min(a, b) + abs(-2)", {"a": 3, "b": 4}).value == 3


def test_safe_formula_blocks_python_execution():
    ev = SafeFormulaEvaluator()
    assert ev.evaluate("__import__('os').system('echo bad')", {}).value is None
    assert ev.evaluate("open('x')", {}).value is None
    assert ev.evaluate("a.__class__", {"a": 1}).value is None
