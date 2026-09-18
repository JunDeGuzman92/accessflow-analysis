"""Human-readable explanations derived only from result codes."""

from __future__ import annotations

from .models import AssessmentResult, ImpactSeverity


def explain(result: AssessmentResult) -> str:
    if result.impact_severity is ImpactSeverity.NOT_EVALUATED:
        impact = "Potential network impact was not evaluated because a complete modeled route result is unavailable."
    elif result.impact_severity is ImpactSeverity.SEVERE:
        impact = "Potential impact is rated SEVERE because the modeled hard closure disconnects the evaluated endpoint pair."
    elif result.impact_severity is ImpactSeverity.HIGH:
        impact = "Potential impact is rated HIGH because the modeled route exceeds a documented detour threshold."
    elif result.impact_severity is ImpactSeverity.MODERATE:
        impact = "Potential impact is rated MODERATE because a modeled detour exists but does not reach the documented HIGH threshold."
    else:
        impact = "Potential impact is rated LOW because the modeled route has no detour."
    return f"{impact} Evidence confidence is {result.evidence_confidence.value}."