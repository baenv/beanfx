"""Wrathful Fire Lotus: a golden caster rises, 21 heavenly flames (the Heavenly Flames ranking of Battle Through the Heavens, ranks 3 to 23)
ignite one by one in a ring round it, spiral into its raised hand and become the 21 petals of a fire lotus, the lotus
squeezes white-hot, is hurled down to the ground and blooms there as a giant lotus of flame that bursts, then embers
in 21 colours and smoke drift off. General mode, 240x240, 120 frames at 24 fps, one-shot, glow strong.

States (frames, 24 fps):
  summon   0-35   caster rises, the 21 flames ignite in a ring (rank 23 first, rank 3 last)
  fuse    36-71   each flame spirals 1 s into the hand and grows into its petal
  squeeze 72-78   the lotus shrinks and turns white-hot, the caster pulls back
  hurl    79-102  thrown down at 79, lands at 89 (peak 89-90), ground lotus bloom, ring, embers
  fade   103-119  petals break into embers, smoke rises, a scorch glows on the ground
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "kit"))
import caster as cs  # noqa: E402
import pfx  # noqa: E402

NAME = "phat_no_hoa_lien"
W, H, N, FPS = 240, 240, 120, 24
OUT = Path(__file__).parent / "out"

SUMMON0, SUMMON_N = 0, 36
FUSE0, FUSE_N = SUMMON0 + SUMMON_N, 36
SQUEEZE0, SQUEEZE_N = FUSE0 + FUSE_N, 7
HURL0 = SQUEEZE0 + SQUEEZE_N
FALL_N = 10
IMPACT = HURL0 + FALL_N
FADE0 = IMPACT + 14

GROUND_Y = 206.0
GROUND = (72.0, GROUND_Y)            # pivot: the caster's feet before the rise
HOVER = (68.0, 130.0)
T = (170.0, GROUND_Y - 2)            # where the lotus lands
SC = 0.44                            # caster about 34 px tall
APPEAR_STEP = 1.2                    # frames between two flames igniting
GATHER_STEP, GATHER_T = 0.55, 24.0   # stagger and travel time of each flame into the lotus

# ---- the 21 flames: rank, name, kind, 5 tones dark edge to white core ----
FLAMES = [
    (3, "Pure Lotus Demon Fire", "lotus", ["#6a5a86", "#b4a6d2", "#e6def4", "#fbf6ff", "#ffffff"]),
    (4, "Golden Emperor Burning Sky Flame", "tall", ["#7a3a08", "#d07a10", "#ffb820", "#ffe680", "#fffbe0"]),
    (5, "Living Spirit Flame", "leaf", ["#1a5a30", "#30a050", "#70e070", "#c8ffb0", "#f8fff0"]),
    (6, "Eight Desolations Destruction Flame", "wings", ["#5a0a10", "#b02020", "#f05030", "#ffa060", "#fff0d0"]),
    (7, "Nine Nether Golden Ancestor Fire", "twin", ["#3a2010", "#8a6a10", "#d0a830", "#f8e070", "#fffbe0"]),
    (8, "Red Lotus Karma Fire", "lotus", ["#4a0618", "#9a1030", "#e02848", "#ff8090", "#ffe8e8"]),
    (9, "Three Thousand Blaze Fire", "dark", ["#140818", "#3a1450", "#7a30a0", "#c070e0", "#f8e0ff"]),
    (10, "Nine Nether Wind Flame", "wind", ["#203040", "#507080", "#90b8c8", "#d8f0f8", "#ffffff"]),
    (11, "Bone Spirit Cold Fire", "frost", ["#284068", "#6088c0", "#a8d0f0", "#e8f8ff", "#ffffff"]),
    (12, "Nine Dragon Thunder Fire", "bolt", ["#384050", "#788090", "#c0c8d8", "#f0f4ff", "#ffffff"]),
    (13, "Turtle Spirit Earth Fire", "spiky", ["#3a2010", "#7a4a20", "#b87838", "#e8b070", "#fff0d0"]),
    (14, "Falling Heart Flame", "heart", ["#40204a", "#8a4a9a", "#d090e0", "#f8d8ff", "#ffffff"]),
    (15, "Sea Heart Flame", "wave", ["#081a50", "#1840a0", "#3080f0", "#90c8ff", "#f0f8ff"]),
    (16, "Fire Cloud Water Flame", "cloud", ["#104050", "#2088a0", "#50c8d8", "#b0f0f0", "#ffffff"]),
    (17, "Volcanic Rock Flame", "rock", ["#2a1410", "#a03010", "#f06010", "#ffb040", "#fff0b0"]),
    (18, "Wind Wrath Dragon Flame", "swirl", ["#501808", "#c04010", "#ff7a20", "#ffc070", "#fff4d8"]),
    (19, "Green Lotus Core Fire", "lotus", ["#083a40", "#108070", "#30c0a0", "#a0f0d8", "#f0fff8"]),
    (20, "Nether Poison Fire", "wisp", ["#0a2a10", "#2a7020", "#70d030", "#c8ff70", "#f8ffe0"]),
    (21, "Yin Yang Twin Flame", "yinyang", ["#606070", "#a8a8b8", "#e0e0ea", "#f8f8ff", "#ffffff"]),
    (22, "Myriad Beasts Spirit Fire", "beast", ["#300808", "#701818", "#b03020", "#f07050", "#ffe0c8"]),
    (23, "Profound Yellow Flame", "round", ["#5a4008", "#a88010", "#e8c020", "#fff080", "#fffff0"]),
]
NF = len(FLAMES)
YIN = ["#08060c", "#201828", "#403850", "#706880", "#a098b0"]   # the dark half of the yin-yang
FUSED = ["#6a1a30", "#d04838", "#ff9a40", "#ffe8a0", "#ffffff"]  # the fused fireball
SMOKE = ["#3a3038", "#5e5050", "#857468"]
GOLD_L = "#ffc860"


def hexf(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


PAL = [np.stack([hexf(c) for c in fl[3]]) for fl in FLAMES]
PAL_YIN = np.stack([hexf(c) for c in YIN])
PAL_FUSED = np.stack([hexf(c) for c in FUSED])
LHUE = [hexf(fl[3][3]) for fl in FLAMES]
WHITE = np.ones(3)
RANK = {fl[0]: i for i, fl in enumerate(FLAMES)}
# lotus slots, outer 10, middle 7, inner 4, hues alternating warm and cool
SLOTS = [RANK[r] for r in (4, 15, 8, 19, 17, 11, 22, 20, 23, 9, 6, 16, 13, 12, 18, 5, 14, 3, 10, 7, 21)]
SLOT_OF = {fi: j for j, fi in enumerate(SLOTS)}
TIERS = [(0, 10), (10, 17), (17, 21)]

YY, XX = np.mgrid[0:H, 0:W].astype(float)
rng = np.random.default_rng(21)


def ease_io(s):
    s = np.clip(s, 0, 1)
    return s * s * (3 - 2 * s)


def eout(s):
    s = min(max(s, 0.0), 1.0)
    return 1 - (1 - s) ** 3


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _win(x0, x1, y0, y1):
    xa, xb = max(int(x0), 0), min(int(x1) + 2, W)
    ya, yb = max(int(y0), 0), min(int(y1) + 2, H)
    return slice(ya, max(yb, ya)), slice(xa, max(xb, xa))


def seg_d(X, Y, a, b):
    ex, ey = b[0] - a[0], b[1] - a[1]
    h = np.clip(((X - a[0]) * ex + (Y - a[1]) * ey) / (ex * ex + ey * ey or 1e-9), 0, 1)
    return np.hypot(X - a[0] - ex * h, Y - a[1] - ey * h)


class Frame:
    """Colour by alpha-over; light as a scalar L plus a hue sum Hc so each flame glows in its own colour."""

    def __init__(self):
        self.rgb = np.zeros((H, W, 3))
        self.a = np.zeros((H, W))
        self.L = np.zeros((H, W))
        self.Hc = np.zeros((H, W, 3))

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

    def _add(self, sy, sx, v, col):
        self.L[sy, sx] += v
        self.Hc[sy, sx] += v[..., None] * col

    def glow(self, x, y, r, k, col, flat=1.0):
        if k <= 0 or r <= 0:
            return
        sy, sx = _win(x - r, x + r, y - r * flat, y + r * flat)
        d = np.hypot(XX[sy, sx] - x, (YY[sy, sx] - y) / flat) / r
        self._add(sy, sx, np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0), col)

    def glow_line(self, p0, p1, r, k, col):
        if k <= 0:
            return
        sy, sx = _win(min(p0[0], p1[0]) - r, max(p0[0], p1[0]) + r, min(p0[1], p1[1]) - r, max(p0[1], p1[1]) + r)
        d = seg_d(XX[sy, sx], YY[sy, sx], p0, p1) / r
        self._add(sy, sx, np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0), col)

    def glow_ring(self, x, y, R, r, k, col, flat=1.0):
        if k <= 0:
            return
        sy, sx = _win(x - R - r, x + R + r, y - (R + r) * flat, y + (R + r) * flat)
        d = np.abs(np.hypot(XX[sy, sx] - x, (YY[sy, sx] - y) / flat) - R) / r
        self._add(sy, sx, np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0), col)

    def fold(self, Ls, col):
        """Bring a scalar light drawn by caster.py into the frame with one hue."""
        self.L += Ls
        self.Hc += Ls[..., None] * col

    def light_rgb(self):
        v = np.clip(self.L, 0, 1)
        hue = self.Hc / np.maximum(self.L, 1e-6)[..., None]
        hue = hue / np.maximum(hue.max(-1, keepdims=True), 1e-6)
        w = np.clip((self.L - 0.5) / 0.6, 0, 1)[..., None]
        return (hue * (1 - w) + w) * v[..., None]

    def rgba(self):
        return np.dstack([self.rgb, self.a])


def tones_of(q):
    return np.select([q < 0.26, q < 0.44, q < 0.64, q < 0.84], [4, 3, 2, 1], 0)


def rim(m):
    er = m.copy()
    er[1:-1, 1:-1] = m[1:-1, 1:-1] & m[:-2, 1:-1] & m[2:, 1:-1] & m[1:-1, :-2] & m[1:-1, 2:]
    return m & ~er


# ---- one flame: tongues in local units (base at 0, up is -v, about 11 units tall) ----
def tongue(u, v, cx, h, r, sway, curl=0.0, spike=0.0, ph=0.0):
    t = -v / h
    tc = np.clip(t, 0, 1)
    ax = cx + sway * tc ** 2 + curl * tc ** 3
    w = r * (1 - tc) ** 0.85 * (1 + 0.35 * (1 - tc))
    if spike:
        w = w * (1 + spike * np.abs(np.sin(tc * 13 + ph)))
    cap = r * 1.35 * np.sqrt(np.clip(1 - (v / (r * 0.9)) ** 2, 0, 1))
    w = np.where(t < 0, cap, w)
    d = np.abs(u - ax) / np.maximum(w, 1e-3)
    inside = (d <= 1) & (t <= 1) & (v <= r * 0.9)
    q = 0.55 * d + 0.55 * tc - 0.08
    return inside, q


def blob(u, v, cx, cy, r):
    d = np.hypot(u - cx, v - cy) / r
    return d <= 1, 0.65 * d + 0.1


def flame_shape(kind, u, v, f, seed, lean):
    """Mask and heat for each kind; a list of (mask, heat) or (mask, heat, "yin") for the dark half."""
    sw = 1.6 * math.sin(f * 0.7 + seed) + lean
    fl = 1 + 0.12 * math.sin(f * 0.9 + seed * 2.3)
    parts = []
    if kind in ("tall", "leaf", "bolt", "rock", "dark"):
        parts.append(tongue(u, v, 0, 12.5 * fl, 3.0, sw))
    elif kind == "lotus":
        parts += [tongue(u, v, 0, 11 * fl, 2.6, sw), tongue(u, v, -2.4, 7 * fl, 1.8, sw * 0.5 - 2.6),
                  tongue(u, v, 2.4, 7 * fl, 1.8, sw * 0.5 + 2.6)]
    elif kind == "wings":
        parts += [tongue(u, v, 0, 10 * fl, 2.6, sw), tongue(u, v, -2.8, 6.5, 2.0, -6 + sw * 0.3),
                  tongue(u, v, 2.8, 6.5, 2.0, 6 + sw * 0.3)]
    elif kind == "twin":
        parts += [tongue(u, v, -1.3, 11 * fl, 2.2, sw - 1.2), tongue(u, v, 1.4, 9 / fl, 2.2, sw + 1.6)]
    elif kind == "wind":
        parts.append(tongue(u, v, 0, 11 * fl, 2.6, sw + 4.5 * math.copysign(1, lean or 1)))
    elif kind == "frost":
        parts.append(tongue(u, v, 0, 11 * fl, 2.8, sw * 0.5, spike=0.18, ph=f * 0.3))
    elif kind == "spiky":
        parts.append(tongue(u, v, 0, 10.5 * fl, 3.0, sw * 0.6, spike=0.55, ph=f * 0.8 + seed))
    elif kind == "heart":
        parts += [tongue(u, v, -1.6, 9 * fl, 2.4, -1.6 + sw * 0.3), tongue(u, v, 1.6, 9 / fl, 2.4, 1.6 + sw * 0.3)]
    elif kind == "wave":
        parts.append(tongue(u, v, 0, 12 * fl, 2.8, sw * 0.6, curl=4.5))
    elif kind == "cloud":
        parts += [blob(u, v, -2.4, -2.8, 2.6), blob(u, v, 2.4, -2.6, 2.6), blob(u, v, 0, -5.2 + 0.4 * sw, 3.0),
                  tongue(u, v, 0, 10 * fl, 1.6, sw)]
    elif kind == "swirl":
        m, q = tongue(u, v, 0, 12 * fl, 3.0, sw)
        q = q + 0.22 * (np.sin(v * 1.5 + u * 1.2 - f * 1.3) > 0.55)
        parts.append((m, q))
    elif kind == "wisp":
        parts += [blob(u, v, 0, -3.4 + 0.5 * math.sin(f * 0.5 + seed), 3.2), tongue(u, v, 0.4, 10, 1.2, sw + 2.5, -3.0)]
    elif kind == "yinyang":
        s1 = math.sin(f * 0.6 + seed)
        a = tongue(u, v, -1.2, 11 * fl, 2.2, 1.8 * s1)
        b = tongue(u, v, 1.2, 11 / fl, 2.2, -1.8 * s1)
        front = np.sin(-v * 0.7 + f * 0.6) > 0
        parts += [(a[0] & ~(b[0] & front), a[1], "yin"), (b[0] & ~(a[0] & ~front), b[1])]
    elif kind == "beast":
        parts += [tongue(u, v, -2.3, 8 * fl, 1.6, -2.6, 1.6), tongue(u, v, 0, 11 * fl, 2.0, sw),
                  tongue(u, v, 2.3, 8 / fl, 1.6, 2.6, -1.6)]
    elif kind == "round":
        parts.append(tongue(u, v, 0, 8 * fl, 4.2, sw * 0.6))
    return parts


def flame(fr, i, x, y, s, f, a=1.0, lean=0.0, hot=0.0, light=1.0):
    """Flame i with its base at (x, y), scale s (1 is about 12 px tall)."""
    kind = FLAMES[i][2]
    sy, sx = _win(x - 9 * s, x + 9 * s, y - 16 * s, y + 4 * s)
    u = (XX[sy, sx] - x) / s
    v = (YY[sy, sx] - y) / s
    rag = 0.1 * np.sin(u * 1.7 + f * 0.9 + i) * np.sin(v * 1.3 - f * 1.1)
    tone = np.full(u.shape, -1)
    yin = np.zeros(u.shape, bool)
    union = np.zeros(u.shape, bool)
    for p in flame_shape(kind, u, v, f, i * 1.37, lean):
        m, q = p[0], p[1]
        tone = np.where(m, np.maximum(tone, tones_of(q + rag)), tone)
        union |= m
        if len(p) > 2:
            yin |= m
    if kind == "dark":
        tone[rim(union)] = 0
    ys, xs = np.nonzero(union)
    if len(ys):
        t = tone[ys, xs]
        rgb = np.where(yin[ys, xs][:, None], PAL_YIN[t], PAL[i][t])
        rgb = rgb * (1 - hot) + WHITE * hot
        fr.over(ys + sy.start, xs + sx.start, rgb, a * (0.72 if kind == "heart" else 1.0))
    k = light * a
    fr.glow(x, y - 4.5 * s, 4.5 * s, 0.24 * k, LHUE[i])
    fr.glow(x, y - 4.5 * s, 12 * s, 0.1 * k, LHUE[i])
    extras(fr, i, kind, x, y, s, f, a)


def extras(fr, i, kind, x, y, s, f, a):
    """Each flame's own secondary motion, in world px so it stays one pixel."""
    p = PAL[i]
    if kind == "leaf":
        for j in range(2):
            ph = (f * 0.05 + j * 0.5) % 1
            lx, ly = x + 4 * s * math.sin(ph * 6 + j * 2), y - (4 + 12 * ph) * s
            fr.dot(lx, ly, p[3], a * (1 - ph))
            fr.dot(lx + 1, ly - 1, p[2], a * (1 - ph))
            fr.glow(lx, ly, 3, 0.2 * a * (1 - ph), LHUE[i])
    elif kind == "frost":
        if (f + i) % 6 < 4:
            gx, gy = x + 4 * s * math.sin(f * 0.37 + i), y - 9 * s + 2 * math.cos(f * 0.5)
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                fr.dot(gx + dx, gy + dy, WHITE if dx == dy == 0 else p[3], a)
            fr.glow(gx, gy, 4, 0.3 * a, WHITE)
    elif kind == "bolt":
        r = np.random.default_rng(f // 2 * 31 + i)
        px, py = x, y - 8 * s
        ang = -math.pi / 2 + r.uniform(-1.2, 1.2)
        for _ in range(4):
            nx, ny = px + math.cos(ang) * 2.2 * s + r.uniform(-1, 1), py + math.sin(ang) * 2.2 * s
            line(fr, (px, py), (nx, ny), WHITE, p[3], a, a * 0.8)
            px, py = nx, ny
        fr.glow_line((x, y - 8 * s), (px, py), 4, 0.25 * a, hexf("#c8d8ff"))
    elif kind == "wind":
        for j in range(2):
            yy = y - (3 + 4 * j) * s
            line(fr, (x - (6 + 3 * j) * s, yy), (x - 2 * s, yy - 1), p[1], p[3], 0.0, 0.7 * a)
    elif kind == "rock":
        for dx in (-3, 2.5):
            rx, ry = x + dx * s, y + 0.5 * s
            fr.over(np.array([int(ry), int(ry), int(ry) + 1, int(ry) + 1]),
                    np.array([int(rx), int(rx) + 1, int(rx), int(rx) + 1]),
                    np.stack([hexf("#7a5040"), hexf("#3a2420"), hexf("#3a2420"), hexf("#1e1010")]), a)
        ph = (f * 0.08 + i * 0.3) % 1
        fr.dot(x + 2 * s * math.sin(ph * 9), y - (6 + 10 * ph) * s, p[3], a * (1 - ph))
    elif kind == "wisp":
        for j in range(2):
            ph = (f * 0.06 + j * 0.5) % 1
            fr.dot(x - (2 + 6 * ph) * s, y - (2 + 8 * ph) * s, p[3], a * (1 - ph) * 0.8)
    elif kind in ("tall", "wings", "beast", "swirl", "round", "dark", "spiky"):
        ph = (f * 0.07 + i * 0.37) % 1
        fr.dot(x + 3 * s * math.sin(ph * 7 + i), y - (10 + 8 * ph) * s, p[3], a * (1 - ph))


def line(fr, p0, p1, c0, c1, a0, a1):
    c0 = hexf(c0) if isinstance(c0, str) else np.asarray(c0, float)
    c1 = hexf(c1) if isinstance(c1, str) else np.asarray(c1, float)
    n = int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))) + 1
    t = np.linspace(0, 1, n)
    xs = np.round(p0[0] + (p1[0] - p0[0]) * t).astype(int)
    ys = np.round(p0[1] + (p1[1] - p0[1]) * t).astype(int)
    fr.over(ys, xs, c0[None] * (1 - t[:, None]) + c1[None] * t[:, None], a0 + (a1 - a0) * t)


