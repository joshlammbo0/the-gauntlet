"""Spoken-presentation layer for the interviewer.

Everything the candidate HEARS passes through here; everything the engine GRADES does not. The
written question text, rubric and citations stay untouched; this module produces a `spoken`
rendering per persona:

  spokenize(text, persona, kind, rng)  -> conversational wording + pause markers
  react(evaluation, action, reason, persona, rng, recent) -> a short grounded reaction
  pronounce(text)                       -> acronym / symbol / number forms a TTS engine says well
  to_say_markup(text, persona)          -> macOS `say` embedded commands ([[slnc]], [[emph]], [[rate]])
  to_chunks(text)                       -> [(chunk, pause_ms)] for browser speechSynthesis

Pause markers are `<p250>` (milliseconds); emphasis is `*word*`. Both are stripped from anything
shown on screen (strip_markup).
"""
import random
import re
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------- pronunciation
# Written form -> spoken form. Applied only to the spoken rendering.
PRONOUNCE: List[Tuple[str, str]] = [
    (r"\bEBITDAR\b", "ee-bit-dar"), (r"\bEBITDA\b", "ee-bit-dah"), (r"\bEBITDAX\b", "ee-bit-dax"), (r"\bEBIT\b", "ee-bit"),
    (r"\bWACC\b", "wack"), (r"\bUFCF\b", "unlevered free cash flow"), (r"\bFCFE\b", "free cash flow to equity"), (r"\bFCF\b", "free cash flow"),
    (r"\bDCFs\b", "D C Fs"), (r"\bDCF\b", "D C F"), (r"\bLBOs\b", "L B Os"), (r"\bLBO\b", "L B O"), (r"\bNOLs\b", "N O Ls"), (r"\bNOL\b", "N O L"),
    (r"\bIRR\b", "I R R"), (r"\bMOIC\b", "mo-ick"), (r"\bAPV\b", "A P V"), (r"\bNPV\b", "N P V"), (r"\brNPV\b", "risk-adjusted N P V"),
    (r"\bPV-?10\b", "P V ten"), (r"\bP/E\b", "P E"), (r"\bP/TBV\b", "price to tangible book"), (r"\bP/B\b", "price to book"), (r"\bEV/EBITDA\b", "E V to ee-bit-dah"),
    (r"\bEV/Revenue\b", "E V to revenue"), (r"\bEV/EBIT\b", "E V to ee-bit"), (r"\bEV\b", "E V"), (r"\bTEV\b", "T E V"), (r"\bTSM\b", "treasury stock method"),
    (r"\bM&A\b", "M and A"), (r"\bS&U\b", "sources and uses"), (r"\bPP&E\b", "P P and E"), (r"\bD&A\b", "D and A"), (r"\bSG&A\b", "S G and A"), (r"\bR&D\b", "R and D"),
    (r"\bCFS\b", "cash flow statement"), (r"\bCFO\b", "cash flow from operations"), (r"\bCFI\b", "cash flow from investing"), (r"\bCFF\b", "cash flow from financing"),
    (r"\bBS\b", "balance sheet"), (r"\bIS\b(?=[\s:,.])", "income statement"), (r"\bNWC\b", "net working capital"), (r"\bNI\b", "net income"), (r"\bCapEx\b", "cap-ex"), (r"\bOpEx\b", "op-ex"),
    (r"\bSBC\b", "stock-based comp"), (r"\bRSUs?\b", "R S Us"), (r"\bDTLs?\b", "deferred tax liabilities"), (r"\bDTAs?\b", "deferred tax assets"), (r"\bNCI\b", "non-controlling interest"),
    (r"\bPDP\b", "P D P"), (r"\bPUDs?\b", "P U Ds"), (r"\bNRI\b", "N R I"), (r"\bNAV\b", "N A V"), (r"\bPPA\b", "P P A"), (r"\bCET1\b", "C E T one"), (r"\bROTCE\b", "rot-see"), (r"\bROE\b", "R O E"), (r"\bROIC\b", "ro-ick"),
    (r"\bNIM\b", "net interest margin"), (r"\bFIG\b", "fig"), (r"\bTMT\b", "T M T"), (r"\bIPO\b", "I P O"), (r"\bCIM\b", "sim"), (r"\bIOIs?\b", "I O Is"), (r"\bCVRs?\b", "C V Rs"),
    (r"\bYTM\b", "yield to maturity"), (r"\bERP\b", "equity risk premium"), (r"\bCAPM\b", "cap-M"), (r"\bGAAP\b", "gap"), (r"\bIFRS\b", "I F R S"), (r"\bASC 842\b", "A S C eight forty-two"),
    (r"\bQ([1-4])\b", r"Q\1"), (r"\bbps\b", "basis points"), (r"\bYoY\b", "year over year"), (r"\bLTM\b", "L T M"), (r"\bNTM\b", "N T M"), (r"\bFY\b", "fiscal"),
    (r"\bUTHR\b", "United Therapeutics"), (r"\bPODD\b", "Insulet"), (r"\bSARO\b", "StandardAero"), (r"\bVSAT\b", "Viasat"), (r"\bGCI\b", "G C I"), (r"\bGADIF\b", "gay-diff"), (r"\bMAP\b", "map"), (r"\bT1D\b", "type one diabetes"),
    (r"\bHenry Hub\b", "Henry Hub"), (r"\bTETCO\b", "tet-co"), (r"\bE&P\b", "E and P"), (r"\bO&G\b", "oil and gas"), (r"\bMRO\b", "M R O"), (r"\bLEO\b", "low earth orbit"),
]

ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}
SMALL = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _int_words(n: int) -> str:
    if n < 20:
        return SMALL[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else "-" + SMALL[n % 10])
    if n < 1000:
        return SMALL[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + _int_words(n % 100))
    if n < 1000000:
        return _int_words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + _int_words(n % 1000))
    return str(n)


