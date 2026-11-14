"""Read-only import of BankVault research (../bankvault/bank-intelligence) for bank-specific interviews.

Nothing here writes to BankVault. Data is loaded lazily and cached in memory. Every fact we surface
carries the bank slug and verificationStatus from the source records so the interviewer can say
"verified" vs "reported".
"""
import json
import os
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
BANKVAULT = os.environ.get("GAUNTLET_BANKVAULT",
                           os.path.normpath(os.path.join(HERE, "..", "..", "..", "bankvault", "bank-intelligence", "data", "banks")))

_CACHE: Dict[str, Dict] = {}

# Display names for banks the candidate targets; others fall back to slug titles.
DISPLAY = {
    "goldman-sachs": "Goldman Sachs", "jp-morgan": "J.P. Morgan", "morgan-stanley": "Morgan Stanley",
    "evercore": "Evercore", "centerview-partners": "Centerview Partners", "lazard": "Lazard",
    "moelis-and-company": "Moelis & Company", "guggenheim-securities": "Guggenheim Securities",
    "wells-fargo-securities": "Wells Fargo", "bank-of-america-securities": "Bank of America",
    "barclays": "Barclays", "houlihan-lokey": "Houlihan Lokey", "jefferies": "Jefferies",
    "leerink-partners": "Leerink Partners", "santander-cib": "Santander CIB", "ubs": "UBS",
    "citi": "Citi", "pjt-partners": "PJT Partners", "perella-weinberg-partners": "Perella Weinberg",
    "rothschild-and-co": "Rothschild & Co", "rbc-capital-markets": "RBC Capital Markets",
    "mizuho": "Mizuho", "oppenheimer": "Oppenheimer", "td-securities": "TD Securities", "bmo-capital-markets": "BMO Capital Markets",
    "deutsche-bank": "Deutsche Bank", "piper-sandler": "Piper Sandler", "william-blair": "William Blair",
    "harris-williams": "Harris Williams", "baird": "Baird", "stifel": "Stifel",
}

PRIORITY = ["goldman-sachs", "jp-morgan", "morgan-stanley", "evercore", "centerview-partners", "lazard",
            "moelis-and-company", "guggenheim-securities", "wells-fargo-securities", "bank-of-america-securities",
            "barclays", "houlihan-lokey", "jefferies", "leerink-partners", "santander-cib", "ubs", "citi",
            "pjt-partners", "perella-weinberg-partners", "rothschild-and-co", "rbc-capital-markets", "mizuho",
            "oppenheimer", "td-securities", "bmo-capital-markets"]


def available() -> bool:
    return os.path.isdir(BANKVAULT)


def _read(slug: str, name: str, key: str) -> List[Dict]:
    p = os.path.join(BANKVAULT, slug, name)
    if not os.path.exists(p):
        return []
    try:
        with open(p) as f:
            return json.load(f).get(key, [])
    except Exception:
        return []


def list_banks() -> List[Dict]:
    if not available():
        return [{"slug": s, "name": DISPLAY.get(s, s), "has_research": False} for s in PRIORITY]
    slugs = sorted(os.listdir(BANKVAULT))
    out = []
    for s in PRIORITY + [x for x in slugs if x not in PRIORITY]:
        if s not in slugs:
            continue
        groups = _read(s, "groups.json", "groups")
        deals = _read(s, "deals.json", "deals")
        out.append({"slug": s, "name": DISPLAY.get(s, s.replace("-", " ").title()),
                    "has_research": bool(groups or deals), "n_groups": len(groups), "n_deals": len(deals)})
    return out