def ellipse_line(fr, cx, cy, rx, ry, cols, a, phase=0.0, dash=None):
    """A 1 px ellipse; cols a list of rgb (21 segments by angle) or one rgb."""
    n = max(int(2 * math.pi * max(rx, 1) * 1.6), 12)
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    if dash:
        th = th[np.sin(th * dash + phase) > -0.2]
    ys = np.round(cy + ry * np.sin(th)).astype(int)
    xs = np.round(cx + rx * np.cos(th)).astype(int)
    if isinstance(cols, list):
        idx = (((th + phase) % (2 * math.pi)) / (2 * math.pi) * len(cols)).astype(int) % len(cols)
        rgb = np.stack(cols)[idx]
    else:
        rgb = cols
    fr.over(ys, xs, rgb, a)


# ---- lotus: 21 petals in three tiers round a vertical axis, seen from a little above ----
def petal_geom(j, cx, cy, K, spin, grow=1.0, big=False):
    for tier, (j0, j1) in enumerate(TIERS):
        if j0 <= j < j1:
            break
    n = j1 - j0
    th = 2 * math.pi * (j - j0) / n + spin + tier * 0.45
    tilt = [math.radians(60), math.radians(38), math.radians(14)][tier]
    if big:
        tilt = [math.radians(68), math.radians(44), math.radians(16)][tier]
    ln = [11.0, 11.5, 10.0][tier] * K * grow
    wd = [3.2, 2.9, 2.5][tier] * K * (0.4 + 0.6 * grow) * (0.72 if big else 1.0)
    rb = (3.0 - tier * 0.8) * K
    bx, bz = rb * math.cos(th), rb * math.sin(th)
    tx = bx + ln * math.sin(tilt) * math.cos(th)
    ty = ln * math.cos(tilt)
    tz = bz + ln * math.sin(tilt) * math.sin(th)
    base = (cx + bx, cy + bz * 0.38)
    tip = (cx + tx, cy - ty * 0.92 + tz * 0.38)
    return base, tip, wd, tz + bz, tier


