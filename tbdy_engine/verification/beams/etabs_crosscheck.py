"""
ETABS crosscheck functions.
Compares engine outputs against ETABS design output.
Diagnostic only. Never mutates engine or verification results.
"""

from __future__ import annotations

from .etabs_design_output import ETABSDesignOutput
from .comparison_result import (
    ETABSComparisonItem,
    ETABSComparisonResult,
    STATUS_CLOSE,
    STATUS_MODERATE,
    STATUS_LARGE,
    STATUS_INCOMPLETE,
    overall_comparison_status,
)

# Design result imports — allowed for type checking only
from tbdy_engine.design.beams.beam_region_flexure import (
    BeamFlexureRegionDesignResult,
)
from tbdy_engine.design.beams.calculators.shear_reinforcement_design import (
    ShearReinforcementDesignResult,
)


# =============================================================================
# Core Numeric Comparison
# =============================================================================

def compare_numeric_field(
    *,
    field: str,
    engine_value: float | None,
    etabs_value: float | None,
    close_threshold_percent: float = 5.0,
    moderate_threshold_percent: float = 20.0,
) -> ETABSComparisonItem:
    """Compare a single numeric field between engine and ETABS."""
    # Missing values
    if engine_value is None or etabs_value is None:
        return ETABSComparisonItem(
            field=field,
            status=STATUS_INCOMPLETE,
            engine_value=engine_value,
            etabs_value=etabs_value,
            message="missing comparison value",
        )

    # Both zero
    if engine_value == 0 and etabs_value == 0:
        return ETABSComparisonItem(
            field=field,
            status=STATUS_CLOSE,
            engine_value=engine_value,
            etabs_value=etabs_value,
            difference=0.0,
            difference_percent=0.0,
            agreement_ratio=1.0,
        )

    # Engine zero, ETABS nonzero
    if engine_value == 0 and etabs_value != 0:
        return ETABSComparisonItem(
            field=field,
            status=STATUS_LARGE,
            engine_value=engine_value,
            etabs_value=etabs_value,
            difference=etabs_value - engine_value,
            difference_percent=None,
            agreement_ratio=None,
            message="engine value is zero while ETABS value is nonzero",
        )

    # Normal comparison
    difference = etabs_value - engine_value
    difference_percent = abs(difference) / abs(engine_value) * 100.0
    agreement_ratio = etabs_value / engine_value

    if difference_percent <= close_threshold_percent:
        status = STATUS_CLOSE
    elif difference_percent <= moderate_threshold_percent:
        status = STATUS_MODERATE
    else:
        status = STATUS_LARGE

    return ETABSComparisonItem(
        field=field,
        status=status,
        engine_value=engine_value,
        etabs_value=etabs_value,
        difference=difference,
        difference_percent=difference_percent,
        agreement_ratio=agreement_ratio,
        evidence={
            "close_threshold_percent": close_threshold_percent,
            "moderate_threshold_percent": moderate_threshold_percent,
        },
    )


# =============================================================================
# Flexure Comparison
# =============================================================================

def compare_flexure_region_to_etabs(
    flexure_region_result: BeamFlexureRegionDesignResult,
    etabs_output: ETABSDesignOutput,
    *,
    close_threshold_percent: float = 5.0,
    moderate_threshold_percent: float = 20.0,
) -> tuple[ETABSComparisonItem, ...]:
    """Compare engine flexure design result to ETABS design output per region."""
    mapping: dict[str, tuple[object | None, float | None]] = {
        "flexure:top_left_As_required_cm2": (
            flexure_region_result.regions.get("top_left"),
            etabs_output.top_left_As_required_cm2,
        ),
        "flexure:bottom_mid_As_required_cm2": (
            flexure_region_result.regions.get("bottom_mid"),
            etabs_output.bottom_mid_As_required_cm2,
        ),
        "flexure:top_right_As_required_cm2": (
            flexure_region_result.regions.get("top_right"),
            etabs_output.top_right_As_required_cm2,
        ),
    }

    items: list[ETABSComparisonItem] = []

    for field, (region, etabs_value) in mapping.items():
        engine_value = None if region is None else getattr(region, "As_design_required_cm2", None)
        items.append(compare_numeric_field(
            field=field,
            engine_value=engine_value,
            etabs_value=etabs_value,
            close_threshold_percent=close_threshold_percent,
            moderate_threshold_percent=moderate_threshold_percent,
        ))

    return tuple(items)


# =============================================================================
# Shear Comparison
# =============================================================================

def compare_shear_spacing_to_etabs(
    shear_result: ShearReinforcementDesignResult,
    etabs_output: ETABSDesignOutput,
    *,
    close_threshold_percent: float = 5.0,
    moderate_threshold_percent: float = 20.0,
) -> tuple[ETABSComparisonItem, ...]:
    """Compare engine shear spacing result to ETABS design output."""
    return (compare_numeric_field(
        field="shear:s_required_limited_mm",
        engine_value=shear_result.s_required_limited_mm,
        etabs_value=etabs_output.shear_spacing_required_mm,
        close_threshold_percent=close_threshold_percent,
        moderate_threshold_percent=moderate_threshold_percent,
    ),)


# =============================================================================
# Combined Runner
# =============================================================================

def compare_engine_to_etabs_design_output(
    *,
    beam_id: str,
    label: str,
    etabs_output: ETABSDesignOutput,
    flexure_region_result: BeamFlexureRegionDesignResult | None = None,
    shear_result: ShearReinforcementDesignResult | None = None,
    close_threshold_percent: float = 5.0,
    moderate_threshold_percent: float = 20.0,
) -> ETABSComparisonResult:
    """
    Compare engine outputs to ETABS design output.

    Diagnostic only. Never mutates design or verification results.
    ETABS disagreement does not mean engine FAIL.
    """
    # Identity guard
    if beam_id != etabs_output.beam_id or label != etabs_output.label:
        return ETABSComparisonResult(
            beam_id=beam_id,
            label=label,
            status=STATUS_INCOMPLETE,
            items=(),
            evidence={
                "method": "engine_to_etabs_design_crosscheck",
                "invalid_inputs": (
                    f"ETABS output identity mismatch: "
                    f"expected={beam_id}/{label}, "
                    f"etabs={etabs_output.beam_id}/{etabs_output.label}"
                ),
            },
        )

    items: list[ETABSComparisonItem] = []

    if flexure_region_result is not None:
        items.extend(compare_flexure_region_to_etabs(
            flexure_region_result,
            etabs_output,
            close_threshold_percent=close_threshold_percent,
            moderate_threshold_percent=moderate_threshold_percent,
        ))

    if shear_result is not None:
        items.extend(compare_shear_spacing_to_etabs(
            shear_result,
            etabs_output,
            close_threshold_percent=close_threshold_percent,
            moderate_threshold_percent=moderate_threshold_percent,
        ))

    items_tuple = tuple(items)

    return ETABSComparisonResult(
        beam_id=beam_id,
        label=label,
        status=overall_comparison_status(items_tuple),
        items=items_tuple,
        evidence={
            "method": "engine_to_etabs_design_crosscheck",
            "etabs_source": etabs_output.source,
            "close_threshold_percent": close_threshold_percent,
            "moderate_threshold_percent": moderate_threshold_percent,
        },
    )
