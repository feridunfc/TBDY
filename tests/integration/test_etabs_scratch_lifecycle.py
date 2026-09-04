from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import tbdy_engine.integration.etabs_scratch_lifecycle as subject
from tbdy_engine.etabs.oapi.file_lifecycle import OpenFileFact


@dataclass(frozen=True)
class _FakeSourceIdentity:
    source_model_ref: str
    normalized_model_reference: str


class _FakeTrustedContext:
    def __init__(self, source_path: str) -> None:
        self.source_model_identity = _FakeSourceIdentity(
            source_model_ref="source-model-ref:test",
            normalized_model_reference=os.path.normcase(
                os.path.normpath(os.path.abspath(source_path))
            ),
        )
        self.verified_session = object()
        self.acquisition_context_ref = "acquisition-context:test"
        self.session_provenance_ref = "session-provenance:test"


@pytest.fixture
def patched_context_type(monkeypatch):
    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", _FakeTrustedContext)


def _canonical(path: os.PathLike[str] | str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(os.fspath(path))))


def _install_active_model_fakes(monkeypatch, source_path: Path):
    state = {"active": _canonical(source_path), "open_calls": []}

    def reread(_session):
        return SimpleNamespace(model_full_path=state["active"])

    def open_file(_session, exact_path, *, timeout_seconds=30.0):
        canonical = _canonical(exact_path)
        state["open_calls"].append((canonical, timeout_seconds))
        state["active"] = canonical
        return OpenFileFact(canonical_requested_path=canonical, return_code=0)

    monkeypatch.setattr(subject, "reread_verified_session_identity", reread)
    monkeypatch.setattr(subject, "open_file_from_session", open_file)
    return state


def _source(tmp_path: Path, data: bytes = b"source-model-bytes") -> Path:
    path = tmp_path / "protected.edb"
    path.write_bytes(data)
    return path


def test_physical_file_snapshot_uses_real_bytes_sha256_and_mtime(tmp_path: Path):
    source = _source(tmp_path, b"abc123")

    snapshot = subject.capture_physical_file_snapshot(source)

    import hashlib

    assert snapshot.exists is True
    assert snapshot.canonical_absolute_path == _canonical(source)
    assert snapshot.file_size_bytes == 6
    assert snapshot.sha256_content_digest == hashlib.sha256(b"abc123").hexdigest()
    assert isinstance(snapshot.mtime_ns, int)
    assert snapshot.mtime_ns >= 0


def test_missing_physical_file_snapshot_is_negative_evidence(tmp_path: Path):
    snapshot = subject.capture_physical_file_snapshot(tmp_path / "missing.edb")

    assert snapshot.exists is False
    assert snapshot.file_size_bytes is None
    assert snapshot.sha256_content_digest is None
    assert snapshot.mtime_ns is None


