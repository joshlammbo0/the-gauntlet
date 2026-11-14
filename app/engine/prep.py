"""Prep command center: interview contexts (what I'm preparing for), generated prep plans, the Today
feed, full-mock defaults and weakness search. Built only from existing data (curriculum evidence,
BankVault research, resume defense, stories, sessions)."""
import datetime
import json
import re
import time
from typing import Dict, List, Optional

from app import db
from app.engine import curriculum, game
from app.knowledge import banks, sources
from app.knowledge.bank import load_bank
from app.knowledge.skills import SKILLS, area_of, prereqs_of
from app.profile import facts, resume_defense

SCHEMA = """
CREATE TABLE IF NOT EXISTS prep_contexts (
  id TEXT PRIMARY KEY, bank TEXT, bank_name TEXT, sector TEXT, round TEXT, date TEXT, persona TEXT,
  technical_weight REAL, emphasis TEXT NOT NULL DEFAULT '[]', notes TEXT DEFAULT '', include_health_story INTEGER DEFAULT 0,
  created REAL, updated REAL, last_used REAL, archived INTEGER DEFAULT 0
);
"""

ROUNDS = [
    {"key": "screen", "name": "HR / first-round screen", "minutes": 20, "technical_weight": 0.45, "persona": "analyst"},
    {"key": "first_round", "name": "First round", "minutes": 30, "technical_weight": 0.65, "persona": "associate"},
    {"key": "technical", "name": "Technical round", "minutes": 30, "technical_weight": 0.9, "persona": "associate"},
    {"key": "superday", "name": "Superday", "minutes": 45, "technical_weight": 0.7, "persona": "vp"},
    {"key": "final", "name": "Final / MD round", "minutes": 30, "technical_weight": 0.5, "persona": "md"},
    {"key": "coffee", "name": "Coffee chat / networking", "minutes": 15, "technical_weight": 0.2, "persona": "analyst"},
]

SECTOR_SKILLS = {
    "healthcare": ["healthcare.biotech", "healthcare.medtech", "healthcare.services", "healthcare.pharma"],
    "energy": ["energy.reserves", "energy.decline_curves", "energy.pricing", "energy.nav"],
    "power": ["energy.renewables", "energy.project_finance"],
    "fig": ["fig.bank_valuation", "fig.bank_drivers", "fig.rates"],
    "m&a": ["ma.accretion_dilution", "ma.financing", "ma.synergies", "ma.process"],
    "tmt": ["commercial.industry", "valuation.multiples"],
    "industrials": ["commercial.industry", "valuation.comps"],
    "generalist": [],
}
CORE_SKILLS = ["accounting.three_statements", "accounting.depreciation", "valuation.ev_equity", "dcf.ufcf", "dcf.wacc", "dcf.terminal_value", "ma.accretion_dilution", "lbo.basics"]


def init() -> None:
    with db.conn() as c:
        c.executescript(SCHEMA)


def _row(r) -> Optional[Dict]:
    if r is None:
        return None
    d = dict(r)
    d["emphasis"] = json.loads(d.get("emphasis") or "[]")
    d["include_health_story"] = bool(d.get("include_health_story"))
    return d


# ------------------------------------------------------------------ contexts
def list_contexts(include_archived: bool = False) -> List[Dict]:
    init()
    with db.conn() as c:
        rows = c.execute("SELECT * FROM prep_contexts %s ORDER BY COALESCE(date,'9999') ASC, updated DESC" % ("" if include_archived else "WHERE archived=0")).fetchall()
    out = [_row(r) for r in rows]
    today = datetime.date.today().isoformat()
    for o in out:
        o["days_until"] = (datetime.date.fromisoformat(o["date"]) - datetime.date.today()).days if o.get("date") else None
        o["past"] = bool(o.get("date") and o["date"] < today)
    return out


