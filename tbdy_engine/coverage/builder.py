"""Coverage matrix builder for C5/C5.1.

The builder inspects FeatureSnapshot availability against check_catalog required
features and records expected source diagnostics. It does not read provider/ETABS
tables, resolve features, execute checks, compute ratios, or emit decisions.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.coverage.diagnostics import CoverageDiagnostic, CoverageDiagnosticCode, CoverageDiagnosticSeverity
from tbdy_engine.coverage.models import (
    CoverageEvidenceStatus,
    CoverageExpectedSource,
    CoverageMatrix,
    CoverageMissingDesignContext,
    CoverageMissingFeature,
    CoveragePolicyStatus,
    CoverageRow,
    CoverageStatus,
    ExpectedSourceKind,
)
from tbdy_engine.features.evidence import FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValueStatus


class CoverageBuilder:
    """Build runnability rows from contracts and FeatureSnapshot objects."""

    def __init__(self, contract_bundle: ContractBundle) -> None:
        self.contract_bundle = contract_bundle
        self.check_catalog: Mapping[str, Any] = contract_bundle.catalog("check_catalog.yaml").get("checks", {})
        self.feature_catalog: Mapping[str, Any] = contract_bundle.catalog("feature_catalog.yaml").get("features", {})
        self.table_registry: Mapping[str, Any] = contract_bundle.catalog("table_registry.yaml").get("tables", {})
        self.element_registry: Mapping[str, Any] = contract_bundle.catalog("element_registry.yaml").get("element_types", {})
        self.scope_items: tuple[Mapping[str, Any], ...] = tuple(
            contract_bundle.catalog("high_ductility_check_scope.yaml").get("scope_items", ())
        )
        self.alignment = contract_bundle.catalog("check_scope_alignment.yaml")

    def build_for_snapshot(
        self,
        snapshot: FeatureSnapshot,
        *,
        check_ids: Sequence[str] | None = None,
        design_context: Mapping[str, Any] | None = None,
    ) -> CoverageMatrix:
        selected = tuple(check_ids or self._checks_for_component_type(snapshot.component_type))
        rows = [self.build_row(snapshot, check_id, design_context=design_context or {}) for check_id in selected]
        return CoverageMatrix(rows=rows)

    def build_row(
        self,
        snapshot: FeatureSnapshot,
        check_id: str,
        *,
        design_context: Mapping[str, Any] | None = None,
    ) -> CoverageRow:
        check_def = self.check_catalog.get(check_id)
        if check_def is None:
            raise ValueError(f"Unknown check_id: {check_id}")
        component_type = str(check_def.get("element_type") or snapshot.component_type)
        if component_type not in self.element_registry:
            raise ValueError(f"Unknown coverage component_type: {component_type}")
        required_features = tuple(str(feature) for feature in check_def.get("required_features", ()) or ())
        unknown_features = [feature for feature in required_features if feature not in self.feature_catalog]
        if unknown_features:
            raise ValueError(f"Check {check_id} references unknown required features: {', '.join(unknown_features)}")
        resolved_features: list[str] = []
        missing_features: list[CoverageMissingFeature] = []
        missing_feature_sources: dict[str, CoverageExpectedSource] = {}
        expected_evidence_requirements: dict[str, tuple[str, ...]] = {}
        diagnostics: list[CoverageDiagnostic] = []
        source_diagnostics: list[CoverageDiagnostic] = []
        evidence_status = CoverageEvidenceStatus.FULL

        for feature_name in required_features:
            expected_source = self._expected_source_for_feature(feature_name)
            expected_evidence_requirements[feature_name] = expected_source.expected_evidence_fields
            feature_value = snapshot.features.get(feature_name)
            if feature_value is None or feature_value.status == FeatureValueStatus.MISSING:
                missing_features.append(CoverageMissingFeature(feature_name, "FeatureSnapshot does not contain a resolved feature value"))
                missing_feature_sources[feature_name] = expected_source
                diagnostics.append(
                    CoverageDiagnostic(
                        severity=CoverageDiagnosticSeverity.ERROR,
                        code=CoverageDiagnosticCode.FEATURE_MISSING,
                        message="Required feature is missing from FeatureSnapshot",
                        details={"check_id": check_id, "feature_name": feature_name},
                    )
                )
                source_diagnostics.append(
                    CoverageDiagnostic(
                        severity=CoverageDiagnosticSeverity.INFO,
                        code=CoverageDiagnosticCode.EXPECTED_SOURCE_RECORDED,
                        message="Expected source metadata recorded for missing feature",
                        details={"check_id": check_id, "feature_name": feature_name, "source_kind": expected_source.source_kind.value},
                    )
                )
                evidence_status = CoverageEvidenceStatus.MISSING
                continue
            if feature_value.status == FeatureValueStatus.PARTIAL:
                resolved_features.append(feature_name)
                evidence_status = CoverageEvidenceStatus.PARTIAL
                diagnostics.append(
                    CoverageDiagnostic(
                        severity=CoverageDiagnosticSeverity.WARNING,
                        code=CoverageDiagnosticCode.EVIDENCE_PARTIAL,
                        message="Required feature is only partially resolved",
                        details={"check_id": check_id, "feature_name": feature_name},
                    )
                )
                source_diagnostics.append(
                    CoverageDiagnostic(
                        severity=CoverageDiagnosticSeverity.INFO,
                        code=CoverageDiagnosticCode.EXPECTED_SOURCE_RECORDED,
                        message="Expected evidence requirements recorded for partial feature",
                        details={"check_id": check_id, "feature_name": feature_name},
                    )
                )
                continue
            if not feature_value.evidence:
                missing_features.append(CoverageMissingFeature(feature_name, "Resolved feature is missing evidence"))
                missing_feature_sources[feature_name] = expected_source
                evidence_status = CoverageEvidenceStatus.MISSING
                diagnostics.append(
                    CoverageDiagnostic(
                        severity=CoverageDiagnosticSeverity.ERROR,
                        code=CoverageDiagnosticCode.EVIDENCE_MISSING,
                        message="Resolved feature is missing evidence",
                        details={"check_id": check_id, "feature_name": feature_name},
                    )
                )
                continue
            if any(ev.evidence_status == FeatureEvidenceStatus.PARTIAL for ev in feature_value.evidence):
                resolved_features.append(feature_name)
                evidence_status = CoverageEvidenceStatus.PARTIAL
                diagnostics.append(
                    CoverageDiagnostic(
                        severity=CoverageDiagnosticSeverity.WARNING,
                        code=CoverageDiagnosticCode.EVIDENCE_PARTIAL,
                        message="Required feature has partial evidence",
                        details={"check_id": check_id, "feature_name": feature_name},
                    )
                )
                source_diagnostics.append(
                    CoverageDiagnostic(
                        severity=CoverageDiagnosticSeverity.INFO,
                        code=CoverageDiagnosticCode.EXPECTED_SOURCE_RECORDED,
                        message="Expected evidence requirements recorded for partial evidence",
                        details={"check_id": check_id, "feature_name": feature_name},
                    )
                )
                continue
            if any(ev.evidence_status == FeatureEvidenceStatus.MISSING for ev in feature_value.evidence):
                missing_features.append(CoverageMissingFeature(feature_name, "Required feature has missing evidence"))
                missing_feature_sources[feature_name] = expected_source
                evidence_status = CoverageEvidenceStatus.MISSING
                diagnostics.append(
                    CoverageDiagnostic(
                        severity=CoverageDiagnosticSeverity.ERROR,
                        code=CoverageDiagnosticCode.EVIDENCE_MISSING,
                        message="Required feature has missing evidence",
                        details={"check_id": check_id, "feature_name": feature_name},
                    )
                )
                continue
            resolved_features.append(feature_name)

        required_context = tuple(self._required_design_context_for_check(check_id))
        context = design_context or {}
        resolved_context = tuple(name for name in required_context if name in context and context[name] is not None)
        missing_context = tuple(
            CoverageMissingDesignContext(name, "Required design context is missing")
            for name in required_context
            if name not in resolved_context
        )
        missing_context_sources = {
            item.context_field: self._expected_source_for_design_context(item.context_field)
            for item in missing_context
        }
        if missing_context:
            diagnostics.append(
                CoverageDiagnostic(
                    severity=CoverageDiagnosticSeverity.WARNING,
                    code=CoverageDiagnosticCode.DESIGN_CONTEXT_MISSING,
                    message="Required design context is missing for coverage",
                    details={"check_id": check_id, "missing_design_context": [item.context_field for item in missing_context]},
                )
            )
            source_diagnostics.append(
                CoverageDiagnostic(
                    severity=CoverageDiagnosticSeverity.INFO,
                    code=CoverageDiagnosticCode.EXPECTED_SOURCE_RECORDED,
                    message="Expected source metadata recorded for missing design context",
                    details={"check_id": check_id, "missing_design_context": list(missing_context_sources)},
                )
            )
        combo_status = self._combo_policy_status(check_id)
        section_state_status = self._section_state_status(check_id)
        ductility_status = CoveragePolicyStatus.RESOLVED if not missing_context else CoveragePolicyStatus.MISSING
        if missing_features:
            coverage_status = CoverageStatus.BLOCKED
            reason = "One or more required features are missing"
        elif evidence_status == CoverageEvidenceStatus.PARTIAL:
            coverage_status = CoverageStatus.PARTIAL
            reason = "One or more required features have partial evidence"
        elif missing_context:
            coverage_status = CoverageStatus.PARTIAL
            reason = "Required design context is incomplete"
        else:
            coverage_status = CoverageStatus.RUNNABLE
            reason = None
        return CoverageRow(
            check_id=check_id,
            component_type=component_type,
            component_id=snapshot.component_id,
            required_features=required_features,
            resolved_features=tuple(resolved_features),
            missing_features=tuple(missing_features),
            required_design_context=required_context,
            resolved_design_context=resolved_context,
            missing_design_context=missing_context,
            combo_policy_status=combo_status,
            section_state_status=section_state_status,
            ductility_context_status=ductility_status,
            evidence_status=evidence_status,
            coverage_status=coverage_status,
            reason=reason,
            diagnostics=tuple(diagnostics),
            missing_feature_sources=missing_feature_sources,
            missing_design_context_sources=missing_context_sources,
            expected_evidence_requirements=expected_evidence_requirements if coverage_status != CoverageStatus.RUNNABLE else {},
            source_diagnostics=tuple(source_diagnostics),
        )

    def validate_contract_alignment(self) -> tuple[CoverageDiagnostic, ...]:
        diagnostics: list[CoverageDiagnostic] = []
        check_ids = set(self.check_catalog.keys())
        reverse_raw = self.alignment.get("reverse_mappings", {})
        if isinstance(reverse_raw, Mapping):
            reverse = set(reverse_raw.keys())
        else:
            reverse = {str(item.get("check_catalog_key")) for item in reverse_raw if isinstance(item, Mapping)}
        for check_id in check_ids:
            if check_id not in reverse:
                diagnostics.append(
                    CoverageDiagnostic(
                        severity=CoverageDiagnosticSeverity.ERROR,
                        code=CoverageDiagnosticCode.CONTRACT_ALIGNMENT_MISSING,
                        message="Check has no scope alignment mapping",
                        details={"check_id": check_id},
                    )
                )
        for item in self.scope_items:
            if item.get("status") != "CONTRACTED":
                continue
            keys = tuple(item.get("related_check_catalog_keys", ()) or ())
            if not keys and not item.get("missing_alignment_reason"):
                diagnostics.append(
                    CoverageDiagnostic(
                        severity=CoverageDiagnosticSeverity.ERROR,
                        code=CoverageDiagnosticCode.CONTRACT_ALIGNMENT_MISSING,
                        message="CONTRACTED scope item lacks check mapping or pending reason",
                        details={"scope_id": item.get("check_scope_id")},
                    )
                )
            for check_id in keys:
                if check_id not in check_ids:
                    diagnostics.append(
                        CoverageDiagnostic(
                            severity=CoverageDiagnosticSeverity.ERROR,
                            code=CoverageDiagnosticCode.CHECK_UNKNOWN,
                            message="Scope item maps to unknown check_id",
                            details={"scope_id": item.get("check_scope_id"), "check_id": check_id},
                        )
                    )
        return tuple(diagnostics)

    def _checks_for_component_type(self, component_type: str) -> tuple[str, ...]:
        return tuple(
            check_id
            for check_id, check_def in self.check_catalog.items()
            if str(check_def.get("element_type")) == component_type
        )

    def _required_design_context_for_check(self, check_id: str) -> tuple[str, ...]:
        requirements: list[str] = []
        for item in self.scope_items:
            if check_id in (item.get("related_check_catalog_keys", ()) or ()):
                requirements.extend(str(value) for value in (item.get("design_context_requirements", ()) or ()))
        return tuple(dict.fromkeys(requirements))

    def _combo_policy_status(self, check_id: str) -> CoveragePolicyStatus:
        for item in self.scope_items:
            if check_id in (item.get("related_check_catalog_keys", ()) or ()):
                families = tuple(item.get("combo_families", ()) or ())
                return CoveragePolicyStatus.NOT_APPLICABLE if families == ("NONE",) or not families else CoveragePolicyStatus.RESOLVED
        return CoveragePolicyStatus.NOT_APPLICABLE

    def _section_state_status(self, check_id: str) -> CoveragePolicyStatus:
        for mapping in self.contract_bundle.catalog("design_combo_matrix.yaml").get("design_mappings", ()):
            if str(mapping.get("element_type")) != str(self.check_catalog[check_id].get("element_type")):
                continue
            if mapping.get("section_state_required"):
                return CoveragePolicyStatus.RESOLVED
        return CoveragePolicyStatus.NOT_APPLICABLE

    def _expected_source_for_feature(self, feature_name: str) -> CoverageExpectedSource:
        feature = self.feature_catalog.get(feature_name, {})
        source = feature.get("source") or {}
        table_key = source.get("table_key")
        evidence_fields = tuple(feature.get("evidence_fields", ()) or ())
        unit = str(feature.get("unit", ""))
        if table_key:
            table = self.table_registry.get(str(table_key), {})
            provider_sources = table.get("provider_sources", {}) if isinstance(table, Mapping) else {}
            table_aliases = tuple(str(x) for x in provider_sources.get("etabs", ()) or ())
            return CoverageExpectedSource(
                source_kind=ExpectedSourceKind.ETABS_TABLE,
                feature_name=feature_name,
                table_key=str(table_key),
                table_aliases=table_aliases,
                field_aliases=tuple(str(x) for x in source.get("field_aliases", ()) or ()),
                filters=tuple(source.get("filters", ()) or ()),
                combo_family=source.get("combo_family"),
                aggregation=source.get("aggregation"),
                unit=unit,
                expected_evidence_fields=evidence_fields,
            )
        return CoverageExpectedSource(
            source_kind=ExpectedSourceKind.COMPUTED,
            feature_name=feature_name,
            custom_resolver=self._custom_resolver_name(feature_name, feature),
            required_inputs=tuple(str(x) for x in (feature.get("derived_from", ()) or feature.get("design_context_dependencies", ()) or ())),
            unit=unit,
            expected_evidence_fields=evidence_fields,
        )

    @staticmethod
    def _custom_resolver_name(feature_name: str, feature: Mapping[str, Any]) -> str:
        if feature.get("custom_resolver"):
            return str(feature["custom_resolver"])
        role = str(feature.get("semantic_role", "")).upper()
        if role == "ENGINE_SELECTED_REBAR":
            return "engine_selected_rebar_resolver"
        if role == "GOVERNING_REQUIRED_REBAR":
            return "governing_rebar_resolver"
        if role == "TBDY_MIN_REQUIRED_REBAR":
            return "tbdy_min_rebar_resolver"
        if feature_name.endswith("requires_detailing_review"):
            return "final_detailing_review_resolver"
        method = (feature.get("fallback") or {}).get("method")
        if method and method not in {"none", "manual_input"}:
            return str(method)
        return "computed_resolver"

    @staticmethod
    def _expected_source_for_design_context(context_name: str) -> CoverageExpectedSource:
        return CoverageExpectedSource(
            source_kind=ExpectedSourceKind.DESIGN_CONTEXT,
            context_name=context_name,
            source_contract="design_basis.yaml",
            source_field=context_name,
            unit="",
            expected_evidence_fields=("source_contract", "source_field", "resolved_value"),
        )


__all__ = ["CoverageBuilder"]
