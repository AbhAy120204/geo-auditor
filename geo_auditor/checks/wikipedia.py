"""Wikipedia presence check.

Checks whether a Wikipedia article exists for the business. Wikipedia coverage
is a strong brand-authority signal: AI engines (especially Perplexity and Gemini)
treat Wikipedia-notable entities as higher-trust sources and preferentially cite
them in answers about that entity's domain.

Most local/small businesses will not have a Wikipedia article — this check scores
20 for the majority and 100 for well-known brands. Low weight in the overall score
reflects this narrow applicability.

One HTTP call to the Wikipedia search API — no auth, no Gemini.
"""
import httpx
from geo_auditor.models import BusinessProfile, CheckResult
from geo_auditor.thresholds import WIKIPEDIA_FOUND_SCORE, WIKIPEDIA_NOT_FOUND_SCORE

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "of", "in", "at", "for",
    "inc", "llc", "co", "ltd", "corp", "company", "group",
})
# Wikimedia's User-Agent policy requires a contact URL; requests without one
# get HTTP 403. https://meta.wikimedia.org/wiki/User-Agent_policy
_HEADERS = {
    "User-Agent": (
        "GEOAuditor/1.0 (https://github.com/AbhAy120204/geo-auditor) "
        "python-httpx"
    ),
    "Accept": "application/json",
}


def _title_matches(title: str, name: str) -> bool:
    t = title.lower()
    n = name.lower().rstrip(".")

    # Direct substring match (handles punctuation variants like "Inc." vs "Inc")
    if n in t or t in n:
        return True

    # Multi-word overlap: require at least 2 significant words from the name
    # to all appear in the title — prevents single-word false positives
    sig = [w for w in n.split() if w not in _STOPWORDS and len(w) > 3]
    return len(sig) >= 2 and all(w in t for w in sig)


def _search_wikipedia(name: str) -> tuple[bool, str]:
    """Returns (found, article_title). Returns (False, '') on error."""
    try:
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": name,
                "format": "json",
                "srlimit": 5,
            },
            headers=_HEADERS,
            timeout=8,
            follow_redirects=True,
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        for r in results:
            if _title_matches(r.get("title", ""), name):
                return True, r.get("title", "")
    except Exception:
        return False, "[api_error]"
    return False, ""


def check_wikipedia_presence(biz_profile: BusinessProfile) -> CheckResult:
    found, title = _search_wikipedia(biz_profile.name)

    if title == "[api_error]":
        # API unreachable — excluded from scoring, not scored as "no article".
        return CheckResult(
            name="Wikipedia Presence",
            score=0.0,
            max_score=100.0,
            evidence="Wikipedia API unreachable — not measured, excluded from score",
            fix_hint="",
            details={"found": None, "article": None, "api_error": True},
            measured=False,
        )

    if found:
        return CheckResult(
            name="Wikipedia Presence",
            score=WIKIPEDIA_FOUND_SCORE,
            max_score=100.0,
            evidence=f"Wikipedia article found: {title!r}",
            fix_hint="",
            details={"found": True, "article": title, "api_error": False},
        )

    return CheckResult(
        name="Wikipedia Presence",
        score=WIKIPEDIA_NOT_FOUND_SCORE,
        max_score=100.0,
        evidence=f"No Wikipedia article found for {biz_profile.name!r}",
        fix_hint=(
            "Wikipedia coverage is a strong AI-search authority signal. For a local "
            "business, a Wikipedia article is not realistic — but ensure your brand "
            "is mentioned in Wikipedia articles about your city, industry, or niche "
            "(e.g. a local restaurant mentioned in a 'Dining in [City]' article). "
            "Wikidata entity registration is achievable for most businesses and "
            "costs nothing."
        ),
        details={"found": False, "article": None, "api_error": False},
    )