def get_context(cid: str) -> Optional[Dict]:
    init()
    with db.conn() as c:
        o = _row(c.execute("SELECT * FROM prep_contexts WHERE id=?", (cid,)).fetchone())
    if o and o.get("date"):
        o["days_until"] = (datetime.date.fromisoformat(o["date"]) - datetime.date.today()).days
    return o


def save_context(data: Dict, cid: Optional[str] = None) -> Dict:
    init()
    cid = cid or db.new_id()
    bank_slug = data.get("bank") or None
    bank_name = None
    if bank_slug:
        for b in banks.list_banks():
            if b["slug"] == bank_slug:
                bank_name = b["name"]
    rnd = next((r for r in ROUNDS if r["key"] == data.get("round")), ROUNDS[1])
    tw = data.get("technical_weight")
    tw = float(tw) if tw is not None else rnd["technical_weight"]
    with db.conn() as c:
        c.execute("""INSERT INTO prep_contexts(id,bank,bank_name,sector,round,date,persona,technical_weight,emphasis,notes,include_health_story,created,updated)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET bank=excluded.bank, bank_name=excluded.bank_name, sector=excluded.sector,
                     round=excluded.round, date=excluded.date, persona=excluded.persona, technical_weight=excluded.technical_weight, emphasis=excluded.emphasis,
                     notes=excluded.notes, include_health_story=excluded.include_health_story, updated=excluded.updated""",
                  (cid, bank_slug, bank_name, data.get("sector") or None, rnd["key"], data.get("date") or None, data.get("persona") or rnd["persona"], tw,
                   json.dumps(data.get("emphasis") or []), data.get("notes") or "", 1 if data.get("include_health_story") else 0, time.time(), time.time()))
    return get_context(cid)


def archive_context(cid: str) -> None:
    with db.conn() as c:
        c.execute("UPDATE prep_contexts SET archived=1, updated=? WHERE id=?", (time.time(), cid))


def touch_context(cid: str) -> None:
    with db.conn() as c:
        c.execute("UPDATE prep_contexts SET last_used=? WHERE id=?", (time.time(), cid))


def next_context() -> Optional[Dict]:
    """The nearest upcoming context; else the most recently used/updated one."""
    cs = [c for c in list_contexts() if not c["past"]]
    dated = [c for c in cs if c.get("date")]
    if dated:
        return dated[0]
    if cs:
        return sorted(cs, key=lambda c: (c.get("last_used") or 0, c.get("updated") or 0), reverse=True)[0]
    return None


# ------------------------------------------------------------------ plan
def _skill_name(s: str) -> str:
    return SKILLS.get(s, s)


