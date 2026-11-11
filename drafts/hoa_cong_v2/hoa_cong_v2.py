"""Fire Attack, the redraw of drafts/hoa_cong: a volley of about 120 fire arrows glints high at the upper left and
rains down on an army camp (tents, a palisade of stakes, a watch tower, banners, crates). Each arrow that sticks
lights a small flame; the burn spreads over cloth and wood, the fires gather into a few big blazes behind the tents
with small licks between them, under one rolling smoke column, then sink to charred frames, glowing stakes and smoke.
No explosion. 240x200, 108 frames at 24 fps, one-shot that holds on the burnt camp, side view, soft style,
glow medium, clarity hazy, no caster.

What changed from hoa_cong (each was a fault in the first draw):
  flames   one flame per 6 px column, all near one height, each with its own dark rim (a row of cones). Now seven
           fire sites sized big, medium or small by what burns there, each a cluster of one main tongue and side
           tongues, summed into one heat field per layer and banded once, so a blaze is one mass with one core.
           The big blazes stand between the palisade and the tents, which read as dark shapes against them.
  smoke    34 puffs each split in three tones along a diagonal and stacked at 34 % alpha, so the seams showed as
           stripes. Now every puff goes into one shade map (kit puffs, lit from the top left, breaking into dots as
           they age) and the map is laid once at one alpha.
  camp     embers and cloth holes picked per pixel from white noise, so the burning camp turned to speckle. Now both
           come from a clumped noise, char keeps three tones, and the burnt frame keeps a warm rim on its lit side.
  framing  the camp sat in the right 60 % of a 320 px cell so the arrows could run in from the left. The arrows now
           fall steeper and the cell is 240 px with the camp near its middle: a quarter less sheet.

States (frames, 24 fps):
  signal    0-11   the first fire arrows come in from afar as glints high at the upper left, the sky glows
  rain      0-58   about 120 fire arrows, each on one path from a far glint into the camp, speeding up
  ignite   20-69   each hit lights a flame; the burn spreads from the hit points, climbing faster than it falls
  blaze    70-91   the big fires roar behind the tents under the smoke column, embers rise
  burndown 92-107  flames sink, charred tent frames and glowing stakes remain under smoke
"""
import math
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "kit"))
import export as ex  # noqa: E402
import facing as fc  # noqa: E402
import fxkit as fk  # noqa: E402
import light as lt  # noqa: E402
import pfx  # noqa: E402

NAME = "hoa_cong_v2"
W, H, N, FPS = 240, 200, 108, 24
SEED = 7
OUT = HERE / "out"
GLOW = "medium"

SIGNAL0, SIGNAL_N = 0, 12
RAIN0 = SIGNAL0 + SIGNAL_N
LAUNCH_LAST = RAIN0 + 34
IGNITE0 = 20
BLAZE0 = 70
BURN0 = 92
STATES = dict(signal=[SIGNAL0, RAIN0 - 1], rain=[SIGNAL0, 58], ignite=[IGNITE0, BLAZE0 - 1],
              blaze=[BLAZE0, BURN0 - 1], burndown=[BURN0, N - 1])

GROUND_Y = 172.0
PIVOT = (136, 172)                   # the middle of the camp, on the ground
CAMP = (52.0, 216.0)
APEX_Y = 16.0
SLANT = math.radians(72)
NA = 120
ALEN = 14.0
LEAN = 0.10                          # every flame leans this share of its height downwind (to the right)

FIRE = ["#7a1c12", "#c83a1a", "#f07c22", "#ffc852", "#fff3c4"]   # dark flame edge to pale core
WOOD = ["#3a2418", "#7a5030", "#c09058"]
SMOKE = ["#3e3438", "#625656", "#8a7c72", "#5c3226", "#8a4c30", "#b06c3e"]  # 3 tones, then the same lit by the fire
SMOKE_A = 0.6                        # the one alpha of the whole smoke layer
CLOTH = ["#3a2a1c", "#7a5e3c", "#a8875a", "#d8bb84"]
TIMBER = ["#2a1a10", "#5a3c22", "#8a6438", "#b89060"]
FLAG = ["#4a0c0c", "#8a1a16", "#c83224", "#e86a40"]
CHAR = ["#24140e", "#472818", "#6a3a20"]                        # burnt cloth and timber: shadow, body, lit face
LIGHT_RAMP = ["#5a1008", "#e05018", "#ffc060", "#ffffff"]


