# CONTINUATION — how the next session should pick this up

1. Start: `cd ~/Documents/GitHub/ib/gauntlet && .venv/bin/python -m app` → http://127.0.0.1:8870. Tests:
   `.venv/bin/python -m pytest -q`; simulations: `.venv/bin/python scripts/simulate.py -v`. Restart the server by killing
   the PID on :8870 (`lsof -nP -iTCP:8870 -sTCP:LISTEN -t`); uvicorn runs without reload.
2. Voice must be tested by the candidate in Chrome/Safari (the embedded pane blocks the mic). Ask the candidate (blocking only for him):
   - Model is connected via the bundled binary (`<binary> auth login`, done 2026-11-09). If the probe ever says not logged in,
     rerun that command in a terminal. Do not enable paid APIs for him. Consider caching the CLI process or switching rapid-fire to offline to cut the ~10–16s per-turn latency.
   - Fill the Hobo Ventures unknowns in Resume defense (price deck, discount rate, differentials, decline method, one recommendation).
   - Settle the StandardAero upside figure (48% resume / 46% model / 23% notes) and the Insulet 29% reference price.
3. Highest-value engineering next:
   - Author follow-ups for the ~136 technical questions that rely on generated hint probes (bank files: add F(...) entries).
   - Deepen FIG/healthcare banks (+20 each) and add more energy numeric generators (PV-10 roll-forward, hyperbolic decline volumes).
   - Interrupted TMAY: implement mid-answer interruption (client-side timer at a beat boundary) rather than only the prompt variant.
   - Explain mode: add prerequisite walk-down (pick an easier prereq question when the ladder fails twice).
   - Behavioral evaluator: with a model connected, A/B the LLM-refined scores against the rubric on the simulate.py archetypes
     and tighten the ±0.3 bound if it drifts; log provider latency in the debrief.
   - Rapid-fire: server-side timing (timestamp when the question was served) instead of client duration.
   - Export: debrief → Markdown/PDF; weekly progress email draft (never auto-send).
4. Conventions: facts only via `app/profile/facts.py` or the KB table, with status/source; keep Python 3.9 syntax; keep
   interviewer turns short; numeric checks override the model; sensitive story gated.

## 2.0 upgrade status (session cut off by usage limit, 2026-11-09 ~02:00)
Done and committed:
- Phase 0: git repo + tag `v1.0-checkpoint`; DB backup in `data/backups/`.
- Phase 1: `app/knowledge/ingest.py` parses M&I 400 (2025 + 2009) and WSP Red Book → `data/knowledge/source_questions.json`
  (1,687 unique records, 1,406 core technical; stable ids; citations with page; off-core sections tagged). `app/knowledge/sources.py`
  turns them into questions with derived rubrics; selector/controller/API/appeal/retest handle `src_*` ids. Cognitive levels 1–5 on all questions.
  `scripts/benchmark_evaluator.py` 21/21. Tests: `pytest -q --deselect tests/test_sources.py::test_ingest_is_idempotent_and_stable` (the deselected one is slow, ~60s, passes).
- Phase 2 (partial): persistent Claude worker pool `app/llm/worker.py` (warm turn ≈4s vs 11–16s; do NOT pass `--bare`, it breaks auth);
  live/deep grading split in `controller.answer` (provisional deterministic grade → background model refinement → `curriculum.revise`);
  callbacks (`callback_pending`/`callbacks` in state, debrief lists them); interruption probe; hands-free mode + privacy defaults in the UI;
  guide-excerpt disclosure setting `send_guide_excerpts`.
- Phase 3 (started): `PREREQS` graph in skills.py; mastery states (untested/learning/developing/proficient/mastered/review_due), per-level
  breakdown, repeat-farming discount, `curriculum.readiness()` with coverage/confidence (exposed in /api/skills).
Known: `tests/test_engine.py::test_callback_revisits_missed_skill_in_new_question` failed on its first run (callback is probabilistic; make it
deterministic by seeding or forcing `rng`), and the candidate's Claude plan hit its 5-hour limit during testing (resets 3:50am), so the server
currently reports `offline` until the next probe.
Next: finish Phase 3 UI (skill graph, Weakness Lab, Teach-Me-Why / Reattempt actions), then Phase 4 (Career Mode, Deathmatch lives, Daily Draft, XP) and Phase 5 (Modeling Lab), and update the dashboard to the readiness-first layout.


## After the 2.0 build (2026-11-09, later session)
Phases 0–5 are implemented and committed (see PROGRESS.md). Next most valuable work, in order:
1. Have the candidate run a hands-free Deathmatch in Chrome and report mic/turn-taking issues; tune `silence_seconds`, `MAX_ANSWER_SEC`.
2. Author components/misconceptions for the most-asked source questions (start with `src_mi400_2025_*` accounting/DCF) to replace derived rubrics.
3. Add level-5 content (exceptions) per core skill; add energy/FIG numeric generators.
4. Career Mode: stage-specific question composition (screening = resume-heavy, technical = source-heavy) via `game.STAGES` → selector weights; persona dialogue per bank from BankVault culture notes.
5. Interview replay with audio when recordings are enabled; export debrief to Markdown.
6. Dashboard: restrict "weakest" to skills with n_obs ≥ 2; add per-area coverage rings.
Gotchas: `db.set_setting("use_llm", False)` against the main DB disables the model silently (the simulate harness does this on its own data dir only); the worker must not use `--bare`; `GAUNTLET_KNOWLEDGE` overrides where ingested guides live.
