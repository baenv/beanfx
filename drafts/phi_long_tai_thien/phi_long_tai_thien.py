"""Phi Long Tai Thien (Eighteen Dragon-Subduing Palms, second palm, "the flying dragon is in the sky"): a golden
caster thrusts a palm up, a gold qi dragon leaves it and climbs in an arc over the caster, who leaps after it; the
dragon turns over at the top, dives head first onto the target and leaves a palm-print crater blast.
General mode, side view facing east (mirror True), 256x192, 60 frames at 24 fps, one-shot, glow medium (gold).

States (frames, 24 fps):
    windup    0-6    0.30 s  palm charges, qi motes gather
    rise      7-25   0.80 s  dragon leaves the palm and climbs the arc, caster leaps to the hover
    turn      26-32  0.30 s  dragon rolls over the apex, caster hangs and pulls the palm back
    dive      33-40  0.35 s  dragon dives, caster pushes the palm down, palm-wind streaks
    hit       41-42  0.10 s  white flash, shockwave ring, crater
    dissolve  43-59  0.70 s  shards, sparks and dust roll out, dragon pours into the crater and breaks up,
                             caster lands
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent / "kit"))
import caster as cs  # noqa: E402
import facing as fc  # noqa: E402
import pfx  # noqa: E402

NAME = "phi_long_tai_thien"
W, H, N, FPS = 256, 192, 60, 24
GY = 168.0                            # ground line
GROUND = (36.0, GY)                   # pivot: the caster's feet
HOVER = (102.0, 108.0)
LAND = (110.0, GY)
T = (184.0, GY)                       # target: where the snout hits
SC = 0.44                             # caster about 34 px tall

WIND0, RISE0, TURN0, DIVE0, HIT0, DIS0 = 0, 7, 26, 33, 41, 43
STATES = dict(windup=[WIND0, RISE0 - 1], rise=[RISE0, TURN0 - 1], turn=[TURN0, DIVE0 - 1],
              dive=[DIVE0, HIT0 - 1], hit=[HIT0, DIS0 - 1], dissolve=[DIS0, N - 1])

GOLD = ["#3a1a08", "#8a4a10", "#d89a20", "#ffd860", "#fff6d0"]    # 0 rim, 1 shadow, 2 mid, 3 lit, 4 hot
EARTH = ["#241a16", "#46362c", "#6e5a48", "#9c8468"]              # crater and rock: rim, shadow, mid, lit
SMOKE = ["#4a3e38", "#76665a", "#a4927e"]
LIGHT_RAMP = ["#5a2a08", "#e0a020", "#ffe8a0", "#ffffff"]
OUT = Path(__file__).parent / "out"

LB = 150.0                            # dragon length, snout tip to tail tip
HS = 1.3                              # head scale: local head units to px
NECK = 17.0 * HS                      # where the body starts behind the tip
TAU = math.tau

YY, XX = np.mgrid[0:H, 0:W].astype(float)
NOISE = np.random.default_rng(5).random((H, W))


def hexf(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


GOLD_RGB = np.stack([hexf(c) for c in GOLD])
EARTH_RGB = np.stack([hexf(c) for c in EARTH])
SMOKE_RGB = np.stack([hexf(c) for c in SMOKE])


def ease_io(s):
    s = np.clip(s, 0, 1)
    return s * s * (3 - 2 * s)


def ease_out(s):
    s = min(max(s, 0.0), 1.0)
    return 1 - (1 - s) ** 2


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _win(x0, x1, y0, y1, w=W, h=H):
    xa, xb = max(int(x0), 0), min(int(x1) + 2, w)
    ya, yb = max(int(y0), 0), min(int(y1) + 2, h)
    return slice(ya, max(yb, ya)), slice(xa, max(xb, xa))


# ---- frame: colour by over, light summed in L ----
class Frame:
    def __init__(self, w=W, h=H):
        self.w, self.h = w, h
        self.rgb = np.zeros((h, w, 3))
        self.a = np.zeros((h, w))
        self.L = np.zeros((h, w))

    def over(self, ys, xs, rgb, a):
        ok = (ys >= 0) & (ys < self.h) & (xs >= 0) & (xs < self.w)
        a = np.broadcast_to(np.asarray(a, float), ok.shape)[ok]
        rgb = np.broadcast_to(np.asarray(rgb, float), (*ok.shape, 3))[ok]
        ys, xs = ys[ok], xs[ok]
        a0 = self.a[ys, xs]
        na = a + a0 * (1 - a)
        self.rgb[ys, xs] = (rgb * a[:, None] + self.rgb[ys, xs] * (a0 * (1 - a))[:, None]) / np.maximum(na, 1e-6)[:, None]
        self.a[ys, xs] = na

    def dot(self, x, y, col, a=1.0):
        self.over(np.array([int(round(y))]), np.array([int(round(x))]), np.asarray(col, float), a)

    def rgba(self):
        return np.dstack([self.rgb, self.a])


def null_over(ys, xs, rgb, a):
    pass


def line(fr, p0, p1, c0, c1, a0, a1):
    n = int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))) + 1
    t = np.linspace(0, 1, n)
    xs = np.round(p0[0] + (p1[0] - p0[0]) * t).astype(int)
    ys = np.round(p0[1] + (p1[1] - p0[1]) * t).astype(int)
    rgb = c0[None] * (1 - t[:, None]) + c1[None] * t[:, None]
    fr.over(ys, xs, rgb, a0 + (a1 - a0) * t)


def ellipse(fr, cx, cy, rx, ry, rgb, a, dash=None, phase=0.0):
    n = max(int(TAU * max(rx, 1) * 1.6), 12)
    th = np.linspace(0, TAU, n, endpoint=False)
    if dash:
        th = th[np.sin(th * dash + phase) > -0.3]
    pts = np.unique(np.stack([np.round(cy + ry * np.sin(th)), np.round(cx + rx * np.cos(th))], 1).astype(int), axis=0)
    fr.over(pts[:, 0], pts[:, 1], rgb, a)


# ---- the arc: a cubic from the palm over the caster down onto the target, then straight into the ground ----
A = (42.0, 132.0)
C1, C2 = (46.0, 4.0), (160.0, 4.0)
B = (T[0], T[1] - 2.0)


def _build_path():
    t = np.linspace(0, 1, 3000)[:, None]
    p = ((1 - t) ** 3 * np.array(A) + 3 * (1 - t) ** 2 * t * np.array(C1) + 3 * (1 - t) * t * t * np.array(C2)
         + t ** 3 * np.array(B))
    end = (np.array(B) - np.array(C2))
    end /= np.linalg.norm(end)
    ext = np.array(B) + np.linspace(0, 200, 400)[1:, None] * end
    p = np.concatenate([p, ext])
    s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
    return p, s


PATH, PS = _build_path()
S_B = float(np.interp(1.0, np.linspace(0, 1, 3000), PS[:3000]))
S_TOP = float(PS[np.argmin(PATH[:3000, 1])])


def path_at(s, path=PATH, ps=PS):
    s = np.clip(s, 0, ps[-1] - 1)
    x = np.interp(s, ps, path[:, 0])
    y = np.interp(s, ps, path[:, 1])
    x2 = np.interp(s + 1.0, ps, path[:, 0])
    y2 = np.interp(s + 1.0, ps, path[:, 1])
    d = math.hypot(x2 - x, y2 - y) or 1
    return x, y, (x2 - x) / d, (y2 - y) / d


def tip_at(f):
    """Arc length of the snout tip, or None before the release."""
    if f < RISE0:
        return None
    if f < TURN0:
        return 14 + (0.9 * S_TOP - 14) * ease_out((f - RISE0) / (TURN0 - RISE0))
    if f < DIVE0:
        return 0.9 * S_TOP + 0.25 * S_TOP * (f - TURN0) / (DIVE0 - TURN0)
    if f < HIT0:
        return 1.15 * S_TOP + (S_B - 1.15 * S_TOP) * ((f - DIVE0) / (HIT0 - DIVE0)) ** 1.7
    return S_B + 150 * ease_out((f - HIT0) / 13)


# ---- the dragon ----
LDIR = np.array([-0.55, -0.65, 0.75])
LDIR /= np.linalg.norm(LDIR)


def radius(q):
    """Body half width from the neck (q 0) to the tail (q 1): a slim neck, a full chest, a long taper."""
    return 1.3 + 5.4 * (1 - q) ** 0.85 * (0.86 + 0.14 * min(1.0, q * 8))


def dragon(fr, f, tip, path_fn, alpha=1.0, brk=0.0, clip_y=None, jaw=0.0, light=1.0):
    """Draw the dragon with its snout tip at arc length `tip` along path_fn(s) -> (x, y, tx, ty).
    Returns the body samples (x, y, r) from neck to tail for the light and sparks."""
    shape = (fr.h, fr.w)
    X, Y = cs._grid(shape)
    tone = np.full(shape, -1)

    def put(m, base, sy=slice(None), sx=slice(None)):
        if m.any():
            t = cs.shade(m, base)
            sub = tone[sy, sx]
            sub[m] = t[m]

    # samples from the neck back
    samp = []
    u = NECK
    while u <= LB:
        s = tip - u
        if s < 0:
            break
        x, y, tx, ty = path_fn(s)
        q = (u - NECK) / (LB - NECK)
        wv = 4.2 * min(1.0, q * 3.5) * (1 - 0.35 * q) * math.sin(u * TAU / 50 - f * 0.8)
        nx, ny = ty, -tx
        samp.append([x + nx * wv, y + ny * wv, radius(q), u, q])
        u += 1.0
    attached = tip - LB < 0
    samp = np.array(samp) if samp else np.zeros((0, 5))

    # tangents from the waved centre line (toward the head)
    tang = np.zeros((len(samp), 2))
    if len(samp) > 1:
        d = np.zeros((len(samp), 2))
        d[1:-1] = samp[:-2, :2] - samp[2:, :2]
        d[0] = samp[0, :2] - samp[1, :2]
        d[-1] = samp[-2, :2] - samp[-1, :2]
        tang = d / np.maximum(np.hypot(*d.T)[:, None], 1e-6)
    elif len(samp) == 1:
        tang[0] = path_fn(tip - NECK)[2:]

    # fins, legs and the tail tuft go under the body
    for i in range(len(samp)):
        x, y, r, uu, q = samp[i]
        tx, ty = tang[i]
        nx, ny = ty, -tx
        if 22 <= uu <= LB - 14 and int(uu) % 6 == 0:
            h = 3.6 * (1 - 0.55 * q) + 0.6
            a_ = (x + nx * r * 0.7 + tx * 2.4, y + ny * r * 0.7 + ty * 2.4)
            b_ = (x + nx * r * 0.7 - tx * 2.0, y + ny * r * 0.7 - ty * 2.0)
            c_ = (x + nx * (r + h) - tx * 3.2, y + ny * (r + h) - ty * 3.2)
            sy, sx = _win(x - 14, x + 14, y - 14, y + 14, fr.w, fr.h)
            put(cs.tri(X[sy, sx], Y[sy, sx], a_, b_, c_), 2, sy, sx)
        if int(uu) in (34, 92):
            # a leg on the belly side, bent back, with three claws
            k0 = (x - nx * r * 0.4, y - ny * r * 0.4)
            knee = (x - nx * (r + 3.5) - tx * 1.5, y - ny * (r + 3.5) - ty * 1.5)
            paw = (knee[0] - nx * 2.5 - tx * 4.0, knee[1] - ny * 2.5 - ty * 4.0)
            sy, sx = _win(x - 16, x + 16, y - 16, y + 16, fr.w, fr.h)
            lx, ly = X[sy, sx], Y[sy, sx]
            m = (cs.seg_d(lx, ly, k0, knee) <= 1.7) | (cs.seg_d(lx, ly, knee, paw) <= 1.3)
            put(m, 2, sy, sx)
            for c in (-0.6, 0.0, 0.6):
                ca = math.atan2(-ny, -nx) + c - 0.6 * math.copysign(1, 1)
                tipc = (paw[0] + math.cos(ca) * 3.0 - tx * 1.2, paw[1] + math.sin(ca) * 3.0 - ty * 1.2)
                put(cs.seg_d(lx, ly, paw, tipc) <= 0.6, 3, sy, sx)
    if len(samp) and not attached:
        x, y, r, uu, q = samp[-1]
        tx, ty = tang[-1]
        sy, sx = _win(x - 16, x + 16, y - 16, y + 16, fr.w, fr.h)
        lx, ly = X[sy, sx], Y[sy, sx]
        back = math.atan2(-ty, -tx)
        for j, (da, ln) in enumerate(((-0.5, 11), (0.0, 14), (0.5, 10))):
            m, _ = cs.strand(lx, ly, (x, y), back + da, back + da * 1.5 + 0.4 * math.sin(f * 0.6 + j),
                             ln, 2.0, 0.5, lambda k, j=j: 0.25 * math.sin(k * 0.8 - f * 0.7 + j), n=8, mw=0.55)
            put(m, 2 if j == 1 else 1, sy, sx)

    # the body: nearest sample per pixel, shaded as a cylinder lit from the top left (fixed in the world)
    D = np.full(shape, np.inf)
    V = np.zeros(shape)
    U = np.zeros(shape)
    NX = np.zeros(shape)
    NY = np.zeros(shape)
    for i in range(len(samp)):
        x, y, r, uu, q = samp[i]
        tx, ty = tang[i]
        sy, sx = _win(x - r - 1, x + r + 1, y - r - 1, y + r + 1, fr.w, fr.h)
        dx, dy = X[sy, sx] - x, Y[sy, sx] - y
        g = np.hypot(dx, dy) / r
        upd = g < D[sy, sx]
        nx, ny = ty, -tx
        D[sy, sx] = np.where(upd, g, D[sy, sx])
        V[sy, sx] = np.where(upd, np.clip((dx * nx + dy * ny) / r, -1, 1), V[sy, sx])
        U[sy, sx] = np.where(upd, uu, U[sy, sx])
        NX[sy, sx] = np.where(upd, nx, NX[sy, sx])
        NY[sy, sx] = np.where(upd, ny, NY[sy, sx])
    body = D <= 1.0
    if body.any():
        v = V
        b = NX * v * LDIR[0] + NY * v * LDIR[1] + np.sqrt(np.clip(1 - v * v, 0, 1)) * LDIR[2]
        bt = np.select([b > 0.96, b > 0.82, b > 0.55, b > 0.15], [4, 3, 2, 1], 0)
        belly = v < -0.42
        bt = np.where(belly, np.where(b > 0.6, 3, np.where(b > 0.2, 2, 1)), bt)
        plate = belly & ((U % 3.2) < 1.0)
        bt = np.where(plate, bt - 1, bt)
        chev = ~belly & (((U + 3.6 * np.abs(v)) % 5.0) < 1.0) & (bt >= 2)
        bt = np.where(chev, bt - 1, bt)
        bt = np.where((D > 0.75) & (b < 0.6), 0, bt)
        tone[body] = bt[body]

    # the head, rigid along the tangent at the tip
    hx, hy, tx, ty = path_fn(tip)
    nx, ny = ty, -tx
    sy, sx = _win(hx - 60, hx + 60, hy - 60, hy + 60, fr.w, fr.h)
    dx, dy = X[sy, sx] - hx, Y[sy, sx] - hy
    ap = (dx * tx + dy * ty) / HS + 24.0           # 0 at the back of the skull, 24 at the snout tip
    bb = (dx * nx + dy * ny) / HS                  # up, away from the arc's inside
    mw = 0.55 / HS

    def segs(pts, w0, w1):
        m = np.zeros(ap.shape, bool)
        n = len(pts) - 1
        for k in range(n):
            w = w0 + (w1 - w0) * k / max(n - 1, 1)
            m |= cs.seg_d(ap, bb, pts[k], pts[k + 1]) <= w
        return m

    put(segs([(7, 5), (1, 9), (-6, 10.5), (-10, 10)], 1.4, 0.7), 1, sy, sx)          # far horn
    for j, b0 in enumerate((4.5, 2.2, 0.0, -2.2, -4.2)):                             # flame mane
        a0 = math.pi - b0 * 0.09
        m, _ = cs.strand(ap, bb, (2.0, b0), a0, a0 - b0 * 0.05 + 0.25 * math.sin(f * 0.5 + j),
                         10 + (j * 7) % 5, 2.4, 0.5, lambda k, j=j: 0.3 * math.sin(k * 0.9 - f * 0.8 + j * 1.3),
                         n=8, mw=mw)
        put(m, 1 if j % 2 == 0 else 0, sy, sx)
    m, _ = cs.strand(ap, bb, (8, -4), math.pi + 0.7, math.pi + 0.4, 8, 1.5, 0.4,
                     lambda k: 0.2 * math.sin(k - f * 0.7), n=6, mw=mw)                 # beard
    put(m, 1, sy, sx)
    skull = ((ap - 7) / 8.0) ** 2 + ((bb - 1) / 6.3) ** 2 <= 1
    snout = ((ap >= 7) & (ap <= 21.5) & (bb <= 4.2 - (ap - 7) * 0.13) & (bb >= -0.8 - (ap - 7) * 0.02)) | \
            (((ap - 21.5) / 2.3) ** 2 + ((bb - 1.4) / 2.6) ** 2 <= 1)
    ang = 0.15 + 0.5 * jaw
    hinge = (6.0, -1.5)
    jend = (hinge[0] + 14 * math.cos(-ang), hinge[1] + 14 * math.sin(-ang))
    jawm = cs.seg_d(ap, bb, hinge, jend) <= 1.8
    mouth = cs.tri(ap, bb, (hinge[0] + 2, hinge[1] + 0.3), (22.0, -0.6), jend) & ~snout & ~jawm
    put(jawm, 1, sy, sx)
    put(skull | snout, 2, sy, sx)
    sub = tone[sy, sx]
    hm = (skull | snout) & (sub >= 0)
    sub[hm & (bb > 2.6) & (sub == 2)] = 3                                                 # lit crown and bridge
    sub[hm & (bb < -0.2) & (sub >= 2)] = 1                                                # under the cheek
    sub[mouth] = 0
    sub[snout & (bb < -0.2) & ((ap % 3.0) < 1.0) & (ap > 11) & (ap < 21)] = 4               # teeth
    sub[cs.seg_d(ap, bb, (9.5, 4.8), (15.0, 5.3)) <= 0.8] = 1                             # brow
    sub[np.hypot(ap - 21.6, bb - 3.0) <= 0.8] = 0                                          # nostril
    put(segs([(5, 5.5), (-3, 11), (-12, 14.5), (-19, 14.5)], 1.7, 0.8)
        | (cs.seg_d(ap, bb, (-3, 11), (-5, 17)) <= 0.8), 4, sy, sx)                        # near horn
    for j, (s0, a0, a1) in enumerate((((20, 2.0), 1.3, 2.8),
                                      ((18, -1.0), -2.0, -2.9))):              # whiskers
        m, _ = cs.strand(ap, bb, s0, a0, a1, 17, 0.6, 0.4,
                         lambda k, j=j: 0.35 * math.sin(k * 0.5 - f * 0.6 + j * 2), n=12, mw=mw)
        sub = tone[sy, sx]
        sub[m & (sub < 0)] = 3
    sub = tone[sy, sx]
    eye = np.hypot(ap - 12.5, bb - 2.6) <= 1.3
    sub[eye] = 4

    if clip_y is not None:
        tone[Y > clip_y] = -1
    if brk > 0:
        gone = NOISE[:fr.h, :fr.w] < brk * (0.5 + 0.7 * np.clip(U / LB, 0, 1))
        tone[gone & (tone >= 0)] = -1
    ys, xs = np.nonzero(tone >= 0)
    fr.over(ys, xs, GOLD_RGB[tone[ys, xs]], alpha)

    # light: a tight core and a pool along the body, the head and its eye
    if light > 0 and len(samp):
        k = light
        step = 7
        for i in range(0, len(samp) - 1, step):
            j = min(i + step, len(samp) - 1)
            p0, p1 = tuple(samp[i, :2]), tuple(samp[j, :2])
            if clip_y is not None and min(p0[1], p1[1]) > clip_y:
                continue
            kk = k * (1 - 0.5 * samp[i, 4])
            cs.glow_line(fr.L, p0, p1, 5, 0.15 * kk)
            cs.glow_line(fr.L, p0, p1, 13, 0.07 * kk)
    if light > 0 and (clip_y is None or hy < clip_y + 6):
        ex, ey = hx - tx * 11.5 * HS + nx * 2.6 * HS, hy - ty * 11.5 * HS + ny * 2.6 * HS
        cs.glow(fr.L, hx - tx * 14, hy - ty * 14, 12, 0.4 * light)
        cs.glow(fr.L, hx - tx * 14, hy - ty * 14, 30, 0.11 * light)
        cs.glow(fr.L, ex, ey, 4, 0.5 * light)
    if attached and light > 0:
        cs.glow(fr.L, *A, 10, 0.35 * light)
    return samp, (hx, hy, tx, ty)


# ---- the caster ----
def foot_at(f):
    if f < 9:
        return GROUND
    if f < 44:
        t = ease_io((f - 9) / 15.0)
        x, y = lerp(GROUND, HOVER, t)
        y -= 10 * math.sin(math.pi * t)
        bob = 1.5 * math.sin((f - 24) * 0.45) * ease_io((f - 22) / 4.0)
        return x, y + bob
    t = ease_io((f - 44) / 13.0)
    return lerp(HOVER, LAND, t)


def caster_light(L, g, charge):
    """cs.body_light with the hip pool sized for this 256 cell (the kit's r 100 is tuned for 640)."""
    cs.glow_line(L, g["feet"], g["head"], 8, 0.12)
    cs.glow_line(L, g["feet"], g["head"], 22, 0.07)
    cs.glow(L, *g["head"], 6, 0.12)
    for pts in g["hair"]:
        for a_, b_ in zip(pts, pts[1:]):
            cs.glow_line(L, a_, b_, 4, 0.06)
    cs.glow(L, *g["hip"], 34, 0.1 * (0.4 + 0.6 * charge), flat=0.85)


def caster_pose(f, foot):
    aim = cs.aim_from(foot, SC, T)
    jab = 4.0 * math.exp(-((f - HIT0) / 2.0) ** 2)
    pose = cs.pose_at(f, [(0, "chest"), (6, "raise"), (24, "raise"), (30, "pull"), (36, "point"), (49, "point"),
                          (58, "rest")],
                      [(0, "rest"), (9, "out"), (50, "out"), (58, "rest")], aim, jab)
    return pose, jab


# ---- the impact ----
rng = np.random.default_rng(23)
SHARDS = [dict(vx=rng.uniform(1.2, 3.6) * s, vy=-rng.uniform(2.8, 5.6), r=rng.uniform(1.4, 3.0),
               rot=rng.uniform(0, TAU), spin=rng.uniform(-0.4, 0.4), d=int(rng.integers(0, 2)))
          for s in [(-1) ** i for i in range(14)]]
SPARKS = [dict(a=rng.uniform(-math.pi * 0.95, -math.pi * 0.05), v=rng.uniform(3.0, 6.5),
               life=int(rng.integers(8, 13)), d=int(rng.integers(0, 2))) for _ in range(10)]
DUST = [dict(s=(-1) ** i, k=rng.uniform(0.45, 1.0), r=rng.uniform(4, 7), d=int(rng.integers(0, 4)))
        for i in range(10)]
CRACKS = [(a, rng.uniform(14, 30)) for a in np.linspace(0, TAU, 7, endpoint=False) + rng.uniform(-0.3, 0.3, 7)]


def crater(fr, f, ox=0.0, oy=0.0):
    age = f - HIT0
    if age < 0:
        return
    cx, cy = T[0] - ox, GY - oy
    k = 1 - 0.6 * ease_io((age - 6) / 12.0)
    X, Y = cs._grid((fr.h, fr.w))
    sy, sx = _win(cx - 30, cx + 30, cy - 8, cy + 8, fr.w, fr.h)
    lx, ly = X[sy, sx] - cx, Y[sy, sx] - cy
    e = np.hypot(lx / 20.0, ly / 4.2)
    tone = np.full(lx.shape, -1)
    tone[e <= 1] = 1
    tone[(e <= 1) & (ly > 0.5)] = 0
    tone[(e > 0.78) & (e <= 1) & (ly < 0)] = 0
    lip = (np.hypot(lx / 23.0, (ly + 0.6) / 5.2) <= 1) & (e > 1)
    tone[lip & (ly < -0.5)] = 3
    tone[lip & (ly >= -0.5)] = 2
    ys, xs = np.nonzero(tone >= 0)
    fr.over(ys + sy.start, xs + sx.start, EARTH_RGB[tone[ys, xs]], 0.95 * k)
    # glowing cracks along the ground, fading
    hot = 1 - ease_io((age - 2) / 14.0)
    if hot > 0.01:
        for a, ln in CRACKS:
            p = (cx, cy)
            pts = [p]
            for j in range(4):
                aa = a + 0.5 * math.sin(j * 2.3 + a * 3)
                p = (p[0] + math.cos(aa) * ln / 4, p[1] + math.sin(aa) * ln / 4 * 0.22)
                pts.append(p)
            for p0, p1 in zip(pts, pts[1:]):
                line(fr, p0, p1, GOLD_RGB[4], GOLD_RGB[2], 0.9 * hot, 0.5 * hot)
                cs.glow_line(fr.L, p0, p1, 4, 0.16 * hot)


def impact(fr, f, ox=0.0, oy=0.0):
    """Flash, ring, shards, sparks and dust round the target; ox, oy shift it into a cropped cell."""
    age = f - HIT0
    if age < 0:
        return
    cx, cy = T[0] - ox, GY - oy
    # white flash disc and light pillar, 2 frames hot
    if age <= 2:
        X, Y = cs._grid((fr.h, fr.w))
        r = 9 + 4 * age
        sy, sx = _win(cx - r, cx + r, cy - r, cy + r, fr.w, fr.h)
        d = np.hypot(X[sy, sx] - cx, (Y[sy, sx] - cy + r * 0.35) / 0.8)
        tone = np.where(d <= r * 0.55, 4, np.where(d <= r * 0.8, 3, np.where(d <= r, 2, -1)))
        tone[Y[sy, sx] > cy + 2] = -1
        ys, xs = np.nonzero(tone >= 0)
        fr.over(ys + sy.start, xs + sx.start, GOLD_RGB[tone[ys, xs]], (1.0, 0.8, 0.4)[age])
    pk = math.exp(-(age / 2.2) ** 2)
    cs.glow(fr.L, cx, cy - 6, 16, 0.75 * pk)
    cs.glow(fr.L, cx, cy - 10, 44, 0.4 * pk, flat=0.7)
    cs.glow_line(fr.L, (cx, cy), (cx - 6, cy - 60), 8, 0.3 * pk)
    # shockwave ring on the ground
    if age <= 11:
        t = ease_out(age / 11.0)
        rx = 8 + 52 * t
        ry = rx * 0.18
        a = 0.9 * (1 - t)
        ellipse(fr, cx, cy, rx, ry, GOLD_RGB[4], a)
        ellipse(fr, cx, cy, rx - 1.5, ry - 0.5, GOLD_RGB[2], a * 0.7)
        cs.glow_ring(fr.L, cx, cy, rx, 5, 0.25 * (1 - t), flat=0.18)
    X, Y = cs._grid((fr.h, fr.w))
    # rock shards: thrown up, fall back, settle and fade
    for i, s in enumerate(SHARDS):
        t = age - s["d"]
        if t < 0:
            continue
        x = cx + s["vx"] * t * (1 - 0.02 * t)
        y = cy - 2 + s["vy"] * t + 0.42 * t * t
        if y > cy - 1:
            tl = (-s["vy"] + math.sqrt(s["vy"] ** 2 + 1.68)) / 0.84    # the frame it lands
            y = cy - 1
            x = cx + s["vx"] * tl * (1 - 0.02 * tl) + s["vx"] * 0.3 * min(t - tl, 3)
        fade = 1 - ease_io((age - 10) / 8.0)
        if fade <= 0.02:
            continue
        rr = s["r"]
        ang = s["rot"] + s["spin"] * t
        sy, sx = _win(x - 5, x + 5, y - 5, y + 5, fr.w, fr.h)
        lx, ly = X[sy, sx] - x, Y[sy, sx] - y
        u = lx * math.cos(ang) + ly * math.sin(ang)
        v = -lx * math.sin(ang) + ly * math.cos(ang)
        m = np.abs(u) / rr + np.abs(v) / (rr * 0.7) <= 1
        tone = np.where(lx + ly < -0.6, 3, np.where(lx + ly > 0.8, 1, 2))
        tone = np.where(np.abs(u) / rr + np.abs(v) / (rr * 0.7) > 0.75, np.minimum(tone, 1), tone)
        ys, xs = np.nonzero(m)
        fr.over(ys + sy.start, xs + sx.start, EARTH_RGB[tone[ys, xs]], fade)
        if t < 5:
            cs.glow(fr.L, x, y, 5, 0.18 * (1 - t / 5))
    # sparks with short trails
    for s in SPARKS:
        t = age - s["d"]
        if t < 0 or t > s["life"]:
            continue
        x = cx + math.cos(s["a"]) * s["v"] * t * 0.8
        y = cy - 4 + math.sin(s["a"]) * s["v"] * t + 0.3 * t * t
        px = cx + math.cos(s["a"]) * s["v"] * max(t - 1.2, 0) * 0.8
        py = cy - 4 + math.sin(s["a"]) * s["v"] * max(t - 1.2, 0) + 0.3 * max(t - 1.2, 0) ** 2
        k = 1 - t / s["life"]
        line(fr, (px, py), (x, y), GOLD_RGB[2], GOLD_RGB[4], 0.3 * k, k)
        cs.glow(fr.L, x, y, 4, 0.45 * k)
        cs.glow(fr.L, x, y, 10, 0.1 * k)
    # dust rolling out both ways, translucent, lit from above
    for s in DUST:
        t = age - s["d"]
        if t < 0:
            continue
        g = ease_out(t / 16.0)
        x = cx + s["s"] * (6 + (44 if s["s"] < 0 else 34) * s["k"] * g)
        y = cy - 2 - 5 * g * s["k"] - 2
        r = s["r"] * (0.5 + 0.8 * g)
        a = 0.42 * (1 - ease_io((t - 4) / 12.0))
        if a <= 0.02:
            continue
        sy, sx = _win(x - r, x + r, y - r, y + r, fr.w, fr.h)
        lx, ly = X[sy, sx] - x, Y[sy, sx] - y
        m = (np.hypot(lx, ly) <= r) & (Y[sy, sx] <= cy + 1)
        ss = lx + ly
        tone = np.where(ss < -r * 0.3, 2, np.where(ss > r * 0.5, 0, 1))
        ys, xs = np.nonzero(m)
        fr.over(ys + sy.start, xs + sx.start, SMOKE_RGB[tone[ys, xs]], a)
        cs.glow(fr.L, x, y - r * 0.4, r * 1.3, 0.05 * a)
    cs.glow(fr.L, cx, cy - 8, 50, (0.1 + 0.22 * pk) * (1 - ease_io((age - 4) / 14.0)), flat=0.55)


# ---- one frame ----
def draw(f, layers=("caster", "charge", "dragon", "impact")):
    fr = Frame()
    foot = foot_at(f)
    pose, jab = caster_pose(f, foot)
    v = foot_at(min(f + 1, N - 1))
    speed = math.hypot(v[0] - foot[0], v[1] - foot[1])
    lift = min(1.0, 0.25 + speed / 5.0) if 9 <= f < 46 else 0.2 + 0.3 * ease_io((f - 3) / 4.0) * (f < 9)
    flut = min(1.0, 0.35 + speed / 4.0)
    over = fr.over if "caster" in layers else null_over
    tip = tip_at(f)

    if "impact" in layers:
        crater(fr, f)

    # charge in the palm, then the release burst where the dragon leaves it
    g = cs.draw(null_over, (H, W), foot, SC, pose, f, lift, flut)
    hand = g["finger"]
    if "charge" in layers:
        c = (0.3 + 0.7 * ease_io(f / 6.0)) * (1 - ease_io((f - RISE0 - 2) / 3.0))
        if c > 0.01:
            for i in range(8):
                a = i * TAU / 8 + f * 0.3
                d = 18 * (1 - ease_io(f / 7.0)) + 3
                p = (hand[0] + math.cos(a) * d, hand[1] + math.sin(a) * d * 0.8)
                fr.dot(*p, GOLD_RGB[4 if i % 2 else 3], 0.9 * c)
                cs.glow(fr.L, *p, 3, 0.3 * c)
            cs.glow(fr.L, *hand, 8, 0.5 * c)
            cs.glow(fr.L, *hand, 22, 0.16 * c)
        rel = f - RISE0
        if 0 <= rel <= 4:
            k = 1 - rel / 5
            ellipse(fr, A[0], A[1], 4 + rel * 3.5, 3 + rel * 2.5, GOLD_RGB[4], 0.8 * k)
            cs.glow_ring(fr.L, A[0], A[1], 4 + rel * 3.5, 4, 0.3 * k, flat=0.75)

    # palm-wind streaks around the dive
    if "dragon" in layers and DIVE0 <= f <= HIT0 and tip is not None:
        hx, hy, tx, ty = path_at(tip)
        nx, ny = ty, -tx
        k = ease_io((f - DIVE0) / 3.0)
        for i, (off, ln, back) in enumerate(((-14, 34, 8), (12, 40, 4), (-22, 24, 16), (20, 28, 14), (-8, 46, 26),
                                             (26, 20, 30))):
            p1 = (hx - tx * back + nx * off, hy - ty * back + ny * off)
            p0 = (p1[0] - tx * ln, p1[1] - ty * ln)
            if p1[1] > GY - 2 or p0[1] < 4:
                continue
            line(fr, p0, p1, GOLD_RGB[2], GOLD_RGB[4], 0.0, 0.55 * k)
            cs.glow_line(fr.L, p0, p1, 4, 0.07 * k)

    if "caster" in layers:
        g = cs.draw(over, (H, W), foot, SC, pose, f, lift, flut, hair="loose")
        caster_light(fr.L, g, 0.6 + 0.4 * ease_io(f / 7.0))
        point = ease_io((f - 34) / 3.0) * (1 - ease_io((f - 50) / 6.0))
        if point > 0.01:
            cs.finger_light(fr.L, g, point, jab * 0.25)
            fr.dot(*g["finger"], hexf("#ffffff"))

    if "dragon" in layers and tip is not None:
        brk = ease_io((f - HIT0 - 1) / 13.0)
        alpha = 1 - 0.4 * brk
        jaw = 0.3 + 0.7 * ease_io((f - 29) / 5.0)
        samp, head = dragon(fr, f, tip, path_at, alpha=alpha, brk=brk, clip_y=GY - 1, jaw=jaw,
                            light=1 - 0.8 * brk)
        # motes rising off the breaking body
        if brk > 0 and len(samp):
            for i in range(14):
                j = int((i * 37) % len(samp))
                x, y = samp[j, 0], samp[j, 1]
                if y > GY - 2:
                    continue
                t = f - DIS0 - (i % 5)
                if t < 0:
                    continue
                k = (1 - t / 14.0) * 0.9
                if k <= 0:
                    continue
                p = (x + math.sin(i * 1.7 + t * 0.3) * 3, y - t * 1.4)
                fr.dot(*p, GOLD_RGB[4 if i % 3 else 3], k)
                cs.glow(fr.L, *p, 4, 0.3 * k)
        # scene pool under the dragon, swelling into the dive
        if len(samp):
            mx, my = samp[:, 0].mean(), samp[:, 1].mean()
            sw = 0.1 + 0.12 * ease_io((f - DIVE0) / 8.0) * (1 - ease_io((f - HIT0 - 2) / 8.0))
            rr = min(72.0, (mx - 3) / 0.75, (W - 3 - mx) / 0.75)
            cs.glow(fr.L, mx, min(my, 120), rr, sw * (1 - brk), flat=0.8)

    if "impact" in layers:
        impact(fr, f)
    return fr


# ---- travel part: the diving dragon on a straight line, a seamless loop the engine moves ----
TW, TH, TN = 100, 188, 8
DIVE_DIR = np.array(B) - np.array(C2)
DIVE_DIR /= np.linalg.norm(DIVE_DIR)
TPIV = (66.0, 176.0)                 # the snout tip
TRAVEL_SPEED = 30.0 * FPS            # px/s, about the dive's mean speed


def draw_travel(f):
    fr = Frame(TW, TH)
    tip_s = LB + 2

    def path_fn(s):
        d = tip_s - s
        return TPIV[0] - DIVE_DIR[0] * d, TPIV[1] - DIVE_DIR[1] * d, DIVE_DIR[0], DIVE_DIR[1]
    ph = f * TAU / TN / 0.8           # the wave phase runs one full cycle per loop
    dragon(fr, ph, tip_s, path_fn, jaw=1.0)
    hx, hy = TPIV
    nx, ny = DIVE_DIR[1], -DIVE_DIR[0]
    for i, (off, ln, back) in enumerate(((-14, 30, 8), (12, 36, 4), (-20, 22, 18), (18, 26, 14))):
        sh = ((f * 7 + i * 11) % 24) - 6
        p1 = (hx - DIVE_DIR[0] * (back + sh) + nx * off, hy - DIVE_DIR[1] * (back + sh) + ny * off)
        p0 = (p1[0] - DIVE_DIR[0] * ln, p1[1] - DIVE_DIR[1] * ln)
        line(fr, p0, p1, GOLD_RGB[2], GOLD_RGB[4], 0.0, 0.5)
        cs.glow_line(fr.L, p0, p1, 4, 0.07)
    return fr


# ---- output ----
def finish(fr):
    col = (np.clip(fr.rgba(), 0, 1) * 255).round().astype(np.uint8)
    Lc = np.clip(fr.L, 0, 1)
    light = pfx.tint(np.repeat(Lc[..., None], 3, -1), LIGHT_RAMP)
    return col, light, Lc


def check(cols, Ls, tag):
    ok = True
    covers, means = [], []
    for f, (col, Lc) in enumerate(zip(cols, Ls)):
        a = col[..., 3] > 0
        if not a.any():
            print(f"{tag} frame {f}: empty colour")
            ok = False
            continue
        edge = np.zeros_like(a)
        edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
        if (a & edge).any() or ((Lc > 0.02) & edge).any():
            print(f"{tag} frame {f}: touches the cell edge")
            ok = False
        ys, xs = np.nonzero(a)
        box = Lc[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        covers.append((box > 0.03).mean())
        means.append(box[box > 0.03].mean() if (box > 0.03).any() else 0)
    return ok, float(np.median(covers)), float(np.median(means))


def crop_box(cols, Ls, pad=3):
    m = np.zeros(cols[0].shape[:2], bool)
    for c, L in zip(cols, Ls):
        m |= (c[..., 3] > 0) | (L > 0.02)
    ys, xs = np.nonzero(m)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, H)
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, W)
    return y0, y1, x0, x1