def hexf(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


PF = np.stack([hexf(c) for c in FIRE])
PW = np.stack([hexf(c) for c in WOOD])
PC = np.stack([hexf(c) for c in CLOTH])
PT = np.stack([hexf(c) for c in TIMBER])
PG = np.stack([hexf(c) for c in FLAG])
PCH = np.stack([hexf(c) for c in CHAR])
WHITE = np.ones(3)
YY, XX = np.mgrid[0:H, 0:W].astype(float)
_GRID = np.random.default_rng(5).random((64, 64))


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
    ex_, ey = b[0] - a[0], b[1] - a[1]
    h = np.clip(((X - a[0]) * ex_ + (Y - a[1]) * ey) / (ex_ * ex_ + ey * ey or 1e-9), 0, 1)
    return np.hypot(X - a[0] - ex_ * h, Y - a[1] - ey * h)


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

    def rgba(self):
        return np.dstack([self.rgb, self.a])


def line(fr, p0, p1, c0, c1, a0, a1):
    n = int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))) + 1
    t = np.linspace(0, 1, n)
    xs = np.round(p0[0] + (p1[0] - p0[0]) * t).astype(int)
    ys = np.round(p0[1] + (p1[1] - p0[1]) * t).astype(int)
    fr.over(ys, xs, c0[None] * (1 - t[:, None]) + c1[None] * t[:, None], a0 + (a1 - a0) * t)


# ---- fire: every tongue adds to one heat field per layer, and the field is banded into tones once ----
def heat_tones(h):
    return np.select([h > 0.8, h > 0.62, h > 0.44, h > 0.27], [4, 3, 2, 1], 0)


def tongue(F, cx, by, hgt, hw, f, seed, sway=3.0, cool=0.0, fork=0.0):
    """One flame tongue added to heat field F (kept where it is hotter): hottest low in the middle, narrowing to a
    tip that leans downwind, its rim torn by noise that rises with the frame. fork splits the upper half of a big
    flame into two tips that trade height, so it never ends in one spike."""
    if hgt < 1.5 or hw < 0.6:
        return
    lean = LEAN * hgt
    sy, sx = _win(cx - hw * 1.8 - sway, cx + hw * 1.8 + sway + lean, by - hgt * 1.25, by + 1)
    X, Y = XX[sy, sx], YY[sy, sx]
    s = (by - Y) / hgt
    sc = np.clip(s, 0, 1)
    axis = cx + sway * np.sin(Y * 0.09 - f * 0.4 + seed) * sc + lean * sc * sc
    w = hw * (1 - 0.86 * sc ** 1.35) + 0.5
    u = (X - axis) / w
    n = 0.6 * vnoise(X * 0.09 + seed * 7, Y * 0.09 + f * 0.6) + 0.4 * vnoise(X * 0.23 + seed, Y * 0.2 + f * 1.05)
    heat = (1 - np.abs(u)) * (1.1 - 0.62 * sc) + (n - 0.5) * (0.55 + 0.6 * sc) - np.maximum(s - 1, 0) * 2.4 - cool
    heat = heat + 0.08 * np.clip(-u, -1, 1) * (1 - sc)          # the pale core sits toward the top left light
    if fork:
        split = 0.18 * math.sin(f * 0.3 + seed)                 # the gap wanders, so the two tips trade height
        heat = heat - fork * np.clip((sc - 0.45) / 0.4, 0, 1) * np.clip(1 - np.abs(u - split) * 3.2, 0, 1)
    heat = np.where(Y <= by, heat, -1.0)
    np.maximum(F[sy, sx], heat, out=F[sy, sx])


