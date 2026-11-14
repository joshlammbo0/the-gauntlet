"""FastAPI application for The Gauntlet."""
import os
import shutil
import tempfile
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import __version__, db
from app.engine import controller, curriculum, personas
from app.engine.evaluator import evaluate_technical, evaluate_numeric
from app.engine.behavioral import evaluate_behavioral
from app.knowledge import banks, numeric, sources, ingest
from app.knowledge.bank import load_bank, validate_bank
from app.knowledge.skills import SKILLS, AREAS
from app.llm import provider
from app.profile import facts, resume_defense
from app.speech import stt, tts

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "..", "static")

app = FastAPI(title="The Gauntlet", version=__version__)


@app.on_event("startup")
def _startup() -> None:
    db.init()
    errs = validate_bank(load_bank())
    if errs:
        print("QUESTION BANK ERRORS:\n" + "\n".join(errs))
    if db.get_setting("preload_whisper", True):
        stt.preload_async()
    if db.get_setting("tts_engine", "auto") in ("auto", "kokoro"):
        tts.start_kokoro()


# ------------------------------------------------------------------ models
class SessionCreate(BaseModel):
    mode: str
    config: Dict[str, Any] = {}


class AnswerIn(BaseModel):
    text: str
    duration: Optional[float] = None
    pauses: Optional[List[float]] = None
    transcript_id: Optional[str] = None
    raw_transcript: Optional[str] = None
    input_mode: Optional[str] = None  # voice | text
    interrupted: bool = False


class KBIn(BaseModel):
    id: Optional[str] = None
    topic: str
    key: Optional[str] = None
    claim: str
    source: str = "the candidate (entered in KB)"
    status: str = "user"


class AppealIn(BaseModel):
    argument: Optional[str] = None
    corrected_text: Optional[str] = None


class TTSIn(BaseModel):
    text: str
    voice: Optional[str] = None
    rate: Optional[int] = None
    persona: Optional[str] = None
    expressive: bool = True
    pause_scale: float = 1.0


class SettingsIn(BaseModel):
    settings: Dict[str, Any]


# ------------------------------------------------------------------ meta
@app.get("/api/health")
def health():
    s = db.all_settings()
    pref = s.get("llm_provider", "auto")
    active = provider.active_provider(pref)
    from app.llm.worker import POOL
    return {"ok": True, "version": __version__, "time": time.time(), "llm": provider.STATUS.to_dict(active), "llm_preference": pref, "workers": POOL.status(),
            "whisper": stt.status(), "tts": {"available": tts.available(), "voices": [v["name"] for v in tts.voices() if v["preferred"]][:12], "premium_installed": tts.premium_installed(),
                                              "neural": tts.kokoro_installed(), "engine": tts.engine(s.get("tts_engine", "auto"))},
            "bankvault": banks.available(), "questions": len(load_bank()), "numeric_generators": sorted(numeric.GENERATORS),
            "settings": s}


@app.post("/api/llm/probe")
def llm_probe():
    provider.STATUS.api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    provider.STATUS.cli_path = provider.find_claude_cli()
    ok = provider.STATUS.probe_cli()
    return {"cli_logged_in": ok, "status": provider.STATUS.to_dict(provider.active_provider(db.get_setting("llm_provider", "auto")))}


@app.get("/api/modes")
def modes():
    return [{"key": k, **v, "meta": controller.MODE_META.get(k, {})} for k, v in controller.MODES.items()]


@app.get("/api/personas")
def get_personas():
    return personas.list_personas()


@app.get("/api/banks")
def get_banks():
    return banks.list_banks()


@app.get("/api/banks/{slug}")
def get_bank(slug: str, sector: Optional[str] = None, group: Optional[str] = None):
    b = banks.bank(slug)
    if not b:
        raise HTTPException(404, "no research for this bank")
    return {"bank": {k: b[k] for k in ("slug", "name", "description", "sectorTags", "productTags", "offices")},
            "groups": [{k: g.get(k) for k in ("id", "name", "sector", "subsectors", "principalOffice", "tier")} for g in b["groups"]],
            "context": banks.context_for_interview(slug, group, sector)}