def _num_words(s: str) -> str:
    s = s.replace(",", "")
    if "." in s:
        whole, frac = s.split(".", 1)
        return (_int_words(int(whole)) if whole else "zero") + " point " + " ".join(SMALL[int(c)] for c in frac if c.isdigit())
    try:
        return _int_words(int(s))
    except ValueError:
        return s


def speak_numbers(text: str) -> str:
    """$10 -> ten dollars; $1.2B -> one point two billion dollars; 25% -> twenty-five percent; 8x -> eight times;
    100bps -> one hundred basis points; years and big round figures are left to the engine."""
    def money(m):
        num, unit = m.group(1), (m.group(2) or "").lower()
        words = _num_words(num)
        unit_w = {"k": " thousand", "m": " million", "mm": " million", "b": " billion", "bn": " billion", "million": " million", "billion": " billion"}.get(unit, "")
        return "%s%s dollars" % (words, unit_w)
    text = re.sub(r"\$\s?(\d[\d,]*(?:\.\d+)?)(?:\s?(k|mm|m|bn|b|million|billion)\b)?", money, text, flags=re.I)
    text = re.sub(r"(\d[\d,]*(?:\.\d+)?)\s?%", lambda m: _num_words(m.group(1)) + " percent", text)
    text = re.sub(r"\b(\d+(?:\.\d+)?)x\b", lambda m: _num_words(m.group(1)) + " times", text)
    text = re.sub(r"\b(\d+)\s?bps\b", lambda m: _num_words(m.group(1)) + " basis points", text)
    text = re.sub(r"\b(\d+)-year\b", lambda m: _num_words(m.group(1)) + "-year", text)
    text = re.sub(r"\b(?<![\d.])(\d{1,3})(?![\d,.%x])\b(?!\s?(?:percent|times|basis|dollars|million|billion))", lambda m: _num_words(m.group(1)) if int(m.group(1)) <= 100 else m.group(1), text)
    return text


