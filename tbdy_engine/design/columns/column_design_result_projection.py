"""Exact component projection of the qualified B6 factual result population.

B6 may execute concrete design for the complete strict-topology Column
population while one application request targets one Column. This module only
projects already-captured factual rows; it does not select governing rows,
change PMMArea, or create reinforcement authority.
"""
from __future__ import annotations

import hashlib
import json

from tbdy_engine.features.column_design_rebar_evidence import (
    FactualColumnDesignResultPopulation,
)


class ColumnDesignResultProjectionError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnDesignResultProjectionError(f"{label} must be a nonblank canonical string")
    return value


def project_factual_design_results_to_component(
    population: FactualColumnDesignResultPopulation,
    *,
    component_id: str,
    design_result_identity_ref: str,
    design_lineage_qualification_ref: str,
) -> FactualColumnDesignResultPopulation:
    """Retain every factual B6 row for exactly one expected component."""
    if not isinstance(population, FactualColumnDesignResultPopulation):
        raise TypeError("population must be FactualColumnDesignResultPopulation")
    if not population.capture_complete:
        raise ColumnDesignResultProjectionError("B6 factual design-result population must be complete")

    component = _text(component_id, "component_id")
    design_result_ref = _text(design_result_identity_ref, "design_result_identity_ref")
    lineage_ref = _text(design_lineage_qualification_ref, "design_lineage_qualification_ref")
    if component not in population.expected_component_ids:
        raise ColumnDesignResultProjectionError(
            f"target component {component!r} is not in the qualified B6 result scope"
        )

    rows = tuple(item for item in population.rows if item.component_id == component)
    if not rows:
        raise ColumnDesignResultProjectionError(
            f"qualified B6 population has no factual rows for target component {component!r}"
        )

    payload = {
        "component_id": component,
        "model_fingerprint": population.model_fingerprint,
        "evidence_epoch_id": population.evidence_epoch_id,
        "design_result_identity_ref": design_result_ref,
        "design_lineage_qualification_ref": lineage_ref,
        "source_row_ids": [item.source_row_id for item in rows],
    }
    projection_ref = "column-design-result-projection:sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()

    return FactualColumnDesignResultPopulation(
        model_fingerprint=population.model_fingerprint,
        evidence_epoch_id=population.evidence_epoch_id,
        expected_component_ids=(component,),
        attempted_component_ids=(component,),
        captured_component_ids=(component,),
        reported_result_row_count=len(rows),
        rows=rows,
        source_refs=tuple(
            dict.fromkeys(
                (
                    *population.source_refs,
                    design_result_ref,
                    lineage_ref,
                    projection_ref,
                )
            )
        ),
    )


__all__ = [
    "ColumnDesignResultProjectionError",
    "project_factual_design_results_to_component",
]
