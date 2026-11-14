"""Challenge classification and follow-up decision.

Given an evaluation (technical/behavioral/numeric) and session context, decide ONE action:
  probe   – challenge the single most important issue (with a reason code)
  clarify – the answer was ambiguous; ask for clarification rather than guessing
  deepen  – the answer was good; go one level deeper (bank follow-up or chained question)
  pivot   – move on (enough depth, or time, or nothing worth probing)
  contradiction – an earlier claim conflicts with this one
Reason codes map to the required challenge taxonomy.
"""
from typing import Dict, List, Optional, Tuple

from app.knowledge.bank import Question, load_bank

REASONS = {
    "factual_error": "Factual error", "math_error": "Mathematical error", "unsupported_assumption": "Unsupported assumption",
    "missing_causal": "Missing causal explanation", "contradiction": "Contradiction", "overgeneralization": "Overgeneralization",
    "irrelevant": "Irrelevant response", "weak_contribution": "Weak personal contribution", "missing_numbers": "Missing numerical justification",
    "superficial_industry": "Superficial industry knowledge", "did_not_answer": "Failure to answer the original question",
    "deeper_probe": "Opportunity for deeper probing", "gave_up": "Gave up too early", "unsupported_claim": "Claim not supported by your documents",
    "generic": "Generic answer", "too_long": "Answer too long / unfocused",
}

CLARIFY_MARKERS = [r"\bit depends\b", r"\bboth\b", r"\beither\b", r"\bor\b.*\bor\b", r"\bsometimes\b", r"\bkind of\b"]

GENERIC_PROBES = {
    "factual_error": ["Walk through that again. {hint}", "That's not right. Where does the cash actually go?", "Check that: {hint}"],
    "math_error": ["Check your math. Talk me through the arithmetic.", "Run that number again, slowly.", "What did you multiply by what?"],
    "unsupported_assumption": ["Why that assumption?", "What economically justifies that?", "Defend that number."],
    "missing_causal": ["Why?", "You're describing what happens. Why does it happen?", "Walk me through the mechanics."],
    "overgeneralization": ["Always? When would that not hold?", "That's a generalization. Give me the exception."],
    "irrelevant": ["That's not what I asked. {restate}", "Come back to the question: {restate}"],
    "weak_contribution": ["You said 'we'. What did you do, specifically?", "What was your personal contribution?"],
    "missing_numbers": ["Can you quantify that?", "Put a number on it.", "Roughly how big was that?"],
    "superficial_industry": ["Go a level deeper on the industry. What's actually driving that?", "Who are the players, and who's winning?"],
    "did_not_answer": ["You didn't answer the question. {restate}", "Let me ask it again: {restate}"],
    "gave_up": ["Don't give up on it. Start with what you do know.", "Take it step by step. What's the first thing that happens?"],
    "unsupported_claim": ["Where does that come from? It isn't in anything you've shown me.", "Be careful: {hint}"],
    "generic": ["That's a generic answer. Give me a specific example.", "I could read that on any cover letter. Make it yours."],
    "too_long": ["Your answer is getting long. What's the single most important point?", "In one sentence: what's the takeaway?"],
    "deeper_probe": ["Okay. {hint}", "Fine. {hint}"],
}


