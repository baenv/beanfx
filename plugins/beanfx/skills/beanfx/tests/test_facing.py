"""Checks kit/facing.py: heading rows point the right way, mirroring keeps pivots and pixels, the JSON holds.

    .venv/bin/python <skill>/tests/test_facing.py      # exits 0 when every check passes
"""
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit"))
import checklog  # noqa: E402  (records each check for pytest, see conftest.py)
import facing as fc  # noqa: E402

W = H = 48
PIV = (24.0, 24.0)


def bolt(a, f):
    """A head 14 px from the pivot along a, with a dim tail behind it."""
    img = np.zeros((H, W, 4), np.uint8)
    ys, xs = np.mgrid[0:H, 0:W] + 0.5
    u = (xs - PIV[0]) * math.cos(a) + (ys - PIV[1]) * math.sin(a)
    v = -(xs - PIV[0]) * math.sin(a) + (ys - PIV[1]) * math.cos(a)
    head = (u - 14) ** 2 + v ** 2 < 9
    tail = (abs(v) < 1) & (u > -4) & (u < 12)
    img[tail] = (120, 60, 20, 255)
    img[head] = (255, 240, 200, 255)
    return img


def heading_of(frame):
    ys, xs = np.nonzero(frame[..., 0] == 255)
    return math.atan2(ys.mean() + 0.5 - PIV[1], xs.mean() + 0.5 - PIV[0]) % fc.TAU


fails = []


def ok(cond, msg):
    checklog.record(cond, msg)
    if not cond:
        fails.append(msg)


for n in (8, 16):
    rs = fc.rows(bolt, n, 3)
    ok(len(rs) == n and all(len(r) == 3 for r in rs), f"{n}: rows shape")
    for k, r in enumerate(rs):
        got, want = heading_of(r[0]), fc.TAU * k / n
        err = abs((got - want + math.pi) % fc.TAU - math.pi)
        ok(err < 0.05, f"{n}: row {k} points at {math.degrees(got):.1f}, want {math.degrees(want):.1f}")
        dx, dy = math.cos(want) * 10, math.sin(want) * 10
        ok(fc.row_of(dx, dy, n) == k, f"{n}: row_of for row {k}")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.png"
        fc.sheet(rs, p)
        ok(Image.open(p).size == (3 * W, n * H), f"{n}: sheet size")
    m = fc.check(fc.meta("top-down", W, H, PIV, directions=n))
    ok(m["directions"] == n and "row_rule" in m and "rows" not in m, f"{n}: meta")
ok(fc.meta("top-down", W, H, PIV, directions=8)["row_names"][2] == "south", "row 2 of 8 is south")
ok(fc.row_of(0, 5, 8) == 2 and fc.row_of(-5, 0, 8) == 4 and fc.row_of(0, -5, 8) == 6, "row_of compass")

# side view: an east sheet flipped faces west, pivot and target follow
east = [bolt(0.0, f) for f in range(3)]
west = fc.mirror(east)
ok(abs(heading_of(west[0]) - math.pi) < 0.05, "mirror faces west")
ok(np.array_equal(west[1], east[1][:, ::-1]), "mirror is a pixel flip")
m = fc.check(fc.meta("side", 176, 192, (40, 170), target=(150, 168)))
ok(m["facing"] == "east" and m["mirror"] is True, "side meta facing and mirror")
ok(m["mirror_pivot"] == [136, 170] and m["mirror_target"] == [26, 168], "mirror pivot and target are w - x")
ok(fc.meta("side", 176, 192, (88, 170))["mirror_pivot"] == [88, 170], "a centred pivot stays put")
json.dumps(m)

# split parts and the checks that must refuse bad metadata
split = fc.meta("side", 320, 200, (40, 172), target=(280, 172))
split["parts"] = dict(
    cast=fc.part("x_cast.png", 96, 96, 20, 24, (48, 88), False, "caster"),
    travel=fc.part("x_travel.png", 48, 48, 12, 24, (24, 24), True, "travel", speed=320,
                   **fc.meta("top-down", 48, 48, (24, 24), directions=16)),
    impact=fc.part("x_impact.png", 128, 128, 30, 24, (64, 110), False, "target"))
fc.check(split)
json.dumps(split)
bad = [
    dict(view="side", directions=1, facing="east", mirror=True),
    dict(view="side", directions=1, facing="east", mirror=False, sheets={}),
    dict(view="top-down", directions=6),
    dict(split, parts=dict(travel=fc.part("t.png", 8, 8, 4, 24, (4, 4), True, "travel"))),
    dict(split, parts=dict(cast=fc.part("c.png", 8, 8, 4, 24, (4, 4), False, "hand"))),
]
for i, b in enumerate(bad):
    try:
        fc.check(b)
        fails.append(f"bad meta {i} passed check")
    except ValueError:
        pass
try:
    fc.meta("isometric", W, H, PIV)
    fails.append("unknown view passed")
except ValueError:
    pass

for f in fails:
    print("FAIL", f)
print(f"{'ok' if not fails else len(fails)} facing checks")
sys.exit(1 if fails else 0)
