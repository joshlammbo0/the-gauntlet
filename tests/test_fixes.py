"""Regression tests for the flaws found by playing the game (rubric matching, Deathmatch rules, farming, state races)."""
import re

from fastapi.testclient import TestClient

from app import db
from app.engine import controller, evaluator, game
from app.knowledge import sources
from app.knowledge.bank import Question
from app.main import app

client = TestClient(app)


# ------------------------------------------------------------------ derived rubrics
def _labels(comps):
    return {c.text for c in comps}


def test_vocab_matches_whole_words_only():
    ans = ("The target can sell the debt to investors; the operating business keeps running. Please see the release "
           "notes. Widespread adoption of IFRS helped, and the improved version is unprecedented.")
    labels = _labels(sources.derive_components(ans, "Some question?"))
    for bogus in ("Mentions pre-tax income", "Mentions credit rating", "Mentions leases", "Mentions options",
                  "Mentions spreads", "Mentions reserves", "Mentions precedent transactions", "Mentions recurring revenue"):
        assert bogus not in labels, bogus


def test_candidate_saying_debt_does_not_count_as_pre_tax_income():
    comps = sources.derive_components("Pre-tax income falls, so net income falls.", "Q?")
    q = Question(id="src_test_pti", topic="accounting", subtopic="", skill="accounting.three_statements", difficulty=2, text="Q?",
                 components=comps, solution="x")
    ev = evaluator.evaluate_technical(q, "The company has more debt and the operating business is fine overall here.", use_llm=False)
    pti = next(c for c in ev["components"] if c["text"] == "Mentions pre-tax income")
    assert not pti["present"]


def test_list_numbers_are_not_figures_and_concepts_have_no_figures():
    ans = "There are two types: 1) maintenance and 2) incurrence covenants. A beta of >1 means more volatile."
    assert not [c for c in sources.derive_components(ans, "What are the types of covenants?") if c.id.startswith("n_")]
    calc = sources.derive_components("Step 1: EBITDA is 100. 2) Multiply by 10x to get 1,000 of EV.", "EBITDA is 100 at 10x?", calculation=True)
    figs = {c.text for c in calc if c.id.startswith("n_")}
    assert "States the figure 1" not in figs and "States the figure 2" not in figs


def test_page_header_is_stripped():
    assert sources.strip_page_header("Greenmail is rare nowadays. MERGERS & ACQUISTIONS") == "Greenmail is rare nowadays."
    assert sources.strip_page_header("Use EV/EBITDA.") == "Use EV/EBITDA."


# ------------------------------------------------------------------ evaluator
def _derived_q():
    comps = sources.derive_components("Free cash flow is cash flow from operations minus capex; a company may need to restructure.", "What is FCF?")
    return Question(id="src_test_fcf", topic="dcf", subtopic="", skill="dcf.ufcf", difficulty=2, text="How do you calculate FCF?", components=comps, solution="x")


def test_keyword_salad_is_capped_below_a_real_answer():
    q = _derived_q()
    salad = "net income depreciation amortization non-cash working capital capex cash flow statement free cash flow balance sheet taxes interest debt"
    good = "Free cash flow is cash flow from operations minus capex, the cash left after reinvesting that can repay debt or go to shareholders."
    s = evaluator.evaluate_technical(q, salad, use_llm=False)
    g = evaluator.evaluate_technical(q, good, use_llm=False)
    assert s["keyword_list"] and s["score"] <= 0.3 and s["verdict"] == "incorrect"
    assert g["score"] > s["score"] + 0.3
    assert not evaluator.is_keyword_list("so it's basically cash from operations minus capex and that is what's left over")


def test_model_carries_more_weight_on_derived_rubrics(monkeypatch):
    q = _derived_q()
    payload = {"components": [], "misconceptions": [], "answered_question": True, "correctness": 0.9, "depth": 0.8, "clarity": 0.9,
               "key_error": "Minor gap.", "stronger_answer": "", "notes": ""}
    monkeypatch.setattr(evaluator.provider, "active_provider", lambda pref="auto": "claude_cli")
    monkeypatch.setattr(evaluator.provider, "complete_json", lambda *a, **k: (payload, "claude_cli"))
    # an answer that avoids the guide's exact vocabulary scores ~0 on keywords
    ans = "You take the cash the business generates from running itself and subtract what it spends on new equipment."
    det = evaluator.evaluate_technical(q, ans, use_llm=False)["score"]
    ev = evaluator.evaluate_technical(q, ans, use_llm=True)
    assert det < 0.3
    assert ev["score"] >= 0.5, "a model-confirmed correct answer must clear the Deathmatch life threshold"


# ------------------------------------------------------------------ Deathmatch rules
def _deathmatch():
    iv = controller.Interview.create("deathmatch", {"use_sources": False})
    iv.start()
    return iv.id


def test_skip_costs_a_life_and_can_end_the_run():
    sid = _deathmatch()
    for _ in range(3):
        if db.get_session(sid)["status"] == "ended":
            break
        controller.Interview(sid).skip()
    s = db.get_session(sid)
    assert s["config"]["deathmatch"]["lives"] == 0
    assert s["status"] == "ended" or controller.Interview(sid).state["phase"] == "ended"


