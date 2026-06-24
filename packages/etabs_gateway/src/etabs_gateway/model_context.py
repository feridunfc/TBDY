"""Pure normalization helpers for ETABS model context."""

from __future__ import annotations

from .contracts import ETABSModelContext, ETABSUnitContext


def normalize_model_path(raw_path: object) -> str | None:
    if raw_path is None:
        return None
    value = str(raw_path).strip()
    return value or None


def build_model_context(
    *,
    raw_model_path: object,
    raw_is_locked: object,
    present_units_code: int | None,
    present_units_name: str | None = None,
) -> ETABSModelContext:
    model_path = normalize_model_path(raw_model_path)

    if model_path is None:
        return ETABSModelContext(
            has_open_model=False,
            model_path=None,
            is_locked=None,
            units=None,
        )

    units = (
        None
        if present_units_code is None
        else ETABSUnitContext(
            present_units_code=int(present_units_code),
            display_name=present_units_name,
        )
    )

    return ETABSModelContext(
        has_open_model=True,
        model_path=model_path,
        is_locked=bool(raw_is_locked),
        units=units,
    )
