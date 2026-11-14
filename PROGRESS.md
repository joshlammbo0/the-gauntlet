# PROGRESS (2.0, 2026-11-09)

## Phase status
| Phase | Status |
|---|---|
| 0 Audit & backup | Done: git repo (`v1.0-checkpoint` tag), DB backup `data/backups/gauntlet-*-pre-v2.db`, baseline 34 tests green, server verified. |
| 1 Knowledge & grading | Done: M&I 400 (2025 + 2009) and WSP Red Book ingested (1,687 unique records, 1,406 core, 0 unverified refs); source questions selectable with derived rubrics and citations; cognitive levels 1–5; evaluator benchmark 21/21 after fixes (sign normalization, off-topic rule, TV tolerance). |
| 2 Voice & adaptive | Done: persistent Claude workers (warm turn ≈2–4 s vs 11–16 s); live/deep grading split (provisional instant, model revision in background with mastery revision); adaptive level-up chains on source questions; callbacks with debrief reporting; interruption of long answers; hands-free mode (auto-record after TTS, auto-submit, click avatar to interrupt); recordings off by default; guide-excerpt disclosure setting. |
| 3 Mastery & debriefs | Done: prerequisite graph (71 edges), mastery states incl. review_due, per-level tracking, repeat-farming discount, readiness with coverage/confidence or "not enough data"; debrief shows callbacks, citations, provisional flags, Teach-me-why and Reattempt actions; Weakness Lab with prerequisite diagnosis and teach pages. |
| 4 Gameplay | Done: Career Mode (18 real-named banks, 5 stages + fictional offer, pass marks, history, instant rematch with new questions, mastery-scaled difficulty, disclaimer), Deathmatch (3 lives, streak multiplier, boss every 5th, records), Daily Draft (local date, streak, resume-if-open), XP/levels with farming decay, 10 evidence-gated achievements, readiness-first dashboard. |
| 5 Modeling Lab & polish | Done (first cut): Mental Math Arena (numeric-only rapid fire, voice-first), 4 written challenges (mini DCF, accretion 3 ways, S&U + goodwill, paper LBO with paydown) with scratchpad, calculator where allowed, step-by-step deterministic grading; new nav; dashboard. Visual polish limited to consistency with the 1.0 terminal theme. |

## 2.1 (2026-11-14): prep command center
Today (four actions + focus queue), Prepare (interview contexts → plans → 10/25/full launches), Fix a Weakness (search, evidence, root cause, four actions), one-click Full Mock with remembered defaults, Practice grouped by intent with mode metadata, room progressive disclosure + shortcuts, verdict-first debrief, Progress/Library tabs. 73 tests. Details in USABILITY_REDESIGN.md.

## Verified in this session
- 50 pytest tests pass (plus the slow ingest idempotency test when run alone). Simulation harness: 14 modes × 5 archetypes; sanity assertions pass after fixing a harness leak (weak candidate had been fed guide answers).
- Browser pane: dashboard, career, lab, modeling challenge, skill graph, deathmatch HUD render without console errors.
- Model: live interviewer turn 2.1 s, deep grade landed ~6 s later with a precise key error; worker pool shows two live processes.

## Known issues
- the candidate's Claude plan has a 5-hour usage cap; when hit, the engine silently falls back to deterministic grading (Settings shows the limit message). Testing consumed part of it.
- Microphone cannot be exercised inside the desktop app's embedded pane; hands-free flow needs Chrome/Safari verification by the candidate.
- Weakest-skills and lab plans can surface `commercial.positioning` early because the 1.0 sessions touched it; it self-corrects with more evidence.
- Interviewer persona rephrasing only applies to probes/follow-ups; main questions are read as authored/ingested.
