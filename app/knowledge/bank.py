"""Question schema, loader and validator for the technical/behavioral question bank.

Questions are authored in Python modules (one per topic) using the helpers below so the
content stays compact and type-checked. `load_bank()` returns a dict id -> Question.
"""
import importlib
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from .skills import SKILLS

TOPIC_MODULES = [
    "accounting", "valuation", "dcf", "ma", "lbo", "fig", "healthcare", "energy", "commercial",
    "behavioral",
]


@dataclass
class Component:
    id: str
    text: str                     # what a complete answer states
    kw: List[str]                 # alternatives; a hit on ANY marks the component present (regex allowed)
    weight: float = 1.0
    required: bool = False        # missing a required component caps the score at "partial"


@dataclass
class Misconception:
    id: str
    kw: List[str]                 # phrases that reveal the misconception
    explain: str                  # the correction, used in debriefs
    severity: str = "major"       # major | minor


@dataclass
class FollowUp:
    when: str                     # 'correct' | 'missing:<component>' | 'misconception:<id>' | 'vague' | 'always' | 'wrong'
    text: str
    next_id: Optional[str] = None # a question id to chain to (optional)


@dataclass
class Question:
    id: str
    topic: str                    # area key
    subtopic: str
    skill: str                    # skill id
    difficulty: int               # 1 (foundational) .. 6 (expert / multi-concept)
    text: str
    components: List[Component] = field(default_factory=list)
    misconceptions: List[Misconception] = field(default_factory=list)
    followups: List[FollowUp] = field(default_factory=list)
    solution: str = ""
    prereqs: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)
    variants: List[str] = field(default_factory=list)
    kind: str = "technical"       # technical | behavioral | numeric | resume | deal
    answer_type: str = "explain"  # explain | number | list | story
    numeric: Optional[Dict] = None  # {'generator': name} for programmatic questions
    source: str = "original"      # original (written for this project) | standard (textbook convention)
    assumptions: str = ""         # conventions assumed (e.g. positive taxable income, 25% tax)
    tags: List[str] = field(default_factory=list)
    sector: Optional[str] = None  # for bank/group targeting
    behavioral_category: Optional[str] = None
    level: int = 2                # cognitive layer 1 definition .. 5 advanced exceptions (derived if not set)

    def to_dict(self) -> Dict:
        return asdict(self)


def C(id, text, kw, weight=1.0, required=False):
    return Component(id, text, kw, weight, required)


def M(id, kw, explain, severity="major"):
    return Misconception(id, kw, explain, severity)


def F(when, text, next_id=None):
    return FollowUp(when, text, next_id)


def Q(id, topic, subtopic, skill, difficulty, text, components=None, misconceptions=None, followups=None,
      solution="", prereqs=None, concepts=None, variants=None, kind="technical", answer_type="explain",
      numeric=None, source="original", assumptions="", tags=None, sector=None, behavioral_category=None):
    return Question(id=id, topic=topic, subtopic=subtopic, skill=skill, difficulty=difficulty, text=text,
                    components=components or [], misconceptions=misconceptions or [], followups=followups or [],
                    solution=solution, prereqs=prereqs or [], concepts=concepts or [], variants=variants or [],
                    kind=kind, answer_type=answer_type, numeric=numeric, source=source, assumptions=assumptions,
                    tags=tags or [], sector=sector, behavioral_category=behavioral_category)


_BANK: Optional[Dict[str, Question]] = None


def load_bank(force: bool = False) -> Dict[str, Question]:
    global _BANK
    if _BANK is not None and not force:
        return _BANK
    bank: Dict[str, Question] = {}
    for mod in TOPIC_MODULES:
        m = importlib.import_module("app.knowledge.questions." + mod)
        for q in m.QUESTIONS:
            if q.id in bank:
                raise ValueError("duplicate question id %s" % q.id)
            _add_default_followups(q)
            q.level = infer_level(q)
            bank[q.id] = q
    _BANK = bank
    return bank


