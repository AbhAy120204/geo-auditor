import os

from dotenv import load_dotenv

from geo_auditor.models import LLMConfig

load_dotenv()

# Gemini model names — three tiers matched to task effort:
#   PROBE    — grounded web search queries (needs full capability + search tool)
#   ANALYSIS — quality judgments: direct-answer lead, fact-density fix hint
#   FAST     — low-effort structured tasks: query generation, status classification
_PROBE_MODEL    = "gemini-3.8-flash"      # grounded web search (google_search tool) — latest flash
_ANALYSIS_MODEL = "gemini-3.8-flash"      # quality judgments: direct-answer lead, fact hints
_FAST_MODEL     = "gemini-2.5-flash-lite" # low-effort structured tasks: query gen, status classification


def _gemini_config(model_name: str) -> LLMConfig | None:
    key = os.getenv("GEMINI_API_KEY", "").strip('"').strip("'")
    if not key:
        return None
    # deployment_name / api_key / api_base / api_version fields reused as
    # model_name / api_key / unused / unused for Gemini — no breaking change to LLMConfig
    return LLMConfig(
        deployment_name=model_name,
        api_key=key,
        api_base="https://generativelanguage.googleapis.com",
        api_version="v1beta",
        model_name=model_name,
        max_completion_tokens=8192,
    )


def get_probe_config() -> LLMConfig | None:
    return _gemini_config(_PROBE_MODEL)


def get_analysis_config() -> LLMConfig | None:
    return _gemini_config(_ANALYSIS_MODEL)


def get_fast_config() -> LLMConfig | None:
    return _gemini_config(_FAST_MODEL)