def petal(fr, i, base, tip, wd, f, depth, a=1.0, hot=0.0, rag=0.0, lick=0.0):
    """A petal of flame i: a pointed leaf, hottest at its base, rimmed, its tip licking like a flame."""
    ex, ey = tip[0] - base[0], tip[1] - base[1]
    ln = math.hypot(ex, ey) or 1e-6
    ux, uy = ex / ln, ey / ln
    m = wd + 2 + lick
    sy, sx = _win(min(base[0], tip[0]) - m, max(base[0], tip[0]) + m, min(base[1], tip[1]) - m,
                  max(base[1], tip[1]) + m)
    X, Y = XX[sy, sx] - base[0], YY[sy, sx] - base[1]
    t = (X * ux + Y * uy) / ln
    s = -X * uy + Y * ux
    tc = np.clip(t, 0, 1)
    sway = lick * np.sin(tc * 3 - f * 0.8 + i) * tc ** 2
    w = wd * np.sin(np.pi * np.clip(t * 0.85 + 0.15, 0, 1)) ** 0.75 * (1 - 0.3 * tc)
    w = w * (1 + rag * np.sin(tc * 11 + f * 0.9 + i * 2.1))
    d = np.abs(s - sway) / np.maximum(w, 1e-3)
    mask = (d <= 1) & (t >= -0.05) & (t <= 1)
    if not mask.any():
        return
    q = 0.5 * d + 0.45 * tc + (0.0 if depth >= 0 else 0.16)
    tone = tones_of(q + 0.08 * np.sin(s * 1.9 + f) * tc)
    r = rim(mask)
    tone[r] = np.minimum(tone[r], 1 if depth >= 0 else 0)
    ys, xs = np.nonzero(mask)
    tt = tone[ys, xs]
    if FLAMES[i][2] == "yinyang":
        rgb = np.where((s[ys, xs] < 0)[:, None], PAL_YIN[tt], PAL[i][tt])
    else:
        rgb = PAL[i][tt]
    rgb = rgb * (1 - hot) + WHITE * hot
    fr.over(ys + sy.start, xs + sx.start, rgb, a)