@app.get("/api/profile")
def profile():
    return {"profile": facts.PROFILE, "experiences": facts.EXPERIENCES, "stories": facts.STORIES, "tmay": facts.TMAY_SPINE,
            "why_bank": facts.WHY_BANK_MATERIAL, "known_weaknesses": facts.KNOWN_WEAKNESSES, "discrepancies": facts.discrepancy_report(),
            "kb": db.kb_list()}


@app.get("/api/resume-defense")
def resume_def():
    kb = db.kb_list()
    filled = {f["key"] for f in kb if f.get("key")}
    out = resume_defense.bullets()
    for b in out:
        for u in b["unknowns"]:
            u["filled"] = u["id"] in filled
    return out


@app.get("/api/kb")
def kb_list(topic: Optional[str] = None):
    return db.kb_list(topic)


@app.post("/api/kb")
def kb_add(item: KBIn):
    fid = db.kb_upsert(item.topic, item.key, item.claim, item.source, item.status, item.id)
    return {"id": fid}


@app.delete("/api/kb/{fid}")
def kb_del(fid: str):
    db.kb_delete(fid)
    return {"ok": True}


@app.get("/api/skills")
def skills():
    return {"areas": AREAS, "skills": curriculum.skill_map(), "weaknesses": curriculum.weaknesses(), "due": curriculum.due_for_review(),
            "remediation": curriculum.remediation_plan(), "longitudinal": curriculum.longitudinal(), "readiness": curriculum.readiness(),
            "states": curriculum.STATES}


@app.get("/api/sources")
def sources_report():
    rep = sources.report()
    paths = ingest.discover_sources()
    return {"report": rep, "discovered": paths, "core_records": len(sources.all_records()), "send_guide_excerpts": db.get_setting("send_guide_excerpts", True)}


@app.post("/api/sources/import")
def sources_import():
    rep = ingest.run(write=True)
    n = sources.reload()
    return {"report": rep, "loaded": n}


@app.get("/api/questions")
def questions(topic: Optional[str] = None, skill: Optional[str] = None, q: Optional[str] = None, origin: Optional[str] = None):
    bank = load_bank()
    stats = db.question_stats()
    out = []
    if origin in (None, "source", "all"):
        for r in sources.all_records():
            if topic and r["area"] != topic:
                continue
            if skill and r["skill"] != skill:
                continue
            if q and q.lower() not in r["question"].lower():
                continue
            st = stats.get(r["id"], {})
            out.append({"id": r["id"], "topic": r["area"], "subtopic": r.get("section"), "skill": r["skill"], "difficulty": r.get("level", 2), "level": r.get("level", 2), "text": r["question"],
                        "kind": "technical", "n_components": 0, "n_followups": len(r.get("variants", [])), "times_asked": st.get("times_asked", 0), "best_score": st.get("best_score"),
                        "source": r["source"], "origin": "source", "prereqs": [], "citation": sources.citation(r)})
    if origin == "source":
        out.sort(key=lambda x: (x["topic"], x["difficulty"]))
        return out
    for item in bank.values():
        if topic and item.topic != topic:
            continue
        if skill and item.skill != skill:
            continue
        if q and q.lower() not in item.text.lower():
            continue
        st = stats.get(item.id, {})
        out.append({"id": item.id, "topic": item.topic, "subtopic": item.subtopic, "skill": item.skill, "difficulty": item.difficulty, "level": item.level, "text": item.text,
                    "kind": item.kind, "n_components": len(item.components), "n_followups": len(item.followups), "times_asked": st.get("times_asked", 0),
                    "best_score": st.get("best_score"), "source": item.source, "origin": "authored", "prereqs": item.prereqs})
    out.sort(key=lambda x: (x["topic"], x["difficulty"]))
    return out


