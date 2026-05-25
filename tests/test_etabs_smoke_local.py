from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.etabs_smoke


def _skip_unless_enabled() -> None:
    if os.environ.get("TBDY_RUN_ETABS_SMOKE") != "1":
        pytest.skip("ETABS smoke disabled; set TBDY_RUN_ETABS_SMOKE=1 to run locally")


def test_local_etabs_com_smoke_is_opt_in_and_safe():
    _skip_unless_enabled()

    try:
        import win32com.client  # type: ignore[import-not-found]
    except BaseException as exc:
        pytest.skip(f"win32com.client unavailable: {exc}")

    try:
        etabs_object = win32com.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
    except BaseException as exc:
        pytest.skip(f"No active ETABS COM object: {exc}")

    assert etabs_object is not None
