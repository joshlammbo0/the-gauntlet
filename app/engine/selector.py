"""Adaptive question selection.

Inputs: mode config, persona topic weights, curriculum priority weights, questions already asked in
this session, recent performance, time remaining, prerequisites. Output: the next question (bank
Question, resume-defense dict, or numeric generator spec) wrapped in a uniform dict.
"""
import random
import time
from typing import Dict, List, Optional

from app.knowledge.bank import Question, load_bank, by_skill
from app.knowledge import numeric, sources
from app.knowledge.skills import area_of
from app.profile import resume_defense
from app.engine import curriculum
from app import db

TECH_AREAS = ["accounting", "valuation", "dcf", "ma", "lbo", "fig", "healthcare", "energy", "commercial"]
SECTOR_AREAS = {"healthcare": ["healthcare"], "energy": ["energy"], "power": ["energy"], "fig": ["fig"], "tmt": [], "industrials": [], "m&a": ["ma"], "generalist": [], "sports": []}


def wrap_bank(q: Question) -> Dict:
    return {"id": q.id, "source": "bank", "kind": q.kind, "skill": q.skill, "topic": q.topic, "difficulty": q.difficulty, "text": q.text,
            "answer_type": q.answer_type, "behavioral_category": q.behavioral_category, "tags": q.tags}


def wrap_numeric(gen: Dict) -> Dict:
    return {"id": gen["id"], "source": "numeric", "kind": "numeric", "skill": gen["skill"], "topic": area_of(gen["skill"]), "difficulty": gen["difficulty"],
            "text": gen["text"], "answer_type": "number", "generator": gen["generator"], "seed": gen["seed"], "tags": ["numeric"]}


def wrap_source(rec: Dict) -> Dict:
    return sources.wrap(rec)


def wrap_resume(rq: Dict) -> Dict:
    return {"id": rq["id"], "source": "resume", "kind": "resume", "skill": rq["skill"], "topic": "resume", "difficulty": rq["difficulty"], "text": rq["text"],
            "answer_type": "explain", "bullet_id": rq["bullet_id"], "experience_id": rq["experience_id"], "level": rq["level"], "tags": ["resume-defense"]}


