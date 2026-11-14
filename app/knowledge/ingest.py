"""Source ingestion: M&I 400 (2025 and 2009 editions) and the Wall Street Prep Red Book (2021).

The guides stay local. This module reads the PDFs, splits them into (question, answer) records with
section and page references, maps each record to our skill taxonomy and a cognitive level, and writes
`data/knowledge/source_questions.json` (idempotent: ids are stable hashes of source + section +
normalized question text). Nothing from the guides is bundled into the repo; the JSON lives in data/.

Verification status: a record is `verified` when the page marker was found directly around the question
text; otherwise `unverified`.
"""
import hashlib
import json
import os
import re
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
# Derived knowledge (not user state) lives with the project unless overridden, so tests and alternate
# data dirs still see the ingested guides.
KNOWLEDGE_DIR = os.environ.get("GAUNTLET_KNOWLEDGE", os.path.join(HERE, "..", "..", "data", "knowledge"))
OUT_PATH = os.path.join(KNOWLEDGE_DIR, "source_questions.json")
SOURCES_PATH = os.path.join(KNOWLEDGE_DIR, "sources.json")

DEFAULT_CANDIDATES = {
    "mi400_2025": ["~/Downloads/400-Questions-IB-Interview-Guide-2025.pdf"],
    "mi400_2009": ["~/Downloads/400-IB-Questions-Interview-Guide.pdf"],
    "wsp_redbook": ["~/Downloads/WSP_RedBook_r_6ad90a078de88.pdf", "~/Downloads/WSP_RedBook_r_6ad90a05c1c9b.pdf"],
}
SOURCE_META = {
    "mi400_2025": {"title": "400 Questions Guide for Investment Banking Interviews: 2025 Edition", "publisher": "Mergers & Inquisitions / Breaking Into Wall Street", "short": "M&I 400 (2025)"},
    "mi400_2009": {"title": "The 400 Investment Banking Interview Questions & Answers You Need to Know", "publisher": "Mergers & Inquisitions / Breaking Into Wall Street", "short": "M&I 400 (2009)"},
    "wsp_redbook": {"title": "Investment Banking Interview Questions (Red Book), 2021 Edition", "publisher": "Wall Street Prep", "short": "WSP Red Book"},
}

# ------------------------------------------------------------------ taxonomy mapping
# (regex on section/subsection) -> (area, default skill)
SECTION_MAP: List[Tuple[str, str, str]] = [
    (r"culture|commitment|career changer|future|brain teaser|warren buffett|background|analytical / attention|fit / qualitative|personal", "behavioral", "behavioral.fit"),
    (r"accounting.*calc|accounting scenario", "accounting", "accounting.three_statements"),
    (r"accounting|financial statement|accrual|advanced accounting", "accounting", "accounting.three_statements"),
    (r"equity value.*calc|enterprise value.*calc", "valuation", "valuation.ev_equity"),
    (r"equity value|enterprise value", "valuation", "valuation.ev_equity"),
    (r"intrinsic valuation|corporate finance theory", "dcf", "dcf.ufcf"),
    (r"valuation method|relative valuation|metrics and multiples|^valuation", "valuation", "valuation.multiples"),
    (r"discount rate", "dcf", "dcf.wacc"),
    (r"dcf|discounted cash flow", "dcf", "dcf.ufcf"),
    (r"merger model.*calc|accretion", "ma", "ma.accretion_dilution"),
    (r"merger|m&a|mergers", "ma", "ma.rationale"),
    (r"lbo.*calc|lbo modeling test", "lbo", "lbo.paper_lbo"),
    (r"lbo|leveraged buyout|private equity investing", "lbo", "lbo.basics"),
    (r"financial institutions|fig", "fig", "fig.bank_valuation"),
    (r"healthcare|biotech", "healthcare", "healthcare.biotech"),
    (r"oil & gas|oil and gas|o&g", "energy", "energy.reserves"),
    (r"power|utilit|renewable|project finance", "energy", "energy.renewables"),
    (r"restructuring|distressed", "commercial", "commercial.restructuring"),
    (r"debt capital|leveraged finance|levfin|debt & leveraged", "commercial", "commercial.capital_markets"),
    (r"equity capital|ecm|equity financing", "commercial", "commercial.capital_markets"),
    (r"finance concept|understanding banking|^introduction|technical section", "commercial", "commercial.capital_allocation"),
    (r"fit|behavioral|personal background|firm specific|past experience|elevator|teamwork|strength|flaw|recruiting|resume|why banking|outside the box|transaction experience|failure|team / leadership|suggested answers", "behavioral", "behavioral.fit"),
    (r"market knowledge|hedge fund|sales & trading", "commercial", "commercial.markets"),
    (r"consumer|retail|industrial|tmt|technology|saas|real estate|reit|repe|metals|mining|secondaries|private companies|financial sponsors", "commercial", "commercial.industry"),
]
OFF_CORE_SECTIONS = r"hedge fund|sales & trading|secondaries|private capital advisory|behavioral interview advice|behavioral section introduction|warren buffett"
GENERALIST_SECTIONS = r"finance concept|understanding banking|market knowledge|^introduction|technical section|corporate finance theory|intrinsic valuation|brain teaser|analytical"

