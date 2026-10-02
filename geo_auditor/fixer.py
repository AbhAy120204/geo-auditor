import json
from geo_auditor.models import BusinessProfile, LLMConfig, Fix
from geo_auditor.llm import chat_complete

SYSTEM = """You are a GEO consultant writing fix instructions for a business owner (not a developer).
Given a failing check and its evidence, produce ONE actionable fix.
Use plain English. Explain any technical terms inline.
Return ONLY valid JSON:
{
  "title": "short action title (max 8 words)",
  "effort": "low|medium|high",
  "impact": "low|medium|high",
  "copy_paste": "ready-to-use text, code, or config the owner can copy-paste directly",
  "explanation": "2-3 plain sentences: what this is, why it matters, what happens if they ignore it"
}"""


def generate_fixes(checks: list, profile: BusinessProfile, config: LLMConfig) -> list:
    fixes = []
    for check in checks:
        prompt = (
            f"Business: {profile.name} ({profile.category}, {profile.city})\n"
            f"Check failed: {check.name} (score: {check.score}/100)\n"
            f"Evidence: {check.evidence[:300]}\n"
            f"Fix hint: {check.fix_hint[:600]}"
        )
        try:
            raw = chat_complete(config, [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ], json_mode=True)
            data = json.loads(raw)
            fixes.append(Fix(
                title=data.get("title", f"Fix {check.name}"),
                effort=data.get("effort", "medium"),
                impact=data.get("impact", "medium"),
                copy_paste=data.get("copy_paste", check.fix_hint),
                explanation=data.get("explanation", ""),
            ))
        except Exception:
            fixes.append(Fix(
                title=f"Fix {check.name}", effort="medium", impact="medium",
                copy_paste=check.fix_hint, explanation="See evidence above.",
            ))
    return fixes
