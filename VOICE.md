# VOICE.md — humanizing the interviewer (2026-11-14)

## Audit: why it sounded robotic
1. **Engine.** Only compact Apple voices (Samantha, Alex, Daniel, Tom…) were installed; no Premium/Enhanced voices. Chrome's built-in
   speechSynthesis used the same compact voices with a flat rate and pitch, one utterance per turn, no pauses.
2. **Text.** Questions were spoken exactly as written for reading ("Explain the impact of a $10 increase… assuming a 25% tax rate, on all
   three financial statements"), with acronyms spelled by the engine (EBITDA, WACC, NOL, PV-10) and symbols ($, %, x, /) read literally.
3. **Reactions.** Acknowledgements came from a 3–4 line persona list ("Okay.", "Fine.") and the follow-up text was read with no reaction,
   so right, wrong, dodged and contradictory answers all sounded the same.
4. **Timing.** No pauses before a challenge, no difference between a 5-word probe and a 40-word scenario, fixed 2.5 s silence cutoff that
   could not tell a thinking pause from a finished answer, no barge-in.

## What changed
- **Spoken layer** (`app/engine/speech_style.py`). Every interviewer turn now carries `meta.spoken`, a conversational rendering with
  `<pNNN>` pause markers and `*emphasis*`, while `text` (what the transcript shows and grading uses) is unchanged. Written→spoken rewrites
  ("Explain the impact of … on all three financial statements" → "Let's say … Walk me through what happens to the three statements"),
  persona openers ("Okay, so" / "Next." / "Let me ask you this."), sentence pauses on long prompts, number and symbol speech
  ("$1.2B" → "one point two billion dollars", "8x" → "eight times", "25%" → "twenty-five percent"), and pronunciation of ~80 terms
  (EBITDA → ee-bit-dah, WACC → wack, DCF → D C F, MOIC → mo-ick, PV-10 → P V ten, EV/EBITDA → E V over ee-bit-dah).
- **Grounded reactions.** 13 situations (strong, partial, wrong, vague, dodge, math, contradiction, ramble, insight, gave up, pivot…)
  × 5 personas, chosen from the evaluator's actual verdict and the follow-up reason, never repeated within the last three, prepended to
  the follow-up with a persona-length pause. Hidden-score modes use a neutral "poker face" set ("Okay.", "Hm.", "Mm-hm.") except for
  dodges, rambling, contradictions and requests for specifics, which real interviewers voice anyway. No "Great question".
- **Persona delivery** (`VOICE_PROFILES`, `PAUSES`): analyst quick/warm (188 wpm, short pauses, affirms often), associate direct (178),
  VP deliberate (165 wpm, 650 ms before a challenge, affirms about half the time), MD slow and sparse (158 wpm, 800 ms, affirms 40%),
  Hot Seat fast and skeptical (182 wpm, 150 ms openers). Each has its own Mac voice and browser rate/pitch.
- **Expressive synthesis.** Mac voice path converts markers to `say` embedded commands: `[[slnc]]` pauses, `[[emph +]]` emphasis, a
  `[[pbas +2]]` pitch lift on the final clause of questions, persona rate. Browser path splits into chunks at pauses and sentence ends,
  with per-chunk rate (slower for long clauses, quicker for short acks) and a pitch lift on questions; prefers an installed
  Premium/Enhanced voice automatically.
- **Model interviewer prompt** now carries the banker-voice guidance and examples; follow-ups rephrased by Claude land in the same spoken pipeline.
- **Conversation loop** (`static/app.js`): "Interviewer thinking…" status while the server works; adaptive silence (1.6× longer when the live
  caption ends mid-sentence, 1.3× when fewer than 12 words, capped at 6.5 s) so thinking pauses are not cut off; barge-in (sustained voice
  for 650 ms while the interviewer speaks cancels it and opens the mic; echo cancellation on, threshold 2.2× the silence floor; toggle in
  Settings); hands-free auto-record after the last chunk; pause-length and expressiveness controls.

## Measured / verified
- `tests/test_voice.py`: pronunciation and numbers, rewrites preserve meaning and strip metadata, say markup and browser chunks, personas
  differ (openers, pauses, affirmation density, rate), reactions grounded and non-repeating with no praise fillers, controller turns carry
  spoken renderings while written text stays intact. Full suite green.
- `scripts/voice_demo.py` renders 35 scenes (7 situations × 5 personas) to `data/voice_demo/*.m4a` with the spoken text in `spoken.txt`
  for a listening test.
- Offline deterministic turns verified end to end (see TEST_REPORT).

## Neural voice: Kokoro (installed 2026-11-14)

Kokoro-82M runs locally in a Python 3.12 sidecar (`tts-venv`, `kokoro-onnx` + onnxruntime), started by the app on launch
when `data/kokoro/kokoro-v1.0.onnx` and `voices-v1.0.bin` are present (gitignored, ~340 MB, from the kokoro-onnx
`model-files-v1.0` release). `scripts/kokoro_server.py` listens on 127.0.0.1:8872; `POST /synth` turns a spoken turn
into 24 kHz WAV: `<pNNN>` markers become real silence, each sentence is synthesized on its own so intonation resets,
`*emphasis*` slows that sentence slightly, and the pronunciation table is applied first.

- Engine order (`/api/tts`): Kokoro when installed and `tts_engine` is `auto`/`kokoro`, else macOS `say`, else browser.
  Settings shows the active engine (`/api/tts/engines`) and lets you pick any of the 28 English voices or keep per persona.
- Persona voices: analyst `af_heart` 1.06×, associate `am_michael` 1.0×, VP `am_fenrir` 0.95×, MD `am_onyx` 0.9×, Hot Seat `bm_george` 1.05×.
- Measured on this Mac (CPU): warm start 1.8 s; one short reaction + question ≈ 1.3 s for 4 s of audio; a long three-statement prompt 2.3 s for 9.5 s of audio. Results are cached in `data/tts/*.wav`, so repeated lines are instant.
- Listening renders: `.venv/bin/python scripts/voice_demo.py` now writes `data/voice_demo/*.wav` through Kokoro (`--engine say` for the old renders).
- Tests: `tests/test_kokoro.py` (skipped on machines without the sidecar) checks engine selection and that a `<p600>` marker lengthens the audio.

## Still limited by the engine
- The compact Apple voices remain the ceiling for timbre. The single biggest audible upgrade is free and local: System Settings →
  Accessibility → Spoken Content → System Voice → Manage Voices → download an English (US) **Premium** voice (Ava, Zoe, Evan, Tom).
  The app detects installed Premium/Enhanced voices (Settings shows them; the browser path prefers them automatically).
- A neural local engine (Kokoro-82M via onnxruntime) would be a further step up but needs a Python 3.12 sidecar (`uv` has 3.12 available)
  and a ~340 MB model download, which was not done without approval. Piper installs on 3.9 but its voices are not clearly better than Premium Apple voices.
- Emotional colouring (surprise, impatience) is approximated by wording, pauses and pitch; the compact voices cannot render it.

## Manual listening test (Chrome)

In Settings, leave Interviewer voice on "Server voice" so Kokoro is used; the engine line under it should read `kokoro`.

1. Settings → Voice: choose Mac system voice; if a Premium voice is installed pick it; leave Expressive on, pause 1.0×.
2. Start Deathmatch (analyst persona) and a Hot Seat run: compare openers, pacing and reactions.
3. Give one wrong, one half, one correct answer in a learning mode (Death Match ladder) and listen for "Not quite…", "You're on the right track, but…", "Yep, that's right."
4. Ramble past 150 s: expect "Alright, let me stop you there."
5. Start talking while the interviewer is mid-sentence: it should stop and the mic should open ("You cut in").
6. Pause mid-sentence for ~3 s while thinking: it should wait; finish a sentence and go quiet: it should submit after ~2.5 s.
