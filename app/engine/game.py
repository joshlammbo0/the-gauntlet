"""Game engine: Career Mode campaigns, Deathmatch runs, Daily Draft, XP, levels, achievements.

Career XP and technical mastery are independent: XP rewards effort and milestones with diminishing
returns for farming; mastery (curriculum.py) only moves on evidence. All state lives in SQLite tables
created here (additive migration; nothing existing is touched).
"""
import datetime
import json
import math
import time
from typing import Dict, List, Optional

from app import db
from app.engine import curriculum
from app.knowledge import banks

SCHEMA = """
CREATE TABLE IF NOT EXISTS game_profile (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS xp_log (id TEXT PRIMARY KEY, amount INTEGER, reason TEXT, session_id TEXT, created REAL);
CREATE TABLE IF NOT EXISTS achievements (key TEXT PRIMARY KEY, unlocked REAL, evidence TEXT);
CREATE TABLE IF NOT EXISTS campaigns (
  bank TEXT PRIMARY KEY, stage INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0, passed INTEGER DEFAULT 0, offer REAL,
  history TEXT NOT NULL DEFAULT '[]', updated REAL
);
CREATE TABLE IF NOT EXISTS deathmatch_runs (id TEXT PRIMARY KEY, session_id TEXT, score INTEGER, questions INTEGER, best_streak INTEGER, max_level REAL, ended REAL);
CREATE TABLE IF NOT EXISTS daily (date TEXT PRIMARY KEY, session_id TEXT, completed REAL, score REAL, n INTEGER);
"""

STAGES = [
    {"key": "screening", "name": "Screening", "minutes": 10, "max_questions": 6, "persona": "analyst", "difficulty": "easy", "technical_weight": 0.5, "pass": 0.55},
    {"key": "first_round", "name": "First Round", "minutes": 15, "max_questions": 8, "persona": "analyst", "difficulty": "medium", "technical_weight": 0.7, "pass": 0.6},
    {"key": "technical", "name": "Technical Interview", "minutes": 20, "max_questions": 10, "persona": "associate", "difficulty": "medium", "technical_weight": 0.95, "pass": 0.65},
    {"key": "superday", "name": "Superday", "minutes": 30, "max_questions": 14, "persona": "vp", "difficulty": "hard", "technical_weight": 0.85, "pass": 0.65, "boss": True},
    {"key": "final", "name": "Final Interview", "minutes": 20, "max_questions": 10, "persona": "md", "difficulty": "hard", "technical_weight": 0.7, "pass": 0.7, "boss": True},
]
OFFER_STAGE = len(STAGES)

CAREER_BANKS = ["jp-morgan", "goldman-sachs", "morgan-stanley", "bank-of-america-securities", "citi", "barclays", "ubs", "evercore",
                "centerview-partners", "lazard", "moelis-and-company", "perella-weinberg-partners", "guggenheim-securities", "wells-fargo-securities",
                "houlihan-lokey", "jefferies", "pjt-partners", "rothschild-and-co"]

DISCLAIMER = ("Career Mode is a simulated training circuit. Bank names are used to make practice feel real; the stages, interviewers "
              "and offers are fictional, are not affiliated with or endorsed by any firm, and say nothing about any bank's actual process or difficulty.")

LEVELS = [(0, "Prospect"), (300, "Summer Candidate"), (900, "First-Round Regular"), (2000, "Superday Veteran"), (4000, "Offer Holder"), (7500, "Analyst"), (12000, "Senior Analyst"), (20000, "Associate")]

ACHIEVEMENTS = {
    "perfect_round": {"name": "Perfect Round", "desc": "Finish an interview of 6+ scored answers with no answer below 0.75."},
    "deep_thinker": {"name": "Deep Thinker", "desc": "Answer three level-4+ technical questions correctly in one session."},
    "comeback": {"name": "Comeback", "desc": "Score 0.75+ on a skill that was 'learning' or 'developing' after an earlier miss."},
    "iron_analyst": {"name": "Iron Analyst", "desc": "Survive 20+ questions in a single Deathmatch run."},
    "full_coverage": {"name": "Full Coverage", "desc": "Reach proficient or better in every core technical area (accounting, valuation, DCF, M&A, LBO)."},
    "superday_survivor": {"name": "Superday Survivor", "desc": "Pass a Career Mode Superday."},
    "the_400_challenge": {"name": "The 400 Challenge", "desc": "Answer 100 distinct M&I 400 questions at 0.75+."},
    "first_offer": {"name": "First Offer", "desc": "Earn a fictional Summer Analyst offer in Career Mode."},
    "streak_7": {"name": "Seven Straight", "desc": "Complete the Daily Draft seven days in a row."},
    "callback_king": {"name": "Consistent", "desc": "Succeed on five interviewer callbacks."},
}


