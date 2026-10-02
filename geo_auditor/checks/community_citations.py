"""Community citation check — forum/discussion proof inside AI answers.

Measures how often an AI engine pulls from community discussion (Reddit, Hacker
News, Stack Overflow, ...) when researching this business and its category.
Reddit and HN threads are heavily cited by Perplexity and ChatGPT Search, and
those citations appear directly in the grounding sources the probe already
collects — so this needs no extra HTTP call or API key.

Scope: a community citation proves the engine drew on forum discussion for a
query about this business's category, not that every cited thread is about this
business specifically. Citations on branded queries are the stronger signal and
are counted separately in details.
"""
from urllib.parse import urlparse

from geo_auditor.models import VisibilityResult, CheckResult
from geo_auditor.thresholds import (
    COMMUNITY_SCORE_TIERS,
    COMMUNITY_SCORE_MAX,
    COMMUNITY_MIN_GROUNDED_QUERIES,
)

# Discussion/forum platforms whose content AI engines cite as community proof.
_COMMUNITY_DOMAINS = frozenset({
    "reddit.com", "news.ycombinator.com", "ycombinator.com",
    "stackoverflow.com", "stackexchange.com", "serverfault.com",
    "superuser.com", "quora.com", "dev.to", "lobste.rs",
    "discourse.org", "substack.com", "medium.com",
})


def _is_community(domain: str) -> bool:
    d = domain.lower().replace("www.", "")
    return any(d == c or d.endswith("." + c) for c in _COMMUNITY_DOMAINS)


def _normalise(raw: str) -> str:
    """Grounding sources arrive as bare domains ('reddit.com') or full URLs."""
    raw = (raw or "").strip().lower()
    if not raw:
        return ""
    if "//" in raw:
        return urlparse(raw).netloc.replace("www.", "")
    return raw.replace("www.", "").split("/")[0]


def check_community_citations(visibility: VisibilityResult) -> CheckResult:
    grounded_queries = 0
    hits: dict[str, int] = {}
    branded_hits = 0

    for q in visibility.queries:
        if not q.sources:
            continue
        grounded_queries += 1
        # Dedupe per query: one thread cited twice is still one discussion.
        seen: set[str] = set()
        for src in q.sources:
            domain = _normalise(src)
            if domain and _is_community(domain) and domain not in seen:
                seen.add(domain)
                hits[domain] = hits.get(domain, 0) + 1
                if q.weight < 2.0:      # branded queries carry weight 1.0
                    branded_hits += 1

    total = sum(hits.values())

    # Gemini only web-searches some queries, so the denominator varies per run.
    # Below the minimum, the sample is too small to report a rate from.
    if grounded_queries < COMMUNITY_MIN_GROUNDED_QUERIES:
        if grounded_queries == 0:
            detail = (
                "No probe query produced grounded web sources — the engine answered "
                "entirely from model knowledge, so there is no citation set to inspect."
            )
        else:
            detail = (
                f"Only {grounded_queries} of {len(visibility.queries)} probe queries "
                f"triggered a live web search (minimum "
                f"{COMMUNITY_MIN_GROUNDED_QUERIES} needed), too small a sample to "
                f"report a community-citation rate from."
                + (f" Seen so far: {', '.join(hits)}." if hits else "")
            )
        return CheckResult(
            name="Community Citations",
            score=0.0,
            max_score=100.0,
            evidence=detail + " Not measured, excluded from score.",
            fix_hint="",
            details={"community_citations": total or None,
                     "domains": dict(hits),
                     "grounded_queries": grounded_queries,
                     "branded_citations": branded_hits},
            measured=False,
        )

    score = COMMUNITY_SCORE_MAX
    for max_count, tier_score in COMMUNITY_SCORE_TIERS:
        if total <= max_count:
            score = tier_score
            break

    if total == 0:
        evidence = (
            f"No community sources cited across {grounded_queries} grounded "
            f"query/queries — AI answers about this category drew only on "
            f"vendor and publisher pages."
        )
        fix_hint = (
            "Reddit and Hacker News threads are among the most frequently cited "
            "sources in Perplexity and ChatGPT Search answers. Take part honestly "
            "in the subreddits and forums where your buyers already compare "
            "options, and answer questions where your product is relevant. "
            "Never astroturf — platforms and users detect and punish it, and the "
            "resulting threads damage the brand they were meant to help."
        )
    else:
        ranked = sorted(hits.items(), key=lambda kv: -kv[1])
        shown = ", ".join(f"{d} ({n}x)" for d, n in ranked[:4])
        evidence = (
            f"{total} community citation(s) across {grounded_queries} grounded "
            f"query/queries: {shown}"
            + (f" — {branded_hits} on branded queries" if branded_hits else "")
        )
        fix_hint = (
            "" if score >= COMMUNITY_SCORE_MAX
            else (
                f"{total} community citation(s) found. Broader organic discussion "
                "raises how often Perplexity and ChatGPT Search cite third-party "
                "proof about you. Engage authentically where your buyers compare "
                "options."
            )
        )

    return CheckResult(
        name="Community Citations",
        score=score,
        max_score=100.0,
        evidence=evidence,
        fix_hint=fix_hint,
        details={
            "community_citations": total,
            "domains": dict(sorted(hits.items(), key=lambda kv: -kv[1])),
            "grounded_queries": grounded_queries,
            "branded_citations": branded_hits,
        },
    )
