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


def synthesize(text: str, voice: Optional[str] = None, rate: int = 175) -> Optional[str]:
    """Return path to an m4a file (cached by content hash)."""
    if not available() or not text.strip():
        return None
    os.makedirs(CACHE, exist_ok=True)
    voice = voice or "Samantha"
    key = hashlib.sha1(("%s|%s|%d|%s" % (voice, rate, 1, text)).encode()).hexdigest()[:20]
    path = os.path.join(CACHE, key + ".m4a")
    if os.path.exists(path):
        return path
    try:
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", path, "--file-format=m4af", text], check=True, timeout=60, capture_output=True)
    except Exception:
        try:
            subprocess.run(["say", "-r", str(rate), "-o", path, "--file-format=m4af", text], check=True, timeout=60, capture_output=True)
        except Exception:
            return None
    return path if os.path.exists(path) else None
