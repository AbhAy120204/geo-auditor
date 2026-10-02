"""Content Freshness check.

Measures how recently the page was updated. Tries three sources in order:
  1. Last-Modified HTTP response header (most reliable)
  2. JSON-LD dateModified / datePublished + meta tags (article:modified_time, og:updated_time)
  3. On-page visible text regex — dates near words like "Updated:", "Last reviewed:"

Why it matters: Perplexity runs a strict 30-day recency window; content updated within
30 days is cited at measurably higher rates (Red-Engage study; Perplexity research report).
Freshness is the dominant ranking signal for Perplexity and matters for all AI engines
that weight recent content (ChatGPT Search, Google AI Overviews freshness triggers).
"""
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from geo_auditor.jsonld import iter_jsonld_objects
from geo_auditor.models import FetchResult, CheckResult
from geo_auditor.thresholds import (
    FRESHNESS_TIERS,
    FRESHNESS_STALE_SCORE,
    FRESHNESS_CDN_GUARD_DAYS,
    FRESHNESS_PAGE_TEXT_SCAN_CHARS,
)

# Regex for visible on-page dates near freshness keywords
_DATE_LABEL = re.compile(
    r'(?:updated?|last\s+(?:updated?|reviewed?|modified)|published|posted)'
    r'[\s:–\-]*'
    r'(\w+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})',
    re.IGNORECASE,
)

# ISO 8601 / RFC 2822 date formats to try when parsing
_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%a, %d %b %Y %H:%M:%S %z",
    "%B %d, %Y",
    "%d %B %Y",
]


def _parse_date(raw: str) -> datetime | None:
    raw = raw.strip().rstrip("Z")
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _days_ago(dt: datetime) -> int:
    now = datetime.now(tz=timezone.utc)
    return (now - dt).days


_TIER_LABELS = {
    0: "Fresh ({days}d ago — within Perplexity's 30-day recency window)",
    1: "Recent ({days}d ago)",
    2: "Aging ({days}d ago)",
    3: "Stale ({days}d ago — over 6 months)",
}


def _score_days(days: int) -> tuple[float, str]:
    """Return (0-1 score, label) based on age in days. Tiers live in thresholds.py."""
    for i, (max_days, score) in enumerate(FRESHNESS_TIERS):
        if days <= max_days:
            return score, _TIER_LABELS[i].format(days=days)
    return FRESHNESS_STALE_SCORE, f"Very stale ({days}d ago — over a year)"


def _from_headers(headers: dict) -> datetime | None:
    raw = headers.get("last-modified") or headers.get("Last-Modified")
    return _parse_date(raw) if raw else None


def _from_jsonld(html: str) -> datetime | None:
    """Newest dateModified/datePublished anywhere in the page's JSON-LD.

    Takes the newest date rather than the first: a page may carry both a
    datePublished and a later dateModified, and freshness means the latter.
    """
    found: list[datetime] = []
    for obj in iter_jsonld_objects(html):
        for field in ("dateModified", "datePublished"):
            val = obj.get(field)
            if isinstance(val, str):
                dt = _parse_date(val)
                if dt:
                    found.append(dt)
    return max(found) if found else None


def _from_meta(html: str) -> datetime | None:
    soup = BeautifulSoup(html, "lxml")
    for prop in ("article:modified_time", "og:updated_time", "article:published_time"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag:
            val = tag.get("content", "")
            dt = _parse_date(val)
            if dt:
                return dt
    return None


def _from_page_text(text: str) -> datetime | None:
    for match in _DATE_LABEL.finditer(text[:FRESHNESS_PAGE_TEXT_SCAN_CHARS]):
        dt = _parse_date(match.group(1))
        if dt:
            return dt
    return None


def check_freshness(fetch_result: FetchResult) -> CheckResult:
    dt: datetime | None = None
    source: str = "not found"
    discarded_header: str | None = None

    dt = _from_headers(fetch_result.headers)
    if dt:
        # Discard Last-Modified < 24h old with no structured date to corroborate
        # it: CDN/SSR stacks return Last-Modified equal to the request time on
        # every hit, which measures render time, not content age.
        if _days_ago(dt) < FRESHNESS_CDN_GUARD_DAYS:
            structured_dt = _from_jsonld(fetch_result.html) or _from_meta(fetch_result.html)
            if not structured_dt:
                discarded_header = dt.strftime("%Y-%m-%d %H:%M UTC")
                dt = None
            else:
                dt = structured_dt
                source = "JSON-LD / meta tag (Last-Modified discarded: generated in last 24h)"
        else:
            source = "Last-Modified header"
    if not dt:
        dt = _from_jsonld(fetch_result.html)
        if dt:
            source = "JSON-LD dateModified/datePublished"
        else:
            dt = _from_meta(fetch_result.html)
            if dt:
                source = "meta tag (article:modified_time / og:updated_time)"
            else:
                dt = _from_page_text(fetch_result.text)
                if dt:
                    source = "on-page visible date"

    if dt:
        days = _days_ago(dt)
        raw_score, label = _score_days(days)
        score = round(raw_score * 100, 1)
        evidence = f"{label} | source: {source} | date: {dt.strftime('%Y-%m-%d')}"
        fix_hint = (
            "" if days <= 30
            else f"Page was last updated {days} days ago. Refresh key stats, dates, and "
                 "pricing. Add a visible 'Last updated: [date]' line. Perplexity's recency "
                 "bias heavily favors content updated within 30 days."
        )
        return CheckResult(
            name="Content Freshness", score=score, max_score=100.0,
            evidence=evidence, fix_hint=fix_hint,
            details={
                "date_found": dt.isoformat(),
                "days_ago": days,
                "source": source,
                "discarded_last_modified": discarded_header,
            },
        )

    # No trustworthy date anywhere: age is unknown, not old. Excluded from the
    # score (measured=False) rather than scored as stale.
    if discarded_header:
        evidence = (
            f"No trustworthy date signal. A Last-Modified header was present "
            f"({discarded_header}) but discarded: it is under 24h old with no "
            f"JSON-LD or meta date to corroborate it, which is the signature of a "
            f"CDN/SSR stamp set at request time rather than a content update. "
            f"Age not measured, excluded from score."
        )
    else:
        evidence = (
            "No date signal found (no Last-Modified header, no JSON-LD dates, "
            "no visible date). Age not measured, excluded from score."
        )

    return CheckResult(
        name="Content Freshness",
        score=0.0,
        max_score=100.0,
        evidence=evidence,
        fix_hint=(
            "Publish an explicit date so AI engines can establish recency: add "
            "dateModified to your JSON-LD, and a visible 'Last updated: [date]' "
            "line near the top of the page. Without one, engines that weight "
            "freshness have nothing to read — a CDN Last-Modified header is not "
            "a substitute, since it reflects render time, not content age."
        ),
        details={
            "date_found": None,
            "days_ago": None,
            "source": source,
            "discarded_last_modified": discarded_header,
        },
        measured=False,
    )
