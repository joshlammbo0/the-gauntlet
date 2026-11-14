# USABILITY_REDESIGN — The Gauntlet 2.0 → prep command center (2026-11-14)

## 1. Current information architecture (before)

Hash-routed SPA (`static/index.html`, `static/app.js` core, `static/game.js` 2.0 pages). Routes:

| Route | Screen | Backing endpoints |
|---|---|---|
| `#/home` | Dashboard: readiness/coverage/trend/rank cards, mastery by area, weakest, recommended challenge, 6 mode cards, collapsed list of all 14 modes with a per-mode setup form | `/api/skills`, `/api/game/summary`, `/api/sessions`, `/api/modes` |
| `#/career` | Career grid (18 banks) | `/api/career`, `/api/career/{slug}/start` |
| `#/lab` | Weakness Lab plan + diagnose/teach pickers | `/api/lab/plan`, `/api/lab/start`, `/api/skills/{s}/diagnose` |
| `#/teach/:skill` | Teach-me-why | `/api/skills/{s}/teach` |
| `#/modeling[/name]` | Modeling Lab | `/api/modeling/*`, `/api/arena/start` |
| `#/skills[/:skill]` | Skill graph | `/api/skills`, `/api/skills/{s}/questions` |
| `#/resume` | Resume defense bullets + KB form | `/api/resume-defense`, `/api/kb` |
| `#/history` | Sessions table | `/api/sessions` |
| `#/bank` | Question bank browser | `/api/questions` |
| `#/profile` | Facts, stories, discrepancies, KB | `/api/profile` |
| `#/settings` | Engine, voice, privacy | `/api/settings`, `/api/health` |
| `#/session/:id` | Interview room | `/api/sessions/{id}/*`, `/api/transcribe`, `/api/tts` |
| `#/debrief/:id` | Debrief | `/api/sessions/{id}/debrief`, appeal/reattempt/retest |

Session flow: `POST /api/sessions {mode, config}` → `controller.Interview.create` applies mode defaults (`game.*_config`, `lab.plan_config`) → `start()` → turns. State is a JSON blob per session row; evaluations per turn; mastery in `skills`; game tables additive.

## 2. Highest-friction points found

1. **Choice overload at the door.** Home shows 4 metric cards, mastery bars, weaknesses, a recommendation, 6 mode cards and 14 more behind a disclosure. Starting a Superday means picking bank, sector, persona, duration, difficulty, mix, three checkboxes.
2. **No notion of "what I'm preparing for."** Bank/sector/persona are re-chosen every time; nothing remembers an upcoming interview or last mock settings.
3. **Weakness fixing is indirect.** You either trust the Lab's auto plan or hunt the skill graph; there is no search, no "recently missed", no choice between teach / practice / pressure-test / retest.
4. **Interview room shows everything at once:** transcript panel, live evaluation panel, controls help text, three rows of buttons, all competing with the question.
5. **Debrief leads with numbers**, then corrections, then a long question list; "what do I do next" is scattered (retest button top, teach/reattempt per question, remediation at the bottom).
6. **Navigation is by feature**, not by intent (Career / Lab / Modeling / Skill graph / Resume / History / Bank / Profile / Settings).
7. Mode cards do not say duration, voice/text, hidden vs live scores, or what they improve.

## 3. Redesign mapping (existing capability → new home)

| Redesign element | Built from |
|---|---|
| **Today** (default) | new `/api/today` aggregating: active session, daily status (`game.daily_status`), due reviews + weak foundations (`curriculum`), readiness, last session summary, next prep context |
| Quick Practice | `POST /api/daily/start` (resume-if-open) |
| Prepare for an Interview | new `prep_contexts` table + `app/engine/prep.py` plan generator using `banks.context_for_interview`, `curriculum`, `resume_defense`, `facts.STORIES`; launches `superday`/`bank_specific`/`weakness_lab` with derived configs |
| Fix a Weakness | new `/api/weakness/search` (skills + question text) + existing `diagnose`, `teach`, `lab/start`, `hot_seat` on one skill, `reattempt` |
| Run a Full Mock | new `/api/mock/defaults` (active context → last mock config in settings → sane default) and a compact launcher; `superday` / `bank_specific` unchanged |
| Practice | existing 14 modes grouped by intent with metadata (`MODE_META` in `app/engine/controller.py`) |
| Progress | skill graph + longitudinal + history filters (existing endpoints; history gains filters client-side plus `context_id`) |
| Library | question bank + sources + resume defense + teach pages |
| Profile / Settings | unchanged |
| Interview room | same endpoints; progressive disclosure (transcript/advanced collapsed, big status pill, keyboard shortcuts) |
| Debrief | same `/debrief` payload; new verdict block computed client-side from existing fields + `next_actions` added server-side |

## 4. Files changed

