"""Source-grounded questions (from the ingested guides) as first-class interview questions.

Records come from data/knowledge/source_questions.json (see ingest.py). Each becomes a question the
selector can pick (`source: "source"`), with:
  - a deterministic fallback rubric derived from the guide's answer (key finance terms + numbers), and
  - the guide's answer as the reference solution for the model-backed evaluator (gated by the
    `send_guide_excerpts` setting, which is disclosed in Settings).
Citations are always the record's source/section/page; verification status is carried through.
"""
import re
from typing import Dict, List, Optional

from app.knowledge import ingest
from app.knowledge.bank import Question, Component, FollowUp

_CACHE: Optional[Dict[str, Dict]] = None

# curated vocabulary for deterministic rubrics: regex -> label
VOCAB: List[tuple] = [
    (r"net income", "net income"), (r"pre.?tax income|ebt\b", "pre-tax income"), (r"ebitda", "EBITDA"), (r"\bebit\b|operating income", "EBIT / operating income"),
    (r"revenue|sales", "revenue"), (r"cogs|cost of goods", "COGS"), (r"gross (profit|margin)", "gross profit"), (r"depreciation", "depreciation"), (r"amortiz", "amortization"),
    (r"non.?cash", "non-cash items"), (r"working capital", "working capital"), (r"receivable", "receivables"), (r"inventory", "inventory"), (r"payable", "payables"),
    (r"deferred revenue|unearned", "deferred revenue"), (r"deferred tax", "deferred taxes"), (r"\bnols?\b|net operating loss", "NOLs"), (r"tax shield|tax (saving|benefit)", "tax shield"),
    (r"cash flow (from|statement)|\bcfs\b|\bcfo\b", "cash flow statement"), (r"balance sheet", "balance sheet"), (r"income statement", "income statement"), (r"retained earnings", "retained earnings"),
    (r"shareholders'? equity|common (shareholders'? )?equity|\bcse\b", "shareholders' equity"), (r"pp&e|property, plant", "PP&E"), (r"capex|capital expenditure", "capex"), (r"goodwill", "goodwill"),
    (r"intangible", "intangibles"), (r"impair", "impairment"), (r"write.?(down|off|up)", "write-down/up"), (r"stock.based|\bsbc\b", "stock-based compensation"), (r"lease", "leases"),
    (r"enterprise value|\bev\b|\btev\b", "enterprise value"), (r"equity value|market cap", "equity value"), (r"net debt", "net debt"), (r"preferred", "preferred stock"), (r"non.?controlling|minority interest", "non-controlling interest"),
    (r"diluted|treasury stock|\btsm\b", "diluted shares / TSM"), (r"convertible", "convertibles"), (r"(stock|employee|call|put) options?|option pool|options and warrants|warrants", "options"), (r"multiple", "multiples"), (r"p\s*/\s*e\b|price.to.earnings", "P/E"),
    (r"t?ev\s*/\s*ebitda", "EV/EBITDA"), (r"comparable|comps|peer", "comparable companies"), (r"precedent", "precedent transactions"), (r"control premium|premium", "premium"), (r"synerg", "synergies"),
    (r"unlevered free cash flow|\bufcf\b|free cash flow|\bfcf\b", "free cash flow"), (r"\bwacc\b|cost of capital", "WACC"), (r"cost of equity", "cost of equity"), (r"cost of debt", "cost of debt"), (r"\bbeta\b", "beta"),
    (r"risk.?free", "risk-free rate"), (r"risk premium|\berp\b", "equity risk premium"), (r"\bcapm\b", "CAPM"), (r"terminal value", "terminal value"), (r"perpetuity|gordon", "perpetuity growth"), (r"exit multiple", "exit multiple"),
    (r"discount(ed|ing)? (rate|back|factor)|present value|\bpv\b|\bnpv\b", "discounting / present value"), (r"mid.?year", "mid-year convention"), (r"sensitiv", "sensitivity"), (r"capital structure|leverage", "capital structure / leverage"),
    (r"accreti", "accretion"), (r"diluti", "dilution"), (r"\beps\b|earnings per share", "EPS"), (r"pro forma", "pro forma"), (r"sources and uses|sources & uses", "sources and uses"), (r"purchase price|purchase accounting|allocation", "purchase price allocation"),
    (r"cash (deal|offer|consideration)|all.cash", "cash consideration"), (r"stock (deal|offer|consideration)|all.stock|exchange ratio", "stock consideration"), (r"transaction fee|advisory fee|financing fee", "fees"), (r"\birr\b|internal rate", "IRR"), (r"moic|multiple of (money|invested)|cash.on.cash", "MOIC"),
    (r"debt paydown|pay down|repay|deleverag", "debt paydown"), (r"cash sweep", "cash sweep"), (r"tranche|term loan|revolver|high.yield|mezzanine|subordinated|senior", "debt tranches"), (r"covenant", "covenants"), (r"sponsor|private equity|\bpe\b", "sponsor"),
    (r"exit", "exit"), (r"dividend recap", "dividend recap"), (r"management|rollover", "management rollover"), (r"interest expense|interest rate", "interest"), (r"tax rate|taxes?\b", "taxes"), (r"\bgaap\b|ifrs", "GAAP/IFRS"),
    (r"book value|tangible book|p\s*/\s*tbv|p\s*/\s*b\b", "book value multiples"), (r"\broe\b|return on equity|rotce", "ROE"), (r"net interest (margin|income)|\bnim\b", "net interest margin"), (r"provision|loan loss|charge.?off", "provisions"), (r"regulatory capital|tier 1|cet1|basel", "regulatory capital"),
    (r"rnpv|risk.adjusted|probability", "probability-weighting / rNPV"), (r"patent|exclusivity|generic", "patent / exclusivity"), (r"reimburse|payer|medicare", "reimbursement"), (r"reserve|pdp|pud|proved", "reserves"), (r"decline", "decline curves"), (r"royalt|mineral|working interest|\bnri\b", "royalty / working interest"),
    (r"\bnav\b|pv.?10", "NAV / PV-10"), (r"commodity|price deck|henry hub|wti|brent", "commodity prices"), (r"hedg", "hedging"), (r"liquidation|chapter 11|bankrupt|distress|restructur", "restructuring"), (r"recovery|waterfall|seniority|priority", "priority / recovery"), (r"covenant|default|maturity|refinanc", "credit terms"),
    (r"growth", "growth"), (r"margin", "margins"), (r"risk", "risk"), (r"\broic\b|return on (invested )?capital", "ROIC"), (r"market share|competit", "competition"), (r"recurring|subscription|\barr\b|churn", "recurring revenue"),
    (r"\bipo\b|offering|underwrit", "equity offering"), (r"bonds?\b|notes\b|coupon|yield", "bonds / yields"), (r"spread", "spreads"), (r"rating", "credit rating"), (r"\bltv\b|loan.to.value|cap rate|noi\b", "real estate metrics"),
]