def cluster(F, cx, by, hgt, hw, f, seed, sides):
    """A fire as one main tongue and its side tongues (dx, height share, width share), each on its own beat."""
    for k, (dx, hs, ws) in enumerate(sides):
        beat = 0.82 + 0.18 * math.sin(f * 0.55 + seed * 3.1 + k * 2.3)
        tongue(F, cx + dx * hw, by + 1.5, hgt * hs * beat, hw * ws, f, seed + 11.7 * (k + 1), sway=2.0)
    tongue(F, cx, by, hgt * (0.9 + 0.1 * math.sin(f * 0.42 + seed)), hw, f, seed, sway=3.0,
           fork=0.9 if hw > 8 else 0.0)


def paint_fire(fr, F, a=1.0):
    ys, xs = np.nonzero(F > 0.12)
    if len(ys):
        fr.over(ys, xs, PF[heat_tones(F[ys, xs])], a)


# ---- the camp: material, tone and a clumped noise per pixel (0 none, 1 cloth, 2 timber, 3 crate) ----
MAT = np.zeros((H, W), np.int8)
TONE = np.zeros((H, W), np.int8)
POLE = np.zeros((H, W), bool)
CN = vnoise(XX * 0.21 + 3.0, YY * 0.21 + 9.0)                   # clumps about 5 px across: holes and embers
CB = vnoise(XX * 0.06 + 17.0, YY * 0.06 + 5.0)                  # patches about 16 px across: how the blaze fills in
TENTS = [(94.0, 34.0, 30.0), (134.0, 50.0, 44.0), (174.0, 36.0, 32.0), (203.0, 22.0, 22.0)]   # x, width, height
TOWER = (62.0, 104.0)                # middle x and roof top y of the watch tower
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
    for cx, w, h in ((112.0, 7, 6), (154.0, 6, 5), (186.0, 8, 6)):  # crates
        m = (X >= cx) & (X < cx + w) & (Y > GROUND_Y - h) & (Y <= GROUND_Y)
        tone = np.full(X.shape, 2, np.int8)
        tone[(X == cx) | (Y == GROUND_Y - h + 1)] = 3
        tone[(X == cx + w - 1) | (Y == GROUND_Y)] = 1
        tone[np.abs((X - cx) - (Y - (GROUND_Y - h)) * w / h) < 0.7] = 0
        _paint(m, 3, tone)


_build_camp()
CY, CX = np.nonzero(MAT > 0)
BEHIND = (MAT[CY, CX] == 2) & ~POLE[CY, CX]      # the palisade and the tower stand behind the fires; tents in front
# the lit rim of the burnt camp: a camp pixel with nothing of the camp up and to its left
_solid = MAT > 0
_closed = _solid | np.roll(_solid, 1, axis=1) | np.roll(_solid, 2, axis=1)     # the gaps between stakes closed
RIM = _solid & ~np.roll(_closed, 1, axis=0) & ~np.roll(np.roll(_closed, 1, axis=0), 1, axis=1)
FLAGS = [dict(pole=(TOWER[0], TOWER[1] + 1), top=TOWER[1] - 16, w=11, h=6),
         dict(pole=(134.0, GROUND_Y - 47), top=GROUND_Y - 62, w=11, h=6),
         dict(pole=(174.0, GROUND_Y - 35), top=GROUND_Y - 48, w=9, h=5)]

