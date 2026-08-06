import os

from dotenv import load_dotenv

from geo_auditor.models import LLMConfig

load_dotenv()

# Gemini model names — probe uses the grounded search model, analysis uses the fast model
_PROBE_MODEL = "gemini-2.5-flash"
_ANALYSIS_MODEL = "gemini-2.5-flash"


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
