import json
import re
import time
from urllib.parse import urlparse

from geo_auditor.models import BusinessProfile, LLMConfig, VisibilityResult, QueryResult
from geo_auditor.llm import web_search_query, chat_complete
from geo_auditor.thresholds import (
    PROBE_SCORE_CITED, PROBE_SCORE_MENTIONED, PROBE_SCORE_ABSENT,
    PROBE_SCORE_ERROR, PROBE_BRAND_MIN_TOKEN_LEN,
)


def generate_queries(p: BusinessProfile, fast_config: LLMConfig) -> list[tuple[str, float]]:
    """Generate 8 buyer-intent queries via Gemini (low-effort structured task).

    Returns list of (query_text, weight) pairs:
      5 unbranded × weight 2.0  (customer doesn't know the business name)
      3 branded   × weight 1.0  (direct brand lookups)

    Raises on failure — there is no silent fallback. A bad query set would
    produce a meaningless probe score, so it is better to fail loudly.
    """
    has_city = p.city and p.city.lower() not in ("unknown", "")
    location_line = f"Location: {p.city}" if has_city else "Location: national/online"

    prompt = (
        f"Generate realistic search queries a potential customer would type to find this business.\n"
        f"Business name: {p.name}\n"
        f"Category: {p.category}\n"
        f"Offering: {p.offering}\n"
        f"{location_line}\n\n"
        f"Rules:\n"
        f"- 5 unbranded queries: customer does NOT know the business name\n"
        f"- 3 branded queries: customer is specifically looking up this business by name\n"
        f"- Queries must sound like real searches, not keyword lists\n"
        f"- Vary phrasing naturally (not all starting with 'best')\n"
        f'Return ONLY valid JSON: {{"unbranded": ["q1","q2","q3","q4","q5"], "branded": ["q1","q2","q3"]}}'
    )
    raw = chat_complete(fast_config, [{"role": "user", "content": prompt}], json_mode=True)
    data = json.loads(raw)
    unbranded = data.get("unbranded", [])[:5]
    branded = data.get("branded", [])[:3]
    if len(unbranded) != 5 or len(branded) != 3:
        raise ValueError(f"Query generation returned wrong counts: {len(unbranded)} unbranded, {len(branded)} branded")
    return [(q, 2.0) for q in unbranded] + [(q, 1.0) for q in branded]


def detect_status(answer: str, sources: list, domain: str, business_name: str,
                  fast_config: LLMConfig) -> str:
    """Classify whether the business is cited, mentioned, or absent.

    Fast string match first — covers most cases. LLM fallback (cheap fast model)
    only for the ambiguous 'absent' case where paraphrases or nicknames may hide a mention.
    """
    quick = _string_match_status(answer, sources, domain)
    if quick in ("cited", "mentioned"):
        return quick

    prompt = (
        f"Analyze this AI search response for visibility of a specific business.\n\n"
        f"Business name: {business_name}\n"
        f"Business domain: {domain}\n\n"
        f"AI response text:\n{answer}\n\n"
        f"Cited source domains: {sources}\n\n"
        f"Classify as exactly one of:\n"
        f'- "mentioned": the business is referenced by name, nickname, or clear paraphrase\n'
        f'- "absent": the business is not referenced anywhere\n\n'
        f'Return ONLY valid JSON: {{"status": "mentioned|absent", "reason": "one sentence"}}'
    )
    try:
        raw = chat_complete(fast_config, [{"role": "user", "content": prompt}], json_mode=True)
        data = json.loads(raw)
        status = data.get("status", "").lower().strip()
        if status in ("mentioned", "absent"):
            return status
    except Exception:
        pass
    return "absent"


def _string_match_status(answer: str, sources: list, domain: str) -> str:
    """Classify a single query result as cited / mentioned / absent.

    Two-tier citation check:
      1. Own domain or subdomain appears in the source URI.
      2. Brand token appears in the URI *path* of a sourced URL — catches
         businesses whose canonical presence is on a platform they don't own
         (GitHub repos, Yelp listings, npm packages, etc.). Requires the token
         to be at least PROBE_BRAND_MIN_TOKEN_LEN chars to avoid false positives
         on short tokens like "ai", "co".
    """
    domain_clean = domain.replace("www.", "").lower()
    brand_hint = domain_clean.split(".")[0]
    brand_norm = re.sub(r"[^a-z0-9]", "", brand_hint)

    for src in sources:
        src_lower = src.lower()
        # Tier 1: own domain / subdomain in source URL
        if domain_clean in src_lower:
            return "cited"
        # Tier 2: brand token in URI path, but ONLY for known identity platforms.
        # A blog path like "/litellm-review" on a random tech site must not
        # count — only GitHub repos, npm packages, and similar owned paths do.
        if brand_norm and len(brand_norm) >= PROBE_BRAND_MIN_TOKEN_LEN and "//" in src_lower:
            host_start = src_lower.find("//") + 2
            host_end = src_lower.find("/", host_start)
            if host_end > 0:
                host = src_lower[host_start:host_end].replace("www.", "")
                if host in _OWNED_PATH_PLATFORMS:
                    path_norm = re.sub(r"[^a-z0-9/]", "", src_lower[host_end:])
                    if brand_norm in path_norm:
                        return "cited"

    # Text-level mention: brand named in the answer but not as a cited source.
    answer_lower = answer.lower()
    answer_norm = re.sub(r"[^a-z0-9]", "", answer_lower)
    if domain_clean in answer_lower or brand_hint in answer_lower or (brand_norm and brand_norm in answer_norm):
        return "mentioned"
    return "absent"


