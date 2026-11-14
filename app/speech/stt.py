"""Speech-to-text with faster-whisper (local, CPU). Finance vocabulary via initial_prompt plus a
post-correction table for common mis-hearings. Model loads lazily in a background thread."""
import os
import re
import threading
import time
from typing import Dict, List, Optional, Tuple

MODEL_NAME = os.environ.get("GAUNTLET_WHISPER", "small.en")
_model = None
_model_error: Optional[str] = None
_lock = threading.Lock()
_loading = False

FINANCE_PROMPT = ("Investment banking interview. EBITDA, EBIT, WACC, UFCF, unlevered free cash flow, NOL, NOLs, DCF, LBO, IRR, MOIC, "
                  "accretion, dilution, accretive, dilutive, APV, enterprise value, equity value, net working capital, terminal value, "
                  "Gordon growth, exit multiple, mid-year convention, basis differentials, Henry Hub, Marcellus, Utica, decline curve, "
                  "PDP, PUD, royalty interest, working interest, net revenue interest, PV-10, risk-adjusted NPV, rNPV, P/TBV, ROTCE, "
                  "net interest margin, CET1, treasury stock method, precedent transactions, trading comps, sources and uses, "
                  "Hobo Ventures, Georgetown, StandardAero, Viasat, Insulet, United Therapeutics, Tyvaso, Omnipod, Seahawks.")

CORRECTIONS: List[Tuple[str, str]] = [
    (r"\bwack\b|\bwhack\b|\bwac\b", "WACC"), (r"\bebit ?da\b|\bebitda\b|\be bit da\b|\beba da\b", "EBITDA"), (r"\bebit\b", "EBIT"),
    (r"\bu ?f ?c ?f\b", "UFCF"), (r"\bn ?o ?l ?(s)?\b", r"NOL\1"), (r"\bd ?c ?f(s)?\b", r"DCF\1"), (r"\bl ?b ?o(s)?\b", r"LBO\1"),
    (r"\bi ?r ?r\b", "IRR"), (r"\bmoic\b|\bmo ?ick\b|\bmoe ?ick\b", "MOIC"), (r"\ba ?p ?v\b", "APV"), (r"\bp ?v ?10\b|\bpv ten\b", "PV-10"),
    (r"\br ?n ?p ?v\b|\brisk adjusted npv\b", "rNPV"), (r"\bp ?e\b ratio", "P/E ratio"), (r"\bp to e\b", "P/E"), (r"\bp ?t ?b ?v\b|\bprice to tangible book\b", "P/TBV"),
    (r"\bcet ?1\b|\bcet one\b", "CET1"), (r"\bp ?d ?p\b", "PDP"), (r"\bp ?u ?d(s)?\b", r"PUD\1"), (r"\bn ?r ?i\b", "NRI"),
    (r"\bhenry hub\b", "Henry Hub"), (r"\bmarcellus\b", "Marcellus"), (r"\butica\b", "Utica"), (r"\bhobo ventures?\b", "Hobo Ventures"),
    (r"\bstandard ?aero\b", "StandardAero"), (r"\bvia ?sat\b", "Viasat"), (r"\binsulet\b|\bincel it\b|\binsolet\b", "Insulet"),
    (r"\btie ?vaso\b|\btyvaso\b", "Tyvaso"), (r"\bomni ?pod\b", "Omnipod"), (r"\bunited therapeutics\b", "United Therapeutics"),
    (r"\baccretive\b|\ba creative\b|\bacretive\b", "accretive"), (r"\baccretion\b|\ba creation\b", "accretion"), (r"\bdilutive\b|\bdelusive\b", "dilutive"),
    (r"\bgordon growth\b", "Gordon growth"), (r"\bbasis differential(s)?\b", r"basis differential\1"), (r"\btreasury stock method\b", "treasury stock method"),
    (r"\bper ?pet ?uity\b", "perpetuity"), (r"\bcap ?ex\b", "capex"), (r"\bop ?ex\b", "opex"), (r"\bfig\b", "FIG"),
    (r"\bthree statements?\b", "three statements"), (r"\bgaap\b", "GAAP"), (r"\bsotp\b|\bs ?o ?t ?p\b", "SOTP"), (r"\bsbc\b", "SBC"),
]


def status() -> Dict:
    return {"model": MODEL_NAME, "loaded": _model is not None, "loading": _loading, "error": _model_error}


def _load() -> None:
    global _model, _model_error, _loading
    with _lock:
        if _model is not None:
            return
        _loading = True
        try:
            from faster_whisper import WhisperModel
            _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8", cpu_threads=4)
            _model_error = None
        except Exception as e:  # noqa
            _model_error = str(e)
        finally:
            _loading = False


def preload_async() -> None:
    if _model is None and not _loading:
        threading.Thread(target=_load, daemon=True).start()


def correct(text: str) -> str:
    out = text
    for pat, rep in CORRECTIONS:
        out = re.sub(pat, rep, out, flags=re.I)
    # spoken numbers like "eight point nine percent" are usually already digits from whisper; normalize "percent"
    out = re.sub(r"(\d)\s*percent\b", r"\1%", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def transcribe(path: str) -> Dict:
    _load()
    if _model is None:
        return {"ok": False, "error": _model_error or "model unavailable", "raw": "", "text": ""}
    t0 = time.time()
    try:
        segments, info = _model.transcribe(path, beam_size=5, initial_prompt=FINANCE_PROMPT, vad_filter=True,
                                           vad_parameters={"min_silence_duration_ms": 500}, word_timestamps=False)
        segs = list(segments)
    except Exception as e:  # noqa: broad on purpose: corrupt/unsupported audio must not crash the server
        return {"ok": False, "error": "could not decode audio: %s" % str(e)[:160], "raw": "", "text": ""}
    raw = " ".join(s.text.strip() for s in segs).strip()
    pauses = []
    for a, b in zip(segs, segs[1:]):
        gap = b.start - a.end
        if gap >= 1.5:
            pauses.append(round(gap, 1))
    return {"ok": True, "raw": raw, "text": correct(raw), "duration": getattr(info, "duration", None),
            "language": getattr(info, "language", "en"), "pauses": pauses, "model": MODEL_NAME, "seconds": round(time.time() - t0, 2)}
