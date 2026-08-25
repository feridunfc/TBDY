from tbdy_engine.design.columns.column_design_demand_engine import (
    ColumnComboDefinition,
    evaluate_column_design_demands,
)
from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState


COMP = "+0.00:C2:236"


def _state(case, case_type, end, station, n, m2, m3, step=None):
    return ColumnDemandState(
        state_id=f"{case}:{end}:{step}",
        component_id=COMP,
        output_case=case,
        case_type=case_type,
        step_type=step,
        step_number=None,
        station_m=station,
        end_tag=end,
        nd_compression_n=n,
        m2_nmm=m2,
        m3_nmm=m3,
        source_identity=f"src:{case}:{end}:{step}",
    )


def test_engine_promotes_supported_combo_independent_of_name():
    case_rows = (
        _state("G", "LinStatic", "I_END", 0.0, 1000.0, 10.0, 20.0),
        _state("RSX", "LinRespSpec", "I_END", 0.0, -100.0, 30.0, 40.0, "Max"),
        _state("G", "LinStatic", "J_END", 4.0, 900.0, -10.0, -20.0),
        _state("RSX", "LinRespSpec", "J_END", 4.0, -80.0, 20.0, 25.0, "Max"),
    )
    result = evaluate_column_design_demands(
        component_id=COMP,
        definitions=(
            ColumnComboDefinition(
                name="ULS_17",
                combo_type="LINEAR_ADD",
                constituents=(ComboPatternConstituent("G", 1.0), ComboPatternConstituent("RSX", 1.0)),
            ),
        ),
        case_demands=case_rows,
    )
    assert result.status == "PROVEN_COLUMN_DESIGN_DEMAND_SCOPE"
    assert result.combination_scope_resolved
    assert len(result.promoted_states) == 16
    assert result.blocked_combo_names == ()
    assert result.combo_results[0].classification.supported


def test_one_unsupported_combo_blocks_full_scope_and_is_not_promoted():
    case_rows = (
        _state("D", "LinStatic", "I_END", 0.0, 1000.0, 10.0, 20.0),
        _state("D", "LinStatic", "J_END", 4.0, 900.0, -10.0, -20.0),
        _state("NL", "NonlinearStatic", "I_END", 0.0, 100.0, 2.0, 3.0),
        _state("NL", "NonlinearStatic", "J_END", 4.0, 80.0, 1.0, 2.0),
    )
    result = evaluate_column_design_demands(
        component_id=COMP,
        definitions=(
            ColumnComboDefinition(
                name="GRAV",
                combo_type="LINEAR_ADD",
                constituents=(ComboPatternConstituent("D", 1.4),),
            ),
            ColumnComboDefinition(
                name="SEIS_LOOKING_NAME",
                combo_type="LINEAR_ADD",
                constituents=(ComboPatternConstituent("NL", 1.0),),
            ),
        ),
        case_demands=case_rows,
    )
    assert result.status == "BLOCKED_COLUMN_DESIGN_DEMAND_SCOPE"
    assert result.blocked_combo_names == ("SEIS_LOOKING_NAME",)
    assert len(result.promoted_states) == 2
    assert result.combo_results[1].build is None


def test_nested_combo_is_reported_blocked_not_raised_by_factual_definition_layer():
    case_rows = (
        _state("D", "LinStatic", "I_END", 0.0, 1000.0, 10.0, 20.0),
        _state("D", "LinStatic", "J_END", 4.0, 900.0, -10.0, -20.0),
    )
    result = evaluate_column_design_demands(
        component_id=COMP,
        definitions=(
            ColumnComboDefinition(
                name="NESTED",
                combo_type="LINEAR_ADD",
                constituents=(ComboPatternConstituent("SUBCOMBO", 1.0, cname_type="LOAD_COMBO"),),
            ),
        ),
        case_demands=case_rows,
    )
    assert result.status == "BLOCKED_COLUMN_DESIGN_DEMAND_SCOPE"
    assert result.blocked_combo_names == ("NESTED",)
    assert result.combo_results[0].classification.pattern == "UNSUPPORTED_COMBO_PATTERN"
    assert result.combo_results[0].build is None