# finer keyword routing inside an area: (regex on question text) -> skill
SKILL_KEYWORDS: List[Tuple[str, str]] = [
    (r"depreciat|amortiz|pp&e|capex|capital expenditure", "accounting.depreciation"),
    (r"deferred tax|nol|net operating loss|tax rate differ", "accounting.deferred_taxes"),
    (r"working capital|receivable|inventory|payable|accrued|prepaid", "accounting.working_capital"),
    (r"deferred revenue|unearned|revenue recognition|recogni[sz]e revenue", "accounting.revenue_recognition"),
    (r"stock.based|sbc|options expense", "accounting.sbc"),
    (r"goodwill|impair|intangible|write.?down|write.?off", "accounting.goodwill"),
    (r"debt|interest expense|bond|loan|pik", "accounting.debt"),
    (r"cash flow statement|cfs|operating cash|investing|financing", "accounting.cash_flow_statement"),
    (r"lease", "accounting.debt"),
    (r"diluted|treasury stock|option|convertible|rsu|warrant", "valuation.diluted_shares"),
    (r"non.?controlling|minority interest|preferred|pension|net debt|cash.*subtract|subtract.*cash|add.*debt", "valuation.bridge_items"),
    (r"precedent|transaction (comp|multiple)|control premium", "valuation.precedents"),
    (r"comparable|public comps|trading comps|peer", "valuation.comps"),
    (r"ev\s*/\s*ebitda|p\s*/\s*e|multiple|ebitda", "valuation.multiples"),
    (r"football field|range", "valuation.football_field"),
    (r"wacc|cost of capital|cost of debt|capital structure", "dcf.wacc"),
    (r"beta|cost of equity|capm|risk.free|risk premium", "dcf.cost_of_equity"),
    (r"terminal|gordon|perpetuity|exit multiple", "dcf.terminal_value"),
    (r"mid.?year|discount factor|stub", "dcf.discounting"),
    (r"sensitiv", "dcf.sensitivities"),
    (r"unlevered|free cash flow|ufcf|fcf", "dcf.ufcf"),
    (r"dcf|discounted cash flow", "dcf.ufcf"),
    (r"levered free|apv|adjusted present", "dcf.levered_vs_unlevered"),
    (r"accreti|diluti|eps|pro forma", "ma.accretion_dilution"),
    (r"synerg", "ma.synergies"),
    (r"sources and uses|sources & uses", "ma.sources_uses"),
    (r"purchase price allocation|goodwill creat|write.?up|dtl", "ma.purchase_accounting"),
    (r"cash vs|stock vs|cash or stock|exchange ratio|financ", "ma.financing"),
    (r"sell.side|buy.side|process|fairness|cim|data room|hostile|defense", "ma.process"),
    (r"premium|rationale|why.*acquire|strategic", "ma.rationale"),
    (r"irr|moic|return", "lbo.returns"),
    (r"paper lbo|modeling test|mental", "lbo.paper_lbo"),
    (r"tranche|covenant|revolver|term loan|mezzanine|sweep|high.yield", "lbo.debt"),
    (r"candidate|good lbo|ideal", "lbo.candidate"),
    (r"exit|dividend recap", "lbo.exit"),
    (r"p\s*/\s*tbv|tangible book|roe|rotce|dividend discount", "fig.bank_valuation"),
    (r"net interest|nim|provision|loan loss|capital ratio|cet1|basel", "fig.bank_drivers"),
    (r"interest rate", "fig.rates"),
    (r"insurance|asset manager|payments|fintech|broker", "fig.other"),
    (r"rnpv|probability|clinical|phase|biotech|drug|pipeline|patent", "healthcare.biotech"),
    (r"device|medtech|reimburs", "healthcare.medtech"),
    (r"hospital|services|payer|physician", "healthcare.services"),
    (r"reserve|pdp|pud|proved", "energy.reserves"),
    (r"decline|production|type curve", "energy.decline_curves"),
    (r"price deck|henry hub|differential|strip|hedg", "energy.pricing"),
    (r"royalt|mineral|working interest", "energy.interests"),
    (r"nav|pv.?10", "energy.nav"),
    (r"ppa|contracted|merchant|renewable|solar|wind", "energy.renewables"),
    (r"project finance|dscr", "energy.project_finance"),
    (r"market siz|how many", "commercial.market_sizing"),
    (r"moat|competitive advantage|positioning", "commercial.positioning"),
    (r"buyback|dividend|capital allocation|raise (debt|equity)", "commercial.capital_allocation"),
    (r"good (business|company).*good (stock|investment)", "commercial.good_business_good_stock"),
    (r"downside|risk|recession|distress|bankrupt", "commercial.downside"),
    (r"tell me about yourself|walk me through your (resume|cv)|background", "behavioral.tmay"),
    (r"why (investment )?banking|why (this|our) (firm|bank|group)|why not", "behavioral.why_ib"),
    (r"strength|weakness|failure|mistake|flaw", "behavioral.failure"),
    (r"team|leader", "behavioral.leadership"),
    (r"conflict|feedback|disagree", "behavioral.conflict"),
    (r"pressure|hours|deadline|priorit", "behavioral.pressure"),
]

