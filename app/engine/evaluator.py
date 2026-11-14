"""Deterministic technical evaluator + optional LLM refinement.

score ∈ [0,1]; verdict ∈ {correct, partial, incorrect, off_topic, non_answer}.
Deterministic layer: component coverage (regex alternatives on normalized text), misconception
detection, numeric extraction/checking, relevance heuristics, keyword-list detection. The LLM (if
available) can flip a component to present/absent with quoted evidence, but can never override a
numeric check. On authored rubrics it can move the score by at most ±0.25; on rubrics derived
automatically from the guides (ids "src_*", term lists with no numbers) the term list is a weak signal,
so the model's judgment carries more weight (70%, at most ±0.5; 90%, at most ±0.8 when the list is thin).
"""
import re
from typing import Dict, List, Optional, Tuple

from app.knowledge.bank import Question
from app.knowledge import numeric as numeric_mod
from app.llm import provider, prompts, schemas

NON_ANSWER = [r"^\s*(i )?(don'?t|do not) know\.?\s*$", r"^\s*(pass|skip|no idea|not sure)\.?\s*$", r"^\s*$", r"^\s*(um+|uh+)[\s.,]*$"]
GIVE_UP = [r"\bi (don'?t|do not) (really )?know\b", r"\bno idea\b", r"\bi('d| would) have to (look|check)\b", r"\bi forget\b", r"\bi'?m blanking\b"]

NORMALIZE = [
    (r"\bwack\b|\bwhack\b", "wacc"), (r"\bebit ?da\b", "ebitda"), (r"\bnet income\b", "net income"), (r"\bp ?p ?& ?e\b|\bpp and e\b|\bproperty,? plant,? and equipment\b", "pp&e"),
    (r"\bd ?& ?a\b|\bd and a\b", "d&a"), (r"\bretained earnings?\b", "retained earnings"), (r"\bcash ?flow statement\b|\bstatement of cash ?flows\b", "cash flow statement"),
    (r"\bdollars?\b", ""), (r"\$", ""), (r"(\d),(\d{3})", r"\1\2"), (r"\bpercent\b", "%"), (r"\bper cent\b", "%"), (r"\bnegative (\d)", r"-\1"),
    (r"\bminus (\d)", r"-\1"), (r"(?<=[a-z&)]) ?[-−–] ?(\d)", r" down \1"), (r"(?<=[a-z&)]) ?\+ ?(\d)", r" up \1"), (r"\bgoes down by\b|\bdecreases by\b|\bfalls by\b|\bdrops by\b", "down"), (r"\bgoes up by\b|\bincreases by\b|\brises by\b", "up"),
    (r"\btwo and a half\b", "2.5"), (r"\bseven and a half\b", "7.5"), (r"\btwelve and a half\b", "12.5"), (r"\bone hundred\b", "100"), (r"\bthirty\b", "30"), (r"\btwenty\b", "20"),
    (r"\b(\d+) ?x\b", r"\1x"), (r"\b(\d+) times\b", r"\1x"),
]

WORD_NUMBERS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "twenty-five": 25, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
                "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100}


def normalize(text: str) -> str:
    t = " " + text.lower() + " "
    for pat, rep in NORMALIZE:
        t = re.sub(pat, rep, t)
    t = re.sub(r"\s+", " ", t)
    return t


def extract_numbers(text: str) -> List[float]:
    t = normalize(text)
    nums = []
    for m in re.finditer(r"(-?\d+(?:\.\d+)?)\s*(%|x|million|billion|m\b|bn\b|k\b)?", t):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        unit = m.group(2) or ""
        if unit in ("billion", "bn"):
            v *= 1000  # express in millions
        if unit == "k":
            v /= 1000
        nums.append(v)
    for w, v in WORD_NUMBERS.items():
        if re.search(r"\b%s\b" % w, t):
            nums.append(float(v))
    return nums


def _hit(patterns: List[str], text: str) -> Optional[str]:
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            return m.group(0)
    return None


