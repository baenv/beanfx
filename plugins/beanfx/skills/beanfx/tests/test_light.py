"""Checks kit/light.py: flashes that die, flicker that is seeded and varied, and a clear scene stays mostly dark.

    .venv/bin/python <skill>/tests/test_light.py      # exits 0 when every check passes
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit"))
import checklog  # noqa: E402  (records each check for pytest, see conftest.py)
import light  # noqa: E402

fails = []


def ok(cond, msg):
    checklog.record(cond, msg)
    if not cond:
        fails.append(msg)


ys, xs = np.mgrid[0:64, 0:64] + 0.5
c = SimpleNamespace(x=xs, y=ys)

# a flash is brightest when born, shrinks and dims, and is gone after its life
fl = light.Flashes()
fl.add(32.5, 32.5, 10, 0.6, life=6)
peaks, reach = [], []
for f in range(8):
    L = light.buffer(c)
    fl.draw(L, c)
    peaks.append(L.max())
    reach.append(int((L > 0.01).sum()))
    fl.step()
ok(abs(peaks[0] - 0.6) < 0.05, "a new flash starts at its k: %.3f" % peaks[0])
ok(all(a > b for a, b in zip(peaks[:6], peaks[1:6])), "a flash dims every frame: %s" % np.round(peaks, 3))
ok(all(a >= b for a, b in zip(reach[:6], reach[1:6])) and reach[5] < reach[0], "a flash shrinks: %s" % reach)
ok(peaks[6] == 0 and not fl.list, "a flash is gone after its life")

# flash_at draws the same light as Flashes from the frame alone, so it fits a per-frame render(f, seed)
fl = light.Flashes()
same = True
for f in range(10):
    if f == 2:
        fl.add(20.5, 30.5, 9, 0.5, life=5)
    A = light.buffer(c); fl.draw(A, c); fl.step()
    B = light.buffer(c); light.flash_at(B, c, f, 2, 20.5, 30.5, 9, 0.5, life=5)
    same = same and np.allclose(A, B)
ok(same, "flash_at matches Flashes frame by frame")
B = light.buffer(c); light.flash_at(B, c, 1, 2, 20.5, 30.5, 9, 0.5, life=5)
ok(B.max() == 0, "flash_at is dark before its birth frame")

# flicker: seeded, in 0..1, differs between sparks and between frames, steady at rate 0
a = [light.flicker(i, f, seed=3) for i in range(40) for f in range(30)]
ok(all(0 <= v <= 1 for v in a), "flicker stays in 0..1")
ok(a == [light.flicker(i, f, seed=3) for i in range(40) for f in range(30)], "flicker repeats for a seed")
ok(a != [light.flicker(i, f, seed=4) for i in range(40) for f in range(30)], "another seed flickers differently")
per_frame = np.array(a).reshape(40, 30)
ok(np.abs(np.diff(per_frame, axis=1)).mean() > 0.15, "flicker changes frame to frame")
ok(per_frame[:, 0].std() > 0.15, "sparks flicker out of step")
ok(light.flicker(5, 7, seed=3, rate=0) == light.flicker(5, 8, seed=3, rate=0), "rate 0 holds still")

# a clear scene (a few emitters, no scene pool) keeps most of its box dark
L = light.buffer(c)
light.glow(L, c, 20, 20, 6, 0.6)
light.glow_line(L, c, (40, 10), (40, 50), 3, 0.4)
ok((L > 0.03).mean() < 0.25, "a clear scene lights under a quarter of its box: %.2f" % (L > 0.03).mean())

# stepped light: a few flat values, hard inside, dithered only in the outer step, dark below the floor
L = light.buffer(c)
light.glow(L, c, 32.5, 32.5, 24, 1.0)
S = light.steps(L, levels=4, floor=0.06)
vals = set(np.round(np.unique(S), 6))
ok(vals <= {0.0, 0.25, 0.5, 0.75, 1.0}, "steps gives only the step values: %s" % sorted(vals))
ok(S.max() == 1.0, "steps keeps a white-hot core")
ok((S[L < 0.06] == 0).all(), "steps is dark below the floor")
inner = L >= 0.25
ok((S[inner] == np.floor(L[inner] * 4 + 1e-9) / 4).all(), "steps is hard inside the light, no dither")
outer = (L >= 0.06) & (L < 0.25)
lit = S[outer] > 0
ok(0.1 < lit.mean() < 0.9, "the outer step is dithered: %.2f lit" % lit.mean())
near = outer & (L > 0.2)
far = outer & (L < 0.1)
ok(S[near].mean() > S[far].mean(), "the dither thins out as the light fades")
ok(not np.array_equal(light.steps(L, phase=(1, 0)), S), "phase moves the dither grid")

print("ok light checks" if not fails else "\n".join("FAIL " + m for m in fails) + "\n%d light checks" % len(fails))
sys.exit(1 if fails else 0)
