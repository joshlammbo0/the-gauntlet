"""Probe a persistent Claude CLI session using stream-json stdin/stdout to measure per-turn latency
without process cold start."""
import json, os, subprocess, sys, time
cli = os.environ["CLI"]
env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDECODE") and k != "CLAUDE_CODE_ENTRYPOINT"}
p = subprocess.Popen([cli, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--model", sys.argv[1] if len(sys.argv) > 1 else "sonnet"],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, bufsize=1)
def turn(text):
    t0 = time.time()
    p.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n"); p.stdin.flush()
    out = None
    while True:
        line = p.stdout.readline()
        if not line:
            break
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("type") == "result":
            out = d
            break
    dt = time.time() - t0
    return dt, (out or {}).get("result", "")[:80], (out or {}).get("duration_api_ms")
for i, q in enumerate(["Reply with exactly: OK", "Return JSON {\"n\": 2} and nothing else", "In one short sentence, why add back depreciation in UFCF?"]):
    dt, res, api = turn(q)
    print("turn %d: %.2fs (api %s ms) -> %r" % (i + 1, dt, api, res))
p.stdin.close(); p.terminate()
print("stderr:", p.stderr.read()[:300])