@app.get("/api/questions/{qid}")
def question_detail(qid: str):
    bank = load_bank()
    if qid in bank:
        return bank[qid].to_dict()
    rec = sources.get(qid)
    if rec:
        d = sources.as_question(rec).to_dict()
        d["citation"] = sources.citation(rec)
        d["variants_full"] = rec.get("variants", [])
        return d
    raise HTTPException(404)


@app.get("/api/settings")
def get_settings():
    return db.all_settings()


@app.post("/api/settings")
def set_settings(body: SettingsIn):
    for k, v in body.settings.items():
        db.set_setting(k, v)
    return db.all_settings()


# ------------------------------------------------------------------ sessions
@app.get("/api/sessions")
def list_sessions(limit: int = 50):
    rows = db.list_sessions(limit)
    for r in rows:
        r["mode_name"] = controller.MODES.get(r["mode"], {}).get("name", r["mode"])
        r["config"] = {k: v for k, v in (r.get("config") or {}).items() if k != "bank_context"}
    return rows


@app.post("/api/sessions")
def create_session(body: SessionCreate):
    try:
        iv = controller.Interview.create(body.mode, body.config)
    except ValueError as e:
        raise HTTPException(400, str(e))
    turns = iv.start()
    return {"session": iv.public(), "turns": turns}


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    try:
        iv = controller.Interview(sid)
    except KeyError:
        raise HTTPException(404)
    turns = db.get_turns(sid)
    evals = {e["turn_id"]: e for e in db.get_evaluations(sid)}
    hide = iv.public()["hide_scores"]
    for t in turns:
        if t["role"] == "candidate" and not hide and t["id"] in evals:
            t["evaluation"] = controller._compact_eval(evals[t["id"]]["data"]) | {"evaluation_id": evals[t["id"]]["id"]}
    return {"session": iv.public(), "turns": turns}


@app.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    db.delete_session(sid)
    return {"ok": True}


@app.post("/api/sessions/{sid}/answer")
def answer(sid: str, body: AnswerIn):
    try:
        iv = controller.Interview(sid)
    except KeyError:
        raise HTTPException(404)
    meta = {"input_mode": body.input_mode, "transcript_id": body.transcript_id, "raw_transcript": body.raw_transcript, "interrupted": body.interrupted}
    out = iv.answer(body.text, body.duration, body.pauses, meta)
    if "error" in out:
        raise HTTPException(400, out["error"])
    return out


@app.post("/api/sessions/{sid}/skip")
def skip(sid: str):
    iv = controller.Interview(sid)
    turns = iv.skip()
    iv.save("ended" if iv.state["phase"] == "ended" else None)
    return {"interviewer_turns": turns, "state": iv.public()}


@app.post("/api/sessions/{sid}/pause")
def pause(sid: str):
    iv = controller.Interview(sid)
    iv.pause()
    return iv.public()


@app.post("/api/sessions/{sid}/resume")
def resume(sid: str):
    iv = controller.Interview(sid)
    iv.resume()
    return iv.public()


@app.post("/api/sessions/{sid}/repeat")
def repeat(sid: str):
    iv = controller.Interview(sid)
    return iv.repeat() or {}


@app.post("/api/sessions/{sid}/end")
def end(sid: str):
    iv = controller.Interview(sid)
    if iv.state["phase"] == "ended":
        return {"interviewer_turns": [], "state": iv.public()}
    turns = iv.end()
    return {"interviewer_turns": turns, "state": iv.public()}


@app.get("/api/sessions/{sid}/debrief")
def debrief(sid: str):
    from app.engine import debrief as dbf
    if not db.get_session(sid):
        raise HTTPException(404)
    return dbf.build(sid)


@app.post("/api/sessions/{sid}/retest")
def retest(sid: str, limit: int = 5):
    if not db.get_session(sid):
        raise HTTPException(404)
    iv = controller.Interview.retest_from(sid, limit)
    turns = iv.start()
    return {"session": iv.public(), "turns": turns}


