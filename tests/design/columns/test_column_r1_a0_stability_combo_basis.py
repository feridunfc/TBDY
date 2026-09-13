from tbdy_engine.design.columns.stability_action_basis import (
    StabilityActionSource,
    TS500_ACTION_E,
    TS500_ACTION_G,
    TS500_ACTION_Q,
    TS500_ACTION_W,
    TS500_LOAD_BASIS_GQE,
    TS500_LOAD_BASIS_GQW,
)
from tbdy_engine.design.columns.stability_combo_basis import (
    FlattenedLinearCombo,
    resolve_existing_ts500_stability_combos,
)


def _source(case, role, pattern_type):
    return StabilityActionSource(
        case_name=case,
        pattern_name=f"PAT_{case}",
        source_pattern_type=pattern_type,
        action_role=role,
        case_scale_factor=1.0,
        source_refs=(f"fact:{case}",),
    )


def test_exact_existing_combos_are_matched_by_role_and_coefficients_not_names():
    sources = (
        _source("D1", TS500_ACTION_G, "DEAD"),
        _source("L1", TS500_ACTION_Q, "LIVE"),
        _source("EQ_A", TS500_ACTION_E, "QUAKE"),
        _source("W_A", TS500_ACTION_W, "WIND"),
    )
    combos = (
        FlattenedLinearCombo(
            name="opaque-17",
            constituents=(("D1", 1.0), ("L1", 1.0), ("EQ_A", -1.0)),
            source_refs=("combo:opaque-17",),
        ),
        FlattenedLinearCombo(
            name="opaque-23",
            constituents=(("D1", 1.0), ("L1", 1.3), ("W_A", 1.3)),
            source_refs=("combo:opaque-23",),
        ),
    )
    result = resolve_existing_ts500_stability_combos(combos, sources)
    assert result.both_bases_present
    assert result.gqe_candidates[0].load_basis == TS500_LOAD_BASIS_GQE
    assert result.gqe_candidates[0].horizontal_scale_factor == -1.0
    assert result.gqw_candidates[0].load_basis == TS500_LOAD_BASIS_GQW
    assert result.gqw_candidates[0].horizontal_scale_factor == 1.3


def test_orthogonal_mixed_horizontal_combo_is_not_promoted():
    sources = (
        _source("D1", TS500_ACTION_G, "DEAD"),
        _source("L1", TS500_ACTION_Q, "LIVE"),
        _source("EX", TS500_ACTION_E, "QUAKE"),
        _source("EY", TS500_ACTION_E, "QUAKE"),
        _source("W", TS500_ACTION_W, "WIND"),
    )
    combos = (
        FlattenedLinearCombo(
            name="mixed",
            constituents=(("D1", 1.0), ("L1", 1.0), ("EX", 1.0), ("EY", 0.3)),
            source_refs=("combo:mixed",),
        ),
        FlattenedLinearCombo(
            name="wind",
            constituents=(("D1", 1.0), ("L1", 1.3), ("W", 1.3)),
            source_refs=("combo:wind",),
        ),
    )
    result = resolve_existing_ts500_stability_combos(combos, sources)
    assert result.gqe_candidates == ()
    assert len(result.gqw_candidates) == 1
    assert result.status == "BLOCKED_TS500_STABILITY_COMBO_SCOPE"