NUM_RE = re.compile(r"(?<![\w.])(-?\$?\d[\d,]*(?:\.\d+)?)(\s*(?:%|x|k|m|mm|million|billion|bn))?", re.I)


def _records() -> Dict[str, Dict]:
    global _CACHE
    if _CACHE is None:
        _CACHE = {r["id"]: r for r in ingest.load_source_questions()}
    return _CACHE


def reload() -> int:
    global _CACHE
    _CACHE = None
    return len(_records())


def all_records(include_off_core: bool = False, include_behavioral: bool = False) -> List[Dict]:
    out = []
    for r in _records().values():
        if r.get("off_core") and not include_off_core:
            continue
        if r["area"] == "behavioral" and not include_behavioral:
            continue
        out.append(r)
    return out


def get(rid: str) -> Optional[Dict]:
    return _records().get(rid)


# Terms that show up in almost any finance answer: they still count, but they say little about understanding.
GENERIC_LABELS = {"taxes", "growth", "risk", "margins", "revenue", "premium", "management rollover", "exit", "multiples", "interest"}


def bounded(pat: str) -> str:
    """Anchor every alternative of a vocabulary pattern at a word start, so 'ebt' cannot match 'debt',
    'rating' cannot match 'operating', 'lease' cannot match 'please', 'option' cannot match 'adoption'."""
    return r"(?<![a-z0-9-])(?:%s)" % pat


_ENUM_AFTER = re.compile(r"\s*[\).:]\s")


def _is_enumerator(text: str, m: "re.Match") -> bool:
    """'1) maintenance', '2. incurrence', '(3)', 'Step 1:' are list markers, not figures to state."""
    tok = m.group(1)
    if m.group(2) or not re.fullmatch(r"\d{1,2}", tok):
        return False
    before = text[max(0, m.start() - 6):m.start()].lower()
    if before.endswith("(") or re.search(r"(step|stage|phase|no\.|#)\s*$", before):
        return True
    return bool(_ENUM_AFTER.match(text, m.end())) and (m.start() == 0 or text[m.start() - 1] in " \n\t(")


