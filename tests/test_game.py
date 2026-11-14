import datetime

from app import db
from app.engine import controller, game, curriculum
from app.knowledge import modeling


def _answer_all(sid, text, n=30):
    for _ in range(n):
        iv = controller.Interview(sid)
        if iv.state["phase"] == "ended":
            break
        iv.answer(text, 10)


def test_xp_persists_and_levels():
    game.init()
    before = game.total_xp()
    game.award_xp(50, "test")
    assert game.total_xp() == before + 50
    assert game.level_for(0)["name"] == "Prospect" and game.level_for(5000)["level"] > game.level_for(0)["level"]


def test_xp_farming_has_diminishing_returns():
    db.bump_question("acc_three_statements", 1.0)
    db.bump_question("acc_three_statements", 1.0)
    db.bump_question("acc_three_statements", 1.0)
    fresh = game.xp_for_answer(1.0, 2, "some_never_asked_question", "technical")
    farmed = game.xp_for_answer(1.0, 2, "acc_three_statements", "technical")
    assert farmed < fresh * 0.5


def test_mastery_not_inflated_by_repeating_same_question():
    # other tests share this database and may already have recorded answers on these skills
    with db.conn() as c:
        c.execute("DELETE FROM skills WHERE skill IN ('valuation.comps', 'valuation.precedents')")
    for _ in range(6):
        curriculum.record("valuation.comps", 1.0, 2, "technical", "val_comps_process", "s1")
    rep = db.get_skill("valuation.comps")
    for i in range(6):
        curriculum.record("valuation.precedents", 1.0, 2, "technical", "q%d" % i, "s1")
    var = db.get_skill("valuation.precedents")
    assert var["mastery"] > rep["mastery"], "distinct questions must count for more than the same question repeated"
    assert curriculum.state_of(rep["mastery"], rep["n_obs"], rep["confidence"], False) != "mastered"


def test_deathmatch_lives_end_run_and_record():
    iv = controller.Interview.create("deathmatch", {"use_sources": False})
    iv.start()
    sid = iv.id
    _answer_all(sid, "I don't know.", n=8)
    s = db.get_session(sid)
    assert s["status"] == "ended"
    assert s["config"]["deathmatch"]["lives"] == 0
    rec = game.deathmatch_records()
    assert rec["runs"] >= 1
    assert s["summary"]["deathmatch"]["questions"] == 3


def test_deathmatch_streak_scores_and_boss():
    dm = game.deathmatch_config()["deathmatch"]
    for i in range(6):
        game.deathmatch_update(dm, 1.0, 2)
    assert dm["lives"] == 3 and dm["streak"] == 6 and dm["score"] > 6 * 22
    assert dm["questions"] == 6 and dm["ladder"] > 1.5


def test_career_pass_advances_stage_and_rematch_differs():
    game.init()
    iv = controller.Interview.create("career", {"bank": "lazard", "use_sources": False, "max_questions": 4})
    turns = iv.start()
    first_ids = [t["question_id"] for t in turns if t["question_id"]]
    sid = iv.id
    _answer_all(sid, "I don't know.", n=12)
    s = db.get_session(sid)
    res = s["summary"]["career"]
    assert res and res["passed"] is False and res["new_stage"] == 0
    assert game.campaign("lazard")["attempts"] == 1
    iv2 = controller.Interview.create("career", {"bank": "lazard", "use_sources": False, "max_questions": 4})
    t2 = iv2.start()
    # rematch allowed immediately; opener may repeat (TMAY) but the session is new and progress intact
    assert iv2.id != sid and game.campaign("lazard")["stage"] == 0


def test_career_resolution_passes_with_good_scores(monkeypatch):
    game.init()
    iv = controller.Interview.create("career", {"bank": "evercore", "use_sources": False, "max_questions": 3})
    iv.start()
    sid = iv.id
    # force high scores by writing evals directly, then end
    iv = controller.Interview(sid)
    iv.state["evals"] = [{"evaluation_id": "x%d" % i, "question_id": "q%d" % i, "skill": "dcf.ufcf", "score": 0.9, "verdict": "correct", "kind": "technical"} for i in range(4)]
    iv.end()
    res = db.get_session(sid)["summary"]["career"]
    assert res["passed"] and res["new_stage"] == 1
    assert game.campaign("evercore")["stage"] == 1


def test_daily_date_rules_and_streak():
    game.init()
    st = game.daily_status()
    assert st["date"] == datetime.date.today().isoformat()
    iv = controller.Interview.create("daily", {"use_sources": False, "max_questions": 2})
    iv.start()
    _answer_all(iv.id, "Net income flows to the cash flow statement and retained earnings; ending cash hits the balance sheet.", n=25)
    st2 = game.daily_status()
    assert st2["completed"] and st2["streak"] >= 1 and st2["session_id"] == iv.id


def test_modeling_challenges_grade_deterministically():
    modeling.self_test()
    ch = modeling.generate("accretion", 3)
    g = modeling.grade("accretion", 3, {s["id"]: s["answer"] for s in ch["steps"]})
    assert g["score"] == 1.0
    g2 = modeling.grade("accretion", 3, {"eps0": 1.0})
    assert g2["score"] < 0.3 and all("expected" in r for r in g2["results"])


def test_lab_diagnoses_prerequisite_root():
    from app.engine import lab
    for i in range(4):
        curriculum.record("dcf.cost_of_equity", 0.1, 2, "technical", "ceq%d" % i, "s")
    d = lab.diagnose("dcf.wacc")
    assert "dcf.cost_of_equity" in [w["skill"] for w in d["weak_prerequisites"]]
    assert d["root_cause"] != "dcf.wacc"
    t = lab.teach("dcf.wacc")
    assert t["short"] and t["worked_example"]
