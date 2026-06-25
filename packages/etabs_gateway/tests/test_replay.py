from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from etabs_gateway.contracts import (
    AttachMode,
    ETABSApplicationInfo,
    ETABSAttachment,
    ETABSGatewayContext,
    ETABSModelContext,
    ETABSUnitContext,
)
from etabs_gateway.errors import ETABSFixtureValidationError
from etabs_gateway.replay import (
    FixtureReplayProvider,
    build_gateway_context_fixture,
    canonical_gateway_context_fixture_json,
    context_from_payload,
    context_to_payload,
    dump_gateway_context_fixture,
    load_gateway_context_fixture,
    parse_gateway_context_fixture,
)


def sample_context(
    *,
    version: str = "23.0.0",
) -> ETABSGatewayContext:
    attached_at = datetime(
        2026,
        6,
        25,
        8,
        0,
        tzinfo=timezone.utc,
    )
    return ETABSGatewayContext(
        attachment=ETABSAttachment(
            prog_id="ETABS.TEST",
            attach_mode=AttachMode.RUNNING_INSTANCE,
            attached_at_utc=attached_at,
            worker_thread_id=777,
        ),
        application=ETABSApplicationInfo(
            version=version,
            process_id=None,
            attached_at_utc=attached_at,
        ),
        model=ETABSModelContext(
            has_open_model=True,
            model_path=r"C:\models\fixture.edb",
            is_locked=True,
            units=ETABSUnitContext(
                present_units_code=6,
                display_name=None,
            ),
        ),
        observed_at_utc=datetime(
            2026,
            6,
            25,
            8,
            0,
            1,
            tzinfo=timezone.utc,
        ),
    )


def fixture_envelope(
    context: ETABSGatewayContext | None = None,
) -> dict[str, object]:
    text = canonical_gateway_context_fixture_json(
        context or sample_context()
    )
    return json.loads(text)


def test_context_payload_round_trip_is_lossless() -> None:
    context = sample_context()

    payload = context_to_payload(context)
    rebuilt = context_from_payload(payload)

    assert rebuilt == context


def test_canonical_fixture_json_is_byte_deterministic() -> None:
    context = sample_context()

    first = canonical_gateway_context_fixture_json(context)
    second = canonical_gateway_context_fixture_json(context)

    assert first == second
    assert "\n" not in first
    assert " " not in first
    assert json.loads(first)["sha256"] == (
        build_gateway_context_fixture(context).sha256
    )


def test_semantically_identical_key_order_has_same_fingerprint() -> None:
    context = sample_context()
    envelope = fixture_envelope(context)
    reordered = {
        "sha256": envelope["sha256"],
        "context": envelope["context"],
        "fixture_type": envelope["fixture_type"],
        "schema_version": envelope["schema_version"],
    }

    replayed = parse_gateway_context_fixture(
        json.dumps(reordered, indent=4)
    )

    assert replayed.context == context
    assert replayed.sha256 == envelope["sha256"]


def test_dump_and_load_are_deterministic(tmp_path) -> None:
    path = tmp_path / "context.json"
    context = sample_context()

    written = dump_gateway_context_fixture(context, path)
    loaded = load_gateway_context_fixture(path)

    assert loaded == written
    assert path.read_text(encoding="utf-8").endswith("\n")
    assert path.read_text(encoding="utf-8").count("\n") == 1


def test_replay_provider_returns_only_immutable_context(tmp_path) -> None:
    path = tmp_path / "context.json"
    context = sample_context()
    fixture = dump_gateway_context_fixture(context, path)

    provider = FixtureReplayProvider.from_path(path)

    assert provider.read_context() == context
    assert provider.fingerprint == fixture.sha256
    assert not hasattr(provider, "application")
    assert not hasattr(provider, "model_api")


def test_changed_context_changes_fingerprint() -> None:
    first = build_gateway_context_fixture(sample_context())
    second = build_gateway_context_fixture(
        sample_context(version="23.0.1")
    )

    assert first.sha256 != second.sha256


