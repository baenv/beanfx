"""van_kiem_quy_tong_v5: Ten Thousand Swords Return to the Origin.

48 silver swords fan out round the caster and shoot up into a sunset cloud layer, the clouds wind into a vortex,
a round hole opens in its eye, a giant jian slides out tip down and plunges into the ground, then bursts into the
48 swords, which fan out wide and circle back round the caster before they go out in glints.

Side view, 1 direction plus mirror, 560x400, 30 fps, 210 frames, one-shot. Painterly HD, glow strong, clarity hazy.

| state  | frames  | s   | what moves                                                                | carrier      |
|--------|---------|-----|---------------------------------------------------------------------------|--------------|
| rise   | 0-59    | 2.0 | swords fan into two rings round the caster, circle, peel off one by one   | small swords |
|        |         |     | and climb near upright into the near half of the deck                     |              |
| swirl  | 60-137  | 2.6 | the deck winds into a vortex, glints circle inside, the eye opens         | clouds       |
| plunge | 138-158 | 0.7 | the giant sword comes down through the eye, holds, plunges; contact 156   | giant sword  |
| return | 159-209 | 1.7 | white-hot sword bursts into 48 swords that slide into two counter-turning | small swords |
|        |         |     | tilted rings round the caster, far side dim and behind it                 |              |

Giant jian, by its overall length (research): blade 78 % with a centre ridge and a tip taper over the last 8 %,
guard 3 % about four blade widths wide with short wings drooping toward the blade, grip 15 % wrapped, pommel 4 %.
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "kit"))
import caster as cs  # noqa: E402
import derive as dv  # noqa: E402
import export as ex  # noqa: E402
import facing as fc  # noqa: E402
import fxlib as fl  # noqa: E402
import pfx  # noqa: E402
import target as tg  # noqa: E402

NAME = "van_kiem_quy_tong_v5"
OUT = HERE / "out"
W, H = 560, 400
FPS, N = 30, 210
SEED = 11
TAU = math.tau

CAST, CHAN, SHIFT = 2.5, 78 / 54, 60   # rise and swirl slowed against the first cut; later states shift by SHIFT


def T(t):
    """Frame in this cut of a frame t of the first cut (rise 0-23, swirl 24-77, then plunge)."""
    if t < 24:
        return t * CAST
    if t < 78:
        return 24 * CAST + (t - 24) * CHAN
    return t + SHIFT


def T_old(f):
    """Inverse of T, and the first cut's frames per frame here."""
    if f < 24 * CAST:
        return f / CAST, 1 / CAST
    if f < 24 * CAST + 54 * CHAN:
        return 24 + (f - 24 * CAST) / CHAN, 1 / CHAN
    return f - SHIFT, 1.0


RISE0, SWIRL0, HOLE0, PLUNGE0 = 0, 60, 98, 138
DROP0, IMPACT, BURST, RETURN0 = 152, 156, 162, 159
STATES = {"rise": [RISE0, SWIRL0 - 1], "swirl": [SWIRL0, PLUNGE0 - 1], "plunge": [PLUNGE0, RETURN0 - 1],
          "return": [RETURN0, N - 1]}

GROUND = 336
FOOT = (150, 334)                      # caster's feet: the pivot
PIVOT = FOOT
EX, EY, RX, FLAT = 360, 72, 180, 0.26  # vortex eye, deck radius, deck squash (side view of a disc)
TH = 14                                # deck thickness: the belly under it
NSW = 48

SW = ["#141826", "#2e3548", "#56627c", "#909eb8", "#cbd6e6", "#f6faff", "#1a1018", "#36222c", "#5a3a40"]
CL = ["#22101e", "#46202a", "#743434", "#a8503a", "#d8803e", "#f4b85c", "#fff0c8"]
DUST = ["#2c1c1e", "#5a3c34", "#8c6650", "#c49a78"]
ROCK = ["#1c1418", "#3e2a26", "#6e4a38", "#a0745a"]
GOLD = "#ffd890"
HOLE = "#fff6dc"
LIGHT_RAMP = ["#3a1406", "#d8702a", "#ffcc78", "#ffffff"]


def hexf(c):
    return np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


SWF, CLF, DUF, ROF = (np.stack([hexf(c) for c in p]) for p in (SW, CL, DUST, ROCK))
WHITE = np.ones(3)
YY, XX = np.mgrid[0:H, 0:W].astype(float) + 0.5


def ease(s):
    s = min(max(s, 0.0), 1.0)
    return s * s * (3 - 2 * s)


class Canvas:
    def __init__(self):
        self.rgb = np.zeros((H, W, 3))
        self.a = np.zeros((H, W))

    def over(self, ys, xs, rgb, a):
        ys = np.asarray(ys).astype(int).ravel()
        xs = np.asarray(xs).astype(int).ravel()
        n = ys.size
        a = np.broadcast_to(np.asarray(a, float), (n,)) if np.ndim(a) == 0 else np.asarray(a, float).ravel()
        rgb = np.asarray(rgb, float)
        rgb = np.broadcast_to(rgb, (n, 3)) if rgb.ndim == 1 else rgb.reshape(n, 3)
        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W) & (a > 0)
        ys, xs, a, rgb = ys[ok], xs[ok], a[ok], rgb[ok]
        ao = self.a[ys, xs]
        na = a + ao * (1 - a)
        self.rgb[ys, xs] = (rgb * a[:, None] + self.rgb[ys, xs] * (ao * (1 - a))[:, None]) / np.maximum(na, 1e-6)[:, None]
        self.a[ys, xs] = na

    def rgba(self):
        return (np.concatenate([self.rgb, self.a[..., None]], -1).clip(0, 1) * 255).round().astype(np.uint8)


def _win(x0, x1, y0, y1):
    return slice(max(int(y0), 0), max(min(int(y1) + 2, H), 0)), slice(max(int(x0), 0), max(min(int(x1) + 2, W), 0))


