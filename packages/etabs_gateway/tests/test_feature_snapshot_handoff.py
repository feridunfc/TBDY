from __future__ import annotations

import ast
import json
import sys
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GATEWAY_SOURCE = REPO_ROOT / "packages" / "etabs_gateway" / "src"
if str(GATEWAY_SOURCE) not in sys.path:
    sys.path.insert(0, str(GATEWAY_SOURCE))

from etabs_gateway.contracts import (  # noqa: E402
    AttachMode,
    ETABSApplicationInfo,
    ETABSAttachment,
    ETABSGatewayContext,
    ETABSModelContext,
)
from etabs_gateway.replay import FixtureReplayProvider  # noqa: E402
from tbdy_engine.features.etabs_gateway_handoff import (  # noqa: E402
    GatewayContextOrigin,
    GatewayFeatureSnapshotInput,
    build_feature_snapshot_from_gateway_context,
)
from tbdy_engine.features.evidence import FeatureEvidenceStatus  # noqa: E402
from tbdy_engine.features.value import FeatureValueStatus  # noqa: E402

FIXTURE_PATH = (
    REPO_ROOT
    / "packages"
    / "etabs_gateway"
    / "tests"
    / "fixtures"
    / "gateway_context_v1.json"
)


def build_replay_snapshot():
    provider = FixtureReplayProvider.from_path(FIXTURE_PATH)
    handoff_input = GatewayFeatureSnapshotInput(
        context=provider.read_context(),
        origin=GatewayContextOrigin.FIXTURE_REPLAY,
        source_fingerprint=provider.fingerprint,
    )
    return provider, build_feature_snapshot_from_gateway_context(handoff_input)


def closed_model_context() -> ETABSGatewayContext:
    attached_at = datetime(2026, 6, 25, 8, 0, tzinfo=timezone.utc)
    return ETABSGatewayContext(
        attachment=ETABSAttachment(
            prog_id="ETABS.TEST",
            attach_mode=AttachMode.RUNNING_INSTANCE,
            attached_at_utc=attached_at,
            worker_thread_id=777,
        ),
        application=ETABSApplicationInfo(
            version="23.0.0",
            process_id=None,
            attached_at_utc=attached_at,
        ),
        model=ETABSModelContext(
            has_open_model=False,
            model_path=None,
            is_locked=None,
            units=None,
        ),
        observed_at_utc=datetime(2026, 6, 25, 8, 0, 1, tzinfo=timezone.utc),
    )


def test_fixture_replay_builds_gateway_context_feature_snapshot() -> None:
    provider, snapshot = build_replay_snapshot()
    assert snapshot.component_type == "ETABS_MODEL_CONTEXT"
    assert snapshot.component_id.startswith("ETABS_CONTEXT:")
    assert snapshot.identity["origin"] == "FIXTURE_REPLAY"
    assert snapshot.identity["source_fingerprint"] == provider.fingerprint
    assert snapshot.identity["source_system"] == "ETABS"


def test_snapshot_contains_expected_data_only_features() -> None:
    _, snapshot = build_replay_snapshot()
    assert tuple(snapshot.features) == (
        "etabs.attachment.prog_id",
        "etabs.attachment.mode",
        "etabs.attachment.worker_thread_id",
        "etabs.application.version",
        "etabs.application.process_id",
        "etabs.model.open",
        "etabs.model.path",
        "etabs.model.locked",
        "etabs.model.units_code",
        "etabs.model.units_display_name",
    )
    assert snapshot.features["etabs.application.version"].value == "23.0.0"
    assert snapshot.features["etabs.model.open"].value is True
    assert snapshot.features["etabs.model.units_code"].value == 6


def test_feature_evidence_preserves_field_path_and_origin() -> None:
    provider, snapshot = build_replay_snapshot()
    evidence = snapshot.evidence_by_feature["etabs.model.units_code"][0]
    assert evidence.evidence_status is FeatureEvidenceStatus.FULL
    assert evidence.source_table == "ETABS_GATEWAY_CONTEXT"
    assert evidence.actual_table_name == "ETABSGatewayContext"
    assert evidence.source_column == "model.units.present_units_code"
    assert evidence.source_row["origin"] == "FIXTURE_REPLAY"
    assert evidence.source_row["source_fingerprint"] == provider.fingerprint


