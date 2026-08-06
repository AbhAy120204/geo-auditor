import json
import time
from geo_auditor.models import BusinessProfile, LLMConfig, VisibilityResult, QueryResult
from geo_auditor.llm import web_search_query, chat_complete


def generate_queries(p: BusinessProfile, config) -> list:
    """Ask LLM to generate natural buyer-intent queries for this specific business.
    Falls back to templates if the LLM call fails.
    """
    has_city = p.city and p.city.lower() not in ("unknown", "")
    location_line = f"Location: {p.city}" if has_city else "Location: national/online (no specific city)"

    prompt = (
        f"Generate realistic search queries a potential customer would type to find this business.\n"
        f"Business name: {p.name}\n"
        f"Category: {p.category}\n"
        f"Offering: {p.offering}\n"
        f"{location_line}\n\n"
        f"Rules:\n"
        f"- 5 unbranded queries: customer does NOT know the business name, just searching for the service\n"
        f"- 3 branded queries: customer is specifically looking up this business by name\n"
        f"- Queries must sound like real searches, not keyword lists\n"
        f"- Vary phrasing naturally (not all starting with 'best')\n"
        f'Return ONLY valid JSON: {{"unbranded": ["q1","q2","q3","q4","q5"], "branded": ["q1","q2","q3"]}}'
    )
    try:
        raw = chat_complete(config, [{"role": "user", "content": prompt}], json_mode=True)
        data = json.loads(raw)
        unbranded = data.get("unbranded", [])[:5]
        branded = data.get("branded", [])[:3]
        if len(unbranded) == 5 and len(branded) == 3:
            return [(q, 2.0) for q in unbranded] + [(q, 1.0) for q in branded]
    except Exception:
        pass
    return _template_queries(p)


def _template_queries(p: BusinessProfile) -> list:
    """Fallback template queries used when LLM generation fails."""
    has_city = p.city and p.city.lower() not in ("unknown", "")
    if has_city:
        unbranded = [
            (f"best {p.category} in {p.city}", 2.0),
            (f"top {p.category} near {p.city}", 2.0),
            (f"recommended {p.category} {p.city}", 2.0),
            (f"where to find {p.offering} in {p.city}", 2.0),
            (f"affordable {p.category} {p.city}", 2.0),
        ]
    else:
        unbranded = [
            (f"best {p.category}", 2.0),
            (f"top {p.category} tools", 2.0),
            (f"best {p.offering}", 2.0),
            (f"{p.category} alternatives", 2.0),
            (f"popular {p.category}", 2.0),
        ]
    return unbranded + [
        (f"what is {p.name}", 1.0),
        (f"tell me about {p.name}", 1.0),
        (f"is {p.name} good", 1.0),
    ]


def detect_status(answer: str, sources: list, domain: str, business_name: str, config) -> str:
    """Classify whether the business is cited, mentioned, or absent.

    Strategy:
    1. String match first — fast and reliable for clear cases (cited or mentioned).
    2. LLM only when string match says absent — catches paraphrases/nicknames/indirect
       references that regex can't see. Avoids the truncation problem where long answers
       would hide a mention beyond the first 800 chars sent to the LLM.
    """
    quick = _string_match_status(answer, sources, domain)
    if quick in ("cited", "mentioned"):
        return quick

    # String match found nothing — ask LLM to look for indirect/paraphrased mentions
    prompt = (
        f"Analyze this AI search response for visibility of a specific business.\n\n"
        f"Business name: {business_name}\n"
        f"Business domain: {domain}\n\n"
        f"AI response text:\n{answer}\n\n"
        f"Cited source domains returned by the search: {sources}\n\n"
        f"Classify visibility as exactly one of:\n"
        f'- "mentioned": the business is referenced by name, nickname, or clear paraphrase\n'
        f'- "absent": the business is not referenced anywhere\n\n'
        f'Return ONLY valid JSON: {{"status": "mentioned|absent", "reason": "one sentence"}}'
    )
    try:
        raw = chat_complete(config, [{"role": "user", "content": prompt}], json_mode=True)
        data = json.loads(raw)
        status = data.get("status", "").lower().strip()
        if status in ("mentioned", "absent"):
            return status
    except Exception:
        pass
    return "absent"


def _string_match_status(answer: str, sources: list, domain: str) -> str:
    """Fallback string matching when LLM detection fails."""
    import re
    domain_clean = domain.replace("www.", "").lower()
    for src in sources:
        if domain_clean in src.lower():
            return "cited"
    answer_lower = answer.lower()
    brand_hint = domain_clean.split(".")[0]
    answer_norm = re.sub(r"[^a-z0-9]", "", answer_lower)
    brand_norm = re.sub(r"[^a-z0-9]", "", brand_hint)
    if domain_clean in answer_lower or brand_hint in answer_lower or (brand_norm and brand_norm in answer_norm):
        return "mentioned"
    return "absent"


def _extract_competitors(queries: list, own_domain: str) -> dict:
    counts = {}
    for q in queries:
        for src in q.sources:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(src)
                d = parsed.netloc if parsed.netloc else src
                d = d.replace("www.", "").lower().strip()
                if d and d != own_domain.lower() and "." in d and "/" not in d:
                    counts[d] = counts.get(d, 0) + 1
            except Exception:
                pass
    return dict(sorted(counts.items(), key=lambda x: -x[1])[:5])


def run_probe(p: BusinessProfile, config) -> VisibilityResult:
    if config is None:
        mock_queries = [
            QueryResult(q, "absent", "[mock — no API key provided]", [], w)
            for q, w in _template_queries(p)
        ]
        return VisibilityResult(score=0.0, queries=mock_queries, is_mocked=True)

    queries_with_weights = generate_queries(p, config)
    results = []

    for query_text, weight in queries_with_weights:
        try:
            answer, sources = web_search_query(config, query_text)
            status = detect_status(answer, sources, p.domain, p.name, config)
            results.append(QueryResult(
                query=query_text, status=status,
                snippet=answer if answer else "",
                sources=sources[:5], weight=weight,
            ))
        except Exception as e:
            results.append(QueryResult(
                query=query_text, status="error",
                snippet=str(e), sources=[], weight=weight,
            ))
        time.sleep(0.3)

    slot_scores = {"cited": 1.0, "mentioned": 0.5, "absent": 0.0, "error": 0.0}
    total_weight = sum(r.weight for r in results)
    weighted_sum = sum(slot_scores[r.status] * r.weight for r in results)
    score = round((weighted_sum / total_weight) * 100, 1) if total_weight else 0.0

    competitors = _extract_competitors(results, p.domain)
    return VisibilityResult(score=score, queries=results, competitor_mentions=competitors)
