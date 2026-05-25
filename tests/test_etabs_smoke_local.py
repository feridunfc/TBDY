from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.etabs_smoke


def _skip_unless_enabled() -> None:
    if os.environ.get("TBDY_RUN_ETABS_SMOKE") != "1":
        pytest.skip("ETABS smoke disabled; set TBDY_RUN_ETABS_SMOKE=1 to run locally")


def test_local_etabs_com_object_is_opt_in_and_safe():
    _skip_unless_enabled()

    try:
        import win32com.client  # type: ignore[import-not-found]
    except Exception as exc:
        pytest.skip(f"win32com.client unavailable: {exc}")

    try:
        etabs_object = win32com.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
    except Exception as exc:
        pytest.skip(f"No active ETABS COM object: {exc}")

    assert etabs_object is not None


@pytest.mark.etabs_smoke
def test_local_etabs_open_model_smoke_requires_explicit_model_opt_in():
    _skip_unless_enabled()
    if os.environ.get("TBDY_RUN_ETABS_MODEL_SMOKE") != "1":
        pytest.skip(
            "ETABS open-model smoke disabled; set TBDY_RUN_ETABS_MODEL_SMOKE=1 "
            "only when SapModel access is known to be safe"
        )

    try:
        import win32com.client  # type: ignore[import-not-found]
    except Exception as exc:
        pytest.skip(f"win32com.client unavailable: {exc}")

    try:
        etabs_object = win32com.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
    except Exception as exc:
        pytest.skip(f"No active ETABS COM object: {exc}")

    try:
        sap_model = etabs_object.SapModel
    except Exception as exc:
        pytest.skip(f"Active ETABS COM object does not expose SapModel safely: {exc}")

    if sap_model is None:
        pytest.skip("Active ETABS object has no SapModel")

    try:
        file_api = getattr(sap_model, "File", None)
        model_name = file_api.GetModelFilename() if file_api is not None else ""
    except Exception as exc:
        pytest.skip(f"Unable to read active ETABS model filename: {exc}")

    if not model_name:
        pytest.skip("No open ETABS model detected")

    assert isinstance(model_name, str)
