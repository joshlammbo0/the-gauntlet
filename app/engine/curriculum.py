"""Skill map, mastery estimation and spaced review.

Mastery is on a 0–5 scale with an explicit `not_assessed` state. Each observation carries a score
(0–1), difficulty (1–6), kind and timestamp. The estimate is a recency-weighted, difficulty-adjusted
mean with shrinkage toward 2.5 for few observations, so one answer never pins mastery at 0 or 5.
Confidence grows with observation count and consistency.

Review scheduling: SM-2 flavored. A good result lengthens the interval (×ease), a poor one resets it
to one day. Intervals are capped and weighted by how foundational the skill is.
"""
import math
import time
from typing import Dict, List, Optional, Tuple

from app import db
from app.knowledge.skills import SKILLS, area_of, prereqs_of, dependents_of
from app.profile import facts

DAY = 86400.0
FOUNDATIONAL = {"accounting.three_statements", "accounting.depreciation", "valuation.ev_equity", "dcf.ufcf", "dcf.wacc", "dcf.terminal_value", "ma.accretion_dilution", "lbo.basics", "behavioral.tmay", "behavioral.why_ib"}


def _estimate(history: List[Dict], now: Optional[float] = None) -> Tuple[Optional[float], float]:
    if not history:
        return None, 0.0
    now = now or time.time()
    num = 0.0
    den = 0.0
    for h in history:
        age_days = max(0.0, (now - h["t"]) / DAY)
        w_rec = math.exp(-age_days / 30.0)  # 30-day half-ish life
        diff = h.get("difficulty", 2)
        # a correct hard answer counts more; a wrong easy answer counts more against
        s = h["score"]
        w_diff = 0.7 + 0.15 * diff if s >= 0.6 else 1.0 + 0.1 * (6 - diff)
        w = w_rec * w_diff
        if h.get("repeat"):
            w *= 0.25  # farming the same question is weak evidence
        num += w * s
        den += w
    mean = num / den if den else 0.5
    n = sum(0.25 if h.get("repeat") else 1.0 for h in history)  # repeats are weak evidence
    # shrink toward 0.5 (2.5/5) when few observations
    k = 2.0
    shrunk = (mean * n + 0.5 * k) / (n + k)
    mastery = round(shrunk * 5, 2)
    # confidence: count and consistency
    recent = [h["score"] for h in history[-6:]]
    var = sum((x - sum(recent) / len(recent)) ** 2 for x in recent) / len(recent) if recent else 0.25
    distinct_q = len({h.get("q") for h in history})
    confidence = round(min(1.0, (1 - math.exp(-n / 4.0)) * (1 - min(var, 0.25) * 2) * min(1.0, 0.4 + 0.15 * distinct_q)), 2)
    return mastery, confidence


STATES = ["untested", "learning", "developing", "proficient", "mastered", "review_due"]


def state_of(mastery: Optional[float], n_obs: int, confidence: float, due: bool, peak: Optional[float] = None) -> str:
    """Documented state rule. `peak` is the best mastery ever reached (achievements persist: a mastered skill that
    becomes due shows review_due, never drops back to 'learning')."""
    if mastery is None or n_obs == 0:
        return "untested"
    if due and (peak or mastery) >= 3.25:
        return "review_due"
    if mastery >= 4.25 and n_obs >= 5 and confidence >= 0.6:
        return "mastered"
    if mastery >= 3.25 and n_obs >= 3:
        return "proficient"
    if mastery >= 2.25:
        return "developing"
    return "learning"


def level_breakdown(history: List[Dict]) -> Dict[str, Dict]:
    """Per cognitive layer (1-5): attempts and recency-weighted average score."""
    out: Dict[str, Dict] = {}
    now = time.time()
    for h in history:
        raw = h.get("level")
        try:
            lv = str(int(raw)) if raw is not None else str(min(5, max(1, int(h.get("difficulty", 2)))))
        except (TypeError, ValueError):
            lv = str(min(5, max(1, int(h.get("difficulty", 2)))))
        o = out.setdefault(lv, {"n": 0, "num": 0.0, "den": 0.0})
        w = math.exp(-max(0.0, (now - h["t"]) / DAY) / 45.0)
        o["n"] += 1
        o["num"] += w * h["score"]
        o["den"] += w
    return {k: {"n": v["n"], "avg": round(v["num"] / v["den"], 2) if v["den"] else None} for k, v in out.items()}


