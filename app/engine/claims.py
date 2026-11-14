"""Claim registry: extracts simple factual/quantitative claims from candidate answers so the
interviewer can notice contradictions later ("earlier you said WACC was 8.9%, now 10%")."""
import re
from typing import Dict, List, Optional

# subject patterns → canonical keys. Values are extracted as numbers near the subject.
SUBJECTS = {
    "wacc": r"\bwacc\b|discount rate|cost of capital",
    "terminal_growth": r"terminal growth|perpetuity growth|long.term growth|\bg\b of",
    "exit_multiple": r"exit multiple",
    "upside": r"upside|price target|target price",
    "beta": r"\bbeta\b",
    "tax_rate": r"tax rate",
    "model_count": r"(\d+)\+? (dcf|discounted cash flow|models?)",
    "hours": r"hours? (a|per) week",
    "gpa": r"\bgpa\b",
    "henry_hub": r"henry hub|gas price",
    "discount_rate_royalty": r"pv.?10|royalty discount",
}

POLARITY_PATTERNS = [
    # (key, positive regex, negative regex) → booleans the candidate asserted
    ("rates_biggest_risk", r"(interest )?rates? (are|is|was) (the )?(biggest|largest|main|key) risk", r"rates? (are|is|were) (immaterial|not (a|the) (big|major|main) (risk|factor)|irrelevant|don'?t matter)"),
    ("built_model_solo", r"\bi (built|made|created) (the|this|that|every|all)", r"\b(we|the team|my teammate|a teammate) (built|made|created)"),
    ("healthcare_focus", r"(most|really|primarily) interested in healthcare|healthcare is (my|the) (focus|priority)", r"(i'?m|i am) (a )?generalist|not (that )?interested in healthcare|open to any group"),
    ("energy_focus", r"(most|really|primarily) interested in energy|energy is (my|the) (focus|priority)", r"energy (was|is) just|not (that )?interested in energy"),
]

NUM = r"(-?\d+(?:\.\d+)?)\s*(%|percent|x|bps|basis points|million|billion|k)?"


def extract(text: str, turn_idx: int, question_id: Optional[str]) -> List[Dict]:
    t = text.lower()
    claims: List[Dict] = []
    for key, pat in SUBJECTS.items():
        for m in re.finditer(pat, t):
            window = t[m.start(): m.end() + 60]
            nm = re.search(NUM, window)
            if nm:
                val = float(nm.group(1))
                unit = (nm.group(2) or "").strip().lower()
                unit = {"percent": "%", "basis points": "bps"}.get(unit, unit)
                claims.append({"key": key, "value": val, "unit": unit, "text": text[max(0, m.start() - 20): m.end() + 60].strip(), "turn": turn_idx, "question_id": question_id})
                break
    for key, pos, neg in POLARITY_PATTERNS:
        if re.search(pos, t):
            claims.append({"key": key, "value": True, "unit": "", "text": re.search(pos, t).group(0), "turn": turn_idx, "question_id": question_id})
        if re.search(neg, t):
            claims.append({"key": key, "value": False, "unit": "", "text": re.search(neg, t).group(0), "turn": turn_idx, "question_id": question_id})
    return claims


def find_contradictions(registry: List[Dict], new_claims: List[Dict], already_flagged: Optional[List[str]] = None) -> List[Dict]:
    """Compare each new claim with the most recent earlier claim on the same key. A key is flagged at most once
    per session (already_flagged holds keys already raised with the candidate)."""
    out = []
    flagged = set(already_flagged or [])
    for nc in new_claims:
        if nc["key"] in flagged:
            continue
        prior = [o for o in registry if o["key"] == nc["key"] and o["turn"] != nc["turn"]]
        if not prior:
            continue
        for old in prior[-1:]:
            if isinstance(nc["value"], bool):
                if old["value"] != nc["value"]:
                    out.append({"key": nc["key"], "earlier": old, "now": nc, "kind": "polarity"})
                    flagged.add(nc["key"])
            else:
                if old.get("unit") == nc.get("unit") and old["value"] and abs(old["value"] - nc["value"]) / max(abs(old["value"]), 1e-9) > 0.10:
                    out.append({"key": nc["key"], "earlier": old, "now": nc, "kind": "numeric"})
                    flagged.add(nc["key"])
    return out


def phrase(contradiction: Dict) -> str:
    key = contradiction["key"].replace("_", " ")
    e, n = contradiction["earlier"], contradiction["now"]
    if contradiction["kind"] == "numeric":
        return "Earlier you said the %s was %s%s; now you're saying %s%s. Which is it?" % (key, _fmt(e["value"]), e["unit"], _fmt(n["value"]), n["unit"])
    return "Earlier you said '%s'. Now you're saying '%s'. Reconcile those for me." % (e["text"], n["text"])


def _fmt(v: float) -> str:
    return ("%d" % v) if float(v).is_integer() else ("%.2f" % v).rstrip("0").rstrip(".")
