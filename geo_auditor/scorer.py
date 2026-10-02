from geo_auditor.models import VisibilityResult
from geo_auditor.thresholds import (
    SCORE_BANDS,
    VISIBILITY_WEIGHT,
    CHECK_WEIGHTS,
    CHECK_WEIGHT_DEFAULT,
)


def score_audit(visibility: VisibilityResult, checks: list) -> tuple:
    """Weighted overall score, renormalised over the checks that were measured.

    Checks with measured=False are dropped and the remaining weights rescaled so
    the achievable maximum stays 100.
    """
    measured = [c for c in checks if getattr(c, "measured", True)]

    weighted = visibility.score * VISIBILITY_WEIGHT
    total_weight = VISIBILITY_WEIGHT
    for check in measured:
        weight = CHECK_WEIGHTS.get(check.name, CHECK_WEIGHT_DEFAULT)
        weighted += check.score * weight
        total_weight += weight

    score = round(weighted / total_weight, 1) if total_weight else 0.0
    band = next(b for threshold, b in SCORE_BANDS if score >= threshold)
    return score, band
