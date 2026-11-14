"""Post-interview debrief built from stored turns and evaluations."""
from typing import Dict, List

from app import db
from app.engine import curriculum
from app.knowledge.skills import SKILLS, area_of
from app.knowledge.bank import load_bank
from app.knowledge import sources


def _canonical_question(qid, text: str, bank) -> str:
    """Show the question itself, without the interviewer's transition ('Hm. Next. Going back to something from earlier. …')."""
    canon = None
    if qid and qid in bank:
        canon = bank[qid].text
    elif qid:
        rec = sources.get(qid)
        canon = rec["question"] if rec else None
    return canon if canon and text.endswith(canon) else text

READINESS = [(0.85, "Strong: answers would hold up in a first round at most banks."),
             (0.7, "Solid with gaps: likely to pass a friendly first round; weak spots would be exposed by a VP."),
             (0.55, "Mixed: fundamentals present, but several answers would not survive a second follow-up."),
             (0.4, "Below the bar: foundational errors or evasive answers in several places."),
             (0.0, "Not ready for live interviews on this material yet.")]


def build(session_id: str) -> Dict:
    s = db.get_session(session_id)
    turns = db.get_turns(session_id)
    evals = db.get_evaluations(session_id)
    bank = load_bank()
    by_turn = {e["turn_id"]: e for e in evals}
    qa: List[Dict] = []
    interviewer_q = None
    for t in turns:
        if t["role"] == "interviewer":
            interviewer_q = t
        elif t["role"] == "candidate":
            e = by_turn.get(t["id"])
            d = (e or {}).get("data", {})
            item = {"turn_id": t["id"], "idx": t["idx"], "question": _canonical_question(interviewer_q.get("question_id"), interviewer_q["text"], bank) if interviewer_q else "", "question_kind": (interviewer_q or {}).get("kind"),
                    "question_id": (interviewer_q or {}).get("question_id"), "answer": t["text"], "duration": (t.get("meta") or {}).get("duration"),
                    "evaluation_id": (e or {}).get("id"), "score": (e or {}).get("score"), "verdict": (e or {}).get("verdict"), "skill": (e or {}).get("skill"),
                    "got_right": [c["text"] for c in d.get("components", []) if c.get("present")],
                    "got_wrong": [m["explain"] for m in d.get("misconceptions", [])],
                    "omitted": [c["text"] for c in d.get("components", []) if not c.get("present")],
                    "answered_question": d.get("answered_question"), "key_error": d.get("key_error") or d.get("key_weakness"),
                    "stronger_answer": sources.strip_page_header(d.get("stronger_answer") or d.get("stronger_version") or "") or None, "coach_notes": d.get("coach_notes"), "delivery": d.get("delivery"),
                    "dimensions": d.get("dimensions"), "unsupported_claims": d.get("unsupported_claims"), "appealed": (e or {}).get("appealed"),
                    "concepts_to_review": [SKILLS.get((e or {}).get("skill") or "", "")] if e else [], "provider": d.get("provider"),
                    "provisional": d.get("provisional", False), "citation": d.get("citation"), "level": d.get("level"), "callback_of": (interviewer_q or {}).get("meta", {}).get("callback_of")}
            qa.append(item)
    scored = [x for x in qa if x["score"] is not None]
    tech = [x for x in scored if x["question_kind"] in ("technical", "numeric", "resume")]
    beh = [x for x in scored if x["question_kind"] == "behavioral"]
    overall = sum(x["score"] for x in scored) / len(scored) if scored else None
    readiness = next(label for thr, label in READINESS if (overall or 0) >= thr) if scored else "No scored answers."
    # technical corrections: precise
    corrections = []
    for x in tech:
        if x["got_wrong"] or (x["score"] is not None and x["score"] < 0.6):
            # once the model has graded the answer, its key error is the precise correction; the keyword checklist is only a fallback
            deep = x.get("provider") not in (None, "offline", "deterministic") and not x.get("provisional")
            errors = x["got_wrong"] or ([x["key_error"]] if deep and x.get("key_error") and x.get("verdict") != "skipped" else [])
            corrections.append({"question": x["question"], "errors": errors, "omitted": [] if deep else x["omitted"][:3], "fix": x["stronger_answer"]})
    # behavioral feedback
    beh_fb = []
    for x in beh:
        beh_fb.append({"question": x["question"], "score": x["score"], "key_weakness": x["key_error"], "dimensions": x["dimensions"],
                       "unsupported_claims": x["unsupported_claims"], "stronger_version": x["stronger_answer"]})
    # delivery aggregate
    durations = [x["duration"] for x in qa if x.get("duration")]
    dls = [x["delivery"] for x in qa if x.get("delivery")]
    delivery = {
        "answers": len(qa), "avg_duration_sec": round(sum(durations) / len(durations), 1) if durations else None,
        "avg_words": round(sum(d["words"] for d in dls) / len(dls)) if dls else None,
        "avg_wpm": round(sum(d["wpm"] for d in dls if d.get("wpm")) / max(1, len([d for d in dls if d.get("wpm")]))) if any(d.get("wpm") for d in dls) else None,
        "total_fillers": sum(d.get("filler_total", 0) for d in dls), "total_hedges": sum(d.get("hedge_total", 0) for d in dls),
        "too_long": sum(1 for d in dls if d.get("length_flag") in ("too_long", "too_long_est")),
        "repeated_phrases": sorted({p for d in dls for p in d.get("repeated_phrases", [])})[:8],
        "notes": [n for d in dls for n in d.get("notes", [])][:10], "basis": "transcript" + ("+acoustic" if any(d.get("basis") == "transcript+acoustic" for d in dls) else ""),
    }
    weakest = sorted(scored, key=lambda x: x["score"])[:5]
    skills_touched = sorted({x["skill"] for x in scored if x["skill"]})
    areas = {}
    for x in scored:
        if x["skill"]:
            areas.setdefault(area_of(x["skill"]), []).append(x["score"])
    contradictions = (s.get("state") or {}).get("contradictions", [])
    callbacks = (s.get("state") or {}).get("callbacks", [])
    pending_deep = sum(1 for e in evals if (e.get("data") or {}).get("provisional"))
    # 30-second verdict: strengths, highest-leverage problems, next actions
    strengths = [x for x in sorted(scored, key=lambda x: -x["score"]) if x["score"] >= 0.75][:3]
    problems = [x for x in sorted(scored, key=lambda x: x["score"]) if x["score"] < 0.6][:3]
    next_actions = []
    rem = curriculum.remediation_plan(2)
    if problems:
        p0 = problems[0]
        if p0.get("skill"):
            next_actions.append({"key": "fix", "label": "Fix the root weakness: %s" % SKILLS.get(p0["skill"], p0["skill"]), "route": "#/fix/%s" % p0["skill"]})
            next_actions.append({"key": "reattempt", "label": "Reattempt with new numbers", "evaluation_id": p0.get("evaluation_id")})
        next_actions.append({"key": "weak", "label": "Review my %d weak answer(s)" % len(problems), "anchor": "weak"})
    if (s.get("config") or {}).get("context_id"):
        next_actions.append({"key": "context", "label": "Continue my interview prep plan", "route": "#/prepare/%s" % s["config"]["context_id"]})
    if scored:
        next_actions.append({"key": "retest", "label": "Targeted follow-up on my weakest questions", "retest": True})
    verdict = {
        "headline": readiness, "score": round(overall, 3) if overall is not None else None,
        "strengths": [{"question": x["question"][:120], "skill": x["skill"], "score": x["score"]} for x in strengths],
        "problems": [{"question": x["question"][:120], "skill": x["skill"], "score": x["score"], "key": x["key_error"]} for x in problems],
        "next_actions": next_actions, "remediation": rem,
    }
    return {
        "session_id": session_id, "mode": s["mode"], "config": s["config"], "status": s["status"], "verdict": verdict,
        "overall": {"score": round(overall, 3) if overall is not None else None, "readiness": readiness, "n_scored": len(scored),
                    "technical_avg": round(sum(x["score"] for x in tech) / len(tech), 3) if tech else None,
                    "behavioral_avg": round(sum(x["score"] for x in beh) / len(beh), 3) if beh else None,
                    "by_area": {a: round(sum(v) / len(v), 3) for a, v in areas.items()},
                    "caveat": "Readiness is a calibrated training indicator from this session's rubric scores, not a prediction of any bank's decision."},
        "questions": qa, "technical_corrections": corrections, "behavioral_feedback": beh_fb, "delivery": delivery,
        "weakest": [{"question_id": x["question_id"], "question": x["question"], "score": x["score"], "skill": x["skill"]} for x in weakest],
        "contradictions": contradictions, "skills_touched": skills_touched,
        "callbacks": callbacks, "pending_deep_grades": pending_deep,
        "remediation": curriculum.remediation_plan(4),
    }
