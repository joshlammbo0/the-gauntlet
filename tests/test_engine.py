import time

from app import db
from app.engine import claims, curriculum, controller, followup, personas
from app.engine.selector import Selector
from app.knowledge.bank import load_bank


def test_claims_contradiction_numeric_and_polarity_once():
    c1 = claims.extract("We used a WACC of 8.9% and I built the whole model myself", 1, "q1")
    c2 = claims.extract("The discount rate was 11 percent and we built the model together as a team", 3, "q2")
    found = claims.find_contradictions(c1, c2)
    kinds = {f["kind"] for f in found}
    assert "numeric" in kinds and "polarity" in kinds
    # once flagged, not raised again
    again = claims.find_contradictions(c1 + c2, claims.extract("The WACC was 12%", 5, "q3"), already_flagged=[f["key"] for f in found])
    assert again == []
    assert "Which is it" in claims.phrase([f for f in found if f["kind"] == "numeric"][0])


def test_mastery_estimate_bounds_and_shrinkage():
    now = time.time()
    m1, c1 = curriculum._estimate([{"t": now, "score": 1.0, "difficulty": 2}])
    m0, _ = curriculum._estimate([{"t": now, "score": 0.0, "difficulty": 2}])
    assert 2.5 < m1 < 4.0, "one correct answer must not pin mastery at 5"
    assert 1.0 < m0 < 2.5, "one wrong answer must not pin mastery at 0"
    many, conf = curriculum._estimate([{"t": now - i * 3600, "score": 1.0, "difficulty": 3} for i in range(10)])
    assert many > 4.3 and conf > c1
    mixed, _ = curriculum._estimate([{"t": now - i * 3600, "score": 1.0, "difficulty": 3} for i in range(8)] + [{"t": now, "score": 0.0, "difficulty": 2}])
    assert mixed > 3.5, "one miss must not erase demonstrated skill"


def test_skill_map_starts_not_assessed():
    sm = curriculum.skill_map()
    assert any(s["state"] == "not_assessed" for s in sm)
    assert all(s["mastery"] is None for s in sm if s["state"] == "not_assessed")


def test_selector_respects_prereqs_and_no_repeats():
    bank = load_bank()
    state = {"asked": [], "evals": [], "seed": 3}
    sel = Selector(state, {"mode": "death_match", "difficulty": "hard"}, personas.persona("vp"))
    hard = bank["acc_nol_acquisition"]
    assert not sel.prereqs_ok(hard)
    picks = set()
    for _ in range(25):
        q = sel.pick_technical()
        assert q and q["id"] not in picks
        picks.add(q["id"])
        state["asked"].append(q["id"])


def test_followup_classification_reasons():
    p = personas.persona("vp")
    st = {"followup_depth": 0, "time_fraction": 0.2}
    a, r, _ = followup.classify({"kind": "technical", "score": 0.3, "verdict": "partial", "answered_question": True, "misconceptions": [{"id": "x", "explain": "No."}], "missing": []}, None, st, p)
    assert (a, r) == ("probe", "factual_error")
    a, r, _ = followup.classify({"kind": "technical", "score": 0.2, "verdict": "off_topic", "answered_question": False, "misconceptions": [], "missing": []}, None, st, p)
    assert (a, r) == ("probe", "did_not_answer")
    a, r, _ = followup.classify({"kind": "behavioral", "score": 0.5, "answered_question": True, "dimensions": {"ownership": 0.2, "specificity": 0.8}, "delivery": {}}, None, st, p)
    assert (a, r) == ("probe", "weak_contribution")
    a, _, _ = followup.classify({"kind": "technical", "score": 0.9, "verdict": "correct", "answered_question": True, "misconceptions": [], "missing": []}, None, {"followup_depth": 3, "time_fraction": 0.2}, p)
    assert a == "pivot"
    a, _, d = followup.classify({"kind": "technical", "score": 0.9, "verdict": "correct", "answered_question": True, "misconceptions": [], "missing": []}, None, {"followup_depth": 0, "time_fraction": 0.95}, p)
    assert a == "pivot" and d["why"] == "time"


def test_controller_full_flow_persists_and_debriefs():
    iv = controller.Interview.create("death_match", {"persona": "associate", "max_questions": 3, "duration_min": 30})
    turns = iv.start()
    assert turns and iv.state["current"]
    sid = iv.id
    # reload from DB (simulates refresh)
    iv2 = controller.Interview(sid)
    assert iv2.state["current"]["id"] == iv.state["current"]["id"]
    out = iv2.answer("I don't know.", 3.0)
    assert out["interviewer_turns"]
    assert out["evaluation"]["verdict"] == "non_answer"
    n = 0
    while controller.Interview(sid).state["phase"] != "ended" and n < 12:
        iv3 = controller.Interview(sid)
        iv3.answer("Honestly I am not sure about this one.", 4.0)
        n += 1
    from app.engine import debrief
    d = debrief.build(sid)
    assert d["overall"]["n_scored"] >= 3
    assert d["overall"]["score"] < 0.3
    assert d["remediation"]


