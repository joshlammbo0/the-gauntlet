"""LLM provider abstraction.

Order of preference (configurable via settings.llm_provider):
  anthropic_api : Anthropic Messages API (needs ANTHROPIC_API_KEY in .env or env). Model from settings.
  claude_cli    : the Claude Code binary in non-interactive mode (`claude -p`). Needs `claude /login` once.
  offline       : no model. Deterministic engine handles everything.

All callers use `complete_json(system, user, schema_hint)` and must tolerate `None` (offline or failure).
Deterministic checks always take precedence over model output downstream.
"""
import json
import os
import re
import shutil
import subprocess
import time
from typing import Dict, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))

DEFAULT_MODEL = "claude-sonnet-5-5"
TIMEOUT = 60


def _load_dotenv() -> None:
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def find_claude_cli() -> Optional[str]:
    cands = [os.environ.get("GAUNTLET_CLAUDE_CLI"), shutil.which("claude"),
             os.path.expanduser("~/.local/bin/claude"), os.path.expanduser("~/.claude/local/claude")]
    base = os.path.expanduser("~/Library/Application Support/Claude/claude-code")
    if os.path.isdir(base):
        for ver in sorted(os.listdir(base), reverse=True):
            vd = os.path.join(base, ver)
            if not os.path.isdir(vd):
                continue
            for sub in os.listdir(vd):
                p = os.path.join(vd, sub, "claude.app", "Contents", "MacOS", "claude")
                if os.path.exists(p):
                    cands.append(p)
    for c in cands:
        if c and os.path.exists(c) and os.access(c, os.X_OK):
            return c
    return None


class ProviderStatus:
    def __init__(self):
        self.api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        self.cli_path = find_claude_cli()
        self.cli_logged_in: Optional[bool] = None
        self.last_error: Optional[str] = None
        self.calls = 0
        self.failures = 0

    def probe_cli(self) -> bool:
        if not self.cli_path:
            self.cli_logged_in = False
            return False
        try:
            env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDECODE") and k != "CLAUDE_CODE_ENTRYPOINT"}
            r = subprocess.run([self.cli_path, "-p", "Reply with the single word OK", "--output-format", "text", "--model", "haiku"],
                               capture_output=True, text=True, timeout=45, env=env)
            out = (r.stdout + r.stderr).strip()
            self.cli_logged_in = r.returncode == 0 and "not logged in" not in out.lower() and "login" not in out.lower()[:80]
            if not self.cli_logged_in:
                self.last_error = out[:200]
        except Exception as e:  # noqa
            self.cli_logged_in = False
            self.last_error = str(e)[:200]
        return bool(self.cli_logged_in)

    def to_dict(self, active: str) -> Dict:
        return {"active": active, "anthropic_api_key": self.api_key, "claude_cli_path": self.cli_path,
                "claude_cli_logged_in": self.cli_logged_in, "last_error": self.last_error, "calls": self.calls, "failures": self.failures}


STATUS = ProviderStatus()


def active_provider(preference: str = "auto") -> str:
    if preference == "offline":
        return "offline"
    if preference == "anthropic_api":
        return "anthropic_api" if STATUS.api_key else "offline"
    if preference == "claude_cli":
        return "claude_cli" if STATUS.cli_path and (STATUS.cli_logged_in or STATUS.probe_cli()) else "offline"
    # auto
    if STATUS.api_key:
        return "anthropic_api"
    if STATUS.cli_path and (STATUS.cli_logged_in if STATUS.cli_logged_in is not None else STATUS.probe_cli()):
        return "claude_cli"
    return "offline"


def _extract_json(text: str) -> Optional[Dict]:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cand = m.group(1) if m else None
    if not cand:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            cand = text[start:end + 1]
    if not cand:
        return None
    try:
        return json.loads(cand)
    except Exception:
        return None


def _call_api(system: str, user: str, model: str, max_tokens: int = 1500) -> Optional[str]:
    import httpx  # local import so offline mode never needs it at import time
    key = os.environ.get("ANTHROPIC_API_KEY")
    base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    body = {"model": model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": user}]}
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(base + "/v1/messages", json=body, headers=headers)
        if r.status_code >= 400:
            STATUS.last_error = "API %s: %s" % (r.status_code, r.text[:200])
            return None
        data = r.json()
        return "".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")


def _call_cli(system: str, user: str, model: str, worker: Optional[str] = None) -> Optional[str]:
    alias = "sonnet" if "sonnet" in model else ("haiku" if "haiku" in model else ("opus" if "opus" in model else model))
    if worker:
        # persistent process: ~1-3s per turn instead of ~4-15s
        from app.llm.worker import POOL
        out = POOL.ask(STATUS.cli_path, worker, alias, system, user)
        if out is not None:
            return out
        STATUS.last_error = "worker %s failed; falling back to one-shot" % worker
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDECODE") and k != "CLAUDE_CODE_ENTRYPOINT"}
    prompt = system + "\n\n---\n\n" + user
    r = subprocess.run([STATUS.cli_path, "-p", prompt, "--output-format", "text", "--model", alias],
                       capture_output=True, text=True, timeout=TIMEOUT * 2, env=env)
    if r.returncode != 0:
        STATUS.last_error = (r.stderr or r.stdout)[:200]
        return None
    return r.stdout


def complete_text(system: str, user: str, preference: str = "auto", model: Optional[str] = None, worker: Optional[str] = None) -> Tuple[Optional[str], str]:
    """`worker` names a persistent CLI process ("evaluator" or "interviewer:<sid>"); None = one-shot call."""
    prov = active_provider(preference)
    model = model or DEFAULT_MODEL
    if prov == "offline":
        return None, prov
    STATUS.calls += 1
    t0 = time.time()
    try:
        out = _call_api(system, user, model) if prov == "anthropic_api" else _call_cli(system, user, model, worker)
    except Exception as e:  # noqa
        STATUS.last_error = str(e)[:200]
        out = None
    if out is None:
        STATUS.failures += 1
    STATUS.last_latency = time.time() - t0
    return out, prov


def complete_json(system: str, user: str, preference: str = "auto", model: Optional[str] = None, worker: Optional[str] = None) -> Tuple[Optional[Dict], str]:
    text, prov = complete_text(system + "\nRespond with a single JSON object and nothing else.", user, preference, model, worker)
    if text is None:
        return None, prov
    return _extract_json(text), prov
