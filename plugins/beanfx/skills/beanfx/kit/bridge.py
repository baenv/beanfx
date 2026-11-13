"""The call into the beanfx binary, the Rust half of the kit (the skill's rust/): sheet export and its checks,
sound, and the preview writers. setup.sh builds it into the project's .venv/bin/beanfx.

    import bridge
    value = bridge.run("export", "check", {"loop": False}, arrays={"frames": stack})

The binary is BEANFX_BIN, else the first .venv/bin/beanfx in a folder above this kit or the current folder, else
beanfx on PATH. Arrays go over as .npy files in a temporary folder; the answer is JSON, and arrays the binary
returns come back as numpy arrays in a dict (run(..., want_arrays=True) returns (value, arrays)).
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

PROTOCOL = 1
_found = None


class BeanfxError(RuntimeError):
    pass


def binary():
    """The path of the beanfx binary; raises with the fix when there is none."""
    global _found
    if _found:
        return _found
    env = os.environ.get("BEANFX_BIN")
    if env:
        _found = env
        return env
    for start in (Path(__file__).resolve().parent, Path.cwd().resolve()):
        for d in (start, *start.parents):
            p = d / ".venv" / "bin" / "beanfx"
            if p.is_file():
                _found = str(p)
                return _found
    p = shutil.which("beanfx")
    if p:
        _found = p
        return p
    raise BeanfxError("no beanfx binary: run setup.sh (it builds the skill's rust/ into .venv/bin/beanfx), "
                      "or set BEANFX_BIN")


def _jsonable(v):
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, Path):
        return str(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    return v


def _save(path, a):
    a = np.asarray(a)
    if a.dtype == bool:
        a = a.astype(np.uint8)
    elif a.dtype.kind == "f" and a.dtype != np.float64:
        a = a.astype(np.float64)
    elif a.dtype.kind in "iu" and a.dtype != np.uint8:
        a = a.astype(np.int64)
    np.save(path, np.ascontiguousarray(a))


def run(area, cmd, args=None, arrays=None, want_arrays=False):
    """One call: args (JSON-able) and arrays {name: ndarray} in, the answer's value out."""
    with tempfile.TemporaryDirectory(prefix="beanfx-") as tmp:
        paths = {}
        for k, a in (arrays or {}).items():
            if a is None:
                continue
            paths[k] = os.path.join(tmp, f"{k}.npy")
            _save(paths[k], a)
        job = json.dumps({"args": _jsonable(args or {}), "arrays": paths, "dir": tmp, "protocol": PROTOCOL})
        run_ = subprocess.run([binary(), area, cmd], input=job, capture_output=True, text=True)
        if run_.stderr:
            print(run_.stderr, end="")
        try:
            ans = json.loads(run_.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise BeanfxError(f"beanfx {area} {cmd} exited {run_.returncode} with no answer: "
                              f"{run_.stdout[-500:]}{run_.stderr[-500:]}") from None
        if "error" in ans:
            raise BeanfxError(f"beanfx {area} {cmd}: {ans['error']}")
        for line in ans.get("print", []):
            print(line)
        value = ans.get("value")
        if want_arrays:
            return value, {k: np.load(p) for k, p in (ans.get("arrays") or {}).items()}
        return value


def stack(frames):
    """A list of equal (h, w, c) frames, or a list of rows of them, as one array (n, h, w, c) or (r, n, h, w, c)."""
    if isinstance(frames[0], (list, tuple)):
        return np.stack([np.stack([np.asarray(f) for f in row]) for row in frames])
    return np.stack([np.asarray(f) for f in frames])