def bank(slug: str) -> Optional[Dict]:
    if slug in _CACHE:
        return _CACHE[slug]
    if not available() or not os.path.isdir(os.path.join(BANKVAULT, slug)):
        return None
    profile = {}
    p = os.path.join(BANKVAULT, slug, "profile.json")
    if os.path.exists(p):
        with open(p) as f:
            profile = json.load(f)
    brief = ""
    bp = os.path.join(BANKVAULT, slug, "brief.md")
    if os.path.exists(bp):
        with open(bp) as f:
            brief = f.read()
    data = {
        "slug": slug, "name": DISPLAY.get(slug, slug.replace("-", " ").title()),
        "description": profile.get("description", ""), "sectorTags": profile.get("sectorTags", []),
        "productTags": profile.get("productTags", []), "offices": profile.get("offices", []),
        "groups": _read(slug, "groups.json", "groups"),
        "deals": _read(slug, "deals.json", "deals"),
        "recruiting": _read(slug, "recruiting.json", "programs"),
        "culture": _read(slug, "culture.json", "reports"),
        "insights": _read(slug, "insights.json", "insights"),
        "claims": _read(slug, "claims.json", "claims"),
        "brief": brief,
    }
    _CACHE[slug] = data
    return data


def group(slug: str, group_id: str) -> Optional[Dict]:
    b = bank(slug)
    if not b:
        return None
    for g in b["groups"]:
        if g.get("id") == group_id or g.get("name", "").lower() == group_id.lower():
            return g
    return None


def verified_deals(slug: str, sector: Optional[str] = None, limit: int = 5) -> List[Dict]:
    b = bank(slug)
    if not b:
        return []
    deals = [d for d in b["deals"] if d.get("verificationStatus") == "verified"]
    if sector:
        s = sector.lower()
        deals = [d for d in deals if s in (d.get("industry", "") + " " + d.get("subsector", "")).lower()] or deals
    deals.sort(key=lambda d: d.get("announcedAt", ""), reverse=True)
    return deals[:limit]


SECTOR_KEYWORDS = {
    "healthcare": ["health", "pharma", "biotech", "medtech", "life science"],
    "energy": ["energy", "power", "renewable", "oil", "gas", "utilit", "natural resource"],
    "fig": ["fig", "financial institution", "bank", "insurance", "fintech"],
    "tmt": ["tmt", "tech", "media", "telecom", "software"],
    "industrials": ["industrial", "aerospace", "defense", "transport"],
    "m&a": ["m&a", "merger"],
    "consumer": ["consumer", "retail"],
    "sports": ["sport", "gaming", "leisure"],
}


def groups_for_sector(slug: str, sector: str) -> List[Dict]:
    b = bank(slug)
    if not b:
        return []
    kws = SECTOR_KEYWORDS.get(sector.lower(), [sector.lower()])
    out = []
    for g in b["groups"]:
        blob = (g.get("name", "") + " " + g.get("sector", "") + " " + " ".join(g.get("subsectors", []))).lower()
        if any(k in blob for k in kws):
            out.append(g)
    return out


def context_for_interview(slug: Optional[str], group_id: Optional[str], sector: Optional[str]) -> Dict:
    """Compact, source-labelled context the interviewer may rely on. Empty when nothing is verified."""
    if not slug:
        return {}
    b = bank(slug)
    if not b:
        return {"slug": slug, "name": DISPLAY.get(slug, slug), "note": "No BankVault research for this bank; firm-specific questions stay generic."}
    g = group(slug, group_id) if group_id else None
    if not g and sector:
        gs = groups_for_sector(slug, sector)
        g = gs[0] if gs else None
    deals = verified_deals(slug, sector or (g or {}).get("sector"), limit=4)
    recruiting = [r for r in b["recruiting"] if "summer" in json.dumps(r).lower() or "analyst" in json.dumps(r).lower()][:3]
    return {
        "slug": slug, "name": b["name"], "description": b["description"][:600],
        "group": {k: g.get(k) for k in ("id", "name", "sector", "subsectors", "principalOffice", "description", "tier", "advantages", "limitations")} if g else None,
        "deals": [{k: d.get(k) for k in ("name", "target", "acquirer", "valueAmount", "valueNote", "announcedAt", "dealType", "industry", "rationale", "keyDetails", "verificationStatus")} for d in deals],
        "recruiting": recruiting,
        "culture_notes": [c.get("summary") or c.get("text") or json.dumps(c)[:300] for c in b["culture"][:3]],
        "source": "BankVault bank-intelligence (read-only snapshot)",
    }
