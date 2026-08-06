import httpx
import trafilatura
from geo_auditor.models import FetchResult

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GEOAuditor/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch(url: str, timeout: int = 15) -> FetchResult:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        text = trafilatura.extract(html, include_tables=True, include_links=True) or ""
        if not text:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        return FetchResult(html=html, text=text, url=str(resp.url), status_code=resp.status_code)
    except Exception as e:
        return FetchResult(html="", text="", url=url, status_code=0, error=str(e))
