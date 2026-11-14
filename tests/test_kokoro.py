import os

import pytest

from app.speech import tts

pytestmark = pytest.mark.skipif(not tts.kokoro_installed(), reason="Kokoro sidecar not installed on this machine")


def test_engine_selection_prefers_kokoro_when_installed():
    assert tts.engine("auto") == "kokoro"
    assert tts.engine("say") == "say"


def test_sidecar_synthesizes_with_pauses_and_persona_voice():
    import wave
    p = tts.synthesize_kokoro("Okay. <p600> So *why* do you use WACC, not the cost of equity?", "vp", None, 1.0)
    assert p and os.path.exists(p) and p.endswith(".wav")
    with wave.open(p) as w:
        frames, rate = w.getnframes(), w.getframerate()
    dur = frames / rate
    assert 2.0 < dur < 12.0, dur
    # the pause marker adds silence: same text without it is shorter
    p2 = tts.synthesize_kokoro("Okay. So why do you use WACC, not the cost of equity?", "vp", None, 1.0)
    with wave.open(p2) as w:
        dur2 = w.getnframes() / w.getframerate()
    assert dur - dur2 >= 0.4
