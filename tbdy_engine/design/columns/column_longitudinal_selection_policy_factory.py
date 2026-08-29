"""Production construction seam for the reviewed column longitudinal policy input.

This module does not define a second ranking policy and does not perform
selection. The reviewed engineering-selection values remain owned by
``column_longitudinal_ranking_authority``. This factory only materializes the
existing reviewed values into the input type required by the production
composition path.
"""
from __future__ import annotations

from tbdy_engine.design.columns.column_longitudinal_ranking_authority import (
    INPUT_REVIEW_REF,
    POLICY_ID,
    POLICY_VERSION,
    PRIMARY_OBJECTIVE,
    TIE_BREAKERS,
)
from tbdy_engine.design.columns.column_longitudinal_selection_contract import (
    ColumnLongitudinalSelectionPolicyInput,
)


def build_reviewed_column_longitudinal_selection_policy_input(
) -> ColumnLongitudinalSelectionPolicyInput:
    """Materialize the currently reviewed production policy input exactly."""

    return ColumnLongitudinalSelectionPolicyInput(
        policy_id=POLICY_ID,
        policy_version=POLICY_VERSION,
        primary_objective=PRIMARY_OBJECTIVE,
        tie_breakers=TIE_BREAKERS,
        review_ref=INPUT_REVIEW_REF,
    )


__all__ = ["build_reviewed_column_longitudinal_selection_policy_input"]
