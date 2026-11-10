"""Checks gate.py against a local Jev stub: the ask rule, every fallback to the model, and the knob files.

    python3 <skill>/tests/test_gate.py      # exits 0 when every check passes; never calls the real Jev
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
GATE = SKILL / "gate.py"
sys.path.insert(0, str(SKILL))
import checklog  # noqa: E402  (records each check for pytest, see conftest.py)
import gate  # noqa: E402

# The stub answers stated::<knob> and applies::<knob> from this table (default 0.0 stated, 1.0 applies).
ANSWERS = {"stated::size": 0.9, "stated::role": 0.8, "applies::view": 0.2, "stated::glow": 0.5,
           "applies::states": 0.9, "stated::states": 0.1}
SEEN = []
STATUS = [200]


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        ans = {k: {"noul": ANSWERS.get(k, 0.0 if k.startswith("stated::") else 1.0)} for k in body["questions"]}
        data = json.dumps({"answers": ans}).encode()
        self.send_response(STATUS[0])
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Stub)
threading.Thread(target=srv.serve_forever, daemon=True).start()
tmp = tempfile.mkdtemp()
BASE = dict(os.environ, TYPESAFE_JEV_URL="http://127.0.0.1:%d" % srv.server_port, TYPESAFE_JEV_API="test-key",
            CLAUDE_JEV_BREAKER=os.path.join(tmp, "breaker"), CLAUDE_JEV_LOG=os.path.join(tmp, "jev.log"))
BASE.pop("BEANFX_GATE", None)
fails = []


def ok(cond, msg):
    checklog.record(cond, msg)
    if not cond:
        fails.append(msg)


def run(prompt, env=None, extra=()):
    p = subprocess.run([sys.executable, str(GATE), prompt, *extra], capture_output=True, text=True,
                       env=env or BASE, timeout=30)
    try:
        return p.returncode, json.loads(p.stdout)
    except ValueError:
        return p.returncode, {"raw": p.stdout + p.stderr}


# knob files: all sixteen, names match the file, each has a Jev question and a "Fixed when" or steps for the model
knobs = gate.load_knobs()
names = [k["name"] for k in knobs]
want = ["role", "view", "size", "timing", "loop", "shape", "style", "palette", "glow", "clarity", "density", "states", "caster", "combo", "placement", "aura"]
ok(names == want, "knob order %s" % names)
for k in knobs:
    ok(Path(k["file"]).stem == k["name"], "%s: file name" % k["name"])
    ok(k["stated"].startswith(("Does", "Is")) and "?" in k["stated"], "%s: stated is a question" % k["name"])
    ok(not k.get("applies") or k["applies"].endswith("?"), "%s: applies is a question" % k["name"])
    body = Path(k["file"]).read_text()
    ok("**Fixed when**" in body or "1. " in body, "%s: body says when it is fixed" % k["name"])
    ok("**Ask" in body or "2. Ask" in body, "%s: body has the question" % k["name"])
ok({k["name"] for k in knobs if k.get("applies")} == {"view", "density", "states", "caster", "combo", "placement", "aura"}, "applies set")

# Jev reads only the stated line, so an exclusion in a knob's "Fixed when" must be in that line too
by = {k["name"]: k for k in knobs}
for n, words in {"palette": "subject", "size": "256", "timing": "Fast", "glow": "Sparkling", "shape": "subject name",
                 "role": "two readings"}.items():
    ok(words in by[n]["stated"] and "not count" in by[n]["stated"], "%s: stated carries its exclusion" % n)

# every role in role.md has a row in the size table
roles = by["role"]["stated"].split("(")[1].split(")")[0].split(", ")
size_rows = [ln.split("|")[1].strip() for ln in Path(by["size"]["file"]).read_text().splitlines()
             if ln.startswith("| ") and not ln.startswith("| role")]
ok(sorted(roles) == sorted(size_rows), "size rows %s match the roles %s" % (size_rows, roles))

# the Jev client is optional; without it (a fresh clone, CI) only the model path is checked
JEV_PY = Path(os.environ.get("BEANFX_JEV_PY", "~/.claude/hooks/jev.py")).expanduser()
HAVE_JEV = JEV_PY.is_file()

if HAVE_JEV:
    # the ask rule through the stub
    code, out = run("a fireball", extra=("--context", "a blue comet sketch"))
    ok(code == 0 and out.get("source") == "jev", "stub run exits 0 with source jev: %s" % out)
    ask = out.get("ask", [])
    ok("size" not in ask and "role" not in ask, "stated knobs are skipped")
    ok("view" not in ask, "a knob that does not apply is skipped")
    ok("glow" not in ask, "stated at exactly 0.5 counts as stated")
    ok("states" in ask and "timing" in ask and "shape" in ask, "open knobs that apply are asked")
    ok(ask == [n for n in want if n in ask], "ask keeps the knob order")
    q = SEEN[-1]["questions"]
    ok(len(q) == 16 + 7 and all(v["type"] == "noul" for v in q.values()), "one call, 23 nouls")
    ok(SEEN[-1]["state"].get("reference_image") == "a blue comet sketch", "context reaches Jev")
    ok("fireball" in SEEN[-1]["state"]["request"], "prompt reaches Jev")

# every fallback exits 0 with source model and the knob files
code, out = run("x", env=dict(BASE, BEANFX_GATE="model"))
ok(code == 0 and out.get("source") == "model" and len(out.get("knobs", [])) == 16,
   "BEANFX_GATE=model")
code, out = run("x", env=dict(BASE, BEANFX_JEV_PY=os.path.join(tmp, "nope.py")))
ok(code == 0 and out.get("reason") == "no jev.py" and "hint" not in out, "missing jev.py: %s" % out)
if not HAVE_JEV:
    code, out = run("x")
    ok(code == 0 and out.get("source") == "model" and out.get("reason") == "no jev.py", "no client: %s" % out)
else:
    code, out = run("x", env=dict(BASE, TYPESAFE_JEV_API="", TYPESAFE_API_KEY="", TYPESAFE_JEV_KEYCHAIN="beanfx-none"))
    ok(code == 0 and "key" in out.get("reason", ""), "no key: %s" % out)
    STATUS[0] = 500
    for _ in range(2):
        code, out = run("x")
        ok(code == 0 and out.get("reason", "").startswith("jev failed"), "HTTP 500: %s" % out)
    STATUS[0] = 200
    code, out = run("x", env=dict(BASE, TYPESAFE_JEV_URL="http://127.0.0.1:9"))
    ok(code == 0 and out.get("source") == "model", "server down: %s" % out)
    code, out = run("x")    # three failed calls above trip (the no-key run sends nothing) the isolated breaker
    ok(code == 0 and out.get("reason") == "jev breaker open", "breaker open after 3 failures: %s" % out)
srv.shutdown()

for f in fails:
    print("FAIL", f)
print("%s gate checks%s" % ("ok" if not fails else len(fails), "" if HAVE_JEV else " (model path only, no Jev client)"))
sys.exit(1 if fails else 0)
