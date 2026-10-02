"""Markdown-safe structure check.

Measures whether H2/H3 headings are phrased as questions with a concise
direct-answer paragraph immediately below them. This pattern survives
HTML→Markdown stripping intact — the exact format AI engines extract
when generating answers from cited pages.

  "What does the pricing include?" + one short paragraph  → extracted
  "Pricing"                        + feature table        → ignored

Sources: Google NLP Q&A guidelines; ChatGPT extraction behavior (favors
H2/H3 + paragraph over H2 + list); Perplexity cited-source pattern analysis.
"""
from bs4 import BeautifulSoup
from geo_auditor.jsonld import find_by_type
from geo_auditor.models import FetchResult, CheckResult
from geo_auditor.thresholds import (
    MARKDOWN_ANSWER_MIN_WORDS,
    MARKDOWN_ANSWER_MAX_WORDS,
    MARKDOWN_SCORE_TIERS,
    MARKDOWN_SCORE_MAX,
    MARKDOWN_BLOCK_TAGS,
)


def _faq_schema_pairs(html: str) -> list[str]:
    """Question names from FAQPage / QAPage JSON-LD.

    A declared FAQPage is an explicit, machine-readable question->answer signal
    that engines consume directly, so it counts alongside prose Q->A headings.
    Only pairs that actually carry an answer are returned.
    """
    questions: list[str] = []
    for page in find_by_type(html, {"FAQPage", "QAPage"}):
        entities = page.get("mainEntity") or []
        if isinstance(entities, dict):
            entities = [entities]
        for q in entities:
            if not isinstance(q, dict):
                continue
            name = (q.get("name") or q.get("text") or "").strip()
            answer = q.get("acceptedAnswer") or q.get("suggestedAnswer") or {}
            if isinstance(answer, list):
                answer = answer[0] if answer else {}
            body = (answer.get("text", "") if isinstance(answer, dict) else "").strip()
            # Only count a pair that actually carries an answer.
            if name and len(body.split()) >= MARKDOWN_ANSWER_MIN_WORDS:
                questions.append(name)
    return questions


def _next_block(tag):
    return tag.find_next_sibling(MARKDOWN_BLOCK_TAGS)


def _has_direct_answer(heading) -> tuple[bool, str]:
    next_el = _next_block(heading)
    if not next_el or next_el.name != "p":
        return False, ""
    text = next_el.get_text(strip=True)
    if MARKDOWN_ANSWER_MIN_WORDS <= len(text.split()) <= MARKDOWN_ANSWER_MAX_WORDS:
        return True, text[:120]
    return False, ""


def check_markdown_structure(fetch_result: FetchResult) -> CheckResult:
    soup = BeautifulSoup(fetch_result.html, "lxml")
    headings = soup.find_all(["h2", "h3"])
    total = len(headings)

    q_answered: list[dict] = []
    q_unanswered: list[str] = []

    for h in headings:
        text = h.get_text(strip=True)
        if "?" not in text:
            continue
        answered, preview = _has_direct_answer(h)
        if answered:
            q_answered.append({"heading": text, "preview": preview})
        else:
            q_unanswered.append(text)

    faq_questions = _faq_schema_pairs(fetch_result.html)

    # Rendered Q->A headings and declared FAQPage pairs are two routes to the
    # same outcome; a page doing either is extractable. Count both.
    count = len(q_answered) + len(faq_questions)
    score = MARKDOWN_SCORE_TIERS.get(count, MARKDOWN_SCORE_MAX)

    if faq_questions and not q_answered:
        evidence = (
            f"{len(faq_questions)} question/answer pair(s) declared in FAQPage "
            f"schema: {'; '.join(faq_questions[:2])}"
            + (f" (+{len(faq_questions) - 2} more)" if len(faq_questions) > 2 else "")
        )
        fix_hint = (
            "" if count >= 3
            else "Add more FAQPage question/answer pairs, or phrase H2 headings as "
                 "questions with a 1-3 sentence answer directly below."
        )
    elif count >= 3:
        shown = [q["heading"] for q in q_answered[:2]] or faq_questions[:2]
        evidence = (
            f"{count} question/answer block(s) AI engines can extract "
            f"({len(q_answered)} heading-based, {len(faq_questions)} FAQPage schema). "
            f"Examples: {'; '.join(shown)}"
        )
        fix_hint = ""
    elif count > 0:
        evidence = (
            f"{len(q_answered)} question heading(s) with direct answer; "
            f"{max(total - len(q_answered), 0)} heading(s) lack the Q→answer pattern."
        )
        fix_hint = (
            f"Rephrase more H2/H3 headings as questions and add a 1–3 sentence "
            f"answer directly below. Already good: {q_answered[0]['heading']!r}"
        )
    else:
        evidence = (
            f"{total} H2/H3 heading(s) found and no FAQPage schema — nothing "
            f"follows the question → answer pattern AI engines extract."
        )
        fix_hint = (
            "Add at least 3 question/answer blocks, by either route: H2 headings "
            "phrased as questions (ending with '?') each followed by a 1–3 sentence "
            "paragraph, or a FAQPage JSON-LD block with question/acceptedAnswer "
            "pairs. This is the format ChatGPT, Gemini, and Perplexity extract when "
            "generating cited answers from your page."
        )

    return CheckResult(
        name="Markdown-safe Structure",
        score=score,
        max_score=100.0,
        evidence=evidence,
        fix_hint=fix_hint,
        details={
            "total_h2_h3": total,
            "q_headings_with_answer": len(q_answered),
            "q_headings_without_answer": len(q_unanswered),
            "faq_schema_pairs": len(faq_questions),
            "extractable_blocks": count,
            "examples": [q["heading"] for q in q_answered[:3]] + faq_questions[:3],
        },
    )
