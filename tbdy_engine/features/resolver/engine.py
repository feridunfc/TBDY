"""Feature resolver orchestration foundation for C4.

This is not CheckEngine. It only coordinates generic feature resolution and
snapshot construction.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.features.resolver.generic import GenericFeatureResolver
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue


class FeatureResolverFoundation:
    """Small foundation wrapper around GenericFeatureResolver."""

    def __init__(self, contract_bundle: ContractBundle, tables: Mapping[str, CanonicalTable] | Sequence[CanonicalTable]):
        self.generic = GenericFeatureResolver(contract_bundle, tables)

    def resolve_feature(self, feature_name: str) -> FeatureValue:
        return self.generic.resolve_feature(feature_name)

    def build_snapshot(
        self,
        *,
        component_type: str,
        component_id: str,
        feature_names: Sequence[str],
        identity: Mapping[str, str] | None = None,
    ) -> FeatureSnapshot:
        features = {name: self.resolve_feature(name) for name in feature_names}
        return FeatureSnapshot(component_type=component_type, component_id=component_id, identity=identity or {}, features=features)


__all__ = ["FeatureResolverFoundation"]
