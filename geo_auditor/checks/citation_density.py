"""Quotation & attribution density check.

Measures whether the page cites external authority — <blockquote>/<cite> markup
and attribution phrases in body text ("according to [source]", "research by X").
AI engines preferentially cite pages that aggregate and attribute evidence; a
page that cites credible sources is treated as a synthesis hub, not an island.

Distinct from Fact Density, which counts raw outbound links. This check measures
attribution intent only — explicit quotation markup and attribution phrases.

Sources: Perplexity source-pattern analysis; Gemini research report on outbound-
citation correlation with AI citation rates.
"""
import re
from bs4 import BeautifulSoup
from geo_auditor.models import FetchResult, CheckResult
from geo_auditor.thresholds import (
    CITATION_SCORE_TIERS,
    CITATION_SCORE_MAX,
    CITATION_TEXT_SCAN_CHARS,
)

_ATTRIBUTION = re.compile(
    r'\baccording to\b'
    r'|\bas (?:stated|reported|noted) by\b'
    r'|\bresearch (?:by|from)\b'
    r'|\bstudy (?:by|from|shows)\b'
    r'|\bdata from\b'
    r'|\breported by\b'
    r'|\bcited (?:by|in)\b'
    r'|\bsources?:\s',
    re.IGNORECASE,
)

# "— Jane Doe, CTO at Acme" / "– Acme Corp" dash attribution inside a quote.
_DASH_ATTRIBUTION = re.compile(r'[—–]\s*[A-Z][\w.\'-]+(?:\s+[\w.\'-]+){0,6}\s*$')


def _attributed_blockquotes(soup) -> tuple[int, int]:
    """Split <blockquote> into (attributed, unattributed).

    A <blockquote> evidences outbound attribution only if it names its source —
    a nested <cite>, a `cite=` URL, a link, or a "— Name" dash attribution.
    Unattributed quotes are testimonials (inbound praise), not citations, and
    are not counted.
    """
    attributed = unattributed = 0
    for bq in soup.find_all("blockquote"):
        has_source = bool(
            bq.find("cite")
            or bq.get("cite")
            or bq.find("a", href=True)
            or _DASH_ATTRIBUTION.search(bq.get_text(" ", strip=True))
        )
        if has_source:
            attributed += 1
        else:
            unattributed += 1
    return attributed, unattributed


def check_citation_density(fetch_result: FetchResult) -> CheckResult:
    soup = BeautifulSoup(fetch_result.html, "lxml")

    blockquotes, unattributed_quotes = _attributed_blockquotes(soup)
    cites = len(soup.find_all("cite"))
    phrase_count = len(_ATTRIBUTION.findall(
        fetch_result.text[:CITATION_TEXT_SCAN_CHARS]
    ))

    total = blockquotes + cites + phrase_count

    score = CITATION_SCORE_MAX
    for max_count, tier_score in CITATION_SCORE_TIERS:
        if total <= max_count:
            score = tier_score
            break

    parts = []
    if blockquotes:
        parts.append(f"{blockquotes} attributed <blockquote>")
    if cites:
        parts.append(f"{cites} <cite>")
    if phrase_count:
        parts.append(f"{phrase_count} attribution phrase(s)")

    if parts:
        evidence = f"Attribution signals: {', '.join(parts)} (total {total})"
    else:
        evidence = "No attribution signals (no attributed quotes, cite tags, or 'according to' phrases)"

    if unattributed_quotes:
        evidence += (
            f". {unattributed_quotes} unattributed <blockquote> not counted "
            f"(no cite, link, or named source — reads as testimonial, not citation)"
        )

    if total >= 8:
        fix_hint = ""
    elif total < 3:
        fix_hint = (
            "Add external attribution: use <blockquote> for direct quotes, <cite> for "
            "source references, and phrases like 'According to [source]…' or 'Research "
            "by [org] shows…'. AI engines treat pages that cite credible sources as "
            "synthesis hubs — pages that attribute evidence are cited at higher rates "
            "than isolated opinion pieces."
        )
    else:
        fix_hint = (
            f"Found {total} attribution signal(s). Add a few more blockquotes or "
            f"'According to [source]' phrases to strengthen authority signals."
        )

    return CheckResult(
        name="Citation Density",
        score=score,
        max_score=100.0,
        evidence=evidence,
        fix_hint=fix_hint,
        details={
            "attributed_blockquotes": blockquotes,
            "unattributed_blockquotes": unattributed_quotes,
            "cite_tags": cites,
            "attribution_phrases": phrase_count,
            "total_signals": total,
        },
    )