# The fires, by what burns there. x and base of the fire, the span of the camp whose burn feeds it, its full height
# and half width, whether it stands behind the tents (they read against it), and its side tongues
# (dx in half widths, height share, width share). Three sizes on purpose: two big, three medium, two small.
SITES = [
    dict(x=137.0, base=162.0, span=(114, 158), hgt=66.0, hw=17.0, back=True,       # behind the great tent: the biggest
         sides=((-1.1, 0.5, 0.5), (1.05, 0.68, 0.55), (0.3, 0.4, 0.4))),
    dict(x=62.0, base=117.0, span=(50, 76), hgt=36.0, hw=7.5, back=False,          # the tower cabin: tall and thin
         sides=((-1.3, 0.5, 0.6), (1.25, 0.34, 0.55))),
    dict(x=92.0, base=160.0, span=(78, 110), hgt=38.0, hw=11.0, back=True,         # behind the left tent
         sides=((1.1, 0.5, 0.55), (-1.05, 0.36, 0.5))),
    dict(x=177.0, base=160.0, span=(160, 192), hgt=46.0, hw=12.0, back=True,       # behind the right tent
         sides=((-1.1, 0.42, 0.55), (1.05, 0.6, 0.55))),
    dict(x=205.0, base=158.0, span=(194, 214), hgt=22.0, hw=6.0, back=True,        # the small tent at the end
         sides=((-1.1, 0.5, 0.6),)),
    dict(x=115.0, base=168.0, span=(108, 122), hgt=15.0, hw=4.5, back=False,       # the crates in front
         sides=((1.3, 0.55, 0.6),)),
    dict(x=188.0, base=168.0, span=(182, 196), hgt=12.0, hw=4.0, back=False,
         sides=()),
]


@lru_cache(maxsize=4)
def scene(seed):
    """Everything a seed decides: where and when each arrow lands, the embers, the smoke puffs and the small licks."""
    rng = np.random.default_rng(seed)
    arrows = []
    launch = SIGNAL0 - 1 + (LAUNCH_LAST - SIGNAL0 + 1) * np.sort(rng.beta(1.4, 1.8, NA))
    for n in range(NA):
        gx = rng.uniform(CAMP[0] + 2, CAMP[1] - 4)
        col = np.nonzero(MAT[:, int(gx)] > 0)[0]
        if len(col) and rng.random() < 0.75:
            gy = float(rng.choice(col)) + 0.5
        else:
            gy = GROUND_Y + rng.uniform(-2, 8)
        ang = SLANT + rng.uniform(-0.07, 0.07)
        sy0 = APEX_Y + rng.uniform(-4, 8)
        dx = (gy - sy0) / math.tan(ang)
        if gx - dx < 10:                                          # enter the cell inside its left margin
            sy0 += (10 - (gx - dx)) * math.tan(ang)
            dx = gx - 10
        fly = rng.uniform(11, 13) * (gy - sy0) / (gy - APEX_Y)
        onobj = bool(len(col)) and gy < GROUND_Y - 0.6
        arrows.append(dict(t0=float(launch[n]), fly=fly, start=(gx - dx, sy0), end=(gx, gy), ang=ang,
                           sink=rng.uniform(3.0, 5.0), ph=rng.uniform(0, 6.28), fh=rng.uniform(5, 8),
                           seed=rng.uniform(0, 50), onobj=onobj,
                           # an arrow in open ground burns out by itself; about one in twelve catches the grass and stays lit
                           burn=1e9 if rng.random() < 0.08 else rng.uniform(5, 12)))
    for a in arrows:
        a["land"] = a["t0"] + a["fly"]
    big = [s for s in SITES if s["hgt"] > 30]
    embers = []
    for _ in range(190):                                          # embers rise off the fires, most off the big ones
        s = big[int(rng.integers(len(big)))] if rng.random() < 0.8 else SITES[int(rng.integers(len(SITES)))]
        embers.append(dict(t0=rng.uniform(30, N - 8), x=s["x"] + rng.normal(0, s["hw"] * 0.9), y0=s["base"] - rng.uniform(0.2, 0.9) * s["hgt"],
                           vy=rng.uniform(0.9, 2.2), vx=rng.uniform(0.0, 1.5), ph=rng.uniform(0, 6.28),
                           life=rng.uniform(10, 24)))
    smokes = [dict(t0=34 + k * 2.2 + rng.uniform(0, 1.5), x=rng.uniform(CAMP[0] + 22, CAMP[1] - 26),
                   vy=rng.uniform(0.8, 1.2), vx=rng.uniform(0.05, 0.3), r0=rng.uniform(4, 6), r1=rng.uniform(11, 16),
                   wob=rng.uniform(0, 6.28), seed=rng.uniform(0, 40)) for k in range(34)]
    licks, x = [], CAMP[0] + rng.uniform(5, 12)                   # small flames along the palisade, unevenly spaced
    while x < CAMP[1] - 6:
        licks.append(dict(x=x, h=rng.uniform(5, 11), hw=rng.uniform(2.0, 3.4), ph=rng.uniform(0, 6.28),
                          seed=rng.uniform(0, 50)))
        x += rng.uniform(9, 24)
    return SimpleNamespace(arrows=arrows, embers=embers, smokes=smokes, licks=licks,
                           HX=np.array([a["end"][0] for a in arrows]), HY=np.array([a["end"][1] for a in arrows]),
                           HL=np.array([a["land"] for a in arrows]))


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


