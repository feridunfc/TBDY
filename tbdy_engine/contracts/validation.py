"""Reusable validation entrypoints for Contract Constitution files.

This module intentionally delegates to the canonical CLI validator without weakening
its semantics. It does not import engine/runtime/provider/check modules.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tbdy_engine.tools.validate_contract_constitution import (
    ContractValidationError,
    DEFAULT_CATALOG_DIR,
    validate_contract_constitution,
)


def validate_contracts(catalog_dir: str | Path = DEFAULT_CATALOG_DIR) -> None:
    """Fail fast if the contract constitution tree is malformed."""
    validate_contract_constitution(Path(catalog_dir))


__all__ = ["ContractValidationError", "validate_contracts"]
