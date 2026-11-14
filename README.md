# The Gauntlet 2.0 — The Investment Banking Interview RPG

*Master the technicals. Survive the superday.*

A personal, local-first interview trainer built around the candidate's actual resume, models and pitches.
It runs ten interview modes (Realistic Superday, Technical Death Match, Resume Defense, Behavioral
Pressure Test, Deal Defense, Rapid-Fire, Explain-It-Until-You-Understand-It, Bank-Specific, Hot Seat,
Walk-Me-Through-Your-Resume), listens through the microphone (local Whisper), speaks the questions,
grades every answer against structured rubrics, tracks mastery per skill with spaced review, and
produces an evidence-based debrief with a one-click retest of the weakest questions.

## Run

```bash
cd ~/Documents/GitHub/ib/gauntlet && .venv/bin/python -m app
```

Open http://127.0.0.1:8870 **in Chrome or Safari** for voice (the desktop app's embedded browser pane blocks the microphone; typing still works there). The Claude desktop app can also start it from the `gauntlet` entry in
`~/Documents/GitHub/ib/.claude/launch.json`.

First-time setup is already done on this Mac (`.venv` with FastAPI; system `faster-whisper`). To
recreate it: `uv venv --python /usr/bin/python3 --system-site-packages .venv && uv pip install --python .venv/bin/python fastapi "uvicorn[standard]" pydantic python-multipart httpx pytest pyyaml`.

## What's new in 2.0
Career Mode (18 real-named banks, fictional campaigns with a disclaimer), Technical Deathmatch (3 lives, bosses, records), Daily Draft, Weakness Lab with prerequisite diagnosis and Teach-Me-Why, Modeling Lab (mental math arena + written challenges), a readiness-first dashboard, 1,400+ source-grounded questions from your local M&I 400 and WSP Red Book with page citations, persistent Claude workers (2–4 s turns), live/deep grading split, callbacks, hands-free voice. See ARCHITECTURE.md and QUESTION_BANK_REPORT.md.

## Reasoning engine

Three tiers, auto-selected (Settings page shows which is active):

| Tier | Needs | What it adds |
|---|---|---|
| Deterministic (always on) | nothing | rubric component matching, misconception patterns, numeric checking, behavioral rubric, claim/contradiction tracking, authored follow-up trees |
| Claude CLI | `claude /login` once in a terminal | model-refined evaluation, interviewer turns rephrased in persona voice, appeals reconsidered |
| Anthropic API | `ANTHROPIC_API_KEY` in `.env` | same as CLI, no login needed (paid) |

Deterministic checks always override the model on numeric correctness; the model may move a score by
at most ±0.25 and must quote evidence to flip a rubric component. Exception: rubrics derived automatically
from the guides (keyword lists) are a weak signal, so there the model's grade weighs 70% (±0.5), or 90% (±0.8)
when the list is thin. Answers that are only a list of terms are capped at 0.3. In Deathmatch, an answer short
of full credit waits for the model grade before a life or points are decided.

## Tests

```bash
.venv/bin/python -m pytest -q            # unit + API tests
.venv/bin/python scripts/simulate.py -v  # five candidate archetypes × ten modes, with sanity assertions
```

See CLAUDE.md, ARCHITECTURE.md, PROGRESS.md, TEST_REPORT.md, QUESTION_BANK_DESIGN.md and CONTINUATION.md.
