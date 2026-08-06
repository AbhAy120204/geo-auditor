# GEO Auditor

A CLI tool that audits any business website for visibility in AI search engines (ChatGPT, Perplexity, Google AI Overviews). Enter a URL; get a scored HTML report showing where you're invisible, why, and exactly what to fix.

## Quick start (under 5 minutes)

```bash
git clone <repo>
cd geo-auditor
python -m venv .venv
# Windows:
.venv\Scripts\pip install -r requirements.txt
cp .env.example .env
# Edit .env: add your Gemini API key (get one free at https://aistudio.google.com/apikey)
.venv\Scripts\python audit.py https://yourbusiness.com --output report.html
# Then open report.html in your browser
```

```bash
# macOS/Linux:
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python audit.py https://yourbusiness.com --output report.html
```

## What it checks

| Check | Weight | What we measure | Research basis |
|-------|--------|-----------------|----------------|
| **AI Visibility Probe** | 50% | 8 buyer-intent queries sent to Gemini with `google_search` grounding — Gemini searches Google live, retrieves real pages, synthesizes an answer, and returns grounded citations. Detects if your domain is cited. Tracks competitor share-of-voice. | Live web-grounded AICF; directly mirrors how ChatGPT/Perplexity/Gemini answer; unbranded queries weighted 2× |
| **Direct Answer Lead** | 20% | Does your opening paragraph directly answer the visitor's query without context? LLM-scored for self-containment. | Princeton KDD '24: 44.2% of all LLM citations from first 30% of page; context starvation |
| **Fact Density & Structure** | 15% | Numbers/stats/dates per 100 words + H2/H3/lists/tables + schema.org types + outbound authority links | Princeton KDD '24: statistics injection = largest single visibility lift; +115.1% for previously low-ranked sites |
| **Agent Discoverability** | 15% | Are GPTBot/ClaudeBot/PerplexityBot/OAI-SearchBot blocked in robots.txt? Is a valid llms.txt file present? Is sitemap.xml accessible? | RAG pipeline requires bot access; llms.txt bypasses noisy HTML parsing |

**Score formula:** `Overall = Visibility×0.50 + DirectAnswer×0.20 + FactDensity×0.15 + Discoverability×0.15`

Every point is traceable — no black-box numbers.

## What I chose to cut and why

| Cut | Reason |
|-----|--------|
| **Perplexity API probe** | No API key available. Would add a second live engine for true cross-engine share-of-voice. Listed in "next week." |
| **Multi-page crawl** | Homepage covers ~80% of signal. A full 5-page crawl adds meaningful cost for a first version — the checks tell you *what* to fix, and fixing the homepage is always the highest-leverage first move. |
| **Content freshness check** | Requires crawling many pages and comparing last-modified timestamps. High effort, medium signal, first version. |
| **Bing index check** | Bing Webmaster Tools API requires verified site ownership — can't check for an arbitrary third-party URL. Noted limitation. |
| **Quotation Addition check** | Research (Princeton KDD '24, pillar 4) shows attributable third-party quotes boost citation probability. Checking for this requires NLP entity/attribution detection — high implementation effort for a first version. Partial signal already captured inside Fact Density (outbound links score). |
| **Cross-Platform Citation Network** | Research (pillar 9) shows 86% of AI citations come from brand-managed external sources (Wikipedia, Reddit, Google Business Profile). Checking these requires scraping multiple third-party platforms with no reliable API — high effort, not feasible in time budget. |
| **Auth / billing / database / CI / Docker** | Not needed — the tool is a stateless CLI that generates a local HTML file. No persistence, no users, no server required. |

## What's real vs mocked

**Everything is real when API keys are present.**

- **AI Visibility Probe** — real Gemini calls with `google_search` grounding. Gemini searches Google live for each buyer query and returns grounded citations. This is genuine live-web-grounded AI visibility measurement — not training data, not a scrape.
- **On-page checks** (robots.txt, llms.txt, sitemap, regex fact density, HTML structure parsing) — always real, no LLM required.
- **LLM analysis** (profiling, direct-answer scoring, fix generation) — real Gemini calls (gemini-2.5-flash).
- If `GEMINI_API_KEY` is missing → visibility probe shows clearly-labelled demo mode (yellow banner on report, `[MOCKED]` in CLI output); analysis checks exit with a clear error.

## What I'd build next (with another week)

1. **Perplexity API integration** — second live engine, true cross-engine share-of-voice table
2. **Multi-page crawl** — audit top 5 pages by traffic, surface the worst offenders per page
3. **Content freshness check** — detect last-modified dates, "last updated" text, flag stale content on time-sensitive queries
4. **Weekly monitoring mode** — re-run on schedule, diff scores over time, alert on drops
5. **Competitor gap analysis** — run the same 8 queries against a named competitor URL, show where they're winning your slots

## Sample reports

Run against three real businesses:

- `reports/audit_1.html` — **Tacombi** (NYC Mexican restaurant chain) — GEO score: 28/100 (Critical) — invisible in AI search despite being a well-known NYC brand; Yelp and TripAdvisor take every unbranded slot
- `reports/audit_2.html` — **Mr. Rooter Plumbing** (national franchise) — GEO score: 49/100 (Poor) — known brand, full discoverability, but AI cites listing aggregators (Angi, HomeAdvisor) over their own domain for unbranded queries
- `reports/audit_3.html` — **Notion** (SaaS productivity tool) — GEO score: 60/100 (Fair) — strong brand awareness in AI answers but loses unbranded slots to Asana, Monday.com, and Slack