def build_plan(ctx: Dict) -> Dict:
    sm = {s["skill"]: s for s in curriculum.skill_map()}
    sector = (ctx.get("sector") or "generalist").lower()
    bank_ctx = banks.context_for_interview(ctx.get("bank"), None, sector if sector != "generalist" else None) if ctx.get("bank") else {}
    # technical areas: core foundations that are weak/untested + sector skills + explicit emphasis
    tech: List[Dict] = []
    seen = set()

    def add(skill, why):
        if skill in seen or skill not in SKILLS:
            return
        seen.add(skill)
        s = sm.get(skill, {})
        tech.append({"skill": skill, "name": _skill_name(skill), "state": s.get("mastery_state", "untested"), "mastery": s.get("mastery"), "why": why})
    for e in ctx.get("emphasis") or []:
        add(e, "you asked to emphasize it")
    for s in CORE_SKILLS:
        st = sm.get(s, {}).get("mastery_state", "untested")
        if st in ("untested", "learning", "developing", "review_due"):
            add(s, "core technical, currently %s" % st.replace("_", " "))
    for s in SECTOR_SKILLS.get(sector, []):
        add(s, "%s coverage question territory" % sector)
    for w in curriculum.weaknesses(6):
        if area_of(w["skill"]) not in ("behavioral", "resume", "deal"):
            add(w["skill"], "weak on evidence (%s/5)" % w["mastery"])
    tech = tech[:8]
    # bank/group-specific angles from BankVault (verified only)
    bank_angles = []
    if bank_ctx.get("group"):
        g = bank_ctx["group"]
        bank_angles.append({"kind": "group", "text": "Why %s at %s? Expect: %s" % (g.get("name"), bank_ctx.get("name"), (g.get("description") or "")[:220])})
    for d in (bank_ctx.get("deals") or [])[:3]:
        bank_angles.append({"kind": "deal", "text": "%s (%s): %s" % (d.get("name"), d.get("announcedAt"), (d.get("keyDetails") or d.get("rationale") or "")[:200]), "verification": d.get("verificationStatus")})
    why_bank = facts.WHY_BANK_MATERIAL.get(ctx.get("bank") or "", {})
    if why_bank.get("points"):
        bank_angles.append({"kind": "your_notes", "text": "Your own why-this-bank material: " + "; ".join(why_bank["points"][:3])})
    # behavioral stories to pressure-test: verified, non-sensitive unless allowed
    stories = [s for s in facts.STORIES if s.get("status") == facts.VERIFIED and (not s.get("sensitive") or ctx.get("include_health_story"))]
    beh_skills = [s for s in ("behavioral.why_ib", "behavioral.why_bank", "behavioral.tmay") if sm.get(s, {}).get("mastery_state") in ("untested", "learning", "developing", "review_due")]
    # resume bullets to defend: those with unfilled unknowns or discrepancies first
    kb = {f["key"] for f in db.kb_list() if f.get("key")}
    bullets = []
    for b in resume_defense.bullets():
        open_unknowns = [u for u in b["unknowns"] if u["id"] not in kb]
        score = len(open_unknowns) * 2 + len(b["discrepancies"]) * 3 + (2 if b["experience_id"] in ("hobo", "gadif", "gci") else 0)
        bullets.append({"id": b["id"], "org": b["org"], "text": b["text"][:140], "open_unknowns": len(open_unknowns), "discrepancies": len(b["discrepancies"]), "score": score})
    bullets.sort(key=lambda x: -x["score"])
    # deal defense picks
    bank_q = load_bank()
    deals = [{"id": q.id, "text": q.text} for q in bank_q.values() if q.skill in ("deal.thesis", "deal.transaction")][:5]
    rnd = next((r for r in ROUNDS if r["key"] == ctx.get("round")), ROUNDS[1])
    return {
        "context": ctx, "round": rnd, "bank_context": {k: bank_ctx.get(k) for k in ("name", "group", "deals")} if bank_ctx else None,
        "technical": tech, "bank_angles": bank_angles, "behavioral": {"skills": [{"skill": s, "name": _skill_name(s)} for s in beh_skills], "stories": [{"id": s["id"], "title": s["title"], "categories": s["categories"]} for s in stories[:6]]},
        "resume_bullets": bullets[:5], "deal_defense": deals,
        "options": [
            {"key": "quick10", "label": "10-minute targeted drill", "minutes": 10, "desc": "Weakness Lab on the two weakest plan skills; instant feedback."},
            {"key": "mix25", "label": "25-minute recommended prep", "minutes": 25, "desc": "Bank-tuned interview: %d%% technical, %s persona, resume questions on, scores hidden." % (round(rnd["technical_weight"] * 100), rnd["persona"])},
            {"key": "full", "label": "Full mock (%d min)" % rnd["minutes"], "minutes": rnd["minutes"], "desc": "The round as it would run, with this bank's research and your persona choice."},
        ],
    }