# ------------------------------------------------------------------ game
from app.engine import game, lab  # noqa: E402


@app.get("/api/game/summary")
def game_summary():
    game.init()
    return game.summary()


@app.get("/api/career")
def career():
    game.init()
    return {"banks": game.campaigns(), "stages": game.STAGES, "disclaimer": game.DISCLAIMER}


def _resume_active(mode: str, match) -> Optional[Dict]:
    """Starting a run while one is still open resumes it, so a bad run cannot be dropped and restarted without a result."""
    for row in db.active_sessions(mode):
        if match(row["config"] or {}):
            iv = controller.Interview(row["id"])
            if iv.state.get("phase") == "ended":
                continue
            if iv.time_fraction() >= 1.0:
                # out of time: close it with its result instead of resuming into an instant "we're at time"
                iv.end()
                continue
            return {"session": iv.public(), "turns": db.get_turns(row["id"]), "resumed": True}
    return None


@app.post("/api/career/{slug}/start")
def career_start(slug: str, sector: Optional[str] = None):
    game.init()
    stage = next((c["stage"] for c in game.campaigns() if c["bank"] == slug), None)
    resumed = _resume_active("career", lambda cfg: (cfg.get("career") or {}).get("bank") == slug and (cfg.get("career") or {}).get("stage") == stage)
    if resumed:
        return resumed
    try:
        iv = controller.Interview.create("career", {"bank": slug, "sector": sector})
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
    turns = iv.start()
    return {"session": iv.public(), "turns": turns}


@app.post("/api/deathmatch/start")
def deathmatch_start(body: Optional[Dict[str, Any]] = None):
    game.init()
    resumed = _resume_active("deathmatch", lambda cfg: (cfg.get("deathmatch") or {}).get("alive", True))
    if resumed:
        return resumed
    iv = controller.Interview.create("deathmatch", {"categories": (body or {}).get("categories") or []})
    return {"session": iv.public(), "turns": iv.start()}


@app.post("/api/daily/start")
def daily_start():
    game.init()
    st = game.daily_status()
    if st["completed"]:
        raise HTTPException(400, "today's Daily Draft is already complete")
    if st["session_id"] and (db.get_session(st["session_id"]) or {}).get("status") == "active":
        iv = controller.Interview(st["session_id"])
        return {"session": iv.public(), "turns": db.get_turns(st["session_id"]), "resumed": True}
    iv = controller.Interview.create("daily", {})
    return {"session": iv.public(), "turns": iv.start()}


@app.get("/api/lab/plan")
def lab_plan(skill: Optional[str] = None):
    return lab.plan_config(skill)


@app.post("/api/lab/start")
def lab_start(body: Optional[Dict[str, Any]] = None):
    iv = controller.Interview.create("weakness_lab", {k: v for k, v in (body or {}).items() if k in ("skill",)})
    return {"session": iv.public(), "turns": iv.start()}


@app.get("/api/skills/{skill}/diagnose")
def skill_diagnose(skill: str):
    if skill not in SKILLS:
        raise HTTPException(404)
    return lab.diagnose(skill)


@app.get("/api/skills/{skill}/teach")
def skill_teach(skill: str):
    if skill not in SKILLS:
        raise HTTPException(404)
    return lab.teach(skill)


@app.get("/api/skills/{skill}/questions")
def skill_questions(skill: str):
    bank = load_bank()
    qs = [{"id": q.id, "text": q.text, "level": q.level, "origin": "authored"} for q in bank.values() if q.skill == skill]
    qs += [{"id": r["id"], "text": r["question"], "level": r.get("level", 2), "origin": "source", "citation": sources.citation(r)} for r in sources.by_skill().get(skill, [])]
    stats = db.question_stats()
    for q in qs:
        st = stats.get(q["id"], {})
        q["times_asked"] = st.get("times_asked", 0)
        q["best_score"] = st.get("best_score")
    evals = [e for e in db.all_evaluations(1000) if e.get("skill") == skill]
    return {"questions": qs, "evidence": [{"when": e["created"], "score": e["score"], "verdict": e["verdict"], "question_id": e["question_id"], "session_id": e["session_id"]} for e in evals[:30]]}