def test_positive_owned_scratch_lifecycle_binds_full_causal_evidence(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    scratch_dir = tmp_path / "scratch"
    scratch_dir.mkdir()
    context = _FakeTrustedContext(str(source))
    state = _install_active_model_fakes(monkeypatch, source)

    owned = subject.create_owned_scratch_context(
        context,
        scratch_directory=scratch_dir,
        timeout_seconds=2.5,
    )

    assert isinstance(owned, subject.OwnedScratchContext)
    assert owned.source_model_identity is context.source_model_identity
    assert owned.source_pre.canonical_absolute_path == _canonical(source)
    assert owned.source_pre.exists is True
    assert owned.scratch_after_copy.exists is True
    assert owned.scratch_path == owned.scratch_after_copy.canonical_absolute_path
    assert owned.scratch_path != owned.source_pre.canonical_absolute_path
    assert owned.scratch_after_copy.file_size_bytes == owned.source_pre.file_size_bytes
    assert owned.scratch_after_copy.sha256_content_digest == owned.source_pre.sha256_content_digest
    assert owned.open_file_fact.success is True
    assert owned.active_model_path == owned.scratch_path
    assert owned.source_post.file_size_bytes == owned.source_pre.file_size_bytes
    assert owned.source_post.sha256_content_digest == owned.source_pre.sha256_content_digest
    assert owned.source_immutability.verified_unchanged is True
    assert owned.cleanup_status is subject.ScratchCleanupStatus.PRESERVED_FOR_EVIDENCE
    assert context.source_model_identity.source_model_ref in owned.lifecycle_provenance_refs
    assert context.acquisition_context_ref in owned.lifecycle_provenance_refs
    assert context.session_provenance_ref in owned.lifecycle_provenance_refs
    assert owned.ownership_proof_ref.startswith(subject.OWNERSHIP_PROOF_PREFIX)
    assert state["active"] == owned.scratch_path
    assert state["open_calls"] == [(owned.scratch_path, 2.5)]
    assert Path(owned.scratch_path).read_bytes() == source.read_bytes()


def test_caller_cannot_mint_positive_owned_scratch_from_identity_shaped_data(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    scratch_dir = tmp_path / "scratch"
    scratch_dir.mkdir()
    context = _FakeTrustedContext(str(source))
    _install_active_model_fakes(monkeypatch, source)
    owned = subject.create_owned_scratch_context(context, scratch_directory=scratch_dir)

    kwargs = {
        "source_model_identity": owned.source_model_identity,
        "source_pre": owned.source_pre,
        "scratch_path": owned.scratch_path,
        "scratch_after_copy": owned.scratch_after_copy,
        "open_file_fact": owned.open_file_fact,
        "active_model_path": owned.active_model_path,
        "source_post": owned.source_post,
        "source_immutability": owned.source_immutability,
        "lifecycle_provenance_refs": owned.lifecycle_provenance_refs,
        "ownership_proof_ref": owned.ownership_proof_ref,
        "cleanup_status": owned.cleanup_status,
    }
    with pytest.raises(TypeError, match="factory-created only"):
        subject.OwnedScratchContext(**kwargs)


def test_invalid_trusted_context_fails_closed():
    with pytest.raises(TypeError, match="TrustedLiveAcquisitionContext"):
        subject.create_owned_scratch_context(object())


def test_source_path_unavailable_fails_closed(
    monkeypatch,
    patched_context_type,
):
    context = _FakeTrustedContext("relative-source.edb")
    context.source_model_identity = _FakeSourceIdentity(
        source_model_ref="source-model-ref:test-relative",
        normalized_model_reference="relative-source.edb",
    )
    reached: list[str] = []

    def must_not_reread(_session):
        reached.append("session_identity_reread")
        raise AssertionError("relative source must fail before session identity reread")

    def must_not_copy(*_args, **_kwargs):
        reached.append("file_copy")
        raise AssertionError("relative source must fail before file copy")

    def must_not_open(*_args, **_kwargs):
        reached.append("open_file")
        raise AssertionError("relative source must fail before OpenFile")

    monkeypatch.setattr(subject, "reread_verified_session_identity", must_not_reread)
    monkeypatch.setattr(subject.shutil, "copy2", must_not_copy)
    monkeypatch.setattr(subject, "open_file_from_session", must_not_open)

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "path_validation"
    assert reached == []


def test_source_reference_binding_mismatch_fails_before_copy(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    context = _FakeTrustedContext(str(source))
    monkeypatch.setattr(
        subject,
        "reread_verified_session_identity",
        lambda _session: SimpleNamespace(model_full_path=str(tmp_path / "other.edb")),
    )
    copied = False

    def copy_should_not_run(*args, **kwargs):
        nonlocal copied
        copied = True

    monkeypatch.setattr(subject.shutil, "copy2", copy_should_not_run)

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "source_reference_binding_mismatch"
    assert copied is False


def test_source_file_absent_fails_closed(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = tmp_path / "missing.edb"
    context = _FakeTrustedContext(str(source))
    monkeypatch.setattr(
        subject,
        "reread_verified_session_identity",
        lambda _session: SimpleNamespace(model_full_path=str(source)),
    )

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "source_file_absent"


def test_existing_scratch_destination_is_rejected_before_copy(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    existing = tmp_path / "already.edb"
    existing.write_bytes(b"existing")
    context = _FakeTrustedContext(str(source))
    _install_active_model_fakes(monkeypatch, source)
    monkeypatch.setattr(subject, "_choose_scratch_destination", lambda *_: _canonical(existing))

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "scratch_destination_exists"
    assert existing.read_bytes() == b"existing"


def test_source_equals_scratch_is_rejected(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    context = _FakeTrustedContext(str(source))
    _install_active_model_fakes(monkeypatch, source)
    monkeypatch.setattr(subject, "_choose_scratch_destination", lambda *_: _canonical(source))

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "source_equals_scratch"
    assert source.read_bytes() == b"source-model-bytes"


def test_copy_exception_preserves_source_and_issues_no_positive_context(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    context = _FakeTrustedContext(str(source))
    _install_active_model_fakes(monkeypatch, source)
    monkeypatch.setattr(subject.shutil, "copy2", lambda *_: (_ for _ in ()).throw(OSError("copy")))

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "copy_failed"
    assert source.read_bytes() == b"source-model-bytes"


def test_scratch_missing_after_copy_is_rejected(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    context = _FakeTrustedContext(str(source))
    _install_active_model_fakes(monkeypatch, source)
    monkeypatch.setattr(subject.shutil, "copy2", lambda *_: None)

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "scratch_missing_after_copy"


def test_scratch_size_mismatch_is_rejected(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path, b"123456")
    context = _FakeTrustedContext(str(source))
    _install_active_model_fakes(monkeypatch, source)

    def wrong_copy(_src, dst):
        Path(dst).write_bytes(b"x")

    monkeypatch.setattr(subject.shutil, "copy2", wrong_copy)

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "scratch_size_mismatch"


def test_scratch_hash_mismatch_is_rejected(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path, b"AAAA")
    context = _FakeTrustedContext(str(source))
    _install_active_model_fakes(monkeypatch, source)

    def wrong_copy(_src, dst):
        Path(dst).write_bytes(b"BBBB")

    monkeypatch.setattr(subject.shutil, "copy2", wrong_copy)

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "scratch_hash_mismatch"


def test_open_file_nonzero_fails_without_positive_issuance(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    context = _FakeTrustedContext(str(source))
    state = _install_active_model_fakes(monkeypatch, source)

    def nonzero(_session, exact_path, *, timeout_seconds=30.0):
        canonical = _canonical(exact_path)
        return OpenFileFact(canonical_requested_path=canonical, return_code=3)

    monkeypatch.setattr(subject, "open_file_from_session", nonzero)
    issued = 0

    def issue_spy(**kwargs):
        nonlocal issued
        issued += 1
        raise AssertionError("positive issuer must not run")

    monkeypatch.setattr(subject, "_issue_owned_scratch_context", issue_spy)

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "open_file_nonzero"
    assert issued == 0
    assert state["active"] == _canonical(source)


def test_open_file_exception_fails_closed(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    context = _FakeTrustedContext(str(source))
    _install_active_model_fakes(monkeypatch, source)
    monkeypatch.setattr(
        subject,
        "open_file_from_session",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("OpenFile")),
    )

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "open_file_exception"


def test_active_model_path_readback_failure_is_rejected(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    context = _FakeTrustedContext(str(source))
    calls = 0

    def reread(_session):
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(model_full_path=str(source))
        raise RuntimeError("readback")

    monkeypatch.setattr(subject, "reread_verified_session_identity", reread)
    monkeypatch.setattr(
        subject,
        "open_file_from_session",
        lambda _session, exact_path, **_: OpenFileFact(
            canonical_requested_path=_canonical(exact_path),
            return_code=0,
        ),
    )

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "active_path_readback_failed"


def test_active_model_path_mismatch_is_rejected(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    context = _FakeTrustedContext(str(source))
    calls = 0

    def reread(_session):
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            model_full_path=str(source if calls == 1 else tmp_path / "wrong-active.edb")
        )

    monkeypatch.setattr(subject, "reread_verified_session_identity", reread)
    monkeypatch.setattr(
        subject,
        "open_file_from_session",
        lambda _session, exact_path, **_: OpenFileFact(
            canonical_requested_path=_canonical(exact_path),
            return_code=0,
        ),
    )

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "active_path_mismatch"


def test_source_post_missing_is_rejected(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    context = _FakeTrustedContext(str(source))
    state = _install_active_model_fakes(monkeypatch, source)
    real_open = subject.open_file_from_session

    def remove_source_after_open(session, exact_path, *, timeout_seconds=30.0):
        fact = real_open(session, exact_path, timeout_seconds=timeout_seconds)
        source.unlink()
        return fact

    monkeypatch.setattr(subject, "open_file_from_session", remove_source_after_open)

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "source_post_missing"
    assert state["active"] != _canonical(source)


def test_source_post_size_change_is_rejected(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path, b"AAAA")
    context = _FakeTrustedContext(str(source))
    _install_active_model_fakes(monkeypatch, source)
    real_open = subject.open_file_from_session

    def mutate_source(session, exact_path, *, timeout_seconds=30.0):
        fact = real_open(session, exact_path, timeout_seconds=timeout_seconds)
        source.write_bytes(b"LONGER")
        return fact

    monkeypatch.setattr(subject, "open_file_from_session", mutate_source)

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "source_post_size_changed"


def test_source_post_same_size_hash_change_is_rejected(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path, b"AAAA")
    context = _FakeTrustedContext(str(source))
    _install_active_model_fakes(monkeypatch, source)
    real_open = subject.open_file_from_session

    def mutate_source(session, exact_path, *, timeout_seconds=30.0):
        fact = real_open(session, exact_path, timeout_seconds=timeout_seconds)
        source.write_bytes(b"BBBB")
        return fact

    monkeypatch.setattr(subject, "open_file_from_session", mutate_source)

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.stage == "source_post_hash_changed"


def test_mtime_change_alone_does_not_override_equal_byte_integrity(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path, b"AAAA")
    context = _FakeTrustedContext(str(source))
    _install_active_model_fakes(monkeypatch, source)
    real_open = subject.open_file_from_session

    def touch_source(session, exact_path, *, timeout_seconds=30.0):
        fact = real_open(session, exact_path, timeout_seconds=timeout_seconds)
        current = source.stat().st_mtime_ns
        os.utime(source, ns=(current + 1_000_000, current + 1_000_000))
        return fact

    monkeypatch.setattr(subject, "open_file_from_session", touch_source)

    owned = subject.create_owned_scratch_context(context)

    assert owned.source_pre.sha256_content_digest == owned.source_post.sha256_content_digest
    assert owned.source_pre.file_size_bytes == owned.source_post.file_size_bytes
    assert owned.source_immutability.verified_unchanged is True


def test_failure_after_scratch_creation_reports_preserved_cleanup_status(
    monkeypatch,
    tmp_path: Path,
    patched_context_type,
):
    source = _source(tmp_path)
    context = _FakeTrustedContext(str(source))
    _install_active_model_fakes(monkeypatch, source)
    monkeypatch.setattr(
        subject,
        "open_file_from_session",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("fail")),
    )

    with pytest.raises(subject.ScratchLifecycleError) as caught:
        subject.create_owned_scratch_context(context)

    assert caught.value.cleanup_status == subject.ScratchCleanupStatus.PRESERVED_FOR_EVIDENCE.value
    assert caught.value.scratch_path is not None
    assert Path(caught.value.scratch_path).exists()
    assert source.exists()
