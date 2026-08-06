from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    deployment_name: str
    api_key: str
    api_base: str
    api_version: str
    model_name: str
    max_completion_tokens: int


@dataclass
class FetchResult:
    html: str
    text: str
    url: str
    status_code: int
    error: str | None = None


@dataclass
class BusinessProfile:
    name: str
    category: str
    city: str
    offering: str
    domain: str


@dataclass
class QueryResult:
    query: str
    status: str        # "cited" | "mentioned" | "absent" | "error"
    snippet: str
    sources: list[str]
    weight: float      # 2.0 for unbranded, 1.0 for branded


@dataclass
class VisibilityResult:
    score: float       # 0-100
    queries: list[QueryResult]
    competitor_mentions: dict[str, int] = field(default_factory=dict)
    is_mocked: bool = False


@dataclass
class CheckResult:
    name: str
    score: float       # 0-100 normalised
    max_score: float   # always 100
    evidence: str      # verbatim text from the page
    fix_hint: str      # raw hint for fixer.py
    details: dict      # check-specific raw values


@dataclass
class Fix:
    title: str
    effort: str        # "low" | "medium" | "high"
    impact: str        # "low" | "medium" | "high"
    copy_paste: str    # ready-to-use text/code
    explanation: str   # plain English, jargon explained


@dataclass
class ScoredAudit:
    url: str
    profile: BusinessProfile
    visibility: VisibilityResult
    checks: list[CheckResult]
    overall_score: float
    band: str
    fixes: list[Fix]
    is_mocked: bool