@app.post("/api/evaluations/{eid}/reattempt")
def reattempt(eid: str):
    q = lab.reattempt_question(eid)
    if not q:
        raise HTTPException(404, "no fresh question available for this skill")
    ev = db.get_evaluation(eid)
    iv = controller.Interview.create("explain", {"skill": ev.get("skill"), "duration_min": 10, "persona": "analyst", "queue": [q["id"]] if q["source"] in ("bank", "source") else [], "max_questions": 3})
    turns = iv.start()
    if q["source"] == "numeric" and iv.state["phase"] != "ended":
        # replace the opener with the fresh numeric question
        iv.state["current"] = q
        iv.state["root_question"] = q
        iv.state["asked"].append(q["id"])
        turns = [iv._say(q["text"], "numeric", q["id"], {"source": "numeric"})]
        iv.save()
    return {"session": iv.public(), "turns": turns, "reattempt_of": eid}


# ------------------------------------------------------------------ prep command center
from app.engine import prep  # noqa: E402


class ContextIn(BaseModel):
    bank: Optional[str] = None
    sector: Optional[str] = None
    round: Optional[str] = "first_round"
    date: Optional[str] = None
    persona: Optional[str] = None
    technical_weight: Optional[float] = None
    emphasis: List[str] = []
    notes: str = ""
    include_health_story: bool = False


class LaunchIn(BaseModel):
    mode: str
    config: Dict[str, Any] = {}


@app.get("/api/today")
def today():
    return prep.today_feed()


@app.get("/api/prep/contexts")
def prep_contexts():
    return {"contexts": prep.list_contexts(), "rounds": prep.ROUNDS, "next": prep.next_context()}


@app.post("/api/prep/contexts")
def prep_create(body: ContextIn):
    return prep.save_context(body.dict())


@app.put("/api/prep/contexts/{cid}")
def prep_update(cid: str, body: ContextIn):
    if not prep.get_context(cid):
        raise HTTPException(404)
    return prep.save_context(body.dict(), cid)


@app.delete("/api/prep/contexts/{cid}")
def prep_archive(cid: str):
    prep.archive_context(cid)
    return {"ok": True}


@app.get("/api/prep/contexts/{cid}/plan")
def prep_plan(cid: str):
    ctx = prep.get_context(cid)
    if not ctx:
        raise HTTPException(404)
    return prep.build_plan(ctx)


@app.post("/api/prep/contexts/{cid}/start/{option}")
def prep_start(cid: str, option: str):
    ctx = prep.get_context(cid)
    if not ctx:
        raise HTTPException(404)
    mode, cfg = prep.session_config_for(ctx, option)
    iv = controller.Interview.create(mode, cfg)
    prep.touch_context(cid)
    return {"session": iv.public(), "turns": iv.start(), "mode": mode, "config": {k: v for k, v in cfg.items() if k != "bank_context"}}


@app.get("/api/mock/defaults")
def mock_defaults():
    d = prep.mock_defaults()
    d["config"] = {k: v for k, v in d["config"].items() if k != "bank_context"}
    return d


@app.post("/api/launch")
def launch(body: LaunchIn):
    """Generic launcher used by Today / Fix / Practice: mode + config → session."""
    try:
        iv = controller.Interview.create(body.mode, body.config)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
    return {"session": iv.public(), "turns": iv.start()}


@app.get("/api/weakness/search")
def weakness_search(q: str = ""):
    return {"results": prep.search_weakness(q), "recent": prep.recently_missed(8), "recommended": [w for w in curriculum.weaknesses(8) if w["area"] not in ("behavioral", "resume", "deal")][:5]}


@app.get("/api/weakness/{skill}")
def weakness_detail(skill: str):
    if skill not in SKILLS:
        raise HTTPException(404)
    return prep.weakness_actions(skill)