def glow(L, x, y, r, k, flat=1.0):
    if k <= 0 or r <= 0:
        return
    sy, sx = _win(x - r, x + r, y - r * flat, y + r * flat)
    d = np.hypot(XX[sy, sx] - x, (YY[sy, sx] - y) / flat) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def glow_line(L, p0, p1, r, k):
    if k <= 0:
        return
    (ax, ay), (bx, by) = p0, p1
    sy, sx = _win(min(ax, bx) - r, max(ax, bx) + r, min(ay, by) - r, max(ay, by) + r)
    X, Y = XX[sy, sx], YY[sy, sx]
    ex_, ey_ = bx - ax, by - ay
    h = np.clip(((X - ax) * ex_ + (Y - ay) * ey_) / (ex_ * ex_ + ey_ * ey_ or 1e-9), 0, 1)
    d = np.hypot(X - ax - ex_ * h, Y - ay - ey_ * h) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def flick(i, f, seed, rate=1.0):
    ph = (i * 2.399 + seed * 0.71) % TAU
    sp = 1.1 + (i * 0.618 + seed * 0.37) % 1.7
    j = ((i * 7919 + f * 104729 + seed * 1299709) % 1000) / 1000.0
    v = 0.5 + 0.5 * math.sin(ph + f * sp * rate)
    return min(1.0, max(0.0, v * (1 - 0.4 * rate) + 0.4 * rate * j))