LEVEL_RULES: List[Tuple[str, int]] = [
    (r"^(what is|what are|define|what does .* mean|what('s| is) the difference)", 1),
    (r"^(how do you (calculate|compute|get|derive)|walk me through|what('s| is) the formula|how is .* calculated)", 2),
    (r"^(why|explain why|what('s| is) the (intuition|logic|rationale)|how does .* work)", 3),
    (r"(suppose|assume|if |what happens|how would .* change|now |let'?s say|instead|\$\d|\d+%|\bx\b)", 4),
    (r"(exception|when would you not|edge case|what('s| is) wrong with|limitation|drawback|pitfall|in theory|never|always|unusual|advanced)", 5),
]


def discover_sources() -> Dict[str, Optional[str]]:
    """Find the guides; user overrides in data/knowledge/sources.json {"mi400_2025": "/path"}."""
    found: Dict[str, Optional[str]] = {}
    overrides = {}
    if os.path.exists(SOURCES_PATH):
        try:
            overrides = json.load(open(SOURCES_PATH))
        except Exception:
            overrides = {}
    for key, cands in DEFAULT_CANDIDATES.items():
        path = overrides.get(key)
        if path and os.path.exists(os.path.expanduser(path)):
            found[key] = os.path.expanduser(path)
            continue
        found[key] = None
        for c in cands:
            p = os.path.expanduser(c)
            if os.path.exists(p):
                found[key] = p
                break
        if found[key] is None:
            # broader search in Downloads/Documents/Desktop by loose name
            pat = {"mi400_2025": r"400.*2025.*\.pdf$", "mi400_2009": r"400.*interview.*guide\.pdf$", "wsp_redbook": r"red.?book.*\.pdf$"}[key]
            for base in ("~/Downloads", "~/Documents", "~/Desktop"):
                b = os.path.expanduser(base)
                if not os.path.isdir(b):
                    continue
                for root, dirs, files in os.walk(b):
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", ".venv")]
                    if root.count(os.sep) - b.count(os.sep) > 3:
                        dirs[:] = []
                    for f in files:
                        if re.search(pat, f, re.I):
                            found[key] = os.path.join(root, f)
                            break
                    if found[key]:
                        break
                if found[key]:
                    break
    return found