LEVEL_RULES = [
    (r"^(what is|what are|define|what does .* mean|what('s| is) the difference|name |list )", 1),
    (r"^(how do you (calculate|compute|get|derive|determine)|walk me through|what('s| is) the formula|how is .* calculated|how are .* linked)", 2),
    (r"^(why|explain why|how does .* work|what economically)", 3),
    (r"(suppose|assume|if |what happens|how would .* change|now |same |instead|\$\d|\d+%|\d+x\b|walk through a)", 4),
    (r"(exception|when would you not|edge case|what('s| is) wrong with|limitation|drawback|pitfall|in theory|misleading|abuse|break down|defend)", 5),
]


def infer_level(q: Question) -> int:
    """Cognitive layer: 1 definition, 2 mechanics, 3 understanding, 4 application, 5 advanced exceptions."""
    if q.kind == "behavioral":
        return 3
    t = q.text.lower()
    level = 2
    for pat, lv in LEVEL_RULES:
        if re.search(pat, t):
            level = lv
    if q.difficulty >= 5:
        level = max(level, 4)
    if q.difficulty >= 6:
        level = 5
    return level


def _add_default_followups(q: Question) -> None:
    """Technical questions without an authored follow-up for a component get a hint-style probe so the
    interviewer can always target the specific omission ("What about the tax effect?") instead of a
    generic 'why?'. Authored follow-ups always take precedence (they are matched first)."""
    if q.kind != "technical":
        return
    have = {f.when for f in q.followups}
    for c in q.components:
        trig = "missing:" + c.id
        if trig in have:
            continue
        head = re.split(r"[:;(]", c.text)[0].strip().rstrip(".")
        if not head:
            continue
        named = {"IS": "the income statement", "BS": "the balance sheet", "CFS": "the cash flow statement", "CFO": "operating cash flow",
                 "CFI": "investing cash flow", "CFF": "financing cash flow", "EV": "enterprise value", "TV": "terminal value"}
        if head.upper() in named:
            text = "You left out %s. Walk me through that side." % named[head.upper()]
        elif len(head.split()) <= 3 and ":" in c.text:
            text = "You skipped the %s part. Walk me through it." % (head[0].lower() + head[1:])
        else:
            text = "You left something out: %s. Walk me through that." % (head[0].lower() + head[1:] if not head[:2].isupper() else head)
        q.followups.append(FollowUp(trig, text))
    if "wrong" not in have and "always" not in have and q.misconceptions:
        q.followups.append(FollowUp("wrong", "That's not right. Take it from the top, one step at a time."))


def validate_bank(bank: Dict[str, Question]) -> List[str]:
    errors = []
    for q in bank.values():
        if q.skill not in SKILLS:
            errors.append("%s: unknown skill %s" % (q.id, q.skill))
        if not (1 <= q.difficulty <= 6):
            errors.append("%s: difficulty out of range" % q.id)
        for p in q.prereqs:
            if p not in bank:
                errors.append("%s: prereq %s missing" % (q.id, p))
        for f in q.followups:
            if f.next_id and f.next_id not in bank:
                errors.append("%s: followup next_id %s missing" % (q.id, f.next_id))
            if not re.match(r"^(correct|vague|always|wrong|missing:[\w-]+|misconception:[\w-]+)$", f.when):
                errors.append("%s: bad followup trigger %s" % (q.id, f.when))
            if f.when.startswith("missing:"):
                cid = f.when.split(":", 1)[1]
                if cid not in [c.id for c in q.components]:
                    errors.append("%s: followup references unknown component %s" % (q.id, cid))
            if f.when.startswith("misconception:"):
                mid = f.when.split(":", 1)[1]
                if mid not in [m.id for m in q.misconceptions]:
                    errors.append("%s: followup references unknown misconception %s" % (q.id, mid))
        if q.kind == "technical" and q.answer_type == "explain" and not q.components:
            errors.append("%s: technical question without components" % q.id)
        if q.kind == "technical" and not q.solution:
            errors.append("%s: no solution" % q.id)
        for c in q.components:
            for k in c.kw:
                try:
                    re.compile(k)
                except re.error:
                    errors.append("%s: bad regex %s" % (q.id, k))
    return errors


def by_skill(bank: Dict[str, Question]) -> Dict[str, List[Question]]:
    out: Dict[str, List[Question]] = {}
    for q in bank.values():
        out.setdefault(q.skill, []).append(q)
    return out
