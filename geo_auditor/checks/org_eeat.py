"""Organization / Local Business E-E-A-T check.

Measures structured-data completeness for the business entity itself.
Not personal authorship (rare on company pages), but Organization /
LocalBusiness JSON-LD that AI engines use to verify a business page's
identity and trust it as an authoritative source for local queries.

Google AI Overviews, Gemini grounding, and Bing Copilot all use
LocalBusiness/Organization schema for entity disambiguation, contact
panel population, and local-query authority ranking.

Completeness is scored on a 0-4 signal level (ORG_EEAT_SCORES in thresholds.py)
via one of two ladders:
  - LocalBusiness: physical-contact NAP (name + phone + address) + sameAs
  - other entities: verifiable identity (sameAs, legalName, foundingDate, logo)

Pure code — no LLM calls.
"""
from geo_auditor.jsonld import find_by_type, type_names
from geo_auditor.models import FetchResult, CheckResult
from geo_auditor.thresholds import ORG_EEAT_SCORES

# Entity types that imply a physical place of business, where NAP (Name,
# Address, Phone) is the correct completeness bar.
_LOCAL_TYPES = frozenset({
    "LocalBusiness",
    "Store", "Restaurant", "MedicalBusiness", "HealthAndBeautyBusiness",
    "HomeAndConstructionBusiness", "LegalService", "FinancialService",
    "ProfessionalService", "EntertainmentBusiness", "FoodEstablishment",
    "AutomotiveBusiness", "RealEstateAgent", "TravelAgency",
    "HotelOrMotel", "LodgingBusiness", "SportsActivityLocation",
})

# All @type values representing a business entity.
_ORG_TYPES = _LOCAL_TYPES | {"Organization", "Corporation", "NGO", "EducationalOrganization"}


def _find_org_schema(html: str) -> dict | None:
    candidates = find_by_type(html, _ORG_TYPES)
    if not candidates:
        return None
    # Prefer a physical-location type over generic Organization — it carries the
    # NAP fields and tells us which scoring ladder applies.
    for c in candidates:
        if any(t in _LOCAL_TYPES for t in type_names(c)):
            return c
    return candidates[0]


def _is_local_type(schema: dict) -> bool:
    """True when the entity claims a physical place of business, which selects
    the NAP scoring ladder over the identity ladder."""
    return any(t in _LOCAL_TYPES for t in type_names(schema))


def _has_address(schema: dict) -> bool:
    addr = schema.get("address")
    if not addr:
        return False
    if isinstance(addr, str):
        return len(addr.strip()) > 5
    if isinstance(addr, dict):
        return bool(addr.get("streetAddress") or addr.get("addressLocality"))
    return False


def _same_as_count(schema: dict) -> int:
    same = schema.get("sameAs")
    if not same:
        return 0
    return 1 if isinstance(same, str) else len(same)


def check_org_eeat(fetch_result: FetchResult) -> CheckResult:
    schema = _find_org_schema(fetch_result.html)

    if not schema:
        return CheckResult(
            name="Organization E-E-A-T",
            score=ORG_EEAT_SCORES[0],
            max_score=100.0,
            evidence="No Organization or LocalBusiness JSON-LD schema found",
            fix_hint=(
                "Add a LocalBusiness JSON-LD block to your page with: name, url, "
                "telephone, address (PostalAddress with streetAddress + addressLocality), "
                "and sameAs (array of your Google Business Profile, Facebook, and LinkedIn "
                "URLs). AI engines use this to verify business identity and rank the page "
                "as authoritative for local queries."
            ),
            details={
                "signal_level": 0, "schema_type": None,
                "has_name": False, "has_phone": False,
                "has_address": False, "same_as_count": 0,
            },
        )

    schema_type = schema.get("@type", "Organization")
    if isinstance(schema_type, list):
        schema_type = next((t for t in schema_type if t in _ORG_TYPES), schema_type[0])

    has_name = bool(schema.get("name", "").strip())
    has_phone = bool(schema.get("telephone") or schema.get("phone"))
    has_address = _has_address(schema)
    sa_count = _same_as_count(schema)
    # Identity signals that verify an entity without needing a street address.
    identity_fields = [k for k in ("legalName", "foundingDate", "logo", "url", "description")
                       if schema.get(k)]
    is_local = _is_local_type(schema)

    # Two ladders by entity kind. A LocalBusiness is scored on physical-contact
    # NAP (name + phone + address); every other entity (software, SaaS,
    # publisher, consultancy) is scored on verifiable identity instead — sameAs
    # profiles, legalName, founding date, logo — since it has no storefront.
    if is_local:
        if has_name and has_phone and has_address and sa_count > 0:
            level = 4
        elif has_name and has_phone and has_address:
            level = 3
        elif has_name and (has_phone or has_address):
            level = 2
        elif has_name:
            level = 1
        else:
            level = 0
    else:
        contact = has_phone or has_address
        if has_name and sa_count >= 2 and len(identity_fields) >= 3:
            level = 4
        elif has_name and (sa_count >= 1 or contact) and len(identity_fields) >= 2:
            level = 3
        elif has_name and (sa_count >= 1 or contact or len(identity_fields) >= 2):
            level = 2
        elif has_name:
            level = 1
        else:
            level = 0

    score = ORG_EEAT_SCORES[level]

    parts = [f"@type: {schema_type}"]
    if has_name:
        parts.append(f"name: {schema.get('name')!r}")
    if has_phone:
        parts.append("telephone ✓")
    if has_address:
        parts.append("address ✓")
    if sa_count:
        parts.append(f"sameAs ({sa_count} link{'s' if sa_count != 1 else ''})")
    if identity_fields:
        parts.append(f"identity: {', '.join(identity_fields)}")

    evidence = "Schema: " + " | ".join(parts)

    if level >= 4:
        fix_hint = ""
    elif is_local:
        missing = []
        if not has_phone:
            missing.append("telephone")
        if not has_address:
            missing.append("address (PostalAddress with streetAddress + addressLocality)")
        if not sa_count:
            missing.append("sameAs (Google Business Profile, Facebook, LinkedIn URLs)")
        fix_hint = (
            f"Your {schema_type} schema is incomplete — missing: {', '.join(missing)}. "
            "Complete NAP (Name, Address, Phone) in structured data is a key local "
            "AI-search trust signal."
        )
    else:
        # Non-local entity: ask for identity signals, never a street address.
        missing = []
        if sa_count < 2:
            missing.append(
                "sameAs (link every official profile you control — LinkedIn, X, "
                "GitHub, Crunchbase, YouTube)"
            )
        for field, hint in (
            ("legalName", "legalName (registered company name)"),
            ("foundingDate", "foundingDate"),
            ("logo", "logo (absolute URL)"),
            ("description", "description (one-sentence summary of what you do)"),
        ):
            if not schema.get(field):
                missing.append(hint)
        fix_hint = (
            f"Your {schema_type} schema is missing: {', '.join(missing[:4])}. "
            "AI engines use these to resolve which real-world entity the page "
            "refers to and whether to trust it as authoritative. A street address "
            "is not required for an entity with no public premises — sameAs "
            "profiles and legalName do the disambiguating work instead."
        )

    return CheckResult(
        name="Organization E-E-A-T",
        score=score,
        max_score=100.0,
        evidence=evidence,
        fix_hint=fix_hint,
        details={
            "signal_level": level,
            "schema_type": schema_type,
            "is_local_entity": is_local,
            "has_name": has_name,
            "has_phone": has_phone,
            "has_address": has_address,
            "same_as_count": sa_count,
            "identity_fields": identity_fields,
        },
    )