def lotus(fr, cx, cy, K, spin, f, grows, hot=0.0, a=1.0, big=False, rag=0.0, lick=0.0, light=1.0, front=None):
    """Petals back to front; grows[j] is each petal's growth. front True or False draws only that half."""
    items = []
    for j in range(NF):
        g = grows[j]
        if g <= 0.01:
            continue
        base, tip, wd, z, tier = petal_geom(j, cx, cy, K, spin, g, big)
        items.append((z, j, base, tip, wd, tier))
    items.sort()
    for z, j, base, tip, wd, tier in items:
        if front is not None and (z >= 0) != front:
            continue
        i = SLOTS[j]
        petal(fr, i, base, tip, wd, f, z, a, hot, rag, lick)
        if light > 0:
            mid = lerp(base, tip, 0.6)
            fr.glow(*mid, max(wd * 1.4, 3), 0.1 * light * a, LHUE[i])
            fr.glow(*tip, max(wd * 2.5, 5), 0.06 * light * a, LHUE[i])


# ---- caster ----
def foot_at(f):
    rise = ease_io((f - 2) / 26.0)
    x, y = lerp(GROUND, HOVER, rise)
    recoil = 3 * math.exp(-((f - HURL0 - 2) / 4.0) ** 2)
    return x - recoil, y + math.sin(f * 0.26) * 2.0 * rise


