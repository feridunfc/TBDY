"""Immutable contract models for the TBDY contract/catalog layer.

C3 infrastructure only: no engine checks, no feature resolution, no provider calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


def freeze_data(value: Any) -> Any:
    """Recursively convert Python containers into read-only equivalents."""
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): freeze_data(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(freeze_data(v) for v in value)
    if isinstance(value, set | frozenset):
        return frozenset(freeze_data(v) for v in value)
    return value


@dataclass(frozen=True, slots=True)
class ContractBundle:
    """Read-only view of loaded contract catalogs, schemas, and examples."""

    catalog_dir: str
    catalogs: Mapping[str, Any]
    schemas: Mapping[str, Any]
    examples: Mapping[str, Any]

    @classmethod
    def from_raw(
        cls,
        *,
        catalog_dir: str,
        catalogs: Mapping[str, Any],
        schemas: Mapping[str, Any],
        examples: Mapping[str, Any],
    ) -> "ContractBundle":
        return cls(
            catalog_dir=catalog_dir,
            catalogs=freeze_data(dict(catalogs)),
            schemas=freeze_data(dict(schemas)),
            examples=freeze_data(dict(examples)),
        )

    @property
    def catalog_count(self) -> int:
        return len(self.catalogs)

    @property
    def schema_count(self) -> int:
        return len(self.schemas)

    @property
    def example_count(self) -> int:
        return len(self.examples)

    def catalog(self, name: str) -> Any:
        return self.catalogs[name]

    def schema(self, name: str) -> Any:
        return self.schemas[name]

    def example(self, name: str) -> Any:
        return self.examples[name]
