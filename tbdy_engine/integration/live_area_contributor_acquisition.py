"""TrustedLiveAcquisitionContext binding for COLUMN-R1 A2 Area facts."""

from __future__ import annotations

from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
)
from tbdy_engine.providers.etabs_area_contributor_provider import (
    AreaContributorPopulation,
    capture_area_contributor_population_from_session,
)


def capture_area_contributors_from_context(
    *,
    context: TrustedLiveAcquisitionContext,
) -> AreaContributorPopulation:
    """Capture A2 facts with identity owned by the trusted live context."""
    if not isinstance(context, TrustedLiveAcquisitionContext):
        raise TypeError("context must be TrustedLiveAcquisitionContext")
    return capture_area_contributor_population_from_session(
        context.verified_session,
        model_fingerprint=context.model_fingerprint,
        evidence_epoch_id=context.evidence_epoch_id,
        session_provenance_ref=context.session_provenance_ref,
    )


__all__ = ["capture_area_contributors_from_context"]
