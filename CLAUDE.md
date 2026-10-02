# GEO Auditor — Dev Guide

## Running locally

```bash
# Windows (always use .venv — never system Python)
.venv\Scripts\python audit.py https://example.com --output report.html

# macOS/Linux
.venv/bin/python audit.py https://example.com --output report.html
```

Required env var: `GEMINI_API_KEY` in `.env` (get one free at https://aistudio.google.com/apikey)

## Tech stack

| Layer | Library | Notes |
|-------|---------|-------|
| CLI | `click` | Single entry point: `audit.py` |
| AI probe | `google-genai` | `google_search` grounding — live web retrieval |
| LLM calls | `google-genai` | three model tiers (probe / analysis / fast) — see below |
| HTML fetch | `httpx` + `trafilatura` | Clean text extraction from any URL |
| HTML parsing | `beautifulsoup4` + `lxml` | Structure/schema analysis |
| Report | `jinja2` | Self-contained HTML, no external CDN |
| Config | `python-dotenv` | `.env` → `GEMINI_API_KEY` |

## Models (geo_auditor/config.py)

```python
_PROBE_MODEL    = "gemini-3.8-flash"      # web_search_query (grounded, google_search tool)
_ANALYSIS_MODEL = "gemini-3.8-flash"      # chat_complete quality judgments (direct answer, fact hint)
_FAST_MODEL     = "gemini-2.5-flash-lite" # low-effort structured tasks (query gen, status classify)
```

Update these constants to change models globally.

## Key files

- `geo_auditor/probe.py` — AI search probe + competitor extraction (most complex file)
- `geo_auditor/llm.py` — all LLM calls; `web_search_query` uses `google_search` grounding
- `geo_auditor/jsonld.py` — shared JSON-LD parser (fact_density, org_eeat, freshness)
- `geo_auditor/checks/discoverability.py` — robots.txt, llms.txt, sitemap
- `geo_auditor/checks/fact_density.py` — regex-based stat/structure scoring
- `geo_auditor/checks/direct_answer.py` — LLM-scored opening paragraph
- `geo_auditor/checks/community_citations.py` — forum citations read from probe grounding sources
- `templates/report.html.j2` — the HTML report template

## Probe architecture

The probe sends 8 queries (5 unbranded × weight 2.0 + 3 branded × weight 1.0) to Gemini with `google_search` grounding. For each query:
1. Gemini searches Google live and synthesizes an answer with citations
2. `detect_status()` checks if the business domain appears in citations or text
3. `_extract_competitors()` extracts competing brands from inline markdown links `[Brand](url)` — URLs are the discriminator because LLMs always link real recommendations but never link section headers

## Competitor extraction invariant

Gemini formats real product recommendations as `[Brand Name](url)` in its markdown answers. Section headers (`**Features:**`, `**Pricing:**`) are never linked. This is the structural invariant that makes URL-only extraction work without any stoplists.

## Score formula

```
Overall = Visibility×0.50 + Σ(check.score × CHECK_WEIGHTS[check])
```

Visibility is 0.50; the ten checks split the rest (see `CHECK_WEIGHTS` in
`thresholds.py`, summing to 1.00 with Visibility). All weights and every scoring
threshold live in `geo_auditor/thresholds.py` — NOT scattered in the check
files. `scorer.py` reads its weights from there.

A check that cannot measure its signal (API down, required data absent) returns
`CheckResult(measured=False)`; `scorer.py` drops it and renormalises the
remaining weights, so an unavailable signal is never scored as a low result.

## Thresholds & calibration

`geo_auditor/thresholds.py` is the single registry of every scoring cutoff,
divisor, and weight. Each value carries a calibration tag:
`[GROUNDED]` (backed by a study), `[HEURISTIC]` (reasoned guess, uncalibrated),
`[STRUCTURAL]` (mechanical detection bound). When adding a threshold, put it
here with a tag — do NOT inline magic numbers in a check.

Rule of thumb (fact vs. judgment): a check that measures a **fact** (a date,
whether a tag exists, entity presence) uses code/free-API and deterministic
thresholds. A check that measures a **judgment** (is this lead self-contained?
substantive vs. filler?) uses an LLM. Never send a deterministic fact to an LLM
— it only adds cost and run-to-run nondeterminism.

Known deferred issue: several on-page checks are correlated (structure / fact
density / direct answer all co-move with content quality), so the weighted sum
double-counts. Revisit before trusting small score deltas.

## Adding a new check

1. Create `geo_auditor/checks/your_check.py` → return `CheckResult`
2. Put its thresholds/weight in `geo_auditor/thresholds.py` (with a calibration tag)
3. Import and call it in `audit.py` after the existing checks
4. Add its weight key to `CHECK_WEIGHTS` in `thresholds.py` (keep the total at 1.00)
5. Add a card for it in `templates/report.html.j2`

## Report output

Reports are generated HTML files — not committed to git (`*.html` in `.gitignore`). Regenerate any time by running `audit.py`. The template at `templates/report.html.j2` is the source of truth.

## Windows notes

- Always use `.venv\Scripts\python` — not `python` or `py`
- Path separators: use forward slashes in code, backslashes in shell commands
- `load_dotenv()` is called at import time in `config.py` — patching env vars in tests requires patching `dotenv.load_dotenv` in `conftest.py`