def classify(evaluation: Dict, question: Optional[Dict], state: Dict, persona: Dict) -> Tuple[str, Optional[str], Dict]:
    """Return (action, reason, details)."""
    kind = evaluation.get("kind")
    score = evaluation.get("score") or 0.0
    depth = state.get("followup_depth", 0)
    max_depth = persona.get("max_followup_depth", 2)
    threshold = persona.get("challenge_threshold", 0.6)
    details: Dict = {}
    # time pressure: late in the interview, pivot more
    if state.get("time_fraction", 0) > 0.9:
        return "pivot", None, {"why": "time"}
    if depth >= max_depth:
        return "pivot", None, {"why": "max_depth"}
    if evaluation.get("verdict") == "non_answer":
        return ("probe", "gave_up", {}) if depth == 0 else ("pivot", None, {"why": "no_answer_twice"})
    if not evaluation.get("answered_question", True):
        return "probe", "did_not_answer", {}
    if kind == "numeric":
        if evaluation.get("verdict") == "correct":
            return "pivot", None, {"why": "numeric_correct"}
        return ("probe", "math_error", {"hint": evaluation.get("key_error")}) if depth == 0 else ("pivot", None, {"why": "numeric_second_miss"})
    if kind == "behavioral":
        if evaluation.get("unsupported_claims"):
            return "probe", "unsupported_claim", {"hint": evaluation["unsupported_claims"][0]}
        d = evaluation.get("dimensions", {})
        dl = evaluation.get("delivery", {})
        if dl.get("length_flag") in ("too_long", "too_long_est") and depth == 0:
            return "probe", "too_long", {}
        if d.get("ownership", 1) < 0.5:
            return "probe", "weak_contribution", {}
        if d.get("specificity", 1) < 0.45 or (dl.get("generic_phrases") and d.get("authenticity", 1) < 0.6):
            return "probe", "generic", {}
        if score < threshold:
            return "probe", "missing_causal", {}
        return ("deepen", "deeper_probe", {}) if depth < max_depth - 1 else ("pivot", None, {"why": "good_enough"})
    # technical / resume
    if evaluation.get("misconceptions"):
        m = evaluation["misconceptions"][0]
        return "probe", "factual_error", {"hint": _hint_from_misconception(m), "misconception": m["id"]}
    if evaluation.get("gave_up") and depth == 0:
        return "probe", "gave_up", {}
    ambiguous = evaluation.get("coverage", 1) < 0.5 and any(__import__("re").search(p, evaluation.get("answer", ""), flags=2) for p in CLARIFY_MARKERS)
    if ambiguous and depth == 0:
        return "clarify", None, {"why": "ambiguous"}
    missing_required = evaluation.get("missing_required") or []
    if missing_required:
        return "probe", "missing_causal", {"component": missing_required[0]}
    if score < threshold:
        if evaluation.get("relevance", 1) < 0.3:
            return "probe", "irrelevant", {}
        return "probe", "missing_causal", {"component": (evaluation.get("missing") or [None])[0]}
    # good answer: deepen (bank-defined 'correct' follow-up) if persona wants depth
    if score >= 0.75 and depth < max_depth - 1 and persona.get("seniority", 2) >= 2:
        return "deepen", "deeper_probe", {}
    return "pivot", None, {"why": "satisfied"}


def _hint_from_misconception(m: Dict) -> str:
    # phrase the correction as a question without giving the answer away
    ex = m.get("explain", "")
    first = ex.split(".")[0]
    return "Think again about this: " + first.lower() + "?" if first else "Think about that again."


def bank_followup(q: Optional[Question], evaluation: Dict, action: str, reason: Optional[str], details: Dict,
                  exclude_texts: Optional[set] = None) -> Optional[Dict]:
    """Pick the most specific follow-up from the question bank for this situation, never one already used."""
    if not q:
        return None
    exclude_texts = exclude_texts or set()
    verdict = evaluation.get("verdict")
    missing = set(evaluation.get("missing") or [])
    mis = {m["id"] for m in evaluation.get("misconceptions") or []}
    order: List[str] = []
    if reason == "factual_error" and details.get("misconception"):
        order.append("misconception:" + details["misconception"])
    if reason in ("missing_causal",) and details.get("component"):
        order.append("missing:" + details["component"])
    for mid in mis:
        order.append("misconception:" + mid)
    for cid in missing:
        order.append("missing:" + cid)
    if action == "deepen" or verdict == "correct":
        order.append("correct")
    if reason in ("generic", "missing_causal", "weak_contribution") or (evaluation.get("coverage", 1) < 0.5):
        order.append("vague")
    if verdict in ("incorrect", "off_topic"):
        order.append("wrong")
    order.append("always")
    for trig in order:
        for f in q.followups:
            if f.when == trig and f.text not in exclude_texts:
                return {"text": f.text, "next_id": f.next_id, "trigger": trig}
    return None


def phrase_probe(reason: str, details: Dict, question_text: str, rng) -> str:
    templates = GENERIC_PROBES.get(reason, GENERIC_PROBES["missing_causal"])
    t = templates[rng.randrange(len(templates))]
    hint = details.get("hint") or ""
    return t.replace("{hint}", hint).replace("{restate}", question_text).strip()