def record(skill: str, score: float, difficulty: int, kind: str, question_id: Optional[str], session_id: Optional[str], level: Optional[int] = None) -> Dict:
    if skill not in SKILLS:
        return {}
    row = db.get_skill(skill)
    history = (row or {}).get("history", []) or []
    # diminishing returns: the same question answered correctly again within 3 days adds little evidence
    recent_same = [h for h in history if h.get("q") == question_id and time.time() - h["t"] < 3 * DAY]
    weight_note = None
    if recent_same and score >= 0.75:
        weight_note = "repeat"
    try:
        lvl = int(level) if level is not None else min(5, max(1, int(difficulty)))
    except (TypeError, ValueError):
        lvl = min(5, max(1, int(difficulty)))
    history.append({"t": time.time(), "score": round(score, 3), "difficulty": difficulty, "level": lvl, "kind": kind, "q": question_id, "s": session_id, **({"repeat": True} if weight_note else {})})
    mastery, conf = _estimate(history)
    interval = (row or {}).get("interval_days") or 1.0
    if score >= 0.75:
        interval = min(interval * (2.2 if difficulty >= 3 else 1.8), 45.0)
    elif score >= 0.5:
        interval = max(1.0, interval * 1.1)
    else:
        interval = 1.0 if skill in FOUNDATIONAL else 2.0
    next_review = time.time() + interval * DAY
    db.upsert_skill(skill, mastery, conf, len(history), next_review, interval, history)
    return {"skill": skill, "mastery": mastery, "confidence": conf, "n_obs": len(history), "interval_days": interval}


def revise(skill: str, question_id: Optional[str], session_id: Optional[str], new_score: float) -> Optional[Dict]:
    """Deep grading finished after a provisional (deterministic) score was recorded: replace that observation
    instead of appending a second one, then recompute mastery."""
    row = db.get_skill(skill)
    if not row:
        return None
    history = row.get("history", []) or []
    for h in reversed(history):
        if h.get("q") == question_id and h.get("s") == session_id:
            h["score"] = round(new_score, 3)
            h["revised"] = True
            break
    else:
        return None
    mastery, conf = _estimate(history)
    db.upsert_skill(skill, mastery, conf, len(history), row.get("next_review"), row.get("interval_days") or 1.0, history)
    return {"skill": skill, "mastery": mastery}


def skill_map() -> List[Dict]:
    rows = db.all_skills()
    hints = {k: v for k, v in facts.KNOWN_WEAKNESSES["items"]}
    out = []
    for sid, name in SKILLS.items():
        r = rows.get(sid)
        hist = (r or {}).get("history") or []
        if r and r.get("n_obs"):
            mastery, conf = r["mastery"], r["confidence"]
            state = "assessed"
            due = (r.get("next_review") or 0) <= time.time()
        else:
            mastery, conf, state, due = None, 0.0, "not_assessed", False
        peak = max((h.get("peak_mastery", 0) for h in hist), default=None)
        # peak mastery: recompute cheaply as the max of a running estimate over the last 10 observations
        if hist:
            peak = max(peak or 0, mastery or 0)
        out.append({"skill": sid, "area": area_of(sid), "name": name, "mastery": mastery, "confidence": conf, "state": state,
                    "mastery_state": state_of(mastery, (r or {}).get("n_obs", 0), conf, due, peak),
                    "n_obs": (r or {}).get("n_obs", 0), "last_seen": (r or {}).get("last_seen"), "next_review": (r or {}).get("next_review"),
                    "due": due, "prior_hint": hints.get(sid), "recent": [h["score"] for h in hist[-5:]],
                    "levels": level_breakdown(hist), "prereqs": prereqs_of(sid), "dependents": dependents_of(sid)})
    by_id = {s["skill"]: s for s in out}
    for s_ in out:
        s_["blocked_by"] = [p for p in s_["prereqs"] if by_id.get(p) and by_id[p]["mastery_state"] in ("learning", "developing")]
    return out


def readiness() -> Dict:
    """Evidence-based technical readiness: mastery over ASSESSED technical skills, reported with coverage and
    confidence; never a single misleading percentage."""
    sm = [s for s in skill_map() if s["area"] not in ("behavioral", "resume", "deal")]
    assessed = [s for s in sm if s["state"] == "assessed"]
    coverage = len(assessed) / max(len(sm), 1)
    if not assessed:
        return {"status": "not_enough_data", "coverage": 0.0, "assessed": 0, "total": len(sm), "estimate": None, "confidence": 0.0,
                "message": "No technical skills assessed yet."}
    w = sum(s["confidence"] + 0.2 for s in assessed)
    est = sum((s["mastery"] or 0) * (s["confidence"] + 0.2) for s in assessed) / w
    conf = sum(s["confidence"] for s in assessed) / len(assessed)
    states = {}
    for s in sm:
        states[s["mastery_state"]] = states.get(s["mastery_state"], 0) + 1
    status = "not_enough_data" if len(assessed) < 8 or coverage < 0.15 else "estimate"
    return {"status": status, "coverage": round(coverage, 3), "assessed": len(assessed), "total": len(sm), "estimate": round(est, 2),
            "estimate_pct": round(est / 5 * 100), "confidence": round(conf, 2), "states": states,
            "message": ("Estimate based on %d of %d technical skills (%.0f%% coverage); untested skills are excluded, so this is not an overall score." % (len(assessed), len(sm), coverage * 100)) if status == "estimate" else "Not enough data: fewer than 8 technical skills assessed."}