def derive_components(answer: str, question: str = "", calculation: bool = False) -> List[Component]:
    """Key finance terms that appear in the guide answer become rubric components. Terms that also appear
    in the question are down-weighted (restating the question is not understanding), as are generic terms.
    Terms are ranked by how central they are to the guide answer (frequency, then first position).
    Figures become components only for calculation questions; list markers never do."""
    low = answer.lower()
    qlow = question.lower()
    ranked = []
    seen = set()
    for pat, label in VOCAB:
        if label in seen:
            continue
        bp = bounded(pat)
        hits = list(re.finditer(bp, low))
        if not hits:
            continue
        seen.add(label)
        w = 0.5 if re.search(bp, qlow) else 1.0
        if label in GENERIC_LABELS:
            w = min(w, 0.4)
        ranked.append((-(len(hits) * w), hits[0].start(), bp, label, w))
    ranked.sort(key=lambda r: (r[0], r[1]))
    terms = [Component("t_%d" % i, "Mentions %s" % label, [bp], weight=w) for i, (_, _, bp, label, w) in enumerate(ranked)]
    numeric: List[Component] = []
    if calculation:
        nums = []
        qnums = set(m.group(1).replace("$", "").replace(",", "") for m in NUM_RE.finditer(question))
        for m in NUM_RE.finditer(answer):
            tok = m.group(1).replace("$", "").replace(",", "")
            try:
                v = float(tok)
            except ValueError:
                continue
            if v in (0.0,) or abs(v) > 1e9 or _is_enumerator(answer, m):
                continue
            unit = (m.group(2) or "").strip().lower()
            key = (tok, unit)
            if key in nums or len(nums) >= 6 or tok in qnums:
                continue  # numbers given in the question are inputs, not evidence of understanding
            nums.append(key)
        # results come last in a worked answer; keep the last few
        for tok, unit in nums[-3:]:
            pat = r"(?<![\d.])%s(?![\d])" % re.escape(tok)
            numeric.append(Component("n_%s" % tok.replace(".", "_"), "States the figure %s%s" % (tok, unit and " " + unit), [pat], weight=1.2, required=False))
    # keep the rubric focused: at most 10 components (numbers first, then the most central terms)
    return numeric + terms[: max(4, 10 - len(numeric))]


_PAGE_HEADER = re.compile(r"\s+[A-Z][A-Z&,\-' ]{5,}[A-Z]\s*$")


def strip_page_header(text: str) -> str:
    """PDF extraction leaves the page's running header ('CAPITAL MARKETS', 'MERGERS & ACQUISTIONS') glued to the end of some answers."""
    return _PAGE_HEADER.sub("", text or "")


def as_question(rec: Dict) -> Question:
    comps = derive_components(strip_page_header(rec.get("answer", "")), rec["question"], calculation=rec.get("kind") == "calculation")
    fus = []
    for v in rec.get("variants", [])[:2]:
        fus.append(FollowUp("correct", "Put it another way: %s" % v["question"]))
    q = Question(id=rec["id"], topic=rec["area"], subtopic=rec.get("section", ""), skill=rec["skill"], difficulty=int(rec.get("level", 2)),
                 text=rec["question"], components=comps, misconceptions=[], followups=fus, solution=strip_page_header(rec.get("answer", "")),
                 prereqs=[], concepts=[], variants=[v["question"] for v in rec.get("variants", [])], kind="technical",
                 answer_type="number" if rec.get("kind") == "calculation" and rec.get("has_numbers") else "explain",
                 source=rec["source"], assumptions="", tags=["source", rec["source"], "level%d" % rec.get("level", 2)] + (["calculation"] if rec.get("kind") == "calculation" else []))
    return q


def citation(rec: Dict) -> Dict:
    meta = ingest.SOURCE_META.get(rec["source"], {})
    return {"source": rec["source"], "short": meta.get("short", rec["source"]), "title": meta.get("title"), "section": rec.get("section"), "page": rec.get("page"),
            "verification": rec.get("verification", "unverified")}


def wrap(rec: Dict) -> Dict:
    return {"id": rec["id"], "source": "source", "kind": "technical", "skill": rec["skill"], "topic": rec["area"], "difficulty": int(rec.get("level", 2)),
            "level": int(rec.get("level", 2)), "text": rec["question"], "answer_type": "number" if rec.get("kind") == "calculation" and rec.get("has_numbers") else "explain",
            "tags": ["source", rec["source"]], "citation": citation(rec), "section": rec.get("section")}


def by_skill(include_off_core: bool = False) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for r in all_records(include_off_core):
        out.setdefault(r["skill"], []).append(r)
    return out


def next_level_question(skill: str, level: int, exclude: set) -> Optional[Dict]:
    cands = [r for r in by_skill().get(skill, []) if r["id"] not in exclude and r.get("level", 2) >= level + 1]
    cands.sort(key=lambda r: (r.get("level", 2), r.get("answer_words", 0)))
    return cands[0] if cands else None


def report() -> Dict:
    import json, os
    if not os.path.exists(ingest.OUT_PATH):
        return {"status": "not_ingested"}
    try:
        return json.load(open(ingest.OUT_PATH)).get("report", {})
    except Exception:
        return {"status": "unreadable"}
