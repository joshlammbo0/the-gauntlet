"""SQLite persistence. One connection per request; WAL mode; JSON columns for flexible state."""
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("GAUNTLET_DATA", os.path.join(HERE, "..", "data"))
DB_PATH = os.environ.get("GAUNTLET_DB", os.path.join(DATA_DIR, "gauntlet.db"))
AUDIO_DIR = os.path.join(DATA_DIR, "audio")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, mode TEXT NOT NULL, config TEXT NOT NULL, state TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active', created REAL, updated REAL, ended REAL, summary TEXT
);
CREATE TABLE IF NOT EXISTS turns (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, idx INTEGER NOT NULL, role TEXT NOT NULL,
  text TEXT NOT NULL, question_id TEXT, kind TEXT, meta TEXT, created REAL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);
CREATE INDEX IF NOT EXISTS turns_session ON turns(session_id, idx);
CREATE TABLE IF NOT EXISTS evaluations (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, turn_id TEXT NOT NULL, question_id TEXT,
  skill TEXT, score REAL, verdict TEXT, data TEXT NOT NULL, appealed INTEGER DEFAULT 0, created REAL
);
CREATE INDEX IF NOT EXISTS eval_session ON evaluations(session_id);
CREATE TABLE IF NOT EXISTS skills (
  skill TEXT PRIMARY KEY, mastery REAL, confidence REAL, n_obs INTEGER DEFAULT 0, last_seen REAL,
  next_review REAL, interval_days REAL DEFAULT 1, history TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS question_stats (
  question_id TEXT PRIMARY KEY, times_asked INTEGER DEFAULT 0, last_asked REAL, last_score REAL, best_score REAL
);
CREATE TABLE IF NOT EXISTS kb_facts (
  id TEXT PRIMARY KEY, topic TEXT NOT NULL, key TEXT, claim TEXT NOT NULL, source TEXT, status TEXT NOT NULL,
  created REAL, updated REAL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transcripts (
  id TEXT PRIMARY KEY, session_id TEXT, turn_id TEXT, raw TEXT, corrected TEXT, audio_path TEXT,
  duration REAL, model TEXT, created REAL
);
"""


def init() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    with conn() as c:
        c.executescript(SCHEMA)


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def now() -> float:
    return time.time()


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def _row(r: Optional[sqlite3.Row], json_cols=()) -> Optional[Dict]:
    if r is None:
        return None
    d = dict(r)
    for k in json_cols:
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
    return d


# ---------------------------------------------------------------- sessions

def create_session(mode: str, config: Dict, state: Dict) -> str:
    sid = new_id()
    with conn() as c:
        c.execute("INSERT INTO sessions(id,mode,config,state,status,created,updated) VALUES(?,?,?,?,?,?,?)",
                  (sid, mode, json.dumps(config), json.dumps(state), "active", now(), now()))
    return sid


def get_session(sid: str) -> Optional[Dict]:
    with conn() as c:
        return _row(c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone(), ("config", "state", "summary"))


def save_state(sid: str, state: Dict, status: Optional[str] = None, summary: Optional[Dict] = None) -> None:
    with conn() as c:
        if status:
            c.execute("UPDATE sessions SET state=?, status=?, updated=?, ended=COALESCE(ended, CASE WHEN ?='ended' THEN ? END), summary=COALESCE(?, summary) WHERE id=?",
                      (json.dumps(state), status, now(), status, now(), json.dumps(summary) if summary else None, sid))
        else:
            c.execute("UPDATE sessions SET state=?, updated=? WHERE id=?", (json.dumps(state), now(), sid))


def list_sessions(limit: int = 50) -> List[Dict]:
    with conn() as c:
        rows = c.execute("SELECT id, mode, config, status, created, updated, ended, summary FROM sessions ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [_row(r, ("config", "summary")) for r in rows]


def active_sessions(mode: str) -> List[Dict]:
    """Active sessions of one mode, newest first."""
    with conn() as c:
        rows = c.execute("SELECT id, mode, config, status, created FROM sessions WHERE mode=? AND status='active' ORDER BY created DESC", (mode,)).fetchall()
        return [_row(r, ("config",)) for r in rows]


def delete_session(sid: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM evaluations WHERE session_id=?", (sid,))
        c.execute("DELETE FROM turns WHERE session_id=?", (sid,))
        c.execute("DELETE FROM transcripts WHERE session_id=?", (sid,))
        c.execute("DELETE FROM sessions WHERE id=?", (sid,))


# ---------------------------------------------------------------- turns / evals

def add_turn(sid: str, idx: int, role: str, text: str, question_id: Optional[str], kind: str, meta: Optional[Dict] = None) -> str:
    tid = new_id()
    with conn() as c:
        c.execute("INSERT INTO turns(id,session_id,idx,role,text,question_id,kind,meta,created) VALUES(?,?,?,?,?,?,?,?,?)",
                  (tid, sid, idx, role, text, question_id, kind, json.dumps(meta or {}), now()))
    return tid


def update_turn_text(tid: str, text: str, meta_patch: Optional[Dict] = None) -> None:
    with conn() as c:
        row = c.execute("SELECT meta FROM turns WHERE id=?", (tid,)).fetchone()
        meta = json.loads(row["meta"]) if row and row["meta"] else {}
        meta.update(meta_patch or {})
        c.execute("UPDATE turns SET text=?, meta=? WHERE id=?", (text, json.dumps(meta), tid))


def get_turns(sid: str) -> List[Dict]:
    with conn() as c:
        return [_row(r, ("meta",)) for r in c.execute("SELECT * FROM turns WHERE session_id=? ORDER BY idx", (sid,)).fetchall()]


def add_evaluation(sid: str, tid: str, question_id: Optional[str], skill: Optional[str], score: Optional[float], verdict: str, data: Dict) -> str:
    eid = new_id()
    with conn() as c:
        c.execute("INSERT INTO evaluations(id,session_id,turn_id,question_id,skill,score,verdict,data,created) VALUES(?,?,?,?,?,?,?,?,?)",
                  (eid, sid, tid, question_id, skill, score, verdict, json.dumps(data), now()))
    return eid


def update_evaluation(eid: str, data: Dict, score: Optional[float], verdict: str, appealed: int = 1) -> None:
    with conn() as c:
        c.execute("UPDATE evaluations SET data=?, score=?, verdict=?, appealed=? WHERE id=?", (json.dumps(data), score, verdict, appealed, eid))


def get_evaluations(sid: str) -> List[Dict]:
    with conn() as c:
        return [_row(r, ("data",)) for r in c.execute("SELECT * FROM evaluations WHERE session_id=? ORDER BY created", (sid,)).fetchall()]


def get_evaluation(eid: str) -> Optional[Dict]:
    with conn() as c:
        return _row(c.execute("SELECT * FROM evaluations WHERE id=?", (eid,)).fetchone(), ("data",))


def all_evaluations(limit: int = 2000) -> List[Dict]:
    with conn() as c:
        return [_row(r, ("data",)) for r in c.execute("SELECT * FROM evaluations ORDER BY created DESC LIMIT ?", (limit,)).fetchall()]


# ---------------------------------------------------------------- skills / stats

def get_skill(skill: str) -> Optional[Dict]:
    with conn() as c:
        return _row(c.execute("SELECT * FROM skills WHERE skill=?", (skill,)).fetchone(), ("history",))


def all_skills() -> Dict[str, Dict]:
    with conn() as c:
        return {r["skill"]: _row(r, ("history",)) for r in c.execute("SELECT * FROM skills").fetchall()}


def upsert_skill(skill: str, mastery: Optional[float], confidence: float, n_obs: int, next_review: Optional[float], interval_days: float, history: List) -> None:
    with conn() as c:
        c.execute("""INSERT INTO skills(skill,mastery,confidence,n_obs,last_seen,next_review,interval_days,history)
                     VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(skill) DO UPDATE SET mastery=excluded.mastery, confidence=excluded.confidence,
                     n_obs=excluded.n_obs, last_seen=excluded.last_seen, next_review=excluded.next_review, interval_days=excluded.interval_days, history=excluded.history""",
                  (skill, mastery, confidence, n_obs, now(), next_review, interval_days, json.dumps(history[-50:])))


def bump_question(question_id: str, score: Optional[float]) -> None:
    with conn() as c:
        r = c.execute("SELECT * FROM question_stats WHERE question_id=?", (question_id,)).fetchone()
        if r:
            best = max(r["best_score"] or 0, score or 0)
            c.execute("UPDATE question_stats SET times_asked=times_asked+1, last_asked=?, last_score=?, best_score=? WHERE question_id=?", (now(), score, best, question_id))
        else:
            c.execute("INSERT INTO question_stats(question_id,times_asked,last_asked,last_score,best_score) VALUES(?,?,?,?,?)", (question_id, 1, now(), score, score))


def question_stats() -> Dict[str, Dict]:
    with conn() as c:
        return {r["question_id"]: dict(r) for r in c.execute("SELECT * FROM question_stats").fetchall()}


# ---------------------------------------------------------------- KB / settings / transcripts

def kb_list(topic: Optional[str] = None) -> List[Dict]:
    with conn() as c:
        if topic:
            rows = c.execute("SELECT * FROM kb_facts WHERE topic=? ORDER BY created", (topic,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM kb_facts ORDER BY topic, created").fetchall()
        return [dict(r) for r in rows]


def kb_upsert(topic: str, key: Optional[str], claim: str, source: str, status: str, fid: Optional[str] = None) -> str:
    fid = fid or new_id()
    with conn() as c:
        c.execute("""INSERT INTO kb_facts(id,topic,key,claim,source,status,created,updated) VALUES(?,?,?,?,?,?,?,?)
                     ON CONFLICT(id) DO UPDATE SET topic=excluded.topic, key=excluded.key, claim=excluded.claim, source=excluded.source, status=excluded.status, updated=excluded.updated""",
                  (fid, topic, key, claim, source, status, now(), now()))
    return fid


def kb_delete(fid: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM kb_facts WHERE id=?", (fid,))


def get_setting(key: str, default: Any = None) -> Any:
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default


def set_setting(key: str, value: Any) -> None:
    with conn() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))


def all_settings() -> Dict[str, Any]:
    with conn() as c:
        return {r["key"]: json.loads(r["value"]) for r in c.execute("SELECT * FROM settings").fetchall()}


def add_transcript(sid: Optional[str], tid: Optional[str], raw: str, corrected: str, audio_path: Optional[str], duration: Optional[float], model: str) -> str:
    xid = new_id()
    with conn() as c:
        c.execute("INSERT INTO transcripts(id,session_id,turn_id,raw,corrected,audio_path,duration,model,created) VALUES(?,?,?,?,?,?,?,?,?)",
                  (xid, sid, tid, raw, corrected, audio_path, duration, model, now()))
    return xid
