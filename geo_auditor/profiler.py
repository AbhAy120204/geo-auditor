import json
from urllib.parse import urlparse
from geo_auditor.models import FetchResult, LLMConfig, BusinessProfile
from geo_auditor.llm import chat_complete

SYSTEM = """You are a business analyst. Given webpage content, extract key business details.
Return ONLY valid JSON with keys: name, category, city, offering.
- name: the business name
- category: the type of business (e.g. "Italian restaurant", "digital marketing agency")
- city: the primary city/location served, or "unknown" if not clear
- offering: the main product or service in 5 words or fewer
"""


def profile(fetch_result: FetchResult, config: LLMConfig) -> BusinessProfile:
    domain = urlparse(fetch_result.url).netloc.replace("www.", "")
    content_preview = fetch_result.text[:1500]
    user_content = f"URL: {fetch_result.url}\n\n{content_preview}"
    try:
        raw = chat_complete(config, [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_content},
        ], json_mode=True)
        data = json.loads(raw)
        return BusinessProfile(
            name=data.get("name") or domain,
            category=data.get("category") or "business",
            city=data.get("city") or "unknown",
            offering=data.get("offering") or "products and services",
            domain=domain,
        )
    except Exception:
        return BusinessProfile(
            name=domain, category="business", city="unknown",
            offering="products and services", domain=domain,
        )