def read_pages(path: str) -> List[str]:
    from pypdf import PdfReader
    r = PdfReader(path)
    return [(pg.extract_text() or "") for pg in r.pages]


# ------------------------------------------------------------------ cleaning
MI_NOISE = [r"^\s*Access the Financial Modeling Course\s*$", r"^\s*Access the Full IB Interview Guide\s*$", r"^\s*\d+ of \d+\s+https?://\S+\s*$",
            r"^\s*https?://\S+\s*$", r"^\s*\d{1,3}\s*$"]
WSP_NOISE = [r"^\s*Licensed to .*$", r"^\s*\d{1,3}\s*$", r"^\s*(ACCOUNTING|VALUATION|MERGERS & ACQUISITIONS|LEVERAGED BUYOUT|CAPITAL MARKETS|INDUSTRY SPECIFIC|BEHAVIORAL)\s*$", r"^\s*QUESTIONS\s*$"]


def _clean_lines(text: str, noise: List[str]) -> List[str]:
    out = []
    for ln in text.splitlines():
        s = ln.rstrip()
        if any(re.match(n, s, re.I) for n in noise):
            continue
        out.append(s)
    return out


def _norm(q: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", q.lower()).strip()


def _stable_id(source: str, section: str, question: str) -> str:
    return "src_%s_%s" % (source, hashlib.sha1(("%s|%s|%s" % (source, section, _norm(question)[:160])).encode()).hexdigest()[:10])


# ------------------------------------------------------------------ M&I parser
def parse_mi(pages: List[str], source: str) -> List[Dict]:
    """Numbered questions 'N. ...' restart per section. Section titles are known from the TOC; we detect
    them as short lines matching TOC-ish titles that precede '1.' questions."""
    toc_titles = set()
    for pg in pages[:3]:
        for ln in pg.splitlines():
            m = re.match(r"^\s*(.+?)\s*\.{4,}\s*\d+\s*$", ln)
            if m:
                toc_titles.add(re.sub(r"\s+", " ", m.group(1)).strip())
    records: List[Dict] = []
    section = "Front matter"
    cur: Optional[Dict] = None
    buf: List[str] = []
    expected_n = 1

    def flush():
        nonlocal cur, buf
        if cur:
            ans = _join(buf)
            cur["answer"] = ans
            records.append(cur)
        cur, buf = None, []

    for pno, pg in enumerate(pages, 1):
        lines = _clean_lines(pg, MI_NOISE)
        i = 0
        while i < len(lines):
            ln = lines[i].strip()
            title = re.sub(r"\s+", " ", ln)
            if title in toc_titles and len(title) < 90:
                flush()
                section = title
                expected_n = 1
                i += 1
                continue
            m = re.match(r"^(\d{1,3})\.\s+(\S.*)$", ln)
            if m and int(m.group(1)) in (expected_n, expected_n + 1) and len(m.group(2)) > 12 and not re.match(r"^\d", m.group(2)):
                # a question may wrap onto following lines until a line that ends with '?' or a blank line / sentence end
                qtext = [m.group(2)]
                j = i + 1
                while j < len(lines) and not qtext[-1].rstrip().endswith(("?", ".", ":")) and lines[j].strip() and len(" ".join(qtext)) < 500:
                    qtext.append(lines[j].strip())
                    j += 1
                flush()
                expected_n = int(m.group(1)) + 1
                q = _join(qtext)
                cur = {"id": _stable_id(source, section, q), "source": source, "section": section, "number": int(m.group(1)), "page": pno,
                       "question": q, "verification": "verified"}
                i = j
                continue
            if cur is not None:
                buf.append(ln)
            i += 1
    flush()
    return records


def _join(lines: List[str]) -> str:
    text = " ".join(l.strip() for l in lines if l.strip())
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s([,.;:?!)])", r"\1", text)
    text = text.replace("( ", "(")
    return text.strip()


