from tbdy_engine.design.columns.stability_action_basis import (
    TS500_ACTION_E,
    TS500_ACTION_G,
    TS500_ACTION_Q,
    TS500_ACTION_W,
    resolve_ts500_stability_load_inventory,
)
from tbdy_engine.providers.etabs_static_linear_case_provider import (
    EtabsLoadPatternTypeEvidence,
    EtabsStaticLinearCaseEvidence,
    EtabsStaticLinearLoadTermEvidence,
)
from tbdy_engine.providers.etabs_ts500_stability_action_provider import (
    promote_etabs_static_cases_to_ts500_stability_actions,
)


def _case(name: str, pattern_name: str, pattern_type: str, type_code: int = 1, scale: float = 1.0):
    pattern = EtabsLoadPatternTypeEvidence(
        name=pattern_name,
        type_code=type_code,
        type_name=pattern_type,
        raw_get_load_type="raw",
    )
    return EtabsStaticLinearCaseEvidence(
        name=name,
        loads=(
            EtabsStaticLinearLoadTermEvidence(
                index=0,
                load_type="Load",
                load_name=pattern_name,
                scale_factor=scale,
                load_pattern=pattern,
            ),
        ),
        raw_get_loads="raw",
    )


def test_roles_are_promoted_from_factual_pattern_type_not_case_name():
    result = promote_etabs_static_cases_to_ts500_stability_actions(
        (
            _case("LC_DL", "LC_DL", "DEAD", 1),
            _case("LC_WDL", "LC_WDL", "SUPER_DEAD", 2),
            _case("LC_DDL", "LC_DDL", "LIVE", 3),
            _case("LC_EQX", "LC_EQX", "QUAKE", 5),
            _case("MISLEADING_WIND_NAME", "P", "LIVE", 3),
        )
    )
    by_case = {item.case_name: item.action_role for item in result.promoted_sources}
    assert by_case["LC_DL"] == TS500_ACTION_G
    assert by_case["LC_WDL"] == TS500_ACTION_G
    assert by_case["LC_DDL"] == TS500_ACTION_Q
    assert by_case["LC_EQX"] == TS500_ACTION_E
    assert by_case["MISLEADING_WIND_NAME"] == TS500_ACTION_Q


def test_unmapped_or_nonatomic_cases_remain_visible_but_unpromoted():
    snow = _case("LC_S", "S", "SNOW", 7)
    scaled = _case("SCALED_G", "G", "DEAD", 1, scale=0.351)
    composite = EtabsStaticLinearCaseEvidence(
        name="EDZ",
        loads=(snow.loads[0], scaled.loads[0]),
        raw_get_loads="raw",
    )
    result = promote_etabs_static_cases_to_ts500_stability_actions((snow, scaled, composite))
    assert result.promoted_sources == ()
    reasons = {item.case_name: item.reason for item in result.excluded_cases}
    assert reasons["LC_S"] == "PATTERN_TYPE_NOT_PROMOTED:SNOW"
    assert reasons["SCALED_G"] == "NOT_UNIT_SCALE_ATOMIC_CASE"
    assert reasons["EDZ"] == "NOT_ATOMIC_SINGLE_LOAD_TERM"


def test_live_proven_inventory_is_missing_wind_and_keeps_direction_separate():
    promotion = promote_etabs_static_cases_to_ts500_stability_actions(
        (
            _case("A", "G", "DEAD", 1),
            _case("B", "SD", "SUPER_DEAD", 2),
            _case("C", "Q", "LIVE", 3),
            _case("EX", "EX", "QUAKE", 5),
            _case("EY", "EY", "QUAKE", 5),
        )
    )
    inventory = resolve_ts500_stability_load_inventory(promotion.promoted_sources)
    assert inventory.status == "BLOCKED_TS500_STABILITY_ACTION_INVENTORY"
    assert inventory.gqe.missing_roles == ()
    assert inventory.gqe.direction_binding_required_roles == (TS500_ACTION_E,)
    assert inventory.gqe.status == "BLOCKED_TS500_STABILITY_DIRECTION_BINDING"
    assert inventory.gqw.missing_roles == (TS500_ACTION_W,)
    assert inventory.gqw.status == "BLOCKED_TS500_STABILITY_ACTION_INVENTORY"
    assert inventory.gqe.candidate_case_names_by_role[TS500_ACTION_G] == ("A", "B")
    assert inventory.gqe.candidate_case_names_by_role[TS500_ACTION_Q] == ("C",)


def test_wind_presence_completes_inventory_but_does_not_auto_bind_direction():
    promotion = promote_etabs_static_cases_to_ts500_stability_actions(
        (
            _case("G", "G", "DEAD", 1),
            _case("Q", "Q", "LIVE", 3),
            _case("E", "E", "QUAKE", 5),
            _case("W", "W", "WIND", 6),
        )
    )
    inventory = resolve_ts500_stability_load_inventory(promotion.promoted_sources)
    assert inventory.status == "PROVEN_TS500_STABILITY_ACTION_INVENTORY"
    assert inventory.gqe.direction_binding_required_roles == (TS500_ACTION_E,)
    assert inventory.gqw.direction_binding_required_roles == (TS500_ACTION_W,)
