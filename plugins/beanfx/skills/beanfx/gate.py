#!/usr/bin/env python3
"""The /beanfx brief gate: which knobs to ask the owner about before drawing.

Each knob is a file in knobs/ whose frontmatter holds two yes or no questions for Jev, an optional prompt
classifier client (~/.claude/hooks/jev.py, or BEANFX_JEV_PY); without it the model decides:
`stated` (true when the request already fixes the knob) and, for some knobs, `applies` (true when the knob matters
for this effect). One Jev call answers all of them; a knob is asked when it applies and is not stated.

    python3 ${CLAUDE_SKILL_DIR}/gate.py "<the owner's prompt>" [--context "<what a reference image shows>"]
    python3 ${CLAUDE_SKILL_DIR}/gate.py - < prompt.txt

Prints one JSON object and exits 0. Source "jev": `ask` (knob names in order) and `skip`. Source "model": Jev is
not available (no jev.py, no key, breaker open, an error); the model reads each knob file's "Fixed when" and
decides. BEANFX_GATE=model turns Jev off. Exit 2 only on bad usage. Standard library only.
"""
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KNOBS = HERE / "knobs"
ASK_BELOW = 0.5     # stated below this: the request leaves the knob open
APPLIES_AT = 0.5    # applies at or above this: the knob matters for this effect
BUDGET_S = 8.0


def load_knobs(folder=KNOBS):
    """Each knob file's one-line frontmatter fields, sorted by order."""
    knobs = []
    for path in sorted(folder.glob("*.md")):
        lines = path.read_text(encoding="utf-8").split("\n")
        if lines[0].strip() != "---":
            continue
        meta = {}
        for line in lines[1:]:
            if line.strip() == "---":
                break
            key, sep, val = line.partition(":")
            if sep:
                meta[key.strip()] = val.strip()
        if meta.get("name") and meta.get("stated"):
            meta["order"] = int(meta.get("order", 99))
            meta["file"] = str(path)    # absolute, so it reads from any project
            knobs.append(meta)
    return sorted(knobs, key=lambda k: k["order"])


def fallback(knobs, reason):
    out = {"source": "model", "reason": reason, "knobs": [k["file"] for k in knobs],
           "note": "Read each knob file's 'Fixed when' and decide which to ask."}
    print(json.dumps(out, indent=1))
    return 0


def import_jev():
    path = Path(os.environ.get("BEANFX_JEV_PY", "~/.claude/hooks/jev.py")).expanduser()
    if not path.is_file():
        return None
    sys.path.insert(0, str(path.parent))
    sys.dont_write_bytecode = True
    import jev
    return jev


def decide(knobs, answers):
    """Knob name to {stated, applies, ask} from Jev's noul answers."""
    out = {}
    for k in knobs:
        n = k["name"]
        stated = float(answers["stated::" + n]["noul"])
        applies = float(answers["applies::" + n]["noul"]) if k.get("applies") else 1.0
        out[n] = {"stated": round(stated, 3), "applies": round(applies, 3),
                  "ask": applies >= APPLIES_AT and stated < ASK_BELOW, "file": k["file"]}
    return out


def main(argv):
    args = argv[1:]
    context = ""
    if "--context" in args:
        i = args.index("--context")
        context = args[i + 1] if i + 1 < len(args) else ""
        del args[i:i + 2]
    if not args:
        print(__doc__.strip())
        return 2
    prompt = sys.stdin.read() if args[0] == "-" else " ".join(args)
    knobs = load_knobs()
    if not knobs:
        print(json.dumps({"source": "model", "reason": "no knob files"}))
        return 0
    if os.environ.get("BEANFX_GATE") == "model":
        return fallback(knobs, "BEANFX_GATE=model")
    try:
        jev = import_jev()
    except Exception as e:
        return fallback(knobs, "jev.py does not import: %s" % type(e).__name__)
    if jev is None:
        return fallback(knobs, "no jev.py")
    if jev.breaker_open():
        return fallback(knobs, "jev breaker open")
    key = jev.api_key()
    if not key:
        return fallback(knobs, "no jev api key")
    questions = {}
    for k in knobs:
        questions["stated::" + k["name"]] = {"type": "noul", "instructions": k["stated"]}
        if k.get("applies"):
            questions["applies::" + k["name"]] = {"type": "noul", "instructions": k["applies"]}
    state = {"request": jev.redact(prompt)[:6000],
             "task": "The request asks for a pixel-art game effect (a sprite sheet)."}
    if context:
        state["reference_image"] = jev.redact(context)[:1000]
    client, t0 = jev.Client(key), time.monotonic()
    record = {"ts": int(time.time()), "hook": "beanfx-gate", "prompt": jev.redact(prompt)[:120]}
    try:
        out = client.ask(state, questions, timeout=BUDGET_S)
        result = decide(knobs, out["answers"])
    except Exception as e:
        record["error"] = str(e)[:200] or type(e).__name__
        jev.breaker_record(record["error"])
        jev.log(record)
        return fallback(knobs, "jev failed: %s" % record["error"].split(":", 1)[0])
    finally:
        client.close()
    jev.breaker_record(None)
    record["ms"] = int((time.monotonic() - t0) * 1000)
    record["ask"] = [n for n, v in result.items() if v["ask"]]
    jev.log(record)
    print(json.dumps({"source": "jev", "ms": record["ms"], "ask": record["ask"],
                      "skip": [n for n, v in result.items() if not v["ask"]], "knobs": result}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
