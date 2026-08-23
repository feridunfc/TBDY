from pathlib import Path
import ast


# 1) Move all regulatory formal-applicability decisions into the reviewed
# structural_system implementation module.
path = Path("tbdy_engine/regulatory/structural_system.py")
text = path.read_text()

old = '''@dataclass(frozen=True, slots=True)
class DirectionalApplicabilityInput:
    enabled: bool = True


def _applies(value: DirectionalApplicabilityInput) -> ApplicabilityState:
    if not isinstance(value, DirectionalApplicabilityInput):
        raise TypeError("applicability requires DirectionalApplicabilityInput")
    return (
        ApplicabilityState.APPLIES
        if value.enabled
        else ApplicabilityState.PROVEN_NOT_APPLICABLE
    )
'''
new = '''@dataclass(frozen=True, slots=True)
class DirectionalApplicabilityInput:
    enabled: bool = True


def _applies(value: DirectionalApplicabilityInput) -> ApplicabilityState:
    if not isinstance(value, DirectionalApplicabilityInput):
        raise TypeError("applicability requires DirectionalApplicabilityInput")
    return (
        ApplicabilityState.APPLIES
        if value.enabled
        else ApplicabilityState.PROVEN_NOT_APPLICABLE
    )


def requires_a16_special_context(table_4_1_row: str) -> bool:
    """Reviewed Table 4.1 scope predicate used by composition only."""
    return table_4_1_policy(table_4_1_row).row == "A16"


@dataclass(frozen=True, slots=True)
class BysEligibilityFormalApplicabilityInput:
    table_4_1_row: str

    def __post_init__(self) -> None:
        table_4_1_policy(self.table_4_1_row)


@dataclass(frozen=True, slots=True)
class Dts4341FormalApplicabilityInput:
    table_4_1_row: str

    def __post_init__(self) -> None:
        table_4_1_policy(self.table_4_1_row)


@dataclass(frozen=True, slots=True)
class A31FormalApplicabilityInput:
    table_4_1_row: str

    def __post_init__(self) -> None:
        table_4_1_policy(self.table_4_1_row)


@dataclass(frozen=True, slots=True)
class A16FormalApplicabilityInput:
    table_4_1_row: str

    def __post_init__(self) -> None:
        table_4_1_policy(self.table_4_1_row)


def evaluate_bys_eligibility_formal_applicability(
    value: BysEligibilityFormalApplicabilityInput,
) -> ApplicabilityState:
    if not isinstance(value, BysEligibilityFormalApplicabilityInput):
        raise TypeError("BYS formal applicability requires BysEligibilityFormalApplicabilityInput")
    return (
        ApplicabilityState.PROVEN_NOT_APPLICABLE
        if requires_a16_special_context(value.table_4_1_row)
        else ApplicabilityState.APPLIES
    )


def evaluate_dts_4_3_4_1_formal_applicability(
    value: Dts4341FormalApplicabilityInput,
) -> ApplicabilityState:
    if not isinstance(value, Dts4341FormalApplicabilityInput):
        raise TypeError("4.3.4.1 formal applicability requires Dts4341FormalApplicabilityInput")
    policy = table_4_1_policy(value.table_4_1_row)
    return (
        ApplicabilityState.PROVEN_NOT_APPLICABLE
        if policy.ductility is RcDuctilityLevel.HIGH
        else ApplicabilityState.APPLIES
    )


def evaluate_a31_formal_applicability(
    value: A31FormalApplicabilityInput,
) -> ApplicabilityState:
    if not isinstance(value, A31FormalApplicabilityInput):
        raise TypeError("A31 formal applicability requires A31FormalApplicabilityInput")
    return (
        ApplicabilityState.APPLIES
        if table_4_1_policy(value.table_4_1_row).row == "A31"
        else ApplicabilityState.PROVEN_NOT_APPLICABLE
    )


def evaluate_a16_formal_applicability(
    value: A16FormalApplicabilityInput,
) -> ApplicabilityState:
    if not isinstance(value, A16FormalApplicabilityInput):
        raise TypeError("A16 formal applicability requires A16FormalApplicabilityInput")
    return (
        ApplicabilityState.APPLIES
        if requires_a16_special_context(value.table_4_1_row)
        else ApplicabilityState.PROVEN_NOT_APPLICABLE
    )


_FORMAL_CHECK_APPLICABILITY_INPUT_TYPES = MappingProxyType(
    {
        RC_TABLE_4_1_BYS_ELIGIBILITY: BysEligibilityFormalApplicabilityInput,
        RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY: Dts4341FormalApplicabilityInput,
        RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY: A31FormalApplicabilityInput,
        RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY: A16FormalApplicabilityInput,
    }
)


def formal_check_applicability_input(rule_id: RuleId, table_4_1_row: str) -> object:
    """Return the reviewed typed applicability input required by one VS-4A rule."""
    if not isinstance(rule_id, RuleId):
        raise TypeError("rule_id must be RuleId")
    row = table_4_1_policy(table_4_1_row).row
    input_type = _FORMAL_CHECK_APPLICABILITY_INPUT_TYPES.get(rule_id)
    if input_type is None:
        return DirectionalApplicabilityInput()
    return input_type(row)
'''
if old not in text:
    raise SystemExit("structural_system applicability insertion point not found")
