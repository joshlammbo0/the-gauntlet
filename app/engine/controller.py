"""Interview session controller: the state machine behind every mode.

State (persisted as JSON after every turn, so a refresh resumes exactly):
  phase: opening | main | probing | closing | ended
  current: the active question dict (from selector) or None
  root_question: the main question the current probe chain hangs off
  followup_depth: how deep the current chain is
  asked: question ids asked (main + chained)
  evals: compact evaluation summaries in order
  claims: claim registry; contradictions: detected contradictions
  weaknesses: skills with low scores this session
  started_at, paused_total, last_resume_at, duration_min
  ladder: difficulty for death-match
"""
import random
import threading
import time
from typing import Dict, List, Optional

from app import db
from app.knowledge.bank import load_bank, Question
from app.knowledge import numeric, banks, sources
from app.engine import personas, selector as selector_mod, followup, claims as claims_mod
from app.engine.evaluator import evaluate_technical, evaluate_numeric
from app.engine.behavioral import evaluate_behavioral
from app.engine import curriculum
from app.engine import game
from app.llm import provider, prompts, schemas
from app.profile import facts

MODES = {
    "superday": {"name": "Realistic Superday", "desc": "Full interview with a persona, time budget and hidden scoring; debrief at the end.", "hide_scores": True},
    "death_match": {"name": "Technical Death Match", "desc": "Technicals that climb in difficulty while you get them right and dig into misunderstandings when you don't.", "hide_scores": False},
    "resume_defense": {"name": "Resume Defense", "desc": "Every bullet on your resume, challenged line by line against what your documents actually support.", "hide_scores": False},
    "behavioral": {"name": "Behavioral Pressure Test", "desc": "Fit and story questions with follow-ups on structure, specificity and authenticity.", "hide_scores": False},
    "deal_defense": {"name": "Deal Defense", "desc": "Defend your pitches (UTHR, Insulet, StandardAero, Viasat, Seahawks) or a transaction.", "hide_scores": False},
    "rapid_fire": {"name": "Rapid-Fire Technicals", "desc": "Timed numeric and conceptual drill; speed and accuracy tracked separately.", "hide_scores": False},
    "explain": {"name": "Explain It Until You Understand It", "desc": "Socratic drill on one skill until you can transfer it to new numbers.", "hide_scores": False},
    "bank_specific": {"name": "Bank-Specific Interview", "desc": "Superday tuned to a bank and group using verified BankVault research.", "hide_scores": True},
    "hot_seat": {"name": "The Hot Seat", "desc": "Adversarial: every claim gets tested, contradictions get called, depth up to four follow-ups.", "hide_scores": True},
    "tmay": {"name": "Walk Me Through Your Resume", "desc": "Timed TMAY variants (60/90/120/180s) with beat and transition detection, including interrupted runs.", "hide_scores": False},
    "career": {"name": "Career Mode", "desc": "Simulated recruiting campaign at a real-named bank: screening → first round → technical → superday → final → fictional offer.", "hide_scores": True},
    "deathmatch": {"name": "Technical Deathmatch", "desc": "Three lives, rising difficulty, streak multipliers, boss questions every fifth. Each verdict is shown as you go, so you know why a life was lost.", "hide_scores": False},
    "daily": {"name": "Daily Draft", "desc": "A 5–10 minute personalized set: due reviews, weak skills, untested foundations and a couple of surprises.", "hide_scores": False},
    "weakness_lab": {"name": "Weakness Lab", "desc": "Diagnoses the real gap (prerequisites included) and teaches immediately: explanations, worked numbers, fresh practice.", "hide_scores": False},
}


NEUTRAL_ACKS = ["Okay.", "Alright.", "Got it."]

# One lock per session guards every read-modify-write of its state (request handlers and background deep grading),
# and the background grading threads are tracked so results can wait for them.
_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_PENDING: Dict[str, List[threading.Thread]] = {}
SETTLE_WAIT_SEC = 20.0


