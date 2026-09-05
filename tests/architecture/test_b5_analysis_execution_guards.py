from __future__ import annotations

import ast
import inspect
from pathlib import Path

import tbdy_engine.integration.etabs_analysis_execution as b5


ROOT = Path(__file__).resolve().parents[2]
TBDY = ROOT / "tbdy_engine"
GATEWAY = ROOT / "packages" / "etabs_gateway" / "src" / "etabs_gateway"
B5_OAPI = TBDY / "etabs" / "oapi" / "analysis_execution.py"
B5_INTEGRATION = TBDY / "integration" / "etabs_analysis_execution.py"
B4B_INTEGRATION = TBDY / "integration" / "etabs_analysis_state_mutation.py"
LINEAGE = TBDY / "integration" / "etabs_analysis_lineage.py"
RESULT_PROVIDER = TBDY / "providers" / "etabs_column_force_result_population_provider.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_text(path), filename=str(path))


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _production_files() -> tuple[Path, ...]:
    roots = (TBDY, GATEWAY)
    return tuple(sorted(path for root in roots for path in root.rglob("*.py")))


def _call_sites(final_name: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in _production_files():
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.Call):
                continue
            dotted = _dotted(node.func)
            if dotted.rsplit(".", 1)[-1] == final_name:
                found.append((path.relative_to(ROOT).as_posix(), dotted))
    return found


def test_runanalysis_has_exactly_one_factual_callsite_and_one_semantic_owner():
    assert _call_sites("RunAnalysis") == [
        ("tbdy_engine/etabs/oapi/analysis_execution.py", "model_api.Analyze.RunAnalysis")
    ]
    semantic_calls = [
        _dotted(node.func).rsplit(".", 1)[-1]
        for node in ast.walk(_tree(B5_INTEGRATION))
        if isinstance(node, ast.Call)
    ]
    assert semantic_calls.count("run_analysis_from_session") == 1
    assert "RunAnalysis" not in semantic_calls
    assert "RunAnalysis(" not in _text(B4B_INTEGRATION)


def test_b5_does_not_introduce_design_execution_or_lock_unit_save_mutation():
    assert _call_sites("StartDesign") == []
    b5_sources = _text(B5_OAPI) + "\n" + _text(B5_INTEGRATION)
    for forbidden in (
        "SetModelIsLocked",
        "SetPresentUnits",
        "SetPresentUnits_2",
        "StartDesign",
        ".File.Save",
        "SaveAs",
    ):
        assert forbidden not in b5_sources


def test_run_scope_and_result_deletion_calls_are_confined_to_b5_factual_oapi():
    for method in ("SetRunCaseFlag", "DeleteResults"):
        sites = _call_sites(method)
        assert sites
        assert {path for path, _ in sites} == {
            "tbdy_engine/etabs/oapi/analysis_execution.py"
        }


def test_b5_factual_oapi_reuses_b4t_and_semantic_owner_never_imports_b4t():
    oapi = _text(B5_OAPI)
    semantic = _text(B5_INTEGRATION)
    assert "etabs_gateway.mutation_transport" in oapi
    assert "_execute_bounded_model_mutation" in oapi
    assert "_B4T_MUTATION_TRANSPORT_KEY" in oapi
    assert "etabs_gateway.mutation_transport" not in semantic
    assert "_execute_bounded_model_mutation" not in semantic


def test_b1_private_factories_remain_private_and_narrow_issuer_has_one_consumer():
    private_symbols = {
        "_EXECUTION_PROOF_FACTORY_TOKEN",
        "_QUALIFICATION_FACTORY_TOKEN",
        "_VerifiedAnalysisExecutionProof",
        "_build_qualified_analysis_lineage",
    }
    offenders: dict[str, set[str]] = {}
    for path in _production_files():
        if path == LINEAGE:
            continue
        used = private_symbols.intersection(_text(path))
        if used:
            offenders[path.relative_to(ROOT).as_posix()] = used
    assert offenders == {}

    issuer = "issue_qualified_analysis_lineage_from_controlled_execution"
    assert _call_sites(issuer) == [
        (
            "tbdy_engine/integration/etabs_analysis_execution.py",
            issuer,
        )
    ]
    assert issuer in _text(LINEAGE)


