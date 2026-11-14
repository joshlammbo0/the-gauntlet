"""Kokoro neural TTS sidecar (runs under tts-venv, Python 3.12).

POST /synth  {"text": "...with <p300> pauses and *emphasis*...", "voice": "am_fenrir", "speed": 0.95, "pause_scale": 1.0}
  -> audio/wav (24 kHz mono). Pauses become inserted silence; sentences are synthesized separately so
     prosody resets naturally; *emphasis* slows that chunk slightly.
GET  /health -> {"ok": true, "voices": [...], "loaded": true}

Local only (127.0.0.1). The model (data/kokoro/kokoro-v1.0.onnx, voices-v1.0.bin) never leaves the machine.
"""
import io
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import soundfile as sf

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from app.engine import speech_style  # noqa: E402  (pure python, works on 3.12)

MODEL = os.path.join(ROOT, "data", "kokoro", "kokoro-v1.0.onnx")
VOICES = os.path.join(ROOT, "data", "kokoro", "voices-v1.0.bin")
PORT = int(os.environ.get("KOKORO_PORT", "8872"))
SR = 24000

_lock = threading.Lock()
_k = None


def model():
    global _k
    if _k is None:
        from kokoro_onnx import Kokoro
        _k = Kokoro(MODEL, VOICES)
    return _k


def synth(text: str, voice: str, speed: float, pause_scale: float) -> bytes:
    k = model()
    pieces = re.split(r"(<p\d+>)", text)
    out = []
    for piece in pieces:
        m = re.match(r"<p(\d+)>", piece)
        if m:
            ms = int(int(m.group(1)) * pause_scale)
            out.append(np.zeros(int(SR * ms / 1000.0), dtype=np.float32))
            continue
        chunk = piece.strip()
        if not chunk:
            continue
        # sentence by sentence so each gets its own intonation contour
        for sent in re.split(r"(?<=[.?!])\s+(?=[A-Z\"'(])", chunk):
            s = sent.strip()
            if not s:
                continue
            emph = "*" in s
            spoken = speech_style.pronounce(s.replace("*", ""))
            spd = speed * (0.93 if emph else 1.0) * (0.96 if len(spoken.split()) > 22 else 1.0)
            with _lock:
                samples, sr = k.create(spoken, voice=voice, speed=max(0.6, min(1.4, spd)), lang="en-us")
            out.append(samples.astype(np.float32))
            out.append(np.zeros(int(SR * 0.12), dtype=np.float32))  # breath between sentences
    audio = np.concatenate(out) if out else np.zeros(SR // 10, dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, audio, SR, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            try:
                k = model()
                self._json(200, {"ok": True, "loaded": True, "voices": sorted(v for v in k.get_voices() if v[:2] in ("af", "am", "bf", "bm"))})
            except Exception as e:  # noqa
                self._json(500, {"ok": False, "error": str(e)[:200]})
        else:
            self._json(404, {"ok": False})

    def do_POST(self):
        if self.path != "/synth":
            return self._json(404, {"ok": False})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            t0 = time.time()
            wav = synth(body.get("text", ""), body.get("voice") or "am_fenrir", float(body.get("speed") or 1.0), float(body.get("pause_scale") or 1.0))
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav)))
            self.send_header("X-Synth-Seconds", "%.2f" % (time.time() - t0))
            self.end_headers()
            self.wfile.write(wav)
        except Exception as e:  # noqa
            self._json(500, {"ok": False, "error": str(e)[:300]})


if __name__ == "__main__":
    threading.Thread(target=model, daemon=True).start()  # warm the model while the port opens
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print("kokoro sidecar on http://127.0.0.1:%d" % PORT, flush=True)
    srv.serve_forever()
