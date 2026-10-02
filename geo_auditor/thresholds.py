"""Central registry of every scoring threshold in the auditor.

WHY THIS FILE EXISTS
--------------------
Each check turns raw page facts into a 0-100 score using cutoffs and weights.
Those numbers were originally chosen by judgment, not measured against pages
that actually win AI citations. Scattering them across check files hid that.
Centralizing them here makes the arbitrariness inspectable and tunable, and
is the precondition for calibrating them later against real citation data.

CALIBRATION STATUS legend (keep honest):
  [GROUNDED]   backed by a cited study / documented engine behavior
  [HEURISTIC]  reasoned guess, plausible but not measured — candidate for calibration
  [STRUCTURAL] not a judgment; a mechanical detection bound, low calibration value

Do NOT replace these with per-audit LLM calls. An LLM re-scoring the same page
differently each run trades an inspectable guess for an undocumented one. The
intended path is a one-off, offline calibration pass that re-grounds the
[HEURISTIC] values, then hard-codes the results back here.
"""

# ---------------------------------------------------------------------------
# Probe slot scores  (geo_auditor/probe.py)
# ---------------------------------------------------------------------------
# Maps each per-query detection status to a 0-1 slot score before weighting.
#
# [HEURISTIC] cited=1.0 and absent=0.0 are definitional.
# mentioned=0.50: brand is named in the answer but Gemini did not fetch the
# business's own page — it learned about the brand from a third-party source
# (comparison article, tutorial, competitor blog). The brand gets discovered
# but receives no direct traffic from the citation. The 0.5 gap vs 1.0 is
# intentional: cited = Gemini treated your page as an authoritative source;
# mentioned = you appeared in someone else's answer about their page.
PROBE_SCORE_CITED    = 1.00   # [GROUNDED] domain or known surface cited as source
PROBE_SCORE_MENTIONED = 0.50  # [HEURISTIC] brand named in answer, not as a citation
PROBE_SCORE_ABSENT   = 0.00   # [GROUNDED]  business not present at all
PROBE_SCORE_ERROR    = 0.00   # [STRUCTURAL] API error — no signal either way

# Minimum brand-token length for path-level URI matching.
# Prevents false-positive matches on short tokens like "ai", "co", "app".
PROBE_BRAND_MIN_TOKEN_LEN = 4  # [STRUCTURAL]

# ---------------------------------------------------------------------------
# Agent Discoverability  (geo_auditor/checks/discoverability.py)
# ---------------------------------------------------------------------------
# Final score blends three sub-scores. Within the bots sub-score, live-search
# bots dominate because blocking them removes a site from answers TODAY, while
# training bots only affect future models. [HEURISTIC] weights.
DISCOVER_BOTS_LIVE_WEIGHT   = 0.85   # live-search bots within the bots sub-score
DISCOVER_BOTS_TRAIN_WEIGHT  = 0.15   # training-only bots within the bots sub-score
DISCOVER_WEIGHT_BOTS    = 0.50       # bots sub-score share of the final score
DISCOVER_WEIGHT_LLMS    = 0.35       # llms.txt sub-score share
DISCOVER_WEIGHT_SITEMAP = 0.15       # sitemap sub-score share
DISCOVER_LLMS_PRESENT_SCORE = 1.0    # llms.txt present and well-formed
DISCOVER_LLMS_ISSUES_SCORE  = 0.6    # llms.txt present but missing required sections

# ---------------------------------------------------------------------------
# Content Freshness  (geo_auditor/checks/freshness.py)
# ---------------------------------------------------------------------------
# Age-in-days -> 0..1 multiplier. The 30-day cliff is [GROUNDED]: Perplexity
# applies a strict ~30-day recency window (Red-Engage / Perplexity research).
# The 90/180/365 steps below it are [HEURISTIC] — a smooth decay would be
# defensible too; these round numbers are not measured.
FRESHNESS_TIERS = [
    (30,  1.00),   # [GROUNDED]  within Perplexity's recency window
    (90,  0.70),   # [HEURISTIC] "recent"
    (180, 0.45),   # [HEURISTIC] "aging"
    (365, 0.20),   # [HEURISTIC] "stale, over 6 months"
]
FRESHNESS_STALE_SCORE = 0.10        # [HEURISTIC] older than 365d
# No FRESHNESS_UNKNOWN_SCORE by design: an undeterminable date returns
# measured=False and is excluded from the score, not scored as stale.

# A Last-Modified header younger than this many days, with NO structured date
# to corroborate it, is discarded: CDN/SSR pages stamp "now" on every request.
FRESHNESS_CDN_GUARD_DAYS = 1        # [HEURISTIC] false-fresh guard
FRESHNESS_PAGE_TEXT_SCAN_CHARS = 3000  # [STRUCTURAL] how far into visible text to scan for a date label

