import httpx
from io import StringIO
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from geo_auditor.models import FetchResult, BusinessProfile, CheckResult
from geo_auditor.thresholds import (
    DISCOVER_BOTS_LIVE_WEIGHT,
    DISCOVER_BOTS_TRAIN_WEIGHT,
    DISCOVER_WEIGHT_BOTS,
    DISCOVER_WEIGHT_LLMS,
    DISCOVER_WEIGHT_SITEMAP,
    DISCOVER_LLMS_PRESENT_SCORE,
    DISCOVER_LLMS_ISSUES_SCORE,
)

# Live-search bots gate real-time answer inclusion; training bots only affect
# future model training. Blocking OAI-SearchBot ≠ blocking GPTBot — a common
# costly mistake (source: developers.openai.com/api/docs/bots).
AI_BOTS = {
    # Live retrieval — blocking = invisible in answers TODAY
    "OAI-SearchBot":     {"live": True,  "consequence": "Invisible in ChatGPT Search answers"},
    "Google-Extended":   {"live": True,  "consequence": "Excluded from Gemini / Google AI Overviews grounding"},
    "PerplexityBot":     {"live": True,  "consequence": "Invisible in Perplexity answers"},
    "Bingbot":           {"live": True,  "consequence": "De-indexed from Bing, hurts ChatGPT Search and Copilot"},
    "ClaudeBot":         {"live": True,  "consequence": "Excluded from Claude.ai web search"},
    # Training only — blocking affects future models, not today's answers
    "GPTBot":            {"live": False, "consequence": "Excluded from OpenAI training data"},
    "CCBot":             {"live": False, "consequence": "Excluded from Common Crawl training corpus"},
    "Applebot-Extended": {"live": False, "consequence": "Excluded from Apple Intelligence training"},
}

LIVE_BOTS  = [b for b, v in AI_BOTS.items() if v["live"]]
TRAIN_BOTS = [b for b, v in AI_BOTS.items() if not v["live"]]

LLMS_TXT_TEMPLATE = """# {name}

> {summary}

## About

- [{name} Homepage](https://{domain}): Main website with full service details
- [{name} Services](https://{domain}/services): Complete list of services offered

## Contact

- [{name} Contact](https://{domain}/contact): Get in touch or request a quote
"""


def parse_robots(robots_txt: str) -> dict:
    """Return {bot_name: consequence} for every blocked bot."""
    blocked = {}
    parser = RobotFileParser()
    parser.parse(StringIO(robots_txt).readlines())
    for bot, meta in AI_BOTS.items():
        if not parser.can_fetch(bot, "/"):
            blocked[bot] = meta["consequence"]
    return blocked


def check_llms_txt(base_url: str):
    url = urljoin(base_url.rstrip("/") + "/", "llms.txt")
    try:
        resp = httpx.get(url, timeout=8, follow_redirects=True)
        if resp.status_code != 200:
            return "missing", []
        content = resp.text
        issues = []
        if not any(line.startswith("# ") for line in content.splitlines()):
            issues.append("Missing required H1 (# Title)")
        if not any(line.startswith("> ") for line in content.splitlines()):
            issues.append("Missing required blockquote summary (> ...)")
        if "## " not in content:
            issues.append("Missing H2 section groupings")
        return "present", issues
    except Exception as e:
        return "error", [str(e)]


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def generate_llms_txt(profile: BusinessProfile) -> str:
    """Build a starter llms.txt for the customer to paste onto their site.

    The location clause is dropped unless a city was identified (profile.city is
    "unknown" for non-local businesses) so the summary never says "based in
    unknown".
    """
    category = profile.category or "business"
    has_city = profile.city and profile.city.strip().lower() not in ("unknown", "n/a", "")
    location = f" based in {profile.city}" if has_city else ""
    summary = (
        f"{profile.name} is {_article(category)} {category}{location}, "
        f"offering {profile.offering}."
    )
    return LLMS_TXT_TEMPLATE.format(
        name=profile.name, summary=summary, domain=profile.domain,
    )


def check_discoverability(fetch_result: FetchResult, profile: BusinessProfile) -> CheckResult:
    parsed = urlparse(fetch_result.url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    blocked_bots = {}
    try:
        resp = httpx.get(urljoin(base_url + "/", "robots.txt"), timeout=8)
        if resp.status_code == 200:
            blocked_bots = parse_robots(resp.text)
    except Exception:
        pass

    blocked_live  = {b: c for b, c in blocked_bots.items() if AI_BOTS[b]["live"]}
    blocked_train = {b: c for b, c in blocked_bots.items() if not AI_BOTS[b]["live"]}

    llms_status, llms_issues = check_llms_txt(base_url)

    sitemap_present = False
    try:
        sr = httpx.get(urljoin(base_url + "/", "sitemap.xml"), timeout=8)
        sitemap_present = sr.status_code == 200
    except Exception:
        pass

    live_score  = (len(LIVE_BOTS) - len(blocked_live)) / len(LIVE_BOTS)
    train_score = (len(TRAIN_BOTS) - len(blocked_train)) / len(TRAIN_BOTS)
    bots_score  = live_score * DISCOVER_BOTS_LIVE_WEIGHT + train_score * DISCOVER_BOTS_TRAIN_WEIGHT

    llms_score = {
        "present": DISCOVER_LLMS_PRESENT_SCORE if not llms_issues else DISCOVER_LLMS_ISSUES_SCORE,
        "missing": 0.0,
        "error": 0.0,
    }[llms_status]
    sitemap_score = 1.0 if sitemap_present else 0.0

    score = round((
        bots_score * DISCOVER_WEIGHT_BOTS
        + llms_score * DISCOVER_WEIGHT_LLMS
        + sitemap_score * DISCOVER_WEIGHT_SITEMAP
    ) * 100, 1)

    # Evidence
    evidence_parts = []
    if blocked_live:
        for bot, consequence in blocked_live.items():
            evidence_parts.append(f"[BLOCKED — live search] {bot}: {consequence}")
    else:
        evidence_parts.append("All live-search AI bots: allowed")
    if blocked_train:
        for bot, consequence in blocked_train.items():
            evidence_parts.append(f"[BLOCKED — training only] {bot}: {consequence}")
    evidence_parts.append(f"llms.txt: {llms_status}" + (f" (issues: {'; '.join(llms_issues)})" if llms_issues else ""))
    evidence_parts.append(f"sitemap.xml: {'present' if sitemap_present else 'missing'}")

    # Fix hints
    generated_llms = generate_llms_txt(profile)
    fix_lines = []
    if blocked_live:
        fix_lines.append(
            "# robots.txt — remove these lines to restore live AI search visibility:\n" +
            "\n".join(f"# User-agent: {b}\n# Disallow: /" for b in blocked_live)
        )
    if blocked_train and not blocked_live:
        fix_lines.append(
            "# Training bots blocked (optional — does not affect today's answers):\n" +
            "\n".join(f"# User-agent: {b}" for b in blocked_train)
        )
    if llms_status != "present" or llms_issues:
        fix_lines.append(f"# Upload this file to https://{profile.domain}/llms.txt\n{generated_llms}")

    return CheckResult(
        name="Agent Discoverability", score=score, max_score=100.0,
        evidence="\n".join(evidence_parts),
        fix_hint="\n\n".join(fix_lines) if fix_lines else "All discoverability checks passed.",
        details={
            "blocked_live_bots":  blocked_live,
            "blocked_train_bots": blocked_train,
            "llms_txt_status":    llms_status,
            "llms_txt_issues":    llms_issues,
            "sitemap_present":    sitemap_present,
            "generated_llms_txt": generated_llms,
        },
    )