def session_config_for(ctx: Dict, option: str) -> Dict:
    """Translate a context + option into (mode, config) for controller.Interview.create."""
    plan = build_plan(ctx)
    rnd = plan["round"]
    tw = float(ctx.get("technical_weight") if ctx.get("technical_weight") is not None else rnd["technical_weight"])
    base = {"bank": ctx.get("bank"), "sector": ctx.get("sector"), "persona": ctx.get("persona") or rnd["persona"], "context_id": ctx["id"],
            "include_health_story": bool(ctx.get("include_health_story")), "resume_questions": True, "use_sources": True}
    if option == "quick10":
        focus = [t["skill"] for t in plan["technical"][:3]] or CORE_SKILLS[:2]
        return "weakness_lab", {**base, "duration_min": 10, "max_questions": 6, "focus_skills": focus, "skill": focus[0]}
    if option == "mix25":
        cats = sorted({area_of(t["skill"]) for t in plan["technical"] if area_of(t["skill"]) not in ("math", "behavioral", "resume", "deal")})
        mode = "bank_specific" if ctx.get("bank") else "superday"
        return mode, {**base, "duration_min": 25, "difficulty": "medium", "technical_weight": tw, "categories": cats[:6]}
    mode = "bank_specific" if ctx.get("bank") else "superday"
    return mode, {**base, "duration_min": rnd["minutes"], "difficulty": "hard" if rnd["key"] in ("superday", "final") else "medium", "technical_weight": tw}


# ------------------------------------------------------------------ mock defaults
MOCK_FALLBACK = {"mode": "superday", "persona": "vp", "duration_min": 30, "difficulty": "medium", "technical_weight": 0.7, "resume_questions": True, "bank": None, "sector": None}


def mock_defaults() -> Dict:
    ctx = next_context()
    last = db.get_setting("last_mock_config")
    if ctx:
        mode, cfg = session_config_for(ctx, "full")
        return {"source": "context", "context": ctx, "mode": mode, "config": cfg}
    if last:
        cfg = dict(last)
        mode = cfg.pop("mode", "superday")
        return {"source": "last", "context": None, "mode": mode, "config": cfg}
    cfg = dict(MOCK_FALLBACK)
    mode = cfg.pop("mode")
    return {"source": "default", "context": None, "mode": mode, "config": cfg}


def remember_mock(mode: str, cfg: Dict) -> None:
    keep = {k: cfg.get(k) for k in ("persona", "duration_min", "difficulty", "technical_weight", "resume_questions", "bank", "sector", "categories", "include_health_story") if k in cfg}
    keep["mode"] = mode
    db.set_setting("last_mock_config", keep)


