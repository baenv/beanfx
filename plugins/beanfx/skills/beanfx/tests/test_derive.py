"""Checks kit/derive.py: outlines hug the shape and close, simplify hits its count, spines run down the middle,
part lines sit where parts meet, scatter stays inside and spreads, local and world round-trip.

    .venv/bin/python <skill>/tests/test_derive.py      # exits 0 when every check passes
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit"))
import checklog  # noqa: E402  (records each check for pytest, see conftest.py)
import derive as dv  # noqa: E402

fails = []


def check(name, ok, detail=""):
    checklog.record(ok, name)
    print(("ok   " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok:
        fails.append(name)


H, W = 80, 120
Y, X = np.mgrid[0:H, 0:W].astype(float)

# a disc, plus a stray speck that the outline must ignore
disc = np.hypot(X - 40, Y - 40) <= 20
disc_s = disc.copy()
disc_s[5, 110] = True
P = dv.outline(disc_s)
r = np.hypot(P[:, 0] - 40, P[:, 1] - 40)
check("outline on the disc edge", (r.min() >= 18.5) and (r.max() <= 20.5), f"r {r.min():.2f} to {r.max():.2f}")
step = np.abs(np.diff(np.vstack([P, P[:1]]), axis=0)).max()
check("outline is a closed 8-connected loop", step <= 1, f"max step {step}")
area = 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])
check("outline is clockwise on screen", area > 0, f"signed area {area:.0f}")
check("outline skips the speck", (P[:, 0] < 70).all())

S = dv.simplify(P, 24)
rs = np.hypot(S[:, 0] - 40, S[:, 1] - 40)
check("simplify near the count", abs(len(S) - 24) <= 2, f"{len(S)} points")
check("simplified points on the edge", (rs.min() >= 18.5) and (rs.max() <= 20.5))
ang = np.unwrap(np.arctan2(S[:, 1] - 40, S[:, 0] - 40))
check("simplified points keep their order", (np.diff(ang) > 0).all() or (np.diff(ang) < 0).all())
gaps = np.hypot(*np.diff(np.vstack([S, S[:1]]), axis=0).T)
check("simplified points spread round", gaps.max() < 3 * gaps.mean(), f"max gap {gaps.max():.1f}")

# a horizontal capsule: its spine is the axis
cap = (np.hypot(X - np.clip(X, 30, 90), Y - 40) <= 8)
sp = dv.spine(cap)
main = sp[0]
check("spine on the capsule axis", np.abs(main[:, 1] - 40).max() <= 1, f"y {main[:, 1].min()} to {main[:, 1].max()}")
check("spine spans the axis", np.ptp(main[:, 0]) >= 0.8 * 60, f"span {np.ptp(main[:, 0]):.0f}")
check("spine chain is ordered", np.abs(np.diff(main, axis=0)).max() <= 1)

# two parts meeting on x = 40: a disc split into left (0) and right (1)
parts = np.where(disc, np.where(X < 40, 0, 1), -1)
pl = dv.part_lines(parts)
check("one part line", len(pl) == 1, f"{len(pl)} lines")
check("part line where the parts meet", np.abs(pl[0][:, 0] - 40).max() <= 1 and np.ptp(pl[0][:, 1]) >= 36)

# scatter inside, spread out
pts = dv.scatter(disc, 30, seed=3)
inside = disc[pts[:, 1].astype(int), pts[:, 0].astype(int)].all()
d = np.hypot(*(pts[:, None] - pts[None]).transpose(2, 0, 1))
d[np.eye(len(pts), dtype=bool)] = np.inf
check("scatter count and inside", len(pts) == 30 and inside)
check("scatter spreads evenly", d.min() >= 0.5 * math.sqrt(disc.sum() / 30), f"min gap {d.min():.1f}")
check("scatter is seeded", np.array_equal(pts, dv.scatter(disc, 30, seed=3)))

# local and world
A, ang_, sc = (40.0, 40.0), 0.7, 1.6
L = dv.local(S, A, ang_, sc)
check("local then world round-trips", np.allclose(dv.world(L, A, ang_, sc), S))
moved = dv.world(L, (60.0, 30.0), ang_ + 0.3, sc)
r2 = np.hypot(moved[:, 0] - 60, moved[:, 1] - 30)
check("points ride the carrier", np.allclose(r2, rs * 1.0))

sys.exit(1 if fails else 0)
