"""Causal owned-scratch lifecycle authority for live ETABS source protection.

B4S establishes ownership only after a complete causal chain:

trusted source context -> physical SOURCE_PRE -> unique OS copy ->
SCRATCH_AFTER_COPY equality -> typed factual OpenFile -> exact active-path
readback -> physical SOURCE_POST equality -> private positive issuance.

Paths, hashes, UUIDs, OpenFile success, model fingerprints, and EvidenceEpochs
are evidence constituents only; none independently establish scratch ownership.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import ntpath
import os
from os import PathLike
import shutil
import uuid

from tbdy_engine.etabs.oapi.file_lifecycle import OpenFileFact, open_file_from_session
from tbdy_engine.etabs.safety import reread_verified_session_identity
from tbdy_engine.integration.live_etabs_acquisition_context import (
    SourceModelIdentity,
    TrustedLiveAcquisitionContext,
)


OWNED_SCRATCH_CONTRACT = "TBDY_OWNED_ETABS_SCRATCH_CONTEXT_V1"
PHYSICAL_FILE_SNAPSHOT_CONTRACT = "TBDY_PHYSICAL_FILE_SNAPSHOT_V1"
SOURCE_INTEGRITY_CONTRACT = "TBDY_SOURCE_PHYSICAL_IMMUTABILITY_V1"
OWNERSHIP_PROOF_PREFIX = "etabs-owned-scratch:sha256:"
LIFECYCLE_EVIDENCE_PREFIX = "etabs-scratch-lifecycle:sha256:"

_OWNED_SCRATCH_ISSUANCE_KEY = object()


class ScratchLifecycleError(RuntimeError):
    """Fail-closed B4S lifecycle error with bounded factual diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        scratch_path: str | None = None,
        cleanup_status: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.scratch_path = scratch_path
        self.cleanup_status = cleanup_status


class ScratchCleanupStatus(str, Enum):
    NOT_CREATED = "NOT_CREATED"
    PRESERVED_FOR_EVIDENCE = "PRESERVED_FOR_EVIDENCE"


@dataclass(frozen=True, slots=True)
class PhysicalFileSnapshot:
    """Immutable physical-file facts; never semantic model identity/ownership."""

    canonical_absolute_path: str
    exists: bool
    file_size_bytes: int | None
    sha256_content_digest: str | None
    mtime_ns: int | None
    contract: str = PHYSICAL_FILE_SNAPSHOT_CONTRACT

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_absolute_path, str) or not self.canonical_absolute_path:
            raise ScratchLifecycleError(
                "physical file snapshot path must be nonblank",
                stage="physical_snapshot_contract",
            )
        if type(self.exists) is not bool:
            raise ScratchLifecycleError(
                "physical file snapshot exists flag must be boolean",
                stage="physical_snapshot_contract",
            )
        if self.contract != PHYSICAL_FILE_SNAPSHOT_CONTRACT:
            raise ScratchLifecycleError(
                "physical file snapshot contract mismatch",
                stage="physical_snapshot_contract",
            )
        if self.exists:
            if type(self.file_size_bytes) is not int or self.file_size_bytes < 0:
                raise ScratchLifecycleError(
                    "existing physical file requires nonnegative size",
                    stage="physical_snapshot_contract",
                )
            digest = self.sha256_content_digest
            if not isinstance(digest, str) or len(digest) != 64:
                raise ScratchLifecycleError(
                    "existing physical file requires SHA-256 content digest",
                    stage="physical_snapshot_contract",
                )
            if type(self.mtime_ns) is not int or self.mtime_ns < 0:
                raise ScratchLifecycleError(
                    "existing physical file requires mtime_ns",
                    stage="physical_snapshot_contract",
                )
        elif any(
            value is not None
            for value in (self.file_size_bytes, self.sha256_content_digest, self.mtime_ns)
        ):
            raise ScratchLifecycleError(
                "missing physical file cannot carry positive byte facts",
                stage="physical_snapshot_contract",
            )