# ------------------------------------------------------------------ Red Book parser
def parse_wsp(pages: List[str], source: str = "wsp_redbook") -> List[Dict]:
    """Questions are unnumbered lines ending with '?' (occasionally wrapping over two lines).
    Sections come from the TOC (page 6) and are detected as lines matching those titles."""
    toc_titles = set()
    for pg in pages[:8]:
        for ln in pg.splitlines():
            m = re.match(r"^\s*(.+?)\s*\.{3,}.*$", ln)
            if m:
                toc_titles.add(re.sub(r"\s+", " ", m.group(1)).strip())
    records: List[Dict] = []
    section = "Front matter"
    cur: Optional[Dict] = None
    buf: List[str] = []

    def flush():
        nonlocal cur, buf
        if cur:
            cur["answer"] = _join(buf)
            records.append(cur)
        cur, buf = None, []

    for pno, pg in enumerate(pages, 1):
        if pno < 8:
            continue
        lines = _clean_lines(pg, WSP_NOISE)
        i = 0
        while i < len(lines):
            ln = lines[i].strip()
            title = re.sub(r"\s+", " ", ln)
            if title in toc_titles and len(title) < 80:
                flush()
                section = title
                i += 1
                continue
            # question: a line (or two) ending in '?', starting with a capital, not a bullet/numbered list inside an answer
            is_q = False
            qlines = []
            if ln and ln[0].isupper() and not re.match(r"^(\d+\.|•|-|Q:)", ln):
                if ln.endswith("?"):
                    is_q, qlines = True, [ln]
                elif i + 1 < len(lines) and lines[i + 1].strip().endswith("?") and len(ln) > 25 and not ln.endswith((".", ":")):
                    nxt = lines[i + 1].strip()
                    if len(nxt) < 140:
                        is_q, qlines = True, [ln, nxt]
            if is_q:
                q = _join(qlines)
                # skip rhetorical questions inside answers: must be reasonably short and not start with 'For example'
                if 15 < len(q) < 260 and not re.match(r"^(for example|e\.g\.|but |so |and |or |then |thus )", q, re.I):
                    flush()
                    cur = {"id": _stable_id(source, section, q), "source": source, "section": section, "number": None, "page": pno,
                           "question": q, "verification": "verified"}
                    i += len(qlines)
                    continue
            if cur is not None:
                buf.append(ln)
            i += 1
    flush()
    return records