FRONT_KEYS = [(0, "rest"), (8, "chest"), (28, "chest"), (36, "raise"), (SQUEEZE0, "raise"),
              (SQUEEZE0 + 5, "pull"), (HURL0 + 1, "point"), (100, "point"), (112, "rest"), (N, "rest")]
BACK_KEYS = [(0, "rest"), (10, "out"), (SQUEEZE0 + 4, "out"), (HURL0 + 1, "behind"), (104, "behind"),
             (114, "out"), (N, "out")]


def lotus_center(f, foot):
    return foot[0] + 8.0, foot[1] - 46.0


ORBIT_R, ORBIT_TILT = 31.0, 0.34    # orbit radius round the waist and how much of it shows as depth
ORBIT_SPIN = 2 * math.pi * 0.45 / FPS  # 0.45 turns a second


def orbit_pos(i, f, foot, e=0.0):
    """Flame i on its 3D orbit round the body: (x, y, depth). e (0..1) pulls it up and in toward the lotus."""
    th = 2 * math.pi * i / NF + f * ORBIT_SPIN + 2 * math.pi * 1.25 * e
    h = 18 + 1.5 * math.sin(f * 0.25 + i * 0.9)
    h = h + (46 - h) * e
    r = ORBIT_R + (5 - ORBIT_R) * e
    return foot[0] + 2 + r * math.cos(th), foot[1] - h + r * ORBIT_TILT * math.sin(th), math.sin(th)


def appear_t(i):
    return SUMMON0 + 5 + (NF - 1 - i) * APPEAR_STEP          # rank 23 (last index) ignites first


def gather_t(i):
    return FUSE0 + (NF - 1 - i) * GATHER_STEP


def lotus_spin(f):
    return f * 0.035 + 0.9 * ease_io((f - SQUEEZE0) / SQUEEZE_N) + max(0, f - HURL0) * 0.25


def flame_state(i, f, foot):
    """Where flame i is and how it looks: (x, y, scale, alpha, depth), or None before it ignites or once a petal."""
    a0 = appear_t(i)
    if f < a0:
        return None
    g0 = gather_t(i)
    grow = eout((f - a0) / 5.0)
    if f <= g0:
        x, y, z = orbit_pos(i, f, foot)
        return x, y, (0.25 + 0.65 * grow) * (0.85 + 0.15 * z), grow * (0.8 + 0.2 * z), z
    t = (f - g0) / GATHER_T
    if t >= 1:
        return None
    e = ease_io(t)
    x, y, z = orbit_pos(i, f, foot, e)
    base, tip, _, _, _ = petal_geom(SLOT_OF[i], *lotus_center(f, foot), 1.6, lotus_spin(f), 1.0)
    end = lerp(base, tip, 0.3)
    w = e ** 4                                                       # land on the petal's slot at the end
    x, y = x + (end[0] - x) * w, y + (end[1] - y) * w
    return x, y, (0.9 - 0.35 * e) * (0.85 + 0.15 * z), 0.8 + 0.2 * max(z, w), z if w < 0.5 else 1.0


def petal_grow(j, f):
    return eout((f - gather_t(SLOTS[j]) - GATHER_T + 2) / 5.0)


# ---- impact pieces ----
EMBERS = []
for n in range(63):
    ang = rng.uniform(math.radians(15), math.radians(165))
    sp = rng.uniform(1.2, 3.4)
    EMBERS.append(dict(i=n % NF, t0=IMPACT + 1 + rng.uniform(0, 7), x=T[0] + rng.uniform(-10, 10),
                       y=T[1] - rng.uniform(3, 14), vx=math.cos(ang) * sp, vy=-math.sin(ang) * sp,
                       life=rng.uniform(14, 34), big=n % 4 == 0))
SMOKES = [dict(t0=IMPACT + 5 + k * 1.3, x=T[0] + rng.uniform(-22, 22), y=T[1] - rng.uniform(4, 22),
               r0=rng.uniform(3, 5), r1=rng.uniform(9, 14), vy=rng.uniform(0.35, 0.7), vx=rng.uniform(-0.25, 0.25))
          for k in range(10)]
STREAKS = [(rng.uniform(0, 2 * math.pi), rng.uniform(18, 34)) for _ in range(14)]
SPARKS = [dict(i=n % NF, t0=IMPACT + rng.uniform(0, 3), a=rng.uniform(math.radians(-10), math.radians(190)),
               sp=rng.uniform(5.5, 9.5), life=rng.uniform(7, 14)) for n in range(84)]