FUNCTION_WORDS = {"a", "an", "the", "is", "are", "was", "be", "it", "its", "it's", "to", "of", "in", "on", "by", "for", "so", "and", "or", "but",
                  "because", "since", "which", "that", "this", "then", "if", "when", "you", "we", "they", "would", "will", "can", "goes", "go", "up",
                  "down", "equals", "minus", "plus", "times", "divided", "over", "into", "from", "with", "as", "than", "more", "less", "has", "have", "means"}


def is_keyword_list(text: str) -> bool:
    """A string of finance terms with no connecting words ('net income depreciation capex working capital…') is not an explanation."""
    words = re.findall(r"[a-z']+", text.lower())
    if len(words) < 8:
        return False
    return sum(1 for w in words if w in FUNCTION_WORDS) / len(words) < 0.08


def is_derived_rubric(q: Question) -> bool:
    return q.id.startswith("src_") and not any(c.id.startswith("n_") for c in q.components)


def is_non_answer(text: str) -> bool:
    return any(re.match(p, text.strip(), flags=re.I) for p in NON_ANSWER) or len(re.findall(r"[a-z]+", text.lower())) < 3


def gave_up(text: str) -> bool:
    return any(re.search(p, text, flags=re.I) for p in GIVE_UP)


def relevance(q: Question, text: str) -> float:
    """Share of the question's concept vocabulary echoed in the answer; a crude off-topic detector."""
    t = normalize(text)
    terms = set()
    for c in q.components:
        for k in c.kw:
            for w in re.findall(r"[a-z&]{4,}", k.lower()):
                if w not in {"down", "decreas", "increas", "same", "change", "that", "this", "with", "from", "into", "which", "what", "because"}:
                    terms.add(w.rstrip("\\"))
    for w in re.findall(r"[a-z&]{5,}", q.text.lower()):
        if w not in {"would", "which", "about", "through", "there", "their", "explain", "describe", "company", "happens", "assume"}:
            terms.add(w)
    if not terms:
        return 1.0
    hits = sum(1 for w in terms if w[:5] in t)
    return hits / max(len(terms), 1)


def evaluate_technical(q: Question, answer: str, llm_pref: str = "auto", use_llm: bool = True) -> Dict:
    text = answer or ""
    norm = normalize(text)
    result: Dict = {"question_id": q.id, "skill": q.skill, "difficulty": q.difficulty, "kind": q.kind, "answer": text,
                    "components": [], "misconceptions": [], "numbers": extract_numbers(text), "llm": None, "provider": "offline"}
    if is_non_answer(text):
        result.update({"score": 0.0, "verdict": "non_answer", "answered_question": False, "key_error": "No substantive answer was given.",
                       "stronger_answer": q.solution, "summary": "No answer."})
        return result
    # components
    total_w = sum(c.weight for c in q.components) or 1.0
    got_w = 0.0
    missing_required = []
    for c in q.components:
        ev = _hit(c.kw, norm) or _hit(c.kw, text)
        present = ev is not None
        result["components"].append({"id": c.id, "text": c.text, "present": present, "evidence": ev, "required": c.required, "weight": c.weight, "source": "deterministic"})
        if present:
            got_w += c.weight
        elif c.required:
            missing_required.append(c.id)
    coverage = got_w / total_w
    # misconceptions
    for m in q.misconceptions:
        ev = _hit(m.kw, norm) or _hit(m.kw, text)
        if ev:
            result["misconceptions"].append({"id": m.id, "evidence": ev, "explain": m.explain, "severity": m.severity})
    major_mis = [m for m in result["misconceptions"] if m["severity"] == "major"]
    rel = relevance(q, text)
    gave = gave_up(text)
    kwlist = is_keyword_list(text)
    # score
    score = coverage
    if kwlist:
        score = min(score, 0.3)
    if major_mis:
        score = min(score, 0.45) * (0.7 ** (len(major_mis) - 1))
    if missing_required:
        score = min(score, 0.65)
    if gave:
        score = min(score, 0.5)
    if coverage == 0 and rel < 0.12 and not major_mis:
        verdict = "off_topic"
        score = min(score, 0.15)
    elif score >= 0.75 and not major_mis and not missing_required:
        verdict = "correct"
    elif score >= 0.35 or (coverage >= 0.4 and not major_mis and not kwlist):
        verdict = "partial"
    else:
        verdict = "incorrect"
    result.update({"coverage": round(coverage, 3), "relevance": round(rel, 3), "gave_up": gave, "keyword_list": kwlist, "score": round(max(0.0, min(1.0, score)), 3),
                   "verdict": verdict, "answered_question": verdict not in ("off_topic", "non_answer"),
                   "missing": [c["id"] for c in result["components"] if not c["present"]], "missing_required": missing_required})
    # key error / omission
    if major_mis:
        result["key_error"] = major_mis[0]["explain"]
    elif kwlist:
        result["key_error"] = "Listed terms without explaining how they connect; an interviewer needs the mechanism, not keywords."
    elif missing_required:
        cm = next(c for c in q.components if c.id == missing_required[0])
        result["key_error"] = "Did not address: %s" % cm.text
    elif result["missing"]:
        if is_derived_rubric(q):
            labels = [c.text.replace("Mentions ", "") for c in q.components if c.id in result["missing"]][:3]
            result["key_error"] = "The guide's answer also brings in: %s" % ", ".join(labels)
        else:
            cm = next(c for c in q.components if c.id == result["missing"][0])
            result["key_error"] = "Omitted: %s" % cm.text
    else:
        result["key_error"] = None
    result["stronger_answer"] = q.solution
    # optional LLM refinement
    if use_llm and provider.active_provider(llm_pref) != "offline":
        _refine_with_llm(q, text, result, llm_pref)
    result["summary"] = _summary(q, result)
    return result


