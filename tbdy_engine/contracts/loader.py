"""Contract Constitution loader.

Source YAML/JSON files remain under ``tbdy_engine/catalogs``. This package is the
Python loader only. C3 does not implement providers, resolvers, formulas, checks,
or engine execution.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.contracts.validation import validate_contracts
from tbdy_engine.tools.validate_contract_constitution import (
    CATALOG_FILES,
    DEFAULT_CATALOG_DIR,
    EXAMPLE_SCHEMA_MAP,
    REQUIRED_SCHEMA_FILES,
)


class ContractConstitutionLoader:
    """Load and validate C1/C2/C3 contract files as read-only data."""

    def __init__(self, catalog_dir: str | Path = DEFAULT_CATALOG_DIR) -> None:
        self.catalog_dir = Path(catalog_dir)

    @property
    def schema_dir(self) -> Path:
        return self.catalog_dir / "schemas"

    @property
    def example_dir(self) -> Path:
        return self.catalog_dir / "examples"

    def load(self) -> ContractBundle:
        """Validate then load all catalogs, schemas, and examples.

        Validation happens first to fail fast on YAML, schema, or cross-reference
        errors. Returned data is immutable/read-only.
        """
        validate_contracts(self.catalog_dir)
        catalogs = {name: self._load_yaml(self.catalog_dir / name) for name in CATALOG_FILES}
        schemas = {name: self._load_json(self.schema_dir / name) for name in REQUIRED_SCHEMA_FILES}
        examples = {name: self._load_json(self.example_dir / name) for name in EXAMPLE_SCHEMA_MAP}
        return ContractBundle.from_raw(
            catalog_dir=str(self.catalog_dir),
            catalogs=catalogs,
            schemas=schemas,
            examples=examples,
        )

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a YAML object")
        return data

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a JSON object")
        return data


def load_contracts(catalog_dir: str | Path = DEFAULT_CATALOG_DIR) -> ContractBundle:
    return ContractConstitutionLoader(catalog_dir).load()


__all__ = ["ContractConstitutionLoader", "load_contracts"]
