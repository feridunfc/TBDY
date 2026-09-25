import pytest

from tbdy_engine.design.columns.stability_combo_basis import StabilityComboCandidate
from tbdy_engine.design.columns.stability_output_state import (
    CSI_LINEAR_ADD_SINGLE_VALUE_STEP_TYPE,
    SIGNED_LINEAR_ADD_STATE,
    StabilityActionDirectionBinding,
    StabilityOutputStateError,
    qualify_signed_linear_add_stability_output,
)


def _candidate(horizontal_case="EX"):
    return StabilityComboCandidate(
        combo_name="COMB_GQE_X",
        load_basis="TS500_FD_1.0G_1.0Q_1.0E",
        horizontal_action_role="E",
        horizontal_case_name=horizontal_case,
        horizontal_scale_factor=1.0,
        role_coefficients=(("E", 1.0), ("G", 1.0), ("Q", 1.0)),
        constituent_case_names=("G", "Q", horizontal_case),
        source_refs=("combo-definition:COMB_GQE_X", "case-role:EX=E"),
    )


def test_signed_linear_add_binding_preserves_direction_and_b5_identity():
    result = qualify_signed_linear_add_stability_output(
        _candidate(),
        direction_binding=StabilityActionDirectionBinding(
            case_name="EX",
            global_direction="X",
            source_refs=("factual-direction:EX:X",),
        ),
        analysis_result_ref="analysis-result:1",
        execution_proof_ref="execution-proof:1",
    )
    assert result.output_name == "COMB_GQE_X"
    assert result.output_kind == "combo"
    assert result.global_direction == "X"
    assert result.combination_method == "LINEAR_ADD"
    assert result.state_semantics == SIGNED_LINEAR_ADD_STATE
    assert (
        result.required_step_type
        == CSI_LINEAR_ADD_SINGLE_VALUE_STEP_TYPE
        == "Single Value"
    )
    assert result.required_step_number == 0.0
    assert result.analysis_result_ref == "analysis-result:1"
    assert result.execution_proof_ref == "execution-proof:1"
    assert result.binding_ref.startswith("stability-output-state:sha256:")


def test_direction_binding_must_match_horizontal_case():
    with pytest.raises(StabilityOutputStateError, match="does not match"):
        qualify_signed_linear_add_stability_output(
            _candidate("EX"),
            direction_binding=StabilityActionDirectionBinding(
                case_name="EY",
                global_direction="Y",
                source_refs=("factual-direction:EY:Y",),
            ),
            analysis_result_ref="analysis-result:1",
            execution_proof_ref="execution-proof:1",
        )


def test_direction_binding_rejects_non_xy_direction():
    with pytest.raises(StabilityOutputStateError, match="X or Y"):
        StabilityActionDirectionBinding(
            case_name="EX",
            global_direction="RZ",
            source_refs=("factual-direction:EX:RZ",),
        )
