"""Weakness Lab: diagnosis (which prerequisite is actually weak), teaching material (Teach Me Why) and
fresh reattempts. Deterministic from the question bank and ingested guides; the model, when connected,
only refines wording."""
from typing import Dict, List, Optional

from app import db
from app.engine import curriculum
from app.knowledge.bank import load_bank, by_skill
from app.knowledge.skills import SKILLS, prereqs_of, area_of
from app.knowledge import sources, numeric


def diagnose(skill: str) -> Dict:
    """Walk the prerequisite graph: the deepest weak prerequisite is the thing to fix first."""
    sm = {s["skill"]: s for s in curriculum.skill_map()}
    chain: List[Dict] = []
    seen = set()

    def walk(sk, depth):
        if sk in seen or depth > 4:
            return
        seen.add(sk)
        for p in prereqs_of(sk):
            walk(p, depth + 1)
        s = sm.get(sk)
        if s:
            chain.append({"skill": sk, "name": SKILLS.get(sk, sk), "state": s["mastery_state"], "mastery": s["mastery"], "n_obs": s["n_obs"], "depth": depth, "levels": s.get("levels", {})})
    walk(skill, 0)
    weak_prereqs = [c for c in chain if c["skill"] != skill and c["state"] in ("learning", "developing")]
    untested_prereqs = [c for c in chain if c["skill"] != skill and c["state"] == "untested"]
    root = weak_prereqs[0]["skill"] if weak_prereqs else skill
    # recent mistakes on this skill
    evals = [e for e in db.all_evaluations(400) if e.get("skill") == skill and (e.get("score") or 0) < 0.6]
    mistakes = []
    for e in evals[:5]:
        d = e.get("data", {})
        mistakes.append({"question_id": e.get("question_id"), "key": d.get("key_error") or d.get("key_weakness"), "misconceptions": [m.get("explain") for m in d.get("misconceptions", [])], "score": e.get("score"), "when": e.get("created")})
    # level profile: where does it break (definition vs mechanics vs application)?
    lv = (sm.get(skill) or {}).get("levels", {})
    weakest_level = None
    for k in sorted(lv, key=lambda x: int(x)):
        if lv[k].get("avg") is not None and lv[k]["avg"] < 0.6:
            weakest_level = int(k)
            break
    return {"skill": skill, "name": SKILLS.get(skill, skill), "root_cause": root, "root_name": SKILLS.get(root, root), "chain": chain,
            "weak_prerequisites": weak_prereqs, "untested_prerequisites": untested_prereqs, "recent_mistakes": mistakes, "weakest_level": weakest_level,
            "advice": ("Fix %s first; it underpins %s." % (SKILLS.get(root, root), SKILLS.get(skill, skill))) if root != skill else
                      ("Foundations hold; the gap is in %s itself%s." % (SKILLS.get(skill, skill), (" at level %d (%s)" % (weakest_level, ["", "definition", "mechanics", "understanding", "application", "exceptions"][weakest_level])) if weakest_level else ""))}


def teach(skill: str) -> Dict:
    """Layered explanation built from authored solutions (short → detailed), a worked numeric example when a
    generator exists, source excerpts by level, and related concepts."""
    bank = load_bank()
    qs = sorted(by_skill(bank).get(skill, []), key=lambda q: (q.level, q.difficulty))
    short = qs[0].solution if qs else ""
    detailed = [{"question": q.text, "explanation": q.solution, "level": q.level, "assumptions": q.assumptions,
                 "misconceptions": [m.explain for m in q.misconceptions]} for q in qs[:4]]
    suffix = skill.split(".")[-1]
    gens = [n for n in numeric.GENERATORS if numeric.GENERATORS[n].skill == skill or numeric.GENERATORS[n].skill.split(".")[-1] == suffix
            or (suffix in ("wacc", "cost_of_equity") and n in ("wacc_calc", "capm")) or (suffix == "accretion_dilution" and n.startswith("accretion"))
            or (suffix in ("returns", "paper_lbo") and n in ("irr_from_moic", "paper_lbo")) or (suffix == "ev_equity" and n == "ev_bridge")
            or (suffix == "depreciation" and n == "depreciation_walk") or (suffix == "interests" and n == "royalty_nri")]
    worked = None
    if gens:
        g = numeric.generate(gens[0], 7)
        worked = {"prompt": g["text"], "solution": g["solution"], "answer": g["answer"], "unit": g.get("unit")}
    src = sorted(sources.by_skill().get(skill, []), key=lambda r: (r.get("level", 2), r.get("answer_words", 0)))
    excerpts = [{"question": r["question"], "answer": r["answer"][:900], "level": r.get("level"), "citation": sources.citation(r)} for r in src[:3]]
    related = prereqs_of(skill) + [k for k, v in __import__("app.knowledge.skills", fromlist=["PREREQS"]).PREREQS.items() if skill in v]
    return {"skill": skill, "name": SKILLS.get(skill, skill), "short": short, "detailed": detailed, "worked_example": worked,
            "source_excerpts": excerpts, "related": [{"skill": r, "name": SKILLS.get(r, r)} for r in related],
            "note": "Explanations come from the authored rubric solutions and your local guides (cited). Nothing here is generated from thin air."}


def plan_config(skill: Optional[str] = None) -> Dict:
    """Session config for a Weakness Lab run: focus skills = root causes of current weaknesses + due reviews."""
    tech = lambda sk: sk.split(".")[0] not in ("behavioral", "resume", "deal")  # noqa: E731
    targets = [skill] if skill else [w["skill"] for w in curriculum.weaknesses(8) if tech(w["skill"])][:4] + [d["skill"] for d in curriculum.due_for_review(4) if tech(d["skill"])][:2]
    focus: List[str] = []
    diags = []
    for t in targets:
        if not t:
            continue
        d = diagnose(t)
        diags.append({"skill": t, "root": d["root_cause"], "advice": d["advice"]})
        for sk in ([d["root_cause"]] if d["root_cause"] != t else []) + [t]:
            if sk not in focus:
                focus.append(sk)
    if not focus:
        # nothing assessed yet: start with foundations
        focus = ["accounting.three_statements", "valuation.ev_equity", "dcf.ufcf"]
    return {"persona": "analyst", "difficulty": "medium", "duration_min": 20, "focus_skills": focus[:5], "diagnoses": diags, "use_sources": True, "max_questions": 14}


def reattempt_question(evaluation_id: str) -> Optional[Dict]:
    """A fresh question on the same skill (never the same id); numeric generators get a new seed."""
    ev = db.get_evaluation(evaluation_id)
    if not ev:
        return None
    qid, skill = ev.get("question_id"), ev.get("skill")
    from app.engine import selector as selector_mod, personas
    state = {"asked": [qid], "evals": [], "seed": int(__import__("time").time()) % 100000}
    sel = selector_mod.Selector(state, {"mode": "explain", "difficulty": "medium", "use_sources": True}, personas.persona("analyst"))
    if qid and qid.startswith("num_"):
        parts = qid.split("_")
        name = "_".join(parts[1:-1])
        return selector_mod.wrap_numeric(numeric.generate(name))
    q = sel.pick_by_skill(skill) if skill else None
    return q