def burn_map(S, f):
    """Burn per camp pixel: fronts spreading from each landed hit, faster upward, plus the blaze filling the rest
    patch by patch."""
    b = np.zeros(len(CY))
    for i in np.nonzero(S.HL <= f - 1)[0]:
        age = min(f - S.HL[i] - 1, 60)
        dy = CY - S.HY[i]
        dd = np.hypot(CX - S.HX[i], np.where(dy < 0, dy * 0.55, dy * 1.5))
        b = np.maximum(b, np.clip((age * 0.32 - dd) / 6.0, 0, 1.3))
    return np.maximum(b, ease_io((f - BLAZE0 + 2) / 22.0) * (0.55 + 0.9 * CB[CY, CX]))


def draw_camp(fr, f, b, sel):
    """The camp pixels in sel (the fence and tower behind the fires, or the tents and crates in front of them),
    charring where the burn reaches. Char keeps the light and dark faces, cloth opens in clumped holes
    down to the poles, a glowing edge runs along the burn front, embers sit in clumps on burnt timber, and the lit
    side of the burnt frame keeps a warm rim so the shape still reads against the dark."""
    mat, tone, cn = MAT[CY, CX], TONE[CY, CX], CN[CY, CX]
    pal = np.where((mat == 1)[:, None], PC[tone], PT[tone])
    charred = ease_io((b - 0.45) / 0.5)[:, None]
    rgb = pal * (1 - charred) + PCH[np.clip(tone - 1, 0, 2)] * charred
    live = max(1 - ease_io((f - BURN0 - 4) / 12.0), 0.0)
    front = np.clip(1 - np.abs(b - 0.22) / 0.2, 0, 1) * (0.6 + 0.4 * np.sin(f * 0.7 + cn * 20)) * live
    ember = ((mat >= 2) & (b > 0.7) & (cn > 0.8)) * (0.35 + 0.25 * np.sin(f * 0.45 + cn * 30))   # dull orange clumps
    rim = RIM[CY, CX] & (b > 0.6)
    warm = np.where(rim, 0.75 * (0.35 + 0.65 * live), 0.0)        # the rim cools to a dull red as the fires sink
    hot = np.clip(np.maximum(front, ember), 0, 1)
    rgb = rgb * (1 - warm[:, None]) + PF[1] * warm[:, None]
    rgb = rgb * (1 - hot[:, None]) + (PF[3] * (hot > 0.6)[:, None] + PF[2] * (hot <= 0.6)[:, None]) * hot[:, None]
    hole = (mat == 1) & ~POLE[CY, CX] & (b > 0.85) & (cn < 0.14 + np.minimum(b - 0.85, 0.45) * 0.5)
    keep = ~hole & sel
    fr.over(CY[keep], CX[keep], rgb[keep], 1.0)
    lit = (hot > 0.2) & keep
    if lit.any():
        np.add.at(fr.L, (CY[lit], CX[lit]), 0.25 * hot[lit])


def draw_flags(fr, F, f, b_at):
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
            edge = (X[ys, xs] - px) > left - 2
            rgb = np.where(edge[:, None], PF[3], rgb * (1 - 0.5 * ease_io((burn - 0.3) / 0.4)))
            fr.glow(px + left, fl["top"] + fl["h"] * 0.5, 6, 0.3)
            tongue(F, px + left - 1, fl["top"] + fl["h"], 6 + 3 * math.sin(f + j), 2.2, f, j * 5.1, sway=1.5)
        fr.over(ys + sy.start, xs + sx.start, rgb, 1.0)


