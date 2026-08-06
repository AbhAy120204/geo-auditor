import os
import time

from google import genai
from google.genai import types

from geo_auditor.models import LLMConfig


def _gemini_client() -> genai.Client:
    key = os.getenv("GEMINI_API_KEY", "").strip('"').strip("'")
    return genai.Client(api_key=key)


def chat_complete(
    config: LLMConfig,
    messages: list[dict],
    json_mode: bool = False,
    retries: int = 2,
) -> str:
    """Chat completion via Gemini. config.model_name used as the Gemini model id."""
    client = _gemini_client()
    # Convert OpenAI-style messages to a single prompt string
    parts = []
    system_text = ""
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_text = content
        else:
            parts.append(content)
    prompt = "\n\n".join(parts)

    cfg_kwargs = {}
    if system_text:
        cfg_kwargs["system_instruction"] = system_text
    if json_mode:
        cfg_kwargs["response_mime_type"] = "application/json"

    for attempt in range(retries + 1):
        try:
            resp = client.models.generate_content(
                model=config.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(**cfg_kwargs) if cfg_kwargs else None,
            )
            return resp.text or ""
        except Exception as e:
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)
    return ""


def web_search_query(
    config: LLMConfig,
    prompt: str,
    retries: int = 2,
) -> tuple[str, list[str]]:
    """Live web search via Gemini google_search grounding tool.
    Returns (answer_text, source_domains).
    """
    client = _gemini_client()
    for attempt in range(retries + 1):
        try:
            resp = client.models.generate_content(
                model=config.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            answer = resp.text or ""
            sources: list[str] = []
            if resp.candidates and resp.candidates[0].grounding_metadata:
                meta = resp.candidates[0].grounding_metadata
                for chunk in (getattr(meta, "grounding_chunks", []) or []):
                    web = getattr(chunk, "web", None)
                    if web:
                        # title is the plain domain (e.g. "rotorooter.com")
                        title = getattr(web, "title", "") or ""
                        uri = getattr(web, "uri", "") or ""
                        # prefer clean domain from title; fallback to uri
                        domain = title.strip()
                        if domain and "." in domain:
                            sources.append(domain.lower())
                        elif uri:
                            sources.append(uri)
            return answer, sources
        except Exception as e:
            if attempt == retries:
                return f"[error: {e}]", []
            time.sleep(2 ** attempt)
    return "", []