def grid(frames, path, n=10, scale=1, bg=None):
    h, w = frames[0].shape[:2]
    rows = math.ceil(len(frames) / n)
    img = np.zeros((rows * h, n * w, 4), np.uint8)
    for i, fr_ in enumerate(frames):
        r, c = divmod(i, n)
        img[r * h:(r + 1) * h, c * w:(c + 1) * w] = fr_
    im = Image.fromarray(img, "RGBA")
    if bg:
        base = Image.new("RGBA", im.size, bg)
        base.alpha_composite(im)
        im = base
    if scale != 1:
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    im.save(path)


def main():
    OUT.mkdir(exist_ok=True)
    cols, lights, Ls, comps = [], [], [], []
    for f in range(N):
        col, light, Lc = finish(draw(f))
        cols.append(col)
        lights.append(light)
        Ls.append(Lc)
        comps.append(pfx.composite(col, light))
    ok, cover, mean = check(cols, Ls, "joined")
    print(f"light cover {cover:.0%}  mean {mean:.3f}  (medium: 50-80%, 0.08-0.12)")

    pfx.strip(comps, OUT / f"{NAME}_strip.png")
    grid(comps, OUT / f"{NAME}.png")
    grid(cols, OUT / f"{NAME}_color.png")
    grid([pfx.composite(np.zeros_like(c), l) for c, l in zip(cols, lights)], OUT / f"{NAME}_light.png")
    pick = list(range(0, N, 4))
    for bg, tag in (("#101018", "dark"), ("#5a6070", "mid")):
        grid([pfx.composite(cols[i], lights[i], bg) for i in pick], OUT / f"{NAME}_x4_{tag}.png", n=5, scale=4)
    pfx.gif(comps, OUT / f"{NAME}.gif", FPS, scale=4)

    # parts: cast (no mockup caster), travel loop, impact
    parts = {}
    pc = [finish(draw(f, ("charge", "dragon"))) for f in range(0, DIVE0)]
    y0, y1, x0, x1 = crop_box([p[0] for p in pc], [p[2] for p in pc])
    cast = [pfx.composite(c[y0:y1, x0:x1], l[y0:y1, x0:x1]) for c, l, _ in pc]
    pfx.strip(cast, OUT / f"{NAME}_cast.png")
    pfx.strip([l[y0:y1, x0:x1] if False else pfx.composite(np.zeros_like(c[y0:y1, x0:x1]), l[y0:y1, x0:x1])
               for c, l, _ in pc], OUT / f"{NAME}_cast_light.png")
    hand_x, hand_y = path_at(tip_at(DIVE0))[:2]
    piv = (float(GROUND[0] - x0), float(GROUND[1] - y0))
    parts["cast"] = fc.part(f"{NAME}_cast.png", int(x1 - x0), int(y1 - y0), DIVE0, FPS, piv, False, "caster",
                            light=f"{NAME}_cast_light.png", frames_in_joined=[0, DIVE0 - 1],
                            handoff=[round(float(hand_x - GROUND[0]), 1), round(float(hand_y - GROUND[1]), 1)],
                            **fc.meta("side", int(x1 - x0), int(y1 - y0), piv))
    ok_c, *_ = check([c[y0:y1, x0:x1] for c, _, _ in pc], [L[y0:y1, x0:x1] for _, _, L in pc], "cast")

    pt = [finish(draw_travel(f)) for f in range(TN)]
    pfx.strip([pfx.composite(c, l) for c, l, _ in pt], OUT / f"{NAME}_travel.png")
    pfx.strip([pfx.composite(np.zeros_like(c), l) for c, l, _ in pt], OUT / f"{NAME}_travel_light.png")
    pfx.gif([pfx.composite(c, l) for c, l, _ in pt], OUT / f"{NAME}_travel.gif", FPS, scale=4)
    parts["travel"] = fc.part(f"{NAME}_travel.png", TW, TH, TN, FPS, TPIV, True, "travel",
                              light=f"{NAME}_travel_light.png", speed=TRAVEL_SPEED,
                              heading_deg=round(math.degrees(math.atan2(DIVE_DIR[1], DIVE_DIR[0])), 1),
                              **fc.meta("side", TW, TH, TPIV))
    ok_t, *_ = check([c for c, _, _ in pt], [L for _, _, L in pt], "travel")

    pi = [finish(draw(f, ("impact",))) for f in range(HIT0, N)]
    y0, y1, x0, x1 = crop_box([p[0] for p in pi], [p[2] for p in pi])
    pfx.strip([pfx.composite(c[y0:y1, x0:x1], l[y0:y1, x0:x1]) for c, l, _ in pi], OUT / f"{NAME}_impact.png")
    pfx.strip([pfx.composite(np.zeros_like(c[y0:y1, x0:x1]), l[y0:y1, x0:x1]) for c, l, _ in pi],
              OUT / f"{NAME}_impact_light.png")
    piv = (float(T[0] - x0), float(T[1] - y0))
    parts["impact"] = fc.part(f"{NAME}_impact.png", int(x1 - x0), int(y1 - y0), N - HIT0, FPS, piv, False, "target",
                              light=f"{NAME}_impact_light.png", frames_in_joined=[HIT0, N - 1], peak=[0, 1],
                              **fc.meta("side", int(x1 - x0), int(y1 - y0), piv))
    ok_i, *_ = check([c[y0:y1, x0:x1] for c, _, _ in pi], [L[y0:y1, x0:x1] for _, _, L in pi], "impact")

    meta = dict(name=NAME, w=W, h=H, frames=N, fps=FPS, cols=10, loop=False, pivot=list(GROUND),
                target=list(T), glow="medium", light_gain=1.0, states=STATES, caster="mockup, joined sheet only",
                sheets=dict(composite=f"{NAME}.png", color=f"{NAME}_color.png", light=f"{NAME}_light.png",
                            strip=f"{NAME}_strip.png"),
                parts=parts)
    meta.update(fc.meta("side", W, H, GROUND, target=T))
    fc.check(meta)
    (OUT / f"{NAME}.json").write_text(json.dumps(meta, indent=1))
    print(f"S_top {S_TOP:.0f}  S_B {S_B:.0f}  dive mean {(S_B - 1.15 * S_TOP) / (HIT0 - DIVE0):.1f} px/frame")
    sys.exit(0 if ok and ok_c and ok_t and ok_i else 1)


if __name__ == "__main__":
    main()