def test_snapshot_contains_no_engineering_verdict_payload() -> None:
    _, snapshot = build_replay_snapshot()
    payload = snapshot.as_dict()
    rendered = json.dumps(payload, sort_keys=True)
    forbidden_keys = {
        "check_id",
        "check_result",
        "check_results",
        "pass_rule",
        "ratio",
        "formula",
    }

    def walk(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                assert str(key).casefold() not in forbidden_keys
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(payload)
    assert '"PASS"' not in rendered
    assert '"FAIL"' not in rendered
    assert '"OK"' not in rendered


def test_handoff_is_deterministic() -> None:
    provider = FixtureReplayProvider.from_path(FIXTURE_PATH)
    handoff_input = GatewayFeatureSnapshotInput(
        context=provider.read_context(),
        origin="FIXTURE_REPLAY",
        source_fingerprint=provider.fingerprint,
    )
    first = build_feature_snapshot_from_gateway_context(handoff_input)
    second = build_feature_snapshot_from_gateway_context(handoff_input)
    assert first.as_dict() == second.as_dict()
    assert first.component_id == second.component_id


def test_replay_origin_requires_sha256_fingerprint() -> None:
    provider = FixtureReplayProvider.from_path(FIXTURE_PATH)
    with pytest.raises(ValueError, match="requires source_fingerprint"):
        GatewayFeatureSnapshotInput(
            context=provider.read_context(),
            origin=GatewayContextOrigin.FIXTURE_REPLAY,
        )


def test_invalid_fingerprint_is_rejected() -> None:
    provider = FixtureReplayProvider.from_path(FIXTURE_PATH)
    with pytest.raises(ValueError, match="SHA-256"):
        GatewayFeatureSnapshotInput(
            context=provider.read_context(),
            origin=GatewayContextOrigin.FIXTURE_REPLAY,
            source_fingerprint="not-a-sha256",
        )


def test_live_origin_allows_no_fingerprint() -> None:
    provider = FixtureReplayProvider.from_path(FIXTURE_PATH)
    snapshot = build_feature_snapshot_from_gateway_context(
        GatewayFeatureSnapshotInput(
            context=provider.read_context(),
            origin=GatewayContextOrigin.LIVE_READ_ONLY,
        )
    )
    assert snapshot.identity["origin"] == "LIVE_READ_ONLY"
    assert snapshot.identity["source_fingerprint"] is None


def test_closed_model_context_emits_missing_model_features() -> None:
    snapshot = build_feature_snapshot_from_gateway_context(
        GatewayFeatureSnapshotInput(
            context=closed_model_context(),
            origin=GatewayContextOrigin.LIVE_READ_ONLY,
        )
    )
    assert snapshot.features["etabs.model.open"].status is FeatureValueStatus.RESOLVED
    for feature_name in (
        "etabs.model.path",
        "etabs.model.locked",
        "etabs.model.units_code",
        "etabs.model.units_display_name",
    ):
        feature = snapshot.features[feature_name]
        assert feature.status is FeatureValueStatus.MISSING
        assert feature.evidence[0].evidence_status is FeatureEvidenceStatus.MISSING
        assert feature.evidence[0].reason


def test_snapshot_contract_is_immutable() -> None:
    _, snapshot = build_replay_snapshot()
    with pytest.raises(FrozenInstanceError):
        snapshot.component_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        snapshot.identity["origin"] = "changed"  # type: ignore[index]


def test_handoff_rejects_non_gateway_context() -> None:
    with pytest.raises(TypeError, match="ETABSGatewayContext"):
        GatewayFeatureSnapshotInput(
            context=object(),  # type: ignore[arg-type]
            origin=GatewayContextOrigin.LIVE_READ_ONLY,
        )


def test_handoff_source_has_no_com_or_check_engine_calls() -> None:
    path = REPO_ROOT / "tbdy_engine" / "features" / "etabs_gateway_handoff.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden_names = {
        "GetActiveObject",
        "SapModel",
        "RunAnalysis",
        "SetPresentUnits",
        "GetTableForDisplayArray",
        "CheckResult",
        "CheckEngine",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                final_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                final_name = node.func.attr
            else:
                final_name = ""
            assert final_name not in forbidden_names
        if isinstance(node, ast.Attribute):
            assert node.attr not in forbidden_names