def draw_smoke(fr, S, f, lvl):
    """The smoke column as one shade map laid at one alpha: kit puffs lit from the top left, the old ones high up and
    drawn first, each breaking into dots as it ages or thins; the puffs just over the fire take the warm tones."""
    cx = PIVOT[0]
    m = np.full((H, W), -1, np.int8)
    puffs = []
    for sm in S.smokes:                                 # gathering toward one column over the great tent
        t = f - sm["t0"]
        if t < 0:
            continue
        r = sm["r0"] + (sm["r1"] - sm["r0"]) * eout(t / 26.0)
        x0 = sm["x"] + (cx - sm["x"]) * min(1.0, t / 30.0) * 0.6
        y = 134 - sm["vy"] * t
        x = x0 + sm["vx"] * t + 3 * math.sin(t * 0.15 + sm["wob"])
        k = min(1.0, t / 4.0) * (1 - float(ease_io((r + 12 - y) / 22.0))) * (0.45 + 0.55 * min(1.0, lvl * 1.6))
        if k > 0.2:
            puffs.append((y, x, r, k, sm["seed"], t))
    if f >= BURN0 - 6:                                  # a late smoke stem off the embers
        for j in range(10):
            t = (f - BURN0 + 6 + j * 3.1) % 30
            y, r = 150 - t * 1.6, 3 + t * 0.32
            puffs.append((y, cx - 30 + (j * 17) % 70 + t * 0.2, r, min(1, t / 4) * (1 - t / 30) * 0.9, j * 1.7, t))
    for y, x, r, k, seed, t in sorted(puffs):           # highest (oldest) first, the young ones over them
        if y - r < 5 or x - r < 5 or x + r > W - 6:
            continue
        brk = min(0.6, max((0.75 - k) * 1.1, (t - 30) / 30.0, 0.0))   # whole while young, dots only as it thins
        fk.puff(m, XX, YY, x, y, r * (0.6 + 0.4 * min(1.0, k * 2)), (0, 1, 2), brk=brk, seed=seed, ph=f * 0.04)
    under = (m >= 0) & (YY > 126 - 14 * lvl - 18 * (fk.bayer(m) - 0.5)) & (lvl > 0.2)
    m[under] += 3                                       # lit from below by the fire, with a dithered boundary
    ys, xs = np.nonzero(m >= 0)
    if len(ys):
        fr.over(ys, xs, np.stack([hexf(c) for c in SMOKE])[m[ys, xs]], SMOKE_A)


def site_fire(F, BF, st, f, k):
    """One site's cluster: it grows as the burn reaches its span and roars in the blaze. Returns its height."""
    heat = float(np.clip(BF[:, st["span"][0]:st["span"][1]].max(), 0, 1))
    grow = float(ease_io((heat - 0.2) / 0.6))
    if grow <= 0.02:
        return 0.0
    roar = float(ease_io((f - BLAZE0 + 10) / 14.0))
    sink = 1 - 0.85 * float(ease_io((f - BURN0) / 13.0))
    hgt = st["hgt"] * grow * (0.3 + 0.7 * roar) * sink
    cluster(F, st["x"], st["base"], hgt, st["hw"] * (0.7 + 0.3 * roar), f, 3.3 + 7.7 * k, st["sides"])
    return hgt