# ------------------------------------------------------------------ modeling lab
from app.knowledge import modeling  # noqa: E402


class ModelingGrade(BaseModel):
    name: str
    seed: int
    answers: Dict[str, Any]
    seconds: Optional[float] = None


@app.get("/api/modeling/challenges")
def modeling_list():
    return modeling.list_challenges()


@app.get("/api/modeling/new/{name}")
def modeling_new(name: str, seed: Optional[int] = None):
    if name not in modeling.CHALLENGES:
        raise HTTPException(404)
    ch = modeling.generate(name, seed)
    return {k: v for k, v in ch.items() if k not in ("solution_table", "solution_notes")} | {"steps": [{k: v for k, v in st.items() if k not in ("answer",)} for st in ch["steps"]]}


@app.post("/api/modeling/grade")
def modeling_grade(body: ModelingGrade):
    if body.name not in modeling.CHALLENGES:
        raise HTTPException(404)
    g = modeling.grade(body.name, body.seed, body.answers)
    game.init()
    # one piece of evidence and one XP award per challenge instance: resubmitting the same numbers is review, not new evidence
    repeat = game.xp_reason_count("modeling:%s:%s" % (body.name, body.seed)) > 0
    xp = 0
    if not repeat:
        curriculum.record(g["skill"], g["score"], 4, "modeling", "mod_%s_%s" % (body.name, body.seed), None, level=4)
        xp = game.award_xp(max(1, game.modeling_xp(body.name, body.seed, g["score"])), "modeling:%s:%s" % (body.name, body.seed))
    g["xp"] = xp
    g["repeat"] = repeat
    g["seconds"] = body.seconds
    return g


@app.post("/api/arena/start")
def arena_start(body: Optional[Dict[str, Any]] = None):
    """Mental Math Arena: numeric-only rapid fire, voice-first, no calculator."""
    cfg = {"duration_min": int((body or {}).get("minutes", 5)), "max_questions": int((body or {}).get("questions", 10)), "numeric_only": True, "persona": "associate", "difficulty": (body or {}).get("difficulty", "medium")}
    iv = controller.Interview.create("rapid_fire", cfg)
    return {"session": iv.public(), "turns": iv.start()}


# ------------------------------------------------------------------ appeals
@app.post("/api/evaluations/{eid}/appeal")
def appeal(eid: str, body: AppealIn):
    ev = db.get_evaluation(eid)
    if not ev:
        raise HTTPException(404)
    data = ev["data"]
    qid = ev["question_id"]
    bank = load_bank()
    text = body.corrected_text or data.get("answer", "")
    pref = db.get_setting("llm_provider", "auto")
    use_llm = db.get_setting("use_llm", True)
    new = None
    note = ""
    src_rec = sources.get(qid) if qid not in bank else None
    if qid in bank or src_rec:
        q = bank[qid] if qid in bank else sources.as_question(src_rec)
        if q.kind == "behavioral":
            new = evaluate_behavioral(q, text, (data.get("delivery") or {}).get("duration_sec"), pref, use_llm)
        else:
            if body.argument and use_llm and provider.active_provider(pref) != "offline":
                # let the evaluator reconsider with the candidate's argument appended as context
                new = evaluate_technical(q, text + "\n\n[Candidate's appeal: %s]" % body.argument, pref, True)
                new["answer"] = text
            else:
                new = evaluate_technical(q, text, pref, use_llm)
    elif qid.startswith("num_"):
        parts = qid.split("_")
        gen = numeric.generate("_".join(parts[1:-1]), int(parts[-1]))
        new = evaluate_numeric(gen, text)
    if new is None:
        raise HTTPException(400, "cannot re-evaluate this question type")
    if src_rec:
        new["stronger_answer"] = src_rec.get("answer", "")
        new["citation"] = sources.citation(src_rec)
    if body.corrected_text:
        note = "Re-evaluated on corrected transcript."
    elif body.argument and provider.active_provider(pref) == "offline":
        note = "Offline: re-evaluated deterministically; your argument is stored for review but cannot be weighed without a model."
    else:
        note = "Re-evaluated against the rubric."
    new["appeal"] = {"argument": body.argument, "corrected_text": body.corrected_text, "previous_score": ev["score"], "note": note, "at": time.time()}
    changed = (new.get("score") or 0) != (ev["score"] or 0)
    db.update_evaluation(eid, new, new.get("score"), new.get("verdict", ""), 1)
    # update turn text if corrected
    if body.corrected_text:
        db.update_turn_text(ev["turn_id"], body.corrected_text, {"corrected": True})
    # re-record skill observation (as a new observation; history keeps both)
    if new.get("score") is not None and ev.get("skill") and changed:
        curriculum.record(ev["skill"], new["score"], new.get("difficulty", 2), new.get("kind", "technical"), qid, ev["session_id"])
    return {"evaluation": controller._compact_eval(new) | {"evaluation_id": eid}, "changed": changed, "note": note}