def star(cv, x, y, size, a=1.0):
    """A four-point glint: a white heart and gold arms."""
    xi, yi = int(round(x)), int(round(y))
    pts, cols = [], []
    for k in range(-size, size + 1):
        for (px, py) in ((xi + k, yi), (xi, yi + k)):
            pts.append((py, px))
            cols.append(WHITE if abs(k) <= size // 2 else hexf(GOLD))
    P = np.array(pts)
    cv.over(P[:, 0], P[:, 1], np.stack(cols), a)


K = 3                    # the giant sword at three times the first cut: its hilt stays hidden in the clouds
LS = 260 * K             # overall length, px
BW = 9.0 * K             # blade half width
HW = 38 * K              # half width of the local map
POMMEL, GRIP, GUARD = 10, 49, 57  # part boundaries from the pommel end, in units of K px (4 %, 15 %, 3 %)


def big_sword(trace=False):
    """Tone map (indices into SW, -1 empty) and part map (pommel 0, grip 1, guard 2, blade 3) of the giant jian,
    vertical, tip down, pommel end at row 0, the axis at column HW. The blade is drawn in pixels (ridge, bevels,
    edge, sheen); the hilt, never on screen, keeps the first cut's shapes scaled by K."""
    S, V = np.meshgrid(np.arange(LS) + 0.5, np.arange(-HW, HW + 1).astype(float), indexing="ij")
    av = np.abs(V)
    tone = np.full(S.shape, -1, int)
    part = np.full(S.shape, -1, int)

    tipz = LS * 0.085
    hw = BW * np.clip((LS - S) / tipz, 0, 1) ** 0.8
    blade = (S >= (GUARD - 1) * K) & (av <= hw + 0.15) & ((av < 0.6) | (hw >= 0.9))
    t = np.where(V < 0, 3, 2)
    bev = np.maximum(1.5, hw * 0.3)                      # the ridge's two faces: lit left, shaded right
    t = np.where((V <= -1) & (V >= -bev), 4, t)
    t = np.where((V >= 1) & (V <= bev), 1, t)
    t = np.where(V == 0, 5, t)
    edge = av >= np.floor(hw + 0.15) - (hw > 6)          # a 2 px edge where the blade is wide
    t = np.where(edge & (V < 0), 4, t)
    t = np.where(edge & (V > 0), 3, t)
    sheen = ((S * 0.8 - V * 2.2) % 150) < 10
    t = np.where(sheen & (V < -bev) & (V > -hw + 2), 4, t)
    sheen2 = ((S * 0.8 - V * 2.2 + 60) % 150) < 4
    t = np.where(sheen2 & (V < -bev) & (V > -hw + 2), 5, t)
    tone[blade], part[blade] = t[blade], 3

    S, V = S / K, V / K                                  # the hilt in the first cut's units
    av = np.abs(V)

    core = (S >= GRIP) & (S < GUARD) & (av <= 12.5)
    wing = (av > 12) & (av <= 4 * BW / K) & (S >= GRIP + (av - 12) * 0.24) & (S <= GUARD - 2.5 + (av - 12) * 0.45)
    guard = core | wing
    g = np.where(V < 0, 3, 2)
    g = np.where(S < GRIP + 2 + (av - 12).clip(0) * 0.24, 4, g)
    g = np.where(av > 4 * BW / K - 3, 4, g)
    g = np.where((av < 3) & (S > GRIP + 2) & (S < GUARD - 2), 5, g)
    g = np.where((S > GUARD - 2 + (av - 12).clip(0) * 0.45) & (V > 0), 1, g)
    tone[guard], part[guard] = g[guard], 2

    grip = (S >= POMMEL - 1) & (S < GRIP) & (av <= 5.2 + 0.8 * np.sin(np.pi * (S - POMMEL) / (GRIP - POMMEL)))
    w = np.where(((S + V * 1.4) % 5) < 1.6, 6, 7)
    w = np.where(((S - V * 1.4) % 5) < 1.2, 6, w)
    w = np.where(V <= -3, 8, w)
    tone[grip], part[grip] = w[grip], 1

    pm = (S < POMMEL + 0.5) & (((S - 5.1) / 5.3) ** 2 + (V / 11) ** 2 <= 1)
    p = np.where(V < 0, 3, 2)
    p = np.where((S < 3.5) & (V < 3), 4, p)
    p = np.where((av < 2) & (S > 3.5) & (S < 7), 5, p)
    tone[pm], part[pm] = p[pm], 0

    if trace:
        return tone, part
    return tone


BIG_TONE, BIG_PART = big_sword(trace=True)
BIG_MASK = BIG_TONE >= 0
CLOUD_LOW = 124          # the deck's underside over the blade: below it the sword is in the open
_rows = np.arange(LS)[:, None] + (GROUND + 20 - LS)  # world rows of the sword once it is planted
BURST_LOCAL = dv.local(dv.scatter(BIG_MASK & (_rows > CLOUD_LOW + 6) & (_rows < GROUND), NSW, seed=SEED), (HW, 0))
RISE_LAUNCH = 30         # first sword peels off the rings; the last goes 20 frames later
EMERGE = 46              # px of tip that slide out under the deck before the plunge


def sword_top(f):
    """World y of the pommel end (the axis stays at x = EX), or None when the sword is not on screen."""
    if f < PLUNGE0 or f >= BURST:
        return None
    tip_hole = EY - 4
    out = CLOUD_LOW + EMERGE - tip_hole
    if f < DROP0:
        s = ease((f - PLUNGE0) / (DROP0 - 2 - PLUNGE0))
        tip = tip_hole + out * s + 2 * max(0, f - (DROP0 - 2))
    elif f < IMPACT:
        s = (f - DROP0) / (IMPACT - DROP0)
        tip = tip_hole + out + 4 + (GROUND + 20 - tip_hole - out - 4) * s ** 1.6
    else:
        tip = GROUND + 20
    return tip - LS


def heat_of(f):
    if f == IMPACT:
        return 0.35
    if f >= RETURN0:
        return ease((f - RETURN0) / (BURST - RETURN0))
    return 0.0


def draw_big(cv, L, f, hole, ctone):
    """The giant sword coming down through the open eye: behind the eye's centre line only the hole shows it, in
    front of it the blade passes over the deck, under a 1 px pale lip where the hole's front edge crosses it. The
    hilt stays above the eye, in the clouds."""
    top = sword_top(f)
    if top is None:
        return
    y0, x0 = int(round(top)), EX - HW
    rr, cc = np.nonzero(BIG_MASK)
    ys, xs = rr + y0, cc + x0
    keep = (ys < GROUND) & (ys >= 0) & (xs >= 0) & (xs < W)
    yc, xc = np.clip(ys, 0, H - 1), np.clip(xs, 0, W - 1)
    keep &= hole[yc, xc] | (ys >= EY)
    rgb = SWF[BIG_TONE[rr, cc]]
    h = heat_of(f)
    if h > 0:
        rgb = rgb * (1 - h) + WHITE * h
    cv.over(ys[keep], xs[keep], rgb[keep], 1.0)
    lip = keep & (ys >= EY) & (ctone[yc, xc] == 6)       # the hole's front rim drawn back over the blade
    cv.over(ys[lip], xs[lip], CLF[6], 1.0)
    vis_top = EY
    tip = min(y0 + LS, GROUND)
    if tip > vis_top:
        glow_line(L, (EX - 9, vis_top), (EX - 9, tip - 8), 10, 0.16 + 0.4 * h)    # the lit face and ridge
        glow_line(L, (EX, vis_top), (EX, tip), 40, 0.13 + 0.2 * h)
    if f < IMPACT:
        glow(L, EX, tip - 10, 18, 0.6)
        if f >= DROP0:                                    # speed lines beside the falling blade
            for j in range(8):
                side = -1 if j % 2 else 1
                xx = EX + side * (BW + 5 + (j // 2) * 7)
                ln = 50 + (j * 23) % 40
                y1 = tip - 30 - (j * 17) % 30
                yy = np.arange(int(max(y1 - ln, vis_top)), int(y1))
                cv.over(yy, np.full(yy.size, int(xx)), hexf(GOLD), np.linspace(0, 0.7, yy.size))
    if h > 0:
        glow(L, EX, (vis_top + GROUND) / 2, 110, 0.35 * h, flat=1.0)


LIGHT_SW = [hexf("#fffdf6"), hexf("#eef4ff"), hexf("#b8cceb"), hexf("#ffe2a0")]   # core, lit edge, far edge, hilt


def small(cv, L, x, y, ang, a=1.0, heat=0.0, lk=1.0, i=0, f=0, seed=SEED, fs=1.0):
    """A light sword (34 px times SC) at (x, y) (the guard), tip along ang, shortened by fs along its length: a 1 px
    white core line, translucent pale edges, a pale gold hilt, no dark tones. The lit edge stays top-left."""
    c, s = math.cos(ang), math.sin(ang)
    e = 27 * SC
    sy, sx = _win(x - e, x + e, y - e, y + e)
    X, Y = XX[sy, sx] - x, YY[sy, sx] - y
    u = (X * c + Y * s) / (SC * fs)
    v = (-X * s + Y * c) / SC
    av = np.abs(v)
    bh = 1.7 * np.clip((24 - u) / 8, 0, 1) ** 0.7
    blade = (u >= 0) & (u <= 24) & (av <= np.maximum(bh, 0.5))
    guard = (u >= -1.4) & (u < 0.4) & (av <= 3.0)
    grip = (u >= -6.2) & (u < -1.4) & (av <= 0.75)
    pommel = np.hypot(u + 7.2, v) <= 1.2
    lit = (v > 0) == ((s - c) > 0)
    t = np.full(u.shape, -1)
    al = np.zeros(u.shape)
    hilt = guard | grip | pommel
    t[hilt], al[hilt] = 3, 0.8
    core = av * SC < 0.6
    t[blade] = np.where(core[blade], 0, np.where(lit[blade], 1, 2))
    al[blade] = np.where(core[blade], 1.0, np.where(lit[blade], 0.75, 0.5))
    ys, xs = np.nonzero(t >= 0)
    rgb = np.stack(LIGHT_SW)[t[ys, xs]]
    if heat > 0:
        rgb = rgb * (1 - heat) + WHITE * heat
    cv.over(ys + sy.start, xs + sx.start, rgb, al[ys, xs] * a)
    if lk > 0:
        ln = SC * fs
        tx, ty = x + c * 23 * ln, y + s * 23 * ln
        k = lk * a * (0.6 + 0.4 * flick(i, f, seed))
        glow(L, tx, ty, 5, 0.5 * k)
        glow_line(L, (x + c * 2 * ln, y + s * 2 * ln), (tx, ty), 5, 0.3 * k)
        glow_line(L, (x, y), (tx, ty), 11, 0.12 * k)


def trail(cv, pts, a0=0.8):
    """A sparkle trail through earlier positions, newest first: 1 px gold dots fading out."""
    for j in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[j], pts[j + 1]
        n = max(int(math.hypot(bx - ax, by - ay)), 1)
        t = np.linspace(0, 1, n, endpoint=False)
        a = a0 * (1 - (j + t) / (len(pts) - 1)) ** 1.5
        cv.over(np.round(ay + (by - ay) * t), np.round(ax + (bx - ax) * t), hexf(GOLD), a)


def bez(p, t):
    t = min(max(t, 0.0), 1.0)
    n = len(p) - 1
    out = np.zeros(2)
    for k, q in enumerate(p):
        out += math.comb(n, k) * (1 - t) ** (n - k) * t ** k * np.asarray(q, float)
    return out


SC = 1.4                 # small sword scale: 34 px in the first cut, about 46 px now
# Two sword rings round the caster, flat discs seen a little from above: the lower one wide, the upper one tight,
# turning against each other, each tilted (roll) the other way.
RINGS = [dict(cy=FOOT[1] - 24, R=84, roll=0.10, spin=1.0), dict(cy=FOOT[1] - 52, R=60, roll=-0.14, spin=-1.0)]
PITCH = 0.27             # how far the camera looks down on the rings
BEND = 0.38              # tips lean outward from the ring's tangent, rad
OMEGA = 0.13             # ring turn, rad per frame


def orbit3(i, th, f, grow=None, lift=None):
    """Guard point, heading, foreshortening and depth of ring sword i at ring angle th at frame f. grow and lift
    default to the return's: the rings close in as they settle, then rise before the swords go out."""
    rg = RINGS[i % 2]
    if grow is None:
        grow = 1.16 - 0.16 * ease((f - BURST - 12) / 30)
    if lift is None:
        lift = 10 * ease((f - BURST - 26) / 20)
    R = rg["R"] * grow
    c, s, sp = math.cos(th), math.sin(th), rg["spin"]
    dx = -s * sp * math.cos(BEND) + c * math.sin(BEND)
    dz = c * sp * math.cos(BEND) + s * math.sin(BEND)
    cr, sr = math.cos(rg["roll"]), math.sin(rg["roll"])
    x, y = R * c, R * s * PITCH
    vx, vy = dx, dz * PITCH
    px, py = FOOT[0] + x * cr - y * sr, rg["cy"] - lift + x * sr + y * cr
    wx, wy = vx * cr - vy * sr, vx * sr + vy * cr
    return (px, py), math.atan2(wy, wx), max(math.hypot(wx, wy), 0.45), s


class Plan:
    """Every seeded choice of the effect, drawn once per seed."""

    def __init__(self, seed):
        rng = np.random.default_rng(seed + 101)
        self.seed = seed
        order = rng.permutation(NSW)
        self.rise = []
        for i in range(NSW):
            # each sword fans out of the caster into its ring, circles, then peels off and climbs near upright
            # into the near (left) half of the deck's underside
            ex_ = rng.uniform(235, 340)
            dx = ex_ - EX
            ey_ = EY + math.sqrt(max(RX * RX - dx * dx, 0.0)) * FLAT * 0.85 + TH * 0.6
            dz = (ey_ - EY - TH * 0.6) / FLAT
            so = 56 + rng.uniform(0, 10)
            self.rise.append(dict(a0=TAU * (i // 2) / (NSW // 2) + (i % 2) * 0.13,
                                  spawn=(i // 2) * 14.0 / (NSW // 2) + (i % 2) * 0.5,
                                  launch=RISE_LAUNCH + order[i] * 20.0 / NSW, dur=rng.uniform(12, 15),
                                  ent=(ex_, ey_), r=math.hypot(dx, dz), th=math.atan2(dz, dx),
                                  sink=T(so), sinkd=T(so + 16) - T(so)))
        P0 = dv.world(BURST_LOCAL, (EX, GROUND + 20 - LS))
        self.ret = []
        for i in range(NSW):
            side = -1 if i % 2 == 0 else 1
            p0 = P0[i]
            c1 = (np.clip(p0[0] + side * rng.uniform(60, 170), 30, 530), np.clip(p0[1] - rng.uniform(60, 170), 30, 300))
            a0 = TAU * (i // 2) / (NSW // 2) + (i % 2) * 0.13
            arrive = BURST + 18 + rng.uniform(0, 12)
            (ex_, ey_), ang, _, _ = orbit3(i, a0 + RINGS[i % 2]["spin"] * OMEGA * (arrive - BURST), arrive)
            c2 = (ex_ - math.cos(ang) * 60, ey_ - math.sin(ang) * 60 - 20)   # slide in along the ring
            self.ret.append(dict(p0=p0, c1=c1, c2=c2, arrive=arrive, a0=a0,
                                 out=BURST + 28 + order[i] * 19.0 / (NSW - 1)))
        self.rocks = [dict(vx=rng.uniform(-3.2, 3.2), vy=rng.uniform(-7, -2.5), s=int(rng.integers(1, 4)),
                           x0=EX + rng.uniform(-8, 8)) for _ in range(44)]
        self.sparks = [dict(vx=rng.uniform(-8.5, 8.5), vy=rng.uniform(-11, -2), life=int(rng.integers(6, 15)),
                            d=int(rng.integers(0, 4))) for _ in range(70)]
        self.dust = []
        for j in range(28):
            side = -1 if j % 2 else 1
            self.dust.append(dict(side=side, x0=EX + side * rng.uniform(2, 26), D=rng.uniform(30, 150),
                                  r=rng.uniform(8, 19), life=rng.uniform(28, 46), rise=rng.uniform(4, 26),
                                  d=rng.uniform(0, 4), ph=rng.uniform(0, TAU)))
        self.cloud_seed = seed * 7 + 3


_plans = {}


def plan(seed):
    if seed not in _plans:
        _plans[seed] = Plan(seed)
    return _plans[seed]


def rise_ring(sw, i, f):
    return orbit3(i, sw["a0"] + RINGS[i % 2]["spin"] * OMEGA * f, f,
                  grow=0.35 + 0.65 * ease((f - sw["spawn"]) / 10), lift=0.0)


def rise_pos(sw, i, f):
    """Guard point, heading, foreshortening and depth of rising sword i at frame f, or None when it is not yet out
    or already in the clouds. It circles in its ring until launch, then leaves along the ring's tangent, climbs,
    and enters the deck straight up."""
    if f < sw["spawn"]:
        return None
    if f < sw["launch"]:
        return rise_ring(sw, i, f)
    t = (f - sw["launch"]) / sw["dur"]
    if t >= 1:
        return None
    (x0, y0), a0, fs0, d0 = rise_ring(sw, i, sw["launch"])
    ex_, ey_ = sw["ent"]
    pts = ((x0, y0), (x0 + math.cos(a0) * 30, y0 + math.sin(a0) * 30 - 40), (ex_, ey_ + 130), (ex_, ey_))
    tt = t ** 1.4
    p = bez(pts, tt)
    q = bez(pts, tt + 0.02) if tt < 0.98 else 2 * p - bez(pts, tt - 0.02)
    k = ease((f - sw["launch"]) / 5)
    return (p[0], p[1]), math.atan2(q[1] - p[1], q[0] - p[0]), fs0 + (1 - fs0) * k, d0 + (1 - d0) * k


def ret_pos(sw, i, f):
    """Guard point, heading, foreshortening and depth (-1 far side, +1 near side) of return sword i at frame f."""
    if f < BURST or f >= sw["out"]:
        return None
    rg = RINGS[i % 2]
    if f < sw["arrive"]:
        end = orbit3(i, sw["a0"] + rg["spin"] * OMEGA * (sw["arrive"] - BURST), sw["arrive"])
        pts = (sw["p0"], sw["c1"], sw["c2"], end[0])
        t = (f - BURST) / (sw["arrive"] - BURST)
        tt = 1 - (1 - t) ** 1.7
        p = bez(pts, tt)
        q = bez(pts, tt + 0.02) if tt < 0.98 else 2 * p - bez(pts, tt - 0.02)
        k = ease((f - sw["arrive"] + 6) / 6)                # fold into the ring's depth as it lands
        return (p[0], p[1]), math.atan2(q[1] - p[1], q[0] - p[0]), 1 + (end[2] - 1) * k, 1 + (end[3] - 1) * k
    return orbit3(i, sw["a0"] + rg["spin"] * OMEGA * (f - BURST), f)


def _spin_rate(t):
    return 0.006 + 0.075 * ease((t - 10) / 50) + 0.03 * ease((t - 60) / 30) - 0.07 * ease((t - 100) / 40)


SPIN = np.cumsum([_spin_rate(T_old(f)[0]) * T_old(f)[1] for f in range(N)])   # the vortex turns slower as it slows
CY0, CY1, CX0, CX1 = 6, 150, 168, 552
CYY, CXX = YY[CY0:CY1, CX0:CX1], XX[CY0:CY1, CX0:CX1]


def hole_r(f):
    return 48 * ease((f - HOLE0) / (PLUNGE0 - HOLE0)) + 60 * ease((f - BURST) / 40)


def eye_k(f):
    k = 0.15 + 0.45 * ease((f - SWIRL0) / (HOLE0 - SWIRL0)) + 0.4 * ease((f - HOLE0) / (PLUNGE0 - HOLE0))
    return k * (1 - ease((f - BURST - 2) / 38))


def deck(f, seed):
    """Cloud deck tone map over its window (CL indices, -1 empty) and the hole as a full-frame mask."""
    sp = SPIN[f]
    grow = 0.55 + 0.45 * ease(f / T(40))
    brk = 0.75 * ease((f - BURST - 2) / 40)
    P = 600.0

    def polar(yoff):
        dx = CXX - EX
        dy = (CYY - EY - yoff) / FLAT
        return np.hypot(dx, dy), np.arctan2(dy, dx), dy

    def field(r, th):
        phi = th - sp + 2.4 * 45 / (r + 45)              # wound tighter near the eye
        n1 = fl.noise((phi % TAU) / TAU * P, r * 2.0, 40, seed + 1, period=(P, 4096))
        n2 = fl.noise(((2 * phi + 1.3) % TAU) / TAU * P, r * 3.0, 30, seed + 2, period=(P, 4096))
        arm = 0.5 + 0.5 * np.cos(3 * (th - sp * 1.2) + 3.2 * np.log1p(r / 25) + 0.8 * (n1 - 0.5))  # three arms
        return 0.3 * n1 + 0.2 * n2 + 0.5 * arm ** 1.5

    def edges(th):
        z = np.zeros_like(th)
        ne = fl.noise(((th - sp * 0.5) % TAU) / TAU * P, z, 50, seed + 3, period=(P, 4096))
        nh = fl.noise(((th + sp) % TAU) / TAU * P, z, 40, seed + 4, period=(P, 4096))
        return RX * grow * (0.84 + 0.16 * ne), hole_r(f) * (0.88 + 0.24 * nh)

    r, th, dy = polar(0)
    c = field(r, th)
    rout, rh = edges(th)
    pres = 0.85 * c + 0.4 * np.clip((rout - r) / 40, 0, 1) - 0.12 - brk + 0.3 * np.clip(1 - r / 70, 0, 1)
    top = (r < rout) & (r > rh) & (pres > 0.18)
    hole = (r <= rh) & (hole_r(f) > 0.5)

    rb, thb, _ = polar(TH * grow)
    cb = field(rb, thb)
    routb, rhb = edges(thb)
    presb = 0.75 * cb + 0.45 * np.clip((routb - rb) / 40, 0, 1) - 0.22 - brk
    belly = (rb < routb * 0.97) & (rb > rhb) & (presb > 0.18) & ~top

    ek = eye_k(f)
    inner = 1 - np.clip((r - rh) / (rout * 0.85), 0, 1)
    b = 0.5 * inner + 0.5 * c + 0.12 * np.clip(-dy / 90, 0, 1) + 0.25 * ek * inner ** 2 - 0.05 - 0.7 * brk
    tone = np.full(r.shape, -1)
    tone[top] = np.clip((b[top] * 6.5).astype(int), 0, 5)
    tone[belly] = np.clip((cb[belly] * 2.6 + 0.4 * ek).astype(int), 0, 2)
    hb = hole.copy()
    hb[1:] |= hole[:-1]
    hb[:-1] |= hole[1:]
    hb[:, 1:] |= hole[:, :-1]
    hb[:, :-1] |= hole[:, 1:]
    tone[(top | belly) & hb] = 6                         # pale rim where the deck meets the open eye
    full_hole = np.zeros((H, W), bool)
    full_hole[CY0:CY1, CX0:CX1] = hole
    return tone, full_hole


def impact(cv, L, f, pl):
    t = f - IMPACT
    if t < 0:
        return
    if t < 48:                                           # crater and glowing cracks along the ground
        fade = 1 - t / 48
        ys, xs = np.nonzero((np.abs(XX - EX) < 34 - 8 * (1 - fade)) & (YY > GROUND - 3)
                            & (YY < GROUND + 3 - np.abs(XX - EX) / 14))
        cv.over(ys, xs, ROF[0], 0.95 * fade)
        for j, ln in enumerate((64, 40, 52, 30)):
            side = -1 if j % 2 else 1
            xx = np.arange(6, ln)
            yy = GROUND - 1 + np.round(np.sin(xx * 0.5 + j) * 0.7 + xx * 0.02 * (j - 1.5))
            cv.over(yy, EX + side * xx, hexf(GOLD), np.clip(fade * 1.4 - xx / ln, 0, 1))
            glow_line(L, (EX, GROUND - 1), (EX + side * ln * 0.7, GROUND - 1), 6, 0.3 * fade ** 2)
    if t < 13:                                           # shock dome: the upper half of a flat ring
        u = t / 12
        R = 24 + 160 * (1 - (1 - u) ** 2)
        ry = R * 0.42
        d = np.abs(np.hypot((XX - EX) / R, (YY - GROUND) / ry) - 1) * R
        ring = (d < 1.2 + 1.2 * (1 - u)) & (YY <= GROUND) & (XX > 8) & (XX < W - 8)
        ys, xs = np.nonzero(ring)
        cv.over(ys, xs, hexf(CL[6]), 0.85 * (1 - u))
        glow(L, EX, GROUND - ry * 0.4, R, 0.12 * (1 - u), flat=0.5)
    for j, r in enumerate(pl.rocks):
        tt = t - (j % 3)
        if tt < 0 or tt > 44:
            continue
        x = r["x0"] + r["vx"] * tt
        y = min(GROUND - 2 + r["vy"] * tt + 0.42 * tt * tt, GROUND - r["s"])
        s = r["s"]
        ys, xs = np.mgrid[0:s, 0:s]
        t_ = np.where((ys + xs) == 0, 3, np.where(ys + xs >= s, 1, 2))
        cv.over(ys.ravel() + int(y), xs.ravel() + int(x), ROF[t_.ravel()], 1 - max(0, tt - 30) / 14)
    for j, sp in enumerate(pl.sparks):                   # sparks: streaks along their velocity, white heart
        tt = t - sp["d"]
        if tt < 0 or tt >= sp["life"]:
            continue
        x = EX + sp["vx"] * tt
        y = GROUND - 4 + sp["vy"] * tt + 0.6 * tt * tt
        if y > GROUND:
            continue
        vx, vy = sp["vx"], sp["vy"] + 1.2 * tt
        k = 1 - tt / sp["life"]
        for q in range(4):
            cv.over([round(y - vy * q * 0.35)], [round(x - vx * q * 0.35)], WHITE if q == 0 else hexf(GOLD),
                    k * (1 - q / 4))
        glow(L, x, y, 5, 0.6 * k * flick(j, f, pl.seed))
    for d in pl.dust:                                    # translucent puffs that roll out and rise
        tt = t - d["d"]
        if tt < 0 or tt > d["life"]:
            continue
        u = tt / d["life"]
        x = d["x0"] + d["side"] * d["D"] * (1 - math.exp(-tt / 9))
        r = d["r"] * (0.35 + 0.65 * (1 - (1 - min(u * 2.5, 1)) ** 2))
        y = GROUND - r * 0.7 - d["rise"] * u
        sy, sx = _win(x - r - 2, x + r + 2, y - r - 2, y + r + 2)
        X, Y = XX[sy, sx] - x, YY[sy, sx] - y
        rr = r * (0.82 + 0.18 * np.sin(np.arctan2(Y, X) * 5 + d["ph"]))
        dd = np.hypot(X, Y)
        m = (dd < rr) & (YY[sy, sx] <= GROUND)
        lit = (-X * d["side"] * 0.5 - Y) / max(r, 1)
        tn = np.clip(1.6 + lit * 1.4 - dd / r * 0.8, 0, 3).astype(int)
        ys, xs = np.nonzero(m)
        a = 0.6 * (1 - u) ** 1.3 * (1 - 0.3 * dd[ys, xs] / r)
        cv.over(ys + sy.start, xs + sx.start, DUF[tn[ys, xs]], a)
    glow(L, EX, GROUND - 10, 75, 0.4 * math.exp(-t / 10))    # the hit's hazy pool
    if t < 2:
        glow(L, EX, GROUND - 20, 40, 0.9)


def render(f, seed=SEED, caster=False):
    """(colour RGBA uint8, light float map) of frame f; with caster, the mockup caster and avatar join it."""
    pl = plan(seed)
    cv = Canvas()
    L = np.zeros((H, W))
    events = []

    def flash(f0, x, y, r, k, life):
        if f0 <= f < f0 + life:
            u = (life - (f - f0)) / life
            events.append((x, y, r * (0.55 + 0.45 * u), k * u * u))

    if caster:
        foot, lift, flut, ghost = caster_state(f)
        gfoot = (foot[0] - 10, foot[1] - 2)
        gg = cs.draw(cv.over, (H, W), gfoot, 1.15, caster_pose(f, gfoot, 1.15), f * 0.7, lift * 0.6, flut * 0.7,
                     hair="loose", ghost=ghost)
        if ghost > 0:
            cs.ghost_light(cv.over, L, gg, ghost * 0.8, f, point_of(f))

    tone, hole = deck(f, pl.cloud_seed)
    ys, xs = np.nonzero(tone >= 0)
    cv.over(ys + CY0, xs + CX0, CLF[tone[ys, xs]], 1.0)
    ek = eye_k(f)
    hr = hole_r(f)
    if hr > 0.5:
        ys, xs = np.nonzero(hole)
        cv.over(ys, xs, hexf(HOLE), 0.92 * (1 - ease((f - BURST) / 14)))
        glow(L, EX, EY, hr * 1.25, 0.7 * min(1, hr / 20) * (1 - ease((f - BURST - 8) / 30)), flat=FLAT * 1.4)
    glow(L, EX, EY, 70, 0.45 * ek, flat=0.45)              # the eye: the light source
    glow(L, EX, EY + 6, 195, 0.12 * ek, flat=0.33)         # hazy pool over the deck
    wash = ease(f / T(10)) * (1 - ease((f - BURST - 6) / 34))
    glow(L, 350, 190, 225, 0.16 * wash, flat=0.9)           # hazy wash under the vortex
    glow(L, FOOT[0], FOOT[1] - 50, 115, 0.14 * ease(f / 6) * (1 - ease((f - RISE_LAUNCH - 10) / 20)))
    if HOLE0 <= f < RETURN0 + 6:                           # a soft shaft under the eye
        o = ease((f - HOLE0) / 20) * (1 - ease((f - RETURN0) / 6))
        glow_line(L, (EX, EY + 8), (EX, GROUND - 10), 34, 0.13 * o)

    for i, sw in enumerate(pl.rise):                     # glints circling inside the deck, drawn into the eye
        e = sw["launch"] + sw["dur"]
        if f < e:
            continue
        flash(math.ceil(e) - 1, *sw["ent"], 16, 0.7, 6)
        s = ease((f - sw["sink"]) / sw["sinkd"])
        rr = sw["r"] * (1 - s) + max(hr * 0.95, 4) * s
        if f >= sw["sink"] + sw["sinkd"] or f >= PLUNGE0:
            flash(int(sw["sink"] + sw["sinkd"]), EX + rr * math.cos(sw["th"]), EY, 10, 0.5, 5)
            continue
        th = sw["th"] + 1.25 * (SPIN[f] - SPIN[int(e)])
        x, y = EX + rr * math.cos(th), EY + rr * math.sin(th) * FLAT
        tx, ty = -math.sin(th), math.cos(th) * FLAT
        n = math.hypot(tx, ty) or 1
        tx, ty = tx / n, ty / n
        k = flick(i, f, pl.seed)
        front = 0.55 + 0.45 * max(0.0, math.sin(th))
        for q in range(4):
            cv.over([round(y - ty * q)], [round(x - tx * q)], WHITE if q == 0 else hexf(GOLD),
                    front * (1 - q / 4) * (0.5 + 0.5 * k))
        glow(L, x, y, 6, 0.5 * k * front)

    ctone = np.full((H, W), -1)
    ctone[CY0:CY1, CX0:CX1] = tone
    draw_big(cv, L, f, hole, ctone)
    flash(BURST, EX, (CLOUD_LOW + GROUND) / 2, 100, 0.9, 8)
    flash(IMPACT, EX, GROUND - 6, 50, 1.0, 8)
    impact(cv, L, f, pl)

    ring = []
    for i, sw in enumerate(pl.rise):
        p = rise_pos(sw, i, f)
        if p is not None:
            ring.append((p[3], i, sw, p, False))
    for i, sw in enumerate(pl.ret):
        if sw["out"] <= f < sw["out"] + 3:
            q = ret_pos(sw, i, sw["out"] - 1)
            if q:
                star(cv, *q[0], 3 - int(f - sw["out"]), 1.0)
                flash(int(math.ceil(sw["out"])), *q[0], 10, 0.6, 4)
        p = ret_pos(sw, i, f)
        if p is not None:
            ring.append((p[3], i, sw, p, True))
    ring.sort(key=lambda r: r[0])                       # far side first, near side last

    def ring_sword(i, sw, p, ret):
        (x, y), ang, fs, dep = p
        vis = 0.55 + 0.45 * (dep + 1) / 2                # the far side of a ring is dimmer
        if ret:
            flying = f < sw["arrive"] + 3
            tr = [q[0] for q in (ret_pos(sw, i, f - k * 0.8) for k in range(7 if flying else 5)) if q is not None]
            trail(cv, tr, (0.8 if flying else 0.45) * vis)
            small(cv, L, x, y, ang, a=vis, heat=max(0.0, 1 - (f - BURST) / 6), lk=vis, i=i, f=f, seed=pl.seed,
                  fs=fs)
            flash(BURST, x, y, 12, 0.6, 5)
            return
        flying = f >= sw["launch"]
        tr = [q[0] for q in (rise_pos(sw, i, f - k * 0.8) for k in range(7 if flying else 5)) if q is not None]
        trail(cv, tr, (0.8 if flying else 0.45) * vis)
        a = vis * min(1.0, (f - sw["spawn"]) / 3 + 0.34)
        small(cv, L, x, y, ang, a=a, lk=a, i=i, f=f, seed=pl.seed, fs=fs)
        flash(int(math.ceil(sw["spawn"])), x, y, 10, 0.5, 5)
        flash(int(math.ceil(sw["launch"])), x, y, 12, 0.5, 5)

    for dep, i, sw, p, ret in ring:
        if dep < 0:
            ring_sword(i, sw, p, ret)
    if caster:                                           # the caster stands between the two halves of the rings
        foot, lift, flut, ghost = caster_state(f)
        g = cs.draw(cv.over, (H, W), foot, 0.52, caster_pose(f, foot, 0.52), f, lift, flut, hair="loose")
        cs.body_light(L, g, 0.4 + 0.6 * min(1, f / 20))
        cs.finger_light(L, g, point_of(f), max(0.0, 1 - abs(f - IMPACT) / 6))
    for dep, i, sw, p, ret in ring:
        if dep >= 0:
            ring_sword(i, sw, p, ret)

    for (x, y, r, k) in events:
        glow(L, x, y, r, k)
    return cv.rgba(), L


def caster_state(f):
    """Mockup caster (preview only): feet, lift, flutter and the avatar's strength at frame f."""
    up = 6 * ease(f / T(16)) * (1 - ease((f - BURST - 2) / 14))
    bob = 1.5 * math.sin(f * 0.25) * ease(f / T(16)) * (1 - ease((f - BURST - 2) / 14))
    act = 0.3 + 0.5 * ease((f - T(10)) / (T(40) - T(10))) * (1 - ease((f - BURST - 8) / 30))
    ghost = ease((f - T(4)) / (T(30) - T(4))) * (1 - ease((f - BURST - 18) / 26))
    return (FOOT[0], FOOT[1] - up + bob), act, 0.35 + 0.5 * act, ghost


def point_of(f):
    return ease((f - IMPACT + 10) / 6) * (1 - ease((f - BURST - 2) / 8))


def caster_pose(f, foot, sc):
    aim = cs.aim_from(foot, sc, (EX, GROUND - 20))
    jab = 3.0 * max(0.0, 1 - abs(f - IMPACT) / 5)
    return cs.pose_at(f, [(0, "chest"), (T(8), "raise"), (PLUNGE0 + 2, "raise"), (IMPACT - 6, "point"),
                          (BURST + 6, "point"), (BURST + 20, "chest")],
                      [(0, "rest"), (T(10), "out"), (BURST + 8, "out"), (BURST + 22, "behind")], aim, jab)


def tint(L):
    return pfx.tint(np.repeat(np.clip(L, 0, 1)[..., None], 3, -1), LIGHT_RAMP)


def grid_img(frames, cols, scale=1):
    h, w = frames[0].shape[:2]
    rows = math.ceil(len(frames) / cols)
    out = np.zeros((rows * h, cols * w, 4), np.uint8)
    for i, fr in enumerate(frames):
        r, c = divmod(i, cols)
        out[r * h:(r + 1) * h, c * w:(c + 1) * w] = fr
    im = Image.fromarray(out, "RGBA")
    return im.resize((im.width * scale, im.height * scale), Image.NEAREST) if scale > 1 else im


def main():
    OUT.mkdir(exist_ok=True)
    cols, lights, finals, previews, mids = [], [], [], [], []
    covers, means = [], []
    hits = [ex.hit(IMPACT, FPS, freeze=0.12, shake=4, push=6, react="knockback")]
    keys = [22, 44, round(T(70)), PLUNGE0 + 8, IMPACT, BURST + 12, BURST + 28, BURST + 44]
    for f in range(N):
        col, L = render(f)
        lt = tint(L)
        cols.append(col)
        lights.append(lt)
        finals.append(pfx.composite(col, lt))
        a = col[..., 3] > 0
        if a.any():
            ys, xs = np.nonzero(a)
            box = np.clip(L[ys.min():ys.max() + 1, xs.min():xs.max() + 1], 0, 1)
            covers.append((box > 0.03).mean())
            if (box > 0.03).any():
                means.append(box[box > 0.03].mean())
        pc, pL = render(f, caster=True)
        pc = tg.under(pc, tg.draw((H, W), (430, GROUND), f, hits, FPS, facing=-1))
        previews.append(pfx.composite(pc, tint(pL), bg="#0c0a14"))
        if f in keys:
            mids.append(pfx.composite(pc, tint(pL), bg="#5a5866"))

    meta = ex.write(OUT, NAME, finals, FPS, PIVOT, False, light=lights, color=cols, states=STATES, hits=hits,
                    poses=[ex.pose(-0.2, "windup"), ex.pose(0.0, "cast", "snap"), ex.pose(SWIRL0 / FPS, "channel"),
                           ex.pose((IMPACT - 6) / FPS, "release", "snap"), ex.pose((IMPACT + 6) / FPS, "follow"),
                           ex.pose((IMPACT + 33) / FPS, "recover")],
                    target={"x": EX - FOOT[0], "react": "knockback"},
                    extra=fc.check(dict(fc.meta("side", W, H, PIVOT, target=[EX, GROUND]), glow="strong",
                                        clarity="hazy")))

    grid_img([previews[k] for k in keys], 4, 2).save(OUT / "keys_2x_dark.png")
    grid_img(mids, 4, 2).save(OUT / "keys_2x_mid.png")
    for k in (22, 44, PLUNGE0 + 8, BURST + 28):
        Image.fromarray(previews[k]).resize((W * 4, H * 4), Image.NEAREST).save(OUT / f"f{k:03d}_4x.png")
    grid_img(previews[::5], 6).save(OUT / "strip_1x.png")
    pfx.gif(ex.hitstop(previews, hits, FPS), OUT / f"{NAME}.gif", FPS, scale=2)

    print(f"light: cover {100 * np.median(covers):.0f} %  mean {np.median(means):.3f}  "
          f"(strong mean 0.08-0.14, hazy cover 40-80 %)")
    bad = ex.check(finals, lights, loop=False, src=__file__)
    bad += ex.check_seeds(lambda f, sd: render(f, sd)[0], N)
    bad += ex.check_act(meta["meta"]["beanfx"].get("act", {}), N, FPS)
    for b in bad:
        print(b)
    print(f"{len(bad)} problems" if bad else "checks: clean")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
