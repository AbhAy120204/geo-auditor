"""Shared JSON-LD extraction, used by fact_density, org_eeat, and freshness.

Handles the four shapes seen in the wild:
    {"@type": "Organization", ...}                  flat object
    {"@context": ..., "@graph": [ {...}, {...} ]}   graph wrapper
    [ {...}, {...} ]                                top-level array
    nested objects under known container keys       e.g. mainEntity
"""
import json

from bs4 import BeautifulSoup

# Keys whose values hold further schema.org objects worth surfacing.
_NESTED_KEYS = ("mainEntity", "mainEntityOfPage", "itemListElement", "hasPart")


def _walk(obj, out: list, depth: int = 0, nested: bool = False) -> None:
    """Collect every dict carrying an @type. @graph is always followed.

    `nested` additionally descends into container keys like mainEntity. Off by
    default so a single FAQPage with N questions counts as one entity, not
    N+1 distinct types.
    """
    if depth > 6:
        return
    if isinstance(obj, list):
        for item in obj:
            _walk(item, out, depth + 1, nested)
        return
    if not isinstance(obj, dict):
        return

    if "@graph" in obj:
        _walk(obj["@graph"], out, depth + 1, nested)

    if obj.get("@type"):
        out.append(obj)

    if nested:
        for key in _NESTED_KEYS:
            if key in obj:
                _walk(obj[key], out, depth + 1, nested)


def iter_jsonld_objects(html: str, nested: bool = False) -> list[dict]:
    """Return the schema.org objects on the page, flattened.

    Malformed blocks are skipped rather than raising — a single broken
    <script> tag must not blind a check to the valid ones beside it.
    """
    soup = BeautifulSoup(html, "lxml")
    objects: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or tag.get_text() or ""
        if not raw.strip():
            continue
        try:
            _walk(json.loads(raw), objects, nested=nested)
        except Exception:
            continue
    return objects


def type_names(obj: dict) -> list[str]:
    """@type normalised to a list — schema.org allows a string or an array."""
    at = obj.get("@type")
    if not at:
        return []
    return [at] if isinstance(at, str) else [t for t in at if isinstance(t, str)]


def distinct_types(html: str) -> set[str]:
    """Distinct @types of the page's top-level / @graph entities."""
    found: set[str] = set()
    for obj in iter_jsonld_objects(html):
        found.update(type_names(obj))
    return found


def find_by_type(html: str, wanted: set[str], nested: bool = False) -> list[dict]:
    """All objects whose @type intersects `wanted`."""
    return [
        obj for obj in iter_jsonld_objects(html, nested=nested)
        if any(t in wanted for t in type_names(obj))
    ]
