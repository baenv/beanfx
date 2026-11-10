"""Checks fxkit.ground_impact: nothing before contact, more of everything as the weight rises, cracks only for heavy
blows, debris that flies, lands and rests, an empty cell at the end of life, and the same frames for the same seed.

    .venv/bin/python <skill>/tests/test_impact.py      # exits 0 when every check passes
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit"))
import checklog  # noqa: E402  (records each check for pytest, see conftest.py)
import fxkit as fk  # noqa: E402
import fxlib as fl  # noqa: E402

W, H, FPS, GY = 128, 80, 24, 60
X, Y = fl.wgrid(W, H, W / 2, GY)
TONES, DUST = (1, 2, 3), (4, 5, 6)
fails = []


def ok(cond, msg):
    checklog.record(cond, msg)
    if not cond:
        fails.append(msg)


def frame(f, weight="heavy", seed=3, life=1.2):
    m = np.full((H, W), -1, np.int8)
    return fk.ground_impact(m, X, Y, f, FPS, TONES, DUST, r=12, weight=weight, life=life, seed=seed)


ok((frame(-1) < 0).all(), "nothing before contact")
ok((frame(0) >= 0).any(), "something on the contact frame")

# more of everything as the weight rises, measured over the first half second
def busy(weight):
    return sum(int((frame(f, weight) >= 0).sum()) for f in range(12))


b = [busy(w) for w in ("light", "heavy", "finisher")]
ok(b[0] < b[1] < b[2], f"light < heavy < finisher: {b}")

# how high debris flies: highest debris pixel above the ground, per weight
def peak(weight):
    top = H
    for f in range(12):
        m = frame(f, weight)
        rows = np.nonzero(((m == TONES[1]) | (m == TONES[2])).any(1))[0]
        if len(rows):
            top = min(top, rows.min())
    return GY - top


p = [peak(w) for w in ("light", "heavy", "finisher")]
ok(p[0] < p[1] < p[2], f"debris flies higher with weight: {p}")

# cracks (tones[0]) only for heavy blows, and they stay while the rest settles
ok(not (frame(4, "light") == TONES[0]).any(), "a light hit leaves no crack")
ok((frame(4, "heavy") == TONES[0]).any() and (frame(14, "heavy") == TONES[0]).any(), "a heavy hit cracks and it stays")

# debris rests: two late frames inside the hold show the same debris pixels; dust is gone by then
late = [frame(f, "finisher", life=2.0) for f in (20, 21)]   # landed by 0.8 s, before the fade at 1.2 s
deb = [np.isin(m, TONES[1:]) for m in late]
ok(deb[0].any() and (deb[0] == deb[1]).all(), "debris lies still once it lands")
ok(not np.isin(frame(15, "finisher"), DUST).any(), "dust has broken up by half its life (0.6 s)")
ok(all((np.nonzero(d)[0] >= GY - 4).all() for d in deb), "resting debris sits on the ground")

# the one-shot ends empty and repeats for the same seed
ok((frame(int(np.ceil(1.2 * FPS)), "finisher") < 0).all(), "empty at the end of life")
ok((frame(5, seed=7) == frame(5, seed=7)).all() and not (frame(5, seed=7) == frame(5, seed=8)).all(), "seeded")

# it stays inside a cell sized for the blow: nothing in the outer 2 px
edge = np.zeros((H, W), bool)
edge[:2], edge[-2:], edge[:, :2], edge[:, -2:] = True, True, True, True
ok(not any(((frame(f, "finisher") >= 0) & edge).any() for f in range(int(1.2 * FPS))), "inside the cell")

for f in fails:
    print("FAIL", f)
print(f"{'ok' if not fails else len(fails)} impact checks")
sys.exit(1 if fails else 0)
