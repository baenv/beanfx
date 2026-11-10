"""Southern Invasion: the ground shakes and a tall dust wall rises at the left and roars, then a horde of war elephants
(caparison, howdah with a rider and banner, flapping ears, curling trunks, tusks) and barbarian soldiers (feather
headdress, rattan shield, spear) bursts out of it in waves and charges left to right in three depth rows, kicking up
rolling dust, pebbles and glowing cracks, and dissolves into dust before the right side; the dust settles.
General mode, 320x200, 120 frames at 24 fps, one-shot, soft style, glow medium, side view, no caster.

States (frames, 24 fps):
  roar     0-17   tremor, dust wall rises, red eyes in the dust, 3 roar arcs expand
  charge  18-95   5 elephants and 30 soldiers charge across in waves, dust, pebbles, cracks
  settle  96-119  the last stragglers dissolve, dust settles, cracks cool, a haze stays
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent / "kit"))
import pfx  # noqa: E402

NAME = "nam_man_nhap_xam"
W, H, N, FPS = 320, 200, 120, 24
OUT = Path(__file__).parent / "out"

ROAR0, ROAR_N = 0, 18
CHARGE0, CHARGE_N = ROAR0 + ROAR_N, 78
SETTLE0 = CHARGE0 + CHARGE_N

GY = 172.0                                  # ground line
WALL = (40.0, 150.0)                        # foot of the dust wall
FADE_IN = (40.0, 70.0)                      # figures come out of the wall over this x range
FADE_OUT = 290.0                            # figures are gone into dust by this x (their front edge)

# palette indices: 0-4 silhouette dark to light, 5-6 cloth, 7 trim, 8-9 tusk, 10 metal, 11-12 banner, 13-14 wood
PAL = ["#0c0a14", "#1a1626", "#272036", "#382e4a", "#4c3f62",
       "#3a1020", "#5e1c2c", "#b0782c", "#7c7260", "#eadfc4", "#c8c0b0", "#4a0e12", "#8a2420",
       "#1e1410", "#3c2a20"]
PAL_RGB = np.stack([np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0 for c in PAL])
SILS = 5
RIM = "#ff9a52"
RIM_FAR = "#b0603a"
DUST = ["#3a2c28", "#6a5242", "#9a7c5e"]
CRACK = "#140a0c"
HOT = "#ff7a36"
EYE = "#ff4a2a"
OUTLINE = "#06050a"
LIGHT_RAMP = ["#3a0e04", "#c84a14", "#ffa060", "#ffffff"]
ROWS = {"far": (156.0, 0.72, 0), "efar": (160.0, 1.0, 0), "mid": (168.0, 1.0, 1), "elephant": (171.0, 1.25, 1),
        "near": (182.0, 1.08, 2)}

YY, XX = np.mgrid[0:H, 0:W].astype(float)
rng = np.random.default_rng(11)


def hexf(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


DUST_RGB = np.stack([hexf(c) for c in DUST])


def ease_io(s):
    s = np.clip(s, 0, 1)
    return s * s * (3 - 2 * s)


def eout(s):
    s = min(max(s, 0.0), 1.0)
    return 1 - (1 - s) ** 3


def _win(x0, x1, y0, y1):
    xa, xb = max(int(x0), 0), min(int(x1) + 2, W)
    ya, yb = max(int(y0), 0), min(int(y1) + 2, H)
    return slice(ya, max(yb, ya)), slice(xa, max(xb, xa))


def seg_d(X, Y, a, b):
    ex, ey = b[0] - a[0], b[1] - a[1]
    h = np.clip(((X - a[0]) * ex + (Y - a[1]) * ey) / (ex * ex + ey * ey or 1e-9), 0, 1)
    return np.hypot(X - a[0] - ex * h, Y - a[1] - ey * h)


class Frame:
    def __init__(self):
        self.rgb = np.zeros((H, W, 3))
        self.a = np.zeros((H, W))
        self.L = np.zeros((H, W))

    def over(self, ys, xs, rgb, a):
        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W)
        a = np.broadcast_to(np.asarray(a, float), ok.shape)[ok]
        rgb = np.broadcast_to(np.asarray(rgb, float), (*ok.shape, 3))[ok]
        ys, xs = ys[ok], xs[ok]
        a0 = self.a[ys, xs]
        na = a + a0 * (1 - a)
        self.rgb[ys, xs] = (rgb * a[:, None] + self.rgb[ys, xs] * (a0 * (1 - a))[:, None]) / np.maximum(na, 1e-6)[:, None]
        self.a[ys, xs] = na

    def dot(self, x, y, rgb, a=1.0):
        self.over(np.array([int(round(y))]), np.array([int(round(x))]), rgb, a)

    def glow(self, x, y, r, k, flat=1.0):
        if k <= 0 or r <= 0:
            return
        sy, sx = _win(x - r, x + r, y - r * flat, y + r * flat)
        d = np.hypot(XX[sy, sx] - x, (YY[sy, sx] - y) / flat) / r
        self.L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)

    def glow_line(self, p0, p1, r, k):
        if k <= 0:
            return
        sy, sx = _win(min(p0[0], p1[0]) - r, max(p0[0], p1[0]) + r, min(p0[1], p1[1]) - r, max(p0[1], p1[1]) + r)
        d = seg_d(XX[sy, sx], YY[sy, sx], p0, p1) / r
        self.L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)

    def rgba(self):
        return np.dstack([self.rgb, self.a])


def line(fr, p0, p1, col, a0, a1):
    n = int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))) + 1
    t = np.linspace(0, 1, n)
    xs = np.round(p0[0] + (p1[0] - p0[0]) * t).astype(int)
    ys = np.round(p0[1] + (p1[1] - p0[1]) * t).astype(int)
    fr.over(ys, xs, hexf(col), a0 + (a1 - a0) * t)


def puff(fr, x, y, r, a, f, seed, lit=0.06):
    """Translucent dust puff, lighter toward the top left, a lumpy edge that rolls."""
    if a <= 0.01 or r < 0.8:
        return
    x = min(max(x, r * 1.2 + 3), W - r * 1.2 - 3)
    y = max(y, r * 1.2 + 3)
    sy, sx = _win(x - r * 1.2, x + r * 1.2, y - r * 1.2, y + r * 1.2)
    X, Y = XX[sy, sx] - x, YY[sy, sx] - y
    ang = np.arctan2(Y, X)
    rr = r * (1 + 0.14 * np.sin(ang * 5 + seed + f * 0.15))
    d = np.hypot(X, Y * 1.15) / rr
    m = d <= 1
    s = (X + Y) / max(r, 1)
    tone = np.where(s < -0.45, 2, np.where(s > 0.5, 0, 1))
    ys, xs = np.nonzero(m)
    da = a * (1 - 0.5 * d[ys, xs] ** 2)
    fr.over(ys + sy.start, xs + sx.start, DUST_RGB[tone[ys, xs]], da)
    fr.L[ys + sy.start, xs + sx.start] += da * lit           # dust lit warm by the horde


def _tri(X, Y, a, b, c):
    def side(p, q):
        return (X - q[0]) * (p[1] - q[1]) - (p[0] - q[0]) * (Y - q[1])
    d1, d2, d3 = side(a, b), side(b, c), side(c, a)
    return ~(((d1 < 0) | (d2 < 0) | (d3 < 0)) & ((d1 > 0) | (d2 > 0) | (d3 > 0)))


# ---- figures in local units, facing +x, feet at y 0; P.idx holds palette indices ----
class Parts:
    def __init__(self, lx, ly):
        self.lx, self.ly = lx, ly
        self.idx = np.full(lx.shape, -1)

    def put(self, m, t):
        self.idx = np.where(m, t, self.idx)

    def cap(self, a, b, r, t):
        m = seg_d(self.lx, self.ly, a, b) <= r
        self.put(m, t)
        return m

    def ell(self, cx, cy, rx, ry, t):
        m = np.hypot((self.lx - cx) / rx, (self.ly - cy) / ry) <= 1
        self.put(m, t)
        return m

    def chain(self, pts, w0, w1, tones):
        """Capsules along pts, width w0 to w1, tone per segment cycling through tones (skin fold bands)."""
        n = len(pts) - 1
        for k in range(n):
            self.cap(pts[k], pts[k + 1], w0 + (w1 - w0) * k / max(n - 1, 1), tones[k % len(tones)])


def elephant(P, ph, f, seed, size):
    """War elephant about 70 units tall with its howdah; size varies the build a little."""
    lx, ly = P.lx, P.ly
    bob = 0.9 * math.sin(2 * ph)
    # tail first (behind the body): swishes with a dark tuft
    sw = math.sin(f * 0.45 + seed)
    tl = [(-19, -28 + bob), (-22 + sw, -22 + bob), (-23 + 2 * sw, -16 + bob)]
    P.chain(tl, 0.9, 0.7, [1])
    P.ell(tl[-1][0], tl[-1][1] + 1.5, 1.2, 2.0, 0)
    # far legs then near legs; 4-phase walk, knees forward on the front legs, hocks back on the hind
    legs = [(-12, 0.0, 0, False), (10, math.pi * 0.5, 0, True), (-10, math.pi, 2, False), (12, math.pi * 1.5, 2, True)]
    for hx, off, base, front in legs:
        c = math.cos(ph + off)
        lift = max(0.0, math.sin(ph + off)) * 4.0
        foot = (hx + 5.5 * c, -lift)
        bend = (2.2 if front else -2.2) * (0.4 + lift / 4.0)
        knee = ((hx + foot[0]) / 2 + bend, -9 - lift * 0.4 + bob * 0.5)
        hip = (hx, -18 + bob)
        P.cap(hip, knee, 3.9 * size, base)
        P.cap(knee, (foot[0], foot[1] - 2), 3.4 * size, base)
        pad = P.ell(foot[0] + 0.4, foot[1] - 1.4, 4.0 * size, 1.9, base)
        leg = seg_d(lx, ly, knee, (foot[0], foot[1] - 2)) <= 3.4 * size
        P.put(leg & ((np.floor(ly + 0.5) % 3) == 0) & (ly < knee[1] + 1), max(base - 1, 0))      # skin folds
        P.put(pad & (ly > foot[1] - 1.0) & (((np.floor(lx) % 2) == 0)), 9 if base else 8)      # toenails
    # body, hump and belly shade
    P.ell(0, -26 + bob, 19 * size, 12.5, 2)
    P.ell(-2, -33 + bob, 13 * size, 6, 3)
    P.put(np.hypot(lx / (16 * size), (ly - (-19 + bob)) / 4.5) <= 1, 1)
    # caparison: cloth over the back, scalloped hem, gold trim, a medallion
    hem = -21 + bob + 1.3 * np.abs(np.sin(lx * 0.55 + 0.6))
    cloth = (np.abs(lx + 2) <= 10 * size) & (ly >= -36 + bob) & (ly <= hem)
    cloth &= np.hypot(lx / (19.5 * size), (ly - (-26 + bob)) / 13) <= 1
    P.put(cloth, 6)
    P.put(cloth & (lx + ly * 0.4 > 3 + bob * 0.4), 5)
    P.put(cloth & ((ly > hem - 1.1) | (ly < -35 + bob)), 7)
    P.put(cloth & (np.abs(lx + 2) + np.abs(ly - (-29 + bob)) <= 2.4), 7)
    # head, forehead dome
    P.ell(18, -29 + bob, 8.5, 9.5, 2)
    P.ell(19, -35 + bob, 6, 4.5, 3)
    # trunk: curls forward and swings, ring folds
    curl = 0.1 + 0.16 * math.sin(f * 0.22 + seed)
    swing = 0.25 * math.sin(ph * 0.5 + seed)
    pts = [(24, -27 + bob)]
    a = math.radians(80) + swing
    for k in range(9):
        a -= curl * (k / 4.0) ** 1.4
        pts.append((pts[-1][0] + math.cos(a) * 2.6, pts[-1][1] + math.sin(a) * 2.6))
    P.chain(pts, 3.1, 1.1, [2, 2, 1])
    P.ell(pts[-1][0], pts[-1][1], 1.3, 1.3, 3)
    # tusks: far one dim, near one pale with a highlight on top
    for dx, t0, t1 in ((-1.6, 8, 8), (0.0, 8, 9)):
        tk = [(22 + dx, -22 + bob), (27 + dx, -20 + bob), (31 + dx, -21.5 + bob), (33.5 + dx, -25 + bob)]
        for k in range(3):
            m = P.cap(tk[k], tk[k + 1], 1.2 - 0.25 * k, t0)
            P.put(m & (ly < (tk[k][1] + tk[k + 1][1]) / 2 - 0.2), t1)
    # ear: big, flaps; dark inside, lit rim
    flap = math.sin(f * 0.55 + seed * 2)
    ex, ey = 12 + flap * 0.6, -29 + bob
    erx = (6.0 + 1.8 * flap) * size
    u, v = lx - ex, ly - ey
    ear = np.hypot(u / erx, v / (9.5 + 2.5 * (v > 0))) <= 1
    ear &= ~((u > erx * 0.45) & (v < -2))                       # the top joins the head, no lobe there
    P.put(ear, 2)
    fold = np.abs(np.hypot((u - 2.5) / (erx * 0.75), (v + 1) / 7.5) - 1) < 0.13
    P.put(ear & fold, 1)
    P.put(ear & (u > erx * 0.55), 1)
    P.put(ear & (v > 8.5), 1)
    # howdah: wooden platform, railing and gold top bar
    hb = -38 + bob
    P.put((lx >= -10) & (lx <= 6) & (ly >= hb - 2) & (ly <= hb + 0.5), 13)
    for px in (-10, -4.5, 1, 6):
        P.cap((px, hb - 2), (px, hb - 8), 0.55, 14)
    P.cap((-10.5, hb - 8), (6.5, hb - 8), 0.6, 7)
    P.cap((-10, hb - 5), (6, hb - 5), 0.4, 14)
    # rider: torso, head, feather, spear held high
    rb = hb - 2
    P.cap((-2, rb), (-1.5, rb - 9), 2.0, 2)
    P.ell(-1, rb - 11.5, 2.2, 2.3, 2)
    for k in range(3):
        aa = math.radians(-110 - 25 * k) + 0.2 * math.sin(f * 0.7 + seed + k)
        P.cap((-1.5, rb - 13), (-1.5 + math.cos(aa) * (5 - k), rb - 13 + math.sin(aa) * (5 - k)), 0.6, 3)
    jab = 1.5 * math.sin(f * 0.35 + seed)
    P.cap((-0.5, rb - 8), (3.5, rb - 12 + jab * 0.3), 0.8, 2)
    P.cap((1.5, rb + 3), (5.5, rb - 22 + jab), 0.5, 14)
    P.cap((5.5, rb - 22 + jab), (6.2, rb - 26 + jab), 0.7, 10)
    # banner at the back of the howdah
    P.cap((-9.5, hb - 2), (-9.5, hb - 26), 0.55, 14)
    fl = math.sin(f * 0.8 + seed)
    tip = (-23 + fl * 1.6, hb - 21 + fl)
    P.put(_tri(lx, ly, (-9.5, hb - 26), (-9.5, hb - 17), tip), 12)
    P.put(_tri(lx, ly, (-9.5, hb - 21.5), (-9.5, hb - 17), tip), 11)
    return dict(eye=(20.5, -31 + bob), tusk=(33.5, -25 + bob), head=(18, -29 + bob), spear=(6.2, rb - 26 + jab))


def soldier(P, ph, f, seed, raise_spear):
    bob = -1.2 * abs(math.sin(ph))
    hip = (0, -11 + bob)
    for off, t in ((math.pi, 1), (0.0, 2)):
        s = math.sin(ph + off)
        foot = (6 * s, -max(0.0, math.cos(ph + off)) * 4)
        knee = ((hip[0] + foot[0]) / 2 + 2.5, (hip[1] + foot[1]) / 2 - 1)
        P.cap(hip, knee, 1.5, t)
        P.cap(knee, foot, 1.3, t)
    neck = (2.0, -19 + bob)
    P.cap(hip, neck, 2.3, 2)
    P.put(seg_d(P.lx, P.ly, (0, -12.5 + bob), (2.6, -12.5 + bob)) <= 0.9, 6)    # loincloth band
    P.ell(3.0, -22 + bob, 2.6, 2.7, 2)
    for k in range(3):
        a = math.radians(-115 - 22 * k) + 0.15 * math.sin(f * 0.7 + seed + k)
        ln = 7 - k
        P.cap((1.5, -24 + bob), (1.5 + math.cos(a) * ln, -24 + bob + math.sin(a) * ln), 0.7, 3 if k != 1 else 12)
    if raise_spear:
        P.cap((2.5, -18 + bob), (4.5, -25 + bob), 1.0, 2)
        P.cap((4.5, -8 + bob), (6.0, -33 + bob), 0.55, 14)
        P.cap((6.0, -33 + bob), (6.4, -37 + bob), 0.7, 10)
        tip = (6.4, -37 + bob)
    else:
        P.cap((1.5, -18 + bob), (6, -17 + bob), 1.1, 2)
        P.cap((-8, -9 + bob), (13, -22 + bob), 0.55, 14)
        P.cap((13, -22 + bob), (17, -24.5 + bob), 0.7, 10)
        tip = (17, -24.5 + bob)
    sh = np.hypot(P.lx - 5.5, P.ly - (-14 + bob))
    P.put(sh <= 4.6, 14)
    P.put((np.abs(sh - 2.6) <= 0.5) | (sh <= 0.9), 7)
    return dict(eye=(4.5, -22.5 + bob), tusk=None, head=(3, -22 + bob), spear=tip)


def figure(fr, d, x, y, s, row, ph, f, alpha):
    """Draw one figure with its feet at (x, y): a 1 px dark outline where it covers what is already drawn, the
    palette fill, a dark step on the bottom-right edge and a warm rim on the top-left."""
    big = d["kind"] == "e"
    sy, sx = _win(x - 30 * s, x + 38 * s, y - 74 * s, y + 3)
    lx = (XX[sy, sx] - x) / s
    ly = (YY[sy, sx] - y) / s
    P = Parts(lx, ly)
    pts = elephant(P, ph, f, d["seed"], d["size"]) if big else soldier(P, ph, f, d["seed"], d["raise"])
    m = P.idx >= 0
    if not m.any():
        return None
    dil = m.copy()
    dil[1:, :] |= m[:-1, :]
    dil[:-1, :] |= m[1:, :]
    dil[:, 1:] |= m[:, :-1]
    dil[:, :-1] |= m[:, 1:]
    ring = dil & ~m & (fr.a[sy, sx] > 0.35)
    ry, rx = np.nonzero(ring)
    fr.over(ry + sy.start, rx + sx.start, hexf(OUTLINE), 0.85 * alpha)

    idx = np.where(m, P.idx, 0)
    sil = idx < SILS
    ul = np.zeros_like(m)
    ul[1:, 1:] = m[:-1, :-1]
    up = np.zeros_like(m)
    up[1:, :] = m[:-1, :]
    dr = np.zeros_like(m)
    dr[:-1, :-1] = m[1:, 1:]
    rim = m & ~up & ~ul
    idx = np.where(m & ~dr & sil, np.maximum(idx - 1, 0), idx)
    rgb = PAL_RGB[idx]
    if row == 0:
        rgb = rgb * 0.62 + PAL_RGB[1] * 0.38
    rk = (0.35, 0.62, 0.8)[row]
    rgb = np.where(rim[..., None], hexf(RIM if row else RIM_FAR) * rk + rgb * (1 - rk), rgb)
    ys, xs = np.nonzero(m)
    fr.over(ys + sy.start, xs + sx.start, rgb[ys, xs], alpha)
    ry, rx = np.nonzero(rim)
    fr.L[ry + sy.start, rx + sx.start] += 0.1 * alpha * rk

    def w(p):
        return (x + p[0] * s, y + p[1] * s)
    eye = w(pts["eye"])
    fr.dot(*eye, hexf(EYE), alpha)
    fr.glow(*eye, 3 * s + 1, 0.5 * alpha * rk)
    fr.glow(*eye, 8 * s, 0.15 * alpha * rk)
    fr.glow(*w(pts["spear"]), 3 * s + 1, 0.25 * alpha * rk)
    if pts["tusk"]:
        fr.glow(*w(pts["tusk"]), 4 * s, 0.25 * alpha * rk)
    fr.glow(*w(pts["head"]), 26 * s if big else 10 * s, 0.07 * alpha * rk)
    return w(pts["head"])


# ---- the horde ----
FIGS = []
for t0, v, size, row in ((CHARGE0, 3.9, 1.0, "elephant"), (CHARGE0 + 8, 4.4, 0.9, "efar"),
                         (CHARGE0 + 22, 3.7, 1.1, "elephant"), (CHARGE0 + 30, 4.6, 0.92, "efar"),
                         (CHARGE0 + 42, 4.2, 1.04, "elephant")):
    FIGS.append(dict(kind="e", row=row, t0=t0, v=v, x0=16.0, stride=26.0, size=size,
                     seed=rng.uniform(0, 6), raise_=False))
for k in range(30):
    row = ["far", "near", "mid", "far", "near"][k % 5]
    wave = k // 10
    FIGS.append(dict(kind="s", row=row, t0=CHARGE0 + 2 + wave * 17 + (k % 10) * 1.6 + rng.uniform(0, 1.5),
                     v=rng.uniform(5.0, 6.6), x0=34.0, stride=9.0, size=1.0, seed=rng.uniform(0, 6),
                     raise_=rng.random() < 0.4))
for d in FIGS:
    d["raise"] = d.pop("raise_")
FIGS.sort(key=lambda d: (ROWS[d["row"]][2], ROWS[d["row"]][0]))


def fig_pos(d, f):
    t = f - d["t0"]
    if t < 0:
        return None
    gy, s, depth = ROWS[d["row"]]
    x = d["x0"] + d["v"] * t
    front = x + (36 if d["kind"] == "e" else 18) * s
    a = ease_io((x - FADE_IN[0]) / (FADE_IN[1] - FADE_IN[0])) * (1 - ease_io((front - FADE_OUT + 30) / 30.0))
    if a <= 0.01:
        return None if front > FADE_OUT - 30 else (x, gy, s, depth, 0.0)
    return x, gy, s, depth, a


DUST_PUFFS = []
for d in FIGS:
    big = d["kind"] == "e"
    for t in range(0, 90, 2 if big else 3):
        f0 = d["t0"] + t
        st = fig_pos(d, f0)
        if st is None or st[4] < 0.05:
            continue
        x, gy, s, depth, a = st
        b = 2.0 if big else 1.0
        DUST_PUFFS.append(dict(f0=f0, x=x - 8 * s * b + rng.uniform(-3, 3), y=gy - 2 * s - rng.uniform(0, 12) * b,
                               r1=(7 + 6 * b) * s, life=rng.uniform(26, 44), a=0.28 * min(1, a + 0.3),
                               vx=rng.uniform(-0.7, -0.15), vy=-rng.uniform(0.7, 1.8) * (1.3 if big else 1.0),
                               seed=rng.uniform(0, 6)))
for d in FIGS:                                      # each figure dissolves into a puff burst at the right
    for t in range(0, 120):
        st = fig_pos(d, d["t0"] + t)
        if st is not None and st[4] < 0.6 and st[0] > 170:
            x, gy, s, depth, a = st
            for k in range(3 if d["kind"] == "s" else 8):
                DUST_PUFFS.append(dict(f0=d["t0"] + t + k * 0.7, x=x + rng.uniform(-6, 16) * s,
                                       y=gy - rng.uniform(4, 50 if d["kind"] == "e" else 16) * s,
                                       r1=rng.uniform(5, 10) * s, life=rng.uniform(16, 26), a=0.3,
                                       vx=rng.uniform(0.2, 0.8), vy=rng.uniform(-0.6, -0.15),
                                       seed=rng.uniform(0, 6)))
            break
DUST_PUFFS.sort(key=lambda p: -p["vy"])
# the dust wall: a column of billows from the ground to y about 40
WALL_PUFFS = []
for k in range(40):
    h = rng.uniform(0, 1) ** 0.8
    WALL_PUFFS.append(dict(x=WALL[0] + rng.uniform(-12, 12) + 6 * h, y=GY - 6 - h * 118, r=rng.uniform(10, 15) - 3 * h,
                           seed=rng.uniform(0, 6), ph=rng.uniform(0, 6), h=h))
WALL_PUFFS.sort(key=lambda p: -p["y"])
WALL_EYES = [(WALL[0] + rng.uniform(-10, 14), GY - rng.uniform(14, 70), rng.uniform(0, 10)) for _ in range(9)]
CRACKS = []
for cx in (82, 112, 140, 168, 196, 222, 248, 270):
    pts = [(cx + rng.uniform(-3, 3), GY + 1)]
    for k in range(5):
        px, py = pts[-1]
        pts.append((px + rng.choice([-1, 1]) * rng.uniform(3, 6), min(py + rng.uniform(0.5, 2.0), GY + 10)))
    CRACKS.append(dict(x=cx, pts=pts, t0=None))
for c in CRACKS:                                    # a crack opens when the first elephant's front foot passes
    for f in range(N):
        if any(d["kind"] == "e" and (st := fig_pos(d, f)) is not None and st[0] + 12 >= c["x"] for d in FIGS):
            c["t0"] = f
            break
PEBBLES = []
for d in FIGS:
    for t in range(0, 80, 3 if d["kind"] == "e" else 5):
        st = fig_pos(d, d["t0"] + t)
        if st is None or st[4] < 0.2:
            continue
        x, gy, s, depth, a = st
        for _ in range(2):
            PEBBLES.append(dict(f0=d["t0"] + t, x=x + rng.uniform(-8, 10) * s, y=gy, vx=rng.uniform(-1.5, 1.0),
                                vy=-rng.uniform(1.8, 3.4), gy=gy, big=rng.random() < 0.4))


def shake(f):
    env = (1 - ease_io((f - 12) / 8.0)) * ease_io(f / 2.0) + 0.4 * math.exp(-((f - 26) / 8.0) ** 2)
    return int(round(1.6 * env * math.sin(f * 2.3)))


def draw(f):
    fr = Frame()
    settle = ease_io((f - SETTLE0) / 20.0)

    for c in CRACKS:                               # cracks first: everything stands on them
        if c["t0"] is None or f < c["t0"]:
            continue
        age = f - c["t0"]
        opn = eout(age / 4.0)
        n = max(2, int(len(c["pts"]) * opn))
        hot = math.exp(-age / 18.0)
        for p0, p1 in zip(c["pts"][:n - 1], c["pts"][1:n]):
            line(fr, p0, p1, CRACK, 0.9 - 0.4 * settle, 0.9 - 0.4 * settle)
            line(fr, (p0[0], p0[1] - 1), (p1[0], p1[1] - 1), HOT, 0.8 * hot, 0.6 * hot)
            fr.glow_line(p0, p1, 3, 0.35 * hot + 0.03)
            fr.glow_line(p0, p1, 8, 0.12 * hot)

    rise = 0.2 + 0.8 * ease_io(f / 14.0)
    wall = (0.25 + 0.75 * ease_io(f / 8.0)) * (1 - 0.7 * settle)
    for p in WALL_PUFFS:                           # the wall grows upward over the roar
        if p["h"] > rise + 0.05:
            continue
        r = p["r"] * (0.6 + 0.4 * ease_io(f / 12.0)) * (1 + 0.07 * math.sin(f * 0.2 + p["ph"]))
        puff(fr, p["x"] + 2 * math.sin(f * 0.1 + p["ph"]), p["y"] - 0.2 * max(0, f - SETTLE0),
             r, (0.5 - 0.15 * p["h"]) * wall, f, p["seed"], lit=0.05)
    for ex, ey, ph in WALL_EYES:                   # eyes in the dust before the charge
        k = ease_io((f - 3 - ph) / 3.0) * (1 - ease_io((f - CHARGE0 - 6) / 8.0))
        if k > 0.02:
            for dx in (0, 3):
                fr.dot(ex + dx, ey, hexf(EYE), k)
            fr.glow(ex + 1.5, ey, 4, 0.45 * k)
    fr.glow(WALL[0] + 6, GY - 55, 70, 0.1 * wall, flat=1.2)

    for k in range(3):                             # the roar: arcs opening to the right
        age = f - (3 + 5 * k)
        if 0 <= age < 13:
            r = 12 + age * 7
            th = np.linspace(-0.85, 0.85, int(r * 2) + 4)
            cx, cy = WALL[0] + 10, GY - 50
            xs = np.round(cx + r * np.cos(th)).astype(int)
            ys = np.round(cy + r * np.sin(th) * 0.8).astype(int)
            a = (1 - age / 13) * 0.8
            fr.over(ys, xs, hexf("#ffd8a8"), a * np.cos(th) ** 2)
            for t in th[::4]:
                fr.glow(cx + r * math.cos(t), cy + r * math.sin(t) * 0.8, 4, 0.12 * a)

    for p in DUST_PUFFS:
        age = f - p["f0"]
        if age < 0 or age > p["life"]:
            continue
        k = age / p["life"]
        r = p["r1"] * (0.35 + 0.65 * eout(k * 1.6))
        puff(fr, p["x"] + p["vx"] * age, p["y"] + p["vy"] * age, r,
             p["a"] * (1 - k) ** 1.3 * min(1, age / 2 + 0.3), f, p["seed"])

    front = []
    for d in FIGS:
        st = fig_pos(d, f)
        if st is None or st[4] <= 0.01:
            continue
        x, gy, s, depth, a = st
        ph = (x - d["x0"]) / (d["stride"] * s) * 2 * math.pi + d["seed"]
        if figure(fr, d, x, gy, s, depth, ph, f, a):
            front.append(x)

    for p in PEBBLES:
        t = f - p["f0"]
        if t < 0:
            continue
        x, y = p["x"] + p["vx"] * t, p["y"] + p["vy"] * t + 0.35 * t * t
        if y > p["gy"] + 1 or t > 14:
            continue
        fr.dot(x, y, PAL_RGB[3], 1.0)
        fr.dot(x, y - 1, hexf(RIM), 0.7)
        if p["big"]:
            fr.dot(x + 1, y, PAL_RGB[2], 1.0)

    haze = ease_io((f - 30) / 24.0)                # the haze the charge leaves, rising as it settles
    if haze > 0:
        for k in range(11):
            hx = 66 + k * 21 + 4 * math.sin(k * 1.7 + f * 0.05)
            hy = GY - 6 - 0.15 * max(0, f - SETTLE0) - 10 * (k % 2)
            puff(fr, hx, hy, 13 + 2 * math.sin(k), 0.13 * haze, f, k)

    mid = float(np.clip(np.mean(front), 115, 205)) if front else 170.0
    charge = ease_io((f - CHARGE0) / 6.0) * (1 - 0.55 * settle)
    fr.glow(mid + 10, GY - 40, 125, 0.15 * charge, flat=0.7)
    fr.glow(165, GY - 40, 155, 0.07 + 0.05 * charge, flat=0.48)

    dy = shake(f)
    if dy:
        fr.rgb = np.roll(fr.rgb, dy, 0)
        fr.a = np.roll(fr.a, dy, 0)
        fr.L = np.roll(fr.L, dy, 0)
    return fr


def main():
    OUT.mkdir(exist_ok=True)
    cols, lights, comps, ok = [], [], [], True
    covers, means = [], []
    for f in range(N):
        fr = draw(f)
        col = (np.clip(fr.rgba(), 0, 1) * 255).round().astype(np.uint8)
        Lc = np.clip(fr.L, 0, 1)
        light = pfx.tint(np.repeat(Lc[..., None], 3, -1), LIGHT_RAMP)
        cols.append(col)
        lights.append(light)
        comps.append(pfx.composite(col, light))
        a = col[..., 3] > 0
        if not a.any():
            print(f"frame {f}: empty colour")
            ok = False
            continue
        edge = np.zeros_like(a)
        edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
        if (a & edge).any() or ((Lc > 0.02) & edge).any():
            print(f"frame {f}: touches the cell edge")
            ok = False
        ys, xs = np.nonzero(a)
        box = Lc[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        covers.append((box > 0.03).mean())
        means.append(box[box > 0.03].mean() if (box > 0.03).any() else 0)
    cv, mn = np.median(covers), np.median(means)
    print(f"light cover {cv:.0%}  mean {mn:.3f}  (medium: 50-80%, 0.08-0.12)")
    if not (0.5 <= cv <= 0.8 and 0.08 <= mn <= 0.12):
        print("light outside the medium row")
        ok = False

    ncol = 12

    def grid(frames, path, idx=None, n=ncol, scale=1):
        idx = list(range(len(frames))) if idx is None else idx
        rows = math.ceil(len(idx) / n)
        img = np.zeros((rows * H, n * W, 4), np.uint8)
        for k, i in enumerate(idx):
            r, cc = divmod(k, n)
            img[r * H:(r + 1) * H, cc * W:(cc + 1) * W] = frames[i]
        im = Image.fromarray(img, "RGBA")
        if scale != 1:
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        im.save(path)

    grid(comps, OUT / f"{NAME}.png")
    grid(cols, OUT / f"{NAME}_color.png")
    grid([pfx.composite(np.zeros((H, W, 4), np.uint8), l) for l in lights], OUT / f"{NAME}_light.png")
    pfx.strip(comps, OUT / f"{NAME}_strip_1x.png")
    pick = [6, 14, 22, 32, 42, 52, 62, 72, 82, 94, 106, 119]
    for bg, tag in (("#101018", "dark"), ("#5a6070", "mid")):
        flat = [pfx.composite(cols[i], lights[i], bg) for i in range(N)]
        grid(flat, OUT / f"{NAME}_contact4x_{tag}.png", pick, n=4, scale=4)
    for i in (10, 40, 62, 84, 119):
        Image.fromarray(pfx.composite(cols[i], lights[i], "#101018"), "RGBA").resize(
            (W * 4, H * 4), Image.NEAREST).save(OUT / f"{NAME}_f{i:03d}_x4.png")
    pfx.gif(comps, OUT / f"{NAME}.gif", FPS, scale=2)
    meta = dict(name=NAME, w=W, h=H, frames=N, fps=FPS, cols=ncol, loop=False, pivot=[WALL[0], GY], glow="medium",
                light_gain=1.0, states=dict(roar=[ROAR0, CHARGE0 - 1], charge=[CHARGE0, SETTLE0 - 1],
                                            settle=[SETTLE0, N - 1]),
                sheets=dict(composite=f"{NAME}.png", color=f"{NAME}_color.png", light=f"{NAME}_light.png"))
    (OUT / f"{NAME}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