# ------------------------------------------------------------------ enrichment
def classify(rec: Dict) -> Dict:
    sec = (rec.get("section") or "").lower()
    q = rec["question"].lower()
    area, skill = "commercial", "commercial.positioning"
    for pat, a, s in SECTION_MAP:
        if re.search(pat, sec):
            area, skill = a, s
            break
    if area != "behavioral":
        # keywords match at a word start: 'eps' must not fire on 'steps', 'nol' on 'technology', 'range' on 'arrange'
        hits = [s for pat, s in SKILL_KEYWORDS if re.search(r"(?<![a-z0-9])(?:%s)" % pat, q) and not s.startswith("behavioral")]
        in_area = [s for s in hits if s.split(".")[0] == area]
        if in_area:
            skill = in_area[0]
        elif hits and re.search(GENERALIST_SECTIONS, sec):
            skill, area = hits[0], hits[0].split(".")[0]
        elif re.search(r"(?<![a-z])(dcf|discounted cash flow)\b", q) and area in ("ma", "lbo"):
            # a DCF question filed in another chapter (e.g. "DCF in a distressed scenario" under M&A) is a DCF question
            skill, area = "dcf.ufcf", "dcf"
    off_core = bool(re.search(OFF_CORE_SECTIONS, sec))
    level = 2
    for pat, lv in LEVEL_RULES:
        if re.search(pat, q):
            level = lv
    if re.search(r"calculation", sec):
        level = max(level, 4)
    if re.search(r"advanced|industry|group.specific|industry specific", sec):
        level = max(level, 4)
    ans = rec.get("answer") or ""
    has_numbers = bool(re.search(r"\$\s?\d|\d+\s?%|\d+x\b", rec["question"] + " " + ans))
    kind = "behavioral" if area == "behavioral" else ("calculation" if (has_numbers and re.search(r"calc|walk through|\$\d", q + " " + sec)) else "concept")
    formulas = re.findall(r"([A-Za-z][A-Za-z &/()]{2,40}\s*=\s*[^.;\n]{4,120})", ans)[:4]
    rec.update({"area": area, "skill": skill, "level": level, "kind": kind, "has_numbers": has_numbers, "formulas": formulas,
                "answer_words": len(ans.split()), "off_core": off_core})
    return rec


def dedupe(records: List[Dict]) -> List[Dict]:
    """Near-duplicate questions across sources are linked (not dropped): the first keeps `variants`."""
    def toks(s):
        return set(w for w in _norm(s).split() if len(w) > 2 and w not in {"the", "and", "for", "what", "how", "you", "does", "would", "with", "are", "this", "that", "company", "companys", "why"})
    kept: List[Dict] = []
    for r in records:
        t = toks(r["question"])
        match = None
        for k in kept:
            kt = k["_toks"]
            if not t or not kt:
                continue
            j = len(t & kt) / len(t | kt)
            if j >= 0.6:
                match = k
                break
        if match:
            match.setdefault("variants", []).append({"id": r["id"], "source": r["source"], "page": r["page"], "question": r["question"], "answer": r.get("answer", "")})
        else:
            r["_toks"] = t
            kept.append(r)
    for k in kept:
        k.pop("_toks", None)
    return kept


def run(write: bool = True) -> Dict:
    paths = discover_sources()
    all_records: List[Dict] = []
    report = {"sources": {}, "counts": {}}
    for key in ("mi400_2025", "wsp_redbook", "mi400_2009"):
        p = paths.get(key)
        if not p:
            report["sources"][key] = {"path": None, "status": "missing"}
            continue
        pages = read_pages(p)
        recs = parse_wsp(pages, key) if key == "wsp_redbook" else parse_mi(pages, key)
        recs = [r for r in recs if r.get("answer") and len(r["answer"].split()) >= 8]
        for r in recs:
            classify(r)
        report["sources"][key] = {"path": p, "status": "ok", "pages": len(pages), "records": len(recs), "md5": hashlib.md5(open(p, "rb").read()).hexdigest(), **SOURCE_META[key]}
        all_records.extend(recs)
    merged = dedupe(all_records)
    report["counts"] = {"raw": len(all_records), "unique": len(merged), "with_variants": sum(1 for r in merged if r.get("variants")),
                        "by_area": {}, "by_level": {}, "by_kind": {}, "skills_mapped": len({r["skill"] for r in merged})}
    for r in merged:
        report["counts"]["by_area"][r["area"]] = report["counts"]["by_area"].get(r["area"], 0) + 1
        report["counts"]["by_level"][str(r["level"])] = report["counts"]["by_level"].get(str(r["level"]), 0) + 1
        report["counts"]["by_kind"][r["kind"]] = report["counts"]["by_kind"].get(r["kind"], 0) + 1
    if write:
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
        with open(OUT_PATH, "w") as f:
            json.dump({"report": report, "records": merged}, f, indent=0)
    return report


def load_source_questions() -> List[Dict]:
    if not os.path.exists(OUT_PATH):
        return []
    try:
        return json.load(open(OUT_PATH)).get("records", [])
    except Exception:
        return []


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