def test_tampered_context_is_rejected_by_fingerprint() -> None:
    envelope = fixture_envelope()
    envelope["context"]["application"]["version"] = "tampered"

    with pytest.raises(ETABSFixtureValidationError) as caught:
        parse_gateway_context_fixture(json.dumps(envelope))

    assert caught.value.operation == "fixture_verify"
    assert caught.value.details["stage"] == "sha256_mismatch"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("fixture_type", "OTHER"),
    ],
)
def test_unsupported_envelope_identity_is_rejected(
    field: str,
    value: str,
) -> None:
    envelope = fixture_envelope()
    envelope[field] = value

    # Recompute is deliberately omitted: identity must fail before replay.
    with pytest.raises(ETABSFixtureValidationError):
        parse_gateway_context_fixture(json.dumps(envelope))


def test_unknown_envelope_key_is_rejected() -> None:
    envelope = fixture_envelope()
    envelope["unexpected"] = True

    with pytest.raises(ETABSFixtureValidationError) as caught:
        parse_gateway_context_fixture(json.dumps(envelope))

    assert caught.value.details["field_path"] == "$"
    assert caught.value.details["unexpected"] == ["unexpected"]


def test_unknown_nested_key_is_rejected_even_with_valid_fingerprint() -> None:
    envelope = fixture_envelope()
    context = envelope["context"]
    context["model"]["unexpected"] = 1

    unsigned = {
        "schema_version": envelope["schema_version"],
        "fixture_type": envelope["fixture_type"],
        "context": context,
    }
    import hashlib

    canonical = json.dumps(
        unsigned,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    envelope["sha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    with pytest.raises(ETABSFixtureValidationError) as caught:
        parse_gateway_context_fixture(json.dumps(envelope))

    assert caught.value.details["field_path"] == "context.model"
    assert caught.value.details["unexpected"] == ["unexpected"]


@pytest.mark.parametrize(
    "bad_timestamp",
    [
        "2026-06-25T08:00:00+03:00",
        "not-a-datetime",
    ],
)
def test_noncanonical_or_invalid_utc_is_rejected(
    bad_timestamp: str,
) -> None:
    payload = context_to_payload(sample_context())
    payload["observed_at_utc"] = bad_timestamp

    with pytest.raises(ETABSFixtureValidationError) as caught:
        context_from_payload(payload)

    assert caught.value.details["field_path"] == (
        "context.observed_at_utc"
    )


def test_invalid_attach_mode_is_rejected() -> None:
    payload = context_to_payload(sample_context())
    payload["attachment"]["attach_mode"] = "CREATE_NEW"

    with pytest.raises(ETABSFixtureValidationError) as caught:
        context_from_payload(payload)

    assert caught.value.details["field_path"] == (
        "context.attachment.attach_mode"
    )


def test_boolean_worker_thread_id_is_rejected() -> None:
    payload = context_to_payload(sample_context())
    payload["attachment"]["worker_thread_id"] = True

    with pytest.raises(ETABSFixtureValidationError) as caught:
        context_from_payload(payload)

    assert caught.value.details["field_path"] == (
        "context.attachment.worker_thread_id"
    )


def test_no_open_model_stale_values_are_rejected() -> None:
    payload = context_to_payload(sample_context())
    payload["model"]["has_open_model"] = False

    with pytest.raises(ETABSFixtureValidationError) as caught:
        context_from_payload(payload)

    assert caught.value.details["stage"] == "contract_validation"


def test_invalid_json_and_missing_file_are_typed(tmp_path) -> None:
    with pytest.raises(ETABSFixtureValidationError) as invalid:
        parse_gateway_context_fixture("{not-json")
    assert invalid.value.details["stage"] == "json_decode"

    with pytest.raises(ETABSFixtureValidationError) as missing:
        load_gateway_context_fixture(tmp_path / "missing.json")
    assert missing.value.details["stage"] == "file_read"
