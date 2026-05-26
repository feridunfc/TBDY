from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

from tbdy_engine.etabs.normalizers.beam_design import (
    build_beam_context_from_tables,
    to_context_namespace,
)
from tbdy_engine.etabs.table_access import EtabsTableAccessStatus, read_etabs_table_on_demand


BEAM_TABLE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "beam_design_summary": (
        "Concrete Beam Design Summary - TS 500-2000(R2018)",
        "Concrete Beam Design Summary",
    ),
    "beam_flexure_envelope": (
        "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
        "Concrete Beam Flexure Envelope -  TS 500-2000(R2018)",
    ),
    "beam_shear_envelope": (
        "Concrete Beam Shear Envelope - TS 500-2000(R2018)",
        "Concrete Beam Shear Envelope -  TS 500-2000(R2018)",
    ),
}


class BeamProviderError(RuntimeError):
    def __init__(self, message: str, *, diagnostics: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class BeamEtabsProvider:
    def __init__(self, table_candidates: dict[str, Sequence[str]] | None = None) -> None:
        self.table_candidates = {
            logical_name: tuple(candidates)
            for logical_name, candidates in (table_candidates or BEAM_TABLE_CANDIDATES).items()
        }
        self.diagnostics: dict[str, object] = {
            "attempted_tables": {},
            "selected_tables": {},
            "missing_tables": {},
        }

    def build_context(self) -> object:
        tables = self._read_required_tables()
        context = build_beam_context_from_tables(tables)
        ctx = to_context_namespace(context)
        self._attach_diagnostics(ctx)
        return ctx

    def _read_required_tables(self) -> dict[str, object]:
        tables: dict[str, object] = {}
        attempted_tables: dict[str, list[dict[str, object]]] = {}
        selected_tables: dict[str, str] = {}
        missing_tables: dict[str, list[str]] = {}

        for logical_name, candidates in self.table_candidates.items():
            attempts: list[dict[str, object]] = []
            selected = None
            for candidate in candidates:
                result = read_etabs_table_on_demand(candidate)
                attempt = result.to_dict()
                attempts.append(attempt)
                if result.status is EtabsTableAccessStatus.OK and result.df is not None:
                    selected = result
                    break

            attempted_tables[logical_name] = attempts
            if selected is None:
                missing_tables[logical_name] = [str(candidate) for candidate in candidates]
                continue

            selected_tables[logical_name] = selected.table_name
            tables[logical_name] = selected.df
            tables[f"{logical_name}_source_table"] = selected.table_name

        self.diagnostics = {
            "attempted_tables": attempted_tables,
            "selected_tables": selected_tables,
            "missing_tables": missing_tables,
        }
        if missing_tables:
            raise BeamProviderError(
                "Required live ETABS beam tables are missing.",
                diagnostics=self.diagnostics,
            )
        return tables

    def _attach_diagnostics(self, ctx: object) -> None:
        diagnostics = getattr(ctx, "diagnostics", None)
        if not isinstance(diagnostics, dict):
            diagnostics = {}
            setattr(ctx, "diagnostics", diagnostics)
        diagnostics["beam_provider"] = self.diagnostics
        setattr(ctx, "beam_provider_diagnostics", self.diagnostics)


def build_live_beam_context() -> object:
    return BeamEtabsProvider().build_context()