def init() -> None:
    with db.conn() as c:
        c.executescript(SCHEMA)


def _get(key, default):
    with db.conn() as c:
        r = c.execute("SELECT value FROM game_profile WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default


def _set(key, value):
    with db.conn() as c:
        c.execute("INSERT INTO game_profile(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))


# ------------------------------------------------------------------ XP
def total_xp() -> int:
    with db.conn() as c:
        r = c.execute("SELECT COALESCE(SUM(amount),0) AS s FROM xp_log").fetchone()
        return int(r["s"])


def level_for(xp: int) -> Dict:
    cur = LEVELS[0]
    nxt = None
    for i, (thr, name) in enumerate(LEVELS):
        if xp >= thr:
            cur = (thr, name)
            nxt = LEVELS[i + 1] if i + 1 < len(LEVELS) else None
    return {"level": LEVELS.index(cur) + 1, "name": cur[1], "xp": xp, "next_at": nxt[0] if nxt else None, "next_name": nxt[1] if nxt else None,
            "progress": round((xp - cur[0]) / (nxt[0] - cur[0]), 3) if nxt else 1.0}


def award_xp(amount: int, reason: str, session_id: Optional[str] = None) -> int:
    if amount <= 0:
        return 0
    with db.conn() as c:
        c.execute("INSERT INTO xp_log(id,amount,reason,session_id,created) VALUES(?,?,?,?,?)", (db.new_id(), int(amount), reason, session_id, time.time()))
    return int(amount)


def xp_reason_count(prefix: str, since: Optional[float] = None) -> int:
    """How many XP awards have a reason starting with `prefix` (optionally since a timestamp)."""
    with db.conn() as c:
        if since is None:
            r = c.execute("SELECT COUNT(*) AS n FROM xp_log WHERE reason LIKE ?", (prefix + "%",)).fetchone()
        else:
            r = c.execute("SELECT COUNT(*) AS n FROM xp_log WHERE reason LIKE ? AND created >= ?", (prefix + "%", since)).fetchone()
    return int(r["n"])


def modeling_xp(name: str, seed: int, score: float) -> int:
    """A given challenge instance (name + seed) pays once; fresh instances of the same challenge pay less within a day."""
    if xp_reason_count("modeling:%s:%s" % (name, seed)):
        return 0
    recent = xp_reason_count("modeling:%s:" % name, since=time.time() - 86400)
    return int(round((20 + 60 * score) * max(0.1, 0.5 ** recent)))


def xp_for_answer(score: float, level: int, question_id: str, kind: str) -> int:
    """Effort + difficulty, with diminishing returns for repeats of the same question (farming)."""
    if score is None:
        return 0
    base = 4 + 3 * max(1, min(5, level))
    mult = 1.0 if score >= 0.75 else (0.5 if score >= 0.5 else 0.15)
    st = db.question_stats().get(question_id, {})
    times = st.get("times_asked", 0)
    farm = 1.0 if times <= 1 else max(0.1, 0.5 ** (times - 1))
    if kind == "numeric":
        base = 8
    return int(round(base * mult * farm))


# ------------------------------------------------------------------ achievements
def unlocked() -> Dict[str, Dict]:
    with db.conn() as c:
        return {r["key"]: dict(r) for r in c.execute("SELECT * FROM achievements").fetchall()}


def unlock(key: str, evidence: str) -> bool:
    if key not in ACHIEVEMENTS or key in unlocked():
        return False
    with db.conn() as c:
        c.execute("INSERT INTO achievements(key,unlocked,evidence) VALUES(?,?,?)", (key, time.time(), evidence[:300]))
    award_xp(150, "achievement:" + key)
    return True


def check_achievements_after_session(session_id: str) -> List[str]:
    s = db.get_session(session_id)
    if not s:
        return []
    evals = [e for e in s["state"].get("evals", []) if e.get("score") is not None and e.get("verdict") != "skipped"]
    newly = []
    if len(evals) >= 6 and all(e["score"] >= 0.75 for e in evals):
        if unlock("perfect_round", "session %s: %d answers all ≥0.75" % (session_id, len(evals))):
            newly.append("perfect_round")
    hard_ok = [e for e in evals if e.get("score", 0) >= 0.75 and e.get("kind") in ("technical", "numeric") and (db.get_evaluation(e["evaluation_id"]) or {}).get("data", {}).get("level", 0) >= 4]
    if len(hard_ok) >= 3 and unlock("deep_thinker", "session %s" % session_id):
        newly.append("deep_thinker")
    cbs = [c for c in s["state"].get("callbacks", []) if c.get("success")]
    total_cb = _get("callback_successes", 0) + len(cbs)
    _set("callback_successes", total_cb)
    if total_cb >= 5 and unlock("callback_king", "%d successful callbacks" % total_cb):
        newly.append("callback_king")
    # comeback: a skill that had a miss earlier and now ≥0.75
    for sk in {e["skill"] for e in evals if e.get("score", 0) >= 0.75}:
        row = db.get_skill(sk)
        hist = (row or {}).get("history") or []
        if len(hist) >= 3 and any(h["score"] < 0.4 for h in hist[:-1]) and hist[-1]["score"] >= 0.75:
            if unlock("comeback", "skill %s" % sk):
                newly.append("comeback")
            break
    sm = {x["skill"]: x for x in curriculum.skill_map()}
    core = ["accounting", "valuation", "dcf", "ma", "lbo"]
    if all(any(x["mastery_state"] in ("proficient", "mastered") for x in sm.values() if x["area"] == a) for a in core):
        if unlock("full_coverage", "proficient in all five core areas"):
            newly.append("full_coverage")
    # 400 challenge: distinct M&I questions ≥0.75
    with db.conn() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM question_stats WHERE question_id LIKE 'src_mi400%' AND best_score >= 0.75").fetchone()["n"]
    if n >= 100 and unlock("the_400_challenge", "%d M&I questions at ≥0.75" % n):
        newly.append("the_400_challenge")
    return newly


# ------------------------------------------------------------------ career
def campaigns() -> List[Dict]:
    with db.conn() as c:
        rows = {r["bank"]: dict(r) for r in c.execute("SELECT * FROM campaigns").fetchall()}
    out = []
    names = {b["slug"]: b["name"] for b in banks.list_banks()}
    for slug in CAREER_BANKS:
        r = rows.get(slug, {"bank": slug, "stage": 0, "attempts": 0, "passed": 0, "offer": None, "history": "[]"})
        hist = json.loads(r["history"]) if isinstance(r.get("history"), str) else (r.get("history") or [])
        stage = r["stage"]
        out.append({"bank": slug, "name": names.get(slug, slug.replace("-", " ").title()), "stage": stage, "stage_name": STAGES[stage]["name"] if stage < OFFER_STAGE else "Offer",
                    "offer": r.get("offer"), "attempts": r["attempts"], "passed": r["passed"], "history": hist[-10:], "research": banks.bank(slug) is not None,
                    "next": STAGES[stage] if stage < OFFER_STAGE else None})
    return out


def campaign(slug: str) -> Dict:
    for c in campaigns():
        if c["bank"] == slug:
            return c
    raise KeyError(slug)


def stage_config(slug: str, sector: Optional[str] = None) -> Dict:
    c = campaign(slug)
    if c["stage"] >= OFFER_STAGE:
        raise ValueError("offer already earned; replay any stage from history instead")
    st = STAGES[c["stage"]]
    # difficulty scales with demonstrated mastery, not with the bank's name
    rd = curriculum.readiness()
    diff = st["difficulty"]
    if rd.get("status") == "estimate" and rd.get("estimate", 0) >= 3.75 and diff != "brutal":
        diff = {"easy": "medium", "medium": "hard", "hard": "brutal"}[diff]
    return {"bank": slug, "sector": sector, "persona": st["persona"], "difficulty": diff, "duration_min": st["minutes"], "max_questions": st["max_questions"],
            "technical_weight": st["technical_weight"], "career": {"bank": slug, "stage": c["stage"], "stage_key": st["key"], "pass": st["pass"], "boss": st.get("boss", False)},
            "use_sources": True, "callback_prob": 0.7 if st.get("boss") else 0.5}


def resolve_career_session(session_id: str) -> Optional[Dict]:
    s = db.get_session(session_id)
    if not s or not (s["config"].get("career")):
        return None
    car = s["config"]["career"]
    evals = [e for e in s["state"].get("evals", []) if e.get("score") is not None]
    if not evals:
        return None
    avg = sum(e["score"] for e in evals) / len(evals)
    tech = [e for e in evals if e.get("kind") in ("technical", "numeric")]
    tech_avg = sum(e["score"] for e in tech) / len(tech) if tech else avg
    passed = avg >= car["pass"] and tech_avg >= car["pass"] - 0.05 and len(evals) >= 3
    with db.conn() as c:
        row = c.execute("SELECT * FROM campaigns WHERE bank=?", (car["bank"],)).fetchone()
        hist = json.loads(row["history"]) if row else []
        stage = row["stage"] if row else 0
        hist.append({"session_id": session_id, "stage": car["stage"], "stage_key": car["stage_key"], "score": round(avg, 3), "tech": round(tech_avg, 3), "passed": passed, "t": time.time()})
        if passed and car["stage"] == stage:
            stage += 1
        offer = time.time() if stage >= OFFER_STAGE and not (row and row["offer"]) else (row["offer"] if row else None)
        c.execute("""INSERT INTO campaigns(bank,stage,attempts,passed,offer,history,updated) VALUES(?,?,?,?,?,?,?)
                     ON CONFLICT(bank) DO UPDATE SET stage=excluded.stage, attempts=excluded.attempts, passed=excluded.passed, offer=excluded.offer, history=excluded.history, updated=excluded.updated""",
                  (car["bank"], stage, (row["attempts"] if row else 0) + 1, (row["passed"] if row else 0) + (1 if passed else 0), offer, json.dumps(hist[-50:]), time.time()))
    xp = award_xp(120 if passed else 40, "career:%s:%s:%s" % (car["bank"], car["stage_key"], "pass" if passed else "fail"), session_id)
    newly = []
    if passed and car["stage_key"] == "superday" and unlock("superday_survivor", "%s superday %.2f" % (car["bank"], avg)):
        newly.append("superday_survivor")
    if offer and stage >= OFFER_STAGE and unlock("first_offer", car["bank"]):
        newly.append("first_offer")
    return {"bank": car["bank"], "stage": car["stage"], "stage_key": car["stage_key"], "score": round(avg, 3), "technical": round(tech_avg, 3), "pass_mark": car["pass"],
            "passed": passed, "new_stage": stage, "offer": bool(offer and stage >= OFFER_STAGE), "xp": xp, "achievements": newly}


# ------------------------------------------------------------------ deathmatch
def deathmatch_config(categories: Optional[List[str]] = None) -> Dict:
    return {"persona": "associate", "difficulty": "medium", "duration_min": 30, "max_questions": 60, "categories": categories or [],
            "deathmatch": {"lives": 3, "streak": 0, "best_streak": 0, "score": 0, "questions": 0, "ladder": 1.5}, "use_sources": True}


def deathmatch_update(state_cfg: Dict, score: Optional[float], level: int, interrupted: bool = False) -> Dict:
    """Apply one answer to the run. Returns the updated deathmatch block (also mutated in place)."""
    dm = state_cfg
    dm["questions"] += 1
    if score is None or score < 0.5:
        dm["lives"] -= 1
        dm["streak"] = 0
    else:
        dm["streak"] += 1
        dm["best_streak"] = max(dm["best_streak"], dm["streak"])
        mult = 1.0 + min(1.0, 0.1 * (dm["streak"] - 1))  # streak multiplier up to 2x
        pts = int(round((10 + 6 * max(1, level)) * (1.0 if score >= 0.75 else 0.5) * mult))
        if dm.get("boss_pending"):
            pts *= 2
        dm["score"] += pts
    dm["ladder"] = min(6.0, 1.5 + 0.25 * dm["questions"] + 0.1 * dm["streak"])
    dm["boss_pending"] = (dm["questions"] % 5 == 4)  # every fifth question is a boss (level 4+)
    dm["alive"] = dm["lives"] > 0
    return dm


def deathmatch_finish(session_id: str, dm: Dict) -> Dict:
    with db.conn() as c:
        c.execute("INSERT OR REPLACE INTO deathmatch_runs(id,session_id,score,questions,best_streak,max_level,ended) VALUES(?,?,?,?,?,?,?)",
                  (db.new_id(), session_id, dm["score"], dm["questions"], dm["best_streak"], dm["ladder"], time.time()))
    award_xp(min(400, dm["score"] // 4), "deathmatch:%d" % dm["score"], session_id)
    newly = []
    if dm["questions"] >= 20 and unlock("iron_analyst", "%d questions, %d pts" % (dm["questions"], dm["score"])):
        newly.append("iron_analyst")
    return {"score": dm["score"], "questions": dm["questions"], "best_streak": dm["best_streak"], "records": deathmatch_records(), "achievements": newly}


def deathmatch_records() -> Dict:
    with db.conn() as c:
        best = c.execute("SELECT MAX(score) AS s, MAX(questions) AS q, MAX(best_streak) AS st, COUNT(*) AS n FROM deathmatch_runs").fetchone()
        recent = [dict(r) for r in c.execute("SELECT score,questions,best_streak,ended FROM deathmatch_runs ORDER BY ended DESC LIMIT 10").fetchall()]
    return {"best_score": best["s"] or 0, "best_questions": best["q"] or 0, "best_streak": best["st"] or 0, "runs": best["n"], "recent": recent}


# ------------------------------------------------------------------ daily draft
def today() -> str:
    return datetime.date.today().isoformat()


def daily_status() -> Dict:
    d = today()
    with db.conn() as c:
        row = c.execute("SELECT * FROM daily WHERE date=?", (d,)).fetchone()
        rows = [r["date"] for r in c.execute("SELECT date FROM daily WHERE completed IS NOT NULL ORDER BY date DESC").fetchall()]
    streak = 0
    cur = datetime.date.today()
    dates = set(rows)
    # today counts if done; otherwise streak counts up to yesterday
    if d not in dates:
        cur = cur - datetime.timedelta(days=1)
    while cur.isoformat() in dates:
        streak += 1
        cur -= datetime.timedelta(days=1)
    return {"date": d, "completed": bool(row and row["completed"]), "session_id": row["session_id"] if row else None, "score": row["score"] if row else None, "streak": streak, "total_days": len(dates)}


def daily_config() -> Dict:
    """5–10 minutes: due reviews, weak skills, untested high-priority skills, plus one or two surprises."""
    tech = lambda sk: sk.split(".")[0] not in ("behavioral", "resume", "deal")  # noqa: E731
    due = [s["skill"] for s in curriculum.due_for_review(6) if tech(s["skill"])][:3]
    weak = [s["skill"] for s in curriculum.weaknesses(8) if tech(s["skill"])][:3]
    untested = [s["skill"] for s in curriculum.skill_map() if s["state"] == "not_assessed" and s["skill"] in curriculum.FOUNDATIONAL][:2]
    focus = []
    for sk in due + weak + untested:
        if sk not in focus:
            focus.append(sk)
    return {"persona": "associate", "difficulty": "medium", "duration_min": 10, "max_questions": 8, "daily": {"date": today(), "focus_skills": focus[:6]},
            "focus_skills": focus[:6], "use_sources": True, "surprise": 2}


def daily_start(session_id: str) -> None:
    with db.conn() as c:
        c.execute("INSERT INTO daily(date,session_id) VALUES(?,?) ON CONFLICT(date) DO UPDATE SET session_id=excluded.session_id", (today(), session_id))


def daily_finish(session_id: str) -> Optional[Dict]:
    s = db.get_session(session_id)
    if not s or not s["config"].get("daily"):
        return None
    evals = [e for e in s["state"].get("evals", []) if e.get("score") is not None]
    avg = sum(e["score"] for e in evals) / len(evals) if evals else None
    d = s["config"]["daily"]["date"]
    with db.conn() as c:
        c.execute("INSERT INTO daily(date,session_id,completed,score,n) VALUES(?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET completed=excluded.completed, score=excluded.score, n=excluded.n, session_id=excluded.session_id",
                  (d, session_id, time.time(), avg, len(evals)))
    award_xp(60, "daily:%s" % d, session_id)
    st = daily_status()
    newly = []
    if st["streak"] >= 7 and unlock("streak_7", "%d-day streak" % st["streak"]):
        newly.append("streak_7")
    return {"date": d, "score": avg, "n": len(evals), "streak": st["streak"], "achievements": newly}


# ------------------------------------------------------------------ dashboard
def summary() -> Dict:
    xp = total_xp()
    camps = campaigns()
    return {"xp": level_for(xp), "achievements": {k: {**v, "unlocked": unlocked().get(k)} for k, v in ACHIEVEMENTS.items()},
            "daily": daily_status(), "deathmatch": deathmatch_records(),
            "career": {"offers": [c for c in camps if c["offer"]], "active": [c for c in camps if c["stage"] > 0 and not c["offer"]], "disclaimer": DISCLAIMER,
                       "banks": camps}}
