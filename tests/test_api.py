import io

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_and_meta():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"]
    assert len(client.get("/api/modes").json()) == 14
    assert client.get("/api/personas").json()
    assert client.get("/api/profile").json()["experiences"]
    assert len(client.get("/api/resume-defense").json()) == 18


def test_session_lifecycle_and_appeal():
    r = client.post("/api/sessions", json={"mode": "death_match", "config": {"max_questions": 2, "duration_min": 30}})
    assert r.status_code == 200
    sid = r.json()["session"]["id"]
    assert r.json()["turns"]
    r = client.post("/api/sessions/%s/answer" % sid, json={"text": "I think the WACK is like 9 percent, I forget the rest", "duration": 12, "input_mode": "text"})
    assert r.status_code == 200
    ev = r.json().get("evaluation")
    assert ev and ev["evaluation_id"]
    # appeal with corrected transcript re-evaluates
    r = client.post("/api/evaluations/%s/appeal" % ev["evaluation_id"], json={"corrected_text": "WACC is the weighted average cost of capital: E/V times cost of equity plus D/V times cost of debt times one minus tax, using market values and CAPM."})
    assert r.status_code == 200 and "note" in r.json()
    r = client.get("/api/sessions/%s" % sid)
    assert r.status_code == 200 and r.json()["turns"]
    client.post("/api/sessions/%s/end" % sid)
    d = client.get("/api/sessions/%s/debrief" % sid).json()
    assert d["overall"]["n_scored"] >= 1
    r = client.post("/api/sessions/%s/retest" % sid)
    assert r.status_code == 200


def test_kb_roundtrip_and_resume_defense_filled_flag():
    r = client.post("/api/kb", json={"topic": "hobo", "key": "hobo_price_deck", "claim": "Base case used the NYMEX strip then flat $3.25.", "source": "test", "status": "user"})
    fid = r.json()["id"]
    rd = client.get("/api/resume-defense").json()
    hobo = [b for b in rd if b["experience_id"] == "hobo"][0]
    assert any(u["id"] == "hobo_price_deck" and u["filled"] for u in hobo["unknowns"])
    client.delete("/api/kb/%s" % fid)


def test_skills_endpoint_shape():
    s = client.get("/api/skills").json()
    assert "skills" in s and "longitudinal" in s and s["longitudinal"]["data_sufficiency"] in ("insufficient", "limited", "ok")


def test_questions_browse_and_detail():
    qs = client.get("/api/questions?topic=energy").json()
    assert qs and all(q["topic"] == "energy" for q in qs)
    d = client.get("/api/questions/%s" % qs[0]["id"]).json()
    assert d["solution"]


def test_transcribe_rejects_garbage_gracefully():
    r = client.post("/api/transcribe", files={"audio": ("x.webm", io.BytesIO(b"notaudio"), "audio/webm")}, data={"keep": "0"})
    assert r.status_code in (200, 503)
