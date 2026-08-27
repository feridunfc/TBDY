"""Strict source-bound composition root for FND-COL-2.

The generic F0 compiler intentionally supports registries with and without a
source-authority catalog. FND-COL-2 is stricter: its production composition root
must always compile through the reviewed F0.9 authority package before execution.

This module adds no engineering formulas and no downstream P8A/rebar authority.
"""
from __future__ import annotations

from tbdy_engine.regulatory.authority import RegulatoryAuthorityCatalog
from tbdy_engine.regulatory.fnd_col_2 import REGISTRY
from tbdy_engine.regulatory.kernel import (
    CompiledRegulatoryProgram,
    KernelCompileError,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RegulatoryStoreSnapshot,
)


def compile_fnd_col_2_program(
    inputs: RegulatoryCompileInputs,
    *,
    authority_catalog: RegulatoryAuthorityCatalog | None,
) -> CompiledRegulatoryProgram:
    """Compile FND-COL-2 only after an explicit F0.9 authority catalog is bound."""
    if not isinstance(inputs, RegulatoryCompileInputs):
        raise TypeError("inputs must be RegulatoryCompileInputs")
    if authority_catalog is None:
        raise KernelCompileError("FND-COL-2 requires a bound regulatory authority catalog")
    if not isinstance(authority_catalog, RegulatoryAuthorityCatalog):
        raise TypeError("authority_catalog must be RegulatoryAuthorityCatalog or None")
    if (
        inputs.regulatory_authority_catalog is not None
        and inputs.regulatory_authority_catalog != authority_catalog
    ):
        raise KernelCompileError(
            "FND-COL-2 compile inputs already contain a different regulatory authority catalog"
        )

    strict_inputs = RegulatoryCompileInputs(
        rule_targets=inputs.rule_targets,
        external_authorities=inputs.external_authorities,
        regulatory_authority_catalog=authority_catalog,
    )
    return RegulatoryCompiler.compile(REGISTRY, strict_inputs)


def compile_source_bound_fnd_col_2_program(
    inputs: RegulatoryCompileInputs,
) -> CompiledRegulatoryProgram:
    """Compile with the concrete reviewed FND-COL-2 authority package."""
    # Late import prevents the authority package -> SPEC import from creating a
    # module-initialization cycle while keeping this composition root strict.
    from tbdy_engine.regulatory.fnd_col_2_authority import FND_COL_2_AUTHORITY_CATALOG

    return compile_fnd_col_2_program(
        inputs,
        authority_catalog=FND_COL_2_AUTHORITY_CATALOG,
    )


def execute_source_bound_fnd_col_2(
    inputs: RegulatoryCompileInputs,
) -> RegulatoryStoreSnapshot:
    """Execute only a plan that successfully consumed the reviewed F0.9 catalog."""
    program = compile_source_bound_fnd_col_2_program(inputs)
    return RegulatoryEngine.execute(program)


__all__ = [
    "compile_fnd_col_2_program",
    "compile_source_bound_fnd_col_2_program",
    "execute_source_bound_fnd_col_2",
]