_c0 = lotus_center(HURL0, foot_at(HURL0))
FALL_FROM = (_c0[0] - 3, _c0[1] + 1)
FALL_TO = (T[0], T[1] - 6)
TRAIL = [dict(tau=k / 26, x=rng.uniform(-2, 2), y=rng.uniform(-2, 2), i=SLOTS[k * 5 % NF]) for k in range(2, 26)]


def spark_at(e, f):
    t = f - e["t0"]
    if t < 0 or t > e["life"]:
        return None
    k = (1 - 0.82 ** t) / 0.18
    vx, vy = math.cos(e["a"]) * e["sp"], -math.sin(e["a"]) * e["sp"] * 0.75
    x, y = T[0] + vx * k, T[1] - 8 + vy * k + 0.12 * t * t
    dv = 0.82 ** t
    return (x, y), (x - vx * dv * 1.2, y - vy * dv * 1.2), 1 - t / e["life"]


def trail_smoke(fr, f):
    """Smoke and cooling motes left along the throw, drifting up after the lotus has passed."""
    for tr in TRAIL:
        age = f - (HURL0 + FALL_N * tr["tau"])
        if age < 0:
            continue
        x, y = lerp(FALL_FROM, FALL_TO, tr["tau"] ** 1.7)
        x, y = x + tr["x"] + 0.15 * age, y + tr["y"] - 0.3 * age
        k = 1 - ease_io(age / 28.0)
        if k <= 0.01:
            continue
        puff(fr, x, y, 2.5 + 3.5 * eout(age / 14.0), 0.38 * k)
        if age < 10:
            fr.dot(x + 1, y + 2, PAL[tr["i"]][3], 1 - age / 10)
            fr.glow(x + 1, y + 2, 4, 0.2 * (1 - age / 10), LHUE[tr["i"]])


def ember_at(e, f):
    t = f - e["t0"]
    if t < 0 or t > e["life"]:
        return None
    drag = 0.95
    k = (1 - drag ** t) / (1 - drag)
    x = e["x"] + e["vx"] * k
    y = min(e["y"] + e["vy"] * k + 0.09 * t * t, GROUND_Y)
    return x, y, 1 - t / e["life"]


def puff(fr, x, y, r, a):
    sy, sx = _win(x - r, x + r, y - r, y + r)
    X, Y = XX[sy, sx], YY[sy, sx]
    m = np.hypot(X - x, (Y - y) * 1.1) <= r * (1 + 0.12 * np.sin(np.arctan2(Y - y, X - x) * 5 + x))
    s = (X - x) + (Y - y)
    tone = np.where(s < -r * 0.35, 2, np.where(s > r * 0.45, 0, 1))
    ys, xs = np.nonzero(m)
    fr.over(ys + sy.start, xs + sx.start, np.stack([hexf(c) for c in SMOKE])[tone[ys, xs]], a)


def fireball(fr, x, y, r, f, cool):
    sy, sx = _win(x - r - 2, x + r + 2, y - r - 2, y + r + 2)
    X, Y = XX[sy, sx] - x, YY[sy, sx] - y
    ang = np.arctan2(Y, X)
    rr = r * (1 + 0.16 * np.sin(ang * 5 + f * 0.7) + 0.08 * np.sin(ang * 9 - f * 1.1))
    d = np.hypot(X, Y) / rr
    lx, ly = X / r + 0.35, Y / r + 0.35            # hottest toward the top left
    q = 0.44 * np.hypot(lx, ly) + 0.4 * d + cool
    tone = tones_of(q)
    ys, xs = np.nonzero(d <= 1)
    fr.over(ys + sy.start, xs + sx.start, PAL_FUSED[tone[ys, xs]], 1.0)


