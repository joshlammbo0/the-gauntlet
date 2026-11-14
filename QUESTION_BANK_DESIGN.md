# QUESTION_BANK_DESIGN

## Taxonomy
Areas → skills (app/knowledge/skills.py, 67 skills): accounting, valuation, dcf, ma, lbo, fig, healthcare, energy,
commercial, math, behavioral, resume, deal. Every question maps to exactly one skill; mastery is tracked per skill.

## Question schema (app/knowledge/bank.py)
id, topic, subtopic, skill, difficulty (1 foundational … 6 multi-concept/expert), text, components
(expected answer parts with regex alternatives, weights, required flag), misconceptions (patterns + correction,
severity), followups (trigger → text, optional chained question id), solution, prereqs, variants, kind
(technical/behavioral/numeric/resume/deal), answer_type, assumptions (stated conventions, e.g. tax rate), source
(`original` written for this project / `standard` textbook convention), tags (`sensitive`, `evidence-check`,
`resume-defense`), sector.

## Content sourcing and quality controls
- All questions are original phrasings of standard IB interview material or built from the candidate's own documents (models,
  pitch decks, cover letters). No commercial guide text is reproduced.
- Facts about companies in the candidate's pitches come from his decks/models (UTHR deck 7 Oct 2026, Insulet DCF 17 Oct 2026,
  SARO/VSAT models, Seahawks model). Where a question mentions a market fact (e.g., PAH market size) it is the figure
  in the candidate's own deck, so the interviewer tests what he presented, not outside truth.
- Numeric questions are generated, never hand-typed; `numeric.self_test()` recomputes each answer independently.
- Conventions are stated in `assumptions` (tax rate, positive taxable income, stock vs asset deal).
- Difficulty rises through interacting concepts (depreciation → zero tax → NOLs → acquisition NOLs), not obscurity.
- `validate_bank()` enforces unique ids, resolvable prerequisites and chained ids, valid triggers, compilable regexes,
  components and solutions on every technical question.
- Default hint follow-ups are generated for components without an authored follow-up so the interviewer can always
  target the specific omission; authored follow-ups take precedence.

## Counts (2026-11-08)
263 authored questions (accounting 37, valuation 33, dcf 33, ma 28, energy 26, lbo 23, healthcare 16, fig 15,
commercial 15, behavioral 37), 17 numeric generators (unbounded variants), 77 resume-defense questions derived from
18 resume bullets, plus unknown-fact probes per experience.

## Known gaps
- FIG and healthcare depth is thinner than accounting/valuation/DCF.
- Deal-in-the-news questions depend on BankVault's verified deal records; the engine asks for headline terms but does
  not itself verify a candidate's deal facts beyond the few embedded in the candidate's documents.
- Behavioral scoring is rubric-based; without a model it cannot judge whether a story is *true* or *moving*, only
  whether it is specific, structured, owned, on-topic and concise.
