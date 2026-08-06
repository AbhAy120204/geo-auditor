from geo_auditor.models import VisibilityResult, CheckResult

BANDS = [
    (90, "Excellent"), (75, "Good"), (56, "Fair"), (31, "Poor"), (0, "Critical"),
]
CHECK_WEIGHTS = {
    "Direct Answer Lead": 0.20,
    "Fact Density & Structure": 0.15,
    "Agent Discoverability": 0.15,
}


def score_audit(visibility: VisibilityResult, checks: list) -> tuple:
    score = visibility.score * 0.50
    for check in checks:
        weight = CHECK_WEIGHTS.get(check.name, 0.15)
        score += check.score * weight
    score = round(score, 1)
    band = next(b for threshold, b in BANDS if score >= threshold)
    return score, band
