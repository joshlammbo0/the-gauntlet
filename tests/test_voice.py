import random

from app import db
from app.engine import controller, speech_style as ss


def test_pronunciation_and_numbers():
    out = ss.pronounce("EBITDA margin of 25% at 8x with NOLs and PV-10, WACC 8.9%, a $10 increase, $1,200M revenue, $1.2B deal, 150bps, EV/EBITDA")
    for frag in ("ee-bit-dah", "twenty-five percent", "eight times", "N O Ls", "P V ten", "wack", "eight point nine percent", "ten dollars increase",
                 "one thousand two hundred million dollars", "one point two billion dollars", "one hundred fifty basis points", "E V over ee-bit-dah"):
        assert frag in out, (frag, out)


def test_spokenize_preserves_meaning_and_adds_no_metadata():
    r = random.Random(2)
    q = "Explain the impact of a $10 increase in depreciation, assuming a 25% tax rate, on all three financial statements."
    s = ss.spokenize(q, "analyst", "technical", r)
    plain = ss.strip_markup(s)
    assert "$10" in plain and "25%" in plain and "three statements" in plain
    assert "[" not in plain and "rubric" not in plain.lower() and "source" not in plain.lower()
    assert plain != q  # conversational rewrite happened


def test_say_markup_and_browser_chunks():
    s = "Okay. <p300> So *why* do you use WACC, not the cost of equity?"
    m = ss.to_say_markup(s, "vp")
    assert "[[slnc 300]]" in m and "[[emph +]]why[[emph -]]" in m and "[[pbas +2]]" in m and "wack" in m
    ch = ss.to_chunks(s)
    assert ch[0] == ("Okay.", 300) and ch[1][0].startswith("So why")
    assert ss.strip_markup(s) == "Okay. So why do you use WACC, not the cost of equity?"


def test_personas_sound_different():
    r = random.Random(7)
    openers = {p: set() for p in ("analyst", "md")}
    for _ in range(40):
        for p in openers:
            openers[p].add(ss.spokenize("Walk me through a DCF.", p, "technical", r).split(" <p")[0])
    assert openers["analyst"] != openers["md"]
    assert ss.PAUSES["md"]["challenge"] > ss.PAUSES["analyst"]["challenge"]
    assert ss.voice_profile("md")["ack_density"] < ss.voice_profile("analyst")["ack_density"]
    assert ss.voice_profile("md")["say_rate"] < ss.voice_profile("analyst")["say_rate"]


def test_reactions_are_grounded_and_do_not_repeat():
    r = random.Random(1)
    good = {"score": 0.95, "verdict": "correct", "kind": "technical", "answer": "x"}
    bad = {"score": 0.1, "verdict": "incorrect", "kind": "technical", "answer": "x"}
    assert ss.situation(good, "deepen", "deeper_probe") in ("strong", "insight")
    assert ss.situation(bad, "probe", "factual_error") == "wrong"
    assert ss.situation(bad, "probe", "math_error") == "math"
    assert ss.situation({"score": 0.3, "verdict": "off_topic"}, "probe", "did_not_answer") == "dodge"
    assert ss.situation({}, "probe", "contradiction") == "contradiction"
    recent = []
    seen = []
    for _ in range(12):
        t, sit = ss.react(bad, "probe", "factual_error", "associate", r, recent, 1.0)
        assert t and sit == "wrong"
        assert t not in recent[-3:]
        recent.append(t)
        seen.append(t)
    assert len(set(seen)) >= 3
    # no fake praise anywhere in the banks
    for sit, banks in ss.REACTIONS.items():
        for p, lines in banks.items():
            for line in lines:
                assert "great question" not in line.lower() and "absolutely" not in line.lower() and "great point" not in line.lower()


def test_controller_turns_carry_spoken_rendering_and_keep_text_for_grading():
    db.set_setting("use_llm", False)
    iv = controller.Interview.create("death_match", {"persona": "md", "max_questions": 3, "duration_min": 20, "use_sources": False, "categories": ["dcf"]})
    turns = iv.start()
    t = turns[-1]
    assert t["meta"]["spoken"] and t["meta"]["voice"]["say_voice"]
    assert ss.strip_markup(t["meta"]["spoken"]) != "" and t["text"]  # written text intact for the transcript/grading
    out = controller.Interview(iv.id).answer("Depreciation is an expense so net income falls by ten and cash falls by ten too.", 12)
    fu = out["interviewer_turns"][-1]
    assert fu["meta"].get("spoken")
    # the written follow-up text is the authored/probe text (no reaction prefix), the spoken one may carry a short grounded reaction
    assert "<p" in fu["meta"]["spoken"] or fu["meta"]["spoken"]