# ------------------------------------------------------------------ today feed
def today_feed() -> Dict:
    game.init()
    sessions = db.list_sessions(30)
    active = next((s for s in sessions if s["status"] == "active"), None)
    last_done = next((s for s in sessions if s["status"] == "ended" and (s.get("summary") or {}).get("avg") is not None), None)
    daily = game.daily_status()
    rd = curriculum.readiness()
    due = [s for s in curriculum.due_for_review(8) if area_of(s["skill"]) not in ("behavioral", "resume", "deal")][:3]
    weak = [w for w in curriculum.weaknesses(10) if area_of(w["skill"]) not in ("behavioral", "resume", "deal")][:2]
    sm = {s["skill"]: s for s in curriculum.skill_map()}
    untested_core = [s for s in CORE_SKILLS if sm.get(s, {}).get("mastery_state") == "untested"][:2]
    ctx = next_context()
    recent_misses = recently_missed(5)
    queue: List[Dict] = []
    if active:
        queue.append({"kind": "resume", "title": "Resume: %s" % game_mode_name(active["mode"]), "detail": "Started %s; state saved after every turn." % _ago(active["created"]), "action": {"type": "session", "id": active["id"]}, "priority": 0})
    if not daily["completed"]:
        queue.append({"kind": "daily", "title": "Quick Practice (Daily Draft)", "detail": "5–10 minutes on due reviews and weak spots. Streak %d." % daily["streak"], "action": {"type": "daily"}, "priority": 1})
    for d in due:
        queue.append({"kind": "review", "title": "Review due: %s" % d["name"], "detail": "Last at %s/5; spaced review is due." % d["mastery"], "action": {"type": "fix", "skill": d["skill"]}, "priority": 2})
    for w in weak:
        queue.append({"kind": "weak", "title": "Weak: %s" % w["name"], "detail": "%s at %s/5 on %d answers." % (w["mastery_state"].replace("_", " "), w["mastery"], w["n_obs"]), "action": {"type": "fix", "skill": w["skill"]}, "priority": 3})
    for s in untested_core:
        queue.append({"kind": "untested", "title": "Untested foundation: %s" % _skill_name(s), "detail": "No evidence yet; it underpins %d other skills." % len([k for k, v in __import__('app.knowledge.skills', fromlist=['PREREQS']).PREREQS.items() if s in v]), "action": {"type": "fix", "skill": s}, "priority": 4})
    if ctx:
        when = ("in %d day(s)" % ctx["days_until"]) if ctx.get("days_until") is not None else "undated"
        queue.append({"kind": "context", "title": "Prepare: %s %s" % (ctx.get("bank_name") or ctx.get("bank") or "interview", _round_name(ctx.get("round"))), "detail": "%s. Recommended 25-minute prep available." % when, "action": {"type": "prepare", "id": ctx["id"]}, "priority": 1 if (ctx.get("days_until") is not None and ctx["days_until"] <= 7) else 5})
    queue.sort(key=lambda q: q["priority"])
    return {
        "active_session": active and {"id": active["id"], "mode": active["mode"], "mode_name": game_mode_name(active["mode"]), "created": active["created"]},
        "daily": daily, "readiness": rd, "next_context": ctx, "queue": queue[:6], "recent_misses": recent_misses,
        "last_session": last_done and {"id": last_done["id"], "mode": last_done["mode"], "mode_name": game_mode_name(last_done["mode"]), "avg": last_done["summary"].get("avg"), "n": last_done["summary"].get("n"), "ended": last_done.get("ended")},
        "trend": curriculum.longitudinal()["weekly_trend"][-6:], "xp": game.level_for(game.total_xp()),
        "top_weakness": weak[0] if weak else None, "mock": mock_defaults(),
    }


def game_mode_name(mode: str) -> str:
    from app.engine import controller
    return controller.MODES.get(mode, {}).get("name", mode)


def _round_name(key: Optional[str]) -> str:
    return next((r["name"] for r in ROUNDS if r["key"] == key), key or "")


