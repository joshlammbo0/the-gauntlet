"""Behavioral and TMAY evaluation: rubric-based, with optional LLM refinement.

Dimensions: relevance, structure, specificity, ownership, authenticity, concision, reflection.
Each is scored 0–1 deterministically from text features; the LLM (if available) can adjust each by
at most ±0.3 with evidence. Unsupported claims are checked against the candidate's verified facts."""
import re
from typing import Dict, List, Optional

from app.knowledge.bank import Question
from app.engine import delivery
from app.llm import provider, prompts, schemas
from app.profile import facts

STRUCTURE_MARKERS = {
    "situation": [r"\b(last|this) (summer|year|fall|spring|season)\b", r"\bwhen i was\b", r"\bat (hobo|georgetown|the practice|gci|gadif)\b", r"\bin (my )?(freshman|sophomore)\b", r"\bduring\b"],
    "task": [r"\b(my (job|role|task|goal) was|i (needed|had) to|i was (asked|responsible|supposed)|the (goal|challenge|problem|question) was|we (had|needed) to|needed to|had to)\b"],
    "action": [r"\bso i\b", r"\bi (decided|built|started|went|called|asked|rebuilt|changed|compared|analyzed|pulled|wrote|organized|set up|proposed|pushed|tracked|tested)\b", r"\bfirst,? i\b", r"\bthen i\b"],
    "result": [r"\b(as a result|the result|in the end|ended up|which led to|we (won|finished|got)|it (worked|passed|was approved)|approved|added it|up \d|\d+%|ranked|committed|got (the|into|a|an)|didn'?t get|won|earned|landed|secured|passed|the (next|following) (time|interview|week|season)|could answer|improved|outcome)\b"],
    "lesson": [r"\b(i learned|the lesson|what i took|taught me|i realized|now i|since then|going forward)\b"],
}

OWNERSHIP_I = r"\bi\b|\bmy\b|\bme\b"
OWNERSHIP_WE = r"\bwe\b|\bour\b|\bus\b|\bthe team\b"

CATEGORY_RELEVANCE = {  # words that should appear for the answer to be on-topic for the category
    "failure": [r"fail|mistake|wrong|missed|lost|fell short|didn't|did not|error"],
    "conflict": [r"disagree|conflict|push(ed)? back|argu|tension|difficult|feedback|criticis"],
    "feedback": [r"feedback|criticis|told me|coach|captain|owner|associate|learned|changed"],
    "leadership": [r"led|lead|organized|convinced|took (charge|ownership|the lead)|stepped up|coach|mentor|team"],
    "teamwork": [r"team|together|teammate|group|we"],
    "pressure": [r"deadline|pressure|hours|juggl|priorit|stress|at the same time|both"],
    "challenge": [r"challenge|hardest|injur|diagnos|setback|obstacle|overc"],
    "analytical": [r"data|model|analy|spreadsheet|excel|found|number|revenue|reimburs|procedure"],
    "initiative": [r"started|built|founded|from scratch|on my own|took (the )?initiative|reached out|created"],
    "why": [r"banking|advis|transaction|deal|m&a|valuation|group|firm|bank"],
    "tmay": [r"pittsburgh|tennis|georgetown|hobo|summer|gci|club|banking"],
    "strengths": [r"strength|weakness|good at|struggle|working on"],
    "other": [r".*"],
}

GENERIC = delivery.GENERIC_PHRASES

# claims that would contradict verified facts (pattern → correction)
FACT_CHECKS = [
    (r"\b(20|25|30|50)\+? (dcf|models)\b", "Resume says 10+ DCF models at Hobo Ventures."),
    (r"\bled (the )?(gci|united therapeutics|uthr) pitch\b|\bmy (uthr|united therapeutics) pitch\b", "The UTHR deck lists five other presenters; say what part was yours."),
    (r"\bno\.? ?1 (singles|in the lineup)\b|\bplayed (number )?one\b", "Resume: No. 3 singles and No. 2 doubles as a freshman."),
    (r"\bfull.time (analyst|intern) at (goldman|morgan|jpm)", "No such role is documented."),
    (r"\b(3\.9|3\.8)\b.{0,10}gpa", "Resume says 4.0 GPA."),
    (r"\b(23|48|46)\s*%.{0,40}(standard ?aero|saro)", "StandardAero upside is inconsistent across your own sources (resume 48%, model 46%, notes 23%); be sure which you quote."),
]


