# PROJECT_PLAN — The Gauntlet

## Goal
Make the candidate measurably better at IB Summer Analyst interviews via realistic, adaptive, voice-enabled
practice with evidence-based debriefs. Not a CRM, not flashcards.

## Milestones and acceptance criteria

### M1 Foundation (done when)
- [ ] FastAPI server starts on :8870, serves SPA, SQLite schema created, launch.json entry added.
- [ ] Profile facts module loads resume + model facts with provenance; discrepancy report generated.
- [ ] LLM provider abstraction with offline fallback; `/api/health` reports provider + whisper status.

### M2 Knowledge system
- [ ] ≥300 structured technical questions across 9 topic areas, each with components, misconceptions,
      follow-ups, solution, difficulty, prerequisites; validator passes (unique ids, prereqs resolve).
- [ ] Numeric generators (paper LBO, TV, EV bridge, accretion/dilution, WACC, IRR) verified by tests.
- [ ] Behavioral bank (≥60 prompts) with rubric; TMAY evaluator; resume-defense question trees
      generated from each resume bullet.

### M3 Interview engine
- [ ] Session controller with phases, time budget, persona, state persisted per turn (survives refresh).
- [ ] Evaluator: component coverage, misconception detection, numeric checking, relevance, behavioral
      rubric. Returns structured JSON validated by pydantic.
- [ ] Follow-up policy picks ONE most-important challenge reason; depth limit; no repeats.
- [ ] Claim registry detects contradictions across turns.
- [ ] 8 modes + Hot Seat + TMAY simulator run end-to-end via API and via simulated candidates.

### M4 Voice
- [ ] MediaRecorder → Whisper transcription with finance vocabulary; correction UI; silence auto-stop;
      text fallback; TTS via browser (default) or macOS `say`.
- [ ] Delivery metrics: duration, WPM, fillers, hedges, repetition (transcript-based, labeled as such).

### M5 Learning engine + debrief
- [ ] Skill map with `not_assessed`; mastery update rule tested for monotonic sanity; spaced review queue.
- [ ] Debrief: overall, per-question, technical corrections, behavioral, delivery, sample answers,
      retry-weakest, appeal.

### M6 Quality
- [ ] pytest suite ≥ 60 tests green. Simulated interviews (strong/weak/evasive/contradictory candidates)
      produce sensible, differentiated outcomes. UI verified in the browser pane.
- [ ] Docs: PROGRESS.md, TEST_REPORT.md, CONTINUATION.md current.