def impact(fr, f):
    dt = f - IMPACT
    # ground scorch, under everything
    sc_k = ease_io(dt / 3.0) * (1 - 0.6 * ease_io((dt - 10) / 20.0))
    sy, sx = _win(T[0] - 34, T[0] + 34, GROUND_Y - 8, GROUND_Y + 8)
    d = np.hypot((XX[sy, sx] - T[0]) / 32, (YY[sy, sx] - GROUND_Y) / 6.5)
    ys, xs = np.nonzero(d <= 1)
    fr.over(ys + sy.start, xs + sx.start, hexf("#2a1418"), 0.55 * sc_k * (1 - d[ys, xs] ** 2))
    for n in range(NF):
        cxk = T[0] + 28 * math.cos(n * 2.4) * ((n * 0.37) % 1)
        cyk = GROUND_Y + 5 * math.sin(n * 2.4) * ((n * 0.37) % 1)
        kk = sc_k * (0.5 + 0.5 * math.sin(f * 0.5 + n))
        if kk > 0.15:
            fr.dot(cxk, cyk, PAL[n][3], kk)
            fr.glow(cxk, cyk, 4, 0.18 * kk, LHUE[n])
    fr.glow(T[0], GROUND_Y, 36, 0.18 * sc_k, hexf("#ff7040"), flat=0.3)

    # the shock ring on the ground, its segments in the 21 colours
    if dt <= 12:
        s = eout(dt / 12.0)
        rx = 8 + 56 * s
        ellipse_line(fr, T[0], GROUND_Y, rx, rx * 0.17, hexf("#ffe8a8"), (1 - s) ** 1.2)
        ellipse_line(fr, T[0], GROUND_Y + 1, rx + 3, (rx + 3) * 0.17, LHUE, 0.85 * (1 - s) ** 1.5, phase=0.3)
        fr.glow_ring(T[0], GROUND_Y, rx, 4, 0.45 * (1 - s), hexf("#ffe0b0"), flat=0.17)
        fr.glow_ring(T[0], GROUND_Y, rx, 12, 0.15 * (1 - s), hexf(GOLD_L), flat=0.2)

    # the ground lotus: back petals, fireball, front petals
    bloom = eout(dt / 4.0)
    fall = ease_io((dt - 8) / 12.0)
    grows = [bloom * (1 + 0.25 * fall)] * NF
    K = 3.5 * (1 - 0.15 * fall)
    a_l = 1 - ease_io((dt - 12) / 9.0)
    rag = 0.18 + 0.4 * fall
    spin = 0.3 + dt * 0.02
    hot = 0.55 * math.exp(-dt / 2.5)
    if a_l > 0.01:
        lotus(fr, T[0], T[1], K, spin, f, grows, hot, a_l, True, rag, 2.5, 0.7, front=False)
    if dt <= 16:
        rise = eout(dt / 16.0)
        r = 7 + 9 * eout(dt / 5.0) - 5 * ease_io((dt - 10) / 6.0)
        fireball(fr, T[0], T[1] - 8 - 22 * rise, r, f, 0.25 * ease_io((dt - 6) / 10.0))
        fr.glow(T[0], T[1] - 8 - 22 * rise, r * 1.4, 0.5 * (1 - rise * 0.6), hexf("#fff0d0"))
    if a_l > 0.01:
        lotus(fr, T[0], T[1], K, spin, f, grows, hot, a_l, True, rag, 2.5, 0.7, front=True)

    # the flash and its streaks on the peak
    if dt <= 2:
        rr = [10, 16, 9][dt]
        sy, sx = _win(T[0] - rr, T[0] + rr, T[1] - 8 - rr, T[1] - 8 + rr)
        dd = np.hypot(XX[sy, sx] - T[0], YY[sy, sx] - T[1] + 8) / rr
        ys, xs = np.nonzero(dd <= 1)
        fr.over(ys + sy.start, xs + sx.start, WHITE, [1.0, 0.8, 0.4][dt])
        for n, (ang, ln) in enumerate(STREAKS):
            ln2 = ln * (0.6 + 0.4 * dt)
            p0 = (T[0] + math.cos(ang) * rr * 0.8, T[1] - 8 + math.sin(ang) * rr * 0.6)
            p1 = (T[0] + math.cos(ang) * ln2, T[1] - 8 + math.sin(ang) * ln2 * 0.6)
            line(fr, p0, p1, WHITE, LHUE[n * 3 % NF], 1.0 - 0.3 * dt, 0.0)
        fr.glow(T[0], T[1] - 8, 22, [1.0, 0.8, 0.4][dt], WHITE)

    for e in SPARKS:
        st = spark_at(e, f)
        if st is None:
            continue
        p1, p0, k = st
        line(fr, p0, p1, PAL[e["i"]][3], WHITE, 0.0, min(1, k * 1.6))
        fr.glow(*p1, 3, 0.25 * k, LHUE[e["i"]])

    for e in EMBERS:
        st = ember_at(e, f)
        if st is None:
            continue
        x, y, k = st
        col = PAL[e["i"]][3] if k > 0.5 else PAL[e["i"]][2]
        fr.dot(x, y, WHITE if k > 0.85 else col, min(1, k * 1.5))
        if e["big"]:
            fr.dot(x + 1, y, col, min(1, k * 1.5))
        fr.glow(x, y, 3, 0.3 * k, LHUE[e["i"]])
        fr.glow(x, y, 8, 0.08 * k, LHUE[e["i"]])

    for sm in SMOKES:
        t = f - sm["t0"]
        if t < 0:
            continue
        k = min(1, t / 4) * (1 - 0.7 * ease_io(t / 24.0))
        r = sm["r0"] + (sm["r1"] - sm["r0"]) * eout(t / 20.0)
        puff(fr, sm["x"] + sm["vx"] * t, sm["y"] - sm["vy"] * t, r, 0.42 * k)


def hand_lotus(fr, f, c):
    grows = [petal_grow(j, f) for j in range(NF)]
    hot, K = 0.0, 1.6
    cx, cy = c
    if f >= SQUEEZE0:
        s = ease_io((f - SQUEEZE0) / SQUEEZE_N)
        K, hot = 1.6 * (1 - 0.4 * s), 0.55 * s
        cx, cy = cx - 3 * s, cy + 1 * s
    if f >= HURL0:
        t = (f - HURL0) / FALL_N
        p = lerp((cx, cy), (T[0], T[1] - 6), t ** 1.7)
        for k in range(1, 9):              # the trail: puffs in petal colours, shrinking and cooling
            q = lerp((cx, cy), (T[0], T[1] - 6), max(t - k * 0.06, 0) ** 1.7)
            flame(fr, SLOTS[(k * 3 + f) % NF], q[0], q[1] + 3, 0.75 - k * 0.07, f, 0.9 - k * 0.08, lean=-2.0,
                  light=0.35)
        tail = lerp((cx, cy), (T[0], T[1] - 6), max(t - 0.35, 0) ** 1.7)
        line(fr, tail, p, "#ffd080", WHITE, 0.0, 0.9)
        fr.glow_line(tail, p, 6, 0.35, hexf("#fff0c0"))
        fr.glow_line(tail, p, 18, 0.16, hexf(GOLD_L))
        cx, cy = p
        K, hot = 1.0 + 0.2 * t, 0.55 - 0.25 * t
    lotus(fr, cx, cy, K, lotus_spin(f), f, grows, hot=hot, lick=0.6)
    done = sum(grows) / NF
    if done > 0.02:
        core = 3 * K * done
        sy, sx = _win(cx - 5, cx + 5, cy - 7, cy + 3)
        dd = np.hypot(XX[sy, sx] - cx, (YY[sy, sx] - cy + 2 * K) * 1.3)
        ys, xs = np.nonzero(dd <= core)
        fr.over(ys + sy.start, xs + sx.start, hexf("#fff8e0") * (1 - hot) + WHITE * hot, 1.0)
        fr.glow(cx, cy - 3 * K, 5 * K, 0.25 * done + 0.4 * hot, hexf("#fff4d0"))
        fr.glow(cx, cy - 3 * K, 30, 0.1 * done + 0.2 * hot, hexf(GOLD_L))
    fuse = ease_io((f - FUSE0) / 8.0) * (1 - ease_io((f - HURL0) / 4.0))
    fr.glow(c[0], c[1], 40, 0.12 * fuse, hexf(GOLD_L), flat=0.9)


