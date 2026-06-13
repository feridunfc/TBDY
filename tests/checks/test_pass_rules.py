from tbdy_engine.checks.pass_rules import PassRuleEvaluator


def test_demand_over_capacity_semantics():
    ev = PassRuleEvaluator()
    assert ev.evaluate(ratio_type="demand_over_capacity", demand=9, capacity=10).status == "OK"
    assert ev.evaluate(ratio_type="demand_over_capacity", demand=10, capacity=10).status == "OK"
    assert ev.evaluate(ratio_type="demand_over_capacity", demand=11, capacity=10).status == "FAIL"


def test_value_over_maximum_ok_when_ratio_below_one():
    assert PassRuleEvaluator().evaluate(ratio_type="value_over_maximum", value=0.8, limit=1.0).status == "OK"


def test_value_over_maximum_ok_when_ratio_equal_one():
    assert PassRuleEvaluator().evaluate(ratio_type="value_over_maximum", value=1.0, limit=1.0).status == "OK"


def test_value_over_maximum_fail_when_ratio_above_one():
    assert PassRuleEvaluator().evaluate(ratio_type="value_over_maximum", value=1.2, limit=1.0).status == "FAIL"


def test_value_over_minimum_ok_when_ratio_above_one():
    assert PassRuleEvaluator().evaluate(ratio_type="value_over_minimum", value=1.2, minimum=1.0).status == "OK"


def test_value_over_minimum_ok_when_ratio_equal_one():
    assert PassRuleEvaluator().evaluate(ratio_type="value_over_minimum", value=1.0, minimum=1.0).status == "OK"


def test_value_over_minimum_fail_when_ratio_below_one():
    assert PassRuleEvaluator().evaluate(ratio_type="value_over_minimum", value=0.8, minimum=1.0).status == "FAIL"


def test_existing_lower_bound_rules():
    ev = PassRuleEvaluator()
    assert ev.evaluate(ratio_type="actual_over_minimum", actual=300, minimum=250).status == "OK"
    assert ev.evaluate(ratio_type="selected_over_required", selected=12, required=10).status == "OK"
    assert ev.evaluate(ratio_type="actual_over_required", actual=11, required=10).status == "OK"
    assert ev.evaluate(ratio_type="required_over_selected", required=10, selected=12).status == "OK"


def test_value_over_limit_is_deprecated_or_aliases_value_over_maximum():
    result = PassRuleEvaluator().evaluate(ratio_type="value_over_limit", value=1.2, limit=1.0)
    assert result.status == "FAIL"
    assert result.diagnostics
    assert any(d.code == "PASS_RULE_DEPRECATED" for d in result.diagnostics)


def test_unknown_pass_rule_never_silent_ok():
    result = PassRuleEvaluator().evaluate(pass_rule="not_known", ratio_type="value_over_maximum", value=1, limit=1)
    assert result.status == "NO_DATA"
    assert result.diagnostics


def test_unknown_ratio_type_never_silent_ok():
    result = PassRuleEvaluator().evaluate(ratio_type="not_known", value=1)
    assert result.status == "NO_DATA"
    assert result.diagnostics


def test_missing_value_returns_no_data():
    result = PassRuleEvaluator().evaluate(ratio_type="value_over_maximum", value=None, limit=1)
    assert result.status == "NO_DATA"


def test_missing_limit_returns_no_data():
    result = PassRuleEvaluator().evaluate(ratio_type="value_over_maximum", value=1.0)
    assert result.status == "NO_DATA"


def test_missing_capacity_returns_no_data():
    result = PassRuleEvaluator().evaluate(ratio_type="demand_over_capacity", demand=1.0, capacity=None)
    assert result.status == "NO_DATA"


def test_availability_and_boolean_semantics():
    ev = PassRuleEvaluator()
    assert ev.evaluate(ratio_type="availability", value=0).status == "OK"
    assert ev.evaluate(ratio_type="availability", value=None).status == "NO_DATA"
    assert ev.evaluate(ratio_type="boolean", value=True).status == "OK"
    assert ev.evaluate(ratio_type="boolean", value=False).status == "FAIL"
    assert ev.evaluate(ratio_type="boolean", value=None).status == "NO_DATA"


def test_invalid_numeric_never_silent_ok():
    result = PassRuleEvaluator().evaluate(ratio_type="value_over_maximum", value="not-a-number", limit=1.0)
    assert result.status == "NO_DATA"