def weaknesses(limit: int = 8) -> List[Dict]:
    sm = [s for s in skill_map() if s["state"] == "assessed"]
    sm.sort(key=lambda s: (s["mastery"] if s["mastery"] is not None else 5, -s["n_obs"]))
    return sm[:limit]


def due_for_review(limit: int = 10) -> List[Dict]:
    sm = [s for s in skill_map() if s["due"]]
    sm.sort(key=lambda s: s["next_review"] or 0)
    return sm[:limit]


def priority_weights() -> Dict[str, float]:
    """Selection weight per skill: higher for weak, due, hinted-weak and unassessed-foundational skills."""
    w: Dict[str, float] = {}
    for s in skill_map():
        base = 1.0
        if s["state"] == "not_assessed":
            base = 1.4 if s["skill"] in FOUNDATIONAL else 1.1
            if s["prior_hint"]:
                base += 0.4
        else:
            m = s["mastery"] if s["mastery"] is not None else 2.5
            base = 0.6 + (5 - m) / 5 * 1.4  # 0.6 (mastered) .. 2.0 (weak)
            if s["due"]:
                base += 0.5
            if s["prior_hint"] and m < 3.5:
                base += 0.2
        w[s["skill"]] = base
    return w


def remediation_plan(limit: int = 5) -> List[Dict]:
    """Specific drills, not 'review accounting'."""
    plan = []
    from app.knowledge.bank import load_bank, by_skill
    bank = load_bank()
    bs = by_skill(bank)
    evals = db.all_evaluations(500)
    for s in weaknesses(limit):
        qs = bs.get(s["skill"], [])
        # the most recent errors on this skill
        errs = [e for e in evals if e.get("skill") == s["skill"] and (e.get("score") or 0) < 0.6]
        detail = None
        for e in errs[:3]:
            d = e.get("data", {})
            if d.get("key_error") or d.get("key_weakness"):
                detail = d.get("key_error") or d.get("key_weakness")
                break
        drill = sorted(qs, key=lambda q: q.difficulty)[:4]
        plan.append({"skill": s["skill"], "name": s["name"], "mastery": s["mastery"], "why": detail or "Recent scores: %s" % s["recent"],
                     "drill": [{"id": q.id, "text": q.text, "difficulty": q.difficulty} for q in drill]})
    return plan


def longitudinal() -> Dict:
    sessions = db.list_sessions(500)
    evals = db.all_evaluations(5000)
    total_time = 0.0
    for s in sessions:
        if s.get("ended") and s.get("created"):
            total_time += max(0.0, s["ended"] - s["created"])
    by_area: Dict[str, List[float]] = {}
    by_week: Dict[str, List[float]] = {}
    lengths = []
    for e in evals:
        sk = e.get("skill") or ""
        if e.get("score") is not None and sk:
            by_area.setdefault(area_of(sk), []).append(e["score"])
            wk = time.strftime("%Y-W%W", time.localtime(e["created"]))
            by_week.setdefault(wk, []).append(e["score"])
        d = e.get("data", {})
        dl = (d.get("delivery") or {}).get("words")
        if dl:
            lengths.append(dl)
    recurring = {}
    for e in evals:
        d = e.get("data", {})
        for m in d.get("misconceptions", []) or []:
            recurring[m["id"]] = recurring.get(m["id"], 0) + 1
    return {
        "sessions": len(sessions), "sessions_completed": sum(1 for s in sessions if s.get("status") == "ended"),
        "practice_hours": round(total_time / 3600, 2), "answers_evaluated": len(evals),
        "accuracy_by_area": {a: round(sum(v) / len(v), 3) for a, v in by_area.items()},
        "weekly_trend": sorted([{"week": k, "avg": round(sum(v) / len(v), 3), "n": len(v)} for k, v in by_week.items()], key=lambda x: x["week"]),
        "avg_answer_words": round(sum(lengths) / len(lengths)) if lengths else None,
        "recurring_misconceptions": sorted(recurring.items(), key=lambda kv: -kv[1])[:8],
        "data_sufficiency": "insufficient" if len(evals) < 15 else ("limited" if len(evals) < 60 else "ok"),
    }