def draw(f, seed=SEED):
    S = scene(seed)
    fr = Frame()
    cx, by = PIVOT
    lvl = fire_level(f)

    draw_smoke(fr, S, f, lvl)

    b = burn_map(S, f)
    BF = np.zeros((H, W))
    BF[CY, CX] = b

    # the fence and tower, then the big fires inside the camp in one heat field, then the tents against them
    draw_camp(fr, f, b, BEHIND)
    back = np.full((H, W), -1.0)
    heights = {}
    for k, st in enumerate(SITES):
        if st["back"]:
            heights[k] = site_fire(back, BF, st, f, k)
    paint_fire(fr, back)
    draw_camp(fr, f, b, ~BEHIND)

    # in front of it: the tower and crate fires, the small licks along the palisade, burning flags and ground fires
    front = np.full((H, W), -1.0)
    for k, st in enumerate(SITES):
        if not st["back"]:
            heights[k] = site_fire(front, BF, st, f, k)
    draw_flags(fr, front, f, lambda x, y: BF[int(y), max(int(x) - 1, 0):int(x) + 3].max())
    sink = 1 - 0.8 * float(ease_io((f - BURN0) / 12.0))
    for lk in S.licks:
        col = BF[:, int(lk["x"]) - 2:int(lk["x"]) + 3]
        rows = np.nonzero((col > 0.15).any(axis=1))[0]
        if not len(rows):
            continue
        heat = float(np.clip(col[rows].max(), 0, 1))
        beat = 0.5 + 0.5 * math.sin(f * 0.33 + lk["ph"])          # each lick swells and dies on its own slow beat
        h = lk["h"] * heat * (0.35 + 0.65 * beat) * sink
        tongue(front, lk["x"], rows.min() + 3, h, lk["hw"], f, lk["seed"], sway=1.5)
        fr.glow(lk["x"], rows.min() - h * 0.3, max(h * 0.8, 3), 0.1 * heat * sink)
    for ar in S.arrows:
        st = arrow_state(ar, f)
        if st is None or st[0] != "stuck" or ar["onobj"]:
            continue
        own = min(1.0, (st[2] + 1) / 4.0) * (1 - float(ease_io((st[2] - ar["burn"]) / 8.0))) * sink
        if own > 0.05:
            x, y = ar["end"]
            tongue(front, x, y + 1, ar["fh"] * own, 2.4, f, ar["seed"], sway=1.2)
            fr.glow(x, y - 3, 6, 0.15 * own)

    # stuck arrows under the front flames
    for ar in S.arrows:
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
    paint_fire(fr, front)

    # light on each fire: a tight core low in the flames and a pool round the cluster
    g = lt.GLOW[GLOW]
    for k, st in enumerate(SITES):
        hgt = heights.get(k, 0.0)
        if hgt < 2:
            continue
        part = min(1.0, hgt / st["hgt"] + 0.25)
        fr.glow(st["x"] + LEAN * hgt * 0.3, st["base"] - hgt * 0.3, max(hgt * 0.42, 5), 0.42 * part)
        fr.glow(st["x"] + LEAN * hgt * 0.4, st["base"] - hgt * 0.4, max(hgt * 0.42, 5) * g["pool_r"],
                0.42 * part * g["pool_k"] * 0.55)

    sky = float(ease_io((f + 2) / 12.0) * (1 - ease_io((f - 40) / 20.0)))
    fr.glow(64, 36, 58, 0.16 * sky, flat=0.5)

    for ar in S.arrows:
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

    for e in S.embers:
        t = f - e["t0"]
        if t < 0 or t > e["life"] or lvl < 0.15:
            continue
        k = (1 - t / e["life"]) * min(1.0, lvl * 1.5)
        x = e["x"] + e["vx"] * t + 2.5 * math.sin(t * 0.35 + e["ph"])
        y = e["y0"] - e["vy"] * t
        if y < 8 or not 8 < x < W - 8:
            continue
        col = PF[4] if k > 0.7 else PF[3] if k > 0.4 else PF[2]
        vx = e["vx"] + 0.9 * math.cos(t * 0.35 + e["ph"])
        line(fr, (x - vx * 1.4, y + e["vy"] * 1.4), (x, y), PF[2], col, 0.2, min(1.0, k * 1.8))
        fr.glow(x, y, 3, 0.4 * k)
        fr.glow(x, y, 7, 0.08 * k)

    # scene pools (clarity hazy): along the burning camp and a wide warm one above it
    fr.glow_line((CAMP[0] + 12, by - 18), (CAMP[1] - 14, by - 18), 30, 0.1 * lvl)
    fr.glow(cx - 6, by - 52, 104, 0.04 + 0.1 * lvl, flat=0.75)
    rain = float(ease_io((f - RAIN0) / 8.0) * (1 - ease_io((f - 50) / 10.0)))
    fr.glow(104, 88, 96, 0.1 * rain, flat=0.7)
    return fr


