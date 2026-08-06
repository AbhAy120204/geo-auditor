import httpx
from io import StringIO
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from geo_auditor.models import FetchResult, BusinessProfile, CheckResult

AI_BOTS = ["GPTBot", "PerplexityBot", "ClaudeBot", "OAI-SearchBot", "Google-Extended"]

LLMS_TXT_TEMPLATE = """# {name}

> {name} is a {category} based in {city}, offering {offering}.

## About

- [{name} Homepage](https://{domain}): Main website with full service details
- [{name} Services](https://{domain}/services): Complete list of services offered

## Contact

- [{name} Contact](https://{domain}/contact): Get in touch or request a quote
"""


def parse_robots(robots_txt: str) -> list:
    blocked = []
    parser = RobotFileParser()
    parser.parse(StringIO(robots_txt).readlines())
    for bot in AI_BOTS:
        if not parser.can_fetch(bot, "/"):
            blocked.append(bot)
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


def generate_llms_txt(profile: BusinessProfile) -> str:
    return LLMS_TXT_TEMPLATE.format(
        name=profile.name, category=profile.category,
        city=profile.city, offering=profile.offering, domain=profile.domain,
    )


def check_discoverability(fetch_result: FetchResult, profile: BusinessProfile) -> CheckResult:
    parsed = urlparse(fetch_result.url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    blocked_bots = []
    try:
        resp = httpx.get(urljoin(base_url + "/", "robots.txt"), timeout=8)
        if resp.status_code == 200:
            blocked_bots = parse_robots(resp.text)
    except Exception:
        pass

    llms_status, llms_issues = check_llms_txt(base_url)

    sitemap_present = False
    try:
        sr = httpx.get(urljoin(base_url + "/", "sitemap.xml"), timeout=8)
        sitemap_present = sr.status_code == 200
    except Exception:
        pass

    bots_score = (len(AI_BOTS) - len(blocked_bots)) / len(AI_BOTS)
    llms_score = {"present": 1.0 if not llms_issues else 0.6, "missing": 0.0, "error": 0.0}[llms_status]
    sitemap_score = 1.0 if sitemap_present else 0.0

    score = round((bots_score * 0.5 + llms_score * 0.35 + sitemap_score * 0.15) * 100, 1)

    generated_llms = generate_llms_txt(profile)
    evidence_parts = []
    if blocked_bots:
        evidence_parts.append(f"Blocked AI bots: {', '.join(blocked_bots)}")
    else:
        evidence_parts.append("All AI bots: allowed in robots.txt")
    evidence_parts.append(f"llms.txt: {llms_status}" + (f" (issues: {'; '.join(llms_issues)})" if llms_issues else ""))
    evidence_parts.append(f"sitemap.xml: {'present' if sitemap_present else 'missing'}")

    fix_lines = []
    if blocked_bots:
        fix_lines.append("# robots.txt patch — remove these lines:\n" +
                         "\n".join(f"# User-agent: {b}\n# Disallow: /" for b in blocked_bots))
    if llms_status != "present" or llms_issues:
        fix_lines.append(f"# Upload this file to https://{profile.domain}/llms.txt\n{generated_llms}")

    return CheckResult(
        name="Agent Discoverability", score=score, max_score=100.0,
        evidence="\n".join(evidence_parts),
        fix_hint="\n\n".join(fix_lines) if fix_lines else "All discoverability checks passed.",
        details={
            "blocked_bots": blocked_bots, "llms_txt_status": llms_status,
            "llms_txt_issues": llms_issues, "sitemap_present": sitemap_present,
            "generated_llms_txt": generated_llms,
        },
    )
