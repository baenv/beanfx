"""Fire Attack: a volley of about 120 fire arrows glints high at the upper left and rains down on an army camp (tents,
a palisade of stakes, a watch tower, banners, crates). Each arrow that sticks lights a small flame; the burn spreads
over cloth and wood (cloth chars and opens holes, edges glow), flames climb the tents and stakes, banners burn, the
fires merge into a blazing camp under a rolling smoke column, then sink to charred frames, glowing stakes and smoke.
No explosion. General mode, 320x200, 108 frames at 24 fps, one-shot, side view, soft style, glow medium, no caster.

States (frames, 24 fps):
  signal    0-11   the first fire arrows come in from afar as glints high at the upper left, the sky glows
  rain      0-58   about 120 fire arrows, each on one path from a far glint into the camp, speeding up
                   (launch 0-46, flight 11-13 frames, about 30 px a frame at the end)
  ignite   20-69   each hit lights a flame; the burn spreads from the hit points, climbing faster than it falls
  blaze    70-91   the whole camp burns with tall licking flames, embers and a smoke column
  burndown 92-107  flames sink, charred tent frames and glowing stakes remain under smoke
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent / "kit"))
import pfx  # noqa: E402

NAME = "hoa_cong"
W, H, N, FPS = 320, 200, 108, 24
OUT = Path(__file__).parent / "out"

SIGNAL0, SIGNAL_N = 0, 12
RAIN0 = SIGNAL0 + SIGNAL_N
LAUNCH_LAST = RAIN0 + 34
IGNITE0 = 20
BLAZE0 = 70
BURN0 = 92

GROUND_Y = 172.0
TGT = (222.0, GROUND_Y)              # pivot: the middle of the camp
CAMP = (138.0, 302.0)
APEX_Y = 28.0
SLANT = math.radians(58)
NA = 120
ALEN = 14.0

FIRE = ["#7a1c12", "#c83a1a", "#f07c22", "#ffc852", "#fff3c4"]   # dark flame edge to pale core
WOOD = ["#3a2418", "#7a5030", "#c09058"]
SMOKE = ["#3e3438", "#625656", "#8a7c72"]
CLOTH = ["#3a2a1c", "#7a5e3c", "#a8875a", "#d8bb84"]
TIMBER = ["#2a1a10", "#5a3c22", "#8a6438", "#b89060"]
FLAG = ["#4a0c0c", "#8a1a16", "#c83224", "#e86a40"]
CHAR = ["#1e120c", "#3a2416"]
LIGHT_RAMP = ["#5a1008", "#e05018", "#ffc060", "#ffffff"]


def hexf(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


PF = np.stack([hexf(c) for c in FIRE])
PW = np.stack([hexf(c) for c in WOOD])
PS = np.stack([hexf(c) for c in SMOKE])
PC = np.stack([hexf(c) for c in CLOTH])
PT = np.stack([hexf(c) for c in TIMBER])
PG = np.stack([hexf(c) for c in FLAG])
PCH = np.stack([hexf(c) for c in CHAR])
WHITE = np.ones(3)
YY, XX = np.mgrid[0:H, 0:W].astype(float)
rng = np.random.default_rng(7)
_GRID = rng.random((64, 64))


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


def vnoise(x, y):
    """Smooth value noise in 0..1, wrapping every 64 units."""
    xi, yi = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - xi, y - yi
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    g = _GRID
    a, b = g[yi % 64, xi % 64], g[yi % 64, (xi + 1) % 64]
    c, d = g[(yi + 1) % 64, xi % 64], g[(yi + 1) % 64, (xi + 1) % 64]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


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

    def glow_ring(self, x, y, R, r, k, flat=1.0):
        if k <= 0:
            return
        sy, sx = _win(x - R - r, x + R + r, y - (R + r) * flat, y + (R + r) * flat)
        d = np.abs(np.hypot(XX[sy, sx] - x, (YY[sy, sx] - y) / flat) - R) / r
        self.L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)

    def rgba(self):
        return np.dstack([self.rgb, self.a])


def line(fr, p0, p1, c0, c1, a0, a1):
    n = int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))) + 1
    t = np.linspace(0, 1, n)
    xs = np.round(p0[0] + (p1[0] - p0[0]) * t).astype(int)
    ys = np.round(p0[1] + (p1[1] - p0[1]) * t).astype(int)
    fr.over(ys, xs, c0[None] * (1 - t[:, None]) + c1[None] * t[:, None], a0 + (a1 - a0) * t)


def heat_tones(h):
    return np.select([h > 0.78, h > 0.6, h > 0.42, h > 0.26], [4, 3, 2, 1], 0)


def fire(fr, cx, by, hgt, hw, f, seed, sway=4.0, swirl=0.0, a=1.0, cool=0.0):
    """A flame body from a heat field: hottest low in the middle toward the top left, ragged by rising noise."""
    if hgt < 1 or hw < 0.5:
        return
    sy, sx = _win(cx - hw * 1.7 - sway, cx + hw * 1.7 + sway, by - hgt * 1.3, by + 1)
    X, Y = XX[sy, sx], YY[sy, sx]
    s = (by - Y) / hgt
    sc = np.clip(s, 0, 1)
    axis = cx + sway * np.sin(Y * 0.07 - f * 0.35 + seed) * sc
    w = hw * (1 - 0.82 * sc ** 1.2) + 0.6
    u = (X - axis) / w
    n = 0.65 * vnoise(X * 0.11 + seed * 7, Y * 0.11 + f * 0.62) + 0.35 * vnoise(X * 0.27 + seed, Y * 0.27 + f * 1.1)
    heat = (1 - np.abs(u)) * (1.05 - 0.6 * sc) + (n - 0.5) * 0.95 - np.maximum(s - 1, 0) * 2.2 - cool
    heat = heat + 0.1 * np.clip(-u, -1, 1) * (1 - sc)
    if swirl:
        heat = heat + swirl * 0.2 * np.sin(u * 2.6 + Y * 0.17 - f * 0.75)
    m = (heat > 0.12) & (Y <= by)
    ys, xs = np.nonzero(m)
    if len(ys):
        fr.over(ys + sy.start, xs + sx.start, PF[heat_tones(heat[ys, xs])], a)
    return m.sum()


# ---- the camp: material, tone and a static noise per pixel (0 none, 1 cloth, 2 timber, 3 crate) ----
MAT = np.zeros((H, W), np.int8)
TONE = np.zeros((H, W), np.int8)
POLE = np.zeros((H, W), bool)
HN = rng.random((H, W))
TENTS = [(180.0, 34.0, 30.0), (220.0, 50.0, 44.0), (260.0, 36.0, 32.0), (289.0, 22.0, 22.0)]
TOWER = (148.0, 104.0)               # middle x and roof top y of the watch tower
STAKE_BASE = 160.0


def _paint(m, mat, tone):
    MAT[m] = mat
    TONE[m] = tone[m] if isinstance(tone, np.ndarray) else tone
    POLE[m] = False


def _build_camp():
    X, Y = XX, YY
    srng = np.random.default_rng(3)
    for x0 in np.arange(CAMP[0], CAMP[1] - 2, 4.0):               # the palisade behind
        h = 13 + srng.uniform(0, 5)
        top = STAKE_BASE - h
        body = (X >= x0) & (X < x0 + 3) & (Y >= top) & (Y <= STAKE_BASE)
        tip = (Y >= top - 4) & (Y < top) & (np.abs(X - x0 - 1) <= (Y - top + 4) * 0.4)
        m = body | tip
        _paint(m, 2, np.where(X == x0, 3, np.where(X == x0 + 2, 1, 2)).astype(np.int8))
    for ry in (STAKE_BASE - 4, STAKE_BASE - 10):
        m = (np.abs(Y - ry) < 0.6) & (X >= CAMP[0]) & (X <= CAMP[1] - 2)
        _paint(m, 2, 1)
    tx, ty = TOWER                                                # the watch tower
    for lx in (tx - 9, tx + 8):
        m = (X >= lx) & (X < lx + 2) & (Y >= ty + 14) & (Y <= GROUND_Y)
        _paint(m, 2, np.where(X == lx, 2, 1).astype(np.int8))
    for k in range(4):                                            # cross braces
        y0 = ty + 22 + k * 11
        t = np.clip((X - (tx - 9)) / 18, 0, 1)
        yy = y0 + (t * 9 if k % 2 else (1 - t) * 9)
        m = (np.abs(Y - yy) < 0.7) & (X >= tx - 9) & (X <= tx + 9)
        _paint(m, 2, 1)
    m = (X >= tx - 13) & (X <= tx + 13) & (Y >= ty + 12) & (Y <= ty + 15)
    _paint(m, 2, np.where(Y == ty + 12, 3, 2).astype(np.int8))
    m = (X >= tx - 12) & (X <= tx + 12) & (Y >= ty + 7) & (Y < ty + 12) & ((np.abs(X - tx) % 6) < 1)
    _paint(m, 2, 2)
    m = (Y >= ty) & (Y <= ty + 7) & (np.abs(X - tx) <= (Y - ty) * 2.0 + 1)
    _paint(m, 1, np.where(X < tx, 3, 1).astype(np.int8))
    for cx, w, h in TENTS:                                        # tents in front
        u = (X - cx) / (w / 2)
        roof = GROUND_Y - h * np.clip(1 - np.abs(u), 0, 1) ** 1.15
        m = (np.abs(u) <= 1) & (Y >= roof) & (Y <= GROUND_Y)
        tone = np.where(u < 0, 2, 1).astype(np.int8)
        tone[(Y < roof + 1.2) & (u < 0)] = 3
        tone[((np.abs(X - cx) % 7) < 1) & (Y > roof + 2)] = 0
        tone[(np.abs(u) < 0.2) & (Y > GROUND_Y - h * 0.45) & (np.abs(X - cx) < (Y - (GROUND_Y - h * 0.45)) * 0.35)] = 0
        tone[Y > GROUND_Y - 1.5] = 0
        _paint(m, 1, tone)
        pm = (np.abs(X - cx) < 0.6) & (Y >= GROUND_Y - h - 3) & (Y <= GROUND_Y - h + 1)
        _paint(pm, 2, 3)
        POLE[pm] = True
    for cx, w, h in ((198.0, 7, 6), (240.0, 6, 5), (272.0, 8, 6)):  # crates
        m = (X >= cx) & (X < cx + w) & (Y > GROUND_Y - h) & (Y <= GROUND_Y)
        tone = np.full(X.shape, 2, np.int8)
        tone[(X == cx) | (Y == GROUND_Y - h + 1)] = 3
        tone[(X == cx + w - 1) | (Y == GROUND_Y)] = 1
        tone[np.abs((X - cx) - (Y - (GROUND_Y - h)) * w / h) < 0.7] = 0
        _paint(m, 3, tone)


_build_camp()
CY, CX = np.nonzero(MAT > 0)
FLAGS = [dict(pole=(TOWER[0], TOWER[1] + 1), top=TOWER[1] - 16, w=11, h=6),
         dict(pole=(220.0, GROUND_Y - 47), top=GROUND_Y - 62, w=11, h=6),
         dict(pole=(260.0, GROUND_Y - 35), top=GROUND_Y - 48, w=9, h=5)]


# ---- the volley ----
ARROWS = []
_launch = SIGNAL0 - 1 + (LAUNCH_LAST - SIGNAL0 + 1) * np.sort(rng.beta(1.4, 1.8, NA))
for _n in range(NA):
    gx = rng.uniform(CAMP[0] + 2, CAMP[1] - 4)
    col = np.nonzero(MAT[:, int(gx)] > 0)[0]
    if len(col) and rng.random() < 0.75:
        gy = float(rng.choice(col)) + 0.5
    else:
        gy = GROUND_Y + rng.uniform(-2, 8)
    ang = SLANT + rng.uniform(-0.08, 0.08)
    sy0 = APEX_Y + rng.uniform(-4, 8)
    dx = (gy - sy0) / math.tan(ang)
    if gx - dx < 14:                                          # enter the cell inside its left margin
        sy0 += (14 - (gx - dx)) * math.tan(ang)
        dx = gx - 14
    fly = rng.uniform(11, 13) * (gy - sy0) / (gy - APEX_Y)
    ARROWS.append(dict(t0=float(_launch[_n]), fly=fly, start=(gx - dx, sy0), end=(gx, gy), ang=ang,
                       sink=rng.uniform(3.0, 5.0), ph=rng.uniform(0, 6.28), appear=float(rng.uniform(-1.5, 10)), fh=rng.uniform(5, 8),
                       seed=rng.uniform(0, 50), onobj=bool(len(col)) and gy < GROUND_Y - 0.6))
for _a in ARROWS:
    _a["land"] = _a["t0"] + _a["fly"]
HX = np.array([a["end"][0] for a in ARROWS])
HY = np.array([a["end"][1] for a in ARROWS])
HL = np.array([a["land"] for a in ARROWS])


def arrow_state(ar, f):
    t = (f - ar["t0"]) / ar["fly"]
    if t < 0:
        return None
    if t < 1:
        u = t * t                                             # far away it crawls, close up it streaks
        return "fly", (ar["start"][0] + (ar["end"][0] - ar["start"][0]) * u,
                       ar["start"][1] + (ar["end"][1] - ar["start"][1]) * u), u
    return "stuck", ar["end"], f - ar["land"]


def shaft(fr, tip, ang, a, sink=0.0, char=0.0):
    """Wooden shaft with pale fletching; char darkens the wood toward soot."""
    ux, uy = math.cos(ang), math.sin(ang)
    tail = (tip[0] - ux * ALEN, tip[1] - uy * ALEN)
    n = int(ALEN) + 2
    t = np.linspace(0, 1, n)
    seg = t * ALEN
    keep = seg >= sink
    wood = np.where((seg < ALEN * 0.5)[:, None], PW[2], PW[1]) * (1 - char) + PW[0] * char
    fr.over(np.round(tip[1] + (tail[1] - tip[1]) * t)[keep].astype(int),
            np.round(tip[0] + (tail[0] - tip[0]) * t)[keep].astype(int), wood[keep], a)
    px, py = -uy, ux
    fl = hexf("#e8dcc0") * (1 - char) + PW[0] * char
    for sgn in (-1, 1):
        b0 = (tail[0] + ux * 1.2, tail[1] + uy * 1.2)
        b1 = (b0[0] - ux * 2.0 + px * sgn, b0[1] - uy * 2.0 + py * sgn)
        line(fr, b0, b1, fl, fl, a * 0.9, a * 0.6)


def burning_head(fr, x, y, ux, uy, f, a, seed):
    """A hot head blob, a short flame tongue licking back and up, and three cooling ember dots."""
    sy, sx = _win(x - 3, x + 3, y - 3, y + 3)
    d = np.hypot(XX[sy, sx] - x, YY[sy, sx] - y) / 2.4
    ys, xs = np.nonzero(d <= 1)
    fr.over(ys + sy.start, xs + sx.start, PF[heat_tones(1.05 - 0.8 * d[ys, xs])], a)
    bx, by = -ux, -uy - 0.55
    n = math.hypot(bx, by)
    bx, by = bx / n, by / n
    flick = 1 + 0.25 * math.sin(f * 1.3 + seed)
    for k in range(1, 6):
        t = k / 5
        fr.dot(x + bx * 6 * t * flick + 0.8 * math.sin(f * 0.9 + seed + k), y + by * 6 * t * flick,
               PF[4] if t < 0.3 else PF[3] if t < 0.6 else PF[2], a * (1 - 0.6 * t))
    for k in range(1, 4):
        fr.dot(x - ux * (7 + 4 * k) + 0.6 * math.sin(seed + k), y - uy * (7 + 4 * k) - 0.5 * k * k,
               PF[2] if k < 3 else PF[1], a * (0.8 - 0.22 * k))
    fr.dot(x + ux, y + uy, WHITE, a)
    fr.glow(x, y, 4, 0.4 * a)
    fr.glow(x, y, 10, 0.12 * a)


def fire_level(f):
    """How hard the camp burns overall: builds with the hits, roars in the blaze, sinks in the burn-down."""
    return (0.45 * ease_io((f - IGNITE0) / 40.0) + 0.55 * ease_io((f - BLAZE0 + 8) / 12.0)) * \
        (1 - 0.7 * ease_io((f - BURN0) / 14.0))


def burn_map(f):
    """Burn per camp pixel: fronts spreading from each landed hit, faster upward, plus the blaze filling the rest."""
    b = np.zeros(len(CY))
    for i in np.nonzero(HL <= f - 1)[0]:
        age = min(f - HL[i] - 1, 60)
        dy = CY - HY[i]
        dd = np.hypot(CX - HX[i], np.where(dy < 0, dy * 0.55, dy * 1.5))
        b = np.maximum(b, np.clip((age * 0.32 - dd) / 6.0, 0, 1.3))
    b = np.maximum(b, ease_io((f - BLAZE0 + 2) / 22.0) * (0.7 + 0.5 * HN[CY, CX]))
    return b


def draw_camp(fr, f, b):
    mat, tone, hn = MAT[CY, CX], TONE[CY, CX], HN[CY, CX]
    pal = np.where((mat == 1)[:, None], PC[tone], PT[tone])
    charred = ease_io((b - 0.45) / 0.5)[:, None]
    ch_col = np.where((tone >= 2)[:, None], PCH[1], PCH[0])
    rgb = pal * (1 - charred) + ch_col * charred
    edge = np.clip(1 - np.abs(b - 0.22) / 0.2, 0, 1)
    live = 1 - ease_io((f - BURN0 - 4) / 12.0)
    glowing = edge * (0.6 + 0.4 * np.sin(f * 0.7 + hn * 20)) * max(live, 0.0)
    ember = ((mat >= 2) & (b > 0.7) & (hn > 0.82)) * (0.6 + 0.4 * np.sin(f * 0.5 + hn * 30))
    hot = np.clip(np.maximum(glowing, ember * 0.9), 0, 1)
    rgb = rgb * (1 - hot[:, None]) + (PF[3] * (hot > 0.6)[:, None] + PF[2] * (hot <= 0.6)[:, None]) * hot[:, None]
    hole = (mat == 1) & ~POLE[CY, CX] & (b > 0.85) & (hn < (b - 0.85) * 2.2)
    keep = ~hole
    fr.over(CY[keep], CX[keep], rgb[keep], 1.0)
    lit = hot > 0.2
    if lit.any():
        np.add.at(fr.L, (CY[lit], CX[lit]), 0.25 * hot[lit])
    return b


def draw_flags(fr, f, b_at):
    for j, fl in enumerate(FLAGS):
        px, py = fl["pole"]
        line(fr, (px, py), (px, fl["top"]), PT[1], PT[2], 1.0, 1.0)
        burn = b_at(px, py + 2) * 1.2
        left = fl["w"] * (1 - ease_io((burn - 0.3) / 0.6))
        if left < 1:
            continue
        sy, sx = _win(px, px + fl["w"] + 2, fl["top"] - 3, fl["top"] + fl["h"] + 3)
        X, Y = XX[sy, sx], YY[sy, sx]
        u = (X - px) / fl["w"]
        wave = 1.4 * np.sin(u * 5 - f * 0.45 + j) * u
        v = Y - fl["top"] - wave
        m = (X > px) & (X - px <= left) & (v >= 0) & (v <= fl["h"] * (1 - 0.35 * u))
        tone = np.where(np.sin(u * 5 - f * 0.45 + j + 1.2) > 0, 2, 1)
        tone[(v < 1)] = 3
        ys, xs = np.nonzero(m)
        rgb = PG[tone[ys, xs]]
        if burn > 0.3:
            front = (X[ys, xs] - px) > left - 2
            rgb = np.where(front[:, None], PF[3], rgb * (1 - 0.5 * ease_io((burn - 0.3) / 0.4)))
            fr.glow(px + left, fl["top"] + fl["h"] * 0.5, 6, 0.3)
            fire(fr, px + left - 1, fl["top"] + fl["h"], 6 + 3 * math.sin(f + j), 2.2, f, j * 5.1, sway=1.5)
        fr.over(ys + sy.start, xs + sx.start, rgb, 1.0)


BUCKETS = np.arange(CAMP[0] + 2, CAMP[1] - 2, 6.0)
BVARY = rng.uniform(0.45, 1.45, len(BUCKETS))
BJIT = rng.uniform(-2, 2, len(BUCKETS))
EMBERS = [dict(t0=rng.uniform(30, N - 8), x=rng.uniform(CAMP[0] + 6, CAMP[1] - 8), vy=rng.uniform(0.9, 2.2),
               vx=rng.uniform(-0.4, 1.4), ph=rng.uniform(0, 6.28), life=rng.uniform(10, 24),
               y0=rng.uniform(0, 1)) for _ in range(230)]
SMOKES = [dict(t0=34 + k * 2.2 + rng.uniform(0, 1.5), x=rng.uniform(CAMP[0] + 16, CAMP[1] - 20),
               vy=rng.uniform(0.8, 1.2), vx=rng.uniform(0.05, 0.3), r0=rng.uniform(4, 6), r1=rng.uniform(11, 16),
               wob=rng.uniform(0, 6.28)) for k in range(34)]


def puff(fr, x, y, r, a, f):
    sy, sx = _win(x - r - 1, x + r + 1, y - r - 1, y + r + 1)
    X, Y = XX[sy, sx], YY[sy, sx]
    ang = np.arctan2(Y - y, X - x)
    m = np.hypot(X - x, Y - y) <= r * (1 + 0.13 * np.sin(ang * 5 + x * 0.3 + f * 0.05))
    s = (X - x) + (Y - y)
    tone = np.where(s < -r * 0.35, 2, np.where(s > r * 0.45, 0, 1))
    ys, xs = np.nonzero(m)
    fr.over(ys + sy.start, xs + sx.start, PS[tone[ys, xs]], a)


def draw(f):
    fr = Frame()
    cx, by = TGT
    lvl = fire_level(f)

    for sm in SMOKES:                                   # smoke behind the camp, gathering toward a column
        t = f - sm["t0"]
        if t < 0:
            continue
        r = sm["r0"] + (sm["r1"] - sm["r0"]) * eout(t / 26.0)
        x0 = sm["x"] + (cx - sm["x"]) * min(1.0, t / 30.0) * 0.6
        y = 136 - sm["vy"] * t
        x = x0 + sm["vx"] * t + 3 * math.sin(t * 0.15 + sm["wob"])
        k = min(1.0, t / 4.0) * (1 - ease_io((r + 10 - y) / 20.0)) * (0.5 + 0.5 * min(1.0, lvl * 1.6))
        if k <= 0.01 or y - r < 3:
            continue
        puff(fr, x, y, r, 0.34 * k, f)
    if f >= BURN0 - 6:                                  # a late smoke stem off the embers
        for j in range(10):
            t = (f - BURN0 + 6 + j * 3.1) % 30
            y = 150 - t * 1.6
            r = 3 + t * 0.32
            if y - r > 6:
                puff(fr, cx - 30 + (j * 17) % 70 + t * 0.2, y, r, 0.28 * min(1, t / 4) * (1 - t / 30), f)

    # the camp itself, charring where the burn reaches
    b = burn_map(f)
    BF = np.zeros((H, W))
    BF[CY, CX] = b
    draw_camp(fr, f, b)
    draw_flags(fr, f, lambda x, y: BF[int(y), max(int(x) - 1, 0):int(x) + 3].max())

    # flames: at the top of the burning part of each 6 px column, climbing with the burn
    for j, bx in enumerate(BUCKETS):
        sl = BF[:, int(bx):int(bx) + 6]
        rows = np.nonzero((sl > 0.12).any(axis=1))[0]
        if not len(rows) or lvl <= 0.01:
            continue
        top = rows.min()
        heat = float(np.clip(sl[rows].max(), 0, 1))
        objh = GROUND_Y - top
        sink = 1 - 0.8 * ease_io((f - BURN0) / 12.0)
        vary = BVARY[j]
        hh = ((4 + 6 * heat) * sink + objh * 0.5 * vary * ease_io((f - BLAZE0 + 8) / 12.0) * sink) * \
            (0.35 + 0.65 * min(1.0, lvl * 1.4))
        wob = 0.8 + 0.25 * math.sin(f * 0.6 + j * 1.9)
        fire(fr, bx + 3 + BJIT[j], top + 4, hh * wob, (3.0 + 1.6 * heat) * (0.8 + 0.4 * vary), f, j * 2.7, sway=3)
        fr.glow(bx + 3, top - hh * 0.3, max(hh * 0.45, 4), 0.2 * heat)
        if len(rows) > 10 and heat > 0.4:              # a second, lower tongue on tall burning parts
            mid = rows[len(rows) // 2]
            fire(fr, bx + 2 + (j % 2) * 2, mid + 3, hh * 0.5 * wob, 2.6, f, j * 4.1 + 9, sway=2)

    # stuck arrows; arrows in open ground keep their own small flame
    for ar in ARROWS:
        st = arrow_state(ar, f)
        if st is None or st[0] != "stuck":
            continue
        age = st[2]
        x, y = ar["end"]
        shaft(fr, (x, y), ar["ang"], 1.0, sink=ar["sink"], char=min(1.0, age / 24.0))
        if age < 3:
            fr.glow(x, y - 2, 8, 0.35 * (1 - age / 3))
            for jj in range(3):
                a_ = math.pi + 0.5 + jj * 0.9 + ar["ph"]
                rr = 2 + age * 2
                fr.dot(x + math.cos(a_) * rr, y - 2 + math.sin(a_) * rr * 0.6, PF[4], 1 - age / 3)
        if not ar["onobj"]:
            own = min(1.0, (age + 1) / 4.0) * (1 - ease_io((f - BURN0) / 12.0))
            if own > 0.02:
                fire(fr, x, y + 1, ar["fh"] * own, 2.6, f, ar["seed"], sway=1.5, a=min(1.0, own * 1.5))
                fr.glow(x, y - 3, 6, 0.15 * own)

    sky = ease_io((f + 2) / 12.0) * (1 - ease_io((f - 40) / 20.0))
    fr.glow(96, 58, 92, 0.16 * sky, flat=0.5)

    for ar in ARROWS:
        st = arrow_state(ar, f)
        if st is None or st[0] != "fly":
            continue
        _, p, u = st
        fade_in = min(1.0, (f - ar["t0"] + 1) / 2.0)
        ux, uy = math.cos(ar["ang"]), math.sin(ar["ang"])
        if u < 0.2:
            tw = 0.5 + 0.5 * math.sin(f * 1.3 + ar["ph"] * 5)
            fr.dot(p[0] - ux * 2, p[1] - uy * 2, PF[2], 0.7 * fade_in)
            fr.dot(*p, PF[4] if tw > 0.5 else PF[3], fade_in)
            fr.glow(*p, 4, (0.2 + 0.2 * tw) * fade_in)
            continue
        shaft(fr, (p[0] - ux * 1.5, p[1] - uy * 1.5), ar["ang"], fade_in)
        burning_head(fr, p[0], p[1], ux, uy, f, fade_in, ar["seed"])
        sl_ = max(min(6 + 30 * u, (p[1] - 9) / uy, (p[0] - 9) / ux), 4.0)
        fr.glow_line((p[0] - ux * sl_, p[1] - uy * sl_), p, 5, 0.1 * fade_in)

    for e in EMBERS:
        t = f - e["t0"]
        if t < 0 or t > e["life"] or lvl < 0.15:
            continue
        k = (1 - t / e["life"]) * min(1.0, lvl * 1.5)
        x = e["x"] + e["vx"] * t + 2.5 * math.sin(t * 0.35 + e["ph"])
        y = 160 - 40 * e["y0"] * lvl - e["vy"] * t
        if y < 8 or not 8 < x < W - 8:
            continue
        col = PF[4] if k > 0.7 else PF[3] if k > 0.4 else PF[2]
        vx = e["vx"] + 0.9 * math.cos(t * 0.35 + e["ph"])
        line(fr, (x - vx * 1.4, y + e["vy"] * 1.4), (x, y), PF[2], col, 0.2, min(1.0, k * 1.8))
        fr.glow(x, y, 3, 0.4 * k)
        fr.glow(x, y, 7, 0.08 * k)

    # pools: along the burning camp and a wide warm one above it
    fr.glow_line((CAMP[0] + 10, by - 18), (CAMP[1] - 10, by - 18), 34, 0.12 * lvl)
    fr.glow(cx - 10, by - 50, 140, 0.05 + 0.12 * lvl, flat=0.65)
    rain = ease_io((f - RAIN0) / 8.0) * (1 - ease_io((f - 50) / 10.0))
    fr.glow(150, 90, 120, 0.12 * rain, flat=0.6)
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
    pick = [6, 18, 26, 34, 44, 54, 62, 70, 80, 90, 100, 107]
    for bg, tag in (("#101018", "dark"), ("#5a6070", "mid")):
        flat = [pfx.composite(cols[i], lights[i], bg) for i in range(N)]
        grid(flat, OUT / f"{NAME}_contact4x_{tag}.png", pick, n=3, scale=4)
    for i in (0, 30, 50, 66, 82, 107):
        Image.fromarray(pfx.composite(cols[i], lights[i], "#101018"), "RGBA").resize(
            (W * 4, H * 4), Image.NEAREST).save(OUT / f"{NAME}_f{i:03d}_x4.png")
    pfx.gif(comps, OUT / f"{NAME}.gif", FPS, scale=2)
    meta = dict(name=NAME, w=W, h=H, frames=N, fps=FPS, cols=ncol, loop=False, pivot=list(TGT), glow="medium",
                light_gain=1.0,
                states=dict(signal=[SIGNAL0, RAIN0 - 1], rain=[SIGNAL0, 58], ignite=[IGNITE0, BLAZE0 - 1],
                            blaze=[BLAZE0, BURN0 - 1], burndown=[BURN0, N - 1]),
                sheets=dict(composite=f"{NAME}.png", color=f"{NAME}_color.png", light=f"{NAME}_light.png"))
    (OUT / f"{NAME}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
