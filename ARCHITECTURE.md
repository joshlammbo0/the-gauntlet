# ARCHITECTURE (2.0)

## Logical systems (all inside one FastAPI process; no extra services)

| System | Modules | Notes |
|---|---|---|
| Knowledge Engine | `app/knowledge/ingest.py`, `sources.py`, `bank.py`, `questions/*.py`, `numeric.py`, `modeling.py`, `skills.py`, `banks.py` | Guides → `data/knowledge/source_questions.json` (stable ids, citations, levels, skill mapping, variants). Authored bank validated at load; cognitive level 1–5 inferred. Prerequisite graph in `skills.PREREQS`. |
| Interview Engine | `app/engine/controller.py`, `selector.py`, `followup.py`, `claims.py`, `personas.py` | Session state machine; adaptive selection (prereqs, difficulty target, curriculum priority, persona weights, recency, source weighting); one follow-up per turn from a 16-reason taxonomy; level-up chains on source questions; callbacks (`callback_pending` → revisit in a new question); interruption probe; contradiction flags. |
| Voice Engine | `app/speech/stt.py`, `tts.py`, `static/app.js` (recorder) | Whisper small.en with finance prompt + corrections; silence auto-stop; hands-free mode (auto-record after TTS, auto-submit); interrupt by clicking the avatar; long-answer cut-off; push-to-talk and text fallback. |
| Evaluation Engine | `app/engine/evaluator.py`, `behavioral.py`, `controller._evaluate_resume` | Deterministic rubric (components, misconceptions, numbers, relevance) → provisional grade instantly; model refinement (bounded ±0.25 on authored rubrics, wider on guide-derived ones; must quote evidence) runs in a background thread (`_deep_grade`), or synchronously in Deathmatch when the provisional grade is short of full credit; career/daily results wait for in-flight deep grades; a per-session lock serializes state writes and revises the stored evaluation and the mastery observation. Numeric checks always win. |
| Mastery Engine | `app/engine/curriculum.py` | Mastery 0–5 with shrinkage toward 2.5; recency (30-day) and difficulty weights; repeats of the same question count 0.25; states untested/learning/developing/proficient/mastered/review_due (`state_of`); per-level breakdown; SM-2-style intervals; `readiness()` reports estimate + coverage + confidence or "not enough data". |
| Career/Game Engine | `app/engine/game.py` | Campaign tables per bank (stage, attempts, history, offer), stage configs, pass marks, mastery-scaled difficulty; Deathmatch lives/streak/boss/records; Daily Draft by local date with streak; XP with farming decay; achievements with evidence. XP never feeds mastery. |
| Weakness Lab | `app/engine/lab.py` | Prerequisite-walk diagnosis (deepest weak prerequisite = root cause), `teach()` layered material (authored solutions by level, worked numeric example, cited guide excerpts, related concepts), fresh reattempt questions. |
| LLM layer | `app/llm/provider.py`, `worker.py`, `prompts.py`, `schemas.py` | Provider order API → CLI → offline. `WorkerPool` keeps persistent `claude -p --input-format stream-json` processes: `evaluator` (recycled every 20 turns) and `interviewer:<session>` (conversational memory, expires after 30 min idle). Outputs validated by pydantic. |
| Persistence | `app/db.py` + additive `CREATE TABLE IF NOT EXISTS` in `game.py` | SQLite WAL. Sessions store full state JSON; evaluations store full data JSON (provisional → deep). Backups in `data/backups/`. Git tags `v1.0-checkpoint`. |
| Frontend | `static/index.html`, `app.js` (core + interview room + debrief + settings), `game.js` (dashboard, career, lab, modeling, teach, skill graph) | Vanilla JS SPA, hash router. |

## One turn (2.0)
1. Client submits text (typed, or Whisper transcript, optionally `interrupted`).
2. `controller.answer`: store turn → **provisional** deterministic evaluation → record mastery (level-aware) → XP → deathmatch/career bookkeeping → claims/contradictions → `_respond` (contradiction / interruption / probe / level-up chain / deepen / pivot; callbacks at pivot) → interviewer text optionally rephrased by the persistent interviewer worker (≈2 s) → persist.
3. Background `_deep_grade`: model-refined evaluation (≈4–7 s), `db.update_evaluation`, `curriculum.revise`, debrief shows `provisional` until then.
4. On end: `_summary` resolves career stage / deathmatch record / daily completion / achievements once (`game_resolved`).

## Invariants
Facts about the candidate only from `facts.py` + KB; untested skills never shown as mastered; realistic/career/deathmatch hide grades until the end; guide excerpts leave the machine only when `send_guide_excerpts` is on (disclosed); recordings off by default.