def render(f, seed=SEED):
    """Colour (h, w, 4) uint8, light (h, w, 3) float and the summed light L of frame f."""
    fr = draw(f, seed)
    col = (np.clip(fr.rgba(), 0, 1) * 255).round().astype(np.uint8)
    L = np.clip(fr.L, 0, 1)
    return col, pfx.tint(np.repeat(L[..., None], 3, -1), LIGHT_RAMP), L


def zoom(img, k):
    return np.asarray(Image.fromarray(img).resize((img.shape[1] * k, img.shape[0] * k), Image.NEAREST))


def main():
    OUT.mkdir(exist_ok=True)
    if sys.argv[1:2] == ["look"]:                       # a few frames at 4x on the dark ground, while drawing
        pick = [int(a) for a in sys.argv[2:]] or [30, 50, 66, 82, 96, 107]
        rows = [zoom(pfx.composite(*render(f)[:2], "#101018"), 4) for f in pick]
        Image.fromarray(np.concatenate(rows, 1) if len(rows) < 4 else np.concatenate(
            [np.concatenate(rows[i:i + 3], 1) for i in range(0, len(rows) - len(rows) % 3, 3)], 0)).save(OUT / "look.png")
        print("look.png", pick)
        return 0

    cols, lights, Ls, finals = [], [], [], []
    for f in range(N):
        c, l, L = render(f)
        cols.append(c), lights.append(l), Ls.append(L)
        finals.append(pfx.composite(c, l))

    cov, mean = [], []
    for c, L in zip(cols, Ls):
        ys, xs = np.nonzero(c[..., 3])
        box = L[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        cov.append((box > 0.03).mean())
        mean.append(box[box > 0.03].mean() if (box > 0.03).any() else 0)
    lo, hi = lt.GLOW[GLOW]["mean"]
    print(f"light: cover {100 * np.median(cov):.0f} %, mean {np.median(mean):.3f} "
          f"({GLOW} mean {lo} to {hi}, hazy cover 40 to 80 %)")
    print(f"colours: median {int(np.median([ex.colours(x) for x in finals]))} a frame (soft style, smooth light)")
    fr = ex.framing(cols)
    print(f"framing: the drawing sits in x {fr['box'][0]}..{fr['box'][2]}, y {fr['box'][1]}..{fr['box'][3]} "
          f"of {W}x{H}, {100 * fr['trim']:.0f} % to trim; {ex.memory_mb(cols, lights):.0f} MB decoded")

    pick = [6, 18, 26, 34, 44, 54, 62, 70, 80, 90, 100, 107]
    for bg, tag in (("#101018", "dark"), ("#5a6070", "mid")):
        cells = [zoom(pfx.composite(cols[i], lights[i], bg), 4) for i in pick]
        Image.fromarray(np.concatenate([np.concatenate(cells[i:i + 3], 1) for i in range(0, 12, 3)], 0)).save(
            OUT / f"{NAME}_4x_{tag}.png")
    pfx.strip(finals, OUT / f"{NAME}_1x.png")
    pfx.contact(OUT / "contact.png", finals, FPS)
    pfx.gif(finals, OUT / f"{NAME}.gif", FPS, scale=3)

    extra = dict(fc.meta("side", W, H, PIVOT), glow=GLOW)
    fc.check(extra)
    ex.write(OUT / "sheets", NAME, finals, FPS, PIVOT, False, light=lights, color=cols, states=STATES, hold=True,
             extra=extra)
    ex.page(OUT / "sheets" / f"{NAME}.json")

    bad = ex.check(cols, lights, loop=False, src=__file__, hold=True)     # the burnt camp stays: end "hold"
    bad += ex.check_seeds(lambda f, sd: render(f, seed=sd)[0], N)
    if not (lo <= np.median(mean) <= hi and 0.4 <= np.median(cov) <= 0.8):
        bad.append(f"light outside the {GLOW} and hazy rows")
    for line_ in bad:
        print(line_)
    print("checks: clean" if not bad else f"{len(bad)} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