def test_b5_public_execution_input_contains_intent_not_caller_truth_authority():
    params = inspect.signature(b5.execute_controlled_analysis).parameters
    assert tuple(params) == (
        "context",
        "owned_scratch",
        "established_state",
        "requested_case_names",
        "timeout_seconds",
    )
    forbidden = {
        "analysis_state_identity",
        "analysis_result_identity",
        "analysis_generation_ref",
        "generation_ref",
        "attempt_ref",
        "qualification",
        "result_population",
        "expected_column_unique_names",
        "evidence_epoch",
        "model_fingerprint",
    }
    assert forbidden.isdisjoint(params)


def test_b5_requires_concrete_b4b_positive_result_not_naked_identity():
    source = _text(B5_INTEGRATION)
    assert "isinstance(established_state, AnalysisStateMutationResult)" in source
    assert "a naked AnalysisStateIdentity is not accepted" in source


def test_b5_freezes_case_and_required_population_scope_before_run():
    tree = _tree(B5_INTEGRATION)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "execute_controlled_analysis"
    )
    calls = [
        _dotted(node.func).rsplit(".", 1)[-1]
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
    ]
    assert calls.count("run_analysis_from_session") == 1
    assert "AnalysisExecutionScope.from_case_names" in {
        _dotted(node.func)
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
    }
    source = ast.get_source_segment(_text(B5_INTEGRATION), function) or ""
    assert "successful_subset" not in source
    assert "result_scope_refs=scope.result_scope_refs" in source
    assert "capture_column_force_population_expectation_from_session" in source
    assert source.index("capture_column_force_population_expectation_from_session") < source.index(
        "run_analysis_from_session"
    )
    assert source.index("capture_column_force_result_population_from_session") > source.index(
        "run_analysis_from_session"
    )


def test_b5_stale_result_policy_is_explicit_all_case_delete_before_run():
    source = _text(B5_INTEGRATION)
    delete_pos = source.index("delete_analysis_results_from_session(")
    run_pos = source.index("run_analysis_from_session(")
    assert delete_pos < run_pos
    assert "all_cases=True" in source[delete_pos:run_pos]
    assert "CSI_ANALYSIS_STATUS_NOT_RUN" in source[delete_pos:run_pos]


def test_b5_result_population_provider_is_session_bound_and_no_raw_capability_escapes():
    provider = _text(RESULT_PROVIDER)
    semantic = _text(B5_INTEGRATION)
    assert "fetch_display_table_from_session" in provider
    assert "fetch_display_table_for_output_from_session" in provider
    assert "EtabsVerifiedSession" in provider
    assert "sap_model" not in provider
    assert "database_tables" not in provider
    assert "SapModel" not in semantic
    assert "DatabaseTables" not in semantic

    tree = _tree(RESULT_PROVIDER)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            arg_names = {
                arg.arg
                for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            }
            assert "sap_model" not in arg_names
            assert "database_tables" not in arg_names
            assert "rows" not in arg_names
            assert "fetcher" not in arg_names
            assert "callback" not in arg_names


def test_b5_result_scope_is_bound_to_exact_required_population_contract():
    source = _text(B5_INTEGRATION)
    assert "COLUMN_FORCE_RESULT_POPULATION_CONTRACT" in source
    assert "TABLE_COLUMN_FORCES" in source
    assert "result_population_expectation" in source
    assert "result_populations" in source
    assert "result_population_refs" in source


def test_b5_oapi_exports_no_raw_model_or_generic_callback_capability():
    tree = _tree(B5_OAPI)
    exported: tuple[str, ...] = ()
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
        ):
            exported = tuple(ast.literal_eval(node.value))
    assert exported
    for forbidden in (
        "SapModel",
        "model_api",
        "application",
        "_gateway_session",
        "_execute_bounded_model_mutation",
    ):
        assert forbidden not in exported
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            arg_names = {
                arg.arg
                for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            }
            assert "callback" not in arg_names
            assert "function" not in arg_names
            assert "model_api" not in arg_names
            assert "sap_model" not in arg_names