text = text.replace(old, new, 1)

old = '''def _check(
    rule_id: RuleId,
    dependencies: tuple[DependencySpec, ...],
    evaluator,
    code_refs: tuple[str, ...],
) -> CheckSpec:
    return CheckSpec(
        rule_id=rule_id,
        code_refs=code_refs,
        rule_version=RULE_VERSION,
        formal_result_type=CheckResult,
        dependencies=dependencies,
        applicability=ApplicabilityBinding(
            f"vs4a:{rule_id.value}:applicability",
            DirectionalApplicabilityInput,
            _applies,
        ),
        evaluator=CheckEvaluatorBinding(
            f"vs4a:{rule_id.value}:evaluator",
            StructuralSystemExecutionInput,
            evaluator,
        ),
    )
'''
new = '''def _check(
    rule_id: RuleId,
    dependencies: tuple[DependencySpec, ...],
    evaluator,
    code_refs: tuple[str, ...],
    *,
    applicability: ApplicabilityBinding | None = None,
) -> CheckSpec:
    return CheckSpec(
        rule_id=rule_id,
        code_refs=code_refs,
        rule_version=RULE_VERSION,
        formal_result_type=CheckResult,
        dependencies=dependencies,
        applicability=applicability
        or ApplicabilityBinding(
            f"vs4a:{rule_id.value}:applicability",
            DirectionalApplicabilityInput,
            _applies,
        ),
        evaluator=CheckEvaluatorBinding(
            f"vs4a:{rule_id.value}:evaluator",
            StructuralSystemExecutionInput,
            evaluator,
        ),
    )
'''
if old not in text:
    raise SystemExit("structural_system _check block not found")
text = text.replace(old, new, 1)