# ------------------------------------------------------------------ speech
@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), session_id: Optional[str] = Form(None), keep: Optional[str] = Form("1")):
    suffix = os.path.splitext(audio.filename or "a.webm")[1] or ".webm"
    os.makedirs(db.AUDIO_DIR, exist_ok=True)
    fname = "%d_%s%s" % (int(time.time() * 1000), (session_id or "x")[:8], suffix)
    path = os.path.join(db.AUDIO_DIR, fname)
    with open(path, "wb") as f:
        shutil.copyfileobj(audio.file, f)
    res = stt.transcribe(path)
    if not res.get("ok"):
        return JSONResponse({"ok": False, "error": res.get("error")}, status_code=503)
    xid = db.add_transcript(session_id, None, res["raw"], res["text"], path if keep == "1" else None, res.get("duration"), res.get("model", ""))
    if keep != "1":
        try:
            os.remove(path)
        except OSError:
            pass
    res["transcript_id"] = xid
    res["audio_url"] = "/api/audio/%s" % fname if keep == "1" else None
    return res


@app.get("/api/audio/{fname}")
def audio(fname: str):
    p = os.path.join(db.AUDIO_DIR, os.path.basename(fname))
    if not os.path.exists(p):
        raise HTTPException(404)
    return FileResponse(p)


@app.post("/api/tts")
def speak(body: TTSIn):
    eng = tts.engine(db.get_setting("tts_engine", "auto"))
    if eng == "kokoro":
        p = tts.synthesize_kokoro(body.text, body.persona, db.get_setting("kokoro_voice") or None, body.pause_scale)
        if p:
            return FileResponse(p, media_type="audio/wav", headers={"X-TTS-Engine": "kokoro"})
    voice = body.voice or None
    p = tts.synthesize(body.text, voice, body.rate or 0, body.persona, body.expressive, body.pause_scale)
    if not p:
        raise HTTPException(503, "tts unavailable")
    return FileResponse(p, media_type="audio/mp4", headers={"X-TTS-Engine": "say"})


@app.get("/api/tts/engines")
def tts_engines():
    kh = tts.kokoro_health(0.8)
    return {"active": tts.engine(db.get_setting("tts_engine", "auto")), "preference": db.get_setting("tts_engine", "auto"),
            "kokoro": {"installed": tts.kokoro_installed(), "running": bool(kh), "voices": (kh or {}).get("voices", []), "persona_voices": tts.KOKORO_VOICES, "selected": db.get_setting("kokoro_voice")},
            "say": {"available": tts.available(), "premium_installed": tts.premium_installed()}}


@app.get("/api/tts/voices")
def tts_voices():
    return tts.voices()


# ------------------------------------------------------------------ static
@app.middleware("http")
async def _no_cache_html(request, call_next):
    resp = await call_next(request)
    if request.url.path in ("/", "/index.html"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")


def main() -> None:
    import uvicorn
    port = int(os.environ.get("GAUNTLET_PORT", "8870"))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
