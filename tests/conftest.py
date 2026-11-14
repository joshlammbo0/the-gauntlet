import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
_tmp = tempfile.mkdtemp(prefix="gauntlet-test-")
os.environ["GAUNTLET_DATA"] = _tmp
os.environ["GAUNTLET_DB"] = os.path.join(_tmp, "test.db")
os.environ["GAUNTLET_TTS_CACHE"] = os.path.join(_tmp, "tts")

import pytest  # noqa: E402
from app import db  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _init_db():
    db.init()
    db.set_setting("use_llm", False)
    db.set_setting("preload_whisper", False)
    yield