def _lock(sid: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(sid, threading.Lock())


def wait_for_deep_grades(sid: str, timeout: float = SETTLE_WAIT_SEC) -> None:
    deadline = time.time() + timeout
    for t in list(_PENDING.get(sid, [])):
        t.join(max(0.0, deadline - time.time()))
    _PENDING[sid] = [t for t in _PENDING.get(sid, []) if t.is_alive()]


def _pivot_fits(template: str, q: Dict) -> bool:
    """A transition must not announce something the next question isn't ('Let's go to your resume.' before a DCF question)."""
    t = template.lower()
    if "?" in t or "last question" in t or "claim" in t or "deal you" in t or "valuation" in t:
        return False
    if "resume" in t:
        return q.get("kind") == "resume" or q.get("source") == "resume"
    if "why you're here" in t:
        return q.get("kind") == "behavioral"
    return True


# Intent metadata for the Practice screen and launchers (duration in minutes; voice: both|text|voice-first)
MODE_META = {
    "daily": {"group": "quick", "minutes": "5–10", "scores": "live", "voice": "both", "when": "Every day; nothing to configure.", "improves": "Due reviews, weak skills, untested foundations"},
    "rapid_fire": {"group": "quick", "minutes": "5–15", "scores": "live", "voice": "both", "when": "You know the formulas but freeze on the numbers.", "improves": "Speed and accuracy on definitions and mental math"},
    "death_match": {"group": "quick", "minutes": "15–30", "scores": "live", "voice": "both", "when": "You want difficulty to climb while you are right and dig in when you are wrong.", "improves": "Depth on one topic ladder at a time"},
    "superday": {"group": "full", "minutes": "15–60", "scores": "hidden", "voice": "both", "when": "You want it to feel like the real thing.", "improves": "Composure, pacing, mixed technical and fit"},
    "bank_specific": {"group": "full", "minutes": "15–60", "scores": "hidden", "voice": "both", "when": "You have a specific bank and group in mind.", "improves": "Why-this-bank, group technicals, verified deal talk"},
    "behavioral": {"group": "full", "minutes": "15–30", "scores": "live", "voice": "both", "when": "Your stories are not tight yet.", "improves": "Structure, specificity, ownership, concision"},
    "resume_defense": {"group": "full", "minutes": "15–30", "scores": "live", "voice": "both", "when": "A bullet on your resume would not survive three follow-ups.", "improves": "Defensibility of every claim; surfaces facts you must fill in"},
    "tmay": {"group": "full", "minutes": "10", "scores": "live", "voice": "voice-first", "when": "Before any first round.", "improves": "Beats, order, length, transitions of your opener"},
    "deal_defense": {"group": "full", "minutes": "15–30", "scores": "live", "voice": "both", "when": "You will be asked about your pitches or a deal in the news.", "improves": "Thesis, variant view, valuation support, risks"},
    "weakness_lab": {"group": "targeted", "minutes": "10–20", "scores": "live", "voice": "both", "when": "You know what is weak and want it fixed, not graded.", "improves": "The root-cause prerequisite, then transfer to new numbers"},
    "explain": {"group": "targeted", "minutes": "10–15", "scores": "live", "voice": "both", "when": "One concept, until you can apply it.", "improves": "A single skill through Socratic follow-ups"},
    "hot_seat": {"group": "pressure", "minutes": "20–45", "scores": "hidden", "voice": "both", "when": "You want every claim tested and contradictions called.", "improves": "Rigor under pressure, consistency"},
    "deathmatch": {"group": "pressure", "minutes": "10–30", "scores": "hidden", "voice": "both", "when": "You want stakes: three lives, rising difficulty, bosses.", "improves": "Accuracy when a miss costs something"},
    "career": {"group": "pressure", "minutes": "10–30", "scores": "hidden", "voice": "both", "when": "You want a campaign arc across banks.", "improves": "Stage-appropriate mixed interviews with pass marks"},
}


def _now() -> float:
    return time.time()


def _lvl(q: Dict) -> int:
    """Cognitive level as an int (resume questions carry 'basic'/'advanced')."""
    v = q.get("level")
    if isinstance(v, str):
        return {"basic": 3, "advanced": 5}.get(v, 3)
    try:
        return int(v) if v is not None else int(q.get("difficulty") or 2)
    except (TypeError, ValueError):
        return 2


class Interview:
    def __init__(self, session_id: str):
        row = db.get_session(session_id)
        if not row:
            raise KeyError(session_id)
        self.id = session_id
        self.row = row
        self.config: Dict = row["config"]
        self.state: Dict = row["state"]
        self.mode = row["mode"]
        self.persona = personas.persona(self.config.get("persona", "vp") if self.mode != "hot_seat" else "hot_seat")
        self.bank = load_bank()
        self.rng = random.Random(self.state.get("seed", 0) + len(self.state.get("asked", [])) * 7 + len(self.state.get("evals", [])))
        self.settings = db.all_settings()
        self.llm_pref = self.settings.get("llm_provider", "auto")

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    def create(cls, mode: str, config: Dict) -> "Interview":
        if mode not in MODES:
            raise ValueError("unknown mode %s" % mode)
        game.init()
        cfg = dict(config)
        if mode == "deathmatch":
            base = game.deathmatch_config(cfg.get("categories"))
            base.update({k: v for k, v in cfg.items() if k != "deathmatch"})
            cfg = base
        elif mode == "daily":
            base = game.daily_config()
            base.update(cfg)
            cfg = base
        elif mode == "career":
            if not cfg.get("bank"):
                raise ValueError("career mode needs a bank")
            base = game.stage_config(cfg["bank"], cfg.get("sector"))
            base.update({k: v for k, v in cfg.items() if k not in ("career",)})
            cfg = base
        elif mode == "weakness_lab":
            from app.engine import lab
            base = lab.plan_config(cfg.get("skill"))
            base.update(cfg)
            cfg = base
        cfg["mode"] = mode
        cfg.setdefault("duration_min", {"rapid_fire": 10, "tmay": 10, "explain": 15}.get(mode, 30))
        cfg.setdefault("difficulty", "medium")
        cfg.setdefault("persona", "hot_seat" if mode == "hot_seat" else "vp")
        if cfg.get("bank"):
            cfg["bank_context"] = banks.context_for_interview(cfg.get("bank"), cfg.get("group"), cfg.get("sector"))
        state = {"phase": "opening", "current": None, "root_question": None, "followup_depth": 0, "asked": [], "evals": [], "claims": [],
                 "contradictions": [], "weaknesses": {}, "started_at": _now(), "paused_total": 0.0, "paused_at": None,
                 "duration_min": cfg["duration_min"], "seed": random.randrange(1 << 30), "turn_idx": 0, "ladder": {"easy": 1.5, "medium": 2.5, "hard": 3.5, "brutal": 4.5}.get(cfg["difficulty"], 2.5),
                 "explain_stage": 0, "tmay_variant": cfg.get("tmay_seconds", 90)}
        sid = db.create_session(mode, cfg, state)
        if mode == "daily":
            game.daily_start(sid)
        if mode in ("superday", "bank_specific") and not cfg.get("career"):
            try:
                from app.engine import prep
                prep.remember_mock(mode, cfg)
                if cfg.get("context_id"):
                    prep.touch_context(cfg["context_id"])
            except Exception:
                pass
        iv = cls(sid)
        return iv

    def save(self, status: Optional[str] = None, summary: Optional[Dict] = None) -> None:
        with _lock(self.id):
            self._merge_deep_grades()
            db.save_state(self.id, self.state, status, summary)

    def _merge_deep_grades(self) -> None:
        """This object's state was loaded at the start of the request; deep grades that landed since then live in the
        evaluations table. Fold them in so saving never reverts a revised score to its provisional value."""
        for e in self.state.get("evals", []):
            if e.get("deep") or not e.get("evaluation_id") or e.get("verdict") == "skipped":
                continue
            row = db.get_evaluation(e["evaluation_id"])
            data = (row or {}).get("data") or {}
            if data.get("deep_graded_at"):
                e.update({"score": row.get("score"), "verdict": row.get("verdict") or data.get("verdict"),
                          "key": data.get("key_error") or data.get("key_weakness"), "deep": True})

    def elapsed(self) -> float:
        paused = self.state.get("paused_total", 0.0)
        if self.state.get("paused_at"):
            paused += _now() - self.state["paused_at"]
        return max(0.0, _now() - self.state["started_at"] - paused)

    def time_fraction(self) -> float:
        total = self.state.get("duration_min", 30) * 60
        return min(1.5, self.elapsed() / total) if total else 0.0

    def pause(self) -> None:
        if not self.state.get("paused_at"):
            self.state["paused_at"] = _now()
            self.save()

    def resume(self) -> None:
        if self.state.get("paused_at"):
            self.state["paused_total"] = self.state.get("paused_total", 0.0) + (_now() - self.state["paused_at"])
            self.state["paused_at"] = None
            self.save()

    def public(self) -> Dict:
        hide = MODES[self.mode]["hide_scores"] and self.state["phase"] != "ended"
        return {"id": self.id, "mode": self.mode, "mode_name": MODES[self.mode]["name"], "config": {k: v for k, v in self.config.items() if k != "bank_context"},
                "bank_context_available": bool(self.config.get("bank_context")), "persona": {"key": self.config.get("persona"), "name": self.persona["name"], "title": self.persona["title"]},
                "phase": self.state["phase"], "current": self.state.get("current"), "followup_depth": self.state.get("followup_depth", 0),
                "elapsed_sec": round(self.elapsed()), "duration_min": self.state.get("duration_min"), "paused": bool(self.state.get("paused_at")),
                "n_asked": len(self.state["asked"]), "hide_scores": hide, "turn_idx": self.state.get("turn_idx", 0),
                "live_scores": None if hide else self.state.get("evals", [])[-5:], "llm_provider": provider.active_provider(self.llm_pref),
                "tmay_variant": self.state.get("tmay_variant"), "ended": self.state["phase"] == "ended",
                "callbacks": len(self.state.get("callbacks", [])), "callbacks_pending": len(self.state.get("callback_pending", [])),
                "deathmatch": {k: v for k, v in (self.config.get("deathmatch") or {}).items() if k in ("lives", "streak", "score", "questions", "boss_pending", "best_streak")} if self.mode == "deathmatch" else None,
                "career": self.config.get("career"), "daily": self.config.get("daily"), "focus_skills": self.config.get("focus_skills"), "xp_earned": self.state.get("xp_earned", 0)}

    # ------------------------------------------------------------------ turns
    def _say(self, text: str, kind: str, question_id: Optional[str], meta: Optional[Dict] = None) -> Dict:
        idx = self.state["turn_idx"]
        tid = db.add_turn(self.id, idx, "interviewer", text, question_id, kind, meta)
        self.state["turn_idx"] = idx + 1
        return {"turn_id": tid, "idx": idx, "role": "interviewer", "text": text, "kind": kind, "question_id": question_id, "meta": meta or {}}

    def _ask_main(self, q: Dict, prefix: str = "") -> Dict:
        self.state["current"] = q
        self.state["root_question"] = q
        self.state["followup_depth"] = 0
        self.state["asked"].append(q["id"])
        self.state["phase"] = "main"
        text = (prefix + " " if prefix else "") + q["text"]
        if self.mode == "tmay":
            text = self._tmay_prompt(q)
        meta = {"source": q["source"], "difficulty": q["difficulty"], "skill": q["skill"], "level": q.get("level")}
        if q.get("callback_of"):
            meta["callback_of"] = q["callback_of"]
            text = (prefix + " " if prefix else "") + "Going back to something from earlier. " + q["text"]
        return self._say(text, q["kind"], q["id"], meta)

    def _tmay_prompt(self, q: Dict) -> str:
        secs = self.state.get("tmay_variant", 90)
        variant = self.config.get("tmay_style", "standard")
        if variant == "interrupted":
            return "Walk me through your resume. I'll jump in with questions as you go."
        if variant == "led":
            return "Rather than the whole story, start with why you came to Georgetown, and I'll steer from there."
        return "%s You have about %d seconds." % (q["text"], secs)

    def start(self) -> List[Dict]:
        if self.state["asked"]:
            return []
        sel = selector_mod.Selector(self.state, self.config, self.persona)
        opener = self.persona["openers"][self.rng.randrange(len(self.persona["openers"]))]
        turns = []
        if self.mode in ("superday", "bank_specific", "hot_seat"):
            turns.append(self._say(opener, "opening", None))
        q = sel.next_main()
        if not q:
            turns.append(self._say("I'm out of questions for this configuration. Let's end here.", "closing", None))
            self.state["phase"] = "ended"
            self.save("ended")
            return turns
        if self.mode == "bank_specific" and self.config.get("bank_context", {}).get("name") and q["id"] == "beh_tmay":
            ctx = self.config["bank_context"]
            grp = (ctx.get("group") or {}).get("name")
            intro = "Good afternoon. I'm with %s%s." % (ctx["name"], (" in " + grp) if grp else "")
            turns.append(self._ask_main(q, intro))
        else:
            turns.append(self._ask_main(q))
        self.save()
        return turns

    def skip(self) -> List[Dict]:
        """Candidate skips the current question: logged as a non-answer, then pivot."""
        cur = self.state.get("current")
        if not cur:
            return self.start()
        idx = self.state["turn_idx"]
        tid = db.add_turn(self.id, idx, "candidate", "[skipped]", cur["id"], "skip", {})
        self.state["turn_idx"] = idx + 1
        ev = {"question_id": cur["id"], "skill": cur["skill"], "difficulty": cur["difficulty"], "kind": cur["kind"], "score": 0.0, "verdict": "skipped", "answered_question": False,
              "key_error": "Skipped.", "summary": "Skipped.", "components": [], "misconceptions": []}
        self._record_eval(tid, cur, ev, skip=True)
        if self.mode == "deathmatch":
            return self._respond(cur, ev, [])  # a skip costs a life; the run may end here
        return self._pivot()

    def repeat(self) -> Optional[Dict]:
        cur = self.state.get("current")
        if not cur:
            return None
        return {"text": cur["text"], "question_id": cur["id"]}

    def end(self) -> List[Dict]:
        try:
            from app.llm.worker import POOL
            POOL.drop("interviewer:%s" % self.id)
        except Exception:
            pass
        closer = self.persona["closers"][self.rng.randrange(len(self.persona["closers"]))]
        t = self._say(closer, "closing", None)
        self.state["phase"] = "ended"
        if self.mode in ("career", "daily"):
            # pass/fail and the daily score are final once resolved: let in-flight model grades land first
            wait_for_deep_grades(self.id)
        self.save("ended")  # persist state first so game resolution reads the final evals
        summary = self._summary()
        self.save("ended", summary)
        return [t]

    def _summary(self) -> Dict:
        evs = [e for e in self.state.get("evals", []) if e.get("score") is not None]
        out = {"n": len(evs), "avg": round(sum(e["score"] for e in evs) / len(evs), 3) if evs else None,
               "elapsed_sec": round(self.elapsed()), "weak_skills": sorted(self.state.get("weaknesses", {}).items(), key=lambda kv: kv[1])[:5],
               "xp_earned": self.state.get("xp_earned", 0)}
        if not self.state.get("game_resolved"):
            self.state["game_resolved"] = True
            try:
                if self.mode == "career":
                    out["career"] = game.resolve_career_session(self.id)
                elif self.mode == "deathmatch":
                    out["deathmatch"] = game.deathmatch_finish(self.id, self.config.get("deathmatch") or game.deathmatch_config()["deathmatch"])
                elif self.mode == "daily":
                    out["daily"] = game.daily_finish(self.id)
                out["achievements"] = game.check_achievements_after_session(self.id)
            except Exception as e:  # noqa
                out["game_error"] = str(e)[:200]
            self.state["game_summary"] = {k: out.get(k) for k in ("career", "deathmatch", "daily", "achievements") if out.get(k) is not None}
        else:
            out.update(self.state.get("game_summary") or {})
        return out

    # ------------------------------------------------------------------ answer handling
    def answer(self, text: str, duration: Optional[float] = None, pauses: Optional[List[float]] = None, transcript_meta: Optional[Dict] = None) -> Dict:
        """Process a candidate answer; return {candidate_turn, evaluation(optional), interviewer_turns}."""
        if self.state["phase"] == "ended":
            return {"error": "session ended"}
        cur = self.state.get("current")
        if not cur:
            turns = self.start()
            return {"interviewer_turns": turns}
        self.resume()
        idx = self.state["turn_idx"]
        tid = db.add_turn(self.id, idx, "candidate", text, cur["id"], "answer", {"duration": duration, "pauses": pauses or [], **(transcript_meta or {})})
        self.state["turn_idx"] = idx + 1
        interrupted = bool((transcript_meta or {}).get("interrupted"))
        # LIVE layer: provisional deterministic evaluation (instant) drives the next question
        ev = self._evaluate(cur, text, duration, pauses, use_llm=False)
        ev["provisional"] = True
        llm_on = self.settings.get("use_llm", True) and provider.active_provider(self.llm_pref) != "offline"
        graded_now = False
        if llm_on and self._needs_final_grade_now(cur, ev):
            # Deathmatch lives and points are final the moment they are applied, so an uncertain keyword grade
            # must not decide them: wait for the model-refined grade (a few seconds) instead.
            try:
                deep = self._evaluate(cur, text, duration, pauses, use_llm=True)
            except Exception:  # noqa
                deep = None
            if deep and deep.get("provider") not in (None, "offline", "deterministic"):
                deep["provisional"] = False
                deep["provisional_score"] = ev.get("score")
                deep["deep_graded_at"] = time.time()
                ev = deep
                graded_now = True
        if interrupted:
            ev["interrupted"] = True
        self._record_eval(tid, cur, ev)
        # DEEP layer: model-refined grading runs in the background and revises the stored evaluation
        if llm_on and not graded_now:
            th = threading.Thread(target=self._deep_grade, args=(cur, text, duration, pauses, ev["evaluation_id"], tid), daemon=True)
            _PENDING.setdefault(self.id, []).append(th)
            th.start()
        # claims + contradictions
        new_claims = claims_mod.extract(text, idx, cur["id"])
        flagged = self.state.setdefault("flagged_claim_keys", [])
        contradictions = claims_mod.find_contradictions(self.state.get("claims", []), new_claims, flagged)
        self.state.setdefault("claims", []).extend(new_claims)
        for c in contradictions:
            flagged.append(c["key"])
            self.state.setdefault("contradictions", []).append({**c, "phrased": claims_mod.phrase(c)})
        # decide next interviewer move
        self.state["time_fraction"] = self.time_fraction()
        turns = self._respond(cur, ev, contradictions)
        hide = MODES[self.mode]["hide_scores"]
        out = {"candidate_turn": {"turn_id": tid, "idx": idx, "text": text}, "interviewer_turns": turns, "state": self.public()}
        if not hide:
            out["evaluation"] = _compact_eval(ev)
        self.save("ended" if self.state["phase"] == "ended" else None, self._summary() if self.state["phase"] == "ended" else None)
        return out

    def _needs_final_grade_now(self, cur: Dict, ev: Dict) -> bool:
        if self.mode != "deathmatch" or cur.get("source") == "numeric":
            return False
        if ev.get("verdict") == "non_answer" or ev.get("keyword_list") or ev.get("gave_up"):
            return False  # the rules are certain about these
        return (ev.get("score") or 0) < 0.75  # anything short of full credit could still flip

    def _deep_grade(self, cur: Dict, text: str, duration: Optional[float], pauses: Optional[List[float]], eid: str, tid: str) -> None:
        try:
            ev = self._evaluate(cur, text, duration, pauses, use_llm=True)
        except Exception as e:  # noqa
            db.update_evaluation(eid, {**(db.get_evaluation(eid) or {}).get("data", {}), "deep_error": str(e)[:200]}, None, "", 0)
            return
        if ev.get("provider") in (None, "offline", "deterministic"):
            return  # nothing new (quota exhausted, worker down): keep the provisional grade
        ev["provisional"] = False
        ev["deep_graded_at"] = time.time()
        prev = db.get_evaluation(eid)
        ev["provisional_score"] = (prev or {}).get("score")
        db.update_evaluation(eid, ev, ev.get("score"), ev.get("verdict", ""), (prev or {}).get("appealed", 0))
        if ev.get("score") is not None:
            curriculum.revise(cur["skill"], cur["id"], self.id, ev["score"])
            # keep the compact in-state summary consistent for the debrief (under the session lock, so a
            # concurrent request cannot interleave its own read-modify-write)
            with _lock(self.id):
                row = db.get_session(self.id)
                if row:
                    st = row["state"]
                    for e in st.get("evals", []):
                        if e.get("evaluation_id") == eid:
                            e["score"] = ev["score"]
                            e["verdict"] = ev.get("verdict")
                            e["key"] = ev.get("key_error") or ev.get("key_weakness")
                            e["deep"] = True
                    db.save_state(self.id, st)

    def _evaluate(self, cur: Dict, text: str, duration: Optional[float], pauses: Optional[List[float]], use_llm: Optional[bool] = None) -> Dict:
        use_llm = self.settings.get("use_llm", True) if use_llm is None else use_llm
        if cur["source"] == "numeric":
            gen = numeric.generate(cur["generator"], cur["seed"])
            ev = evaluate_numeric(gen, text)
            ev["time_sec"] = duration
            if duration is not None:
                ev["speed"] = "fast" if duration <= 20 else ("ok" if duration <= 60 else "slow")
            return ev
        if cur["source"] == "resume":
            return self._evaluate_resume(cur, text, duration, use_llm)
        if cur["source"] == "source":
            rec = sources.get(cur["id"])
            q = sources.as_question(rec)
            if not self.settings.get("send_guide_excerpts", True):
                q.solution = "(reference withheld by setting: guide excerpts are not sent to the model)"
            ev = evaluate_technical(q, text, self.llm_pref, use_llm)
            ev["stronger_answer"] = rec.get("answer", "")
            ev["citation"] = sources.citation(rec)
            ev["level"] = rec.get("level", 2)
            return ev
        q = self.bank[cur["id"]]
        if q.kind == "behavioral":
            return evaluate_behavioral(q, text, duration, self.llm_pref, use_llm, pauses)
        return evaluate_technical(q, text, self.llm_pref, use_llm)

    def _evaluate_resume(self, cur: Dict, text: str, duration: Optional[float], use_llm: bool) -> Dict:
        """Resume-defense answers are judged on specificity, mechanics, ownership and consistency with documents.
        Deterministic: a pseudo-rubric from the bullet's claims + energy/valuation concept vocabulary."""
        from app.profile import resume_defense
        from app.engine import delivery as dl
        import re
        b = next((x for x in resume_defense.bullets() if x["id"] == cur["bullet_id"]), None)
        low = text.lower()
        metrics = dl.analyze(text, duration, "technical")
        concept_words = {
            "hobo": [r"decline|hyperbolic|exponential|b.factor|type curve", r"price deck|strip|henry hub|flat price", r"basis|differential|dominion|tetco|deduction", r"royalt|nri|net revenue interest|mineral", r"pdp|pud|undeveloped|producing", r"discount rate|pv.?10|risk.adjust", r"sensitiv|downside|scenario", r"operator|permit|rig|drill", r"present|principal|owner|recommend"],
            "gpva": [r"reimburs|payer|medicare|commercial", r"procedure|volume|physician|referral", r"revenue|collection|mix", r"recommend|present|management", r"excel|data|year"],
            "gadif": [r"wacc|beta|cost of (equity|debt)", r"terminal|exit multiple|perpetuity", r"starlink|leo|capex|refinanc|leverage|pass.through|mro|aftermarket", r"sotp|comps|dcf", r"upside|downside|target|\$\d", r"variant|market (misses|underestimat)|consensus", r"risk"],
            "gci": [r"rnpv|probabilit|approval|ipf|ralinepag|patent|liquidia|tyvaso", r"omnipod|pod|aid|type 2|international|medtronic|tandem|lilly", r"dcf|wacc|terminal|growth|margin|comps", r"team|my (part|role|section)|i built", r"risk|bear|concentrat|competit", r"\$\d|%"],
            "map": [r"media|national|shared|gate|premium|sponsor", r"salary cap|player", r"dcf|comps|precedent|ev/revenue|multiple", r"forbes|sportico|9\.6|transaction", r"team|my (part|role)|i built", r"scarc|trophy|buyer"],
            "tennis": [r"hours|train|travel|schedule", r"match|lineup|singles|doubles", r"injur|rehab|back", r"result|won|ranked|learned|lesson"],
        }
        pats = concept_words.get(cur["experience_id"], [])
        hits = [p for p in pats if re.search(p, low)]
        coverage = len(hits) / max(len(pats), 1)
        numbers = len(re.findall(r"\d", text))
        ownership = len(re.findall(r"\bi\b|\bmy\b", low)) / max(1, len(re.findall(r"\bi\b|\bmy\b|\bwe\b|\bour\b", low)))
        vague = bool(re.search(r"\b(various|a lot of|different things|kind of|sort of|and stuff|things like that)\b", low))
        gave = bool(re.search(r"i (don'?t|do not) (really )?(know|remember)|can'?t recall|not sure", low))
        score = 0.45 * coverage + 0.2 * min(1.0, numbers / 3) + 0.2 * ownership + 0.15 * (0 if vague else 1)
        if gave:
            score = min(score, 0.45)
        words = metrics["words"]
        if words < 25:
            score = min(score, 0.35)
        # unsupported vs facts
        unsupported = []
        for e in facts.EXPERIENCES:
            if e["id"] == cur["experience_id"]:
                for d in e.get("discrepancies", []):
                    if cur["experience_id"] == "gadif" and re.search(r"\b(23|46|48)\s*%", low):
                        unsupported.append(d)
                        break
        ev = {"question_id": cur["id"], "skill": cur["skill"], "difficulty": cur["difficulty"], "kind": "resume", "answer": text, "components": [
            {"id": "c%d" % i, "text": "Mentions: " + p.replace("|", " / ")[:60], "present": p in hits, "required": False, "weight": 1.0, "source": "deterministic"} for i, p in enumerate(pats)],
            "misconceptions": [], "coverage": round(coverage, 2), "numbers": numbers, "ownership": round(ownership, 2), "vague": vague, "gave_up": gave,
            "score": round(max(0.0, min(1.0, score)), 3), "answered_question": words >= 12, "delivery": metrics, "unsupported_claims": unsupported,
            "missing": ["c%d" % i for i, p in enumerate(pats) if p not in hits], "missing_required": [], "provider": "offline"}
        ev["verdict"] = "correct" if ev["score"] >= 0.7 else ("partial" if ev["score"] >= 0.4 else "incorrect")
        ev["key_error"] = (unsupported[0] if unsupported else ("Vague: no concrete mechanics or numbers an interviewer could test." if (vague or numbers == 0) else ("Your personal role is unclear; say what you built." if ownership < 0.5 else None)))
        if b:
            ev["stronger_answer"] = "A defensible answer names the mechanics (%s), gives at least one number, and states your personal role. Documented support: %s. Gaps you must fill in the KB: %s." % (
                "; ".join(b["claims"][:3]), ", ".join(b["evidence"]), "; ".join(u["ask"] for u in b["unknowns"][:2]) or "none listed")
        ev["summary"] = "Covered %d of %d expected concept areas; %d numbers; ownership %.0f%%.%s" % (len(hits), len(pats), numbers, ownership * 100, " Vague phrasing." if vague else "")
        if use_llm and provider.active_provider(self.llm_pref) != "offline" and b:
            from app.knowledge.bank import Question as QC, Component as CC
            pseudo = QC(id=cur["id"], topic="resume", subtopic=cur["experience_id"], skill=cur["skill"], difficulty=cur["difficulty"], text=cur["text"],
                        components=[CC("c%d" % i, "Mentions " + p.replace("|", "/")[:50], [p]) for i, p in enumerate(pats)],
                        solution=ev["stronger_answer"], assumptions="Only facts in the candidate's documents are verified: " + " | ".join(f["text"][:140] for f in (facts.experience(cur["experience_id"]) or {}).get("facts", [])[:4]))
            from app.engine.evaluator import _refine_with_llm
            ev["missing_required"] = []
            _refine_with_llm(pseudo, text, ev, self.llm_pref)
        return ev

    def _record_eval(self, tid: str, cur: Dict, ev: Dict, skip: bool = False) -> None:
        score = ev.get("score")
        eid = db.add_evaluation(self.id, tid, cur["id"], cur["skill"], score, ev.get("verdict", ""), ev)
        ev["evaluation_id"] = eid
        self.state.setdefault("evals", []).append({"evaluation_id": eid, "question_id": cur["id"], "skill": cur["skill"], "score": score, "verdict": ev.get("verdict"),
                                                   "kind": ev.get("kind"), "depth": self.state.get("followup_depth", 0), "key": ev.get("key_error") or ev.get("key_weakness")})
        if score is not None and not skip:
            curriculum.record(cur["skill"], score, cur["difficulty"], ev.get("kind", "technical"), cur["id"], self.id, level=_lvl(cur))
            if score < 0.6:
                w = self.state.setdefault("weaknesses", {})
                w[cur["skill"]] = min(w.get(cur["skill"], 1.0), score)
        if cur["source"] in ("bank", "source"):
            db.bump_question(cur["id"], score)
        # interviewer memory: a missed concept becomes a callback candidate; a later callback records its outcome
        if score is not None and not skip:
            if cur.get("callback_of"):
                self.state.setdefault("callbacks", []).append({"skill": cur["skill"], "original_question": cur["callback_of"], "question_id": cur["id"], "score": score, "success": score >= 0.6, "turn": self.state.get("turn_idx")})
            elif score < 0.5 and cur["kind"] not in ("behavioral", "resume") and cur["source"] != "resume":
                pend = self.state.setdefault("callback_pending", [])
                if not any(p["skill"] == cur["skill"] for p in pend):
                    pend.append({"skill": cur["skill"], "question_id": cur["id"], "asked_at": len(self.state["asked"]), "key": ev.get("key_error")})
        if self.mode == "death_match" and score is not None:
            self.state["ladder"] = max(1.0, min(6.0, self.state.get("ladder", 2.5) + (0.8 if score >= 0.75 else (-0.8 if score < 0.4 else 0.0))))
        if self.mode == "deathmatch":
            # a skip is a non-answer: it costs a life like any other miss
            dm = self.config.setdefault("deathmatch", game.deathmatch_config()["deathmatch"])
            game.deathmatch_update(dm, score, _lvl(cur))
            self.state["deathmatch"] = dict(dm)
            self.save()
            with db.conn() as c:
                c.execute("UPDATE sessions SET config=? WHERE id=?", (__import__("json").dumps(self.config), self.id))
        if score is not None and not skip:
            xp = game.xp_for_answer(score, _lvl(cur), cur["id"], ev.get("kind", "technical"))
            if xp:
                game.award_xp(xp, "answer:%s" % cur["id"], self.id)
                self.state["xp_earned"] = self.state.get("xp_earned", 0) + xp

    # ------------------------------------------------------------------ interviewer policy
    def _respond(self, cur: Dict, ev: Dict, contradictions: List[Dict]) -> List[Dict]:
        turns: List[Dict] = []
        if self.mode == "rapid_fire":
            return self._pivot(ack=self._ack(ev))
        if self.mode == "deathmatch":
            dm = self.config.get("deathmatch") or {}
            if not dm.get("alive", True):
                turns.append(self._say("That's your last life. Run over.", "closing", None))
                turns.extend(self.end())
                return turns
            ack = self._ack(ev)
            if dm.get("boss_pending"):
                ack = (ack + " Boss question.").strip()
            return self._pivot(ack=ack)
        # contradictions take priority once per chain, in skeptical personas
        if contradictions and self.persona.get("seniority", 2) >= 2 and self.state.get("followup_depth", 0) < self.persona["max_followup_depth"]:
            text = claims_mod.phrase(contradictions[0])
            self.state["followup_depth"] += 1
            self.state["phase"] = "probing"
            turns.append(self._say(text, "followup", cur["id"], {"reason": "contradiction", "root": self.state["root_question"]["id"]}))
            return turns
        if self.mode in ("explain", "weakness_lab"):
            return self._explain_policy(cur, ev)
        if ev.get("interrupted") and self.state.get("followup_depth", 0) < self.persona["max_followup_depth"]:
            self.state["followup_depth"] = self.state.get("followup_depth", 0) + 1
            self.state["phase"] = "probing"
            text = "Let me stop you there. In one sentence: what's the single most important point?"
            self.state.setdefault("used_followups", []).append(text)
            turns.append(self._say(text, "followup", cur["id"], {"reason": "too_long", "action": "probe", "root": (self.state.get("root_question") or cur)["id"]}))
            return turns
        action, reason, details = followup.classify(ev, cur, self.state, self.persona)
        # don't press the same point three times: if the same reason fired on the previous probe, move on
        if action == "probe" and reason == self.state.get("last_probe_reason") and self.state.get("followup_depth", 0) >= 2:
            action, reason = "pivot", None
        self.state["last_probe_reason"] = reason if action == "probe" else None
        if action == "deepen":
            # deepen only when the bank has a real follow-up for a good answer, and not every time
            q_tmp = self.bank.get(cur["id"]) if cur["source"] == "bank" else None
            has_deeper = bool(q_tmp and any(f.when in ("correct", "always") for f in q_tmp.followups)) or cur["source"] == "source"
            p_deepen = {"hot_seat": 0.85, "md": 0.5, "vp": 0.6, "associate": 0.45, "analyst": 0.3}.get(self.config.get("persona") if self.mode != "hot_seat" else "hot_seat", 0.5)
            if not has_deeper or self.rng.random() > p_deepen:
                action, reason = "pivot", None
        q_obj: Optional[Question] = self.bank.get(cur["id"]) if cur["source"] == "bank" else (sources.as_question(sources.get(cur["id"])) if cur["source"] == "source" else None)
        used = set(self.state.setdefault("used_followups", []))
        # adaptive chain: a good answer to a source question at level L leads to a same-skill question at level L+1
        if action == "deepen" and cur["source"] == "source" and (ev.get("score") or 0) >= 0.75:
            nxt = sources.next_level_question(cur["skill"], int(cur.get("level", 2)), set(self.state["asked"]))
            if nxt:
                nq = selector_mod.wrap_source(nxt)
                self.state["followup_depth"] = self.state.get("followup_depth", 0) + 1
                self.state["phase"] = "probing"
                self.state["current"] = nq
                self.state["asked"].append(nq["id"])
                turns.append(self._say(self._ack(ev) + " " + nq["text"], "followup", nq["id"], {"reason": "level_up", "action": "deepen", "root": (self.state.get("root_question") or cur)["id"], "chained_to": nq["id"], "level": nq["level"]}))
                return turns
        if action in ("probe", "deepen", "clarify"):
            fu = followup.bank_followup(q_obj, ev, action, reason, details, used)
            if fu is None and action == "deepen":
                return self._pivot(ack=self._ack(ev))
            if action == "clarify":
                text = "Which is it? Pick one and defend it."
                if fu and fu["trigger"] == "vague":
                    text = fu["text"]
            elif fu:
                text = fu["text"]
            elif cur["source"] == "resume":
                text = self._resume_probe(cur, ev, reason)
            else:
                text = followup.phrase_probe(reason or "missing_causal", details, cur["text"], self.rng)
            if text in used:
                # never ask the same follow-up twice: vary the probe or move on
                alt = followup.phrase_probe(reason or "missing_causal", details, cur["text"], self.rng)
                if alt in used or self.state.get("followup_depth", 0) >= 1:
                    return self._pivot(ack=self._ack(ev))
                text = alt
            self.state["used_followups"].append(text)
            text = self._style(text, ev, action)
            text = self._maybe_llm_rephrase(text, cur, ev, action, reason)
            self.state["followup_depth"] = self.state.get("followup_depth", 0) + 1
            self.state["phase"] = "probing"
            meta = {"reason": reason, "action": action, "root": (self.state.get("root_question") or cur)["id"], "trigger": (fu or {}).get("trigger")}
            # chained question: becomes the current question for evaluation purposes
            if fu and fu.get("next_id") and fu["next_id"] in self.bank and fu["next_id"] not in self.state["asked"]:
                nq = selector_mod.wrap_bank(self.bank[fu["next_id"]])
                self.state["current"] = nq
                self.state["asked"].append(nq["id"])
                meta["chained_to"] = nq["id"]
                turns.append(self._say(text, "followup", nq["id"], meta))
            else:
                turns.append(self._say(text, "followup", cur["id"], meta))
            return turns
        return self._pivot(ack=self._ack(ev))

    def _ack(self, ev: Dict) -> str:
        if MODES[self.mode]["hide_scores"]:
            # scores are hidden: the acknowledgement must not hint at the verdict
            return NEUTRAL_ACKS[self.rng.randrange(len(NEUTRAL_ACKS))]
        score = ev.get("score") or 0
        bank_ = self.persona["ack_good"] if score >= 0.7 else self.persona["ack_neutral"]
        return bank_[self.rng.randrange(len(bank_))]

    def _style(self, text: str, ev: Dict, action: str) -> str:
        if self.mode in ("hot_seat",) and action == "probe" and self.rng.random() < 0.4:
            pre = self.persona["probe_templates"][self.rng.randrange(len(self.persona["probe_templates"]))]
            if "{" not in pre and len(pre) < 60 and not text.startswith(pre):
                return pre + " " + text
        return text

    def _resume_probe(self, cur: Dict, ev: Dict, reason: Optional[str]) -> str:
        from app.profile import resume_defense
        exp = facts.experience(cur["experience_id"]) or {}
        unknowns = exp.get("unknowns", [])
        asked_unknowns = self.state.setdefault("asked_unknowns", [])
        for u in unknowns:
            if u["id"] not in asked_unknowns:
                asked_unknowns.append(u["id"])
                return u["ask"]
        pool = [r for r in resume_defense.question_pool(cur["experience_id"]) if r["id"] not in self.state["asked"] and r["level"] == "advanced"]
        if pool:
            r = pool[self.rng.randrange(len(pool))]
            self.state["asked"].append(r["id"])
            return r["text"]
        return followup.phrase_probe(reason or "missing_numbers", {}, cur["text"], self.rng)

    def _maybe_llm_rephrase(self, text: str, cur: Dict, ev: Dict, action: str, reason: Optional[str]) -> str:
        if not self.settings.get("use_llm", True) or provider.active_provider(self.llm_pref) == "offline":
            return text
        if not self.settings.get("llm_interviewer", True):
            return text
        fact_lines = []
        exp = facts.experience(cur.get("experience_id", "")) if cur.get("experience_id") else None
        if exp:
            fact_lines = [b["text"][:160] for b in exp["bullets"]] + [f["text"][:160] for f in exp.get("facts", [])[:3]]
        findings = "verdict=%s score=%.2f key=%s missing=%s" % (ev.get("verdict"), ev.get("score") or 0, ev.get("key_error") or ev.get("key_weakness"), (ev.get("missing") or [])[:3])
        user = prompts.INTERVIEWER_USER.format(
            mode=MODES[self.mode]["name"], bank=self.config.get("bank") or "-", group=self.config.get("group") or "-", elapsed_min=self.elapsed() / 60,
            total_min=self.state.get("duration_min"), phase=self.state["phase"], question_id=cur["id"], question_text=cur["text"], answer=ev.get("answer", "")[:1500],
            findings=findings, decision="%s (%s)" % (action, reason), suggested=text, facts="\n".join(fact_lines) or "(none needed)",
            bank_context=str(self.config.get("bank_context") or {})[:1500])
        system = prompts.INTERVIEWER_SYSTEM.format(persona_name=self.persona["name"], persona_title=self.persona["title"], persona_style=self.persona["style"])
        data, _ = provider.complete_json(system, user, self.llm_pref, worker="interviewer:%s" % self.id)
        turn = schemas.parse(schemas.InterviewerTurn, data)
        if turn and 3 < len(turn.utterance) < 400 and not any(w in turn.utterance.lower() for w in ("great answer", "excellent", "fantastic", "love that")):
            return turn.utterance
        return text

    def _pivot(self, ack: str = "") -> List[Dict]:
        turns: List[Dict] = []
        tf = self.time_fraction()
        n_main = len([a for a in self.state["asked"]])
        max_q = self.config.get("max_questions")
        if tf >= 1.0 or (max_q and n_main >= int(max_q)):
            turns.extend(self.end())
            return turns
        sel = selector_mod.Selector(self.state, self.config, self.persona)
        if self.mode == "tmay":
            return self._tmay_pivot(ack)
        boss = self.mode == "deathmatch" and (self.config.get("deathmatch") or {}).get("boss_pending")
        q = (None if boss else self._maybe_callback(sel)) or sel.next_main()
        if not q:
            turns.extend(self.end())
            return turns
        pivot_phrase = ""
        root = self.state.get("root_question") or {}
        if ack and self.mode not in ("rapid_fire",):
            pivot_phrase = ack
        if (root and root.get("topic") != q.get("topic") and not q.get("callback_of") and self.rng.random() < 0.5
                and self.mode not in ("rapid_fire", "death_match", "deathmatch")):
            pvs = [t for t in self.persona["pivot_templates"] if _pivot_fits(t, q)]
            if pvs:
                pv = pvs[self.rng.randrange(len(pvs))]
                pivot_phrase = (pivot_phrase + " " + pv).strip()
        turns.append(self._ask_main(q, pivot_phrase))
        return turns

    def _maybe_callback(self, sel) -> Optional[Dict]:
        """Revisit a concept missed earlier, at least three main questions later, in a different question
        (never the same one), at most once per concept and not on consecutive turns."""
        if self.mode in ("rapid_fire", "tmay", "explain", "resume_defense"):
            return None
        pend = self.state.get("callback_pending") or []
        n = len(self.state["asked"])
        if not pend or self.state.get("last_callback_at", -10) >= n - 2:
            return None
        for p in list(pend):
            if n - p["asked_at"] < 1:  # at least one other main question in between
                continue
            if self.rng.random() > float(self.config.get("callback_prob", 0.6)):
                continue
            q = sel.pick_by_skill(p["skill"])
            if not q or q["id"] == p["question_id"]:
                pend.remove(p)  # nothing new to ask on this skill; drop it
                continue
            pend.remove(p)
            q["callback_of"] = p["question_id"]
            q["tags"] = (q.get("tags") or []) + ["callback"]
            self.state["last_callback_at"] = n
            return q
        return None

    # ------------------------------------------------------------------ mode-specific policies
    def _tmay_pivot(self, ack: str) -> List[Dict]:
        """Cycle variants: 90s → 60s → 120s → interrupted → led; then end."""
        order = [90, 60, 120, 180]
        done = self.state.setdefault("tmay_done", [])
        done.append(self.state.get("tmay_variant"))
        remaining = [s for s in order if s not in done]
        if remaining and self.config.get("tmay_style", "standard") == "standard":
            self.state["tmay_variant"] = remaining[0]
            q = selector_mod.wrap_bank(self.bank["beh_tmay"])
            self.state["current"] = q
            self.state["root_question"] = q
            self.state["followup_depth"] = 0
            self.state["asked"].append("beh_tmay_%d" % remaining[0])
            return [self._say("%s Again, this time in about %d seconds." % (ack, remaining[0]), "behavioral", q["id"], {"variant": remaining[0]})]
        if len(done) < 6 and self.config.get("tmay_style", "standard") == "standard":
            # interrupted variant last
            self.config["tmay_style"] = "interrupted"
            q = selector_mod.wrap_bank(self.bank["beh_walk_resume"])
            self.state["current"] = q
            self.state["root_question"] = q
            self.state["followup_depth"] = 0
            self.state["asked"].append("beh_walk_resume_interrupted")
            return [self._say("Last one. Walk me through your resume and I'll interrupt as I go. Start with Pittsburgh.", "behavioral", q["id"], {"variant": "interrupted"})]
        return self.end()

    def _explain_policy(self, cur: Dict, ev: Dict) -> List[Dict]:
        """Socratic ladder for one skill: probe → decompose → rebuild → transfer (numeric) → revisit later."""
        stage = self.state.get("explain_stage", 0)
        score = ev.get("score") or 0
        q_obj = self.bank.get(cur["id"]) if cur["source"] == "bank" else None
        turns = []
        if score >= 0.75 and stage >= 2:
            # transfer test with numbers if a generator exists for the skill
            sel = selector_mod.Selector(self.state, self.config, self.persona)
            gens = [n for n in numeric.GENERATORS if numeric.GENERATORS[n].skill == cur["skill"] or numeric.GENERATORS[n].skill.split(".")[0] == cur["skill"].split(".")[0]]
            if gens and not self.state.get("explain_transfer_done"):
                self.state["explain_transfer_done"] = True
                nq = sel.pick_numeric(cur["skill"]) if any(numeric.GENERATORS[n].skill == cur["skill"] for n in gens) else selector_mod.wrap_numeric(numeric.generate(gens[0], self.rng.randrange(1 << 30)))
                self.state["explain_stage"] = stage + 1
                turns.append(self._ask_main(nq, "Good. Now with numbers."))
                return turns
            nxt = sel.pick_by_skill(cur["skill"])
            if nxt and self.state["explain_stage"] < 6:
                self.state["explain_stage"] = stage + 1
                turns.append(self._ask_main(nxt, "Okay. Different angle on the same idea."))
                return turns
            if self.mode == "weakness_lab":
                focus = list(self.config.get("focus_skills") or [])
                done = self.state.setdefault("lab_done", [])
                done.append(cur["skill"])
                rem = [f for f in focus if f not in done]
                if rem:
                    self.state["explain_stage"] = 0
                    self.state["explain_transfer_done"] = False
                    nq = sel.pick_by_skill(rem[0])
                    if nq:
                        turns.append(self._ask_main(nq, "Good, that one holds. Next weakness."))
                        return turns
            turns.extend(self.end())
            return turns
        if score >= 0.75:
            self.state["explain_stage"] = stage + 1
            self.state["explain_fails"] = 0
            fu = followup.bank_followup(q_obj, ev, "deepen", "deeper_probe", {}) if q_obj else None
            text = fu["text"] if fu else "Okay. Now explain it as if to someone who has never seen a cash flow statement."
            self.state["followup_depth"] += 1
            turns.append(self._say(text, "followup", cur["id"], {"reason": "explain_deepen"}))
            return turns
        # weak: decompose using misconception or missing component; after two failed attempts on the same
        # question, teach the mechanism and test transfer on a sibling question instead of looping
        fails = self.state.get("explain_fails", 0) + 1
        self.state["explain_fails"] = fails
        if fails >= 3 and q_obj is not None:
            sel = selector_mod.Selector(self.state, self.config, self.persona)
            nxt = sel.pick_by_skill(cur["skill"])
            self.state["explain_fails"] = 0
            self.state["explain_stage"] = stage + 1
            teach = "Here is the mechanism: %s" % q_obj.solution
            if nxt and self.state["explain_stage"] < 6:
                turns.append(self._say(teach, "teach", cur["id"], {"reason": "explain_teach", "skill": cur["skill"]}))
                turns.append(self._ask_main(nxt, "Now apply it."))
                return turns
            if self.mode == "weakness_lab":
                # move to the next focus skill instead of ending
                focus = list(self.config.get("focus_skills") or [])
                done = self.state.setdefault("lab_done", [])
                done.append(cur["skill"])
                rem = [f for f in focus if f not in done]
                if rem:
                    self.state["explain_stage"] = 0
                    nq = sel.pick_by_skill(rem[0])
                    if nq:
                        turns.append(self._say(teach, "teach", cur["id"], {"reason": "explain_teach", "skill": cur["skill"]}))
                        turns.append(self._ask_main(nq, "Next weakness."))
                        return turns
            turns.append(self._say(teach, "teach", cur["id"], {"reason": "explain_teach"}))
            turns.extend(self.end())
            return turns
        fu = followup.bank_followup(q_obj, ev, "probe", "missing_causal", {"component": (ev.get("missing") or [None])[0]}) if q_obj else None
        if ev.get("misconceptions"):
            text = "Let's slow down. %s Start with just that piece: what is it, and is it cash?" % ev["misconceptions"][0]["explain"].split(".")[0] + "."
        elif fu:
            text = fu["text"]
        else:
            text = "Break it into pieces. What is the first thing that happens, mechanically?"
        self.state["followup_depth"] += 1
        self.state["explain_stage"] = max(stage, 1)
        turns.append(self._say(text, "followup", cur["id"], {"reason": "explain_decompose"}))
        return turns

    # ------------------------------------------------------------------ retest
    @classmethod
    def retest_from(cls, session_id: str, limit: int = 5) -> "Interview":
        src = db.get_session(session_id)
        evs = sorted([e for e in src["state"].get("evals", []) if e.get("score") is not None and e.get("question_id")], key=lambda e: e["score"])
        qids = []
        for e in evs:
            if e["question_id"] not in qids and not e["question_id"].startswith("num_"):
                qids.append(e["question_id"])
            if len(qids) >= limit:
                break
        iv = cls.create("death_match", {"persona": src["config"].get("persona", "vp"), "difficulty": src["config"].get("difficulty", "medium"), "retest_of": session_id, "queue": qids, "duration_min": 15, "max_questions": len(qids)})
        return iv


def _compact_eval(ev: Dict) -> Dict:
    keys = ("evaluation_id", "question_id", "skill", "kind", "score", "verdict", "answered_question", "key_error", "key_weakness", "summary", "coverage",
            "components", "misconceptions", "dimensions", "delivery", "stronger_answer", "stronger_version", "unsupported_claims", "expected", "closest", "speed", "provider", "tmay_beats", "why_beats")
    return {k: ev.get(k) for k in keys if k in ev}