def _refine_with_llm(q: Question, text: str, result: Dict, pref: str) -> None:
    findings = "Deterministic coverage %.0f%%; components present: %s; missing: %s; misconceptions: %s; numbers found: %s" % (
        result["coverage"] * 100, [c["id"] for c in result["components"] if c["present"]], result["missing"],
        [m["id"] for m in result["misconceptions"]], result["numbers"][:8])
    user = prompts.EVALUATOR_USER.format(
        question_id=q.id, skill=q.skill, difficulty=q.difficulty, question_text=q.text,
        components="\n".join("- %s: %s" % (c.id, c.text) for c in q.components),
        misconceptions="\n".join("- %s: %s" % (m.id, m.explain) for m in q.misconceptions) or "(none listed)",
        solution=q.solution, assumptions=q.assumptions or "(none)", findings=findings, answer=text)
    data, prov = provider.complete_json(prompts.EVALUATOR_SYSTEM, user, pref, worker="evaluator")
    ev = schemas.parse(schemas.TechnicalEvaluation, data)
    result["provider"] = prov
    if not ev:
        return
    result["llm"] = ev.dict()
    # merge: LLM may flip components with evidence
    by_id = {c["id"]: c for c in result["components"]}
    changed = False
    for cj in ev.components:
        if cj.id in by_id and by_id[cj.id]["present"] != cj.present and (cj.evidence or not cj.present):
            by_id[cj.id].update({"present": cj.present, "evidence": cj.evidence, "source": "llm"})
            changed = True
    for mj in ev.misconceptions:
        ids = {m["id"] for m in result["misconceptions"]}
        if mj.present and mj.id not in ids:
            mdef = next((m for m in q.misconceptions if m.id == mj.id), None)
            if mdef:
                result["misconceptions"].append({"id": mj.id, "evidence": mj.evidence, "explain": mdef.explain, "severity": mdef.severity, "source": "llm"})
    if changed:
        total_w = sum(c.weight for c in q.components) or 1.0
        got = sum(c["weight"] for c in result["components"] if c["present"])
        result["coverage"] = round(got / total_w, 3)
        result["missing"] = [c["id"] for c in result["components"] if not c["present"]]
        result["missing_required"] = [c["id"] for c in result["components"] if not c["present"] and c["required"]]
    model = 0.6 * ev.correctness + 0.25 * ev.depth + 0.15 * ev.clarity
    if is_derived_rubric(q) and not result.get("keyword_list"):
        # auto-derived term lists are a weak signal; trust the model's reading more, and most when the list is thin
        thin = sum(c.weight for c in q.components) < 3.0
        w_model, band = (0.9, 0.8) if thin else (0.7, 0.5)
    else:
        w_model, band = 0.5, 0.25
    blended = (1 - w_model) * result["score"] + w_model * model
    blended = max(result["score"] - band, min(result["score"] + band, blended))
    result["score"] = round(max(0.0, min(1.0, blended)), 3)
    # recompute the verdict so it stays consistent with the blended score
    sc = result["score"]
    major = [m for m in result["misconceptions"] if m.get("severity") == "major"]
    if sc >= 0.75 and not major and not result["missing_required"]:
        result["verdict"] = "correct"
    elif sc >= 0.35:
        result["verdict"] = "partial"
    else:
        result["verdict"] = "incorrect"
    if not ev.answered_question:
        result["answered_question"] = False
        result["verdict"] = "off_topic" if result["score"] < 0.3 else result["verdict"]
    if ev.key_error:
        result["key_error"] = ev.key_error
    if ev.stronger_answer:
        result["stronger_answer"] = ev.stronger_answer
    if ev.notes:
        result["llm_notes"] = ev.notes