- `app/db.py`: additive `prep_contexts` table; `sessions.config.context_id` (JSON field, no schema change).
- `app/engine/prep.py` (new): contexts CRUD, plan generation, session configs for 10 / 25 / full, today feed, mock defaults, weakness search.
- `app/engine/controller.py`: `MODE_META` (intent group, duration, voice, hidden scores, improves); records `last_mock_config` on create for superday/bank_specific.
- `app/engine/debrief.py`: `verdict` block (strengths, problems, next actions).
- `app/main.py`: `/api/today`, `/api/prep/*`, `/api/mock/defaults`, `/api/weakness/search`, `/api/modes` enriched.
- `static/index.html`: six-item nav; `static/ux.js` (new): Today, Prepare, Practice, Fix, Mock launcher, Progress, Library routes; `static/app.js`: room layout and debrief order.
- `tests/test_ux.py` (new).

## 5. Assumptions

- "Full Mock" = Realistic Superday (or Bank-Specific when a context names a bank), 30 min, hidden scores, voice preferred.
- Interview dates are plain ISO dates typed by the user; the nearest future context is "next".
- No new frontend framework: vanilla JS modules continue; `window.G` is the shared bridge.
- Scoring, selection, mastery and voice engines are untouched except for adding metadata and the optional `context_id` tag on sessions.

## 6. Implemented (2026-11-14)

### Before → after user flows
| Goal | Before | After |
|---|---|---|
| Practice something useful now | Dashboard → find "Recommended challenge" or scroll to a mode → setup form → Begin | **Today → Quick Practice** (one click; Daily Draft, resumes if already open) |
| Prep for JPM healthcare first round next Friday | Remember to pick bank + sector + persona + duration + mix every time; no plan | **Prepare → New plan** (bank, group, round, date) → plan page lists technical areas, verified bank/deal angles, behavioral skills, resume bullets with open facts, deal defense → **Start recommended 25-min** (or 10-min drill / full mock). Plan becomes the default for mocks. |
| Fix WACC | Skill graph → find cell → drill, or trust the Lab's auto plan | **Fix a Weakness** → search "wacc" or pick from Recommended / Recently missed → why weak, root cause, evidence, time → **Teach / Practice / Pressure-test / Re-test** |
| Run a realistic mock | Home → Realistic Superday card → 8-field form | **Today → Run a Full Mock** → one summary card (format, persona, bank, mix, input, hidden scores) → **Start mock**; Customize is a collapsed drawer; last setup remembered |
| Reach any advanced mode | 14 cards behind a disclosure | **Practice** groups by intent (quick / full / targeted / pressure / modeling) with duration, voice, hidden-vs-live, when to use, what it improves |
| Interview room | Transcript, live-eval card and a help card always visible | Question + answer + one status pill; transcript and controls in collapsible sections; keyboard shortcuts (Space, Enter, R, P, Esc); simulation vs learning badge |
| Debrief | Scores → corrections → long list | **30-second verdict** (headline, what held up, highest-leverage problems, next-action buttons) → scores → corrections → question list (collapsible) → delivery → callbacks |
| Progress / Library | Separate nav items for skills, history, career, bank, resume, profile | Two tabbed screens; shortcuts for power access |

### Manual QA (four primary workflows)
1. Quick Practice: open `/#/today`, click **Quick Practice** → Daily Draft room opens with the first question read aloud; answer by voice or text; finish → debrief shows the verdict block; Today shows "Daily done".
2. Prepare: `/#/prepare` → New plan: J.P. Morgan, healthcare, First round, a date → **Create plan** → plan page → **Start recommended 25-min** → room shows the J.P. Morgan intro; `/#/mock` now defaults to that plan.
3. Fix a Weakness: `/#/fix` → type "wacc" → Open → detail card shows why/root cause/evidence → **Practice (lab)** starts a lab session on the root cause; **Teach me** opens the layered explanation.
4. Full Mock: `/#/mock` → read the summary → **Start mock** (one click) → hands-free room with hidden scores → End → debrief verdict + next actions.

### Tests
`.venv/bin/python -m pytest -q --deselect tests/test_sources.py::test_ingest_is_idempotent_and_stable` → 73 passed. `tests/test_ux.py` covers the eight required checks (cold-start quick practice; mock defaults and context precedence; context → plan → launch; weakness search → four actions; all modes reachable; history/settings/mastery untouched by the new feeds; offline text-only; voice controls present in shipped markup).

### Deferred usability opportunities
- Interview-specific history filter chips (filter by context/bank exists in data via `config.context_id`; UI shows plain table).
- Progress "is improvement real?" view separating first-attempt vs repeat-question accuracy (data exists in `skills.history[].repeat`).
- Plan progress tracking (mark a plan item done; show coverage of the plan's technical areas over sessions).
- Compare two debriefs on the same skill side by side.
- Room: inline transcript correction without opening the typed box.
