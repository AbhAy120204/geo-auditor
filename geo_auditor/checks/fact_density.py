import json
import re
from bs4 import BeautifulSoup
from geo_auditor.models import FetchResult, LLMConfig, CheckResult
from geo_auditor.llm import chat_complete

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
    soup = BeautifulSoup(html, "lxml")
    types = set()
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            t = data.get("@type")
            if t:
                types.add(t if isinstance(t, str) else str(t))
        except Exception:
            pass
    return len(types)


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

    text_600 = " ".join(fetch_result.text.split()[:600])
    density, fact_count = compute_fact_density(text_600)
    structure = _count_structure(fetch_result.html)
    schema_count = _count_schema_types(fetch_result.html)

    density_score = min(density / 1.0, 1.0)
    structure_score = min((structure["h2_count"] + structure["h3_count"] + structure["list_count"]) / 5, 1.0)
    schema_score = min(schema_count / 2, 1.0)
    links_score = min(structure["outbound_links"] / 3, 1.0)

    raw = density_score * 0.4 + structure_score * 0.3 + schema_score * 0.2 + links_score * 0.1
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
        weak_para = text_600[:200]
        rewrite = ""

    return CheckResult(
        name="Fact Density & Structure", score=score, max_score=100.0,
        evidence=weak_para or text_600[:200],
        fix_hint=f"Weak paragraph: {weak_para}\nSuggested rewrite: {rewrite}",
        details={
            "fact_density": density, "fact_count": fact_count,
            "schema_types": schema_count, "structure": structure, "rewrite": rewrite,
        },
    )
