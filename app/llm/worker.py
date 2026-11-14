"""Persistent Claude CLI workers (stream-json over stdin/stdout).

A cold `claude -p` call costs ~3s of process start-up on top of the model latency; a long-lived
process answers in ~1–3s. Workers:
  - "evaluator": stateless use; recycled every RECYCLE_TURNS turns so context does not accumulate.
  - "interviewer:<session_id>": one per live interview; keeps conversational memory (callbacks),
    expires after IDLE_SECONDS of inactivity.
Each worker is guarded by a lock; a wedged process is killed and restarted. All failures surface as
None so callers fall back to the deterministic engine.
"""
import json
import os
import subprocess
import threading
import time
from typing import Dict, Optional

RECYCLE_TURNS = 20
IDLE_SECONDS = 1800
TURN_TIMEOUT = 75


class Worker:
    def __init__(self, cli: str, model: str, system_prompt: str, name: str):
        self.cli = cli
        self.model = model
        self.system_prompt = system_prompt
        self.name = name
        self.proc: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()
        self.turns = 0
        self.last_used = time.time()
        self.last_error: Optional[str] = None
        self.started_at = 0.0

    def _spawn(self) -> None:
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDECODE") and k != "CLAUDE_CODE_ENTRYPOINT"}
        args = [self.cli, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--model", self.model,
                "--no-session-persistence", "--tools", "", "--system-prompt", self.system_prompt]
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, bufsize=1)
        self.turns = 0
        self.started_at = time.time()

    def _kill(self) -> None:
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def ask(self, text: str, timeout: float = TURN_TIMEOUT) -> Optional[Dict]:
        """Send one user message; return the CLI result dict (keys: result, duration_api_ms, ...) or None."""
        with self.lock:
            if not self.alive() or (self.name == "evaluator" and self.turns >= RECYCLE_TURNS):
                self._kill()
                try:
                    self._spawn()
                except Exception as e:  # noqa
                    self.last_error = "spawn: %s" % e
                    return None
            self.last_used = time.time()
            try:
                self.proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n")
                self.proc.stdin.flush()
            except Exception as e:  # noqa
                self.last_error = "write: %s" % e
                self._kill()
                return None
            result: Optional[Dict] = None
            box: Dict = {}

            def reader():
                while True:
                    line = self.proc.stdout.readline()
                    if not line:
                        return
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    if d.get("type") == "result":
                        box["r"] = d
                        return

            t = threading.Thread(target=reader, daemon=True)
            t.start()
            t.join(timeout)
            if t.is_alive() or "r" not in box:
                self.last_error = "timeout after %.0fs" % timeout
                self._kill()
                return None
            result = box["r"]
            self.turns += 1
            if result.get("is_error"):
                self.last_error = str(result.get("result"))[:200]
                return None
            return result


class WorkerPool:
    def __init__(self):
        self.workers: Dict[str, Worker] = {}
        self.lock = threading.Lock()
        self.stats = {"turns": 0, "failures": 0, "total_ms": 0.0, "last_ms": None}

    def get(self, cli: str, name: str, model: str, system_prompt: str) -> Worker:
        with self.lock:
            w = self.workers.get(name)
            if w is None or w.model != model or w.system_prompt != system_prompt:
                if w:
                    w._kill()
                w = Worker(cli, model, system_prompt, name)
                self.workers[name] = w
            self._reap()
            return w

    def _reap(self) -> None:
        now = time.time()
        for k in list(self.workers):
            w = self.workers[k]
            if k != "evaluator" and now - w.last_used > IDLE_SECONDS:
                w._kill()
                del self.workers[k]

    def ask(self, cli: str, name: str, model: str, system_prompt: str, text: str) -> Optional[str]:
        w = self.get(cli, name, model, system_prompt)
        t0 = time.time()
        r = w.ask(text)
        ms = (time.time() - t0) * 1000
        self.stats["turns"] += 1
        self.stats["last_ms"] = round(ms)
        self.stats["total_ms"] += ms
        if r is None:
            self.stats["failures"] += 1
            return None
        return r.get("result", "")

    def drop(self, name: str) -> None:
        with self.lock:
            w = self.workers.pop(name, None)
            if w:
                w._kill()

    def status(self) -> Dict:
        return {"workers": {k: {"alive": w.alive(), "turns": w.turns, "model": w.model, "last_error": w.last_error, "idle_s": round(time.time() - w.last_used)} for k, w in self.workers.items()},
                "avg_ms": round(self.stats["total_ms"] / self.stats["turns"]) if self.stats["turns"] else None, **{k: v for k, v in self.stats.items() if k != "total_ms"}}

    def shutdown(self) -> None:
        for k in list(self.workers):
            self.drop(k)


POOL = WorkerPool()
