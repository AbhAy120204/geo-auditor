"""Content depth check.

Measures word count of the main page content. AI engines filter thin pages
from citations regardless of other signals — a page with fewer than ~300 words
rarely gets cited even if it's technically accessible and well-structured.

Benchmarked against company/service pages, not blog posts: a homepage can be
authoritative at 400 words; the 2500-word benchmark from SEO guides applies to
long-form content, not business landing pages.

Tiers are in thresholds.py (all [HEURISTIC] — calibrate against actual citation
data once available).

Pure code — no LLM calls.
"""
from geo_auditor.models import FetchResult, CheckResult
from geo_auditor.thresholds import DEPTH_SCORE_TIERS, DEPTH_SCORE_MAX

_TIER_LABELS = [
    "Very thin — likely filtered from AI citations",
    "Thin — below minimum for reliable citation",
    "Moderate — borderline for most AI engines",
    "Substantial — above typical citation threshold",
]


def check_content_depth(fetch_result: FetchResult) -> CheckResult:
    word_count = len(fetch_result.text.split())

    score = DEPTH_SCORE_MAX
    tier_idx = len(DEPTH_SCORE_TIERS)   # default: above all tiers = max
    for i, (max_words, tier_score) in enumerate(DEPTH_SCORE_TIERS):
        if word_count <= max_words:
            score = tier_score
            tier_idx = i
            break

    if tier_idx < len(DEPTH_SCORE_TIERS):
        label = _TIER_LABELS[tier_idx]
        evidence = f"{word_count} words — {label}"
    else:
        evidence = f"{word_count} words — well above citation threshold"

    if score >= DEPTH_SCORE_MAX:
        fix_hint = ""
    elif word_count < 150:
        fix_hint = (
            f"Page has only {word_count} words. AI engines typically filter pages under "
            "~300 words from citations — there is not enough content to extract a useful "
            "answer. Expand with specific details: services offered, process, pricing "
            "range, service area, and FAQs."
        )
    elif word_count < 300:
        fix_hint = (
            f"Page has {word_count} words — below the reliable citation threshold. "
            "Add 100–200 more words covering specific details (process, credentials, "
            "service area) to cross the minimum threshold most AI engines apply."
        )
    elif word_count < 600:
        fix_hint = (
            f"Page has {word_count} words. Expanding to 600+ words with specific facts, "
            "a FAQ section, or a clear explanation of your process would increase citation "
            "probability, especially for Perplexity (which favors substantive sources)."
        )
    else:
        fix_hint = (
            f"Page has {word_count} words — solid depth. Adding a short FAQ section "
            "would push past 1000 words and strengthen citation potential further."
        )

    return CheckResult(
        name="Content Depth",
        score=score,
        max_score=100.0,
        evidence=evidence,
        fix_hint=fix_hint,
        details={"word_count": word_count},
    )