def pronounce(text: str) -> str:
    out = text
    for pat, rep in PRONOUNCE:
        out = re.sub(pat, rep, out)
    out = speak_numbers(out)
    out = out.replace("→", " to ").replace("−", " minus ").replace("≈", " about ").replace("×", " times ")
    out = re.sub(r"(?<=\w)/(?=\w)", " over ", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


# ---------------------------------------------------------------- written -> spoken rewrites
REWRITES: List[Tuple[str, str]] = [
    (r"^Explain the impact of (.+?) on all three financial statements\.?$", r"Let's say \1. Walk me through what happens to the three statements."),
    (r"^Walk me through how (.+?) flows? through the three statements\.?", r"Walk me through \1 across the three statements."),
    (r"^Explain (why|how|what) ", r"So \1 "),
    (r"^Describe ", "Tell me about "), (r"^Define ", "What's "), (r"^Please ", ""), (r"^Discuss ", "Talk me through "),
    (r"^What is the difference between ", "What's the difference between "), (r"^What is ", "What's "), (r"^What are ", "What are "),
    (r"^How do you calculate ", "How do you get to "), (r"^Provide an example of ", "Give me an example of "),
    (r"^In your own words, ", ""), (r"^Can you (explain|describe|walk me through) ", r"\1 ".replace("explain", "Explain").replace("describe", "Describe")),
    (r"Assume a (\d+%) tax rate\.?", r"Say the tax rate's \1."), (r"[Aa]ssuming a (\d+%) tax rate", r"with a \1 tax rate"),
    (r"\bi\.e\.,?\s*", "that is, "), (r"\be\.g\.,?\s*", "say, "), (r"\betc\.", "and so on"), (r"\(([^)]{1,40})\)", r", \1,"),
    (r"\s*\(Josh (used|had) [^)]*\)", ""), (r"\s*Your [A-Za-z]+ (bullet|model|pitch) says [^.]*\.", ""),
]

# persona-specific openers for MAIN questions (probability of using one, then the bank)
OPENERS: Dict[str, Tuple[float, List[str]]] = {
    "analyst": (0.55, ["Okay, so", "Alright,", "Cool. Next one:", "Let's try this one.", "Okay.", "Sure, so"]),
    "associate": (0.45, ["Alright.", "Next.", "Okay.", "Let's do this one.", "Moving on.", "Right."]),
    "vp": (0.4, ["Okay.", "Let's switch gears.", "Alright.", "Here's one.", "Fine.", "Let me ask you this."]),
    "md": (0.35, ["Okay.", "So.", "Let me ask you something.", "Alright.", "Here's what I actually care about."]),
    "hot_seat": (0.5, ["Okay.", "Next.", "Let's see.", "Try this.", "Different angle.", "Alright, keep going."]),
}

# pauses in ms by persona: after an opener, before a hard follow-up, between sentences in long questions
PAUSES: Dict[str, Dict[str, int]] = {
    "analyst": {"opener": 220, "sentence": 180, "challenge": 300, "think": 350},
    "associate": {"opener": 260, "sentence": 220, "challenge": 380, "think": 450},
    "vp": {"opener": 380, "sentence": 260, "challenge": 650, "think": 800},
    "md": {"opener": 450, "sentence": 300, "challenge": 800, "think": 1100},
    "hot_seat": {"opener": 150, "sentence": 160, "challenge": 420, "think": 300},
}

LONG_QUESTION_WORDS = 28


def strip_markup(text: str) -> str:
    return re.sub(r"\s*<p\d+>\s*", " ", text).replace("*", "").strip()


def spokenize(text: str, persona: str = "vp", kind: str = "technical", rng: Optional[random.Random] = None, opener: bool = True) -> str:
    """Conversational rendering of a written prompt. Meaning, numbers and difficulty are preserved."""
    rng = rng or random.Random()
    p = PAUSES.get(persona, PAUSES["vp"])
    t = text.strip()
    # drop anything that reads like metadata or a citation
    t = re.sub(r"\s*\[(source|citation|level|rubric)[^\]]*\]", "", t, flags=re.I)
    for pat, rep in REWRITES:
        t = re.sub(pat, rep, t, flags=re.M)
    # emphasize the pivotal word in common technical frames
    t = re.sub(r"\b(why|how|not|exactly|actually|really)\b(?=[^.?!]*\?)", r"*\1*", t, count=1, flags=re.I)
    # long multi-sentence prompts get breathing room between sentences
    sentences = re.split(r"(?<=[.?!])\s+", t)
    if len(sentences) > 1 and len(t.split()) > LONG_QUESTION_WORDS:
        t = (" <p%d> " % p["sentence"]).join(s.strip() for s in sentences if s.strip())
    # opener
    prob, bank = OPENERS.get(persona, OPENERS["vp"])
    if opener and kind in ("technical", "behavioral", "resume", "numeric", "deal") and rng.random() < prob:
        o = bank[rng.randrange(len(bank))]
        t = "%s <p%d> %s" % (o, p["opener"], t[0].upper() + t[1:] if t else t)
    t = re.sub(r",\s*([.?!])", r"\1", t)          # "rate,." -> "rate."
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"\s+([,.?!])", r"\1", t)
    return re.sub(r"\s{2,}", " ", t).strip()


