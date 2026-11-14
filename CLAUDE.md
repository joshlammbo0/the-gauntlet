# The Gauntlet 2.0 — Investment Banking Interview RPG

Personal, local-first interview trainer for one candidate (real profile lives in the gitignored private facts module). It simulates a skeptical banker, evaluates answers against
structured rubrics, tracks mastery over time, and runs a voice loop (local Whisper STT, system TTS).

## Run

```bash
cd ~/Documents/GitHub/ib/gauntlet && .venv/bin/python -m app        # http://127.0.0.1:8870
```

Launch entry `gauntlet` exists in `~/Documents/GitHub/ib/.claude/launch.json` (port 8870).
Tests: `.venv/bin/python -m pytest -q`. Simulated interviews: `.venv/bin/python scripts/simulate.py`.

Environment: `.venv` was created with `uv venv --python /usr/bin/python3 --system-site-packages`
so it sees the user-site `faster-whisper` (Python 3.9, models `small.en`/`base.en` cached in
`~/.cache/huggingface`). FastAPI/uvicorn/pydantic live in the venv. No Node needed.

## Architecture (see ARCHITECTURE.md)

- `app/main.py` FastAPI app + static SPA (`static/`). SQLite at `data/gauntlet.db` (`app/db.py`).
- `app/engine/` the interview orchestration: `controller.py` (session state machine),
  `selector.py` (adaptive question selection), `followup.py` (challenge classification),
  `evaluator.py` (deterministic rubric scoring + optional LLM evaluator), `claims.py`
  (claim registry / contradiction detection), `curriculum.py` (skill map, mastery, spaced
  repetition), `debrief.py`, `personas.py`, `delivery.py` (transcript-based delivery metrics).
- `app/knowledge/` question bank (Python modules, one per topic, validated by `bank.py`),
  numeric generators (`numeric.py`, programmatically verified), skill taxonomy, bank/group
  context imported read-only from `../bankvault/bank-intelligence` (`banks.py`).
- `app/profile/` the candidate's verified facts: `facts.py` (resume + source-document extraction with
  provenance), `kb.py` (user-editable verified knowledge base), `resume_defense.py`.
- `app/llm/` provider abstraction: `anthropic_api` (needs ANTHROPIC_API_KEY in `.env`),
  `claude_cli` (desktop app binary, needs `claude /login`), `offline` (deterministic; always on).
- `app/speech/` `stt.py` (faster-whisper with finance vocabulary prompt + correction table),
  `tts.py` (Kokoro neural sidecar → wav when installed, else macOS `say` → m4a; browser speechSynthesis as the no-server fallback).
- Kokoro: `tts-venv` (uv Python 3.12, `kokoro-onnx soundfile numpy`) + model files in `data/kokoro/` (both gitignored). `scripts/kokoro_server.py` on :8872 is spawned by the app at startup; `tts_engine` setting `auto|kokoro|say`. See VOICE.md.

## 2.0 additions
- `app/knowledge/ingest.py` + `sources.py`: local guides → `data/knowledge/source_questions.json` (regenerate with `python app/knowledge/ingest.py`; idempotent). Guides never leave the Mac except excerpts in grading prompts when `send_guide_excerpts` is on.
- `app/llm/worker.py`: persistent `claude -p --input-format stream-json` processes (never pass `--bare`; it breaks auth).
- `app/engine/game.py` (career/deathmatch/daily/XP/achievements), `lab.py` (diagnose/teach/reattempt), `app/knowledge/modeling.py` (written challenges).
- Grades are provisional (deterministic) first and revised by the model in a background thread; `curriculum.revise` replaces the observation.
- Mastery states and readiness come from `curriculum.state_of` / `readiness()`; XP never influences them.

## 2.1 prep command center
- `app/engine/prep.py`: interview contexts (`prep_contexts` table), plan generation, `/api/today` feed, mock defaults (`last_mock_config` setting), weakness search/actions. `static/ux.js`: Today, Prepare, Practice, Fix, Mock, Progress/Library tabs. `controller.MODE_META` feeds the Practice screen. See USABILITY_REDESIGN.md.

## Conventions and rules

- **Never fabricate the candidate's facts.** Everything about his experience comes from `app/profile/facts.py`
  with a `source` and `status` (`verified` = in a source document, `user` = entered in the KB,
  `prompt_only` = only in the build prompt, `unknown` = not documented). The interviewer may ask
  about unknowns; it must never assert them. Sample answers mark placeholders in [brackets].
- The interviewer never reveals scores mid-interview in Realistic/Hot Seat modes.
- Deterministic checks (numeric answers, component coverage on authored rubrics) always override LLM opinions.
  Guide-derived keyword rubrics (`src_*`) are weaker: the model weighs more there (see `evaluator._refine_with_llm`).
- Vocabulary regexes must match at word starts (`sources.bounded`): unanchored terms matched inside other words
  ("ebt" in "debt", "rating" in "operating") and corrupted about half the derived rubrics.
- Mastery starts `not_assessed`; one answer never sets mastery to 5 or 0.
- T1D / health details are sensitive: off by default (`settings.include_health_story`).
- Keep interviewer turns short (one question). No "Great answer!" fillers.
- Python 3.9 compatible code (no `match`, no `X | Y` types at runtime; use `typing.Optional`).
- No network calls except the optional Anthropic API. BankVault data is copied, never modified.