# Platforms where a URL path segment uniquely identifies an owned account,
# repository, or package listing. Tier 2 citation detection only fires for
# these hosts — a blog URL containing the brand name in its path
# (e.g. "towardsdatascience.com/litellm-review") is NOT a citation.
_OWNED_PATH_PLATFORMS = frozenset({
    # code hosting — path is org/repo
    "github.com", "gitlab.com", "bitbucket.org", "sourceforge.net",
    # package registries — path is package name
    "npmjs.com", "pypi.org", "crates.io", "hub.docker.com",
    "packagist.org", "nuget.org", "pkg.go.dev", "rubygems.org",
    # listing / identity platforms
    "yelp.com", "g.page", "producthunt.com", "huggingface.co",
})

# Domains that represent reference/infrastructure sites, not business competitors.
# Used to filter Source 2 (markdown link) extraction.
_REFERENCE_DOMAINS = frozenset({
    "youtube.com", "reddit.com", "wikipedia.org", "twitter.com", "x.com",
    "linkedin.com", "facebook.com", "instagram.com", "medium.com",
    "forbes.com", "techcrunch.com", "wired.com", "theverge.com",
    "g2.com", "capterra.com", "trustpilot.com", "yelp.com",
    "amazon.com", "google.com", "bing.com", "quora.com",
    # dev/hosting infrastructure — not business competitors
    "github.com", "gitlab.com", "vercel.com", "netlify.com", "heroku.com",
    "aws.amazon.com", "cloud.google.com", "azure.microsoft.com",
    "npmjs.com", "pypi.org", "docs.microsoft.com", "developer.mozilla.org",
})


def _extract_competitors(queries: list, own_domain: str) -> dict:
    """Extract competitor product names from inline markdown links in Gemini answers.

    Only Source 2 (inline markdown [Brand](url) links) is used. Source 1
    (raw grounding metadata domains) was dropped because it mixes reference
    sites (github.com, vercel.com) with real competitors and always produces
    domain strings instead of readable product names.

    The markdown-link invariant: Gemini formats real product recommendations as
    [Brand Name](url). Section headers and generic labels are never linked.
    This is the structural discriminator — no stoplist needed.
    """
    own_domain_lower = own_domain.replace("www.", "").lower()
    own_brand = own_domain_lower.split(".")[0]
    counts: dict[str, int] = {}

    for q in queries:
        if not q.snippet:
            continue
        for link_text, url in re.findall(
            r'\[([^\]]{2,60})\]\((https?://[^\)]+)\)', q.snippet
        ):
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "").lower()
            if not domain or "." not in domain:
                continue
            if domain == own_domain_lower or own_brand in domain:
                continue
            if domain in _REFERENCE_DOMAINS:
                continue
            display = link_text.strip().rstrip(':').rstrip('.')
            if own_brand and own_brand in display.lower():
                continue
            counts[display] = counts.get(display, 0) + 1

    return dict(sorted(counts.items(), key=lambda x: -x[1])[:8])


def run_probe(p: BusinessProfile, probe_config: LLMConfig,
              fast_config: LLMConfig) -> VisibilityResult:
    queries_with_weights = generate_queries(p, fast_config)
    results = []

    for query_text, weight in queries_with_weights:
        try:
            answer, sources, source_uris, gemini_searches = web_search_query(probe_config, query_text)
            status = detect_status(answer, sources, p.domain, p.name, fast_config)
            results.append(QueryResult(
                query=query_text, status=status,
                snippet=answer or "",
                sources=sources[:5], weight=weight,
                source_uris=source_uris[:5],
                gemini_searches=gemini_searches,
            ))
        except Exception as e:
            results.append(QueryResult(
                query=query_text, status="error",
                snippet=str(e), sources=[], weight=weight,
            ))
        time.sleep(0.3)

    slot_scores = {
        "cited":    PROBE_SCORE_CITED,
        "mentioned": PROBE_SCORE_MENTIONED,
        "absent":   PROBE_SCORE_ABSENT,
        "error":    PROBE_SCORE_ERROR,
    }
    total_weight = sum(r.weight for r in results)
    weighted_sum = sum(slot_scores[r.status] * r.weight for r in results)
    score = round((weighted_sum / total_weight) * 100, 1) if total_weight else 0.0

    competitors = _extract_competitors(results, p.domain)
    return VisibilityResult(score=score, queries=results, competitor_mentions=competitors)