def _summary(q: Question, r: Dict) -> str:
    got = [c["text"] for c in r["components"] if c["present"]]
    miss = [c["text"] for c in r["components"] if not c["present"]]
    parts = []
    if got:
        parts.append("Covered: " + "; ".join(g[:70] for g in got[:4]) + ".")
    if miss:
        parts.append("Missing: " + "; ".join(m[:70] for m in miss[:3]) + ".")
    for m in r["misconceptions"]:
        parts.append("Error: " + m["explain"])
    if r.get("gave_up"):
        parts.append("Signalled uncertainty ('I don't know' / 'I forget').")
    return " ".join(parts) or "No rubric components matched."


# ----------------------------------------------------------------------------- numeric

def evaluate_numeric(gen_q: Dict, answer: str) -> Dict:
    text = answer or ""
    nums = extract_numbers(text)
    result = {"question_id": gen_q["id"], "skill": gen_q["skill"], "difficulty": gen_q["difficulty"], "kind": "numeric", "answer": text,
              "numbers": nums, "expected": gen_q["answer"], "unit": gen_q.get("unit"), "components": [], "misconceptions": [], "provider": "deterministic"}
    if not nums:
        result.update({"score": 0.0, "verdict": "non_answer", "answered_question": False, "key_error": "No number given.",
                       "stronger_answer": gen_q["solution"], "summary": "No numeric answer."})
        return result
    best = None
    for v in nums:
        ok, err = numeric_mod.check(v, gen_q)
        if best is None or (err is not None and err < best[1]):
            best = (ok, err, v)
    ok, err, v = best
    secondary_ok = False
    if gen_q.get("secondary_answer") is not None:
        sa = gen_q["secondary_answer"]
        secondary_ok = any(abs(n - sa) <= max(0.05 * abs(sa), 0.05) for n in nums)
    score = 1.0 if ok else (0.5 if (err is not None and err <= 3 * (gen_q["tolerance"] if gen_q.get("tol_type") == "abs" else gen_q["tolerance"] * abs(gen_q["answer"]))) else 0.0)
    if not ok and secondary_ok:
        score = max(score, 0.4)
    verdict = "correct" if ok else ("partial" if score > 0 else "incorrect")
    result.update({"score": score, "verdict": verdict, "answered_question": True, "closest": v, "error": err, "secondary_ok": secondary_ok,
                   "key_error": None if ok else "Expected about %s %s; you said %s." % (_fmt(gen_q["answer"]), gen_q.get("unit", ""), _fmt(v)),
                   "stronger_answer": gen_q["solution"], "summary": ("Correct (%s)." % _fmt(v)) if ok else ("Off: %s vs expected %s." % (_fmt(v), _fmt(gen_q["answer"])))})
    return result


def _fmt(v: float) -> str:
    if v is None:
        return "?"
    if abs(v) >= 100:
        return "%.0f" % v
    return ("%.2f" % v).rstrip("0").rstrip(".")