def _ratio(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text, flags=re.I))


def evaluate_behavioral(q: Question, answer: str, duration_sec: Optional[float] = None, llm_pref: str = "auto", use_llm: bool = True,
                        pauses: Optional[List[float]] = None) -> Dict:
    text = answer or ""
    cat = q.behavioral_category or "other"
    kind = "tmay" if cat == "tmay" else ("why" if cat == "why" else "story")
    metrics = delivery.analyze(text, duration_sec, kind, pauses)
    n_words = metrics["words"]
    result: Dict = {"question_id": q.id, "skill": q.skill, "difficulty": q.difficulty, "kind": "behavioral", "category": cat, "answer": text,
                    "delivery": metrics, "components": [], "misconceptions": [], "llm": None, "provider": "offline"}
    if n_words < 8:
        result.update({"score": 0.0, "verdict": "non_answer", "answered_question": False, "dimensions": {}, "key_weakness": "No real answer given.",
                       "unsupported_claims": [], "stronger_version": q.solution, "summary": "No answer."})
        return result
    low = text.lower()
    # demands (components) from the question definition
    for c in q.components:
        ev = None
        for k in c.kw:
            m = re.search(k, low, flags=re.I)
            if m:
                ev = m.group(0)
                break
        result["components"].append({"id": c.id, "text": c.text, "present": ev is not None, "evidence": ev, "required": c.required, "weight": c.weight, "source": "deterministic"})
    demands_met = sum(1 for c in result["components"] if c["present"]) / max(len(result["components"]), 1)
    # structure
    present = {k: any(re.search(p, low) for p in pats) for k, pats in STRUCTURE_MARKERS.items()}
    if kind == "story":
        structure = (0.15 * present["situation"] + 0.15 * present["task"] + 0.35 * present["action"] + 0.25 * present["result"] + 0.10 * present["lesson"])
    elif kind == "tmay":
        beats = [r"pittsburgh|grew up|from", r"tennis", r"georgetown|msb|finance", r"hobo|summer|royalt|energy|valuation", r"gci|gadif|club|aerospace|collegiate", r"banking|advis|transaction"]
        hits = [bool(re.search(b, low)) for b in beats]
        order_ok = True
        pos = [re.search(b, low).start() if re.search(b, low) else None for b in beats]
        last = -1
        for p in pos:
            if p is not None:
                if p < last - 200:  # tolerate small inversions
                    order_ok = False
                last = max(last, p)
        structure = 0.7 * (sum(hits) / len(beats)) + 0.3 * (1.0 if order_ok else 0.4)
        result["tmay_beats"] = dict(zip(["origin", "tennis", "georgetown", "spark", "clubs", "bridge"], hits))
        result["tmay_order_ok"] = order_ok
    else:  # why
        spark = bool(re.search(r"hobo|summer|royalt|first (time|experience)|when i|started|spark", low))
        proof = bool(re.search(r"gci|gadif|pitch|calls?|conversation|map|fellow|club|built|model", low))
        ib_specific = bool(re.search(r"advis|transaction|deal|m&a|capital (structure|rais)|execut|client|sell.side|buy.side", low))
        contrast = bool(re.search(r"(rather than|instead of|versus|vs\.?|not|unlike).{0,40}(research|consulting|investing|buy.side|private equity|operator)|investing side|advisory side", low))
        structure = 0.25 * spark + 0.25 * proof + 0.3 * ib_specific + 0.2 * contrast
        result["why_beats"] = {"spark": spark, "proof": proof, "ib_specific": ib_specific, "contrast": contrast}
    # specificity: numbers, named entities, concrete nouns
    numbers = len(re.findall(r"\b\d[\d,.%x]*\b", text))
    names = len(re.findall(r"\b(hobo|georgetown|gci|gadif|map|wells|guggenheim|insulet|viasat|standardaero|united therapeutics|seahawks|marcellus|utica|pittsburgh|vascular|owner|principal|cio|coach|captain|endocrinologist|morgan stanley|goldman|evercore|lazard|barclays|jefferies|leerink|santander|houlihan|moelis|centerview|fig|organon|devon|coterra|tyvaso|omnipod)\b", low))
    # proper nouns mid-sentence (people, firms, products) count as specifics too
    proper = len(set(m.group(1) for m in re.finditer(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{2,})\b", text) if m.group(1) not in {"The", "And", "But", "When", "Then", "After", "Division", "Georgetown", "Tennis"}))
    specificity = min(1.0, 0.25 + 0.15 * min(numbers, 3) + 0.12 * min(names + proper, 4))
    # ownership
    i_n, we_n = _ratio(OWNERSHIP_I, text), _ratio(OWNERSHIP_WE, text)
    if cat in ("leadership", "initiative", "analytical", "failure", "feedback", "conflict"):
        ownership = min(1.0, (i_n + 1) / (i_n + we_n + 1) * 1.1)
    elif cat == "teamwork":
        ownership = 1.0 if 0.25 <= (i_n / max(i_n + we_n, 1)) <= 0.8 else 0.6
    else:
        ownership = 0.85
    # authenticity: penalize generic phrases, reward specific detail
    generic_hits = sum(metrics["generic_phrases"].values())
    authenticity = max(0.0, min(1.0, 0.8 + 0.1 * min(names + numbers, 2) - 0.2 * generic_hits))
    # concision
    lo, hi = metrics["target_seconds"]
    est_sec = duration_sec or (n_words / 150 * 60)
    if est_sec <= hi:
        concision = 1.0 if est_sec >= lo * 0.6 else 0.7
    else:
        concision = max(0.2, 1.0 - (est_sec - hi) / hi)
    concision -= min(0.3, 0.03 * metrics["filler_total"] + 0.05 * metrics["hedge_total"])
    concision = max(0.0, concision)
    # reflection
    reflection = 1.0 if present["lesson"] else (0.4 if kind != "story" else 0.2)
    if kind != "story":
        reflection = 0.8 if re.search(r"realized|learned|what i (want|found)|that's why|which is why", low) else 0.5
    # relevance
    cat_pats = CATEGORY_RELEVANCE.get(cat, [r".*"])
    rel_hits = sum(1 for p in cat_pats if re.search(p, low))
    relevance = 1.0 if rel_hits else 0.3
    answered = relevance >= 0.5 and demands_met >= 0.34
    # unsupported claims vs verified facts
    unsupported = [note for pat, note in FACT_CHECKS if re.search(pat, low)]
    # prompt_only stories used as fact
    for s in facts.STORIES:
        if s["status"] == facts.PROMPT_ONLY and re.search(r"captain|modeling mistake|junior (tennis )?student", low) and s["id"] in ("captain_feedback", "model_mistake", "junior_student"):
            unsupported.append("Story '%s' is not yet in your verified knowledge base; add the specifics before relying on it." % s["title"])
            break
    dims = {"relevance": relevance, "structure": round(structure, 2), "specificity": round(specificity, 2), "ownership": round(ownership, 2),
            "authenticity": round(authenticity, 2), "concision": round(concision, 2), "reflection": round(reflection, 2), "demands_met": round(demands_met, 2)}
    weights = {"relevance": 0.2, "structure": 0.2, "specificity": 0.15, "ownership": 0.1, "authenticity": 0.1, "concision": 0.1, "reflection": 0.05, "demands_met": 0.1}
    score = sum(dims[k] * w for k, w in weights.items())
    if not answered:
        score = min(score, 0.4)
    if unsupported:
        score = min(score, 0.6)
    missing_required_demands = [c for c in result["components"] if c["required"] and not c["present"]]
    if missing_required_demands:
        score = min(score, 0.6 if len(missing_required_demands) == 1 else 0.45)
    if generic_hits >= 2 and specificity < 0.5:
        score = min(score, 0.4)
    if metrics.get("stalling"):
        score -= 0.05
    result.update({"dimensions": dims, "score": round(max(0.0, min(1.0, score)), 3), "answered_question": answered, "unsupported_claims": unsupported,
                   "structure_present": present})
    # key weakness (deterministic pick)
    weak = sorted(((k, v) for k, v in dims.items() if k != "demands_met"), key=lambda kv: kv[1])
    kw_map = {"relevance": "You did not actually answer this question; the story fits a different prompt.",
              "structure": "Structure is missing pieces: %s." % ", ".join(k for k, v in present.items() if not v) if kind == "story" else "The arc is incomplete (see beats).",
              "specificity": "Too few specifics: no numbers, names or concrete details an interviewer could probe.",
              "ownership": "Your personal role is unclear ('we' dominates); say what YOU did.",
              "authenticity": "Generic phrasing (%s) makes it sound rehearsed." % ", ".join(metrics["generic_phrases"]) if metrics["generic_phrases"] else "It reads generic; add a memorable detail.",
              "concision": "Too long or too many fillers/hedges for the question type.",
              "reflection": "No lesson or reflection; say what changed in how you operate."}
    result["key_weakness"] = unsupported[0] if unsupported else (kw_map["relevance"] if not answered else kw_map[weak[0][0]])
    missing_demands = [c["text"] for c in result["components"] if not c["present"] and c["required"]]
    result["missing_demands"] = missing_demands
    result["coach_notes"] = q.solution
    result["stronger_version"] = _stronger_template(q, result, kind, lo, hi)
    if use_llm and provider.active_provider(llm_pref) != "offline":
        _refine(q, text, result, llm_pref)
    result["verdict"] = "strong" if result["score"] >= 0.75 and answered else ("adequate" if result["score"] >= 0.5 else ("weak" if answered else "off_topic"))
    result["summary"] = _summary(result)
    return result


def _refine(q: Question, text: str, result: Dict, pref: str) -> None:
    fact_lines = []
    for e in facts.EXPERIENCES:
        fact_lines.append("%s (%s): %s" % (e["org"], e["dates"], " | ".join(b["text"][:120] for b in e["bullets"])))
    for s in facts.STORIES:
        if s["status"] == facts.VERIFIED and not s.get("sensitive"):
            fact_lines.append("Story: %s: %s" % (s["title"], s["summary"][:200]))
    user = prompts.BEHAVIORAL_EVALUATOR_USER.format(
        question_text=q.text, demands="; ".join(c.text for c in q.components), facts="\n".join(fact_lines)[:4000],
        metrics=str({k: result["dimensions"][k] for k in result["dimensions"]}) + " " + str(result["delivery"]["notes"]), answer=text)
    data, prov = provider.complete_json(prompts.BEHAVIORAL_EVALUATOR_SYSTEM, user, pref, worker="evaluator")
    ev = schemas.parse(schemas.BehavioralEvaluation, data)
    result["provider"] = prov
    if not ev:
        return
    result["llm"] = ev.dict()
    d = result["dimensions"]
    for k in ("relevance", "structure", "specificity", "ownership", "authenticity", "concision", "reflection"):
        v = getattr(ev, k)
        d[k] = round(max(d[k] - 0.3, min(d[k] + 0.3, 0.5 * d[k] + 0.5 * v)), 2)
    weights = {"relevance": 0.2, "structure": 0.2, "specificity": 0.15, "ownership": 0.1, "authenticity": 0.1, "concision": 0.1, "reflection": 0.05, "demands_met": 0.1}
    score = sum(d[k] * w for k, w in weights.items())
    if not ev.answered_question:
        result["answered_question"] = False
        score = min(score, 0.4)
    result["unsupported_claims"] = list(dict.fromkeys(result["unsupported_claims"] + ev.unsupported_claims))
    if result["unsupported_claims"]:
        score = min(score, 0.6)
    result["score"] = round(max(0.0, min(1.0, score)), 3)
    if ev.key_weakness:
        result["key_weakness"] = ev.key_weakness
    if ev.stronger_version:
        result["stronger_version"] = ev.stronger_version
    if ev.notes:
        result["llm_notes"] = ev.notes


def _stronger_template(q: Question, r: Dict, kind: str, lo: int, hi: int) -> str:
    """Offline 'stronger answer': a concrete rebuild plan using only the candidate's own facts, with [brackets] for
    specifics only he can supply. Not a scripted answer; the point is the shape and the missing pieces."""
    missing = [c["text"] for c in r["components"] if not c["present"]]
    pres = r.get("structure_present", {})
    parts = []
    if kind == "story":
        parts.append("Open with one sentence of situation (when, where, stakes)" + ("" if pres.get("situation") else " [missing]") + ".")
        parts.append("State your task in one line" + ("" if pres.get("task") else " [missing]") + ".")
        parts.append("Spend most of the time on two or three actions YOU took, with one number or name each" + ("" if pres.get("action") else " [missing]") + ".")
        parts.append("Give the result as a fact ([ranking, approval %, outcome])" + ("" if pres.get("result") else " [missing]") + ".")
        parts.append("Close with the lesson in one sentence and how you apply it now" + ("" if pres.get("lesson") else " [missing]") + ".")
    elif kind == "tmay":
        beats = r.get("tmay_beats", {})
        order = ["origin", "tennis", "georgetown", "spark", "clubs", "bridge"]
        labels = {"origin": "Pittsburgh origin", "tennis": "tennis thread", "georgetown": "Georgetown/MSB finance", "spark": "Hobo Ventures asset-level valuation spark", "clubs": "GCI/GADIF/MAP follow-through", "bridge": "investing-vs-advising bridge into banking"}
        parts.append("Keep the six beats in order: " + ", ".join(("%s%s" % (labels[b], "" if beats.get(b) else " [missing]")) for b in order) + ".")
        parts.append("Say 'didn't know what I wanted' at most once; end on the advisory line, not on 'happy to dive deeper'.")
    else:
        wb = r.get("why_beats", {})
        parts.append("Spark: the specific moment at Hobo Ventures where valuation turned into a decision" + ("" if wb.get("spark") else " [missing]") + ".")
        parts.append("Proof: two actions since (GCI/GADIF pitches, MAP, banker conversations)" + ("" if wb.get("proof") else " [missing]") + ".")
        parts.append("A banking-only reason: advising on transactions / capital structure execution, contrasted with research or consulting" + ("" if (wb.get("ib_specific") and wb.get("contrast")) else " [missing]") + ".")
        parts.append("One honest line on the hours; no exits.")
    if missing:
        parts.append("This question specifically wanted: " + "; ".join(m[:90] for m in missing[:3]) + ".")
    parts.append("Target %d–%d seconds." % (lo, hi))
    return " ".join(parts)


def _summary(r: Dict) -> str:
    d = r["dimensions"]
    parts = ["Score %.0f/100." % (r["score"] * 100)]
    if not r["answered_question"]:
        parts.append("Did not answer the question asked.")
    lows = [k for k, v in d.items() if v < 0.5 and k != "demands_met"]
    if lows:
        parts.append("Weak on: " + ", ".join(lows) + ".")
    if r.get("missing_demands"):
        parts.append("Missing: " + "; ".join(m[:60] for m in r["missing_demands"][:2]) + ".")
    if r.get("unsupported_claims"):
        parts.append("Fact check: " + r["unsupported_claims"][0])
    if r["delivery"]["notes"]:
        parts.append(r["delivery"]["notes"][0])
    return " ".join(parts)