# ---------------------------------------------------------------- grounded reactions
# Each bank is a list of short, natural lines. They are selected by (persona, situation) and never
# repeated back-to-back. Situations come from the evaluator/follow-up decision, so they are always
# tied to real grading evidence.
REACTIONS: Dict[str, Dict[str, List[str]]] = {
    "strong": {
        "analyst": ["Yeah, exactly.", "Yep, that's right.", "Nice, that's it.", "Good.", "Right, that's it."],
        "associate": ["Correct.", "Yes.", "That's right.", "Good."],
        "vp": ["Fine.", "Right.", "Yeah.", "Good."],
        "md": ["Good.", "Sure.", "Fine."],
        "hot_seat": ["That holds.", "Fine.", "Yeah."],
    },
    "partial": {
        "analyst": ["Okay, you're on the right track, but", "Close. But", "Mostly, yeah. One thing, though:", "Okay, partly."],
        "associate": ["You're missing something.", "That's incomplete.", "Partly.", "Okay, but there's a gap."],
        "vp": ["Okay, but", "You're skipping a step.", "That's half of it.", "Hm. Not quite all of it."],
        "md": ["Okay, but so what?", "You're part of the way there.", "Hm."],
        "hot_seat": ["You're skipping a step.", "Not all of it.", "Incomplete.", "Keep going; that's not the whole thing."],
    },
    "wrong": {
        "analyst": ["Hm, not quite.", "I don't think that's right.", "Okay, let's slow down.", "Not exactly."],
        "associate": ["That's not right.", "No.", "Check that.", "That's incorrect."],
        "vp": ["That's not right.", "No, think about that again.", "Hm. No.", "Walk that back."],
        "md": ["No.", "That's wrong.", "Try again."],
        "hot_seat": ["Wrong.", "No. Again.", "That's not it.", "Think about that."],
    },
    "vague": {
        "analyst": ["Can you be more specific?", "Okay, but what does that actually mean?", "Give me specifics."],
        "associate": ["Be specific.", "That's generic. Specifics.", "Give me the mechanics."],
        "vp": ["That's a generic answer.", "Can you be more specific?", "What does that mean in practice?"],
        "md": ["That's a generic answer. Give me a specific example.", "Be specific.", "What's the actual point?"],
        "hot_seat": ["That's generic. Specifics.", "Anyone could say that. What did *you* do?", "Be concrete."],
    },
    "dodge": {
        "analyst": ["That's not really what I asked, though.", "Okay, but come back to the question.", "Let me re-ask it."],
        "associate": ["That's not what I asked.", "Answer the question.", "You didn't answer it."],
        "vp": ["That's not really what I asked.", "You didn't answer the question.", "Come back to it."],
        "md": ["That's not what I asked.", "Answer the question I asked.", "No. The question was"],
        "hot_seat": ["That's not what I asked.", "You dodged it.", "Again. The question was"],
    },
    "math": {
        "analyst": ["You sure about that number?", "Hm, check that math for me.", "Run that again?"],
        "associate": ["You sure about that number?", "Check your math.", "That number's off."],
        "vp": ["You sure about that?", "Do that math again.", "That doesn't tie."],
        "md": ["You sure?", "Check that.", "Do it again."],
        "hot_seat": ["You sure about that number?", "Wrong number. Again.", "Check it."],
    },
    "contradiction": {
        "analyst": ["Hang on. Didn't you just say the opposite?", "Wait, earlier you said something different."],
        "associate": ["Hang on. Didn't you just say the opposite?", "That contradicts what you said earlier."],
        "vp": ["Hang on. Didn't you just say the opposite?", "That's not what you said a minute ago.", "Which is it?"],
        "md": ["Hang on. Didn't you just say the opposite?", "Which is it?"],
        "hot_seat": ["Hang on. Didn't you just say the opposite?", "You said the opposite two minutes ago. Which is it?"],
    },
    "ramble": {
        "analyst": ["Alright, let me stop you there.", "Okay, okay. Short version?"],
        "associate": ["Let me stop you there.", "Stop. One sentence."],
        "vp": ["Alright, let me stop you there.", "Your answer's getting long. What's the point?"],
        "md": ["Let me stop you there.", "What's the single most important point?"],
        "hot_seat": ["Stop. One sentence.", "Let me stop you there."],
    },
    "insight": {
        "analyst": ["Oh, interesting. Tell me more about that.", "Huh, good point. Go on."],
        "associate": ["Interesting. Go on.", "Okay, expand on that."],
        "vp": ["Interesting. Tell me more about that.", "Okay. Push on that."],
        "md": ["Interesting.", "Go on."],
        "hot_seat": ["Interesting. Defend it.", "Okay. Prove it."],
    },
    "gave_up": {
        "analyst": ["No worries. Start with what you do know.", "Okay, take it step by step."],
        "associate": ["Don't give up on it. First step?", "Start with what you know."],
        "vp": ["Take it from the top. What's the first thing that happens?", "Don't give up on it."],
        "md": ["Try.", "Start somewhere."],
        "hot_seat": ["No. Try.", "Start with step one."],
    },
    "pivot": {
        "analyst": ["Cool, let's switch gears.", "Okay, moving on.", "Alright, different topic."],
        "associate": ["Next.", "Different topic.", "Moving on."],
        "vp": ["Let's switch gears.", "Okay. Different topic.", "Let me change direction."],
        "md": ["Let's talk about something else.", "Different question."],
        "hot_seat": ["Different angle.", "Let's test something else.", "Next."],
    },
}