def draw(f):
    fr = Frame()
    foot = foot_at(f)
    c = lotus_center(f, foot)
    jab = math.exp(-((f - HURL0 - 1) / 2.0) ** 2) * 3.0
    pose = cs.pose_at(f, FRONT_KEYS, BACK_KEYS, cs.aim_from(foot, SC, T), jab)
    nxt = foot_at(f + 1)
    speed = math.hypot(nxt[0] - foot[0], nxt[1] - foot[1])
    blast = math.exp(-(f - IMPACT) / 8.0) if f >= IMPACT else 0.0
    lift = min(1.0, 0.35 + speed * 0.5 + 0.3 * (FUSE0 <= f < HURL0) + 0.4 * blast)
    flut = min(1.0, 0.4 + speed * 0.4 + 0.4 * blast)
    charge = ease_io((f - 4) / 40.0) * (1 - 0.5 * ease_io((f - 100) / 15.0))

    states = []
    for i in range(NF):
        st = flame_state(i, f, foot)
        if st is not None:
            states.append((st[4], i, st))
    states.sort()

    def draw_flame(i, st):
        x, y, s, a, _ = st
        g0 = gather_t(i)
        if f > g0:                        # a short trail of shrinking puffs behind a travelling flame
            for k in (2, 4):
                pst = flame_state(i, f - k, foot)
                if pst is not None and f - k > g0:
                    flame(fr, i, pst[0], pst[1], pst[2] * (0.7 - 0.12 * k), f - k, 0.45 - 0.08 * k, light=0.3)
        if f <= g0 + GATHER_T * 0.7:      # a 1 px arc behind it along the orbit
            for k in range(1, 6):
                pst = flame_state(i, f - k * 0.4, foot)
                if pst is not None:
                    fr.dot(pst[0], pst[1] - 3 * pst[2], PAL[i][3] if k < 3 else PAL[i][2], 0.75 * a * (1 - k / 6))
        flame(fr, i, x, y, s, f, a, lean=-1.5 if f > g0 else 0.0)
        a0 = appear_t(i)
        if 0 <= f - a0 < 4:               # ignition flash
            k = 1 - (f - a0) / 4
            fr.glow(x, y - 4, 9, 0.5 * k, LHUE[i])
            fr.dot(x, y - 4, WHITE, k)

    for z, i, st in states:
        if z < 0:
            draw_flame(i, st)

    Ls = np.zeros((H, W))
    g = cs.draw(fr.over, (H, W), foot, SC, pose, f, lift, flut, hair="loose")
    cs.body_light(Ls, g, charge)
    point = ease_io((f - HURL0) / 2.0) * (1 - ease_io((f - 100) / 6.0))
    if point > 0.01:
        cs.finger_light(Ls, g, point, jab / 3.0)
        fr.dot(*g["finger"], WHITE)
    fr.fold(Ls * 0.5, hexf(GOLD_L))

    for z, i, st in states:
        if z >= 0:
            draw_flame(i, st)

    if f >= HURL0:
        trail_smoke(fr, f)
    if f < IMPACT:
        hand_lotus(fr, f, c)
    else:
        impact(fr, f)

    # scene pools: round the caster while charging, along the throw, over the field on the impact
    scene = ease_io((f - 4) / 20.0) * (1 - 0.5 * ease_io((f - IMPACT) / 10.0))
    fr.glow(foot[0] + 8, foot[1] - 28, 50, 0.06 * scene, hexf(GOLD_L), flat=0.95)
    if f >= HURL0:
        mid = lerp(c, T, 0.5)
        fr.glow(mid[0], mid[1], 80, 0.12 * ease_io((f - HURL0) / 6.0) * (1 - ease_io((f - IMPACT - 6) / 10.0)),
                hexf(GOLD_L), flat=0.8)
    if f >= IMPACT:
        dt = f - IMPACT
        fr.glow(T[0] - 6, T[1] - 24, 82, 0.2 + 0.4 * math.exp(-dt / 3.0) - 0.08 * ease_io((dt - 14) / 16.0),
                hexf("#ffb070"), flat=0.7)
    return fr


def main():
    OUT.mkdir(exist_ok=True)
    cols, lights, comps, ok = [], [], [], True
    covers, means = [], []
    for f in range(N):
        fr = draw(f)
        col = (np.clip(fr.rgba(), 0, 1) * 255).round().astype(np.uint8)
        Lc = np.clip(fr.L, 0, 1)
        light = fr.light_rgb()
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
    print(f"light cover {cv:.0%}  mean {mn:.3f}  (strong: 75-95%, 0.12-0.18)")
    if not (0.75 <= cv <= 0.95 and 0.12 <= mn <= 0.18):
        print("light outside the strong row")
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
    pick = [8, 20, 32, 44, 56, 66, 76, 84, 89, 92, 98, 119]
    for bg, tag in (("#101018", "dark"), ("#5a6070", "mid")):
        flat = [pfx.composite(cols[i], lights[i], bg) for i in range(N)]
        grid(flat, OUT / f"{NAME}_contact4x_{tag}.png", pick, n=4, scale=4)
    for i in (32, 70, 77, 90, 96):
        Image.fromarray(pfx.composite(cols[i], lights[i], "#101018"), "RGBA").resize(
            (W * 4, H * 4), Image.NEAREST).save(OUT / f"{NAME}_f{i:03d}_x4.png")
    pfx.gif(comps, OUT / f"{NAME}.gif", FPS, scale=2)
    meta = dict(name=NAME, w=W, h=H, frames=N, fps=FPS, cols=ncol, loop=False, pivot=list(GROUND),
                target=list(T), glow="strong", light_gain=1.0,
                states=dict(summon=[SUMMON0, FUSE0 - 1], fuse=[FUSE0, SQUEEZE0 - 1], squeeze=[SQUEEZE0, HURL0 - 1],
                            hurl=[HURL0, FADE0 - 1], fade=[FADE0, N - 1]),
                flames=[dict(rank=r, name=nm, kind=k) for r, nm, k, _ in FLAMES],
                sheets=dict(composite=f"{NAME}.png", color=f"{NAME}_color.png", light=f"{NAME}_light.png"))
    (OUT / f"{NAME}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
