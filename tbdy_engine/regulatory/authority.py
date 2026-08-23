"""F0.9 source-bound regulatory authority metadata and validation.

This module is a bounded constitutional extension to the existing F0 regulatory
kernel.  It does not execute engineering formulas, discover rules, or create a
second regulatory engine.  Source authority is explicit composition/review
metadata consumed by the existing ``RegulatoryCompiler``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import importlib.util
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from .contracts import CheckSpec, RegulatoryDerivationSpec, RuleId
from .registry import RegulatoryRegistry

RuleDefinition = RegulatoryDerivationSpec | CheckSpec


class RegulatoryAuthorityError(ValueError):
    """Deterministic fail-closed source-authority validation failure."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = _text(code, "authority error code")
        self.detail = _text(detail, "authority error detail")
        super().__init__(f"{self.code}: {self.detail}")


class AuthorityReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _strings(values: Sequence[str], label: str, *, require_nonempty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{label} must be a sequence of strings")
    items = tuple(_text(item, label) for item in values)
    if require_nonempty and not items:
        raise ValueError(f"{label} must contain at least one value")
    if len(items) != len(set(items)):
        raise ValueError(f"{label} contains duplicate values")
    return tuple(sorted(items))


def _unique(items: Sequence[object], attr: str, label: str) -> None:
    identities = [getattr(item, attr) for item in items]
    if len(identities) != len(set(identities)):
        raise ValueError(f"duplicate {label} identity")


@dataclass(frozen=True, slots=True, order=True)
class RegulatorySourceDocument:
    source_id: str
    title: str
    edition: str
    issuer: str
    jurisdiction: str
    source_fingerprint: str

    def __post_init__(self) -> None:
        for label in ("source_id", "title", "edition", "issuer", "jurisdiction", "source_fingerprint"):
            _text(getattr(self, label), label)


@dataclass(frozen=True, slots=True, order=True)
class SourceAnchor:
    anchor_id: str
    source_id: str
    locator: str

    def __post_init__(self) -> None:
        _text(self.anchor_id, "anchor_id")
        _text(self.source_id, "source_id")
        _text(self.locator, "locator")


@dataclass(frozen=True, slots=True)
class RegulatoryClaim:
    claim_id: str
    claim_version: str
    anchor_refs: tuple[str, ...]
    normalized_statement: str

    def __init__(
        self,
        *,
        claim_id: str,
        claim_version: str,
        anchor_refs: Sequence[str],
        normalized_statement: str,
    ) -> None:
        object.__setattr__(self, "claim_id", _text(claim_id, "claim_id"))
        object.__setattr__(self, "claim_version", _text(claim_version, "claim_version"))
        object.__setattr__(self, "anchor_refs", _strings(anchor_refs, "anchor_ref", require_nonempty=True))
        object.__setattr__(self, "normalized_statement", _text(normalized_statement, "normalized_statement"))

    @property
    def sort_key(self) -> tuple[str, str]:
        return self.claim_id, self.claim_version


def regulatory_claim_fingerprint(
    *,
    claim: RegulatoryClaim,
    anchors: Sequence[SourceAnchor],
    source_documents: Sequence[RegulatorySourceDocument],
) -> str:
    """Fingerprint the exact reviewed claim and its resolved source chain.

    The digest contains no source text and no repository identity.  Only the
    normalized claim plus deterministic anchor/source metadata are included.
    """

    if not isinstance(claim, RegulatoryClaim):
        raise TypeError("claim must be RegulatoryClaim")
    anchor_items = tuple(anchors)
    source_items = tuple(source_documents)
    if any(not isinstance(item, SourceAnchor) for item in anchor_items):
        raise TypeError("anchors must contain SourceAnchor")
    if any(not isinstance(item, RegulatorySourceDocument) for item in source_items):
        raise TypeError("source_documents must contain RegulatorySourceDocument")
    _unique(anchor_items, "anchor_id", "anchor")
    _unique(source_items, "source_id", "source")

    anchors_by_id = {item.anchor_id: item for item in anchor_items}
    sources_by_id = {item.source_id: item for item in source_items}
    resolved_anchors: list[SourceAnchor] = []
    resolved_sources: dict[str, RegulatorySourceDocument] = {}
    for anchor_ref in claim.anchor_refs:
        try:
            anchor = anchors_by_id[anchor_ref]
            source = sources_by_id[anchor.source_id]
        except KeyError as exc:
            raise RegulatoryAuthorityError(
                "BROKEN_REGULATORY_SOURCE_CHAIN",
                f"claim {claim.claim_id} cannot resolve anchor/source {anchor_ref}",
            ) from exc
        resolved_anchors.append(anchor)
        resolved_sources[source.source_id] = source

    payload = {
        "claim": [
            claim.claim_id,
            claim.claim_version,
            claim.normalized_statement,
            list(claim.anchor_refs),
        ],
        "anchors": [
            [item.anchor_id, item.source_id, item.locator]
            for item in sorted(resolved_anchors, key=lambda x: x.anchor_id)
        ],
        "sources": [
            [
                item.source_id,
                item.edition,
                item.source_fingerprint,
                item.title,
                item.issuer,
                item.jurisdiction,
            ]
            for item in sorted(resolved_sources.values(), key=lambda x: x.source_id)
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthorityReviewRecord:
    review_id: str
    claim_id: str
    status: AuthorityReviewStatus
    review_version: str
    reviewed_claim_fingerprint: str
    review_basis_refs: tuple[str, ...] = field(default_factory=tuple)

    def __init__(
        self,
        *,
        review_id: str,
        claim_id: str,
        status: AuthorityReviewStatus,
        review_version: str,
        reviewed_claim_fingerprint: str,
        review_basis_refs: Sequence[str] = (),
    ) -> None:
        if not isinstance(status, AuthorityReviewStatus):
            raise TypeError("status must be AuthorityReviewStatus")
        object.__setattr__(self, "review_id", _text(review_id, "review_id"))
        object.__setattr__(self, "claim_id", _text(claim_id, "claim_id"))
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "review_version", _text(review_version, "review_version"))
        object.__setattr__(
            self,
            "reviewed_claim_fingerprint",
            _text(reviewed_claim_fingerprint, "reviewed_claim_fingerprint"),
        )
        object.__setattr__(self, "review_basis_refs", _strings(review_basis_refs, "review_basis_ref"))

    @property
    def sort_key(self) -> tuple[str, str]:
        return self.review_id, self.review_version


@dataclass(frozen=True, slots=True)
class ApprovedImplementationBinding:
    binding_id: str
    rule_id: RuleId
    claim_refs: tuple[str, ...]
    review_refs: tuple[str, ...]
    evaluator_binding_id: str
    rule_version: str
    implementation_modules: tuple[str, ...]
    approved_implementation_fingerprint: str
    binding_version: str

    def __init__(
        self,
        *,
        binding_id: str,
        rule_id: RuleId,
        claim_refs: Sequence[str],
        review_refs: Sequence[str],
        evaluator_binding_id: str,
        rule_version: str,
        implementation_modules: Sequence[str],
        approved_implementation_fingerprint: str,
        binding_version: str,
    ) -> None:
        if not isinstance(rule_id, RuleId):
            raise TypeError("rule_id must be RuleId")
        object.__setattr__(self, "binding_id", _text(binding_id, "binding_id"))
        object.__setattr__(self, "rule_id", rule_id)
        object.__setattr__(self, "claim_refs", _strings(claim_refs, "claim_ref", require_nonempty=True))
        object.__setattr__(self, "review_refs", _strings(review_refs, "review_ref", require_nonempty=True))
        object.__setattr__(self, "evaluator_binding_id", _text(evaluator_binding_id, "evaluator_binding_id"))
        object.__setattr__(self, "rule_version", _text(rule_version, "rule_version"))
        object.__setattr__(
            self,
            "implementation_modules",
            _strings(implementation_modules, "implementation_module", require_nonempty=True),
        )
        object.__setattr__(
            self,
            "approved_implementation_fingerprint",
            _text(approved_implementation_fingerprint, "approved_implementation_fingerprint"),
        )
        object.__setattr__(self, "binding_version", _text(binding_version, "binding_version"))

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return self.rule_id.value, self.binding_id, self.binding_version


@dataclass(frozen=True, slots=True)
class ValidatedRuleAuthority:
    rule_id: RuleId
    binding_id: str
    approved_implementation_fingerprint: str
    claim_refs: tuple[str, ...]
    review_refs: tuple[str, ...]

    @property
    def binding_ref(self) -> str:
        return f"{self.rule_id.value}:{self.binding_id}"

    @property
    def fingerprint_ref(self) -> str:
        return f"{self.rule_id.value}:{self.approved_implementation_fingerprint}"

    @property
    def sort_key(self) -> tuple[str, str]:
        return self.rule_id.value, self.binding_id


@dataclass(frozen=True, slots=True)
class RegulatoryAuthorityCatalog:
    source_documents: tuple[RegulatorySourceDocument, ...]
    anchors: tuple[SourceAnchor, ...]
    claims: tuple[RegulatoryClaim, ...]
    review_records: tuple[AuthorityReviewRecord, ...]
    implementation_bindings: tuple[ApprovedImplementationBinding, ...]
    catalog_version: str
    _sources_by_id: Mapping[str, RegulatorySourceDocument] = field(repr=False, compare=False)
    _anchors_by_id: Mapping[str, SourceAnchor] = field(repr=False, compare=False)
    _claims_by_id: Mapping[str, RegulatoryClaim] = field(repr=False, compare=False)
    _reviews_by_id: Mapping[str, AuthorityReviewRecord] = field(repr=False, compare=False)
    _bindings_by_id: Mapping[str, ApprovedImplementationBinding] = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        source_documents: Sequence[RegulatorySourceDocument] = (),
        anchors: Sequence[SourceAnchor] = (),
        claims: Sequence[RegulatoryClaim] = (),
        review_records: Sequence[AuthorityReviewRecord] = (),
        implementation_bindings: Sequence[ApprovedImplementationBinding] = (),
    ) -> None:
        sources = tuple(source_documents)
        anchor_items = tuple(anchors)
        claim_items = tuple(claims)
        reviews = tuple(review_records)
        bindings = tuple(implementation_bindings)
        expected = (
            (sources, RegulatorySourceDocument, "source_documents"),
            (anchor_items, SourceAnchor, "anchors"),
            (claim_items, RegulatoryClaim, "claims"),
            (reviews, AuthorityReviewRecord, "review_records"),
            (bindings, ApprovedImplementationBinding, "implementation_bindings"),
        )
        for items, item_type, label in expected:
            if any(not isinstance(item, item_type) for item in items):
                raise TypeError(f"{label} must contain {item_type.__name__}")

        _unique(sources, "source_id", "source")
        _unique(anchor_items, "anchor_id", "anchor")
        _unique(claim_items, "claim_id", "claim")
        _unique(reviews, "review_id", "review")
        _unique(bindings, "binding_id", "binding")

        sources = tuple(sorted(sources, key=lambda item: item.source_id))
        anchor_items = tuple(sorted(anchor_items, key=lambda item: item.anchor_id))
        claim_items = tuple(sorted(claim_items, key=lambda item: item.sort_key))
        reviews = tuple(sorted(reviews, key=lambda item: item.sort_key))
        bindings = tuple(sorted(bindings, key=lambda item: item.sort_key))

        sources_by_id = {item.source_id: item for item in sources}
        anchors_by_id = {item.anchor_id: item for item in anchor_items}
        claims_by_id = {item.claim_id: item for item in claim_items}
        reviews_by_id = {item.review_id: item for item in reviews}
        bindings_by_id = {item.binding_id: item for item in bindings}

        for anchor in anchor_items:
            if anchor.source_id not in sources_by_id:
                raise ValueError(f"missing source document for anchor {anchor.anchor_id}: {anchor.source_id}")
        for claim in claim_items:
            missing = tuple(ref for ref in claim.anchor_refs if ref not in anchors_by_id)
            if missing:
                raise ValueError(f"missing anchor for claim {claim.claim_id}: {','.join(missing)}")
        for review in reviews:
            if review.claim_id not in claims_by_id:
                raise ValueError(f"missing claim for review {review.review_id}: {review.claim_id}")
        for binding in bindings:
            missing_claims = tuple(ref for ref in binding.claim_refs if ref not in claims_by_id)
            if missing_claims:
                raise ValueError(
                    f"missing claim for implementation binding {binding.binding_id}: {','.join(missing_claims)}"
                )
            missing_reviews = tuple(ref for ref in binding.review_refs if ref not in reviews_by_id)
            if missing_reviews:
                raise ValueError(
                    f"missing review for implementation binding {binding.binding_id}: {','.join(missing_reviews)}"
                )
            unrelated_reviews = tuple(
                ref for ref in binding.review_refs if reviews_by_id[ref].claim_id not in binding.claim_refs
            )
            if unrelated_reviews:
                raise ValueError(
                    f"binding review does not review a bound claim {binding.binding_id}: {','.join(unrelated_reviews)}"
                )

        payload = {
            "sources": [
                [
                    item.source_id,
                    item.title,
                    item.edition,
                    item.issuer,
                    item.jurisdiction,
                    item.source_fingerprint,
                ]
                for item in sources
            ],
            "anchors": [[item.anchor_id, item.source_id, item.locator] for item in anchor_items],
            "claims": [
                [item.claim_id, item.claim_version, list(item.anchor_refs), item.normalized_statement]
                for item in claim_items
            ],
            "reviews": [
                [
                    item.review_id,
                    item.claim_id,
                    item.status.value,
                    item.review_version,
                    item.reviewed_claim_fingerprint,
                    list(item.review_basis_refs),
                ]
                for item in reviews
            ],
            "bindings": [
                [
                    item.binding_id,
                    item.rule_id.value,
                    list(item.claim_refs),
                    list(item.review_refs),
                    item.evaluator_binding_id,
                    item.rule_version,
                    list(item.implementation_modules),
                    item.approved_implementation_fingerprint,
                    item.binding_version,
                ]
                for item in bindings
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        catalog_version = "f0.9:" + hashlib.sha256(encoded).hexdigest()

        object.__setattr__(self, "source_documents", sources)
        object.__setattr__(self, "anchors", anchor_items)
        object.__setattr__(self, "claims", claim_items)
        object.__setattr__(self, "review_records", reviews)
        object.__setattr__(self, "implementation_bindings", bindings)
        object.__setattr__(self, "catalog_version", catalog_version)
        object.__setattr__(self, "_sources_by_id", MappingProxyType(sources_by_id))
        object.__setattr__(self, "_anchors_by_id", MappingProxyType(anchors_by_id))
        object.__setattr__(self, "_claims_by_id", MappingProxyType(claims_by_id))
        object.__setattr__(self, "_reviews_by_id", MappingProxyType(reviews_by_id))
        object.__setattr__(self, "_bindings_by_id", MappingProxyType(bindings_by_id))

    def source(self, source_id: str) -> RegulatorySourceDocument:
        return self._sources_by_id[_text(source_id, "source_id")]

    def anchor(self, anchor_id: str) -> SourceAnchor:
        return self._anchors_by_id[_text(anchor_id, "anchor_id")]

    def claim(self, claim_id: str) -> RegulatoryClaim:
        return self._claims_by_id[_text(claim_id, "claim_id")]

    def review(self, review_id: str) -> AuthorityReviewRecord:
        return self._reviews_by_id[_text(review_id, "review_id")]

    def binding(self, binding_id: str) -> ApprovedImplementationBinding:
        return self._bindings_by_id[_text(binding_id, "binding_id")]

    def bindings_for_rule(self, rule_id: RuleId) -> tuple[ApprovedImplementationBinding, ...]:
        if not isinstance(rule_id, RuleId):
            raise TypeError("rule_id must be RuleId")
        return tuple(item for item in self.implementation_bindings if item.rule_id == rule_id)


def _module_source_bytes(module_name: str) -> bytes:
    module_name = _text(module_name, "implementation_module")
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        raise RegulatoryAuthorityError(
            "REGULATORY_IMPLEMENTATION_MODULE_UNRESOLVED",
            f"cannot resolve reviewed implementation module {module_name}",
        )
    path = Path(spec.origin)
    if not path.is_file():
        raise RegulatoryAuthorityError(
            "REGULATORY_IMPLEMENTATION_MODULE_UNRESOLVED",
            f"reviewed implementation module has no readable source file {module_name}",
        )
    if path.suffix not in {".py", ".pyw"}:
        raise RegulatoryAuthorityError(
            "REGULATORY_IMPLEMENTATION_MODULE_NOT_SOURCE",
            f"reviewed implementation module is not Python source {module_name}: {path.name}",
        )
    return path.read_bytes()


def implementation_fingerprint(
    *,
    rule_id: RuleId,
    rule_version: str,
    evaluator_binding_id: str,
    implementation_modules: Sequence[str],
) -> str:
    """Hash only explicitly reviewed implementation modules plus rule binding identity."""

    if not isinstance(rule_id, RuleId):
        raise TypeError("rule_id must be RuleId")
    rule_version = _text(rule_version, "rule_version")
    evaluator_binding_id = _text(evaluator_binding_id, "evaluator_binding_id")
    modules = _strings(implementation_modules, "implementation_module", require_nonempty=True)
    module_hashes = [
        [module_name, hashlib.sha256(_module_source_bytes(module_name)).hexdigest()]
        for module_name in modules
    ]
    payload = {
        "rule_id": rule_id.value,
        "rule_version": rule_version,
        "evaluator_binding_id": evaluator_binding_id,
        "implementation_modules": module_hashes,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _rule_candidates(
    spec: RuleDefinition,
    catalog: RegulatoryAuthorityCatalog,
) -> tuple[ApprovedImplementationBinding, ...]:
    candidates = catalog.bindings_for_rule(spec.rule_id)
    if not candidates:
        raise RegulatoryAuthorityError(
            "MISSING_REGULATORY_AUTHORITY_BINDING",
            f"no approved implementation binding metadata exists for RuleId {spec.rule_id.value}",
        )
    exact = tuple(
        item
        for item in candidates
        if item.rule_version == spec.rule_version
        and item.evaluator_binding_id == spec.evaluator.binding_id
    )
    if len(exact) == 1:
        return exact
    if len(exact) > 1:
        raise RegulatoryAuthorityError(
            "AMBIGUOUS_REGULATORY_AUTHORITY_BINDING",
            f"multiple current implementation bindings match RuleId {spec.rule_id.value}",
        )
    if len(candidates) == 1:
        item = candidates[0]
        if item.rule_version != spec.rule_version:
            raise RegulatoryAuthorityError(
                "REGULATORY_RULE_VERSION_MISMATCH",
                f"RuleId {spec.rule_id.value} actual={spec.rule_version} approved={item.rule_version}",
            )
        raise RegulatoryAuthorityError(
            "REGULATORY_EVALUATOR_BINDING_MISMATCH",
            f"RuleId {spec.rule_id.value} actual={spec.evaluator.binding_id} approved={item.evaluator_binding_id}",
        )
    raise RegulatoryAuthorityError(
        "NO_CURRENT_REGULATORY_AUTHORITY_BINDING",
        f"no unique current binding matches RuleId {spec.rule_id.value}",
    )


def validate_rule_authority(
    spec: RuleDefinition,
    catalog: RegulatoryAuthorityCatalog,
) -> ValidatedRuleAuthority:
    """Validate exact source/review/evaluator/fingerprint authority for one F0 rule."""

    if not isinstance(spec, (RegulatoryDerivationSpec, CheckSpec)):
        raise TypeError("spec must be RegulatoryDerivationSpec or CheckSpec")
    if not isinstance(catalog, RegulatoryAuthorityCatalog):
        raise TypeError("catalog must be RegulatoryAuthorityCatalog")

    binding = _rule_candidates(spec, catalog)[0]
    if binding.rule_id != spec.rule_id:
        raise RegulatoryAuthorityError(
            "REGULATORY_BINDING_RULE_ID_MISMATCH",
            f"binding {binding.binding_id} does not match RuleId {spec.rule_id.value}",
        )

    bound_reviews = tuple(catalog.review(ref) for ref in binding.review_refs)
    review_claims = {item.claim_id for item in bound_reviews}
    missing_review_for_claim = tuple(ref for ref in binding.claim_refs if ref not in review_claims)
    if missing_review_for_claim:
        raise RegulatoryAuthorityError(
            "MISSING_APPROVED_REGULATORY_CLAIM_REVIEW",
            f"binding {binding.binding_id} has no referenced review for claims {','.join(missing_review_for_claim)}",
        )
    nonapproved = tuple(
        f"{item.review_id}:{item.status.value}"
        for item in bound_reviews
        if item.status is not AuthorityReviewStatus.APPROVED
    )
    if nonapproved:
        raise RegulatoryAuthorityError(
            "UNAPPROVED_REGULATORY_CLAIM_REVIEW",
            f"binding {binding.binding_id} references non-approved reviews {','.join(nonapproved)}",
        )

    for review in bound_reviews:
        try:
            claim = catalog.claim(review.claim_id)
        except KeyError as exc:
            raise RegulatoryAuthorityError(
                "MISSING_REGULATORY_CLAIM",
                f"review {review.review_id} references missing claim {review.claim_id}",
            ) from exc
        try:
            resolved_anchors = tuple(catalog.anchor(ref) for ref in claim.anchor_refs)
            resolved_sources_by_id = {}
            for anchor in resolved_anchors:
                source = catalog.source(anchor.source_id)
                resolved_sources_by_id[source.source_id] = source
            current_claim_fingerprint = regulatory_claim_fingerprint(
                claim=claim,
                anchors=resolved_anchors,
                source_documents=tuple(
                    resolved_sources_by_id[source_id]
                    for source_id in sorted(resolved_sources_by_id)
                ),
            )
        except KeyError as exc:
            raise RegulatoryAuthorityError(
                "BROKEN_REGULATORY_SOURCE_CHAIN",
                f"claim {claim.claim_id} cannot resolve its reviewed source chain",
            ) from exc
        if current_claim_fingerprint != review.reviewed_claim_fingerprint:
            raise RegulatoryAuthorityError(
                "STALE_REGULATORY_CLAIM_REVIEW",
                (
                    f"review {review.review_id} approved={review.reviewed_claim_fingerprint} "
                    f"actual={current_claim_fingerprint}"
                ),
            )

    # Resolve every bound claim/source chain independently of review matching.
    for claim_ref in binding.claim_refs:
        try:
            claim = catalog.claim(claim_ref)
        except KeyError as exc:
            raise RegulatoryAuthorityError(
                "MISSING_REGULATORY_CLAIM",
                f"binding {binding.binding_id} references missing claim {claim_ref}",
            ) from exc
        for anchor_ref in claim.anchor_refs:
            try:
                anchor = catalog.anchor(anchor_ref)
                catalog.source(anchor.source_id)
            except KeyError as exc:
                raise RegulatoryAuthorityError(
                    "BROKEN_REGULATORY_SOURCE_CHAIN",
                    f"claim {claim.claim_id} cannot resolve anchor/source {anchor_ref}",
                ) from exc

    evaluator_module = _text(spec.evaluator.evaluator.__module__, "evaluator module")
    if evaluator_module not in binding.implementation_modules:
        raise RegulatoryAuthorityError(
            "EVALUATOR_IMPLEMENTATION_MODULE_NOT_REVIEWED",
            f"binding {binding.binding_id} does not include evaluator module {evaluator_module}",
        )

    actual_fingerprint = implementation_fingerprint(
        rule_id=spec.rule_id,
        rule_version=spec.rule_version,
        evaluator_binding_id=spec.evaluator.binding_id,
        implementation_modules=binding.implementation_modules,
    )
    if actual_fingerprint != binding.approved_implementation_fingerprint:
        raise RegulatoryAuthorityError(
            "STALE_REGULATORY_IMPLEMENTATION_BINDING",
            (
                f"binding {binding.binding_id} approved={binding.approved_implementation_fingerprint} "
                f"actual={actual_fingerprint}"
            ),
        )

    return ValidatedRuleAuthority(
        rule_id=spec.rule_id,
        binding_id=binding.binding_id,
        approved_implementation_fingerprint=binding.approved_implementation_fingerprint,
        claim_refs=binding.claim_refs,
        review_refs=binding.review_refs,
    )


def validate_registry_authority(
    registry: RegulatoryRegistry,
    catalog: RegulatoryAuthorityCatalog,
) -> tuple[ValidatedRuleAuthority, ...]:
    """Validate every rule in one immutable F0 registry; no partial acceptance."""

    if not isinstance(registry, RegulatoryRegistry):
        raise TypeError("registry must be RegulatoryRegistry")
    if not isinstance(catalog, RegulatoryAuthorityCatalog):
        raise TypeError("catalog must be RegulatoryAuthorityCatalog")
    validated = tuple(
        validate_rule_authority(spec, catalog)
        for spec in (*registry.derivations, *registry.checks)
    )
    return tuple(sorted(validated, key=lambda item: item.sort_key))


__all__ = [
    "AuthorityReviewStatus",
    "RegulatorySourceDocument",
    "SourceAnchor",
    "RegulatoryClaim",
    "AuthorityReviewRecord",
    "ApprovedImplementationBinding",
    "RegulatoryAuthorityCatalog",
    "ValidatedRuleAuthority",
    "RegulatoryAuthorityError",
    "regulatory_claim_fingerprint",
    "implementation_fingerprint",
    "validate_rule_authority",
    "validate_registry_authority",
]