replacements = {
'''BYS_CHECK_SPEC = _check(
    RC_TABLE_4_1_BYS_ELIGIBILITY,
    (ROW_DEP, BYS_DEP, EFFECTIVE_BYS_REG_DEP, BYS_ELIGIBILITY_REG_DEP),
    evaluate_bys_eligibility,
    ("TBDY 2018 4.3.1.2; Table 4.1",),
)
''': '''BYS_CHECK_SPEC = _check(
    RC_TABLE_4_1_BYS_ELIGIBILITY,
    (ROW_DEP, BYS_DEP, EFFECTIVE_BYS_REG_DEP, BYS_ELIGIBILITY_REG_DEP),
    evaluate_bys_eligibility,
    ("TBDY 2018 4.3.1.2; Table 4.1",),
    applicability=ApplicabilityBinding(
        f"vs4a:{RC_TABLE_4_1_BYS_ELIGIBILITY.value}:applicability",
        BysEligibilityFormalApplicabilityInput,
        evaluate_bys_eligibility_formal_applicability,
    ),
)
''',
'''DTS_CHECK_SPEC = _check(
    RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY,
    (DTS_DEP, BYS_DEP, DUCTILITY_REG_DEP, DTS_ELIGIBILITY_REG_DEP),
    evaluate_dts_system_eligibility,
    ("TBDY 2018 4.3.4.1",),
)
''': '''DTS_CHECK_SPEC = _check(
    RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY,
    (DTS_DEP, BYS_DEP, DUCTILITY_REG_DEP, DTS_ELIGIBILITY_REG_DEP),
    evaluate_dts_system_eligibility,
    ("TBDY 2018 4.3.4.1",),
    applicability=ApplicabilityBinding(
        f"vs4a:{RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY.value}:applicability",
        Dts4341FormalApplicabilityInput,
        evaluate_dts_4_3_4_1_formal_applicability,
    ),
)
''',
'''A31_CHECK_SPEC = _check(
    RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY,
    (ROW_DEP, DTS_DEP, A31_ELIGIBILITY_REG_DEP),
    evaluate_a31_dts_eligibility,
    ("TBDY 2018 4.3.4.3",),
)
''': '''A31_CHECK_SPEC = _check(
    RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY,
    (ROW_DEP, DTS_DEP, A31_ELIGIBILITY_REG_DEP),
    evaluate_a31_dts_eligibility,
    ("TBDY 2018 4.3.4.3",),
    applicability=ApplicabilityBinding(
        f"vs4a:{RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY.value}:applicability",
        A31FormalApplicabilityInput,
        evaluate_a31_formal_applicability,
    ),
)
''',
'''A16_CHECK_SPEC = _check(
    RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY,
    (ROW_DEP, A16_CONTEXT_DEP, A16_ELIGIBILITY_REG_DEP),
    evaluate_a16_special_eligibility,
    ("TBDY 2018 Table 4.1 A16",),
)
''': '''A16_CHECK_SPEC = _check(
    RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY,
    (ROW_DEP, A16_CONTEXT_DEP, A16_ELIGIBILITY_REG_DEP),
    evaluate_a16_special_eligibility,
    ("TBDY 2018 Table 4.1 A16",),
    applicability=ApplicabilityBinding(
        f"vs4a:{RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY.value}:applicability",
        A16FormalApplicabilityInput,
        evaluate_a16_formal_applicability,
    ),
)
''',
}
for old_block, new_block in replacements.items():
    if old_block not in text:
        raise SystemExit("formal check spec replacement block not found")
    text = text.replace(old_block, new_block, 1)

marker = '    "DirectionalAnalysisSystemAssumption",\n'
additions = '''    "DirectionalAnalysisSystemAssumption",
    "DirectionalApplicabilityInput",
    "BysEligibilityFormalApplicabilityInput",
    "Dts4341FormalApplicabilityInput",
    "A31FormalApplicabilityInput",
    "A16FormalApplicabilityInput",
    "requires_a16_special_context",
    "formal_check_applicability_input",
    "evaluate_bys_eligibility_formal_applicability",
    "evaluate_dts_4_3_4_1_formal_applicability",
    "evaluate_a31_formal_applicability",
    "evaluate_a16_formal_applicability",
'''
if marker not in text:
    raise SystemExit("__all__ insertion marker not found")
text = text.replace(marker, additions, 1)
path.write_text(text)


# 2) Orchestration composes typed inputs only. No regulatory branching remains.
path = Path("tbdy_engine/regulatory/vs4a_program.py")
text = path.read_text()
start = text.find("def _formal_check_applies(")
if start < 0:
    raise SystemExit("_formal_check_applies block not found")
end = text.find("\n\ndef _reviewed_refs", start)
if end < 0:
    raise SystemExit("_reviewed_refs boundary not found")
replacement = '''def _directional_targets(direction: str, row: str) -> tuple[RuleScopeTarget, ...]:
    return tuple(
        RuleScopeTarget(
            rule_id=rule_id,
            grain=Grain.DIRECTION,
            scope_ref=ss.BUILDING_SCOPE,
            direction=direction,
            applicability_input=ss.formal_check_applicability_input(rule_id, row),
            analysis_basis_status=AnalysisBasisStatus.MATCH,
        )
        for rule_id in ss.DIRECTIONAL_VS4A_RULE_IDS
    )
'''
text = text[:start] + replacement + text[end:]
old_a16 = 'if declaration.table_4_1_row == "A16"'
if text.count(old_a16) != 2:
    raise SystemExit(f"expected two direct A16 orchestration branches, got {text.count(old_a16)}")
