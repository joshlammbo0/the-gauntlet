"""Render realistic interviewer turns to audio for a listening test.

Writes data/voice_demo/<persona>_<n>.m4a for a technical question, a behavioral question, a reaction to
a wrong answer, a reaction to a correct answer, a contradiction call and a ramble cut-off, in each
persona's voice. Also writes the spoken text alongside so you can compare what was said.
Usage: .venv/bin/python scripts/voice_demo.py [--voice "Ava (Premium)"]
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.engine import speech_style as ss  # noqa: E402
from app.speech import tts  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "voice_demo")
voice_override = None
if "--voice" in sys.argv:
    voice_override = sys.argv[sys.argv.index("--voice") + 1]

SCENES = [
    ("technical", "Explain the impact of a $10 increase in depreciation, assuming a 25% tax rate, on all three financial statements.", None),
    ("behavioral", "Tell me about a time you received tough feedback. What did you do with it?", None),
    ("wrong", "You left out the cash flow statement. Walk me through that side.", ("probe", "factual_error", {"score": 0.2, "verdict": "incorrect", "kind": "technical"})),
    ("right", "Now what changes if the tax rate is zero?", ("deepen", "deeper_probe", {"score": 0.95, "verdict": "correct", "kind": "technical", "answer": "x"})),
    ("contradiction", "Earlier you said the WACC was 8.9%; now you're saying 11%. Which is it?", ("probe", "contradiction", {})),
    ("ramble", "In one sentence: what's the single most important point?", ("probe", "too_long", {"score": 0.5})),
    ("numeric", "A company has EV of $1,200M, revenue of $500M and a 20% EBITDA margin. What is its EV/EBITDA multiple?", None),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    rng = random.Random(11)
    rows = []
    for persona in ("analyst", "associate", "vp", "md", "hot_seat"):
        recent = []
        for i, (label, text, react) in enumerate(SCENES):
            if react:
                action, reason, ev = react
                lead, _ = ss.react(ev, action, reason, persona, rng, recent, 1.0)
                recent.append(lead)
                pause = ss.PAUSES[persona]["challenge"]
                spoken = "%s <p%d> %s" % (lead, pause, ss.spokenize(text, persona, "followup", rng, opener=False)) if lead else ss.spokenize(text, persona, "followup", rng, opener=False)
            else:
                spoken = ss.spokenize(text, persona, label if label != "numeric" else "numeric", rng)
            path = tts.synthesize(spoken, voice_override, 0, persona, True, 1.0)
            dest = os.path.join(OUT, "%s_%d_%s.m4a" % (persona, i + 1, label))
            if path:
                os.replace(path, dest)
            rows.append((persona, label, spoken, ss.to_say_markup(spoken, persona), dest if path else "(no audio)"))
    with open(os.path.join(OUT, "spoken.txt"), "w") as f:
        for p, label, spoken, markup, dest in rows:
            f.write("[%s / %s]\n  spoken: %s\n  say:    %s\n  file:   %s\n\n" % (p, label, ss.strip_markup(spoken), markup, os.path.basename(dest)))
    print("wrote %d renders to %s" % (len(rows), os.path.abspath(OUT)))
    for p, label, spoken, markup, dest in rows[:7]:
        print("  %-10s %-13s %s" % (p, label, ss.strip_markup(spoken)[:110]))


if __name__ == "__main__":
    main()