class Selector:
    def __init__(self, state: Dict, config: Dict, persona: Dict):
        self.state = state
        self.config = config
        self.persona = persona
        self.bank = load_bank()
        self.by_skill = by_skill(self.bank)
        self.rng = random.Random(state.get("seed", 0) + len(state.get("asked", [])))
        self.priority = curriculum.priority_weights()
        self.qstats = db.question_stats()
        self.mode = config.get("mode", "superday")
        self.sector = (config.get("sector") or "").lower()

    # ------------------------------------------------------------ helpers
    def asked_ids(self) -> set:
        return set(self.state.get("asked", []))

    def recent_scores(self, n: int = 3) -> List[float]:
        return [t["score"] for t in self.state.get("evals", [])[-n:] if t.get("score") is not None]

    def target_difficulty(self) -> float:
        base = {"easy": 1.5, "medium": 2.5, "hard": 3.5, "brutal": 4.5}.get(self.config.get("difficulty", "medium"), 2.5)
        rs = self.recent_scores()
        if self.mode == "deathmatch":
            return max(1.0, min(6.0, float((self.config.get("deathmatch") or {}).get("ladder", base))))
        if self.mode == "death_match" and rs:
            # ladder: up on success, down on failure
            return max(1.0, min(6.0, self.state.get("ladder", base) + (0.8 if rs[-1] >= 0.75 else (-0.8 if rs[-1] < 0.4 else 0))))
        if rs:
            avg = sum(rs) / len(rs)
            base += 0.6 if avg >= 0.8 else (-0.6 if avg < 0.4 else 0)
        return max(1.0, min(6.0, base))

    def prereqs_ok(self, q: Question) -> bool:
        if not q.prereqs:
            return True
        # satisfied if asked (any score) this session, or skill mastery ≥ 3, or no record and difficulty low
        asked = self.asked_ids()
        for p in q.prereqs:
            pq = self.bank.get(p)
            if p in asked:
                continue
            sk = db.get_skill(pq.skill) if pq else None
            if sk and sk.get("n_obs") and (sk.get("mastery") or 0) >= 3.0:
                continue
            if q.difficulty <= 2:
                continue
            return False
        return True

    def allowed_areas(self) -> List[str]:
        cats = self.config.get("categories") or []
        if cats:
            return [c for c in cats if c in TECH_AREAS]
        areas = ["accounting", "valuation", "dcf", "ma", "lbo", "commercial"]
        for a in SECTOR_AREAS.get(self.sector, []):
            if a not in areas:
                areas.append(a)
        if self.sector in ("generalist", "") and self.mode in ("death_match", "rapid_fire"):
            areas += ["fig", "healthcare", "energy"]
        return areas

    # ------------------------------------------------------------ candidates
    def _weight(self, q: Question, target: float) -> float:
        w = self.priority.get(q.skill, 1.0)
        w *= self.persona.get("topic_weights", {}).get(q.topic, 1.0)
        w *= 1.0 / (1.0 + abs(q.difficulty - target))  # closeness to target difficulty
        st = self.qstats.get(q.id)
        if st:
            days = (time.time() - (st.get("last_asked") or 0)) / 86400
            if (st.get("best_score") or 0) >= 0.85 and days < 7:
                w *= 0.25  # recently nailed: rest it
            elif (st.get("last_score") or 0) < 0.5:
                w *= 1.3  # recently missed: revisit (spaced by curriculum weight too)
        if q.sector and self.sector and q.sector.lower() != self.sector:
            w *= 0.4
        if "sensitive" in q.tags and not self.config.get("include_health_story"):
            w = 0
        if "evidence-check" in q.tags and self.mode in ("rapid_fire", "death_match"):
            w *= 0.3
        return w

    def pick_technical(self, areas: Optional[List[str]] = None, exclude_kinds=("behavioral",)) -> Optional[Dict]:
        target = self.target_difficulty()
        areas = areas or self.allowed_areas()
        asked = self.asked_ids()
        cands = []
        for q in self.bank.values():
            if q.id in asked or q.kind in exclude_kinds or q.topic not in areas:
                continue
            if not self.prereqs_ok(q):
                continue
            w = self._weight(q, target)
            if w > 0:
                cands.append((w, ("bank", q)))
        if self.config.get("use_sources", True):
            src_w = float(self.config.get("source_weight", 0.8))
            for r in sources.all_records():
                if r["id"] in asked or r["area"] not in areas:
                    continue
                w = self.priority.get(r["skill"], 1.0) * self.persona.get("topic_weights", {}).get(r["area"], 1.0) * src_w
                w *= 1.0 / (1.0 + abs(int(r.get("level", 2)) - target))
                st = self.qstats.get(r["id"])
                if st:
                    days = (time.time() - (st.get("last_asked") or 0)) / 86400
                    if (st.get("best_score") or 0) >= 0.85 and days < 7:
                        w *= 0.25
                    elif (st.get("last_score") or 0) < 0.5:
                        w *= 1.3
                if w > 0:
                    cands.append((w, ("source", r)))
        if not cands:
            return None
        kind, item = self._weighted_choice(cands)
        return wrap_bank(item) if kind == "bank" else wrap_source(item)

    def pick_by_skill(self, skill: str, level: Optional[int] = None) -> Optional[Dict]:
        asked = self.asked_ids()
        target = level if level is not None else self.target_difficulty()
        qs = [("bank", q) for q in self.by_skill.get(skill, []) if q.id not in asked]
        if self.config.get("use_sources", True):
            qs += [("source", r) for r in sources.by_skill().get(skill, []) if r["id"] not in asked]
        if not qs:
            return None
        def lv(item):
            return item[1].level if item[0] == "bank" else int(item[1].get("level", 2))
        qs.sort(key=lambda it: (abs(lv(it) - target), 0 if it[0] == "bank" else 1, self.rng.random()))
        kind, item = qs[0]
        return wrap_bank(item) if kind == "bank" else wrap_source(item)

    def pick_behavioral(self, category: Optional[str] = None) -> Optional[Dict]:
        asked = self.asked_ids()
        cands = []
        for q in self.bank.values():
            if q.kind != "behavioral" or q.id in asked:
                continue
            if category and q.behavioral_category != category:
                continue
            if "sensitive" in q.tags and not self.config.get("include_health_story"):
                continue
            w = self.priority.get(q.skill, 1.0) * self.persona.get("topic_weights", {}).get("behavioral", 1.0)
            # bank-specific questions need bank context
            if q.id in ("beh_why_bank",) and not self.config.get("bank"):
                w *= 0.3
            cands.append((w, q))
        if not cands:
            return None
        return wrap_bank(self._weighted_choice(cands))

    def pick_resume(self, experience_id: Optional[str] = None, level: Optional[str] = None) -> Optional[Dict]:
        asked = self.asked_ids()
        pool = [r for r in resume_defense.question_pool(experience_id) if r["id"] not in asked]
        if level:
            pool = [r for r in pool if r["level"] == level] or pool
        if not pool:
            return None
        cands = [(self.priority.get(r["skill"], 1.0) * (1.3 if r["experience_id"] in ("hobo", "gadif", "gci") else 1.0), r) for r in pool]
        return wrap_resume(self._weighted_choice(cands))

    def pick_numeric(self, skill_hint: Optional[str] = None) -> Dict:
        names = list(numeric.GENERATORS)
        if skill_hint:
            names = [n for n in names if numeric.GENERATORS[n].skill == skill_hint] or names
        target = self.target_difficulty()
        weights = [((1.0 / (1 + abs(numeric.GENERATORS[n].difficulty - target))) * self.priority.get(numeric.GENERATORS[n].skill, 1.0), n) for n in names]
        name = self._weighted_choice(weights)
        return wrap_numeric(numeric.generate(name, self.rng.randrange(1 << 30)))

    def pick_deal(self) -> Optional[Dict]:
        asked = self.asked_ids()
        deal_qs = [q for q in self.bank.values() if (q.skill in ("deal.thesis", "deal.transaction") or q.topic in ("commercial",) and "pitch" in q.subtopic) and q.id not in asked]
        focus = (self.config.get("deal_focus") or "").lower()
        if focus:
            f = [q for q in deal_qs if focus in q.text.lower() or focus in q.id]
            deal_qs = f or deal_qs
        if not deal_qs:
            return None
        return wrap_bank(self.rng.choice(deal_qs))

    def _weighted_choice(self, cands):
        total = sum(w for w, _ in cands)
        r = self.rng.random() * total
        acc = 0.0
        for w, item in cands:
            acc += w
            if acc >= r:
                return item
        return cands[-1][1]

    # ------------------------------------------------------------ mode policy
    def next_main(self) -> Optional[Dict]:
        """Choose the next MAIN question according to mode, phase and the technical/behavioral mix."""
        n = len(self.state.get("asked", []))
        mode = self.mode
        queue = self.config.get("queue") or []
        for qid in queue:
            if qid in self.asked_ids():
                continue
            if qid in self.bank:
                return wrap_bank(self.bank[qid])
            rec = sources.get(qid)
            if rec:
                return wrap_source(rec)
        if queue:
            return None
        if mode in ("death_match", "deathmatch"):
            if mode == "deathmatch":
                dm = self.config.get("deathmatch") or {}
                if dm.get("boss_pending"):
                    saved = self.state.get("ladder")
                    self.state["ladder"] = max(4.0, float(dm.get("ladder", 2.5)))
                    q = self.pick_technical()
                    self.state["ladder"] = saved
                    return q
            return self.pick_technical()
        if mode in ("daily", "weakness_lab"):
            focus = list(self.config.get("focus_skills") or [])
            n_focus = len([a for a in self.state.get("asked", []) if a])
            surprise = int(self.config.get("surprise", 0))
            # cycle through focus skills first; surprises come from the general pool at the end
            if focus and n_focus < len(focus) * 1 + (0 if surprise else 0):
                skill = focus[n_focus % len(focus)]
                q = self.pick_by_skill(skill)
                if q:
                    return q
            return self.pick_technical() or self.pick_behavioral()
        if mode == "career":
            pass  # falls through to the superday mix below
        if mode == "rapid_fire":
            # alternate numeric and short conceptual (numeric only in the Mental Math Arena)
            if n % 2 == 0 or self.config.get("numeric_only"):
                return self.pick_numeric()
            q = self.pick_technical(exclude_kinds=("behavioral",))
            return q
        if mode == "resume_defense":
            return self.pick_resume(self.config.get("experience_id"), "basic" if n < 4 else None) or self.pick_behavioral()
        if mode == "behavioral":
            if n == 0 and self.config.get("start_with_tmay", True):
                q = self.bank.get("beh_tmay")
                return wrap_bank(q) if q and q.id not in self.asked_ids() else self.pick_behavioral()
            return self.pick_behavioral(self.config.get("behavioral_category"))
        if mode == "deal_defense":
            return self.pick_deal() or self.pick_technical(["commercial", "dcf", "valuation"])
        if mode == "tmay":
            return wrap_bank(self.bank["beh_tmay"]) if "beh_tmay" not in self.asked_ids() else wrap_bank(self.bank["beh_walk_resume"])
        if mode == "explain":
            skill = self.config.get("skill")
            return self.pick_by_skill(skill) if skill else self.pick_technical()
        # superday / bank_specific / hot_seat: mix by persona emphasis and config weighting
        tech_w = float(self.config.get("technical_weight", 0.6))
        emph = self.persona.get("emphasis", {"technical": 0.5, "resume": 0.3, "behavioral": 0.2})
        phase = self.state.get("phase", "opening")
        if n == 0:
            # realistic opener: TMAY or why-bank/why-ib
            opener = self.bank.get("beh_tmay")
            if self.config.get("bank") and self.rng.random() < 0.3:
                opener = self.bank.get("beh_why_bank")
            return wrap_bank(opener)
        if n == 1 and "beh_why_ib" not in self.asked_ids() and self.rng.random() < 0.7:
            return wrap_bank(self.bank["beh_why_ib"])
        r = self.rng.random()
        p_tech = tech_w * (emph["technical"] + emph["resume"]) / max(emph["technical"] + emph["resume"], 1e-9)
        p_tech = 0.5 * p_tech + 0.5 * tech_w
        if r < p_tech * (emph["technical"] / (emph["technical"] + emph["resume"])):
            q = self.pick_technical()
            if q:
                return q
        if r < p_tech and self.config.get("resume_questions", True):
            q = self.pick_resume()
            if q:
                return q
        if r < p_tech:
            q = self.pick_technical()
            if q:
                return q
        q = self.pick_behavioral()
        return q or self.pick_technical() or self.pick_resume()