# Poker-face reactions for hidden-score modes: natural, varied, but revealing nothing about the verdict.
NEUTRAL: Dict[str, List[str]] = {
    "analyst": ["Okay.", "Mm-hm.", "Got it.", "Alright.", "Okay, sure."],
    "associate": ["Okay.", "Noted.", "Alright.", "Mm-hm.", "Understood."],
    "vp": ["Okay.", "Mm-hm.", "Alright.", "Noted.", "Keep going."],
    "md": ["Okay.", "Mm.", "Alright.", "Keep going."],
    "hot_seat": ["Okay.", "Alright.", "Keep going.", "Noted."],
}
# situations a real interviewer would still voice even when they are not grading out loud
REVEAL_SAFE = {"dodge", "ramble", "contradiction", "vague", "gave_up"}

SITUATION_FROM_REASON = {
    "factual_error": "wrong", "math_error": "math", "unsupported_assumption": "partial", "missing_causal": "partial", "contradiction": "contradiction",
    "overgeneralization": "partial", "irrelevant": "dodge", "weak_contribution": "vague", "missing_numbers": "vague", "superficial_industry": "vague",
    "did_not_answer": "dodge", "deeper_probe": "strong", "gave_up": "gave_up", "unsupported_claim": "partial", "generic": "vague", "too_long": "ramble", "level_up": "strong",
}


def situation(evaluation: Dict, action: str, reason: Optional[str]) -> str:
    if reason in SITUATION_FROM_REASON:
        s = SITUATION_FROM_REASON[reason]
        if s == "strong" and (evaluation.get("score") or 0) >= 0.9 and evaluation.get("kind") == "technical" and len((evaluation.get("answer") or "").split()) > 60:
            return "insight"
        return s
    v = evaluation.get("verdict")
    sc = evaluation.get("score") or 0
    if v in ("non_answer",):
        return "gave_up"
    if v in ("off_topic",):
        return "dodge"
    if sc >= 0.75:
        return "strong"
    if sc >= 0.4:
        return "partial"
    return "wrong"