def test_deathmatch_shows_verdicts_and_hidden_modes_use_neutral_acks():
    """Hidden-score modes never voice the verdict: reactions come from the persona's neutral set (or are skipped),
    never from the revealing banks (strong/partial/wrong/math)."""
    from app.engine import speech_style as ss
    assert controller.MODES["deathmatch"]["hide_scores"] is False
    iv = controller.Interview.create("superday", {"persona": "vp"})
    revealing = {line for sit in ("strong", "partial", "wrong", "math", "insight") for lines in ss.REACTIONS[sit].values() for line in lines}
    for score in (0.1, 0.95):
        for _ in range(20):
            a = iv._ack({"score": score, "verdict": "correct" if score > 0.5 else "incorrect", "kind": "technical"})
            assert a == "" or a in ss.NEUTRAL["vp"]
            assert a not in revealing


def test_pivot_transitions_fit_the_next_question():
    tech = {"kind": "technical", "source": "bank"}
    assert not controller._pivot_fits("Let's go to your resume.", tech)
    assert controller._pivot_fits("Let's go to your resume.", {"kind": "resume", "source": "resume"})
    assert not controller._pivot_fits("Last question.", tech)
    assert controller._pivot_fits("Different topic.", tech)


def test_boss_question_is_not_replaced_by_a_callback():
    sid = _deathmatch()
    iv = controller.Interview(sid)
    iv.config["deathmatch"]["boss_pending"] = True
    iv.state["callback_pending"] = [{"skill": "accounting.three_statements", "question_id": "x", "asked_at": -5, "key": None}]
    iv.config["callback_prob"] = 1.0
    turns = iv._pivot(ack="Okay.")
    assert turns and "Going back to something from earlier" not in turns[-1]["text"]


def test_uncertain_deathmatch_answers_wait_for_the_model():
    sid = _deathmatch()
    iv = controller.Interview(sid)
    cur = {"source": "bank"}
    assert iv._needs_final_grade_now(cur, {"score": 0.4, "verdict": "partial"})
    assert not iv._needs_final_grade_now(cur, {"score": 0.9, "verdict": "correct"})
    assert not iv._needs_final_grade_now(cur, {"score": 0.0, "verdict": "non_answer"})
    assert not iv._needs_final_grade_now(cur, {"score": 0.3, "verdict": "incorrect", "keyword_list": True})
    assert not iv._needs_final_grade_now({"source": "numeric"}, {"score": 0.0, "verdict": "incorrect"})


# ------------------------------------------------------------------ farming and abandoned runs
def test_modeling_resubmission_pays_once():
    ch = client.get("/api/modeling/new/paper_lbo_full").json()
    body = {"name": "paper_lbo_full", "seed": ch["seed"], "answers": {"equity": "400"}, "seconds": 300}
    first = client.post("/api/modeling/grade", json=body).json()
    second = client.post("/api/modeling/grade", json=body).json()
    assert first["xp"] > 0 and not first["repeat"]
    assert second["xp"] == 0 and second["repeat"]
    hist = [h for h in (db.get_skill("lbo.paper_lbo") or {}).get("history", []) if h.get("q") == "mod_paper_lbo_full_%s" % ch["seed"]]
    assert len(hist) == 1


def test_starting_deathmatch_resumes_the_open_run():
    a = client.post("/api/deathmatch/start", json={}).json()
    b = client.post("/api/deathmatch/start", json={}).json()
    assert b.get("resumed") and b["session"]["id"] == a["session"]["id"]
    client.post("/api/sessions/%s/end" % a["session"]["id"])
    c = client.post("/api/deathmatch/start", json={}).json()
    assert c["session"]["id"] != a["session"]["id"]
    client.post("/api/sessions/%s/end" % c["session"]["id"])


def test_starting_career_resumes_the_open_interview():
    a = client.post("/api/career/goldman-sachs/start").json()
    b = client.post("/api/career/goldman-sachs/start").json()
    assert b.get("resumed") and b["session"]["id"] == a["session"]["id"]
    client.post("/api/sessions/%s/end" % a["session"]["id"])


# ------------------------------------------------------------------ deep grades are never reverted
def test_saving_a_stale_state_keeps_a_landed_deep_grade():
    iv = controller.Interview.create("death_match", {"max_questions": 5})
    iv.start()
    iv.answer("I don't really know, something about cash.")
    sid = iv.id
    stale = controller.Interview(sid)  # a request that loaded state before the deep grade landed
    e = stale.state["evals"][-1]
    row = db.get_evaluation(e["evaluation_id"])
    data = dict(row["data"], deep_graded_at=1.0, provisional=False, verdict="partial", score=0.55)
    db.update_evaluation(e["evaluation_id"], data, 0.55, "partial", 0)
    stale.save()
    fresh = db.get_session(sid)["state"]["evals"][-1]
    assert fresh["score"] == 0.55 and fresh["deep"]
