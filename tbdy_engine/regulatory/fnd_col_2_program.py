"""Strict source-bound composition root for FND-COL-2.

The generic F0 compiler intentionally supports registries with and without a
source-authority catalog. FND-COL-2 is stricter: its production composition root
must always compile through the reviewed F0.9 authority package before execution.

This module adds no engineering formulas and no downstream P8A/rebar authority.
"""
from __future__ import annotations

from dataclasses import dataclass

from tbdy_engine.design.columns.column_design_readiness import ColumnDesignDemandReadiness
from tbdy_engine.regulatory.authority import RegulatoryAuthorityCatalog
from tbdy_engine.regulatory.contracts import DependencyKey, RuleInstanceId
from tbdy_engine.regulatory.fnd_col_2 import (
    READINESS_KEY,
    REGISTRY,
    RULE_ID,
    _capture_typed_readiness_execution,
)
from tbdy_engine.regulatory.kernel import (
    CompiledRegulatoryProgram,
    KernelCompileError,
    KernelExecutionError,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RegulatoryStoreSnapshot,
)


@dataclass(frozen=True, slots=True)
class FndCol2ReadinessExecutionRecord:
    """Typed readiness plus the exact F0 execution identity that produced it."""

    readiness: ColumnDesignDemandReadiness
    readiness_instance_ref: RuleInstanceId
    plan_identity: str
    dependency_refs: tuple[DependencyKey, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FndCol2ExecutionArtifact:
    """Canonical snapshot plus typed readiness retained from the same execution."""

    snapshot: RegulatoryStoreSnapshot
    readiness_records: tuple[FndCol2ReadinessExecutionRecord, ...]

    @property
    def readiness(self) -> ColumnDesignDemandReadiness | None:
        """Return the typed readiness for the common single-instance execution."""
        if not self.readiness_records:
            return None
        if len(self.readiness_records) != 1:
            raise ValueError("FND-COL-2 execution contains multiple typed readiness instances")
        return self.readiness_records[0].readiness


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


def _bind_captured_readiness(
    snapshot: RegulatoryStoreSnapshot,
    captured: tuple[
        tuple[object, ColumnDesignDemandReadiness, tuple[str, ...]], ...
    ],
) -> tuple[FndCol2ReadinessExecutionRecord, ...]:
    records: list[FndCol2ReadinessExecutionRecord] = []
    seen: set[RuleInstanceId] = set()
    for envelope, readiness, evidence_refs in captured:
        if envelope.plan_identity != snapshot.plan_identity:
            raise KernelExecutionError("FND-COL-2 typed readiness plan identity mismatch")
        if envelope.rule_id != RULE_ID:
            raise KernelExecutionError("FND-COL-2 typed readiness rule identity mismatch")
        if envelope.instance_id in seen:
            raise KernelExecutionError("duplicate FND-COL-2 typed readiness capture")
        if readiness.component_id != envelope.instance_id.scope_ref:
            raise KernelExecutionError("FND-COL-2 typed readiness component identity mismatch")

        quantities = tuple(
            item
            for item in snapshot.quantities_for(envelope.instance_id)
            if item.quantity_key == READINESS_KEY
        )
        if len(quantities) != 1:
            raise KernelExecutionError(
                "FND-COL-2 typed readiness has no unique canonical RegulatoryQuantity"
            )
        quantity = quantities[0]
        if tuple(quantity.dependency_refs) != tuple(envelope.declared_dependency_refs):
            raise KernelExecutionError("FND-COL-2 typed readiness dependency identity mismatch")
        if tuple(quantity.evidence_refs) != tuple(evidence_refs):
            raise KernelExecutionError("FND-COL-2 typed readiness evidence identity mismatch")
        if quantity.scope_ref != readiness.component_id:
            raise KernelExecutionError("FND-COL-2 quantity/readiness component mismatch")
        if quantity.value.get("status") != readiness.status:
            raise KernelExecutionError("FND-COL-2 quantity/readiness status mismatch")
        if tuple(quantity.provenance[2:]) != tuple(readiness.source_refs):
            raise KernelExecutionError("FND-COL-2 quantity/readiness provenance mismatch")

        records.append(
            FndCol2ReadinessExecutionRecord(
                readiness=readiness,
                readiness_instance_ref=envelope.instance_id,
                plan_identity=envelope.plan_identity,
                dependency_refs=tuple(envelope.declared_dependency_refs),
                evidence_refs=tuple(evidence_refs),
            )
        )
        seen.add(envelope.instance_id)
    return tuple(records)


def execute_source_bound_fnd_col_2_with_artifact(
    inputs: RegulatoryCompileInputs,
) -> FndCol2ExecutionArtifact:
    """Execute once and retain exact typed readiness before serialization identity is lost."""
    program = compile_source_bound_fnd_col_2_program(inputs)
    with _capture_typed_readiness_execution() as captured:
        snapshot = RegulatoryEngine.execute(program)
    records = _bind_captured_readiness(snapshot, tuple(captured))
    return FndCol2ExecutionArtifact(snapshot=snapshot, readiness_records=records)


def execute_source_bound_fnd_col_2(
    inputs: RegulatoryCompileInputs,
) -> RegulatoryStoreSnapshot:
    """Preserve the existing public snapshot-only source-bound execution contract."""
    return execute_source_bound_fnd_col_2_with_artifact(inputs).snapshot


__all__ = [
    "FndCol2ExecutionArtifact",
    "FndCol2ReadinessExecutionRecord",
    "compile_fnd_col_2_program",
    "compile_source_bound_fnd_col_2_program",
    "execute_source_bound_fnd_col_2",
    "execute_source_bound_fnd_col_2_with_artifact",
]
