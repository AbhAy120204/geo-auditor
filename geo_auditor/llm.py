import os
import time
from urllib.parse import urlparse

import httpx
from google import genai
from google.genai import types

from geo_auditor.models import LLMConfig

_VERTEX_REDIRECT_HOST = "vertexaisearch.cloud.google.com"


def _resolve_redirect_domain(uri: str) -> str | None:
    """Resolve a Vertex AI grounding redirect to its real bare domain.

    Vertex AI wraps every source URL in an opaque redirect
    (https://vertexaisearch.cloud.google.com/grounding-api-redirect/<hash>);
    a live HEAD request is the only way to learn the destination. Called only
    when web.title is not already a usable domain, since the HEAD request is slow.

    Returns the bare domain (e.g. "litellm.ai") or None on failure/timeout.
    """
    if not uri or _VERTEX_REDIRECT_HOST not in uri:
        return None
    try:
        resp = httpx.head(uri, follow_redirects=True, timeout=2.0)
        real_domain = urlparse(str(resp.url)).netloc.replace("www.", "").lower()
        return real_domain if "." in real_domain else None
    except Exception:
        return None


def _looks_like_domain(title: str) -> bool:
    """True when web.title is already a bare domain, not a page headline."""
    if not title or " " not in title.strip():
        return "." in title and "/" not in title
    return False


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
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)
    return ""


def web_search_query(
    config: LLMConfig,
    prompt: str,
    retries: int = 2,
) -> tuple[str, list[str], list[str], list[str]]:
    """Live web search via Gemini's google_search grounding tool.

    Returns:
        answer_text     — Gemini's synthesized answer
        source_domains  — bare domains (from web.title), used for citation detection
        source_uris     — Vertex AI redirect URIs (from web.uri), used for display;
                          index-aligned with source_domains
        gemini_searches — the Google queries Gemini issued internally

    Two source lists because web.uri is an opaque redirect that does not reveal
    its destination domain, while web.title carries the bare domain used for
    cited/mentioned matching.
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
            gemini_searches: list[str] = []
            # domain -> first redirect URI seen for it; keeps the two output
            # lists deduped and index-aligned.
            by_domain: dict[str, str] = {}

            if resp.candidates and resp.candidates[0].grounding_metadata:
                meta = resp.candidates[0].grounding_metadata

                for chunk in (getattr(meta, "grounding_chunks", []) or []):
                    web = getattr(chunk, "web", None)
                    if not web:
                        continue
                    title = (getattr(web, "title", "") or "").strip().lower()
                    uri = (getattr(web, "uri", "") or "").strip()

                    # Prefer web.title (already a bare domain); fall back to a
                    # redirect HEAD request only when it is a page headline.
                    domain = title if _looks_like_domain(title) else None
                    if domain is None and uri:
                        domain = _resolve_redirect_domain(uri)

                    if domain and domain not in by_domain:
                        by_domain[domain] = uri

                for q in (getattr(meta, "web_search_queries", []) or []):
                    if isinstance(q, str) and q.strip():
                        gemini_searches.append(q.strip())

            source_domains = list(by_domain.keys())
            source_uris = list(by_domain.values())

            return answer, source_domains, source_uris, gemini_searches
        except Exception as e:
            if attempt == retries:
                return f"[error: {e}]", [], [], []
            time.sleep(2 ** attempt)
    return "", [], [], []