@dataclass(frozen=True, slots=True)
class SourceImmutabilityFact:
    source_path: str
    pre_sha256: str
    post_sha256: str
    pre_size_bytes: int
    post_size_bytes: int
    verified_unchanged: bool
    contract: str = SOURCE_INTEGRITY_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != SOURCE_INTEGRITY_CONTRACT:
            raise ScratchLifecycleError(
                "source immutability contract mismatch",
                stage="source_integrity_contract",
            )
        if self.verified_unchanged is not True:
            raise ScratchLifecycleError(
                "positive source immutability fact must be verified",
                stage="source_integrity_contract",
            )


@dataclass(frozen=True, slots=True, init=False)
class OwnedScratchContext:
    """Factory-only positive result of the complete verified B4S lifecycle."""

    source_model_identity: SourceModelIdentity
    source_pre: PhysicalFileSnapshot
    scratch_path: str
    scratch_after_copy: PhysicalFileSnapshot
    open_file_fact: OpenFileFact
    active_model_path: str
    source_post: PhysicalFileSnapshot
    source_immutability: SourceImmutabilityFact
    lifecycle_provenance_refs: tuple[str, ...]
    ownership_proof_ref: str
    cleanup_status: ScratchCleanupStatus
    contract: str

    def __init__(
        self,
        *,
        _issuance_key: object = None,
        source_model_identity: SourceModelIdentity,
        source_pre: PhysicalFileSnapshot,
        scratch_path: str,
        scratch_after_copy: PhysicalFileSnapshot,
        open_file_fact: OpenFileFact,
        active_model_path: str,
        source_post: PhysicalFileSnapshot,
        source_immutability: SourceImmutabilityFact,
        lifecycle_provenance_refs: tuple[str, ...],
        ownership_proof_ref: str,
        cleanup_status: ScratchCleanupStatus,
        contract: str = OWNED_SCRATCH_CONTRACT,
    ) -> None:
        if _issuance_key is not _OWNED_SCRATCH_ISSUANCE_KEY:
            raise TypeError(
                "OwnedScratchContext is factory-created only; use "
                "create_owned_scratch_context"
            )
        if contract != OWNED_SCRATCH_CONTRACT:
            raise ScratchLifecycleError(
                "owned scratch contract mismatch",
                stage="owned_scratch_contract",
            )
        if cleanup_status is not ScratchCleanupStatus.PRESERVED_FOR_EVIDENCE:
            raise ScratchLifecycleError(
                "B4S positive scratch must be preserved for evidence",
                stage="owned_scratch_contract",
            )
        object.__setattr__(self, "source_model_identity", source_model_identity)
        object.__setattr__(self, "source_pre", source_pre)
        object.__setattr__(self, "scratch_path", scratch_path)
        object.__setattr__(self, "scratch_after_copy", scratch_after_copy)
        object.__setattr__(self, "open_file_fact", open_file_fact)
        object.__setattr__(self, "active_model_path", active_model_path)
        object.__setattr__(self, "source_post", source_post)
        object.__setattr__(self, "source_immutability", source_immutability)
        object.__setattr__(self, "lifecycle_provenance_refs", tuple(lifecycle_provenance_refs))
        object.__setattr__(self, "ownership_proof_ref", ownership_proof_ref)
        object.__setattr__(self, "cleanup_status", cleanup_status)
        object.__setattr__(self, "contract", contract)


def _canonical_absolute_path(value: str | PathLike[str], *, label: str) -> str:
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise ScratchLifecycleError(
            f"{label} must be a filesystem path",
            stage="path_validation",
        ) from exc
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise ScratchLifecycleError(
            f"{label} must be a nonblank text path",
            stage="path_validation",
        )
    expanded = os.path.expanduser(raw)
    if not os.path.isabs(expanded):
        raise ScratchLifecycleError(
            f"{label} must be absolute",
            stage="path_validation",
        )
    return os.path.normcase(os.path.normpath(os.path.abspath(expanded)))