# ---------------------------------------------------------------------------
# Markdown-safe Structure  (geo_auditor/checks/markdown_structure.py)
# ---------------------------------------------------------------------------
# A question heading "counts" only if the paragraph directly below it is a
# real answer — long enough to be substantive, short enough to be a lead.
# Both bounds are [STRUCTURAL] detection cutoffs, not quality judgments: a
# 251-word paragraph is not "worse", it just falls outside the lead pattern.
MARKDOWN_ANSWER_MIN_WORDS = 15
MARKDOWN_ANSWER_MAX_WORDS = 250

# Count of question->answer headings -> 0-100 score. [HEURISTIC] throughout;
# the "3 well-formed Q&A blocks is good" target comes from cited-source pattern
# analysis but the exact point values are unmeasured. 5+ headings -> 100.
MARKDOWN_SCORE_TIERS = {
    0: 20.0,
    1: 45.0,
    2: 65.0,
    3: 80.0,
    4: 90.0,
}
MARKDOWN_SCORE_MAX = 100.0          # 5 or more question->answer headings

# Block-level tags scanned when locating the element directly after a heading.
# [STRUCTURAL] — mechanical, not a scoring number.
MARKDOWN_BLOCK_TAGS = [
    "p", "ul", "ol", "table", "div", "h1", "h2", "h3", "h4",
    "h5", "h6", "blockquote", "pre", "section", "figure",
]

# ---------------------------------------------------------------------------
# Fact Density & Structure  (geo_auditor/checks/fact_density.py)
# ---------------------------------------------------------------------------
# Each component is normalised to 0..1 by dividing the raw count by a target,
# then capped at 1.0. All targets are [HEURISTIC].
#
# KNOWN LIMITATION — saturation. These targets are low enough that an ordinary
# content page pins three of the four components at 1.0, so the check barely
# discriminates good from excellent. Proper fix is a calibration pass against
# pages known to win/lose AI citations; until then, read this check as
# near-binary rather than swapping in another uncalibrated guess.
FACT_DENSITY_TARGET_PCT = 1.0       # ~1 fact per 100 words saturates the density component
FACT_STRUCTURE_TARGET = 5           # h2+h3+lists count that saturates the structure component
FACT_SCHEMA_TARGET = 2              # distinct JSON-LD @types that saturates the schema component
FACT_LINKS_TARGET = 3               # outbound links that saturate the links component

# Weights blending the four components (must sum to 1.0). [HEURISTIC].
FACT_WEIGHT_DENSITY = 0.40
FACT_WEIGHT_STRUCTURE = 0.30
FACT_WEIGHT_SCHEMA = 0.20
FACT_WEIGHT_LINKS = 0.10

FACT_TEXT_WORD_LIMIT = 600          # [STRUCTURAL] words of body text sampled for density/LLM
FACT_WEAK_PARA_CHARS = 200          # [STRUCTURAL] max chars of the quoted weak paragraph

# ---------------------------------------------------------------------------
# Direct Answer Lead  (geo_auditor/checks/direct_answer.py)
# ---------------------------------------------------------------------------
# This check IS an LLM judgment (fact-vs-judgment: "is the lead self-contained?"
# is genuinely subjective). These constants only shape how the LLM's own
# confidence maps to a score. [HEURISTIC].
DIRECT_ANSWER_LEAD_WORDS = 100      # [STRUCTURAL] words of lead sent to the LLM
DIRECT_ANSWER_PASS_BASE = 50.0      # self-contained -> 50 + confidence*50
DIRECT_ANSWER_PASS_SPAN = 50.0
DIRECT_ANSWER_FAIL_SPAN = 40.0      # not self-contained -> confidence*40

# ---------------------------------------------------------------------------
# Citation Density  (geo_auditor/checks/citation_density.py)
# ---------------------------------------------------------------------------
# Attribution signals = <blockquote> + <cite> + attribution phrases in text.
# Intentionally excludes raw outbound links (already counted in Fact Density).
# (max_total, score) pairs — first match where total <= max_total wins.
# [HEURISTIC] throughout — not empirically calibrated.
CITATION_SCORE_TIERS = [
    (0,  15.0),   # [HEURISTIC] no attribution at all
    (2,  40.0),   # [HEURISTIC] minimal
    (4,  65.0),   # [HEURISTIC] some
    (7,  80.0),   # [HEURISTIC] good
]
CITATION_SCORE_MAX = 100.0          # [HEURISTIC] 8+ signals
CITATION_TEXT_SCAN_CHARS = 5000     # [STRUCTURAL] body text scanned for attribution phrases

