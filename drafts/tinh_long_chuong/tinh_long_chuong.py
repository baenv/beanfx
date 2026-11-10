"""tinh_long_chuong: star dragon palm. The caster rises, pulls stars down from the sky and gathers them into a big
dragon head constellation around themself, links them with gold threads, the head lights up solid, then shoots up
out of the caster, turns and plunges straight down into the ground with a gold body uncoiling behind it, its tail
breaking into stars.

General mode, 320x320, 24 fps, 174 frames (7.25 s), one-shot, soft style, glow medium (the flying body strong).

State table (frames at 24 fps):
    state      first  len  seconds  what moves                                              carrier
    rise           0   22   0.9     caster flies up and hovers mid-cell, gold motes spiral  caster
    pull          22   31   1.3     66 stars blink in at the top and accelerate down        stars
    gather        53   29   1.2     stars spiral onto the head outline round the caster     stars
    link          82   29   1.2     21 chains of gold threads trace the outline in parallel gold threads
    form         111   19   0.8     rim lights, fill sparkles in (12), hold and rear (7)    dragon head
    strike       130   24   1.0     shoots up (11), plunges (6), peak 147-148, ring          head and body
    dissolve     154   20   0.8     head shatters, body breaks tail to neck into stars      dust
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "kit"))
import caster as cs  # noqa: E402
import pfx  # noqa: E402

NAME = "tinh_long_chuong"
OUT = Path(__file__).resolve().parent / "out"
W = H = 320
FPS = 24

RISE0, RISE_N = 0, 22
PULL0, PULL_N = RISE0 + RISE_N, 31
GATHER0, GATHER_N = PULL0 + PULL_N, 29
LINK0, LINK_N = GATHER0 + GATHER_N, 29
FORM0, FORM_N, FILL_N = LINK0 + LINK_N, 19, 12
STRIKE0, STRIKE_N, UP_N, DOWN_N = FORM0 + FORM_N, 24, 11, 6
DISS0, DISS_N = STRIKE0 + STRIKE_N, 20
N = DISS0 + DISS_N
HOLD0 = FORM0 + FILL_N
IMP = STRIKE0 + UP_N + DOWN_N
STATES = dict(rise=[RISE0, PULL0 - 1], pull=[PULL0, GATHER0 - 1], gather=[GATHER0, LINK0 - 1],
              link=[LINK0, FORM0 - 1], form=[FORM0, STRIKE0 - 1], strike=[STRIKE0, DISS0 - 1],
              dissolve=[DISS0, N - 1])

GROUND = 284
CAST = (130.0, 208.0)                     # caster's hover foot
HEAD_A0 = (120.0, 190.0, 0.0, 1.45)       # anchor x, y, angle, scale: the caster sits inside the skull
HEAD_BACK = (118.0, 186.0, -0.06, 1.5)    # reared back before the strike
FLY_S = 1.2
NECK = 30.0                               # px from the head anchor back to where the body starts
BODY_L = 230.0

HEAD = ["#35204e", "#7c3c22", "#c8742a", "#f2b544", "#ffe9a6", "#ffffff",
        "#3a0c1c", "#7a1a24", "#c8402a", "#f07a50"]           # gold 0-5, then mouth red 6-9
STAR_COOL = ["#7080c8", "#b8ccff", "#ffffff"]
STAR_GOLD = ["#c8742a", "#ffd870", "#ffffff"]
THREAD = ["#f2b544", "#fff0c0"]
DUST = ["#3a3050", "#5e5068", "#8c7a7a"]
GOLD_RAMP = ["#6a2c08", "#e89a30", "#ffe2a0", "#ffffff"]
COOL_RAMP = ["#1a2a6a", "#5a86e8", "#cfe0ff", "#ffffff"]


def hexf(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


HEADF = np.stack([hexf(c) for c in HEAD])

# old hand-placed chains, still used for the head's skull and jaw outlines in local units (snout to +x, y down)
SKULL_C = [(52, -2), (50, -10), (42, -12), (34, -10), (27, -14), (21, -21), (12, -21), (4, -23), (-6, -24),
           (-16, -20), (-24, -11), (-27, 0)]
LIP_C = [(52, -2), (47, 3), (38, 4), (28, 5), (18, 8), (-8, 10)]
JAW_C = [(-8, 10), (10, 16), (26, 19), (44, 21), (45, 26), (38, 29), (18, 32), (0, 28), (-8, 10)]
EYE_C = [(11, -12), (17, -15), (23, -11), (17, -8), (11, -12)]
ANTLER_C = [(2, -23), (-6, -34), (-14, -42), (-24, -50), (-36, -54)]
TINES = [[(-6, -34), (0, -46)], [(-14, -42), (-10, -56)], [(-24, -50), (-26, -62)]]
FAR_C = [(-8, -23), (-18, -30), (-30, -36), (-42, -38)]
FAR_TINE = [(-18, -30), (-16, -42)]
WHISK_C = [[(48, -6), (58, -14), (67, -20), (75, -16), (77, -8)], [(40, 4), (52, 10), (60, 20), (58, 30)]]
BEARD_C = [[(38, 29), (34, 38), (26, 46), (18, 50)], [(18, 32), (12, 42), (4, 48)]]
MANE_C = [[(-16, -20), (-32, -22), (-46, -16), (-56, -6)], [(-27, 0), (-40, 2), (-52, 8), (-60, 18)]]
FRILL_C = [[(-8, 10), (-20, 18), (-34, 24)], [(0, 28), (-10, 34), (-22, 40)]]
FANG_C = [[(38, 4), (39, 12)], [(30, 19), (31, 12)]]
CHAINS = [SKULL_C, LIP_C, JAW_C, EYE_C, ANTLER_C, *TINES, FAR_C, FAR_TINE, *WHISK_C, *BEARD_C, *MANE_C,
          *FRILL_C, *FANG_C]

STAR_TARGET, PENS, PEN_GAP, EDGE_GAP, EDGE_N = 90, 10, 0.6, 1.8, 3
STARS, EDGES, FLARE, NS = [], [], {}, 0         # set by build_constellation(), traced from the solid head
RNG = np.random.default_rng(7)
DUST_N = 18
DSKY = np.stack([RNG.uniform(14, W - 14, DUST_N), RNG.uniform(8, 56, DUST_N)], 1)
DEND = np.stack([RNG.uniform(60, 240, DUST_N), RNG.uniform(120, 220, DUST_N)], 1)
DDEL = RNG.uniform(0, 10, DUST_N)
EMB = [(RNG.uniform(-math.pi * 0.95, -math.pi * 0.05), RNG.uniform(1.4, 4.0), RNG.uniform(0.6, 1.0))
       for _ in range(44)]
STREAKS = [(-math.pi * (0.08 + 0.84 * i / 15) + RNG.uniform(-0.08, 0.08), RNG.uniform(18, 44)) for i in range(16)]
PUFFS = [(RNG.uniform(-56, 56), RNG.uniform(6, 10), RNG.uniform(0, 3)) for _ in range(10)]
NOISE = RNG.random((H, W))
MOTES = [(RNG.uniform(0, 6.28), RNG.uniform(8, 16), RNG.uniform(0, 10)) for _ in range(8)]

YY, XX = np.mgrid[0:H, 0:W].astype(float)


def ease_io(s):
    s = min(max(s, 0.0), 1.0)
    return s * s * (3 - 2 * s)


def ease_out(s):
    s = min(max(s, 0.0), 1.0)
    return 1 - (1 - s) ** 2


def clamp01(s):
    return min(max(s, 0.0), 1.0)


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))


def catmull(pts, n=40):
    pts = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = (np.array(p, float) for p in pts[i - 1:i + 3])
        for t in np.linspace(0, 1, n, endpoint=False):
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(np.array(pts[-2], float))
    return np.array(out)


# the strike path: out of the caster up and right, over the top, then straight down onto the ground
PATH = catmull([HEAD_BACK[:2], (150, 124), (196, 100), (232, 132), (240, 186), (240, 224)])
ARC = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(PATH, axis=0).T))])
S_APEX = float(ARC[np.argmin(PATH[:, 1])] + 30)
S_END = float(ARC[-1])
PI = (240.0, float(GROUND))


def path_at(s):
    s = np.clip(s, 0, S_END)
    x = np.interp(s, ARC, PATH[:, 0])
    y = np.interp(s, ARC, PATH[:, 1])
    x2 = np.interp(np.clip(s + 2, 0, S_END), ARC, PATH[:, 0]) - np.interp(np.clip(s - 2, 0, S_END), ARC, PATH[:, 0])
    y2 = np.interp(np.clip(s + 2, 0, S_END), ARC, PATH[:, 1]) - np.interp(np.clip(s - 2, 0, S_END), ARC, PATH[:, 1])
    return x, y, np.arctan2(y2, x2)


def s_head(f):
    if f < STRIKE0:
        return 0.0
    if f < STRIKE0 + UP_N:
        return S_APEX * ease_io((f - STRIKE0 + 1) / UP_N)
    if f < IMP:
        return S_APEX + (S_END - S_APEX) * ((f - STRIKE0 - UP_N + 1) / DOWN_N) ** 2
    return S_END


def transform(f):
    if f < HOLD0:
        return HEAD_A0
    if f < STRIKE0:
        return mix(HEAD_A0, HEAD_BACK, ease_io((f - HOLD0) / (STRIKE0 - HOLD0)))
    s = s_head(f)
    x, y, a = path_at(s)
    k = clamp01((f - STRIKE0 + 1) / 3)
    a = HEAD_BACK[2] + (float(a) - HEAD_BACK[2]) * k
    return float(x), float(y), a, HEAD_BACK[3] + (FLY_S - HEAD_BACK[3]) * clamp01((f - STRIKE0 + 1) / 8)


def to_world(tr, p):
    ax, ay, a, s = tr
    c, n = math.cos(a), math.sin(a)
    return ax + s * (p[0] * c - p[1] * n), ay + s * (p[0] * n + p[1] * c)


def foot_at(f):
    t = ease_io((f - RISE0 - 2) / (RISE_N - 2))
    y = GROUND - (GROUND - CAST[1]) * t + 2 * math.sin(f * 0.25) * t
    if f >= DISS0:
        y += 6 * ease_io((f - DISS0) / DISS_N)
    return CAST[0], y


class Frame:
    def __init__(self):
        self.col = np.zeros((H, W, 3))
        self.a = np.zeros((H, W))
        self.Lg = np.zeros((H, W))
        self.Lc = np.zeros((H, W))

    def over(self, ys, xs, rgb, a):
        ys = np.atleast_1d(np.asarray(ys)).astype(int)
        xs = np.atleast_1d(np.asarray(xs)).astype(int)
        rgb = np.broadcast_to(np.asarray(rgb, float), (len(ys), 3))
        a = np.broadcast_to(np.asarray(a, float), (len(ys),))
        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W) & (a > 0.003)
        ys, xs, rgb, a = ys[ok], xs[ok], rgb[ok], a[ok]
        a0 = self.a[ys, xs]
        ao = a + a0 * (1 - a)
        self.col[ys, xs] = (rgb * a[:, None] + self.col[ys, xs] * (a0 * (1 - a))[:, None]) / np.maximum(ao, 1e-6)[:, None]
        self.a[ys, xs] = ao

    def px(self, x, y, rgb, a):
        self.over([round(y)], [round(x)], rgb, a)


def line_pts(p0, p1):
    n = max(int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * 2), 1)
    t = np.linspace(0, 1, n + 1)
    pts = np.stack([np.round(p0[1] + (p1[1] - p0[1]) * t), np.round(p0[0] + (p1[0] - p0[0]) * t)], 1).astype(int)
    _, idx = np.unique(pts, axis=0, return_index=True)
    return pts[np.sort(idx)]


def box(m, r):
    k = 2 * r + 1
    p = np.pad(m, r + 1)
    c = p.cumsum(0).cumsum(1)
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k])[:m.shape[0], :m.shape[1]] / (k * k)


def bevel_step(m):
    """-1, 0, +1 or +2 per pixel: a soft rounded form lit from the top left."""
    b = box(m.astype(float), 2)
    e = np.zeros_like(b)
    e[2:-2, 2:-2] = b[4:, 4:] - b[:-4, :-4]
    return (e > 0.2).astype(int) + (e > 0.55) - (e < -0.2)


def star(fr, x, y, size, a, gold):
    ramp = [hexf(c) * (1 - gold) + hexf(g) * gold for c, g in zip(STAR_COOL, STAR_GOLD)]
    xi, yi = round(x), round(y)
    if size >= 3:
        for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            fr.px(xi + dx, yi + dy, ramp[0], a * 0.45)
    for d in range(1, int(size) + 1):
        tone = ramp[1] if d == 1 else ramp[0]
        aa = a * (1 - (d - 1) / (size + 0.5)) * 0.9
        for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
            fr.px(xi + dx, yi + dy, tone, aa)
    fr.px(xi, yi, ramp[2], a)
    for L, w in ((fr.Lc, 1 - gold), (fr.Lg, gold)):
        if w > 0:
            cs.glow(L, x, y, 3 + size, 0.4 * a * w)
            cs.glow(L, x, y, 8 + 2.5 * size, 0.14 * a * w)


def star_pos(i, f, T):
    d = DELAY[i]
    m0 = PULL0 + 4 + d
    m1 = GATHER0 + d * 0.5
    m2 = GATHER0 + 20 + d * 0.4
    s = SKY[i] + np.array([0.0, 0.15 * max(f - (PULL0 - 4), 0)])
    c = np.asarray(T) + CLOUD[i]
    if f < m0:
        return s
    if f < m1:
        t = ((f - m0) / (m1 - m0)) ** 2
        s0 = SKY[i] + np.array([0.0, 0.15 * (m0 - (PULL0 - 4))])
        return s0 + (c - s0) * t
    e = ease_out((f - m1) / (m2 - m1))
    o = c - np.asarray(T)
    r = -1.2 * e
    o = np.array([o[0] * math.cos(r) - o[1] * math.sin(r), o[0] * math.sin(r) + o[1] * math.cos(r)])
    return np.asarray(T) + o * (1 - e)


def draw_stars(fr, f, tr):
    if f >= FORM0 + 10 or f < PULL0 - 4:
        return
    fade = 1 - clamp01((f - FORM0 - 2) / 8)
    for i in range(NS):
        T = to_world(tr, STARS[i])
        a_in = clamp01((f - (PULL0 - 4 + DELAY[i])) / 5) * fade
        if a_in <= 0:
            continue
        p = np.clip(star_pos(i, f, T), 10, W - 10)
        q = np.clip(star_pos(i, f - 2, T), 10, W - 10)
        if math.hypot(*(p - q)) > 2.5:
            pts = line_pts(q, p)
            fr.over(pts[:, 0], pts[:, 1], hexf(STAR_COOL[1]), np.linspace(0.1, 0.45, len(pts)) * a_in)
            cs.glow_line(fr.Lc, tuple(q), tuple(p), 4, 0.1 * a_in)
        gold = clamp01((f - FLARE[i]) / 4)
        size = 1 + (math.sin(f * 0.55 + TW[i]) > 0.6)
        if f >= FLARE[i]:
            size = max(size, 3 - 2 * clamp01((f - FLARE[i]) / 5))
        star(fr, p[0], p[1], size, a_in, gold)
    for j in range(DUST_N):                       # dust stars fall with the rest and are absorbed on the way
        t0 = PULL0 - 2 + DDEL[j]
        if f < t0:
            continue
        a_in = clamp01((f - t0) / 4)
        t = clamp01((f - t0 - 6) / 24)
        a = a_in * (1 - t)
        if a <= 0.02:
            continue
        p = DSKY[j] + (DEND[j] - DSKY[j]) * t * t
        q = DSKY[j] + (DEND[j] - DSKY[j]) * max(t - 0.08, 0) ** 2
        if t > 0.1:
            pts = line_pts(q, p)
            fr.over(pts[:, 0], pts[:, 1], hexf(STAR_COOL[0]), np.linspace(0.05, 0.4, len(pts)) * a)
        star(fr, p[0], p[1], 1 if (j + f // 3) % 3 else 0, a * 0.8, 0)


def draw_threads(fr, f, tr):
    if f < LINK0:
        return
    fade = 1 - clamp01((f - FORM0 - 2) / (FILL_N * 0.5))
    if fade <= 0.02:
        return
    for a, b, t0 in EDGES:
        p = clamp01((f - t0) / EDGE_N)
        if p <= 0:
            continue
        pa, pb = to_world(tr, STARS[a]), to_world(tr, STARS[b])
        tip = (pa[0] + (pb[0] - pa[0]) * ease_out(p), pa[1] + (pb[1] - pa[1]) * ease_out(p))
        pts = line_pts(pa, tip)
        fr.over(pts[:, 0], pts[:, 1], hexf(THREAD[0]), 0.85 * fade)
        cs.glow_line(fr.Lg, pa, tip, 2.5, 0.12 * fade)
        if p < 1:
            fr.over(pts[-2:, 0], pts[-2:, 1], hexf(THREAD[1]), 1.0)
            fr.px(tip[0], tip[1], hexf("#ffffff"), 1.0)
            cs.glow(fr.Lg, tip[0], tip[1], 5, 0.45)


def poly(U, V, pts):
    inside = np.zeros(U.shape, bool)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        cond = ((y0 > V) != (y1 > V)) & (U < (x1 - x0) * (V - y0) / ((y1 - y0) or 1e-9) + x0)
        inside ^= cond
    return inside


def taper(U, V, pts, w0, w1, mw):
    m = np.zeros(U.shape, bool)
    n = len(pts) - 1
    for k, (a, b) in enumerate(zip(pts, pts[1:])):
        w = max(w0 + (w1 - w0) * (k + 0.5) / n, mw)
        m |= cs.seg_d(U, V, a, b) <= w
    return m


SKULL = SKULL_C + [(-20, 7)] + LIP_C[::-1][:-1]
JAW = JAW_C[:-1]
MANE_X = [((-4, -22), 222, 30), ((-11, -21), 215, 38), ((-17, -17), 207, 44), ((-22, -11), 199, 48),
          ((-25, -4), 191, 48), ((-26, 4), 184, 46), ((-24, 11), 177, 40), ((-20, 17), 170, 34),
          ((-15, 21), 163, 28)]
HORN_C = [(4, -19), (-6, -30), (-20, -40), (-36, -46), (-50, -46), (-58, -42)]
HORN_T = [(-20, -40), (-24, -50), (-22, -60)]
GOLD7 = np.stack([hexf(c) for c in ("#1e1028", "#4a2418", "#86461c", "#c27a28", "#e8aa3c", "#ffd877", "#fff4d0")])
HORN6 = np.stack([hexf(c) for c in ("#1c0c18", "#4a2216", "#844a24", "#c08a48", "#ecca88", "#fff4d8")])
RED4 = np.stack([hexf(c) for c in ("#2a0814", "#5a1020", "#a02a28", "#e0604a")])
KEY = np.array([-0.5, -0.62, 0.6]) / np.linalg.norm([-0.5, -0.62, 0.6])
HALF = (KEY + [0, 0, 1]) / np.linalg.norm(KEY + [0, 0, 1])


def shade_v(h):
    """Light a height map (px): key from the top left, a specular glint, a warm rim from the bottom right."""
    gy, gx = np.gradient(h)
    nz = 1 / np.sqrt(gx * gx + gy * gy + 1)
    nx, ny = -gx * nz, -gy * nz
    diff = np.clip(nx * KEY[0] + ny * KEY[1] + nz * KEY[2], 0, 1)
    spec = np.clip(nx * HALF[0] + ny * HALF[1] + nz * HALF[2], 0, 1) ** 28
    rim = np.clip(nx * 0.75 + ny * 0.45, 0, 1) * (1 - nz) ** 1.5
    return np.clip(0.02 + 0.85 * diff ** 1.6 + 0.55 * spec + 0.3 * rim, 0, 1)


def ramp(v, pal, lo=0, hi=None):
    hi = len(pal) - 1 if hi is None else hi
    return pal[np.clip(np.round(lo + v * (hi - lo)).astype(int), lo, hi)]


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b + (a - b) * h - k * h * (1 - h)


def sd_ell(U, V, cx, cy, rx, ry):
    return (np.hypot((U - cx) / rx, (V - cy) / ry) - 1) * min(rx, ry)


def sd_cap(U, V, a, b, ra, rb):
    ex, ey = b[0] - a[0], b[1] - a[1]
    h = np.clip(((U - a[0]) * ex + (V - a[1]) * ey) / (ex * ex + ey * ey), 0, 1)
    return np.hypot(U - a[0] - ex * h, V - a[1] - ey * h) - (ra + (rb - ra) * h)


def dome(d, R):
    t = np.clip(-d, 0, R)
    return np.sqrt(t * (2 * R - t))


def bump(dist, k, w):
    return k * np.exp(-dist * dist / w)


def tube(U, V, pts, r0, r1, ring=0.0):
    """A tapered tube along a polyline: mask, height (local units) and arc length, for horns."""
    best = np.full(U.shape, 1e9)
    hh = np.zeros(U.shape)
    s_acc = 0.0
    total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
    sat = np.zeros(U.shape)
    for a, b in zip(pts, pts[1:]):
        ex, ey = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(ex, ey)
        h = np.clip(((U - a[0]) * ex + (V - a[1]) * ey) / (ln * ln), 0, 1)
        d = np.hypot(U - a[0] - ex * h, V - a[1] - ey * h)
        s = s_acc + h * ln
        r = r0 + (r1 - r0) * (s / total)
        r = r * (1 - ring * (np.sin(s * 1.6) > 0.55))
        e = d - r
        upd = e < best
        best = np.where(upd, e, best)
        hh = np.where(upd, np.sqrt(np.clip(r * r - d * d, 0, None)), hh)
        sat = np.where(upd, s, sat)
        s_acc += ln
    return best <= 0, hh, sat


def lipline(u):
    return 8.5 - (u + 10) * 7.5 / 58


def jawtop(u):
    return 15 + (u + 10) * 10.5 / 55 - (7 - (u + 10) * 3.6 / 55)


def draw_head(fr, f, tr, alpha=1.0, fill=None, whiten=0.0, shatter=0.0, light=True, trace=False):
    """trace=True returns the head's silhouette with the mouth open (no tongue, teeth or whiskers) for the
    constellation, instead of drawing."""
    ax, ay, ang, S = tr
    r = 112 * S
    sy, sx = cs._win((H, W), ax - r, ax + r, ay - r, ay + r)
    X, Y = XX[sy, sx] - ax, YY[sy, sx] - ay
    c, n = math.cos(ang), math.sin(ang)
    U, V = (X * c + Y * n) / S, (-X * n + Y * c) / S
    mw = 0.6 / S
    col = np.zeros(U.shape + (3,))
    union = np.zeros(U.shape, bool)
    tmask = np.zeros(U.shape, bool)

    def lay(m, rgb, tmode="add"):
        col[m] = rgb[m] if rgb.ndim == 3 else rgb
        union[m] = True
        if tmode == "add":
            tmask[m] = True
        elif tmode == "cut":
            tmask[m] = False

    def flat(m, base, tmode="add"):
        if m.any():
            lay(m, GOLD7[np.clip(cs.shade(m, base) + 1, 0, 6)], tmode)

    def lock(s0, a0, a1, ln, w0, base, wave, n=12):
        m, pts = cs.strand(U, V, s0, a0, a1, ln, w0, 0.4, wave, n=n, mw=mw)
        flat(m, base)
        mid = np.zeros(U.shape, bool)
        for p, q in zip(pts[1:-3], pts[2:-2]):
            mid |= cs.seg_d(U, V, p, q) <= 0.45
        col[m & mid] = GOLD7[max(base, 1)]

    def horn(pts, tine, r0, dark):
        m, hh, s = tube(U, V, pts, r0, 0.9, ring=0.03)
        m2, h2, _ = tube(U, V, tine, r0 * 0.5, 0.7, ring=0.03)
        hh = np.where(m2 & ~m, h2, hh)
        m = m | m2
        v = shade_v(hh * S) ** 1.3 * (1 - 0.08 * ((np.sin(s * 1.6) > 0.55) & m)) - dark
        lay(m, ramp(np.clip(v, 0, 1), HORN6))

    far = [(p[0] - 7, p[1] + 3) for p in HORN_C]
    horn(far, [(p[0] - 7, p[1] + 3) for p in HORN_T], 4.2, 0.3)
    for j, (s0, a0, ln) in enumerate(MANE_X):                                       # mane, flame locks
        lock(s0, math.radians(a0), math.radians(a0 + 42 + 6 * math.sin(f * 0.2 + j)), ln, 4.2,
             2 if j % 2 else 3, lambda k, j=j: 0.45 * math.sin(k * 0.6 - f * 0.4 + j * 1.1))
    for j in range(6):                                                               # cheek frill
        lock((-8 + j * 1.5, 12 + j * 3), math.radians(160 + j * 7), math.radians(178 + j * 9), 20 - j * 1.5, 2.2,
             3 if j % 2 else 2, lambda k, j=j: 0.15 * math.sin(k * 0.9 - f * 0.5 + j), n=8)

    # mouth: dark red inside and a tongue that curls out
    mouth = poly(U, V, [(-10, 8.5), (50, 0.5), (48, 23), (-10, 12)])
    lay(mouth, ramp(np.clip(0.2 + 0.25 * (U + 10) / 58, 0, 1), RED4), "none")
    tm, th, _ = tube(U, V, [(-6, 15), (12, 18), (30, 17), (46, 12), (56, 14), (61, 20), (59, 25)], 2.8, 1.1)
    lay(tm, ramp(shade_v(th * S), RED4), "none")

    # lower jaw: a tapered capsule with a chin, a lit lip ridge and plates under it
    dj = smin(sd_cap(U, V, (-10, 15), (45, 25.5), 7.0, 3.4), sd_ell(U, V, 42, 27.5, 4.5, 3.5), 2.0)
    jaw = dj <= 0
    hj = dome(dj, 7) + bump(cs.seg_d(U, V, (-8, 8.6), (45, 22.1)), 1.6, 1.2)
    hj += (0.7 * np.clip(1 - (((U + 60) % 5) - 2.5) ** 2 / 4, 0, 1)) * (V > 16 + (U + 10) * 10.5 / 55)
    lay(jaw, ramp(shade_v(hj * S), GOLD7))
    teeth = np.zeros(U.shape, bool)                                                  # lower teeth and fangs
    for u in np.arange(-2, 44, 3.4):
        v = jawtop(u) + 0.3
        teeth |= cs.tri(U, V, (u - 1.3, v + 0.4), (u + 1.3, v + 0.4), (u, v - 2.6))
    for u, ln in ((40, 7), (16, 5)):
        v = jawtop(u) + 0.3
        teeth |= cs.tri(U, V, (u - 1.8, v + 0.5), (u + 1.8, v + 0.5), (u + 0.6, v - ln))
    lay(teeth, ramp(np.clip(0.75 + 0.25 * (np.mod(U, 3.4) < 1.6), 0, 1), HORN6), "cut")

    # skull: cranium, tapered snout, brow, cheek and nose blended into one smooth form
    d = sd_ell(U, V, -9, -4, 21, 13)
    d = smin(d, sd_cap(U, V, (-4, -6), (49, -4), 12, 6.0), 7)
    d = smin(d, sd_ell(U, V, 16, -14, 10, 5.5), 3)
    d = smin(d, sd_ell(U, V, -4, 0, 13, 7), 4)
    d = smin(d, sd_ell(U, V, 49, -5.5, 5, 5), 2)
    skull = d <= 0
    hs = dome(d, 10) * 0.65
    hs += bump(cs.seg_d(U, V, (-26, -2), (-4, -18)), 1.8, 6)                          # occipital ridge
    hs += bump(cs.seg_d(U, V, (5, -17), (27, -15)), 3.2, 5)                           # brow ridge
    hs += bump(cs.seg_d(U, V, (-14, 1), (12, -3)), 2.6, 4)                            # cheekbone
    hs += bump(cs.seg_d(U, V, (26, -11), (47, -9)), 1.6, 2.5)                         # nasal ridge
    hs += bump(np.hypot((U + 8) / 1.6, V - 6), 2.0, 22)                               # jaw muscle
    hs -= bump(np.hypot((U - 17) / 1.7, V + 10), 3.4, 9)                              # eye socket
    hs -= bump(cs.seg_d(U, V, (-10, 8.5), (48, 1)), 2.2, 1.4)                         # lip groove
    hs -= bump(np.hypot(U - 47, V + 5), 2.6, 2.5)                                     # nostril
    row = np.floor((V + 40) / 3)                                                      # overlapping scales, cheek
    cu = ((U + 1.8 * (row % 2) + 100) % 3.6) - 1.8
    cv = ((V + 40) % 3) / 3
    wsc = np.clip((4 - U) / 10, 0, 1) * np.clip((V + 12) / 6, 0, 1) * np.clip((np.hypot(U - 17, V + 10) - 8) / 4, 0, 1)
    hs += 0.7 * np.clip(1 - cu * cu / 3.2, 0, 1) * (1 - cv) * wsc
    pl = ((U + 100) % 5.5) - 2.75                                                     # plates on the snout top
    hs += 0.9 * np.clip(1 - pl * pl / 5, 0, 1) * (U > 22) * (U < 47) * np.clip((-V - 6) / 3, 0, 1)
    lay(skull, ramp(shade_v(hs * S), GOLD7))

    teeth = np.zeros(U.shape, bool)                                                  # upper teeth and fangs
    for u in np.arange(-4, 46, 3.4):
        v = lipline(u)
        teeth |= cs.tri(U, V, (u - 1.3, v - 0.4), (u + 1.3, v - 0.4), (u, v + 2.6))
    for u, ln in ((42, 8), (20, 6)):
        v = lipline(u)
        teeth |= cs.tri(U, V, (u - 1.8, v - 0.5), (u + 1.8, v - 0.5), (u + 0.6, v + ln))
    lay(teeth & (V > lipline(U) - 0.6), ramp(np.clip(0.75 + 0.25 * (np.mod(U, 3.4) < 1.6), 0, 1), HORN6), "cut")

    # eye: almond, glowing iris, slit pupil, a dark lid line and a glint
    eye = poly(U, V, [(10, -10.5), (15, -13.8), (21, -13.2), (24, -11.2), (18, -8.6)])
    lay(eye, np.broadcast_to(hexf("#ffb030"), U.shape + (3,)))
    col[eye & (np.hypot((U - 18) / 4.5, (V + 11.3) / 2.2) <= 1)] = hexf("#ffe890")
    col[eye & (np.abs(U - 18.3) < max(0.55, mw * 0.9))] = hexf("#2a0c10")
    lid = skull & ~eye & (cs.seg_d(U, V, (9.5, -10.5), (15, -14.3)) <= 0.8 + mw
                          ) | skull & ~eye & (cs.seg_d(U, V, (15, -14.3), (24.5, -11.5)) <= 0.8 + mw)
    col[lid] = GOLD7[0]
    col[np.hypot(U - 15.8, V + 12.3) <= max(0.7, mw)] = hexf("#ffffff")

    # beard and whiskers
    for j, (s0, a0) in enumerate((((38, 28), 112), ((32, 27.5), 118), ((26, 27), 124), ((20, 26), 130),
                                  ((14, 25), 136))):
        lock(s0, math.radians(a0), math.radians(a0 + 34), 16 + (j * 5) % 9, 2.0, 2 if j % 2 else 3,
             lambda k, j=j: 0.25 * math.sin(k * 0.8 - f * 0.5 + j), n=9)
    for j, (s0, a0, a1, ln) in enumerate((((46, -3), 70, 175, 58), ((40, 4), 95, 190, 48))):
        wm, pts = cs.strand(U, V, s0, math.radians(a0), math.radians(a1), ln, 1.6, 0.5,
                            lambda k, j=j: 0.5 * math.sin(k * 0.55 - f * 0.35 + j * 2), n=16, mw=mw)
        flat(wm, 3, "none")
        for p_, q_ in zip(pts[:8], pts[1:9]):
            col[wm & (cs.seg_d(U, V, p_, q_) <= 0.5)] = GOLD7[5]
    # brow spikes swept back, then the near horn on top
    for j, (s0, a0, ln) in enumerate((((10, -18), 222, 11), ((17, -19.5), 214, 14), ((24, -17), 208, 10))):
        lock(s0, math.radians(a0), math.radians(a0 - 20), ln, 2.4, 3,
             lambda k, j=j: 0.1 * math.sin(k - f * 0.5 + j), n=8)
    horn(HORN_C, HORN_T, 5.2, 0.0)
    if trace:
        return tmask, sy, sx

    a = np.where(union, 0.95, 0.0) * alpha
    fresh = np.zeros(U.shape, bool)
    if fill is not None:                       # pixels sparkle in at full colour; the light runs ahead of them
        nz = NOISE[sy, sx]
        lit = nz < fill * 1.25 - 0.15
        fresh = union & lit & (nz > fill * 1.25 - 0.35)
        a = np.where(lit, a, 0.0)
        col[fresh] = GOLD7[6]
    if whiten > 0:
        col = col + (1 - col) * 0.45 * whiten * 2
    if shatter > 0:
        a = a * (NOISE[sy, sx] > shatter) * (1 - 0.5 * shatter)
    ys, xs = np.nonzero(a > 0.01)
    fr.over(ys + sy.start, xs + sx.start, col[ys, xs], a[ys, xs])

    if light:
        k = alpha * (1 if fill is None else clamp01(fill * 1.2)) * (1 - shatter)
        w = lambda p: to_world(tr, p)                                                        # noqa: E731
        cs.glow_line(fr.Lg, w((-24, -6)), w((48, -5)), 9 * S, 0.12 * k)
        cs.glow_line(fr.Lg, w((-24, -6)), w((48, -5)), 26 * S, 0.08 * k)
        cs.glow_line(fr.Lg, w((4, -19)), w((-58, -42)), 4 * S, 0.08 * k)
        cs.glow(fr.Lg, *w((18, -11)), 4 * S, 0.6 * k)
        cs.glow(fr.Lg, *w((18, -11)), 12 * S, 0.22 * k)
        cs.glow(fr.Lg, *w((36, 11)), 12 * S, 0.24 * k)                                    # throat fire
        cs.glow(fr.Lg, *w((-34, 0)), 34 * S, 0.07 * k)
        ghost = 0.0 if fill is None else 0.7 * clamp01(fill * 4) * (1 - fill * 0.8)
        flash = 0.0 if fill is None else 0.5 * math.exp(-((fill - 0.85) / 0.12) ** 2)
        inside = alpha * (1 - shatter) * (0.2 + flash)
        fr.Lg[sy, sx] += np.where(union, np.where(a > 0.01, inside, ghost), 0.0) + fresh * 0.35
        cs.glow(fr.Lg, *w((4, -6)), 70 * S, (0.12 + 0.25 * flash) * alpha * (1 - shatter), flat=0.8)


def draw_body(fr, f, sh, s_break=None, gone=0.0):
    """The gold body along the strike path, from the neck back BODY_L px; the tail breaks into stars.
    s_break: arc length below which the body has already broken away (the dissolve, tail first); gone: how far
    the rest has sparkled away, faster near the neck so the body breaks up with the head."""
    s_neck = sh - NECK
    s_tail = max(0.0, s_neck - BODY_L)
    if s_break is not None:
        s_tail = max(s_tail, s_break)
    if s_neck - s_tail < 4:
        return
    ss = np.arange(s_tail, s_neck + 0.1, 3.0)
    px, py, pa = path_at(ss)
    m_ = 18
    sy, sx = cs._win((H, W), px.min() - m_, px.max() + m_, py.min() - m_, py.max() + m_)
    X, Y = XX[sy, sx], YY[sy, sx]
    best = np.full(X.shape, 1e9)
    sb = np.zeros(X.shape)
    vb = np.zeros(X.shape)
    for i in range(len(ss) - 1):
        ax_, ay_, bx_, by_ = px[i], py[i], px[i + 1], py[i + 1]
        ex, ey = bx_ - ax_, by_ - ay_
        ln = math.hypot(ex, ey) or 1e-6
        h = np.clip(((X - ax_) * ex + (Y - ay_) * ey) / (ln * ln), 0, 1)
        d = np.hypot(X - ax_ - ex * h, Y - ay_ - ey * h)
        upd = d < best
        best = np.where(upd, d, best)
        sb = np.where(upd, ss[i] + h * (ss[i + 1] - ss[i]), sb)
        vb = np.where(upd, (-(X - ax_) * ey + (Y - ay_) * ex) / ln, vb)
    u = np.clip((s_neck - sb) / BODY_L, 0, 1)
    rad = 2.5 + 10.5 * (1 - u) ** 0.8
    body = best <= rad
    vn = vb / rad
    tone = np.full(X.shape, 2)
    belly = vn > 0.3
    tone[belly] = 3
    tone[belly & ((sb / 4.0) % 1 < 0.25)] = 2                                          # belly plates
    scale = ((sb / 5.0 + (vn * 1.2) ** 2) % 1) < 0.2
    tone[~belly & scale] = 1
    tone[vn < -0.75] = 1
    hb = np.sqrt(np.clip(rad * rad - best * best, 0, None))
    cu = (sb % 6) - 3
    cv = ((vb + 2 * (np.floor(sb / 6) % 2) + 100) % 4) - 2
    hb += np.where(belly, 0.8 * np.clip(1 - ((sb % 4) - 2) ** 2 / 4, 0, 1),
                   1.1 * np.sqrt(np.clip(1 - cu * cu / 9 - cv * cv / 4, 0, 1))) * body
    vbody = shade_v(hb) + 0.12 * belly
    spines = np.zeros(X.shape, bool)                                                   # flame fins on the back
    for s0 in np.arange(s_neck - 6, s_tail, -8.0):
        x0, y0, a0 = (float(v) for v in path_at(s0))
        uu = clamp01((s_neck - s0) / BODY_L)
        r0 = 2.5 + 10.5 * (1 - uu) ** 0.8
        nx, ny = -math.sin(a0), math.cos(a0)
        tx, ty = math.cos(a0), math.sin(a0)
        bxp, byp = x0 - nx * r0, y0 - ny * r0
        hgt = 3 + 6 * (1 - uu)
        tip = (bxp - nx * hgt - tx * 4, byp - ny * hgt - ty * 4)
        spines |= cs.tri(X, Y, (bxp + tx * 3, byp + ty * 3), (bxp - tx * 3, byp - ty * 3), tip)
    spines &= ~body
    tone[spines] = 3
    claws = np.zeros(X.shape, bool)                                                    # two claws by the neck
    talons = np.zeros(X.shape, bool)
    for off in (22, 40):
        s0 = s_neck - off
        if s0 < s_tail + 6:
            continue
        x0, y0, a0 = (float(v) for v in path_at(s0))
        nx, ny = -math.sin(a0), math.cos(a0)
        tx, ty = math.cos(a0), math.sin(a0)
        r0 = 2.5 + 10.5 * (1 - clamp01(off / BODY_L)) ** 0.8
        hip = (x0 + nx * r0 * 0.5, y0 + ny * r0 * 0.5)
        knee = (hip[0] + nx * 9 + tx * 3, hip[1] + ny * 9 + ty * 3)
        paw = (knee[0] + tx * 6 + nx * 3, knee[1] + ty * 6 + ny * 3)
        claws |= (cs.seg_d(X, Y, hip, knee) <= 2.6) | (cs.seg_d(X, Y, knee, paw) <= 1.8)
        for j in (-1, 0, 1):
            ang = a0 + 0.5 * j + 0.4
            talons |= cs.seg_d(X, Y, paw, (paw[0] + math.cos(ang) * 5, paw[1] + math.sin(ang) * 5)) <= 0.7
    tone[claws] = 3
    tone[talons] = 5
    allm = body | spines | claws | talons
    a = np.where(allm, 0.94, 0.0)
    nz = NOISE[sy, sx]
    tail = np.clip((u - 0.6) / 0.4, 0, 1)
    a = a * (nz > tail * 0.95) * (1 - 0.4 * tail)
    if s_break is not None:
        front = np.clip((sb - s_break) / 14, 0, 1)
        a = a * (nz < front * 1.1)
    if gone > 0:
        thr = gone * (1 + 1.5 * np.clip((sb - s_neck + 40) / 40, 0, 1))
        a = a * (nz > thr)
        tone = np.where(nz < thr + 0.08, 5, tone)
    ys, xs = np.nonzero(a > 0.01)
    rgb = HEADF[np.clip(tone, 0, 5)]
    shaded = body & ~spines & ~claws & ~talons & (tone != 5)
    rgb[shaded] = ramp(np.clip(vbody, 0, 1), GOLD7)[shaded]
    fr.over(ys + sy.start, xs + sx.start, rgb[ys, xs], a[ys, xs])
    last = len(ss) - 1
    for i in range(0, last, 4):
        k = 1 - 0.6 * clamp01((s_neck - ss[i]) / BODY_L)
        j = min(i + 4, last)
        cs.glow_line(fr.Lg, (px[i], py[i]), (px[j], py[j]), 11, 0.15 * k)
        cs.glow_line(fr.Lg, (px[i], py[i]), (px[j], py[j]), 34, 0.09 * k)
    lit_in = a * (0.3 + 0.7 * (1 - u)) * 0.3
    fr.Lg[sy, sx] += np.where(spines, a * 0.22, lit_in)
    for s0 in np.arange(s_tail + 3, s_tail + 0.4 * (s_neck - s_tail), 9.0):    # stars the tail breaks into
        x0, y0, _ = (float(v) for v in path_at(s0))
        j = int(s0)
        ox = (NOISE[j % H, (j * 7) % W] - 0.5) * 16
        oy = (NOISE[(j * 3) % H, j % W] - 0.5) * 16
        star(fr, x0 + ox, y0 + oy, 2 if (j // 9 + f) % 4 == 0 else 1, 0.9, 1.0)
    if s_break is not None:
        x0, y0, _ = (float(v) for v in path_at(s_tail + 4))
        for j in range(3):
            star(fr, x0 + (j - 1) * 6, y0 - j * 3, 2, 0.9, 1.0)
    if gone > 0:                                                               # sparkles where it breaks up
        for s0 in np.arange(s_tail + 6, s_neck, 14.0):
            x0, y0, _ = (float(v) for v in path_at(s0))
            j = int(s0)
            star(fr, x0 + (NOISE[j % H, (j * 5) % W] - 0.5) * 18, y0 + (NOISE[(j * 11) % H, j % W] - 0.5) * 18,
                 2 if (j // 14 + f) % 3 == 0 else 1, 0.9 * (1 - gone), 1.0)


def draw_strike(fr, f):
    if f < STRIKE0:
        return
    tt = f - IMP
    if f < IMP:
        sh = s_head(f)
        for d in (6, 14, 22):                                                # speed lines by the head
            x0, y0, a0 = (float(v) for v in path_at(sh - d))
            x1, y1, _ = (float(v) for v in path_at(max(sh - d - 26, 0)))
            nx, ny = -math.sin(a0), math.cos(a0)
            for side in (-1, 1):
                o = side * (18 + d * 0.6)
                pts = line_pts((x1 + nx * o, y1 + ny * o), (x0 + nx * o, y0 + ny * o))
                fr.over(pts[:, 0], pts[:, 1], hexf(THREAD[1]), np.linspace(0.0, 0.55, len(pts)))
        return
    x, y = PI
    if tt <= 1:                                                              # peak: flash disc
        R = 16 + 4 * tt
        d = np.hypot(XX - x, (YY - y) / 0.6)
        m = (d <= R) & (YY <= y + 3)
        fr.over(YY[m].astype(int), XX[m].astype(int), hexf("#ffffff"), 1.0)
        m2 = (d > R) & (d <= R + 2) & (YY <= y + 3)
        fr.over(YY[m2].astype(int), XX[m2].astype(int), hexf(HEAD[3]), 0.9)
        cs.glow(fr.Lg, x, y - 6, 26, 0.75)
    s = clamp01(tt / 11)
    if tt <= 11:                                                             # shock ring
        R = 10 + 52 * (1 - (1 - s) ** 2)
        cs.ellipse_line(fr.over, x, y, R, R * 0.3, HEAD[4] if tt < 4 else HEAD[3], 0.9 * (1 - s))
        cs.ellipse_line(fr.over, x, y, R - 3, (R - 3) * 0.3, HEAD[2], 0.5 * (1 - s))
        cs.glow_ring(fr.Lg, x, y, R, 5, 0.26 * (1 - s), flat=0.3)
    if tt <= 7:                                                              # streaks
        for a, ln in STREAKS:
            r1 = ln * ease_out(tt / 3)
            r0 = ln * ease_io(tt / 7)
            if r1 - r0 < 1:
                continue
            ux, uy = math.cos(a), math.sin(a) * 0.8
            p0 = (x + ux * (r0 + 8), y + uy * (r0 + 8))
            p1 = (x + ux * (r1 + 8), y + uy * (r1 + 8))
            pts = line_pts(p0, p1)
            fr.over(pts[:, 0], pts[:, 1], hexf("#ffffff" if tt < 3 else HEAD[4]), np.linspace(0.3, 1.0, len(pts)))
            cs.glow_line(fr.Lg, p0, p1, 3, 0.15 * (1 - tt / 8))
    if 0 <= tt < 4:
        cs.glow(fr.Lg, x, y, 70, 0.4 * (1 - tt / 4) + 0.12, flat=0.4)          # scene pool on the peak
    for k, (a, v, life) in enumerate(EMB):                                     # embers
        if tt < 1:
            continue
        t = tt - 1
        ll = 1 - t / (26 * life)
        if ll <= 0:
            continue
        ex = x + math.cos(a) * v * t * 1.2
        ey = y - 3 + math.sin(a) * v * t * 0.9 + 0.18 * t * t
        if ey > GROUND + 1 or not (8 < ex < W - 8 and ey > 8):
            continue
        col = HEAD[5] if ll > 0.8 else HEAD[4] if ll > 0.5 else HEAD[3] if ll > 0.25 else HEAD[2]
        fr.px(ex, ey, hexf(col), min(1.0, ll * 1.6))
        if ll > 0.6 and k % 3 == 0:
            fr.px(ex + 1, ey, hexf(HEAD[3]), ll * 0.8)
        cs.glow(fr.Lg, ex, ey, 4, 0.32 * ll)
    if tt >= 1:                                                                # dust
        t = tt - 1
        for dx, r0, ph in PUFFS:
            fa = clamp01(1 - t / (22 + ph * 2)) * clamp01(t / 2)
            if fa <= 0:
                continue
            r = r0 + 11 * ease_out(t / 16)
            cx = x + dx * (0.4 + 0.6 * ease_out(t / 10))
            cy = y - 2 - r * 0.4 - t * 0.35
            d = np.hypot(XX - cx, (YY - cy) / 0.75) / r
            m = d <= 1
            if not m.any():
                continue
            ys, xs = np.nonzero(m)
            dd = d[m]
            top = (YY[m] - cy) < -r * 0.35
            colr = np.where(top[:, None], hexf(DUST[2]), np.where((dd > 0.7)[:, None], hexf(DUST[0]), hexf(DUST[1])))
            fr.over(ys, xs, colr, 0.5 * fa * (1 - dd ** 3))
            cs.glow(fr.Lg, cx, cy - r * 0.3, r * 1.6, 0.05 * fa)
        cs.glow_line(fr.Lg, (x - 48, y), (x + 48, y), 7, 0.22 * clamp01(1 - t / 24))   # scorched ground glow
        cs.glow(fr.Lg, x, y - 10, 64, 0.12 * clamp01(1 - t / 24), flat=0.5)
        cs.glow(fr.Lg, x - 40, y - 70, 130, 0.12 * clamp01(1 - t / 30), flat=0.7)
    if tt >= 2:                                                                # star glints rising from the blow
        for i in range(0, NS, 2):
            t = tt - 2 - (i % 6)
            if t < 0:
                continue
            ll = clamp01(1 - t / 22) * clamp01(t / 2 + 0.5)
            p = to_world(transform(IMP), STARS[i])
            gx = min(max(x + (p[0] - x) * 1.1, 24), W - 26) + math.sin(t * 0.3 + i) * 2
            gy = max(p[1] - 10 - t * 1.1, 20)
            star(fr, gx, gy, 2 if (t + i) % 4 < 1 else 1, ll, 1.0)


def draw_caster(fr, f):
    foot = foot_at(f)
    sc = 0.44
    pf = foot_at(f - 1)
    speed = math.hypot(foot[0] - pf[0], foot[1] - pf[1])
    lift = clamp01(0.25 + speed / 5 + (0.5 if f >= IMP else 0) * clamp01(1 - (f - IMP) / 14))
    flut = clamp01(0.35 + speed / 6 + (0.5 if IMP <= f < IMP + 10 else 0) + (0.3 if STRIKE0 <= f < IMP else 0))
    jab = 4 * clamp01(1 - abs(f - IMP) / 4)
    pose = cs.pose_at(f, [(0, "chest"), (18, "chest"), (30, "raise"), (84, "raise"), (100, "chest"),
                          (STRIKE0 - 6, "pull"), (STRIKE0, "pull"), (STRIKE0 + 3, "point")],
                      [(0, "rest"), (14, "out"), (STRIKE0, "out"), (STRIKE0 + 3, "behind")],
                      cs.aim_from(foot, sc, PI), jab)
    g = cs.draw(fr.over, (H, W), foot, sc, pose, f, lift, flut, hair="loose")
    charge = clamp01(f / RISE_N) if f < PULL0 else 0.6
    cs.glow_line(fr.Lg, g["feet"], g["head"], 7, 0.1)
    cs.glow_line(fr.Lg, g["feet"], g["head"], 20, 0.06)
    cs.glow(fr.Lg, *g["head"], 6, 0.12)
    cs.glow(fr.Lg, *g["hip"], 42, 0.1 * (0.4 + 0.6 * charge))
    point = 1.0 if (30 <= f < 100 or STRIKE0 + 2 <= f < DISS0) else 0.3
    cs.finger_light(fr.Lg, g, point, jab)
    if point > 0.5:
        fr.px(g["finger"][0], g["finger"][1], hexf("#ffffff"), 1.0)
    if f < GATHER0:                                                            # gold motes spiralling up
        for ph, rr, d in MOTES:
            t = (f - d) / 20
            if not 0 <= t <= 1:
                continue
            mx = foot[0] + math.cos(ph + t * 7) * rr
            my = foot[1] - 8 - t * 50
            fr.px(mx, my, hexf(HEAD[4]), 1 - t)
            cs.glow(fr.Lg, mx, my, 4, 0.3 * (1 - t))


def moore(m):
    """Outer boundary of the blob holding the top-left-most pixel, clockwise, as (x, y) pixels."""
    ys, xs = np.nonzero(m)
    i = np.lexsort((xs, ys))[0]
    x0, y0 = int(xs[i]), int(ys[i])
    D = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    out, x, y, d, first = [(x0, y0)], x0, y0, 0, None
    for _ in range(100000):
        for k in range(8):
            nd = (d + 6 + k) % 8
            nx, ny = x + D[nd][0], y + D[nd][1]
            if m[ny, nx]:
                break
        if (x, y) == (x0, y0):
            if first is None:
                first = nd
            elif nd == first:
                break
        x, y, d = nx, ny, nd
        out.append((x, y))
    return np.array(out[:-1], float)


def rdp(P, eps):
    keep = np.zeros(len(P), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(P) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = P[i], P[j]
        ab = b - a
        ln = np.hypot(*ab) or 1e-9
        seg = P[i + 1:j]
        d = np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / ln
        k = int(np.argmax(d))
        if d[k] > eps:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return keep


def build_constellation():
    """Trace the solid head's outline (mouth open) and keep about STAR_TARGET corners as the stars; PENS pens
    draw the threads round the loop at once."""
    global STARS, EDGES, FLARE, NS, SKY, CLOUD, DELAY, TW
    tm, sy, sx = draw_head(Frame(), HOLD0, HEAD_A0, trace=True)
    P = moore(np.pad(tm, 1)) - 1 + [sx.start, sy.start]
    far = int(np.argmax(np.hypot(*(P - P[0]).T)))
    lo, hi = 0.2, 20.0
    for _ in range(30):
        eps = (lo + hi) / 2
        k1, k2 = rdp(P[:far + 1], eps), rdp(np.vstack([P[far:], P[:1]]), eps)
        n = k1.sum() + k2.sum() - 2
        lo, hi = (eps, hi) if n > STAR_TARGET else (lo, eps)
    pts = np.vstack([P[:far + 1][k1][:-1], np.vstack([P[far:], P[:1]])[k2][:-1]])
    ax, ay, ang, S = HEAD_A0
    STARS = [((x - ax) / S, (y - ay) / S) for x, y in pts]
    NS = len(STARS)
    per = math.ceil(NS / PENS)
    EDGES, FLARE = [], {}
    for k in range(NS):
        pen, j = divmod(k, per)
        t0 = LINK0 + pen * PEN_GAP + j * EDGE_GAP
        EDGES.append((k, (k + 1) % NS, t0))
        for s_ in (k, (k + 1) % NS):
            FLARE[s_] = min(FLARE.get(s_, 1e9), t0)
    rng = np.random.default_rng(11)
    SKY = np.stack([rng.uniform(16, W - 16, NS), rng.uniform(10, 50, NS)], 1)
    CLOUD = rng.normal(0, 16, (NS, 2))
    DELAY = rng.uniform(0, 8, NS)
    TW = rng.uniform(0, 6.28, NS)


build_constellation()


def render(f):
    fr = Frame()
    tr = transform(f)
    if GATHER0 <= f < STRIKE0 + 4:                                             # scene pool round the head
        k = (0.08 + 0.08 * clamp01((f - LINK0) / LINK_N)) * (1 - clamp01((f - STRIKE0) / 4))
        cs.glow(fr.Lg, HEAD_A0[0] + 10, HEAD_A0[1] - 4, 160, k, flat=0.8)
    if PULL0 - 4 <= f < LINK0 + 6:
        cs.glow(fr.Lc, W / 2, 56 + 70 * clamp01((f - PULL0) / (PULL_N + GATHER_N)), 170,
                0.13 * clamp01((f - PULL0 + 4) / 8) * (1 - clamp01((f - LINK0) / 6)), flat=0.45)
    draw_stars(fr, f, tr)
    if f >= STRIKE0:
        brk = None
        if f > IMP + 1:
            brk = (S_END - NECK - BODY_L) + BODY_L * ease_io((f - IMP - 1) / 22)
        draw_body(fr, f, s_head(f), brk, ease_io((f - IMP - 1) / 16))
    if FORM0 <= f < IMP + 8:
        fill = ease_io((f - FORM0 + 1) / FILL_N) if f < HOLD0 else None
        whiten = 0.5 if IMP - 1 <= f <= IMP + 1 else 0.0
        shatter = clamp01((f - IMP - 1) / 7)
        draw_head(fr, f, tr, fill=fill, whiten=whiten, shatter=shatter)
    draw_threads(fr, f, tr)
    draw_strike(fr, f)
    draw_caster(fr, f)
    rgba = (np.clip(np.concatenate([fr.col, fr.a[..., None]], -1), 0, 1) * 255).round().astype(np.uint8)
    light = pfx.tint(np.repeat(np.clip(fr.Lg, 0, 1)[..., None], 3, -1), GOLD_RAMP) \
        + pfx.tint(np.repeat(np.clip(fr.Lc, 0, 1)[..., None], 3, -1), COOL_RAMP)
    return rgba, np.clip(light, 0, 1), fr.Lg + fr.Lc


def grid(frames, cols):
    rows = math.ceil(len(frames) / cols)
    h, w = frames[0].shape[:2]
    out = np.zeros((rows * h, cols * w, frames[0].shape[2]), frames[0].dtype)
    for i, fr in enumerate(frames):
        out[(i // cols) * h:(i // cols + 1) * h, (i % cols) * w:(i % cols + 1) * w] = fr
    return out


def main():
    from PIL import Image
    OUT.mkdir(exist_ok=True)
    colors, lights, finals, bad, covers, means = [], [], [], [], [], []
    for f in range(N):
        rgba, light, L = render(f)
        final = pfx.composite(rgba, light)
        colors.append(rgba)
        lights.append(light)
        finals.append(final)
        a = rgba[..., 3]
        edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
        le = np.concatenate([L[0], L[-1], L[:, 0], L[:, -1]])
        if not a.any():
            bad.append(f"frame {f}: empty colour")
        elif edge.any() or (le > 0.02).any():
            bad.append(f"frame {f}: touches the cell edge (colour {int(edge.any())}, light {int((le > 0.02).any())})")
        ys, xs = np.nonzero(a)
        if len(ys):
            box_ = np.clip(L[ys.min():ys.max() + 1, xs.min():xs.max() + 1], 0, 1)
            covers.append((box_ > 0.03).mean())
            means.append(box_[box_ > 0.03].mean() if (box_ > 0.03).any() else 0.0)

    cols = 14
    Image.fromarray(grid(finals, cols), "RGBA").save(OUT / f"{NAME}.png")
    Image.fromarray(grid(colors, cols), "RGBA").save(OUT / f"{NAME}_color.png")
    lt = (np.stack(lights) * 255).round().astype(np.uint8)
    Image.fromarray(grid(list(lt), cols), "RGB").save(OUT / f"{NAME}_light.png")
    pfx.strip(finals, OUT / f"{NAME}_strip_1x.png")
    keys = sorted(set(list(range(0, N, 8)) + [HOLD0, STRIKE0 + 5, STRIKE0 + 11, IMP - 2, IMP, IMP + 1, N - 1]))
    for bg, tag in (("#101018", "dark"), ("#4a5a6a", "mid")):
        cells = [pfx.composite(colors[k], lights[k], bg) for k in keys]
        img = Image.fromarray(grid(cells, 7)[..., :3])
        img.resize((img.width * 4, img.height * 4), Image.NEAREST).save(OUT / f"{NAME}_4x_{tag}.png")
    pfx.gif(finals, OUT / f"{NAME}.gif", FPS, scale=4)
    pfx.gif(finals, OUT / f"{NAME}_2x.gif", FPS, scale=2)
    meta = dict(name=NAME, w=W, h=H, frames=N, fps=FPS, columns=cols, pivot=[int(PI[0]), int(PI[1])], loop=False,
                glow="medium", glow_body="strong", light_gain=1.0, light_sheet=f"{NAME}_light.png", color_sheet=f"{NAME}_color.png",
                states=STATES, impact_frame=IMP, stars=NS, threads=len(EDGES))
    (OUT / f"{NAME}.json").write_text(json.dumps(meta, indent=1))

    print(f"frames {N} at {FPS} fps ({N / FPS:.2f} s), impact {IMP}, stars {NS}, threads {len(EDGES)}")
    print(f"light: cover {np.median(covers):.0%} mean {np.median(means):.3f} (medium: 50-80 %, 0.08-0.12)")
    for s, (a, b) in STATES.items():
        print(f"  {s:9s} {a:3d}-{b:3d}  cover {np.median(covers[a:b + 1]):.0%}  mean {np.median(means[a:b + 1]):.3f}")
    if bad:
        print("FAIL\n" + "\n".join(bad[:20]))
        sys.exit(1)
    print("check ok")


if __name__ == "__main__":
    main()
