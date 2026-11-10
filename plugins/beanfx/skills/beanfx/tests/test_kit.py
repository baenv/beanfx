"""Checks the kit helpers drafts used to write by hand: fxlib.Pen (put and line in world px) and pfx.contact.

    .venv/bin/python <skill>/tests/test_kit.py      # exits 0 when every check passes
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit"))
import checklog  # noqa: E402  (records each check for pytest, see conftest.py)
import fxlib  # noqa: E402
import pfx  # noqa: E402

fails = []


def ok(cond, msg):
    checklog.record(cond, msg)
    if not cond:
        fails.append(msg)


# Pen: a point in grid coordinates lands on the pixel whose centre the grid reads as that point
W, H, PX, PY = 40, 30, 17, 12
for dens in (1.0, 2.0):
    x, y = fxlib.wgrid(W, H, PX, PY, dens)
    pen = fxlib.Pen(PX, PY, dens)
    for col, row in [(PX, PY), (PX - 7, PY + 3), (PX + 10, PY - 9)]:
        wx, wy = x[row, col], y[row, col]
        m = fxlib.empty(W, H)
        pen.put(m, wx, wy, 3)
        ys, xs = np.nonzero(m >= 0)
        ok(len(ys) == 1 and (ys[0], xs[0]) == (row, col),
           "Pen.put at density %s lands on (%s, %s)" % (dens, wx, wy))
m = fxlib.empty(W, H)
fxlib.Pen(PX, PY).line(m, -5.5, 0.5, 4.5, 0.5, 2)
ys, xs = np.nonzero(m >= 0)
ok(set(ys) == {PY} and xs.min() == PX - 6 and xs.max() == PX + 4, "Pen.line runs along the pivot row")

# contact: n labelled moments, a second row for the reference, the same phases in both
fr = [np.full((10, 12, 4), [40 * i % 255, 80, 120, 255], np.uint8) for i in range(25)]
ref = [np.full((16, 8, 4), [200, 50, 50, 255], np.uint8) for _ in range(51)]
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "contact.png"
    picks = pfx.contact(p, fr, 24, n=6, scale=2)
    im = Image.open(p)
    ok(picks == [[0, 5, 10, 14, 19, 24]], "contact picks even phases: %s" % picks)
    one = im.size
    picks = pfx.contact(p, fr, 24, n=6, scale=2, ref=(ref, 30))
    ok(picks[0][0] == 0 and picks[0][-1] == 24 and picks[1][0] == 0 and picks[1][-1] == 50, "both rows end on the last frame")
    two = Image.open(p).size
    ok(two[1] > one[1] and two[0] >= one[0], "the reference adds a row: %s then %s" % (one, two))
    picks = pfx.contact(p, fr, 24, n=6, ref=(ref, 30), by="time")
    ok(picks[0][-1] is None and picks[0][3] is not None and picks[1][-1] == 50, "by time a shorter run leaves its late cells empty: %s" % picks)
    half = [np.zeros((10, 12, 4), np.uint8)]
    pfx.contact(p, half * 3, 12, n=3)
    ok(np.asarray(Image.open(p).convert("RGB"))[20, 20].tolist() == [16, 16, 24], "transparency goes over bg")

print("ok kit checks" if not fails else "\n".join("FAIL " + m for m in fails) + "\n%d kit checks" % len(fails))
sys.exit(1 if fails else 0)
