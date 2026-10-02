# GEO Auditor

A CLI tool that audits any business website for visibility in AI search engines (ChatGPT, Perplexity, Google AI Overviews). Enter a URL; get a scored HTML report showing where you're invisible, why, and exactly what to fix.

**[Live demo report →](https://abhay120204.github.io/geo-auditor/)**

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

### Scoring weights at a glance

| Check | Weight | Method | Calibration |
|-------|--------|---------|-------------|
| **AI Visibility Probe** | **50%** | Live Gemini `google_search` grounding | [GROUNDED] |
| **Direct Answer Lead** | **11%** | LLM judgment | [GROUNDED] |
| **Agent Discoverability** | **9%** | HTTP + file parsing | [GROUNDED] |
| **Content Freshness** | **5%** | Structured data + headers | [GROUNDED / HEURISTIC] |
| **Markdown-safe Structure** | **5%** | HTML heading analysis | [HEURISTIC] |
| **Fact Density & Structure** | **4%** | Regex + HTML + JSON-LD | [GROUNDED] |
| **Citation Density** | **4%** | HTML tag + phrase parsing | [HEURISTIC] |
| **Organization E-E-A-T** | **4%** | JSON-LD schema parsing | [HEURISTIC] |
| **Content Depth** | **4%** | Word count (trafilatura) | [HEURISTIC] |
| **Wikipedia Presence** | **2%** | Wikipedia Search API | [GROUNDED] |
| **Community Citations** | **2%** | Forum domains in probe grounding sources | [HEURISTIC] |

**Score formula:** `Overall = Visibility×0.50 + Σ(check × weight)`  
All weights and thresholds live in `geo_auditor/thresholds.py` — no magic numbers scattered in check files.

---

### Check details and research basis

#### AI Visibility Probe — 50%

8 buyer-intent queries sent to Gemini with `google_search` grounding (5 unbranded × weight 2.0 + 3 branded × weight 1.0). Gemini searches Google live, retrieves real pages, synthesizes an answer, and returns grounded citations. Detects if your domain is cited, mentioned, or absent. Tracks competitor share-of-voice.

**Why 50%:** Direct measurement of AI search presence — the entire purpose of the audit. Unbranded queries are weighted 2× because they represent customers who don't already know your name.  
**Proof:** [Perplexity citation analysis](https://aithinkerlab.com/generative-engine-optimization-2026/) shows AI Overviews weight live-crawled grounded results, not training-data recall. Gemini `google_search` grounding is the only public API that mirrors this pipeline.

---

#### Direct Answer Lead — 11%

Does your opening paragraph directly answer the visitor's query without any surrounding context? LLM-scored for self-containment (pass → 50 + confidence×50; fail → confidence×40).

**Why 11%:** First-paragraph bias is the single most documented GEO finding.  
**Proof:** [Princeton KDD '24 (Aggarwal et al.)](https://arxiv.org/abs/2311.09735) — 44.2% of all LLM citations originate from the first 30% of a page. A self-contained opening paragraph is the cheapest intervention with the highest citation lift.

---

#### Agent Discoverability — 9%

Are GPTBot / ClaudeBot / PerplexityBot / OAI-SearchBot blocked in `robots.txt`? Is a valid `llms.txt` present? Is `sitemap.xml` reachable?

**Why 9%:** A blocked bot cannot index your page — zero score on the probe is guaranteed regardless of content quality.  
**Proof:** [OpenAI GPTBot documentation](https://platform.openai.com/docs/gptbot) — crawl permission is a hard prerequisite. [llmstxt.org specification](https://llmstxt.org/) — `llms.txt` bypasses noisy HTML-to-text conversion, giving AI engines a clean structured context file.

---

#### Content Freshness — 5%

Detects last-published or last-updated date via structured data (`datePublished` / `dateModified` in JSON-LD, visible date labels) and `Last-Modified` HTTP header (with CDN false-positive guard: header < 1 day old and no structured date → discarded).

**Why 5%:** Recency is a gated signal — stale content is deprioritized at the retrieval step before any quality scoring happens.  
**Proof:** [Perplexity source freshness documentation](https://www.perplexity.ai/hub/blog/perplexity-pages) — Perplexity applies an approximate 30-day recency preference window. Pages updated within 30 days score 1.0×; older content decays on a curve down to 0.10× beyond 365 days. The 30-day cutoff is [GROUNDED]; the decay curve is [HEURISTIC].

---

#### Markdown-safe Structure — 5%

Counts headings that are phrased as questions (`?` at end) with a substantive direct-answer paragraph (15–250 words) immediately following. AI engines convert HTML to plain text before synthesis — question/answer heading patterns produce naturally citable snippets.

**Why 5%:** AI engines extract structured Q&A blocks as discrete citation candidates.  
**Proof:** [AutoGEO (Wu et al., CMU — ICLR 2026)](https://arxiv.org/abs/2510.11438) confirmed structured, self-contained Q&A patterns consistently outperform marketing prose in citation rate across all major generative engines tested.

---

#### Fact Density & Structure — 4%

Numbers/stats/dates per 100 words (40% weight) + H2/H3/lists/tables count (30%) + distinct JSON-LD `@type`s (20%) + outbound authority links (10%).

**Why 4%:** Statistics injection is the single largest measurable lift in the original GEO paper — but it co-moves with overall content quality (correlated with Direct Answer Lead and Content Depth), so it carries a lower independent weight to avoid double-counting.  
**Proof:** [Princeton KDD '24 (Aggarwal et al.)](https://arxiv.org/abs/2311.09735) — statistics injection yielded +115.1% visibility lift for previously low-ranked sites, the highest of any single intervention tested.

---

#### Citation Density — 4%

Counts `<blockquote>` tags, `<cite>` tags, and attribution phrases in body text ("according to", "research by", "data from", "reported by", "cited in", "sources:"). Intentionally **excludes outbound links** (already counted in Fact Density).

**Why 4%:** Pages that cite sources signal authoritative, trustworthy content — a pattern AI engines trained on academic and journalistic text have learned to prefer.  
**Proof:** [AutoGEO (Wu et al., CMU — ICLR 2026)](https://arxiv.org/abs/2510.11438) — well-sourced content (explicit attributions, not just links) was among the top discriminators for citation by generative engines. Threshold values are [HEURISTIC] — not empirically calibrated against citation-winning pages.

---

#### Organization E-E-A-T — 4%

Finds `LocalBusiness` / `Organization` JSON-LD (20+ schema.org subtypes, handles `@graph` format). Scores NAP completeness: name only → 40; + phone or address → 65; full NAP → 85; full NAP + `sameAs` social profiles → 100.

**Why 4%:** Google's Search Generative Experience and Bing Copilot use Organization schema to verify business identity before featuring a brand in an AI answer. Missing NAP = unverifiable entity.  
**Proof:** [Google Search Central — schema.org LocalBusiness](https://developers.google.com/search/docs/appearance/structured-data/local-business) — structured NAP is a documented trust signal for local knowledge panels, which feed SGE answers. `sameAs` social proof is a [HEURISTIC] extension of this.

---

#### Content Depth — 4%

Word count of trafilatura-extracted body text (navigation, footer, and boilerplate stripped). Tiers calibrated for company/service pages, not blog posts: <150 → 15; 150–299 → 40; 300–599 → 65; 600–999 → 85; 1000+ → 100.

**Why 4%:** Thin pages are filtered at the retrieval step by AI engines before quality scoring. 300 words is the practical minimum for a page to be considered substantive.  
**Proof:** [AutoGEO (Wu et al., CMU — ICLR 2026)](https://arxiv.org/abs/2510.11438) — comprehensive content (sufficient depth to cover the topic) was consistently rewarded across all engines tested. Tier breakpoints are [HEURISTIC].

---

#### Wikipedia Presence — 2%

One HTTP GET to the Wikipedia Search API (no auth). Matches results against business name using substring + multi-word overlap (requires ≥ 2 significant words, len > 3, excluding stopwords like "inc", "llc"). Binary: article found → 100; not found → 20.

**Why 2%:** Wikipedia is the single most-cited source across all major AI engines. A Wikipedia article is the strongest brand-authority signal available. Low weight because it's binary and most small businesses will score 20 — it shouldn't dominate.  
**Proof:** [Perplexity citation analysis](https://aithinkerlab.com/generative-engine-optimization-2026/) — Wikipedia pages are consistently top-3 cited domains in AI-synthesized answers. Score values are [GROUNDED] for the direction; threshold is [HEURISTIC].

---

#### Community Citations — 2%

No extra HTTP call. Counts forum/discussion domains (Reddit, Hacker News, Stack Overflow, …) in the grounding sources the probe already collected — i.e. how often the AI engine actually drew on community discussion when answering about this category. Count-based tiers in `thresholds.py`. Self-excludes (not scored) when too few probe queries triggered a live search to report a rate from.

**Why 2%:** Perplexity and ChatGPT Browse surface Reddit and HN heavily — authentic user discussion is treated as corroborating evidence.  
**Proof:** [Nine Pillars of GEO Visibility](https://aithinkerlab.com/generative-engine-optimization-2026/) — community corroboration (Reddit, forums) is listed as a distinct GEO ranking factor. Tier breakpoints are [HEURISTIC].

> Replaces an earlier Reddit Footprint check that called Reddit's search JSON API directly; that endpoint returns HTTP 403 to unauthenticated clients, so it could never measure anything.

---

## What's real vs unmeasured

**Everything is real when an API key is present.**

- **AI Visibility Probe** — real Gemini calls with `google_search` grounding. Gemini searches Google live for each buyer query and returns grounded citations. This is genuine live-web-grounded AI visibility measurement — not training data, not a scrape.
- **On-page checks** (robots.txt, llms.txt, sitemap, regex fact density, HTML structure parsing, Wikipedia API) — always real, no LLM required.
- **LLM analysis** (profiling, direct-answer scoring, fix generation) — real Gemini calls.
- `GEMINI_API_KEY` is required; without it the tool exits with a clear error (there is no mock/demo mode).
- A check that cannot measure its signal (API unreachable, required data absent) is marked **not measured** and excluded from the score — the remaining weights renormalise — rather than reported as a low result.

## Architecture

```
audit.py                         ← CLI entry point (click)
geo_auditor/
  config.py                      ← Model tiers (probe / analysis / fast)
  thresholds.py                  ← Every scoring cutoff and weight (single source of truth)
  models.py                      ← Dataclasses for all domain types
  jsonld.py                      ← Shared JSON-LD parser (fact_density, org_eeat, freshness)
  profiler.py                    ← Extracts business name/category/city from URL via LLM
  probe.py                       ← Live AI search probe (Gemini + google_search grounding)
  llm.py                         ← Gemini API calls (chat + grounded web search)
  scorer.py                      ← Weighted score aggregation (reads weights from thresholds.py)
  fixer.py                       ← LLM-generated copy-paste fix recommendations
  reporter.py                    ← Jinja2 → self-contained HTML report
  fetcher.py                     ← httpx + trafilatura page fetch and text extraction
  checks/
    direct_answer.py             ← LLM-scored opening paragraph self-containment
    fact_density.py              ← Regex + HTML parsing for stats/structure/schema
    discoverability.py           ← robots.txt, llms.txt, sitemap checks
    freshness.py                 ← Structured data + Last-Modified date detection
    markdown_structure.py        ← Question-heading + answer-paragraph pattern detection
    citation_density.py          ← Blockquote/cite tags + attribution phrases
    org_eeat.py                  ← LocalBusiness / Organization JSON-LD NAP completeness
    content_depth.py             ← Word count of trafilatura-extracted body text
    wikipedia.py                 ← Wikipedia Search API presence check
    community_citations.py       ← Forum citations from probe grounding sources
templates/
  report.html.j2                 ← Self-contained HTML report (no external CDN)
```

## Threshold calibration

All scoring thresholds live in `geo_auditor/thresholds.py`. Each value is tagged:

| Tag | Meaning |
|-----|---------|
| `[GROUNDED]` | Backed by a cited academic study or documented engine behavior |
| `[HEURISTIC]` | Reasoned estimate — plausible but not measured against real citation data |
| `[STRUCTURAL]` | Mechanical detection bound — low calibration value (e.g. regex character limits) |

The intended calibration path for `[HEURISTIC]` values: run the audit against a corpus of pages that actually win AI citations, observe where the current thresholds over/under-penalize, and update `thresholds.py`. **Do not replace thresholds with per-audit LLM calls** — that trades an inspectable guess for an undocumented one and adds run-to-run nondeterminism.

## Design decisions & tradeoffs

| Decision | Rationale |
|----------|-----------|
| **Gemini `google_search` grounding as probe** | The only public API that mirrors how AI Overviews / Perplexity work — live web retrieval, not training-data recall. |
| **All thresholds in `thresholds.py`** | Centralizes every magic number with a calibration tag. Makes it obvious what's measured vs. guessed. |
| **Fact vs. judgment routing** | Deterministic facts (dates, tag counts, entity existence) → code/free-API + thresholds. Judgments (is this lead self-contained?) → LLM. Mixing them adds nondeterminism without improving accuracy. |
| **Three model tiers** | `gemini-3.8-flash` for probe/analysis (grounded search + quality judgment); `gemini-2.5-flash-lite` for low-effort structured JSON tasks (query generation, status classification). Cost-optimized without degrading quality-sensitive paths. |
| **URL-only competitor extraction** | Gemini links real product recommendations as `[Brand](url)` but never links section headers. URL-based discrimination eliminates all stoplists. Also filters on link text to prevent the audited business from appearing in its own competitor list. |
| **String match before LLM detection** | Cheaper and catches full-text mentions that would be truncated in an LLM prompt. LLM only fires for ambiguous absent cases. |
| **Homepage-only crawl** | Covers ~80% of GEO signal. Multi-page crawl is a roadmap item. |
| **Stateless CLI → local HTML** | No auth, no database, no server. The output is a single file you can email or share. |

## Known limitations

- **Correlated checks:** Direct Answer Lead, Fact Density, Content Depth, and Markdown Structure all co-move with overall content quality. Summing them as independent weights double-counts the content quality signal. Treat the overall score as directional — don't trust differences smaller than ~5 points.
- **Fact Density saturation:** its component targets are low enough that most content pages max three of four components, so the check barely discriminates good from excellent until the thresholds are calibrated against a cited-page corpus.
- **Community Citations denominator:** depends on how many probe queries Gemini chose to web-search, which varies per run; the check self-excludes below a minimum rather than report an unstable rate.
- **freshness CDN guard:** The Last-Modified header guard (discard if < 1 day old with no structured date) catches most CDN/SSR false-fresh stamps but not all edge cases.
- **Wikipedia name matching:** Multi-word overlap matching may miss brands with non-obvious Wikipedia article titles (e.g. a company known by an acronym different from its legal name).

## Roadmap

1. **Weekly monitoring mode** — re-run on schedule, diff scores over time, alert on drops
2. **Multi-page crawl** — audit top 5 pages by traffic, surface the worst offenders per page
3. **Competitor gap analysis** — run the same queries against a named competitor URL, show where they're winning your slots
4. **Threshold calibration tooling** — script to run audits against a known-cited page corpus and propose updated `[HEURISTIC]` values
5. **Bing index presence** — requires Bing Webmaster Tools API (site ownership verification barrier)

## Research foundation

**[GEO: Generative Engine Optimization](https://arxiv.org/abs/2311.09735)**  
Aggarwal et al., Princeton University / Georgia Tech / Allen Institute for AI — ACM SIGKDD 2024.  
Key findings: 44.2% of all LLM citations originate from the first 30% of a page; statistics injection yields the single largest visibility lift (+115.1% for previously low-ranked sites).

**[AutoGEO: What Generative Search Engines Like and How to Optimize Web Content Cooperatively](https://arxiv.org/abs/2510.11438)**  
Wu et al., Carnegie Mellon University — ICLR 2026.  
Confirmed that different generative engines reward structured, comprehensive, well-sourced, self-contained content.

**[The Nine Pillars of GEO Visibility](https://aithinkerlab.com/generative-engine-optimization-2026/)**  
Industry synthesis of millions of AI citations. Ranking factor framework that maps to this tool's scoring dimensions.

**[llms.txt specification](https://llmstxt.org/)**  
Emerging standard for machine-readable site context for LLMs — directly implemented in the Agent Discoverability check.
