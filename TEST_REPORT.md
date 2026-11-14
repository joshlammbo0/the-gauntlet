# TEST_REPORT (2.0, 2026-11-09)

## Automated: `.venv/bin/python -m pytest -q` → 50 passed (+1 slow ingest test, passes when run alone, ~60 s)
- test_bank (5): validator, areas, depreciation ladder, skills, numeric self-check.
- test_evaluator (13): correct/misconception/non-answer/off-topic/partial/gave-up, normalization, numeric tolerance, MOIC partial credit, behavioral specific vs generic, unsupported claims, off-topic story, TMAY beats, filler metrics.
- test_engine (12): contradictions once per key, mastery bounds and shrinkage, not_assessed start, selector prereqs/no repeats, follow-up reasons, full controller flow with reload, realistic mode hides scores, pause/resume, retest queue, no repeated follow-up, **callback revisits a missed skill in a new question**, **deep-grade revision replaces the observation**, **interrupted answer gets the concision probe**.
- test_api (6): meta, lifecycle + appeal, KB round-trip, skills shape, question browse, corrupt audio → 503.
- test_sources (4): ingest idempotent/stable with ≥1,200 unique records, citations/skills/levels on every record, derived rubric rewards correct mechanics, authored levels.
- test_game (10): XP persists and levels; farming decay; **mastery not inflated by repeating one question**; deathmatch lives end the run and record; streak/boss scoring; career fail keeps stage and allows instant rematch; career pass advances stage; daily date rules and streak; modeling challenges grade deterministically; lab diagnoses the weak prerequisite.

## Evaluator benchmark: `scripts/benchmark_evaluator.py` → 21/21 within expected bands
Covers fully correct, partial, confident-wrong, unconventional wording, missing concepts, misconceptions, numerically wrong, reasonable assumptions, needs-clarification, speech-noise, no-mechanism, outdated, rules of thumb, linear-IRR error; 6 numeric cases incl. the forgotten (1+g) step.

## Simulated interviews: `scripts/simulate.py` → 14 modes × 5 archetypes, all sanity checks pass
(strong ≥ weak + 0.15 everywhere; evasive ≤ 0.5; contradictions flagged once each). Deterministic seeds (crc32).

## Model integration (measured)
| Path | Before (1.0) | 2.0 |
|---|---|---|
| One-shot CLI call | 11–16 s | n/a (fallback only) |
| Persistent worker, warm | — | 1–3 s trivial; 4–7 s full evaluation |
| Live interviewer turn (API) | 11 s | 2.1 s |
| Deep grade landing after answer | n/a | ~6 s, in background |
Quota: the plan's 5-hour limit was hit once during testing; fallback to deterministic grading worked and is surfaced in Settings.

## Manual (browser pane)
Dashboard (readiness "Not enough data" with 8% coverage, mastery by area, weakest, recommendation), Career grid with stage bars and sector select, Weakness Lab plan with root-cause lines, Mini DCF challenge with givens/scratchpad/calculator, Skill graph with states and prerequisites, Deathmatch room with lives/score HUD and hands-free toggle. No console errors.

## Not covered / manual verification required
- Human microphone end to end (blocked in the embedded pane): open http://127.0.0.1:8870 in Chrome, start Deathmatch, confirm hands-free loop, interruption at 150 s, and that silence stops recording.
- Model-refined behavioral grading A/B against the rubric (needs quota).
- Long (45–60 min) sessions and multi-day streak behavior (needs real days).
