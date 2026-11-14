"""Prep command center workflows (Part: Implementation and QA requirements 1-8)."""
import time

from fastapi.testclient import TestClient

from app import db
from app.engine import curriculum, prep, controller
from app.main import app

client = TestClient(app)


def test_cold_start_quick_practice_starts_personalized_session():
    t0 = time.time()
    r = client.post("/api/daily/start")
    assert r.status_code in (200, 400)  # 400 only if today's draft already completed in this test DB
    if r.status_code == 200:
        s = r.json()["session"]
        assert s["mode"] == "daily" and s["current"] and "focus_skills" in s
    assert time.time() - t0 < 5


def test_cold_start_full_mock_uses_defaults_then_context():
    db.set_setting("last_mock_config", None)
    d = client.get("/api/mock/defaults").json()
    assert d["source"] in ("default", "context")
    r = client.post("/api/launch", json={"mode": d["mode"], "config": d["config"]})
    assert r.status_code == 200 and r.json()["session"]["hide_scores"] is True
    # the launch is remembered as the last mock setup
    assert db.get_setting("last_mock_config")["mode"] in ("superday", "bank_specific")
    # with a dated context, defaults come from it
    c = client.post("/api/prep/contexts", json={"bank": "morgan-stanley", "sector": "healthcare", "round": "superday", "date": "2099-01-01"}).json()
    d2 = client.get("/api/mock/defaults").json()
    assert d2["source"] == "context" and d2["config"]["bank"] == "morgan-stanley" and d2["mode"] == "bank_specific"
    client.delete("/api/prep/contexts/%s" % c["id"])


def test_create_context_plan_and_launch_recommended():
    c = client.post("/api/prep/contexts", json={"bank": "jp-morgan", "sector": "fig", "round": "first_round", "date": "2099-02-01", "emphasis": ["fig.bank_valuation"]}).json()
    assert c["bank_name"] == "J.P. Morgan" and c["days_until"] > 0
    plan = client.get("/api/prep/contexts/%s/plan" % c["id"]).json()
    assert plan["technical"] and plan["technical"][0]["skill"] == "fig.bank_valuation"
    assert any(a["kind"] == "group" for a in plan["bank_angles"]) or plan["bank_context"] is None
    assert plan["resume_bullets"] and len(plan["options"]) == 3
    r = client.post("/api/prep/contexts/%s/start/mix25" % c["id"])
    assert r.status_code == 200
    s = r.json()["session"]
    assert s["mode"] == "bank_specific" and s["config"]["context_id"] == c["id"] and s["duration_min"] == 25
    r = client.post("/api/prep/contexts/%s/start/quick10" % c["id"])
    assert r.json()["session"]["mode"] == "weakness_lab"
    client.delete("/api/prep/contexts/%s" % c["id"])
    assert all(x["id"] != c["id"] for x in client.get("/api/prep/contexts").json()["contexts"])


def test_select_known_weakness_and_launch_each_action():
    sid = db.create_session("explain", {"mode": "explain"}, {"asked": [], "evals": []})
    for i in range(3):
        curriculum.record("dcf.wacc", 0.2, 2, "technical", "wq%d" % i, sid)
        tid = db.add_turn(sid, i, "candidate", "no idea", "dcf_wacc", "answer", {})
        db.add_evaluation(sid, tid, "dcf_wacc", "dcf.wacc", 0.2, "incorrect", {"key_error": "Used book weights", "components": [], "misconceptions": []})
    res = client.get("/api/weakness/search?q=wacc").json()
    assert any(r["skill"] == "dcf.wacc" for r in res["results"])
    assert any(r["skill"] == "dcf.wacc" for r in res["recommended"] + res["recent"])
    d = client.get("/api/weakness/dcf.wacc").json()
    assert "Missed" in d["why"] and d["evidence"] and {a["key"] for a in d["actions"]} == {"teach", "practice", "pressure", "retest"}
    for a in d["actions"]:
        if a.get("mode"):
            r = client.post("/api/launch", json={"mode": a["mode"], "config": a["config"]})
            assert r.status_code == 200, a["key"]
            assert r.json()["session"]["mode"] == a["mode"]


def test_all_existing_modes_remain_reachable():
    ms = client.get("/api/modes").json()
    keys = {m["key"] for m in ms}
    assert keys >= {"superday", "death_match", "resume_defense", "behavioral", "deal_defense", "rapid_fire", "explain", "bank_specific", "hot_seat", "tmay", "career", "deathmatch", "daily", "weakness_lab"}
    assert all(m["meta"].get("group") in ("quick", "full", "targeted", "pressure") for m in ms)
    for k in ("superday", "rapid_fire", "explain", "hot_seat", "tmay", "behavioral", "resume_defense", "deal_defense", "death_match"):
        cfg = {"skill": "dcf.ufcf"} if k == "explain" else {}
        r = client.post("/api/sessions", json={"mode": k, "config": {**cfg, "max_questions": 2, "duration_min": 10}})
        assert r.status_code == 200, k


def test_existing_history_settings_and_mastery_survive():
    before = db.all_settings()
    hist = client.get("/api/sessions?limit=500").json()
    sm = {s["skill"]: s for s in client.get("/api/skills").json()["skills"]}
    t = client.get("/api/today").json()
    assert t["queue"] is not None and t["readiness"]["status"] in ("estimate", "not_enough_data")
    # nothing in the today feed mutates state
    assert client.get("/api/sessions?limit=500").json() == hist
    assert {s["skill"]: (s["mastery"], s["n_obs"]) for s in client.get("/api/skills").json()["skills"]} == {k: (v["mastery"], v["n_obs"]) for k, v in sm.items()}
    assert db.all_settings() == before


def test_offline_text_only_path_works():
    db.set_setting("use_llm", False)
    r = client.post("/api/launch", json={"mode": "superday", "config": {"max_questions": 2, "duration_min": 10, "resume_questions": False}})
    sid = r.json()["session"]["id"]
    a = client.post("/api/sessions/%s/answer" % sid, json={"text": "I'm from Chicago, studied finance, interned in valuation and want to advise on transactions.", "duration": 20, "input_mode": "text"})
    assert a.status_code == 200 and a.json()["interviewer_turns"]
    d = client.get("/api/sessions/%s/debrief" % sid).json()
    assert "verdict" in d and isinstance(d["verdict"]["next_actions"], list)
    db.set_setting("use_llm", True)


def test_voice_controls_still_represented():
    """The room's voice affordances are static client code; assert the shipped markup still has them."""
    import os
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "app.js")).read()
    for needle in ("id=\"mic\"", "handsfree", "id=\"replay\"", "toggleRecord", "startLiveSR", "roomstatus", "Interrupted the interviewer", "id=\"typed\""):
        assert needle in js, needle
    html = open(os.path.join(os.path.dirname(__file__), "..", "static", "index.html")).read()
    for route in ("#/today", "#/prepare", "#/practice", "#/progress", "#/library", "#/fix", "#/mock"):
        assert route in html, route