def _canonical_model_reference(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ScratchLifecycleError(
            f"{label} must be a nonblank model reference",
            stage="source_reference_binding",
        )
    return ntpath.normcase(ntpath.normpath(value))


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_physical_file_snapshot(
    path: str | PathLike[str],
) -> PhysicalFileSnapshot:
    """Capture bounded physical facts without assigning semantic authority."""
    canonical = _canonical_absolute_path(path, label="physical file path")
    if not os.path.exists(canonical):
        return PhysicalFileSnapshot(
            canonical_absolute_path=canonical,
            exists=False,
            file_size_bytes=None,
            sha256_content_digest=None,
            mtime_ns=None,
        )
    if not os.path.isfile(canonical):
        raise ScratchLifecycleError(
            "physical evidence path exists but is not a regular file",
            stage="physical_snapshot_not_file",
        )
    stat = os.stat(canonical)
    return PhysicalFileSnapshot(
        canonical_absolute_path=canonical,
        exists=True,
        file_size_bytes=int(stat.st_size),
        sha256_content_digest=_sha256_file(canonical),
        mtime_ns=int(stat.st_mtime_ns),
    )


def _digest_ref(prefix: str, payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()


def _snapshot_payload(snapshot: PhysicalFileSnapshot) -> dict[str, object]:
    return {
        "canonical_absolute_path": snapshot.canonical_absolute_path,
        "exists": snapshot.exists,
        "file_size_bytes": snapshot.file_size_bytes,
        "sha256_content_digest": snapshot.sha256_content_digest,
        "mtime_ns": snapshot.mtime_ns,
        "contract": snapshot.contract,
    }


def _choose_scratch_destination(source_path: str, scratch_directory: str | None) -> str:
    directory = (
        os.path.dirname(source_path)
        if scratch_directory is None
        else _canonical_absolute_path(scratch_directory, label="scratch_directory")
    )
    if not os.path.isdir(directory):
        raise ScratchLifecycleError(
            "scratch directory must already exist",
            stage="scratch_directory_unavailable",
        )
    source_name = os.path.basename(source_path)
    stem, suffix = os.path.splitext(source_name)
    candidate = _canonical_absolute_path(
        os.path.join(directory, f"{stem}.tbdy-b4s-{uuid.uuid4().hex}{suffix}"),
        label="scratch destination",
    )
    return candidate


def _failure(
    message: str,
    *,
    stage: str,
    scratch_path: str | None = None,
) -> ScratchLifecycleError:
    cleanup = (
        ScratchCleanupStatus.PRESERVED_FOR_EVIDENCE.value
        if scratch_path and os.path.exists(scratch_path)
        else ScratchCleanupStatus.NOT_CREATED.value
    )
    return ScratchLifecycleError(
        message,
        stage=stage,
        scratch_path=scratch_path,
        cleanup_status=cleanup,
    )


def _issue_owned_scratch_context(
    *,
    context: TrustedLiveAcquisitionContext,
    source_pre: PhysicalFileSnapshot,
    scratch_after_copy: PhysicalFileSnapshot,
    open_file_fact: OpenFileFact,
    active_model_path: str,
    source_post: PhysicalFileSnapshot,
) -> OwnedScratchContext:
    source_digest = source_pre.sha256_content_digest
    post_digest = source_post.sha256_content_digest
    source_size = source_pre.file_size_bytes
    post_size = source_post.file_size_bytes
    if (
        source_digest is None
        or post_digest is None
        or source_size is None
        or post_size is None
    ):
        raise ScratchLifecycleError(
            "positive ownership requires complete source physical evidence",
            stage="positive_issuance",
        )
    integrity = SourceImmutabilityFact(
        source_path=source_pre.canonical_absolute_path,
        pre_sha256=source_digest,
        post_sha256=post_digest,
        pre_size_bytes=source_size,
        post_size_bytes=post_size,
        verified_unchanged=True,
    )
    lifecycle_payload = {
        "contract": OWNED_SCRATCH_CONTRACT,
        "source_model_ref": context.source_model_identity.source_model_ref,
        "source_pre": _snapshot_payload(source_pre),
        "scratch_after_copy": _snapshot_payload(scratch_after_copy),
        "open_file": {
            "path": open_file_fact.canonical_requested_path,
            "return_code": open_file_fact.return_code,
            "contract": open_file_fact.contract,
        },
        "active_model_path": active_model_path,
        "source_post": _snapshot_payload(source_post),
        "source_integrity_contract": integrity.contract,
        "acquisition_context_ref": context.acquisition_context_ref,
        "session_provenance_ref": context.session_provenance_ref,
    }
    lifecycle_ref = _digest_ref(LIFECYCLE_EVIDENCE_PREFIX, lifecycle_payload)
    proof_ref = _digest_ref(
        OWNERSHIP_PROOF_PREFIX,
        {
            **lifecycle_payload,
            "lifecycle_ref": lifecycle_ref,
        },
    )
    provenance = tuple(
        dict.fromkeys(
            (
                context.source_model_identity.source_model_ref,
                context.acquisition_context_ref,
                context.session_provenance_ref,
                lifecycle_ref,
            )
        )
    )
    return OwnedScratchContext(
        _issuance_key=_OWNED_SCRATCH_ISSUANCE_KEY,
        source_model_identity=context.source_model_identity,
        source_pre=source_pre,
        scratch_path=scratch_after_copy.canonical_absolute_path,
        scratch_after_copy=scratch_after_copy,
        open_file_fact=open_file_fact,
        active_model_path=active_model_path,
        source_post=source_post,
        source_immutability=integrity,
        lifecycle_provenance_refs=provenance,
        ownership_proof_ref=proof_ref,
        cleanup_status=ScratchCleanupStatus.PRESERVED_FOR_EVIDENCE,
    )


def create_owned_scratch_context(
    context: TrustedLiveAcquisitionContext,
    *,
    scratch_directory: str | PathLike[str] | None = None,
    timeout_seconds: float = 30.0,
) -> OwnedScratchContext:
    """Create, open, and causally qualify one disposable owned ETABS scratch.

    The protected source path is derived exclusively from the trusted acquisition
    context.  Callers may select only the containing scratch directory; they
    cannot supply a source path, ownership flag, proof ref, scratch UUID/name,
    or positive context data.
    """
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")

    source_reference = context.source_model_identity.normalized_model_reference
    source_path = _canonical_absolute_path(source_reference, label="protected source path")
    if _canonical_model_reference(source_path, label="physical source path") != (
        _canonical_model_reference(source_reference, label="trusted source model reference")
    ):
        raise _failure(
            "protected physical source path does not bind to SourceModelIdentity",
            stage="source_reference_binding",
        )

    # Re-read the active model before any copy so a stale acquisition context
    # cannot silently authorize a different currently-open source.
    try:
        current_identity = reread_verified_session_identity(context.verified_session)
    except Exception as exc:
        raise _failure(
            "active source model path could not be re-read before scratch creation",
            stage="source_reference_readback_failed",
        ) from exc
    if _canonical_model_reference(
        current_identity.model_full_path,
        label="active source model path",
    ) != _canonical_model_reference(
        source_reference,
        label="trusted source model reference",
    ):
        raise _failure(
            "active model no longer matches the trusted protected source reference",
            stage="source_reference_binding_mismatch",
        )

    source_pre = capture_physical_file_snapshot(source_path)
    if not source_pre.exists:
        raise _failure(
            "protected source file does not exist",
            stage="source_file_absent",
        )

    scratch_dir = (
        None
        if scratch_directory is None
        else _canonical_absolute_path(scratch_directory, label="scratch_directory")
    )
    scratch_path = _choose_scratch_destination(source_path, scratch_dir)
    if scratch_path == source_path:
        raise _failure(
            "scratch destination must be physically distinct from protected source",
            stage="source_equals_scratch",
            scratch_path=scratch_path,
        )
    if os.path.exists(scratch_path):
        raise _failure(
            "scratch destination already exists",
            stage="scratch_destination_exists",
            scratch_path=scratch_path,
        )

    try:
        shutil.copy2(source_path, scratch_path)
    except Exception as exc:
        raise _failure(
            "OS scratch copy failed",
            stage="copy_failed",
            scratch_path=scratch_path,
        ) from exc

    scratch_after_copy = capture_physical_file_snapshot(scratch_path)
    if not scratch_after_copy.exists:
        raise _failure(
            "scratch file is missing after OS copy",
            stage="scratch_missing_after_copy",
            scratch_path=scratch_path,
        )
    if scratch_after_copy.file_size_bytes != source_pre.file_size_bytes:
        raise _failure(
            "scratch byte size does not match SOURCE_PRE",
            stage="scratch_size_mismatch",
            scratch_path=scratch_path,
        )
    if scratch_after_copy.sha256_content_digest != source_pre.sha256_content_digest:
        raise _failure(
            "scratch SHA-256 does not match SOURCE_PRE",
            stage="scratch_hash_mismatch",
            scratch_path=scratch_path,
        )

    try:
        open_file_fact = open_file_from_session(
            context.verified_session,
            scratch_path,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        raise _failure(
            "typed ETABS File.OpenFile failed",
            stage="open_file_exception",
            scratch_path=scratch_path,
        ) from exc
    if not open_file_fact.success:
        raise _failure(
            f"ETABS File.OpenFile returned nonzero code {open_file_fact.return_code}",
            stage="open_file_nonzero",
            scratch_path=scratch_path,
        )

    try:
        active_identity = reread_verified_session_identity(context.verified_session)
        active_model_path = _canonical_absolute_path(
            active_identity.model_full_path,
            label="active scratch model path",
        )
    except Exception as exc:
        raise _failure(
            "active model path readback failed after OpenFile",
            stage="active_path_readback_failed",
            scratch_path=scratch_path,
        ) from exc
    if active_model_path != scratch_path:
        raise _failure(
            "active ETABS model path does not equal the exact scratch path",
            stage="active_path_mismatch",
            scratch_path=scratch_path,
        )

    source_post = capture_physical_file_snapshot(source_path)
    if not source_post.exists:
        raise _failure(
            "protected source is missing after scratch OpenFile",
            stage="source_post_missing",
            scratch_path=scratch_path,
        )
    if source_post.file_size_bytes != source_pre.file_size_bytes:
        raise _failure(
            "protected source size changed during scratch lifecycle",
            stage="source_post_size_changed",
            scratch_path=scratch_path,
        )
    if source_post.sha256_content_digest != source_pre.sha256_content_digest:
        raise _failure(
            "protected source SHA-256 changed during scratch lifecycle",
            stage="source_post_hash_changed",
            scratch_path=scratch_path,
        )

    return _issue_owned_scratch_context(
        context=context,
        source_pre=source_pre,
        scratch_after_copy=scratch_after_copy,
        open_file_fact=open_file_fact,
        active_model_path=active_model_path,
        source_post=source_post,
    )


__all__ = [
    "OWNED_SCRATCH_CONTRACT",
    "PHYSICAL_FILE_SNAPSHOT_CONTRACT",
    "OwnedScratchContext",
    "PhysicalFileSnapshot",
    "ScratchCleanupStatus",
    "ScratchLifecycleError",
    "SourceImmutabilityFact",
    "capture_physical_file_snapshot",
    "create_owned_scratch_context",
]