def test_realistic_mode_hides_scores_until_end():
    iv = controller.Interview.create("superday", {"persona": "vp", "max_questions": 2, "duration_min": 30})
    iv.start()
    out = iv.answer("I'm from Pittsburgh, played tennis, came to Georgetown, worked at Hobo Ventures on royalty valuation, joined GCI and GADIF, and want to move to advisory work in banking.", 40)
    assert "evaluation" not in out
    assert out["state"]["hide_scores"] is True


def test_pause_resume_timer():
    iv = controller.Interview.create("behavioral", {"max_questions": 2})
    iv.start()
    iv.pause()
    e1 = iv.elapsed()
    time.sleep(0.2)
    assert abs(iv.elapsed() - e1) < 0.05
    iv.resume()
    time.sleep(0.1)
    assert iv.elapsed() > e1


def test_retest_queues_weakest_questions():
    iv = controller.Interview.create("death_match", {"max_questions": 2, "duration_min": 30})
    iv.start()
    controller.Interview(iv.id).answer("no idea", 2)
    controller.Interview(iv.id).answer("no idea", 2)
    controller.Interview(iv.id).end()
    rt = controller.Interview.retest_from(iv.id)
    turns = rt.start()
    assert rt.config["queue"] and rt.state["current"]["id"] in rt.config["queue"]


def test_no_repeated_followup_text_in_session():
    iv = controller.Interview.create("behavioral", {"persona": "vp", "max_questions": 3, "duration_min": 30})
    iv.start()
    sid = iv.id
    generic = "That's a great question. I'm passionate about finance and I bring a strong work ethic from tennis. I love valuation."
    for _ in range(10):
        cur = controller.Interview(sid)
        if cur.state["phase"] == "ended":
            break
        cur.answer(generic, 15)
    texts = [t["text"] for t in db.get_turns(sid) if t["role"] == "interviewer" and t["kind"] == "followup"]
    assert len(texts) == len(set(texts)), texts


def test_callback_revisits_missed_skill_in_new_question():
    import random
    hits = 0
    for seed in range(6):
        iv = controller.Interview.create("superday", {"persona": "vp", "max_questions": 12, "duration_min": 60, "categories": ["accounting"], "use_sources": False, "callback_prob": 1.0, "technical_weight": 1.0, "resume_questions": False})
        iv.start()
        sid = iv.id
        # first main question is behavioral (TMAY); answer it, then miss the first technical question
        controller.Interview(sid).answer("I'm from Pittsburgh, play tennis, came to Georgetown, worked at Hobo Ventures and now want banking.", 30)
        while controller.Interview(sid).state["current"]["kind"] != "technical" and controller.Interview(sid).state["phase"] != "ended":
            controller.Interview(sid).answer("I'm from Pittsburgh, play tennis, came to Georgetown, worked at Hobo Ventures and built royalty DCFs with decline curves and a price deck; now I want banking.", 30)
        first = controller.Interview(sid).state["current"]
        controller.Interview(sid).answer("I don't know.", 2)  # miss -> callback pending
        for _ in range(18):
            cur = controller.Interview(sid)
            if cur.state["phase"] == "ended":
                break
            cur.answer("Net income, cash flow statement, balance sheet; it balances because retained earnings move with net income.", 20)
        turns = db.get_turns(sid)
        # other generic answers can miss too and earn their own callbacks; check the one for the first miss
        cb = [t for t in turns if t["role"] == "interviewer" and (t.get("meta") or {}).get("callback_of") == first["id"]]
        if cb:
            hits += 1
            assert cb[0]["question_id"] != first["id"]
            assert "Going back" in cb[0]["text"]
    assert hits >= 1, "no callback fired across 6 sessions"


def test_deep_grade_revise_replaces_observation():
    curriculum.record("dcf.wacc", 0.2, 2, "technical", "qX", "sessX")
    before = db.get_skill("dcf.wacc")
    n = before["n_obs"]
    out = curriculum.revise("dcf.wacc", "qX", "sessX", 0.9)
    after = db.get_skill("dcf.wacc")
    assert out and after["n_obs"] == n and after["history"][-1]["score"] == 0.9 and after["history"][-1].get("revised")
    assert after["mastery"] > before["mastery"]


def test_interrupted_answer_gets_concision_probe():
    iv = controller.Interview.create("superday", {"persona": "vp", "max_questions": 3, "duration_min": 30, "use_sources": False})
    iv.start()
    out = controller.Interview(iv.id).answer("I grew up in Pittsburgh " * 60, 160, None, {"interrupted": True})
    assert any("single most important point" in t["text"] for t in out["interviewer_turns"])
