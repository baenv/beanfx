"""Checks the shape helpers a draft draws with: every painter in kit/fxkit.py and kit/fxlib.py draws something,
draws the same pixels on a second call (no hidden randomness), keeps to the shades it was given, and holds the
few rules a drawing leans on (a dissolve only removes, a hit ends empty, a puff breaks up from its edge), and the
mockup caster in kit/caster.py draws a figure.

    .venv/bin/python <skill>/tests/test_shapes.py      # exits 0 when every check passes
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit"))
import checklog  # noqa: E402  (records each check for pytest, see conftest.py)
import caster  # noqa: E402
import fxkit as fk  # noqa: E402
import fxlib as fl  # noqa: E402

fails = []


def ok(cond, msg):
    checklog.record(cond, msg)
    if not cond:
        fails.append(msg)


W, H = 64, 48
X, Y = fl.wgrid(W, H, W // 2, H // 2)


def painted(name, paint, shades, low=4):
    """paint(m) draws into an empty map: something is drawn, a second run draws the same, only `shades` are used."""
    a, b = fl.empty(W, H), fl.empty(W, H)
    paint(a)
    paint(b)
    used = set(np.unique(a[a >= 0]).tolist())
    ok(int((a >= 0).sum()) >= low, "%s draws (%d px)" % (name, int((a >= 0).sum())))
    ok(np.array_equal(a, b), "%s draws the same pixels twice" % name)
    ok(used <= set(shades), "%s keeps to its shades: %s of %s" % (name, sorted(used), sorted(set(shades))))
    return a


# ---- fxlib: colour, grids, strokes, noise ----
r = fl.ramp("#c83a1a")
lum = [fl._lum(c) for c in r]
ok(len(r) == 4 and lum == sorted(lum), "ramp gives four shades, dark to pale: %s" % r)
ok(fl.tohex(fl.hexc("#12ab9f")) == "#12ab9f", "hexc and tohex round trip")
gx, gy = fl.grid(8, 6, 3, 2)
ok(gx.shape == (6, 8) and gx[2, 3] == 0.5 and gy[2, 3] == 0.5, "grid reads pixel centres relative to the pivot")
wx, wy = fl.wgrid(16, 12, 8, 6, 2.0)
ok(abs((wx[0, 1] - wx[0, 0]) - 0.5) < 1e-9, "wgrid at density 2 steps half a world px a pixel")

d, t, side = fl.stroke(X, Y, [(-20, 0), (20, 0)], 6.0, 0.0)
on = d < 0
ok(on.any() and on[:, :W // 2].sum() > on[:, W // 2:].sum(), "stroke tapers from its root to its tip")
ok(t[on].min() >= 0 and t[on].max() <= 1 and set(np.unique(np.sign(side[on]))) >= {-1.0, 1.0},
   "stroke returns t along it and a side each way")

m = fl.empty(W, H)
fl.put(m, 5, 5, 2)
fl.put(m, -3, 5, 2)                  # off the map: ignored
fl.put_max(m, 5, 5, 1)
ok(m[5, 5] == 2 and (m >= 0).sum() == 1, "put clips to the map and put_max keeps the brighter shade")
fl.line(m, 2, 20, 30, 20, 1)
ok((m[20, 2:31] == 1).all(), "line joins its two ends")
ring_m = fl.outline(m.copy(), 0)
ok((ring_m >= 0).sum() > (m >= 0).sum() and (ring_m[m >= 0] == m[m >= 0]).all(),
   "outline adds a rim and leaves the drawing as it was")
dst = fl.empty(W, H)
fl.stamp(dst, m, 4, -3)
ok(dst[2, 9] == 2 and (dst >= 0).sum() <= (m >= 0).sum(), "stamp moves a map by its offset, clipped")

n1 = fl.noise(X, Y, 8, 5)
ok(0 <= n1.min() and n1.max() <= 1 and np.array_equal(n1, fl.noise(X, Y, 8, 5)), "noise stays in 0..1 and repeats by seed")
ok(not np.array_equal(n1, fl.noise(X, Y, 8, 6)), "another seed gives another noise")
per = fl.noise(X, Y, 8, 5, period=(32, 32))
ok(np.allclose(per, fl.noise(X + 32, Y + 32, 8, 5, period=(32, 32))), "periodic noise wraps at its period")
ck = fl.checker(X, Y)
ok(ck[0, 0] != ck[0, 1] and ck[0, 0] != ck[1, 0], "checker alternates each pixel")
ok(abs(fl.ground_dist(np.array([10.0]), np.array([0.0]), 10, 4)[0] - 1) < 1e-9, "ground_dist is 1 on the rim")
painted("ground_ring", lambda q: fl.ground_ring(q, W // 2, H // 2, 20, 8, width=3, shades=(1, 2, 3)), (0, 1, 2, 3))

# impact frames: a cell heated toward white, shrunk toward its pivot, and rays round it
PAL = ["#3a1408", "#c83a1a", "#f07c22", "#fff3c4"]
cell = np.zeros((H, W, 4), np.uint8)
cell[16:32, 22:42] = (*fl.hexc(PAL[1]), 255)
hot = fl.heat(cell, PAL, 2)
ok(hot.shape == cell.shape and hot[..., :3][cell[..., 3] > 0].mean() > cell[..., :3][cell[..., 3] > 0].mean(),
   "heat moves a cell toward white")
small = fl.contract(cell, (W // 2, H // 2), 0.6)
ok(0 < (small[..., 3] > 0).sum() < (cell[..., 3] > 0).sum(), "contract shrinks a cell toward its pivot")
order = fl.impact_order(8, 3)
ok(len(order) == 8 and max(order) < 8, "impact_order names a source frame per slot: %s" % order)
BOX = (4, 44, 8, 56)            # y0, y1, x0, x1: the bounds the rays may reach
rays = fl.flash_rays(hot, PAL, 1, BOX, seed=4)
ok((rays[..., 3] > 0).sum() > (hot[..., 3] > 0).sum(), "flash_rays adds streaks round the hot cell")
ok(np.array_equal(rays, fl.flash_rays(hot, PAL, 1, BOX, seed=4)), "flash_rays repeats by seed")
ys, xs = np.nonzero(rays[..., 3] > 0)
ok(ys.min() >= BOX[0] and ys.max() <= BOX[1] and xs.min() >= BOX[2] and xs.max() <= BOX[3], "flash_rays stays inside its box")

# ---- fxkit: dissolve, round shapes, trails ----
full = np.full((H, W), 2, np.int8)
left = [int((fk.fade(full, a) >= 0).sum()) for a in (0, 0.25, 0.5, 0.75, 1)]
ok(left[0] == W * H and left[-1] == 0 and left == sorted(left, reverse=True), "fade removes more as it rises: %s" % left)
half = fk.fade(full, 0.5)
ok(np.array_equal(half[:4, :4], half[4:8, 4:8]), "fade dissolves by a repeating 4x4 pattern, not by noise")
ok(fk.hsh(3, 1) == fk.hsh(3, 1) and 0 <= fk.hsh(3, 1) < 1 and fk.hsh(3, 1) != fk.hsh(4, 1), "hsh is a fixed value per index")
u, v = fk.rot(np.array([1.0]), np.array([0.0]), math.pi / 2)
ok(abs(u[0]) < 1e-9 and abs(v[0] + 1) < 1e-9, "rot turns world px into along and across a heading")

d = fk.lumpy(X, Y, 0, 0, 10, amp=0.2, seed=1)
edge = np.hypot(X, Y)[(d < 1) & (fk.lumpy(X, Y, 0, 0, 10.6, amp=0.2, seed=1) >= 1)]
ok(d[H // 2, W // 2] < 0.2 and (d < 1).sum() > 200, "lumpy is inside at its centre")
ok(np.hypot(X, Y)[d < 1].max() - np.hypot(X, Y)[d >= 1].min() > 1.5, "lumpy has a lobed rim, not a circle")
painted("heat_bands", lambda q: fk.heat_bands(q, d, (3, 2, 1, 0), (0.3, 0.55, 0.8, 1.0)), (0, 1, 2, 3))
b = painted("ball", lambda q: fk.ball(q, X, Y, 0, 0, 9, (0, 1, 2, 3)), (0, 1, 2, 3))
ys, xs = np.nonzero(b == 3)
ok(len(ys) and xs.mean() < W / 2 and ys.mean() < H / 2, "ball puts its highlight toward the top left light")

whole = painted("puff", lambda q: fk.puff(q, X, Y, 0, 0, 10, (0, 1, 2)), (0, 1, 2))
broken = fl.empty(W, H)
fk.puff(broken, X, Y, 0, 0, 10, (0, 1, 2), brk=0.7)
gone = (whole >= 0) & (broken < 0)
ok(0 < gone.sum() < (whole >= 0).sum() and not ((broken >= 0) & (whole < 0)).any(), "a breaking puff only loses pixels")
ok(np.hypot(X, Y)[gone].mean() > np.hypot(X, Y)[broken >= 0].mean(), "a puff breaks up from its edge inward")

U, V = fk.rot(X, Y, 0.0)
painted("trail_puffs", lambda q: fk.trail_puffs(q, X, Y, U, V, 20, 6, 0.4), (0, 1, 2, 3))
s8 = painted("streaks", lambda q: fk.streaks(q, X, Y, 0, 0, 8, 3, 18, 3, (0, 1, 2), seed=2), (0, 1, 2))
ok((s8[np.hypot(X, Y) < 1.2] < 0).all() and (s8[np.hypot(X, Y) > 22] < 0).all(), "streaks run from their inner radius to their outer one")
ring = fk.ring(X, Y, 0, 0, 12, 2)
ok(ring.any() and not ring[H // 2, W // 2] and abs(np.hypot(X, Y)[ring].mean() - 11) < 0.6, "ring is a band inside its radius")

pts = fk.polygon(0, 0, 12, 6, seed=3)
ok(len(pts) == 6 and pts == fk.polygon(0, 0, 12, 6, seed=3), "polygon repeats by seed")
painted("facets", lambda q: fk.facets(q, X, Y, pts, (0, 1, 2, 3)), (0, 1, 2, 3), low=100)
tw = painted("twinkle", lambda q: fk.twinkle(q, 20, 20, 3, 3, 2), (2, 3))
ok(tw[20, 20] == 3 and tw[20, 23] == 2 and tw[21, 21] < 0, "twinkle is a four point star, hot at the centre")
ok(fk.to_px(tw, X, Y, 0.5, 0.5) == (W // 2, H // 2) and fk.at(tw, X, Y, 0.0, 4.5, 0.5) == (W // 2 + 4, H // 2),
   "to_px and at find the pixel of a world point")
k = painted("kite", lambda q: fk.kite(q, X, Y, 0, 0, 0.0, 16, 6, (0, 1, 2, 3)), (0, 1, 2, 3))
ys, xs = np.nonzero(k >= 0)
ok(np.ptp(xs) > 2 * np.ptp(ys), "kite is long along its heading")
lf = painted("leaf", lambda q: fk.leaf(q, X, Y, -10, 0, 0.0, 20, 8, (0, 1, 2, 3)), (0, 1, 2, 3))
thin = fl.empty(W, H)
fk.leaf(thin, X, Y, -10, 0, 0.0, 20, 8, (0, 1, 2, 3), roll=0.3)
ok(0 < (thin >= 0).sum() < (lf >= 0).sum(), "a leaf turning edge on narrows")
ok(fk.rim_if(lf.copy(), 0, False) is not None and (fk.rim_if(lf.copy(), 0, True) >= 0).sum() > (lf >= 0).sum(),
   "rim_if rims only when asked")
ok((fk.rim(lf, 0) >= 0).sum() > (lf >= 0).sum(), "rim adds a 1 px rim")

# ---- claws and drops ----
local = fk.claw_tracks(10, n=3)
tracks = fk.to_world(local, 0.0)
ok(len(tracks) == 3 and len(tracks[0]) == 14 and tracks[0] != tracks[1], "claw_tracks gives n parallel tracks")
painted("claw_marks", lambda q: fk.claw_marks(q, X, Y, tracks, 0.7, 0.4, (0, 1, 2, 3), (4, 5, 6)), range(7))
gone_by = fl.empty(W, H)
tip = fk.claw_marks(gone_by, X, Y, tracks, 2.0, 0.4, (0, 1, 2, 3), (4, 5, 6))
ok(tip is None and set(np.unique(gone_by[gone_by >= 0]).tolist()) <= {4, 5, 6}, "once the claws leave, only the scar is left")
painted("drop", lambda q: fk.drop(q, X, Y, 0, 0, 2.5, (0, 1, 2, 3), tail=(-4, 0)), (0, 1, 2, 3))
painted("claw_drops", lambda q: fk.claw_drops(q, X, Y, tracks, 2, 5, (0, 1, 2, 3)), (0, 1, 2, 3), low=1)
before = fl.empty(W, H)
fk.claw_drops(before, X, Y, tracks, 0, 5, (0, 1, 2, 3))
ok(not (before >= 0).any(), "no drops fly before the claws start")

# ---- hits: a blow in six frames, the cell of a themed hit, and the ground's reaction ----
TONES, SMOKE = (0, 1, 2, 3), (4, 5, 6)
burst = []
for f in range(6):
    burst.append(painted("hit_burst frame %d" % f,
                         lambda q, f=f: fk.hit_burst(q, X, Y, f, TONES, SMOKE, 7, r=12, seed=1, shards=TONES),
                         range(8), low=3))
ok(int((burst[1] >= 0).sum()) > int((burst[0] >= 0).sum()), "hit_burst grows from its core to the flash")
ok(any((q == 3).any() for q in burst[:2]), "hit_burst is hottest at the start")
TH = dict(kind="shard", rim=0, streak=(1, 2, 3), disc=(2, 3), deb=(4, 5, 6, 7), drop=(4, 5, 6, 7), drops=None, mist=(8, 9, 10))
cells = [fk.hit_cell(X, Y, f, True, TH, seed=2) for f in range(6)]
ok(all((c >= 0).any() for c in cells[:5]), "hit_cell draws its six frames")
ok(np.array_equal(cells[1], fk.hit_cell(X, Y, 1, True, TH, seed=2)), "hit_cell repeats by seed")
ok((fk.hit_cell(X, Y, 1, True, TH, seed=2) >= 0).sum() > (fk.hit_cell(X, Y, 1, False, TH, seed=2) >= 0).sum(),
   "a big hit covers more than a small one")

FPS = 24
for weight in fk.GROUND:
    g0 = fl.empty(W, H)
    fk.ground_impact(g0, X, Y, 2, FPS, (0, 1, 2), (3, 4, 5), cy=10, weight=weight, seed=3)
    ok((g0 >= 0).sum() > 0, "ground_impact %s throws dust or debris" % weight)
none = fk.ground_impact(fl.empty(W, H), X, Y, -1, FPS, (0, 1, 2), (3, 4, 5), cy=10)
ok(not (none >= 0).any(), "ground_impact draws nothing before the contact frame")
end = fk.ground_impact(fl.empty(W, H), X, Y, int(1.2 * FPS) + 1, FPS, (0, 1, 2), (3, 4, 5), cy=10, life=1.2)
ok(not (end >= 0).any(), "ground_impact ends empty after its life")
heavy = fk.ground_impact(fl.empty(W, H), X, Y, 3, FPS, (0, 1, 2), (3, 4, 5), cy=10, weight="heavy", seed=3)
light_hit = fk.ground_impact(fl.empty(W, H), X, Y, 3, FPS, (0, 1, 2), (3, 4, 5), cy=10, weight="light", seed=3)
ok((heavy >= 0).sum() > (light_hit >= 0).sum(), "a heavy blow marks the ground more than a light one")
x0, y0, rest0 = fk.debris_at(0, 0.02, 0, 10, 12, 1.0, 0.35, 3)
x1, y1, rest1 = fk.debris_at(0, 5.0, 0, 10, 12, 1.0, 0.35, 3)
ok(not rest0 and rest1 and y0 < y1 and abs(y1 - 10) <= 0.35 * 12 * 0.25 + 1e-9,
   "debris flies up, then rests on the ground plane")

# ---- the mockup caster: a figure with its feet on the ground and light on its body ----
CW, CH = 96, 128
rgb = np.zeros((CH, CW, 3))
alpha = np.zeros((CH, CW))


def over(ys, xs, col, a):
    keep = (ys >= 0) & (ys < CH) & (xs >= 0) & (xs < CW)
    rgb[ys[keep], xs[keep]] = np.broadcast_to(np.asarray(col, float), (*keep.shape, 3))[keep]
    alpha[ys[keep], xs[keep]] = 1.0


pose = caster.pose_at(4, [(0, "rest"), (8, "raise")], [(0, "rest")])
g = caster.draw(over, (CH, CW), (56, 118), 1.0, pose, 4)
ys, xs = np.nonzero(alpha)
ok(len(ys) > 300 and np.ptp(ys) > np.ptp(xs) and ys.max() >= g["feet"][1], "caster draws a standing figure down to its feet")
ok(g["head"][1] < g["neck"][1] < g["hip"][1] < g["feet"][1], "caster returns its key points, head above hip above feet")
L = np.zeros((CH, CW))
caster.body_light(L, g)
ok(L.max() > 0.2 and L[int(g["hip"][1]), int(g["hip"][0])] > L[2, 2], "caster lights its body, not the far corner")
aim = caster.aim_from((56, 118), 1.0, (90, 60))
ok(abs(math.hypot(*aim) - 1) < 1e-6 and aim[0] > 0, "aim_from points from the shoulder at the target")
point = caster.pose_at(8, [(0, "rest"), (8, "point")], [(0, "rest")], aim=aim)
ok(point != pose, "a pointing pose differs from the raise")

print("ok shape checks" if not fails else "\n".join("FAIL " + m for m in fails) + "\n%d shape checks" % len(fails))
sys.exit(1 if fails else 0)
