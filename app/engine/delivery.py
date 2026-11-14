"""Transcript-based delivery metrics. These are text measurements, never judgments about the
speaker's confidence, honesty or ability. Acoustic measurements (pauses) come from the client when
available and are labelled separately."""
import re
from collections import Counter
from typing import Dict, List, Optional

FILLERS = [r"\bum+\b", r"\buh+\b", r"\ber+\b", r"\byou know\b", r"\bkind of\b", r"\bsort of\b", r"\bbasically\b",
           r"\bhonestly\b", r"\bi mean\b", r"\bliterally\b", r"\bobviously\b", r"\bactually\b", r"\blike,\b", r"\bso yeah\b"]
HEDGES = [r"\bi guess\b", r"\bi don'?t know\b", r"\bmaybe\b", r"\bor something\b", r"\bpretty much\b", r"\bi think\b",
          r"\bprobably\b", r"\bi feel like\b", r"\bnot sure\b", r"\bi'?m not (an )?expert\b"]
GENERIC_PHRASES = [r"\bfast.paced\b", r"\bdynamic environment\b", r"\bpassionate about finance\b", r"\bsteep learning curve\b",
                   r"\bwork with (the )?smartest people\b", r"\bteam player\b", r"\bhard.?working\b", r"\bdetail.?oriented\b",
                   r"\bgo.getter\b", r"\bperfectionis", r"\bwell.?rounded\b", r"\bmake an impact\b", r"\badd value\b"]
EXCUSE_PATTERNS = [r"\bi haven'?t (really )?(prepared|prepped|thought about)\b", r"\bgood question\b", r"\bthat'?s a (great|good) question\b"]

TARGETS = {  # seconds, by answer kind
    "story": (60, 120), "tmay": (60, 100), "why": (45, 75), "technical": (30, 120), "numeric": (5, 90), "rapid": (5, 40),
}


def _count(patterns: List[str], text: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for p in patterns:
        n = len(re.findall(p, text, flags=re.I))
        if n:
            out[re.sub(r"\\b|\(|\)|\?|\+", "", p).replace("\\", "")] = n
    return out


def analyze(text: str, duration_sec: Optional[float], kind: str = "technical", pauses: Optional[List[float]] = None) -> Dict:
    words = re.findall(r"[A-Za-z0-9'%$.]+", text)
    n_words = len(words)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    wpm = (n_words / (duration_sec / 60)) if duration_sec and duration_sec > 0 else None
    fillers = _count(FILLERS, text)
    hedges = _count(HEDGES, text)
    generic = _count(GENERIC_PHRASES, text)
    excuses = _count(EXCUSE_PATTERNS, text)
    filler_total = sum(fillers.values())
    hedge_total = sum(hedges.values())
    # repeated phrases (3-grams used 3+ times)
    toks = [w.lower().strip(".,") for w in words]
    grams = Counter(tuple(toks[i:i + 3]) for i in range(max(0, len(toks) - 2)))
    repeated = [" ".join(g) for g, n in grams.items() if n >= 3 and not all(t in {"the", "a", "of", "to", "and", "in", "is", "that", "it"} for t in g)]
    lo, hi = TARGETS.get(kind, TARGETS["technical"])
    length_flag = None
    if duration_sec:
        if duration_sec > hi * 1.25:
            length_flag = "too_long"
        elif duration_sec < lo * 0.5 and kind in ("story", "tmay", "why"):
            length_flag = "too_short"
    elif n_words:
        est = n_words / 150 * 60
        if est > hi * 1.25:
            length_flag = "too_long_est"
    pace_flag = None
    if wpm:
        if wpm > 190:
            pace_flag = "fast"
        elif wpm < 100:
            pace_flag = "slow"
    long_pauses = [p for p in (pauses or []) if p >= 3.0]
    notes = []
    if filler_total and n_words:
        per100 = filler_total / n_words * 100
        if per100 >= 3:
            notes.append("Filler density %.1f per 100 words (%s)." % (per100, ", ".join("%s×%d" % kv for kv in list(fillers.items())[:4])))
    if hedge_total >= 2:
        notes.append("Hedging %d times (%s)." % (hedge_total, ", ".join("%s×%d" % kv for kv in list(hedges.items())[:4])))
    if generic:
        notes.append("Generic phrases: %s." % ", ".join(generic))
    if excuses:
        notes.append("Stalling phrases: %s." % ", ".join(excuses))
    if repeated:
        notes.append("Repeated phrases: %s." % "; ".join(repeated[:3]))
    if length_flag == "too_long":
        notes.append("Answer ran %.0fs; target %d–%ds for this kind of question." % (duration_sec, lo, hi))
    if length_flag == "too_long_est":
        notes.append("About %d words; that is ~%.0fs spoken, above the %ds target." % (n_words, n_words / 150 * 60, hi))
    if length_flag == "too_short":
        notes.append("Only %.0fs; a story this short is usually missing the action or result." % duration_sec)
    if pace_flag == "fast":
        notes.append("Pace %.0f wpm (transcript-based); above ~180 the listener loses structure." % wpm)
    if long_pauses:
        notes.append("%d pause(s) over 3s (acoustic, from the recorder)." % len(long_pauses))
    return {
        "words": n_words, "sentences": len(sentences), "duration_sec": duration_sec, "wpm": round(wpm) if wpm else None,
        "fillers": fillers, "filler_total": filler_total, "hedges": hedges, "hedge_total": hedge_total,
        "generic_phrases": generic, "stalling": excuses, "repeated_phrases": repeated[:5],
        "length_flag": length_flag, "pace_flag": pace_flag, "long_pauses": len(long_pauses),
        "target_seconds": [lo, hi], "notes": notes,
        "basis": "transcript" if not pauses else "transcript+acoustic",
    }
