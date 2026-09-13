from __future__ import annotations

import pytest

from tbdy_engine.etabs.oapi.analysis_execution import LoadCaseTypeRuntimeFact
from tbdy_engine.providers.etabs_column_combo_case_type_provider import (
    EtabsColumnComboCaseTypeError,
    project_b5_column_combo_case_types,
)


def _fact(name: str, case_type: int, ret: int = 0) -> LoadCaseTypeRuntimeFact:
    return LoadCaseTypeRuntimeFact(
        case_name=name,
        case_type=case_type,
        sub_type=0,
        design_type=0,
        design_type_option=0,
        runtime_auto_slot_value=0,
        return_code=ret,
    )


def test_projects_only_exact_supported_b5_case_types() -> None:
    population = project_b5_column_combo_case_types(
        (_fact("G", 1), _fact("EX", 4)),
        required_case_names=("G", "EX"),
        analysis_result_identity_ref="analysis-result:sha256:" + "1" * 64,
        execution_proof_ref="analysis-execution-proof:test",
    )
    assert dict(population.case_types) == {"EX": "LinRespSpec", "G": "LinStatic"}
    assert population.status == "PROVEN_B5_COLUMN_COMBO_CASE_TYPES"
    assert _fact("G", 1).evidence_ref in population.source_refs


@pytest.mark.parametrize(
    ("facts", "required", "message"),
    [
        ((_fact("G", 1),), ("G", "EX"), "missing required"),
        ((_fact("G", 2),), ("G",), "unsupported CSI"),
        ((_fact("G", 1, ret=1),), ("G",), "nonzero return code"),
    ],
)
def test_fails_closed_for_incomplete_or_unqualified_case_type_facts(facts, required, message) -> None:
    with pytest.raises(EtabsColumnComboCaseTypeError, match=message):
        project_b5_column_combo_case_types(
            facts,
            required_case_names=required,
            analysis_result_identity_ref="analysis-result:test",
            execution_proof_ref="analysis-execution-proof:test",
        )