def react(evaluation: Dict, action: str, reason: Optional[str], persona: str, rng: random.Random, recent: List[str], density: float = 1.0,
          hide_scores: bool = False) -> Tuple[str, str]:
    """Return (reaction_text, situation). `density` < 1 makes senior personas skip affirmations more often.
    With hide_scores, verdict-revealing situations fall back to a neutral acknowledgement (poker face)."""
    sit = situation(evaluation, action, reason)
    if hide_scores and sit not in REVEAL_SAFE:
        if rng.random() > density:
            return "", sit
        bank = NEUTRAL.get(persona) or NEUTRAL["vp"]
        choices = [b for b in bank if b not in recent[-3:]] or bank
        return choices[rng.randrange(len(choices))], sit
    if sit == "strong" and rng.random() > density:
        return "", sit
    bank = REACTIONS.get(sit, {}).get(persona) or REACTIONS.get(sit, {}).get("vp") or []
    choices = [b for b in bank if b not in recent[-3:]] or bank
    if not choices:
        return "", sit
    return choices[rng.randrange(len(choices))], sit


# ---------------------------------------------------------------- engine-specific markup
def to_say_markup(text: str, persona: str = "vp", rate_wpm: Optional[int] = None) -> str:
    """macOS `say` embedded commands: pauses -> [[slnc ms]], *word* -> [[emph +]]word[[emph -]]; a question mark
    gets a slight pitch lift via [[pbas +2]] on the last clause so questions sound like questions."""
    t = pronounce(text)
    t = re.sub(r"<p(\d+)>", lambda m: "[[slnc %s]]" % m.group(1), t)
    t = re.sub(r"\*([^*]+)\*", r"[[emph +]]\1[[emph -]]", t)
    # lift the final clause of a question
    parts = re.split(r"(?<=[.!?])\s+", t)
    out = []
    for s in parts:
        if s.rstrip().endswith("?") and len(s.split()) >= 4:
            words = s.split()
            k = max(1, len(words) - 4)
            s = " ".join(words[:k]) + " [[pbas +2]] " + " ".join(words[k:]) + " [[pbas -2]]"
        out.append(s)
    t = " ".join(out)
    if rate_wpm:
        t = "[[rate %d]] " % rate_wpm + t
    return re.sub(r"\s{2,}", " ", t).strip()


def to_chunks(text: str) -> List[Tuple[str, int]]:
    """For browser speechSynthesis (no SSML): split at pause markers and sentence ends; return (chunk, pause_after_ms)."""
    t = pronounce(text).replace("*", "")
    pieces = re.split(r"(<p\d+>)", t)
    chunks: List[Tuple[str, int]] = []
    buf = ""
    for piece in pieces:
        m = re.match(r"<p(\d+)>", piece)
        if m:
            if buf.strip():
                chunks.append((buf.strip(), int(m.group(1))))
            buf = ""
        else:
            buf += piece
    if buf.strip():
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", buf.strip()):
            if s.strip():
                chunks.append((s.strip(), 120))
    return chunks


# ---------------------------------------------------------------- persona voice profiles
VOICE_PROFILES: Dict[str, Dict] = {
    "analyst": {"say_voice": "Samantha", "say_rate": 188, "browser_rate": 1.06, "browser_pitch": 1.05, "ack_density": 1.0, "label": "quick, warm, conversational"},
    "associate": {"say_voice": "Alex", "say_rate": 178, "browser_rate": 1.0, "browser_pitch": 1.0, "ack_density": 0.8, "label": "direct, efficient, composed"},
    "vp": {"say_voice": "Daniel", "say_rate": 165, "browser_rate": 0.94, "browser_pitch": 0.95, "ack_density": 0.55, "label": "deliberate, comfortable with silence"},
    "md": {"say_voice": "Tom", "say_rate": 158, "browser_rate": 0.9, "browser_pitch": 0.9, "ack_density": 0.4, "label": "slow, sparse, judgment-focused"},
    "hot_seat": {"say_voice": "Daniel", "say_rate": 182, "browser_rate": 1.04, "browser_pitch": 0.97, "ack_density": 0.5, "label": "intense, rapid, skeptical"},
}


def voice_profile(persona: str) -> Dict:
    return VOICE_PROFILES.get(persona, VOICE_PROFILES["vp"])
