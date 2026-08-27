from __future__ import annotations

import hashlib
import inspect
import json
import ntpath
import subprocess
import sys

import pytest

from tbdy_engine import model_identity as canonical
from tbdy_engine.integration import live_beam_geometry_f0 as legacy

MODEL_PATH = r"C:\Projects\TBDY\Kres.edb"


def _frozen_expected(path: str) -> str:
    payload = {
        "contract": "ETABS_MODEL_IDENTITY_V1",
        "model_path": ntpath.normcase(ntpath.normpath(path.strip())),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "etabs:model-identity:sha256:" + hashlib.sha256(encoded).hexdigest()


def test_old_import_contract_reexports_canonical_owner() -> None:
    assert legacy.model_fingerprint_from_path is canonical.model_fingerprint_from_path
    assert (
        legacy.normalize_observed_etabs_model_path
        is canonical.normalize_observed_etabs_model_path
    )
    assert legacy.MODEL_IDENTITY_CONTRACT == canonical.MODEL_IDENTITY_CONTRACT
    assert legacy.MODEL_FINGERPRINT_PREFIX == canonical.MODEL_FINGERPRINT_PREFIX


def test_new_canonical_import_works_in_fresh_interpreter_without_integration_import() -> None:
    code = (
        "import sys; "
        "import tbdy_engine.model_identity as m; "
        "assert 'tbdy_engine.integration' not in sys.modules; "
        "assert 'tbdy_engine.integration.f0_evidence_adapter' not in sys.modules; "
        "assert 'comtypes' not in sys.modules; "
        f"assert m.model_fingerprint_from_path({MODEL_PATH!r}) == {_frozen_expected(MODEL_PATH)!r}"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_old_new_fingerprint_is_exact_frozen_bytes() -> None:
    expected = _frozen_expected(MODEL_PATH)
    assert canonical.model_fingerprint_from_path(MODEL_PATH) == expected
    assert legacy.model_fingerprint_from_path(MODEL_PATH) == expected


def test_path_normalization_regression() -> None:
    first = r"C:\Projects\TBDY\.\Sub\..\Kres.edb"
    second = r"c:/projects/tbdy/kres.edb"
    expected = ntpath.normcase(ntpath.normpath(second))
    assert canonical.normalize_observed_etabs_model_path(first) == expected
    assert canonical.normalize_observed_etabs_model_path(second) == expected
    assert canonical.model_fingerprint_from_path(first) == canonical.model_fingerprint_from_path(second)


@pytest.mark.parametrize("value", [None, "", "   ", "\t\r\n"])
def test_blank_path_fails_closed_through_old_and_new_contracts(value: object) -> None:
    with pytest.raises(canonical.ModelIdentityError) as canonical_exc:
        canonical.model_fingerprint_from_path(value)
    assert canonical_exc.value.status == "BLOCKED_BY_MISSING_LIVE_EPOCH_IDENTITY"

    with pytest.raises(legacy.MissingLiveEpochIdentityError) as legacy_exc:
        legacy.model_fingerprint_from_path(value)
    assert legacy_exc.value.status == "BLOCKED_BY_MISSING_LIVE_EPOCH_IDENTITY"


def test_no_duplicate_model_fingerprint_or_path_normalization_implementation() -> None:
    legacy_source = inspect.getsource(legacy)
    canonical_source = inspect.getsource(canonical)
    assert "def model_fingerprint_from_path" not in legacy_source
    assert "def normalize_observed_etabs_model_path" not in legacy_source
    assert canonical_source.count("def model_fingerprint_from_path") == 1
    assert canonical_source.count("def normalize_observed_etabs_model_path") == 1