text = text.replace(
    old_a16,
    "if ss.requires_a16_special_context(declaration.table_4_1_row)",
)
if "_formal_check_applies" in text:
    raise SystemExit("regulatory formal applicability helper remains in composition")
if 'table_4_1_row == "A16"' in text or 'table_4_1_row != "A16"' in text:
    raise SystemExit("direct A16 row branching remains in composition")
path.write_text(text)


# 3) Explicit boundary/application regressions.
path = Path("tests/regulatory/test_structural_system.py")
text = path.read_text()
if "import inspect\n" not in text:
    text = text.replace(
        "from __future__ import annotations\n\n",
        "from __future__ import annotations\n\nimport inspect\n",
        1,
    )
old_import = "from tbdy_engine.regulatory import structural_system as ss\n"
new_import = (
    "from tbdy_engine.regulatory import structural_system as ss\n"
    "from tbdy_engine.regulatory import vs4a_program as vs4a_program_module\n"
)
if "vs4a_program as vs4a_program_module" not in text:
    if old_import not in text:
        raise SystemExit("structural_system test import marker not found")
    text = text.replace(old_import, new_import, 1)
if "test_formal_applicability_evaluators_are_reviewed_structural_system_code" not in text:
    text += '''


def test_formal_applicability_evaluators_are_reviewed_structural_system_code():
    for spec in (
        ss.BYS_CHECK_SPEC,
        ss.DTS_CHECK_SPEC,
        ss.A31_CHECK_SPEC,
        ss.A16_CHECK_SPEC,
    ):
        assert spec.applicability.evaluator.__module__ == "tbdy_engine.regulatory.structural_system"
        assert spec.applicability.input_type.__module__ == "tbdy_engine.regulatory.structural_system"


def test_vs4a_program_contains_no_regulatory_formal_applicability_branching():
    source = inspect.getsource(vs4a_program_module)
    assert "_formal_check_applies" not in source
    assert 'table_4_1_row == "A16"' not in source
    assert 'table_4_1_row != "A16"' not in source
    assert "ss.formal_check_applicability_input(" in source
    assert "ss.requires_a16_special_context(" in source


def test_4_3_4_1_high_mixed_limited_applicability_boundaries_are_exact():
    for row, policy in ss.TABLE_4_1_A_SERIES.items():
        actual = ss.evaluate_dts_4_3_4_1_formal_applicability(
            ss.Dts4341FormalApplicabilityInput(row)
        )
        expected = (
            ApplicabilityState.PROVEN_NOT_APPLICABLE
            if policy.ductility is ss.RcDuctilityLevel.HIGH
            else ApplicabilityState.APPLIES
        )
        assert actual is expected, row
'''
path.write_text(text)

path = Path("tests/regulatory/test_vs4a_source_authority.py")
text = path.read_text()
if "    IMPLEMENTATION_MODULE,\n" not in text:
    text = text.replace(
        "    CLAIMS_FOR_RULE,\n",
        "    CLAIMS_FOR_RULE,\n    IMPLEMENTATION_MODULE,\n",
        1,
    )
if "test_formal_applicability_bindings_are_fresh_under_reviewed_module_boundary" not in text:
    text += '''


def test_formal_applicability_bindings_are_fresh_under_reviewed_module_boundary():
    catalog = build_vs4a_authority_catalog()
    validated = {
        item.rule_id: item for item in validate_registry_authority(ss.VS4A_REGISTRY, catalog)
    }
    affected = (
        ss.RC_TABLE_4_1_BYS_ELIGIBILITY,
        ss.RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY,
        ss.RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY,
        ss.RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY,
    )
    for rule_id in affected:
        spec = next(item for item in ss.VS4A_REGISTRY.checks if item.rule_id == rule_id)
        binding = catalog.binding(validated[rule_id].binding_id)
        assert binding.implementation_modules == (IMPLEMENTATION_MODULE,)
        assert spec.applicability.evaluator.__module__ == IMPLEMENTATION_MODULE
        actual = implementation_fingerprint(
            rule_id=spec.rule_id,
            rule_version=spec.rule_version,
            evaluator_binding_id=spec.evaluator.binding_id,
            implementation_modules=binding.implementation_modules,
        )
        assert binding.approved_implementation_fingerprint == actual
        assert APPROVED_IMPLEMENTATION_FINGERPRINTS[rule_id.value] == actual
'''
path.write_text(text)


