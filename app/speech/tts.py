"""Server-side text-to-speech via macOS `say` → m4a (AAC). The browser's speechSynthesis is the
default client-side path; this is the higher-quality fallback/alternative with cached files."""
import hashlib
import os
import subprocess
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get("GAUNTLET_TTS_CACHE", os.path.join(HERE, "..", "..", "data", "tts"))

PREFERRED = ["Samantha", "Alex", "Daniel", "Karen", "Moira", "Tom", "Ava", "Evan", "Nathan", "Zoe", "Allison", "Susan", "Eddy (English (US))", "Flo (English (US))", "Reed (English (US))", "Rocko (English (US))", "Sandy (English (US))", "Shelley (English (US))"]

PERSONA_VOICES = {"analyst": "Samantha", "associate": "Alex", "vp": "Daniel", "md": "Tom", "hot_seat": "Daniel"}
PREMIUM_HINTS = ["Ava (Premium)", "Zoe (Premium)", "Evan (Enhanced)", "Tom (Enhanced)", "Samantha (Enhanced)", "Allison (Enhanced)", "Nathan (Enhanced)", "Joelle (Enhanced)", "Daniel (Enhanced)", "Oliver (Enhanced)", "Serena (Premium)", "Jamie (Premium)"]


def premium_installed() -> List[str]:
    names = {v["name"] for v in voices()}
    return [n for n in PREMIUM_HINTS if n in names] + sorted(n for n in names if ("Premium" in n or "Enhanced" in n) and n not in PREMIUM_HINTS)


def available() -> bool:
    return os.path.exists("/usr/bin/say")


def voices() -> List[Dict]:
    if not available():
        return []
    try:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    vs = []
    for line in out.splitlines():
        parts = line.split("#")[0].rstrip()
        if not parts:
            continue
        # name may contain spaces; language code is the last token
        toks = parts.split()
        lang = toks[-1]
        name = " ".join(toks[:-1]).strip()
        if lang.startswith("en"):
            vs.append({"name": name, "lang": lang, "preferred": name in PREFERRED})
    vs.sort(key=lambda v: (not v["preferred"], v["name"]))
    return vs


def default_voice(persona: str) -> str:
    names = {v["name"] for v in voices()}
    want = PERSONA_VOICES.get(persona, "Samantha")
    if want in names:
        return want
    for p in PREFERRED:
        if p in names:
            return p
    return next(iter(names), "Samantha")


def synthesize(text: str, voice: Optional[str] = None, rate: int = 175, persona: Optional[str] = None, expressive: bool = True, pause_scale: float = 1.0) -> Optional[str]:
    """Return path to an m4a file (cached by content hash). `text` may carry <pNNN> pause markers and *emphasis*;
    they become `say` embedded commands so questions get pauses, emphasis and a pitch lift."""
    if not available() or not text.strip():
        return None
    from app.engine import speech_style
    os.makedirs(CACHE, exist_ok=True)
    prof = speech_style.voice_profile(persona or "vp")
    voice = voice or prof["say_voice"]
    if voice not in {v["name"] for v in voices()}:
        voice = default_voice(persona or "vp")
    rate = rate or prof["say_rate"]
    if expressive:
        scaled = text
        if pause_scale != 1.0:
            import re as _re
            scaled = _re.sub(r"<p(\d+)>", lambda m: "<p%d>" % int(int(m.group(1)) * pause_scale), text)
        spoken = speech_style.to_say_markup(scaled, persona or "vp")
    else:
        spoken = speech_style.pronounce(speech_style.strip_markup(text))
    key = hashlib.sha1(("%s|%s|%d|%s" % (voice, rate, 3, spoken)).encode()).hexdigest()[:20]
    path = os.path.join(CACHE, key + ".m4a")
    if os.path.exists(path):
        return path
    try:
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", path, "--file-format=m4af", spoken], check=True, timeout=60, capture_output=True)
    except Exception:
        try:
            subprocess.run(["say", "-r", str(rate), "-o", path, "--file-format=m4af", spoken], check=True, timeout=60, capture_output=True)
        except Exception:
            return None
    return path if os.path.exists(path) else None