def _ago(t: float) -> str:
    d = time.time() - (t or time.time())
    if d < 3600:
        return "%d min ago" % (d // 60)
    if d < 86400:
        return "%d h ago" % (d // 3600)
    return "%d day(s) ago" % (d // 86400)


# ------------------------------------------------------------------ weakness search
def recently_missed(limit: int = 8) -> List[Dict]:
    evals = db.all_evaluations(300)
    out = []
    seen = set()
    for e in evals:
        if (e.get("score") or 0) >= 0.6 or not e.get("skill") or e["skill"] in seen:
            continue
        if area_of(e["skill"]) in ("behavioral", "resume", "deal"):
            continue
        d = e.get("data", {})
        seen.add(e["skill"])
        out.append({"skill": e["skill"], "name": _skill_name(e["skill"]), "score": e["score"], "when": e["created"], "key": d.get("key_error") or d.get("key_weakness"), "question_id": e.get("question_id"), "evaluation_id": e["id"]})
        if len(out) >= limit:
            break
    return out


def search_weakness(q: str, limit: int = 12) -> List[Dict]:
    """Match skills by name/id, then by question text (authored + guide) mapping back to skills."""
    ql = (q or "").lower().strip()
    sm = {s["skill"]: s for s in curriculum.skill_map()}
    hits: Dict[str, Dict] = {}
    if ql:
        for sid, name in SKILLS.items():
            if ql in name.lower() or ql in sid.lower() or any(ql in w for w in re.split(r"[\s/,()]+", name.lower())):
                hits[sid] = {"match": "skill"}
        if len(hits) < limit:
            for qq in load_bank().values():
                if qq.kind == "technical" and ql in qq.text.lower() and qq.skill not in hits:
                    hits[qq.skill] = {"match": "question: " + qq.text[:90]}
            for r in sources.all_records():
                if len(hits) >= limit:
                    break
                if ql in r["question"].lower() and r["skill"] not in hits:
                    hits[r["skill"]] = {"match": "guide: " + r["question"][:90]}
    out = []
    for sid, h in hits.items():
        s = sm.get(sid, {})
        out.append({"skill": sid, "name": _skill_name(sid), "area": area_of(sid), "state": s.get("mastery_state", "untested"), "mastery": s.get("mastery"), "n_obs": s.get("n_obs", 0),
                    "prereqs": [{"skill": p, "name": _skill_name(p)} for p in prereqs_of(sid)], **h})
    order = {"learning": 0, "developing": 1, "review_due": 2, "untested": 3, "proficient": 4, "mastered": 5}
    out.sort(key=lambda x: (0 if x["match"] == "skill" else 1, order.get(x["state"], 9)))
    return out[:limit]


def weakness_actions(skill: str) -> Dict:
    """Why it's weak, root cause, evidence, time, and the four actions with launch configs."""
    from app.engine import lab
    d = lab.diagnose(skill)
    sm = {s["skill"]: s for s in curriculum.skill_map()}
    s = sm.get(skill, {})
    evals = [e for e in db.all_evaluations(500) if e.get("skill") == skill][:8]
    evidence = [{"when": e["created"], "score": e["score"], "verdict": e["verdict"], "question_id": e["question_id"], "session_id": e["session_id"], "key": (e.get("data") or {}).get("key_error") or (e.get("data") or {}).get("key_weakness")} for e in evals]
    misses = [e for e in evidence if (e["score"] or 0) < 0.6]
    why = "No evidence yet." if not evidence else ("Missed %d of the last %d answers%s." % (len(misses), len(evidence), ("; most recent issue: " + (misses[0]["key"] or "")[:120]) if misses and misses[0]["key"] else ""))
    minutes = 10 if s.get("mastery_state") in ("review_due", "proficient") else 20
    return {"skill": skill, "name": _skill_name(skill), "state": s.get("mastery_state", "untested"), "mastery": s.get("mastery"), "n_obs": s.get("n_obs", 0),
            "why": why, "root_cause": d["root_cause"], "root_name": d["root_name"], "advice": d["advice"], "weak_prerequisites": d["weak_prerequisites"], "weakest_level": d["weakest_level"],
            "evidence": evidence, "minutes": minutes,
            "actions": [
                {"key": "teach", "label": "Teach me", "desc": "Layered explanation with worked numbers and cited guide excerpts.", "route": "#/teach/%s" % skill},
                {"key": "practice", "label": "Practice (lab)", "desc": "Socratic drill with instant feedback, starting at the root cause.", "mode": "weakness_lab", "config": {"skill": d["root_cause"] if d["root_cause"] != skill else skill, "focus_skills": list(dict.fromkeys([d["root_cause"], skill])), "duration_min": minutes}},
                {"key": "pressure", "label": "Pressure-test", "desc": "Hot Seat on this skill only; scores hidden until the end.", "mode": "hot_seat", "config": {"duration_min": 15, "max_questions": 6, "categories": [area_of(skill)], "focus_skills": [skill], "technical_weight": 1.0, "resume_questions": False}},
                {"key": "retest", "label": "Re-test with fresh numbers", "desc": "New questions on this skill at the next level up; live scoring.", "mode": "explain", "config": {"skill": skill, "duration_min": 10, "max_questions": 4, "persona": "associate"}},
            ]}
