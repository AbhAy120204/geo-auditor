import json
from geo_auditor.models import FetchResult, LLMConfig, CheckResult
from geo_auditor.llm import chat_complete
from geo_auditor.thresholds import (
    DIRECT_ANSWER_LEAD_WORDS,
    DIRECT_ANSWER_PASS_BASE,
    DIRECT_ANSWER_PASS_SPAN,
    DIRECT_ANSWER_FAIL_SPAN,
)

SYSTEM = """You are a GEO (Generative Engine Optimization) analyst.
Evaluate whether the FIRST 100 WORDS of this webpage content are self-contained and directly answer
the implicit question a visitor would have. A good direct-answer lead:
- States what the business IS and what it DOES in the first sentence
- Includes at least one specific fact (number, location, credential)
- Can be lifted out of context and still make sense
Return ONLY valid JSON: {"is_self_contained": true/false, "confidence": 0.0-1.0, "weakness": "one sentence or empty string"}
"""


def check_direct_answer(fetch_result: FetchResult, config: LLMConfig) -> CheckResult:
    if not fetch_result.text.strip():
        return CheckResult(
            name="Direct Answer Lead", score=0.0, max_score=100.0,
            evidence="Could not extract page content.",
            fix_hint="Page content could not be fetched or extracted.",
            details={"first_100_words": "", "is_self_contained": False, "confidence": 0.0},
        )

    words = fetch_result.text.split()
    first_100 = " ".join(words[:DIRECT_ANSWER_LEAD_WORDS])

    try:
        raw = chat_complete(config, [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": first_100},
        ], json_mode=True)
        data = json.loads(raw)
        is_self_contained = bool(data.get("is_self_contained", False))
        confidence = float(data.get("confidence", 0.0))
        weakness = str(data.get("weakness", ""))
    except Exception:
        is_self_contained, confidence, weakness = False, 0.0, "LLM evaluation failed"

    if is_self_contained:
        score = round(DIRECT_ANSWER_PASS_BASE + confidence * DIRECT_ANSWER_PASS_SPAN, 1)
    else:
        score = round(confidence * DIRECT_ANSWER_FAIL_SPAN, 1)

    fix_hint = weakness if weakness else "Opening paragraph is vague marketing copy — no specific facts or direct answer."

    return CheckResult(
        name="Direct Answer Lead", score=score, max_score=100.0,
        evidence=first_100, fix_hint=fix_hint,
        details={
            "first_100_words": first_100, "is_self_contained": is_self_contained,
            "confidence": confidence, "weakness": weakness,
        },
    )
