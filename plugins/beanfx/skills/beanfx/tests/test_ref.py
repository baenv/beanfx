"""Checks kit/ref.py on a drawn sword: the mask, value levels, derivative edges, skeleton and paint.

    .venv/bin/python <skill>/tests/test_ref.py      # exits 0 when every check passes
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit"))
import checklog  # noqa: E402  (records each check for pytest, see conftest.py)
import ref  # noqa: E402

fails = []


def ok(cond, msg):
    checklog.record(cond, msg)
    if not cond:
        fails.append(msg)


H, W = 60, 200
BLADE = (slice(26, 35), slice(20, 150))   # light steel
RIDGE = (slice(30, 31), slice(22, 148))   # dark line along the blade
GUARD = (slice(14, 47), slice(150, 156))  # mid bronze crossbar
GRIP = (slice(27, 34), slice(156, 186))   # dark grip


def sword(bg):
    img = np.zeros((H, W, 4), np.uint8)
    img[...] = bg
    img[BLADE] = (215, 220, 230, 255)
    img[RIDGE] = (90, 95, 110, 255)
    img[GUARD] = (170, 120, 50, 255)
    img[GRIP] = (60, 35, 25, 255)
    return img


shape = np.zeros((H, W), bool)
for s in (BLADE, GUARD, GRIP):
    shape[s] = True

with tempfile.TemporaryDirectory() as d:
    for tag, bg in (("plain ground", (250, 250, 245, 255)), ("alpha", (0, 0, 0, 0))):
        p = Path(d) / f"{tag}.png"
        Image.fromarray(sword(bg), "RGBA").save(p)
        t = ref.trace(p, tones=4)
        iou = (t.mask & shape).sum() / (t.mask | shape).sum()
        ok(iou > 0.98, f"{tag}: mask iou {iou:.3f}")
        ok(t.shade[28, 80] > t.shade[30, 170] and t.shade[28, 80] == 3, f"{tag}: blade lighter than grip "
           f"{t.shade[28, 80]} vs {t.shade[30, 170]}")
        ok(t.shade[30, 80] < t.shade[28, 80], f"{tag}: ridge darker than the blade")
        ok(t.edges[29:32, 40:140].any(axis=0).mean() > 0.95, f"{tag}: the ridge shows in the edges")
        ok(t.edges[26, 40:140].all() and not t.edges[0, :].any(), f"{tag}: rim on, background off")
        sp = max(t.spine, key=len)
        xs = [x for x, y in sp]
        ok(max(xs) - min(xs) > 120, f"{tag}: skeleton runs the blade, span {max(xs) - min(xs)}")
        ok(len(t.outline) > 50, f"{tag}: outline points")
        m = ref.paint(t, ramp_index=[1, 2, 3, 4], edge=0)
        ok(m[0, 0] == -1 and m[28, 80] in (0, 4) and set(np.unique(m[t.mask])) <= {0, 1, 2, 3, 4},
           f"{tag}: paint indices {np.unique(m)}")

    # scaling: a half size trace keeps the shape
    t2 = ref.trace(Path(d) / "alpha.png", height=30)
    ok(t2.mask.shape == (30, 100) and abs(t2.mask.mean() - shape.mean()) < 0.03, "half size mask")

for f in fails:
    print("FAIL", f)
print(f"{'ok' if not fails else len(fails)} ref checks")
sys.exit(1 if fails else 0)
