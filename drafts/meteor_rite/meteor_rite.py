"""meteor_rite: a long chant draws a gold circle round the caster, it flares, he points, and a burning meteor falls
on the target; a white flash, a ground shock, a dust wall, an ejecta cone and smoke flatten the scene.

Side view facing east (mirror), 320x200, 30 fps, 180 frames (6 s), one-shot. Painterly HD (more tones, no
outline, translucent soft volumes), strong glow. Gold circle, ember fire, warm smoke.

| state  | frames  | s         | what moves                                                                  |
|--------|---------|-----------|-----------------------------------------------------------------------------|
| chant  | 0-74    | 0.0-2.5   | motes rise; outer ring, second ring, ticks, hexagram, inner ring draw in      |
| flare  | 75-86   | 2.5-2.9   | the circle goes white, a ring wave runs out, columns of light rise           |
| point  | 87-95   | 2.9-3.2   | he points at the sky; a star kindles where he points                         |
| fall   | 96-128  | 3.2-4.3   | the burning rock falls on a 30 degree slant, growing, smoke and embers shed   |
| impact | 129-140 | 4.3-4.7   | white flash and rays, fireball, ground shock ring, dust wall, ejecta cone    |
| fade   | 141-179 | 4.7-6.0   | smoke rises and breaks up, ejecta lands, the crater cools to embers         |

Parts for the engine: cast (circle, anchor caster), travel (meteor loop, anchor travel), impact (anchor target).
Run with `peak` to write only out/peak.png.
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "kit"))
import caster as cs  # noqa: E402
import export as ex  # noqa: E402
import facing as fc  # noqa: E402
import fxkit as fk  # noqa: E402
import fxlib as fl  # noqa: E402
import pfx  # noqa: E402
import target as tg  # noqa: E402
from PIL import Image  # noqa: E402

NAME = "meteor_rite"
OUT = Path(__file__).parent / "out"
W, H, FPS, N, SEED = 320, 200, 30, 180, 11
TAU = math.tau
GY = 176                                   # ground line
CAST, TGT, PIVOT = (70.0, 176.0), (220.0, 176.0), (70, 176)
CX, CY, RX, RY = 70.0, 176.0, 42.0, 10.0   # the circle on the ground round the caster
STAR, HIT = (136.0, 26.0), (220.0, 168.0)  # where the meteor kindles, where its centre lands

# state starts; each state runs to the next start
CHANT, FLARE, POINT, FALL, IMP, FADE = 0, 75, 87, 96, 129, 141
STATES = {"chant": (CHANT, FLARE - 1), "flare": (FLARE, POINT - 1), "point": (POINT, FALL - 1),
          "fall": (FALL, IMP - 1), "impact": (IMP, FADE - 1), "fade": (FADE, N - 1)}

GOLD = ["#3a2a10", "#a07020", "#f0c040", "#fff0b0"]
ROCK = ["#140c10", "#1e1418", "#3a2626", "#5e3a30", "#86563c"]
FIRE = ["#3a1020", "#8a2a18", "#e0601c", "#ffc040", "#fff4d0", "#ffffff"]
SMOKE = ["#1c1418", "#33262a", "#523c38", "#7a5c4c", "#a07c60"]
LGOLD = ["#3a2408", "#d09a30", "#ffe08a", "#ffffff"]
LFIRE = ["#4a1208", "#e8601a", "#ffc860", "#ffffff"]
FIRE_A = np.array([0.5, 0.78, 0.94, 1.0, 1.0, 1.0])


def hexf(c):
    return np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


PAL = {k: np.stack([hexf(c) for c in v]) for k, v in dict(gold=GOLD, rock=ROCK, fire=FIRE, smoke=SMOKE).items()}
YY, XX = np.mgrid[0:H, 0:W].astype(float)


class Frame:
    """Straight-alpha colour plus two light maps (gold for the circle, fire for the rock and the blast)."""

    def __init__(self):
        self.rgb = np.zeros((H, W, 3))
        self.a = np.zeros((H, W))
        self.Lg = np.zeros((H, W))
        self.Lf = np.zeros((H, W))

    def over(self, ys, xs, rgb, a):
        if len(ys) == 0:
            return
        a = np.broadcast_to(np.asarray(a, float), ys.shape)
        rgb = np.broadcast_to(np.asarray(rgb, float), (len(ys), 3))
        A = self.a[ys, xs]
        out = a + A * (1 - a)
        self.rgb[ys, xs] = (rgb * a[:, None] + self.rgb[ys, xs] * (A * (1 - a))[:, None]) / np.maximum(out, 1e-6)[:, None]
        self.a[ys, xs] = out

    def tones(self, sl, m, pal, alpha=1.0):
        on = m >= 0
        if not on.any():
            return
        ys, xs = np.nonzero(on)
        a = alpha[ys, xs] if np.ndim(alpha) == 2 else alpha
        self.over(ys + sl[0].start, xs + sl[1].start, PAL[pal][m[ys, xs]], a)

    def colour(self):
        return np.concatenate([self.rgb, self.a[..., None]], -1).__mul__(255).round().astype(np.uint8)


def win(x0, x1, y0, y1):
    xa, xb = max(int(math.floor(x0)), 0), min(int(math.ceil(x1)) + 1, W)
    ya, yb = max(int(math.floor(y0)), 0), min(int(math.ceil(y1)) + 1, H)
    sl = (slice(ya, max(ya, yb)), slice(xa, max(xa, xb)))
    return sl, XX[sl], YY[sl]


def smooth(s):
    s = np.clip(s, 0, 1)
    return s * s * (3 - 2 * s)


# ---------------------------------------------------------------- circle
def circle_energy(f):
    """How lit the circle is: a breathing chant, a white flare, then it fades after the point."""
    if f < FLARE:
        return 0.55 + 0.2 * f / FLARE + 0.06 * math.sin(f * 0.45)
    if f < POINT:
        k = (f - FLARE) / (POINT - FLARE)
        return 0.85 + 0.25 * math.sin(math.pi * min(k * 1.6, 1.0))
    return max(0.0, 0.85 * (1 - (f - POINT) / (130 - POINT)))


def seg(p, q, n=None):
    n = n or max(int(math.hypot(q[0] - p[0], q[1] - p[1]) * 1.6) + 2, 2)
    t = np.linspace(0, 1, n)
    return p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t


def on_ground(rr, th):
    return CX + RX * rr * np.cos(th), CY + RY * rr * np.sin(th)


def circle_ink(f):
    """Points of the circle drawn so far, (x, y, hot) with hot 1 at each drawing head, and the head points."""
    rot = 0.012 * f
    xs, ys, hs, heads = [], [], [], []

    def prog(a, b):
        return float(np.clip((f - a) / (b - a), 0, 1))

    def ring(rr, a, b, th0, sgn):
        p = prog(a, b)
        if p <= 0:
            return
        th = th0 + sgn * TAU * np.linspace(0, p, max(int(700 * rr * p), 2))
        x, y = on_ground(rr, th)
        xs.append(x), ys.append(y), hs.append(np.zeros_like(x))
        if p < 1:
            heads.append((x[-1], y[-1]))

    ring(1.0, 3, 34, math.pi / 2, 1)
    ring(0.86, 18, 44, math.pi / 2, -1)
    p = prog(36, 58)                                    # 24 ticks between the rings, one after another
    for k in range(24):
        q = np.clip(p * 24 - k, 0, 1)
        if q <= 0:
            continue
        th = rot + TAU * k / 24
        a = on_ground(0.88, th)
        b = on_ground(0.88 + 0.1 * q, th)
        x, y = seg(a, b, 6)
        xs.append(x), ys.append(y), hs.append(np.zeros_like(x))
    p = prog(46, 70)                                    # hexagram: six edges, each drawn after the last
    vs = [on_ground(0.8, rot + math.pi / 2 + TAU * k / 3) for k in range(3)]
    vs2 = [on_ground(0.8, rot + math.pi / 2 + math.pi / 3 + TAU * k / 3) for k in range(3)]
    edges = [(vs[k], vs[(k + 1) % 3]) for k in range(3)] + [(vs2[k], vs2[(k + 1) % 3]) for k in range(3)]
    for k, (a, b) in enumerate(edges):
        q = float(np.clip(p * 6 - k, 0, 1))
        if q <= 0:
            continue
        x, y = seg(a, (a[0] + (b[0] - a[0]) * q, a[1] + (b[1] - a[1]) * q))
        xs.append(x), ys.append(y), hs.append(np.zeros_like(x))
        if q < 1:
            heads.append((x[-1], y[-1]))
    ring(0.4, 58, 72, -math.pi / 2, 1)
    if not xs:
        return None, heads
    return (np.concatenate(xs), np.concatenate(ys), np.concatenate(hs)), heads


def grow(m):
    g = m.copy()
    g[1:] |= m[:-1]
    g[:-1] |= m[1:]
    g[:, 1:] |= m[:, :-1]
    g[:, :-1] |= m[:, 1:]
    return g


def draw_circle(fr, f, back):
    e = circle_energy(f)
    if e <= 0:
        return
    ink, heads = circle_ink(f)
    if ink is not None:
        x, y, _ = ink
        xi, yi = np.round(x).astype(int), np.round(y).astype(int)
        keep = (yi < CY) if back else (yi >= CY)
        if f > 100:                                           # break the lines up as they fade
            gone = (f - 100) / 26.0
            keep &= np.array([fk.hsh(i, 9) for i in range(len(xi))]) >= min(gone, 0.99)
        core = np.zeros((H, W), bool)
        core[yi[keep], xi[keep]] = True
        r1 = grow(core) & ~core
        r2 = grow(core | r1) & ~(core | r1)
        if back:                                              # the halo stays on its own side of the caster
            r1[int(CY):] = r2[int(CY):] = False
        else:
            r1[:int(CY)] = r2[:int(CY)] = False
        a = min(e, 1.0)
        sl = (slice(0, H), slice(0, W))
        m = np.full((H, W), -1, int)
        m[r2 & (f < 106)] = 0
        fr.tones(sl, m, "gold", 0.4 * a)
        m = np.full((H, W), -1, int)
        m[r1 & (f < 114)] = 2 if e > 0.95 else 1
        fr.tones(sl, m, "gold", 0.75 * a)
        m = np.full((H, W), -1, int)
        m[core] = 3 if e > 0.8 else 2
        fr.tones(sl, m, "gold", min(1.0, 0.4 + a))
    if not back:
        for hx, hy in heads:                                  # the drawing heads spark
            twinkle(fr, hx, hy, 2, "gold")
            cs.glow(fr.Lg, hx, hy, 5, 0.5)
            cs.glow(fr.Lg, hx, hy, 14, 0.18)
        cs.glow_ring(fr.Lg, CX, CY, RX, 5, 0.4 * e, flat=RY / RX)
        cs.glow_ring(fr.Lg, CX, CY, RX * 0.8, 4, 0.18 * e, flat=RY / RX)
        cs.glow(fr.Lg, CX, CY - 4, RX * 1.35, 0.16 * e, flat=0.45)
        cs.glow(fr.Lg, CX, CY - 36, 64, 0.42 * e, flat=0.8)


def twinkle(fr, x, y, size, pal, a=1.0):
    xi, yi = int(round(x)), int(round(y))
    pts = [(xi, yi, len(PAL[pal]) - 1)]
    for d in range(1, size + 1):
        t = max(len(PAL[pal]) - 1 - d, 1)
        pts += [(xi + d, yi, t), (xi - d, yi, t), (xi, yi + d, t), (xi, yi - d, t)]
    pts = [p for p in pts if 0 < p[0] < W - 1 and 0 < p[1] < H - 1]
    if pts:
        p = np.array(pts)
        fr.over(p[:, 1], p[:, 0], PAL[pal][p[:, 2]], a)


def flare(fr, f, back):
    """The flare: a ring wave runs out over the ground, columns of light rise from the ring."""
    if not FLARE <= f < POINT + 4:
        return
    k = (f - FLARE) / (POINT + 4 - FLARE)
    rise = smooth(k * 1.8)
    fade = 1 - smooth((k - 0.45) / 0.55)
    rr = 1 + 0.55 * smooth(k * 1.3)
    th = np.linspace(0, TAU, 900)
    x, y = on_ground(rr, th)
    xi, yi = np.round(x).astype(int), np.round(y).astype(int)
    sel = (yi < CY) if back else (yi >= CY)
    pts = np.unique(np.stack([yi[sel], xi[sel]], 1), axis=0)
    fr.over(pts[:, 0], pts[:, 1], PAL["gold"][3 if k < 0.3 else 2], 0.9 * (1 - k))
    for j in range(16):                                   # columns of light from points on the ring
        a = TAU * j / 16 + 0.2
        cx0, cy0 = on_ground(0.93, a)
        if (cy0 < CY) != back:
            continue
        hgt = (40 + 36 * fk.hsh(j, 4)) * rise
        if hgt < 1:
            continue
        ys = np.arange(int(cy0 - hgt), int(cy0) + 1)
        t = (cy0 - ys) / max(hgt, 1)
        alpha = 0.85 * fade * np.clip(1 - t, 0, 1) ** 1.3
        tone = np.where(t < 0.3, 3, np.where(t < 0.7, 2, 1))
        xs = np.full(ys.shape, int(round(cx0)))
        fr.over(ys, xs, PAL["gold"][tone], alpha)
        if not back:
            cs.glow_line(fr.Lg, (cx0, cy0), (cx0, cy0 - hgt), 3, 0.22 * fade)
    if not back:
        cs.glow_line(fr.Lg, (CX, CY - 4), (CX, CY - 96 * rise), 26, 0.36 * fade)
        cs.glow_line(fr.Lg, (CX, CY - 4), (CX, CY - 80 * rise), 8, 0.4 * fade)
        cs.glow_ring(fr.Lg, CX, CY, RX * rr, 6, 0.4 * (1 - k), flat=RY / RX)


def motes(fr, f, seed, back):
    """Gold motes rising off the circle through the chant."""
    rng = np.random.default_rng(seed + 1)
    n = 46
    birth = rng.uniform(-30, 92, n)
    th = rng.uniform(0, TAU, n)
    rr = rng.uniform(0.3, 1.0, n)
    vy = rng.uniform(0.45, 1.0, n)
    life = rng.uniform(20, 38, n)
    ph = rng.uniform(0, TAU, n)
    for i in range(n):
        age = f - birth[i]
        if not 0 <= age < life[i]:
            continue
        x0, y0 = on_ground(rr[i], th[i])
        if (y0 < CY) != back:
            continue
        x = x0 + 1.6 * math.sin(age * 0.25 + ph[i])
        y = y0 - vy[i] * age
        a = 1 - age / life[i]
        xi, yi = int(round(x)), int(round(y))
        fr.over(np.array([yi]), np.array([xi]), PAL["gold"][3 if a > 0.5 else 2], 0.9 * a)
        cs.glow(fr.Lg, x, y, 4, 0.3 * a)


# ---------------------------------------------------------------- meteor
ANG = math.atan2(HIT[1] - STAR[1], HIT[0] - STAR[0])
DIR = (math.cos(ANG), math.sin(ANG))


def path(f):
    """Centre, radius and speed (0..1) of the rock at frame f: it accelerates and grows as it comes down."""
    t = float(np.clip((f - FALL) / (IMP - FALL), 0, 1))
    e = t ** 1.7
    return (STAR[0] + (HIT[0] - STAR[0]) * e, STAR[1] + (HIT[1] - STAR[1]) * e), 3 + 9 * t ** 0.9, t ** 0.7


def meteor(fr, x0, y0, r, ang, tail, ph, seed, spin, period=None):
    """The burning rock: a fire envelope hottest at the bow in front, streaming back into a tail; the rock lit cold
    from the sky at the top left and hot on the face it falls with; lava cracks."""
    ca, sa = math.cos(ang), math.sin(ang)
    tx, ty = x0 - ca * tail, y0 - sa * tail
    R = r * 1.45
    sl, x, y = win(min(x0, tx) - R - 3, max(x0, tx) + R + 3, min(y0, ty) - R - 3, max(y0, ty) + R + 3)
    if x.size == 0:
        return
    u, v = fk.rot(x - x0, y - y0, ang)
    n = fl.noise(u + ph * 9, v * 1.7 + 40, 4, seed, period=period)
    s = np.clip(-u / tail, 0, None)
    wid = R * np.clip(1 - s, 0, 1) ** 0.75 * (0.8 + 0.45 * n)
    front = (u >= 0) & (np.hypot(u, v) < R * (0.88 + 0.22 * n))
    body = (u < 0) & (s < 1) & (np.abs(v) < wid)
    env = front | body
    heat_f = 1.3 - np.hypot(u, v) / R * 1.05
    heat_t = (1 - (np.abs(v) / np.maximum(wid, 1e-6)) ** 2) * np.clip(1 - s, 0, 1) ** 1.1 * 1.05 + 0.12
    heat = np.where(u >= 0, heat_f, heat_t) + 0.32 * (n - 0.5)
    m = np.digitize(heat, [0.18, 0.38, 0.58, 0.78, 1.0])
    m[~env] = -1
    fr.tones(sl, m, "fire", FIRE_A[np.clip(m, 0, 5)])
    d = fk.lumpy(x, y, x0, y0, r, 0.13, seed + 3.0, spin, 5)
    on = d < 1
    nx, ny = (x - x0) / r, (y - y0) / r
    nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
    sky = np.clip(-0.55 * nx - 0.6 * ny + 0.58 * nz, 0, 1)
    hot = np.clip(nx * ca + ny * sa, 0, 1)
    mr = np.where(on, np.clip((sky * 4.6).astype(int), 0, 4), -1)
    fr.tones(sl, mr, "rock")
    ru, rv = fk.rot(x - x0, y - y0, spin)
    c = fl.noise(ru + 60, rv + 60, max(r * 0.4, 1.6), seed + 7)
    crack = on & (np.abs(c - 0.5) < 0.045) & (d < 0.85)
    mf = np.full(x.shape, -1, int)
    mf[crack] = 1
    mf[on & (hot > 0.3)] = 2
    mf[on & (hot > 0.6)] = 3
    mf[on & (hot > 0.82) & (d > 0.5)] = 4
    fr.tones(sl, mf, "fire", np.where(mf == 2, 0.85, 1.0))
    cs.glow(fr.Lf, x0, y0, r * 1.3, 0.6)
    cs.glow(fr.Lf, x0, y0, r * 3.6, 0.26)
    cs.glow_line(fr.Lf, (x0, y0), (tx, ty), R * 0.9, 0.3)
    cs.glow_line(fr.Lf, (x0, y0), (x0 - ca * tail * 0.5, y0 - sa * tail * 0.5), R * 2.7, 0.13)


def puff(fr, cx, cy, r, alpha, seed, ph=0.0, brk=0.0, hot=0.0):
    """A soft translucent smoke puff lit from the top left, its rim thinning, its underside lit by fire (hot)."""
    sl, x, y = win(cx - r * 1.3, cx + r * 1.3, cy - r * 1.3, cy + r * 1.3)
    if x.size == 0 or r < 0.6:
        return
    d = fk.lumpy(x, y, cx, cy, r, 0.2, seed, ph, 4)
    on = d < 1
    ox, oy = fk.lit_offset(r, 0.4)
    h = np.hypot(x - cx - ox, y - cy - oy) / r
    m = np.full(x.shape, -1, int)
    m[on] = 1
    m[on & (h < 1.05)] = 2
    m[on & (h < 0.65)] = 3
    m[on & (h < 0.3)] = 4
    m[on & (h > 1.25)] = 0
    m[d > 1 - 0.35 * brk] = -1                             # painterly break-up: the puff thins and shrinks
    fr.tones(sl, m, "smoke", alpha * (1 - 0.6 * brk) * np.clip((1 - d) * 3, 0.3, 1))
    if hot > 0:
        under = (m >= 0) & (y > cy - r * 0.1)
        mh = np.where(under, np.where(y > cy + r * 0.45, 2, 1), -1)
        fr.tones(sl, mh, "fire", 0.6 * hot * alpha)


def draw_meteor(fr, f, seed):
    if POINT <= f < FALL + 2:                                  # the star he points at
        k = (f - POINT) / (FALL + 2 - POINT)
        twinkle(fr, *STAR, 1 + int(2 * k), "fire", 0.6 + 0.4 * k)
        cs.glow(fr.Lf, *STAR, 6 + 4 * k, 0.6 * k + 0.2)
        cs.glow(fr.Lf, *STAR, 18, 0.2 * k)
    # trail smoke and embers stay where they were shed
    rng = np.random.default_rng(seed + 2)
    for g in range(FALL, IMP):
        ev = rng.uniform(0, 1, (2, 5))
        age = f - g
        if age < 0:
            continue
        (px, py), r, sp = path(g)
        if age < 24:
            a = 0.6 * (1 - age / 24) ** 1.2 * float(np.clip(1 - (f - IMP) / 10, 0, 1))
            cx = px - DIR[0] * r * 1.1 + (ev[0, 0] - 0.5) * 2
            cy = py - DIR[1] * r * 1.1 + (ev[0, 1] - 0.5) * 2 - age * 0.12
            puff(fr, cx, cy, 1 + 0.45 * r + 0.32 * age, a, g * 1.3, age * 0.1, brk=age / 24,
                 hot=max(0.0, 1 - age / 6))
        for e in ev:
            life = 8 + 8 * e[2]
            if age >= life:
                continue
            vx = -DIR[0] * (0.5 + e[3]) + (e[4] - 0.5) * 1.2 * -DIR[1]
            vy = -DIR[1] * (0.5 + e[3]) + (e[4] - 0.5) * 1.2 * DIR[0]
            ex_, ey_ = px + vx * age, py + vy * age + 0.03 * age * age
            k = 1 - age / life
            fr.over(np.array([int(round(ey_))]), np.array([int(round(ex_))]), PAL["fire"][2 + int(2 * k)], 0.6 + 0.4 * k)
            cs.glow(fr.Lf, ex_, ey_, 3, 0.25 * k)
    if FALL <= f < IMP:
        (x0, y0), r, sp = path(f)
        meteor(fr, x0, y0, r, ANG, r * (1.5 + 4.5 * sp), f / 4, seed, f * 0.18)
        cs.glow(fr.Lf, x0, y0, float(np.clip(min(y0 - 4, H - 4 - y0), 8, 64)), 0.16 + 0.3 * sp)
        cs.glow_line(fr.Lf, STAR, (x0, y0), 30, 0.1 + 0.1 * sp)
    if IMP - 4 <= f < IMP:                                     # the ground lights before contact
        k = (f - IMP + 5) / 5
        cs.glow(fr.Lf, HIT[0], GY - 2, 34, 0.3 * k, flat=0.35)


# ---------------------------------------------------------------- impact
def draw_impact(fr, f, seed):
    t = f - IMP
    if t < 0:
        return
    hx, hy = HIT
    # crater: a hot pit with a lit rim that cools and shrinks to a few embers
    heat = max(0.0, 1 - t / 48)
    ca = float(np.clip(1 - (t - 26) / 20, 0, 1))
    sl, x, y = win(hx - 24, hx + 24, GY - 8, GY + 2)
    d = np.hypot((x - hx) / 21, (y - (GY - 1)) / 4.5)
    n = fl.noise(x, y * 2, 3, seed + 21)
    m = np.full(x.shape, -1, int)
    if ca > 0:
        rim = (d < 1) & (d >= 0.7)
        m[rim] = np.where(y[rim] < GY - 1, 3, 1)
        m[(d < 0.7)] = 1
        fr.tones(sl, m, "rock", ca)
    lava = (d < 0.72) & (n > 0.45 + 0.5 * (1 - heat))
    ml = np.where(lava, np.clip((heat * (1.3 - d) * 4 + (n - 0.5) * 2).astype(int), 0, 4), -1)
    fr.tones(sl, ml, "fire", 0.9)
    cs.glow(fr.Lf, hx, GY - 2, 26, 0.32 * heat, flat=0.4)
    cs.glow(fr.Lf, hx, GY - 12, 50, 0.14 * heat, flat=0.6)
    cs.glow(fr.Lf, hx, 140, 84, 0.5 * heat ** 0.5, flat=0.6)

    # ground shock ring
    if t < 10:
        rx = 14 + 72 * (1 - math.exp(-t / 4))
        th = np.linspace(0, TAU, 900)
        xi = np.round(hx + rx * np.cos(th)).astype(int)
        yi = np.round(GY - 1 + rx * 0.1 * np.sin(th)).astype(int)
        p = np.unique(np.stack([yi, xi], 1), axis=0)
        fr.over(p[:, 0], p[:, 1], PAL["fire"][max(4 - t // 3, 2)], 1 - t / 10)
        cs.glow_ring(fr.Lf, hx, GY - 1, rx, 7, 0.4 * (1 - t / 10), flat=0.12)

    # dust wall rolling out both ways along the ground
    if t < 50:
        xf = 12 + 60 * (1 - math.exp(-t / 5))
        a = 0.78 * float(np.clip(1 - (t - 14) / 34, 0, 1))
        brk = float(np.clip((t - 16) / 28, 0, 1))
        for side in (-1, 1):
            for j in range(11, -1, -1):                       # back to front: the rolling head is drawn last
                h1, h2, h3 = (fk.hsh(j, 61 + side), fk.hsh(j, 67 + side), fk.hsh(j, 71 + side))
                fr_ = 1 - j * 0.075 - 0.05 * h1
                grow_ = 0.5 + 0.5 * min(t / 4, 1)
                r = (2.2 + 7 * fr_ ** 2 * (0.6 + 0.6 * h2)) * grow_ * (1 + t / 40)
                px = hx + side * (xf * fr_ + (h3 - 0.5) * 4)
                py = GY - r * (0.55 + 0.5 * h1) - t * 0.08 * (1 - fr_) * 6 - (h2 - 0.5) * 3
                puff(fr, px, py, r, a * (0.55 + 0.45 * fr_), 31 + j * 7 + side, t * 0.12, brk,
                     hot=max(0.0, 1 - t / 9) * fr_)

    # fireball rising and cooling
    if t < 26:
        r = 9 + 15 * (1 - math.exp(-t / 5))
        cy = hy - 26 * (1 - math.exp(-t / 9))
        ht = float(np.clip(1.15 - t / 20, 0.05, 1.15))
        alpha = float(np.clip(1.7 - t / 15, 0, 1))
        sl, x, y = win(hx - r * 1.3, hx + r * 1.3, cy - r * 1.3, cy + r * 1.3)
        d = fk.lumpy(x, y, hx, cy, r, 0.22, seed + 5.0, t * 0.1, 6)
        nn = fl.noise(x, y + t * 1.5, 5, seed + 23)
        ox, oy = fk.lit_offset(r, 0.25)
        q = np.hypot(x - hx - ox, y - cy - oy) / r
        hh = ht * (1.2 - q) + 0.3 * (nn - 0.5)
        m = np.digitize(hh, [0.12, 0.3, 0.5, 0.7, 0.9])
        m[(d >= 1) | (y > GY)] = -1
        fr.tones(sl, m, "fire", alpha * FIRE_A[np.clip(m, 0, 5)])
        cs.glow(fr.Lf, hx, cy, r * 1.1, 0.55 * ht)
        cs.glow(fr.Lf, hx, cy, r * 2.8, 0.26 * ht)

    # smoke column from the fireball
    rng = np.random.default_rng(seed + 5)
    k = 14
    birth = rng.uniform(3, 15, k)
    jx = rng.uniform(-11, 11, k)
    vy = rng.uniform(0.45, 0.95, k)
    vx = rng.uniform(-0.35, 0.35, k)
    life = rng.uniform(26, 36, k)
    r1 = rng.uniform(9, 15, k)
    for i in range(k):
        age = t - birth[i]
        if not 0 <= age < life[i]:
            continue
        s = age / life[i]
        puff(fr, hx + jx[i] + vx[i] * age, hy - 14 - vy[i] * age, 4 + (r1[i] - 4) * math.sqrt(s),
             0.72 * (1 - s ** 1.5), 50 + i, age * 0.08, brk=s, hot=max(0.0, 1 - age / 10))

    # ejecta: shards on a cone, ballistic, hot then cold, landing round the crater
    rng = np.random.default_rng(seed + 3)
    k = 16
    side = np.where(np.arange(k) % 2 == 0, 1, -1)
    th = np.radians(rng.uniform(45, 72, k))
    v = rng.uniform(2.3, 3.8, k)
    size = rng.uniform(1.4, 3.2, k)
    spin = rng.uniform(-0.3, 0.3, k)
    g = 0.2
    for i in range(k):
        if t > 52:
            break
        vx, vy0 = side[i] * v[i] * math.cos(th[i]), -v[i] * math.sin(th[i])
        tl = (-vy0 + math.sqrt(vy0 * vy0 + 2 * g * (GY - size[i] - hy))) / g    # time to land
        tt = min(t, tl)
        px, py = hx + vx * tt, hy + vy0 * tt + 0.5 * g * tt * tt
        a = float(np.clip(1 - (t - tl - 8) / 12, 0, 1))
        if a <= 0:
            continue
        cool = max(0.0, 1 - t / 16)
        if t >= tl:                                              # landed: it smoulders until it fades
            cool = max(cool, 0.5 * a * (1 - (t - tl) / 30))
        pts = fk.polygon(px, py, size[i], 5, i + 40, ph=spin[i] * tt)
        sl, x, y = win(px - size[i] - 2, px + size[i] + 2, py - size[i] - 2, py + size[i] + 2)
        m = np.full(x.shape, -1, int)
        fk.facets(m, x, y, pts, (1, 2, 3, 4))
        if cool > 0.45:
            fr.tones(sl, np.where(m >= 0, m, -1), "fire", a)
        else:
            fr.tones(sl, m, "rock", a)
            if cool > 0:
                mh = np.where(m == 4, 3, np.where(m == 3, 2, -1))
                fr.tones(sl, mh, "fire", cool * 1.6)
        if t < tl and t < 12:                                    # a short hot streak behind it while it flies
            sx_, sy_ = seg((px, py), (px - vx * 2.5, py - (vy0 + g * tt) * 2.5), 5)
            fr.over(np.round(sy_).astype(int), np.round(sx_).astype(int), PAL["fire"][2], 0.7 * (1 - t / 12))
        cs.glow(fr.Lf, px, py, 4 + size[i], 0.4 * cool + 0.04 * a)
        cs.glow(fr.Lf, px, py, 12, 0.12 * cool)

    # sparks
    rng = np.random.default_rng(seed + 4)
    k = 26
    th = np.radians(rng.uniform(15, 85, k))
    v = rng.uniform(2.4, 4.8, k)
    life = rng.uniform(8, 18, k)
    sd = np.where(rng.uniform(0, 1, k) < 0.5, -1, 1)
    for i in range(k):
        if t >= life[i]:
            continue
        vx, vy0 = sd[i] * v[i] * math.cos(th[i]), -v[i] * math.sin(th[i])
        px, py = hx + vx * t, hy - 4 + vy0 * t + 0.125 * t * t
        if py > GY:
            continue
        a = 1 - t / life[i]
        sx_, sy_ = seg((px, py), (px - vx * 0.8, py - (vy0 + 0.25 * t) * 0.8), 3)
        fr.over(np.round(sy_).astype(int), np.round(sx_).astype(int), PAL["fire"][np.array([5, 4, 3]) if a > 0.5
                                                                                  else np.array([4, 3, 2])], a)
        cs.glow(fr.Lf, px, py, 3.5, 0.35 * a)

    # the white flash and its rays, last so they sit on top
    if t <= 3:
        fk_ = [1.0, 0.9, 0.75, 0.55][t]
        rx = [26, 31, 21, 12][t]
        cy = 164
        sl, x, y = win(hx - rx * 2, hx + rx * 2, cy - rx * 1.6, GY + 1)
        ryb = GY + 1 - cy
        dd = np.hypot((x - hx) / rx, (y - cy) / np.where(y > cy, ryb, rx * 0.75))
        m = np.full(x.shape, -1, int)
        if t < 3:
            fk.streaks(m, x, y, hx, cy, 14, rx * 0.6, rx * 1.75, 2.2, (2, 3, 4), seed=seed, flat=0.8)
        m[dd < 1] = 3
        m[dd < 0.7] = 4
        m[dd < 0.45] = 5
        m[y > GY + 1] = -1
        fr.tones(sl, m, "fire", fk_ * np.clip((1.15 - dd) * 2.5, 0.3, 1.0))
        cs.glow(fr.Lf, hx, cy, rx + 4, 0.9 * fk_)
        cs.glow(fr.Lf, hx, 150, 92, 0.6 * fk_, flat=0.5)


# ---------------------------------------------------------------- render
def caster_pose(f):
    aim = cs.aim_from(CAST, 0.44, STAR)
    jab = 4 * math.exp(-max(f - POINT - 3, 0) / 3) if f >= POINT + 3 else 0.0
    pose = cs.pose_at(f, [(0, "chest"), (FLARE - 4, "chest"), (FLARE + 4, "raise"), (POINT + 3, "point"),
                          (IMP + 18, "point"), (N - 6, "chest")],
                      [(0, "rest"), (FLARE, "out"), (IMP + 18, "out"), (N - 6, "rest")], aim, jab)
    return pose, jab


def render(f, seed=SEED, caster=False, parts=("circle", "meteor", "impact")):
    """Frame f as (colour uint8, light rgb 0..1, summed light)."""
    fr = Frame()
    if "circle" in parts:
        draw_circle(fr, f, True)
        flare(fr, f, True)
        motes(fr, f, seed, True)
    if caster:
        e = circle_energy(f)
        pose, jab = caster_pose(f)
        g = cs.draw(fr.over, (H, W), CAST, 0.44, pose, f, 0.15 + 0.6 * e, 0.25 + 0.45 * e, hair="loose")
        cs.body_light(fr.Lg, g, e)
        pt = float(np.clip((f - POINT) / 4, 0, 1)) * (1 if f < IMP + 18 else 0.4)
        cs.finger_light(fr.Lg, g, pt, jab)
    if "circle" in parts:
        draw_circle(fr, f, False)
        flare(fr, f, False)
        motes(fr, f, seed, False)
    if "meteor" in parts:
        draw_meteor(fr, f, seed)
    if "impact" in parts:
        draw_impact(fr, f, seed)
    Lg, Lf = np.clip(fr.Lg, 0, 1), np.clip(fr.Lf, 0, 1)
    light = np.clip(pfx.tint(np.repeat(Lg[..., None], 3, -1), LGOLD) + pfx.tint(np.repeat(Lf[..., None], 3, -1), LFIRE),
                    0, 1)
    return fr.colour(), light, fr.Lg + fr.Lf


# travel part: the rock at full size on a loop, in its own cell
TW, TH, TN = 140, 160, 15
TPIV = (88, 110)


def render_travel(f, seed=SEED):
    fr = Frame()
    global W, H, XX, YY
    keep = W, H, XX, YY
    W, H = TW, TH
    YY, XX = np.mgrid[0:H, 0:W].astype(float)
    try:
        ph = f / TN
        meteor(fr, TPIV[0], TPIV[1], 12, ANG, 12 * 5.6, 4 * ph, seed, TAU * ph, period=(36, 1024))
        Lf = np.clip(fr.Lf, 0, 1)
        light = pfx.tint(np.repeat(Lf[..., None], 3, -1), LFIRE)
        return fr.colour(), light, fr.Lf
    finally:
        W, H, XX, YY = keep


def bg(colour, ground):
    img = np.zeros((H, W, 3))
    img[:] = hexf(colour)
    img[GY + 1:] = hexf(ground)
    return img


def over_bg(col, light, base):
    a = col[..., 3:4] / 255.0
    rgb = col[..., :3] / 255.0 * a + base * (1 - a) + light
    return (np.concatenate([np.clip(rgb, 0, 1), np.ones_like(a)], -1) * 255).round().astype(np.uint8)


def preview(f, hits, ground):
    col, light, _ = render(f, caster=True)
    dummy = tg.draw((H, W), (int(TGT[0]), int(TGT[1])), f, hits, FPS, facing=-1)
    return over_bg(tg.under(col, dummy), light, ground)


def zoom(img, k):
    return np.kron(img, np.ones((k, k, 1), np.uint8))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    hits = [ex.hit(IMP, FPS, freeze=0.15, shake=5, push=6, react="knockback")]
    dark = bg("#101018", "#1a1822")
    if sys.argv[1:] == ["peak"]:
        pick = [40, 66, 79, 92, 104, 116, 124, 129, 131, 135, 142, 156, 170, 179]
        rows = [zoom(preview(f, hits, dark), 3) for f in pick]
        half = (len(rows) + 1) // 2
        a = np.concatenate(rows[:half], 1)
        b = np.concatenate(rows[half:] + [np.zeros_like(rows[0])] * (2 * half - len(rows)), 1)
        Image.fromarray(np.concatenate([a, b], 0)).save(OUT / "peak.png")
        print("peak.png", pick)
        return 0

    cols, lights, Ls, finals = [], [], [], []
    for f in range(N):
        c, l, L = render(f)
        cols.append(c), lights.append(l), Ls.append(L)
        finals.append(pfx.composite(c, l))

    # light measure
    cov, mean = [], []
    for c, L in zip(cols, Ls):
        ys, xs = np.nonzero(c[..., 3])
        if len(ys) == 0:
            continue
        box = np.clip(L[ys.min():ys.max() + 1, xs.min():xs.max() + 1], 0, 1)
        cov.append((box > 0.03).mean())
        mean.append(box[box > 0.03].mean() if (box > 0.03).any() else 0)
    print(f"light: cover {100 * np.median(cov):.0f} %, mean {np.median(mean):.3f} (strong: 75 to 95 %, 0.12 to 0.18)")
    for st, (a, b) in STATES.items():
        print(f"  {st}: cover {100 * np.median(cov[a:b + 1]):.0f} %, mean {np.median(mean[a:b + 1]):.3f}")

    # previews: caster and dummy, dark and mid grounds
    mid = bg("#5a5a66", "#4a4a54")
    pv = [preview(f, hits, dark) for f in range(N)]
    Image.fromarray(np.concatenate([zoom(pv[f], 4) for f in range(0, N, 9)], 1)).save(OUT / f"{NAME}_4x_dark.png")
    Image.fromarray(np.concatenate([zoom(preview(f, hits, mid), 4) for f in range(0, N, 9)], 1)).save(
        OUT / f"{NAME}_4x_mid.png")
    pfx.strip(finals, OUT / f"{NAME}_1x.png")
    pfx.gif(ex.hitstop(pv, hits, FPS), OUT / f"{NAME}.gif", FPS, scale=4)

    # parts: cast (circle, caster anchored), travel (rock loop), impact (target anchored)
    CAST_N = 129
    cast = [render(f, parts=("circle",)) for f in range(CAST_N)]
    cx0, cx1 = 0, 176
    cast_c = [c[:, cx0:cx1] for c, _, _ in cast]
    cast_l = [l[:, cx0:cx1] for _, l, _ in cast]
    ix0 = 112
    imp = [render(f, parts=("impact",)) for f in range(IMP, N)]
    imp_c = [c[:, ix0:] for c, _, _ in imp]
    imp_l = [l[:, ix0:] for _, l, _ in imp]
    trav = [render_travel(f) for f in range(TN)]
    trav_c = [c for c, _, _ in trav]
    trav_l = [l for _, l, _ in trav]
    speed = round(math.hypot(HIT[0] - STAR[0], HIT[1] - STAR[1]) / ((IMP - FALL) / FPS) * 1.3)

    bad = []
    for nm, cc, ll, lp in (("cast", cast_c, cast_l, False), ("impact", imp_c, imp_l, False),
                           ("travel", trav_c, trav_l, True)):
        bad += [f"{nm}: {b}" for b in ex.check(cc, ll, loop=lp)]
        ex.write(OUT, f"{NAME}_{nm}", [pfx.composite(c, l) for c, l in zip(cc, ll)], FPS,
                 {"cast": PIVOT, "impact": (int(TGT[0]) - ix0, int(TGT[1])), "travel": TPIV}[nm], lp,
                 light=ll, color=cc, extra=fc.meta("side", cc[0].shape[1], H if nm != "travel" else TH,
                                                    {"cast": PIVOT, "impact": (int(TGT[0]) - ix0, int(TGT[1])),
                                                     "travel": TPIV}[nm]))
    parts = {
        "cast": fc.part(f"{NAME}_cast.png", cx1 - cx0, H, CAST_N, FPS, PIVOT, False, "caster", start=0),
        "travel": fc.part(f"{NAME}_travel.png", TW, TH, TN, FPS, TPIV, True, "travel", speed=speed,
                          start=FALL, end=IMP, heading_deg=round(math.degrees(ANG), 1),
                          spawn_from_target=[round(STAR[0] - TGT[0]), round(STAR[1] - TGT[1])],
                          grow=[0.25, 1.0], note="spawn above the target, fly along heading_deg (below east), "
                                                 "scale from grow[0] to grow[1], hand over to impact on contact"),
        "impact": fc.part(f"{NAME}_impact.png", W - ix0, H, N - IMP, FPS, (int(TGT[0]) - ix0, int(TGT[1])), False,
                          "target", start=IMP),
    }
    extra = dict(fc.meta("side", W, H, PIVOT, target=[int(TGT[0]), int(TGT[1])]), glow="strong", parts=parts,
                 range_px=int(TGT[0] - CAST[0]))
    fc.check(extra)
    meta = ex.write(OUT, NAME, finals, FPS, PIVOT, False, light=lights, color=cols, states=STATES, hits=hits,
                    poses=[ex.pose(0.0, "channel"), ex.pose(FLARE / FPS, "cast"),
                           ex.pose(POINT / FPS, "release", "snap"), ex.pose((IMP + 18) / FPS, "recover")],
                    target={"x": int(TGT[0] - CAST[0]), "react": "knockback"}, extra=extra)

    bad += ex.check(cols, lights, loop=False, src=__file__)
    bad += ex.check_seeds(lambda f, sd: render(f, seed=sd)[0], N)
    bad += ex.check_act(meta["meta"]["beanfx"]["act"], N, FPS, False)
    for b in bad:
        print(b)
    print("ok" if not bad else f"{len(bad)} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