# 4) Architecture/status documentation.
for doc_name in (
    "docs/architecture/VS4A_RC_SYSTEM_BASELINE_POLICY.md",
    "docs/architecture/VS4A_RC_SYSTEM_BASELINE_POLICY_STATUS.md",
):
    path = Path(doc_name)
    text = path.read_text()
    if "Authority-boundary correction" not in text:
        text += '''

## Authority-boundary correction

Formal regulatory applicability for BYS, TBDY 4.3.4.1, A31, and A16 is evaluated by typed applicability contracts implemented in `tbdy_engine.regulatory.structural_system`. `vs4a_program.py` only composes reviewed row/context inputs and delegates both formal applicability input construction and the A16-special-context requirement to reviewed helpers in that module. The F0.9 implementation boundary therefore remains exactly `tbdy_engine.regulatory.structural_system`; orchestration is not broadened into executable regulatory authority.
'''
    path.write_text(text)


# 5) Recompute exact F0.9 implementation fingerprints. Claims/source chain stay unchanged.
from tbdy_engine.regulatory import structural_system as ss
from tbdy_engine.regulatory.authority import implementation_fingerprint

path = Path("tbdy_engine/regulatory/sources/tbdy2018.py")
lines = path.read_text().splitlines()
index = next(
    (i for i, line in enumerate(lines) if line.startswith("APPROVED_IMPLEMENTATION_FINGERPRINTS = ")),
    None,
)
if index is None:
    raise SystemExit("approved implementation fingerprint assignment not found")
old_fingerprints = ast.literal_eval(lines[index].split("=", 1)[1].strip())
anchor_line_before = next(line for line in lines if line.startswith("ANCHOR_DATA = "))
claim_line_before = next(line for line in lines if line.startswith("CLAIM_DATA = "))
specs = sorted(
    (*ss.VS4A_REGISTRY.derivations, *ss.VS4A_REGISTRY.checks),
    key=lambda spec: spec.rule_id.value,
)
new_fingerprints = {
    spec.rule_id.value: implementation_fingerprint(
        rule_id=spec.rule_id,
        rule_version=spec.rule_version,
        evaluator_binding_id=spec.evaluator.binding_id,
        implementation_modules=("tbdy_engine.regulatory.structural_system",),
    )
    for spec in specs
}
if set(old_fingerprints) != set(new_fingerprints):
    raise SystemExit("implementation fingerprint key set changed unexpectedly")
affected = (
    ss.RC_TABLE_4_1_BYS_ELIGIBILITY.value,
    ss.RC_TBDY_4_3_4_1_DTS_SYSTEM_ELIGIBILITY.value,
    ss.RC_TBDY_4_3_4_3_A31_DTS_ELIGIBILITY.value,
    ss.RC_TABLE_4_1_A16_SPECIAL_ELIGIBILITY.value,
)
delta = []
for rule_id in affected:
    if old_fingerprints[rule_id] == new_fingerprints[rule_id]:
        raise SystemExit(f"authority-boundary change did not stale old fingerprint: {rule_id}")
    delta.append(
        f"{rule_id}: old={old_fingerprints[rule_id]} new={new_fingerprints[rule_id]}"
    )
lines[index] = "APPROVED_IMPLEMENTATION_FINGERPRINTS = " + repr(new_fingerprints)
if next(line for line in lines if line.startswith("ANCHOR_DATA = ")) != anchor_line_before:
    raise SystemExit("source anchors changed unexpectedly")
if next(line for line in lines if line.startswith("CLAIM_DATA = ")) != claim_line_before:
    raise SystemExit("regulatory claims/review fingerprints changed unexpectedly")
path.write_text("\n".join(lines) + "\n")
Path("/tmp/vs4a_fingerprint_delta.txt").write_text("\n".join(delta) + "\n")