# ---------------------------------------------------------------------------
# Content Depth  (geo_auditor/checks/content_depth.py)
# ---------------------------------------------------------------------------
# (max_words_inclusive, score) — first match where word_count <= max_words wins.
# Benchmarked against company/service pages, not blog posts. [HEURISTIC].
DEPTH_SCORE_TIERS = [
    (149,  15.0),   # [HEURISTIC] <150 words — dangerously thin, likely filtered
    (299,  40.0),   # [HEURISTIC] 150-299 words — thin
    (599,  65.0),   # [HEURISTIC] 300-599 words — moderate
    (999,  85.0),   # [HEURISTIC] 600-999 words — substantial
]
DEPTH_SCORE_MAX = 100.0             # [HEURISTIC] 1000+ words

# ---------------------------------------------------------------------------
# Organization E-E-A-T  (geo_auditor/checks/org_eeat.py)
# ---------------------------------------------------------------------------
# Signal level (0-4) -> score. The level is assigned by org_eeat.py via one of
# two completeness ladders (NAP for LocalBusiness, identity for other entities).
# [HEURISTIC] score values — tiers are logical but not empirically calibrated.
ORG_EEAT_SCORES = {
    0: 15.0,   # [HEURISTIC] no Organization/LocalBusiness schema
    1: 40.0,   # [HEURISTIC] schema + name only
    2: 65.0,   # [HEURISTIC] partial completeness
    3: 85.0,   # [HEURISTIC] strong completeness
    4: 100.0,  # [HEURISTIC] full completeness
}

# ---------------------------------------------------------------------------
# Wikipedia Presence  (geo_auditor/checks/wikipedia.py)
# ---------------------------------------------------------------------------
WIKIPEDIA_FOUND_SCORE     = 100.0   # [GROUNDED] Wikipedia coverage = encyclopedic brand authority
WIKIPEDIA_NOT_FOUND_SCORE =  20.0   # [HEURISTIC] no article — expected for most local businesses

# ---------------------------------------------------------------------------
# Community Citations  (geo_auditor/checks/community_citations.py)
# ---------------------------------------------------------------------------
# Counts forum/discussion domains (Reddit, HN, Stack Overflow...) in the probe's
# grounding sources — citations within 8 probe answers, not total threads on
# Reddit, so the scale is small. [HEURISTIC] throughout.
COMMUNITY_SCORE_TIERS = [
    (0,   25.0),   # [HEURISTIC] no community source cited at all
    (1,   55.0),   # [HEURISTIC] a single community citation
    (3,   80.0),   # [HEURISTIC] 2–3 citations
]
COMMUNITY_SCORE_MAX = 100.0         # [HEURISTIC] 4+ community citations

# Minimum grounded queries before a community rate is reported at all.
# [STRUCTURAL] Gemini only web-searches some queries, so the denominator varies
# per run; below this, the sample is too small to score without reporting
# query-generation luck as a property of the business. A future fix is to pin a
# review-intent branded query so the denominator is comparable every run.
COMMUNITY_MIN_GROUNDED_QUERIES = 3

# ---------------------------------------------------------------------------
# Overall scorer  (geo_auditor/scorer.py)
# ---------------------------------------------------------------------------
# Score bands. [HEURISTIC] labels for presentation only.
SCORE_BANDS = [
    (90, "Excellent"),
    (75, "Good"),
    (56, "Fair"),
    (31, "Poor"),
    (0,  "Critical"),
]

# Overall = Visibility*0.50 + sum(check.score * weight). Must total 1.00.
# KNOWN ISSUE (council, deferred): several on-page checks are correlated
# (structure / fact density / direct answer all co-move with content quality),
# so summing them as independent weights double-counts. Revisit before trusting
# small score deltas. [HEURISTIC] weights.
VISIBILITY_WEIGHT = 0.50
CHECK_WEIGHTS = {
    "Direct Answer Lead":       0.11,
    "Fact Density & Structure": 0.04,
    "Agent Discoverability":    0.09,
    "Content Freshness":        0.05,
    "Markdown-safe Structure":  0.05,
    "Citation Density":         0.04,
    "Organization E-E-A-T":     0.04,
    "Content Depth":            0.04,
    "Wikipedia Presence":       0.02,
    "Community Citations":      0.02,
    # + Visibility 0.50 = 1.00
}
CHECK_WEIGHT_DEFAULT = 0.15         # fallback weight for a check not listed above

# Weights are renormalised at scoring time over the checks that actually
# measured something (CheckResult.measured). A check that could not run is
# dropped and the remainder rescaled, so an unreachable API never costs the
# site points. See scorer.score_audit.
