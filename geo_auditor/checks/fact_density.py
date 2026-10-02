import json
import re
from bs4 import BeautifulSoup
from geo_auditor.jsonld import distinct_types
from geo_auditor.models import FetchResult, LLMConfig, CheckResult
from geo_auditor.llm import chat_complete
from geo_auditor.thresholds import (
    FACT_DENSITY_TARGET_PCT,
    FACT_STRUCTURE_TARGET,
    FACT_SCHEMA_TARGET,
    FACT_LINKS_TARGET,
    FACT_WEIGHT_DENSITY,
    FACT_WEIGHT_STRUCTURE,
    FACT_WEIGHT_SCHEMA,
    FACT_WEIGHT_LINKS,
    FACT_TEXT_WORD_LIMIT,
    FACT_WEAK_PARA_CHARS,
)

FACT_PATTERN = re.compile(
    r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?%?\b'
    r'|\$\d+[\d,]*'
    r'|\b(19|20)\d{2}\b'
)

SYSTEM = """You are a GEO analyst. Find the single most fact-sparse paragraph in the content.
Return ONLY valid JSON:
{"weak_paragraph": "exact quote of the weakest paragraph (max 200 chars)", "rewrite": "improved version with specific facts — mark invented stats as [VERIFY: ...]"}
If all paragraphs are strong, set weak_paragraph to "N/A" and rewrite to "N/A"."""


def compute_fact_density(text: str):
    words = text.split()
    if not words:
        return 0.0, 0
    matches = FACT_PATTERN.findall(text)
    count = len(matches)
    density = (count / len(words)) * 100
    return round(density, 2), count


def _count_schema_types(html: str) -> int:
    """Count distinct JSON-LD @types on the page."""
    return len(distinct_types(html))


def _count_structure(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    return {
        "h2_count": len(soup.find_all("h2")),
        "h3_count": len(soup.find_all("h3")),
        "list_count": len(soup.find_all(["ul", "ol"])),
        "table_count": len(soup.find_all("table")),
        "outbound_links": len([
            a for a in soup.find_all("a", href=True)
            if a["href"].startswith("http") and "." in a["href"]
        ]),
    }


def check_fact_density(fetch_result: FetchResult, config: LLMConfig) -> CheckResult:
    if not fetch_result.text.strip():
        return CheckResult(
            name="Fact Density & Structure", score=0.0, max_score=100.0,
            evidence="Could not extract page content.",
            fix_hint="Page content could not be extracted.", details={},
        )

    text_600 = " ".join(fetch_result.text.split()[:FACT_TEXT_WORD_LIMIT])
    density, fact_count = compute_fact_density(text_600)
    structure = _count_structure(fetch_result.html)
    schema_count = _count_schema_types(fetch_result.html)

    density_score = min(density / FACT_DENSITY_TARGET_PCT, 1.0)
    structure_score = min((structure["h2_count"] + structure["h3_count"] + structure["list_count"]) / FACT_STRUCTURE_TARGET, 1.0)
    schema_score = min(schema_count / FACT_SCHEMA_TARGET, 1.0)
    links_score = min(structure["outbound_links"] / FACT_LINKS_TARGET, 1.0)

    raw = (
        density_score * FACT_WEIGHT_DENSITY
        + structure_score * FACT_WEIGHT_STRUCTURE
        + schema_score * FACT_WEIGHT_SCHEMA
        + links_score * FACT_WEIGHT_LINKS
    )
    score = round(raw * 100, 1)

    weak_para, rewrite = "", ""
    try:
        llm_raw = chat_complete(config, [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": text_600},
        ], json_mode=True)
        data = json.loads(llm_raw)
        weak_para = data.get("weak_paragraph", "")
        rewrite = data.get("rewrite", "")
    except Exception:
        weak_para = text_600[:FACT_WEAK_PARA_CHARS]
        rewrite = ""

    return CheckResult(
        name="Fact Density & Structure", score=score, max_score=100.0,
        evidence=weak_para or text_600[:FACT_WEAK_PARA_CHARS],
        fix_hint=f"Weak paragraph: {weak_para}\nSuggested rewrite: {rewrite}",
        details={
            "fact_density": density, "fact_count": fact_count,
            "schema_types": schema_count, "structure": structure, "rewrite": rewrite,
        },
    )
