"""Great Wild Sky-Prison Finger: a storm swirls, its eye tears open, a giant stone finger carved with runes slides out of
the void and slams the ground, which breaks into heaved slabs inside a rune ring; then the finger crumbles and
pulls back, the rift shuts and the clouds thin. General mode, 320x320, 30 fps, one-shot, glow strong, soft style,
with a small glowing caster (violet-silver) who flies up first and points down.

State table (30 fps, 195 frames, 6.5 s)
  state     frames    s    what moves                                                         carrier
  fly       0..29    1.0   caster lifts off and raises the sign to the sky, the tip charges     caster
  gather   30..59    1.0   dark clouds roll in from the sides and swirl                         clouds
  tear     60..83    0.8   purple cracks split the swirl's eye, the hole tears open             rift
  descend  84..119   1.2   finger slides out, hangs 0.3 s, slams; the caster's arm follows it   finger, caster
  prison  120..155   1.2   2-frame white peak, the ground breaks into heaved slabs, ring spreads ground, ring
  fade    156..194   1.3   cracks glow, the finger crumbles and pulls up, rift shuts            shards, dust
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "kit"))
import caster as cs  # noqa: E402
import pfx  # noqa: E402
from fxlib import noise  # noqa: E402

NAME = "dai_hoang_tu_thien_chi"
W = H = 320
FPS = 30
# states: start and length, each starts where the last ends
FLY, FLY_N = 0, 30
GATHER = FLY + FLY_N
GATHER_N = 30
TEAR = GATHER + GATHER_N
TEAR_N = 24
DESC = TEAR + TEAR_N
DESC_N = 36
EMERGE_N, HOLD_N = 24, 9                     # descend = emerge, hold, slam (3 frames)
PRISON = DESC + DESC_N
PRISON_N = 36
FADE = PRISON + PRISON_N
FADE_N = 39
N = FADE + FADE_N
STATES = {"fly": [FLY, GATHER - 1], "gather": [GATHER, TEAR - 1], "tear": [TEAR, DESC - 1], "descend": [DESC, PRISON - 1],
          "prison": [PRISON, FADE - 1], "fade": [FADE, N - 1]}

CX, CY = 172, 58          # eye of the storm, centre of the rift
FX, GY = 172, 262         # finger axis x, ground where the tip lands
HOLE_R = 46               # rift half width when open (half as deep)
FOOT = (62, 290)          # caster's feet

STONE = ["#16121f", "#2e2840", "#4e4760", "#767088", "#a6a2b6", "#d8d6e4"]
CLOUD = ["#0e0b16", "#1c1628", "#2d2440", "#43385a", "#605279", "#8a74ae"]
VOID = ["#06030d", "#140a28", "#2c1258", "#4a1e8a"]
CAST = ["#22163e", "#4a3480", "#8a6cd0", "#cbb8f4", "#fbf6ff"]
RIM, CORE, EDGE = "#e2c8ff", "#ffffff", "#9a5cf0"
LIGHT_RAMP = ["#2c0b5a", "#8a3cf0", "#d6b0ff", "#ffffff"]
GLOW = "strong"


def hexf(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


STONE_F = np.stack([hexf(c) for c in STONE])
CLOUD_F = np.stack([hexf(c) for c in CLOUD])
VOID_F = np.stack([hexf(c) for c in VOID])

YY, XX = np.mgrid[0:H, 0:W].astype(float)
rng = np.random.default_rng(7)


def clamp(t):
    return min(max(t, 0.0), 1.0)


def ease_io(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 2


def ease_in(t):
    t = clamp(t)
    return t * t


def hsh(i, salt=0):
    return (math.sin(i * 12.9898 + salt * 78.233) * 43758.5453) % 1.0


def fbm(x, y, cells, seed, octs=3):
    s, a, n = 0.0, 1.0, 0.0
    for o in range(octs):
        s = s + a * noise(x, y, cells / 2 ** o, seed + o)
        n += a
        a *= 0.5
    return s / n


# ---------------------------------------------------------------- canvas
class Frame:
    def __init__(self):
        self.col = np.zeros((H, W, 4))
        self.L = np.zeros((H, W))

    def over(self, ys, xs, rgb, a):
        ys = np.asarray(ys).astype(int).ravel()
        xs = np.asarray(xs).astype(int).ravel()
        rgb = np.broadcast_to(np.asarray(rgb, float), (len(ys), 3)) if np.ndim(rgb) == 1 else np.asarray(rgb)
        a = np.broadcast_to(np.asarray(a, float), ys.shape).astype(float)
        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W) & (a > 0)
        ys, xs, rgb, a = ys[ok], xs[ok], rgb[ok], a[ok]
        ca = self.col[ys, xs, 3]
        na = a + ca * (1 - a)
        self.col[ys, xs, :3] = (rgb * a[:, None] + self.col[ys, xs, :3] * (ca * (1 - a))[:, None]) \
            / np.maximum(na, 1e-6)[:, None]
        self.col[ys, xs, 3] = na

    def mask(self, m, rgb, a=1.0):
        ys, xs = np.nonzero(m)
        if len(ys) == 0:
            return
        if np.ndim(rgb) == 3:
            rgb = rgb[ys, xs]
        if np.ndim(a) == 2:
            a = a[ys, xs]
        self.over(ys, xs, rgb, a)


def win(x, y, rx, ry):
    return (slice(int(max(0, y - ry)), int(min(H, y + ry + 2))), slice(int(max(0, x - rx)), int(min(W, x + rx + 2))))


def glow(L, x, y, r, k, flat=1.0):
    sy, sx = win(x, y, r, r * flat)
    if sy.start >= sy.stop or sx.start >= sx.stop:
        return
    d = np.hypot(XX[sy, sx] - x, (YY[sy, sx] - y) / flat) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def glow_line(L, p0, p1, r, k):
    (ax, ay), (bx, by) = p0, p1
    x0, x1 = min(ax, bx) - r, max(ax, bx) + r
    y0, y1 = min(ay, by) - r, max(ay, by) + r
    sy = slice(int(max(0, y0)), int(min(H, y1 + 2)))
    sx = slice(int(max(0, x0)), int(min(W, x1 + 2)))
    if sy.start >= sy.stop or sx.start >= sx.stop:
        return
    X, Y = XX[sy, sx], YY[sy, sx]
    ex, ey = bx - ax, by - ay
    h = np.clip(((X - ax) * ex + (Y - ay) * ey) / (ex * ex + ey * ey or 1e-9), 0, 1)
    d = np.hypot(X - ax - ex * h, Y - ay - ey * h) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def glow_ring(L, x, y, R, r, k, flat=1.0):
    sy, sx = win(x, y, R + r, (R + r) * flat + r)
    d = np.abs(np.hypot(XX[sy, sx] - x, (YY[sy, sx] - y) / flat) - R) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def pixels(pts):
    """Polyline points to unique integer pixels, sampled every half pixel."""
    out = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        n = max(int(math.hypot(bx - ax, by - ay) * 2), 1)
        t = np.linspace(0, 1, n, endpoint=False)
        out.append(np.stack([ay + (by - ay) * t, ax + (bx - ax) * t], 1))
    if not out:
        return np.zeros((0, 2), int)
    p = np.round(np.concatenate(out + [np.array([[pts[-1][1], pts[-1][0]]])])).astype(int)
    return np.unique(p, axis=0)


def line_px(fr, pts, core, edge, a=1.0, edge_a=0.75):
    """A 1 px hot core with a 1 px tinted edge (soft style line)."""
    p = pixels(pts)
    if len(p) == 0:
        return
    e = np.concatenate([p + d for d in ((0, 1), (0, -1), (1, 0), (-1, 0))])
    fr.over(e[:, 0], e[:, 1], hexf(edge), edge_a * a)
    fr.over(p[:, 0], p[:, 1], hexf(core), a)


def polyline_part(pts, p):
    """The first share p (0..1) of a polyline by length."""
    pts = [tuple(q) for q in pts]
    seg = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    tot = sum(seg) * clamp(p)
    out = [pts[0]]
    for (a, b), ln in zip(zip(pts, pts[1:]), seg):
        if tot <= 0:
            break
        if ln <= tot:
            out.append(b)
            tot -= ln
        else:
            t = tot / ln
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            break
    return out


# ---------------------------------------------------------------- timing curves
def gather(f):
    return ease_io((f - GATHER) / 26)


def cloud_amt(f):
    return gather(f) * (1 - 0.72 * ease_io((f - (FADE + 16)) / 22))


def opening(f):
    if f < FADE + 20:
        return ease_out((f - (TEAR + 10)) / 13)
    return 1 - ease_io((f - (FADE + 20)) / 14)


def tip_y(f):
    """Finger tip height, or None when it is not out."""
    if f < DESC:
        return None
    t = f - DESC
    if t < EMERGE_N:
        return CY + 4 + 90 * (t / EMERGE_N) ** 1.5
    if t < EMERGE_N + HOLD_N:
        u = (t - EMERGE_N) / HOLD_N
        return CY + 94 + 6 * u + (1 if t % 2 else -1) * 0.8
    if f < PRISON:
        s = (t - EMERGE_N - HOLD_N + 1) / 4
        return CY + 100 + (GY - CY - 100) * s * s
    if f == PRISON:
        return GY + 5
    if f < PRISON + 4:
        return GY + 4
    r0 = FADE + 6
    if f < r0:
        return GY + 3
    y = GY + 3 - (GY + 3 - (CY - 34)) * ease_io((f - r0) / 24)
    return y if y > CY - 30 else None


def rune_glow(f):
    if f < DESC + 18:
        return 0.0
    if f < DESC + EMERGE_N + HOLD_N:
        return 0.65 * ease_io((f - DESC - 18) / 15)
    if f < PRISON:
        return 0.8
    if f < PRISON + 2:
        return 1.3
    if f < FADE:
        return 0.7 + 0.6 * math.exp(-(f - PRISON - 2) / 4)
    return 0.7 * (1 - ease_io((f - FADE) / 16))


def charge(f):
    if f < PRISON:
        return 0.3 + 0.7 * ease_io((f - FLY) / (DESC + EMERGE_N - FLY))
    return 1 - 0.6 * ease_io((f - PRISON) / 30)


# ---------------------------------------------------------------- clouds and rift
CDX = XX - CX
CDY = (YY - CY) / 0.36
C_R = np.hypot(CDX, CDY)
C_TH = np.arctan2(CDY, CDX)
C_ELL = np.hypot((XX - CX) / 140, (YY - CY) / 50)
H_R = np.hypot(XX - CX, (YY - CY) / 0.5)
H_TH = np.arctan2((YY - CY) / 0.5, XX - CX)


def jag(th):
    tri = np.abs(((th * 9 / math.pi) % 2) - 1) - 0.5
    return 0.22 * tri + 0.12 * np.sin(5 * th + 1.3) + 0.07 * np.sin(13 * th + 0.4)


H_JAG = jag(H_TH)


def hole(f):
    o = opening(f)
    if o <= 0.01:
        return o, np.zeros((H, W), bool), np.zeros((H, W))
    hr = HOLE_R * o * (1 + H_JAG)
    return o, H_R < hr, hr


def draw_clouds(fr, f, hole_in, hr, o):
    amt = cloud_amt(f)
    if amt <= 0.01:
        return
    th = C_TH + (0.012 + 0.05 * np.exp(-C_R / 60)) * f + 0.9 * np.exp(-C_R / 80) * gather(f)
    rr = C_R + 0.9 * f
    nx, ny = rr * np.cos(th), rr * np.sin(th)
    big = fbm(nx + 300, ny + 300, 46, 11)
    det = fbm(nx * 1.3 + 90, ny * 1.3 + 40, 22, 21, 2)
    reach = 1.1 - 1.1 * gather(f)
    env = np.clip((1.0 - C_ELL) / 0.35, 0, 1) * np.clip((C_ELL - reach) / 0.25 + (1 if reach <= 0 else 0), 0, 1)
    dens = np.clip((big - 0.3) / 0.22, 0, 1) * env * amt
    dens = np.maximum(dens, np.clip((0.85 - C_ELL) / 0.4, 0, 1) * env * amt * 0.75)
    if o > 0.01:
        dens = np.where(hole_in, 0, dens)
        near = np.exp(-np.clip(H_R - hr, 0, None) / 10) * o
    else:
        near = np.zeros((H, W))
    under = np.clip((YY - CY) / 40, -1, 1)
    shade = 0.5 * det + 0.25 * (1 - dens) + 0.4 * near + 0.1 * under + 0.02
    # puff volume: a lit step where the density rises toward the top left, a dark one toward the bottom right
    tl = np.roll(np.roll(big, 2, 0), 2, 1)
    br = np.roll(np.roll(big, -2, 0), -2, 1)
    shade = shade + np.where(big - tl > 0.012, 0.2, 0) - np.where(big - br > 0.012, 0.16, 0)
    tone = np.clip((shade * 5).astype(int), 0, 5)
    a = np.select([dens > 0.55, dens > 0.25, dens > 0.07], [0.96, 0.82, 0.5], 0.0)
    fr.mask(a > 0, CLOUD_F[tone], a)
    # light: the storm glows from inside its eye, more as the rift opens
    glow(fr.L, CX, CY + 6, 150, (0.08 + 0.14 * o) * amt, flat=0.34)
    glow(fr.L, CX, CY + 4, 60, 0.12 * gather(f) * amt, flat=0.5)


def crack_paths():
    paths = []
    for i in range(8):
        a = i * math.tau / 8 + (hsh(i, 3) - 0.5) * 0.5
        pts = [(0.0, 0.0)]
        for k in range(1, 12):
            r = k * 6
            j = (hsh(i * 17 + k, 5) - 0.5) * 5
            pts.append((math.cos(a) * r - math.sin(a) * j, math.sin(a) * r + math.cos(a) * j))
        paths.append(pts)
    return paths


CRACKS = crack_paths()


def draw_rift(fr, f, hole_in, hr, o):
    if f < TEAR:
        return
    # cracks: grow from the eye, then linger past the torn rim and fade
    grow = ease_out((f - TEAR) / 12)
    fadek = 1 - ease_io((f - DESC) / (FADE + 10 - DESC))
    if grow > 0 and fadek > 0:
        for i, pts in enumerate(CRACKS):
            ln = grow * (0.6 + 0.4 * hsh(i, 9))
            p = polyline_part([(CX + x, CY + y * 0.5) for x, y in pts], ln)
            if len(p) < 2:
                continue
            q = pixels(p)
            keep = ~hole_in[np.clip(q[:, 0], 0, H - 1), np.clip(q[:, 1], 0, W - 1)]
            q = q[keep]
            if len(q):
                fr.over(q[:, 0], q[:, 1], hexf(CORE if f < DESC else RIM), fadek)
            k = 0.5 * fadek * (1.3 if f < TEAR + 12 else 1)
            Lc = np.zeros((H, W))
            for a_, b_ in zip(p, p[1:]):
                glow_line(Lc, a_, b_, 3, k * 0.5)
                glow_line(Lc, a_, b_, 9, k * 0.2)
            fr.L += Lc * ~hole_in if o > 0.01 else Lc
    if f in (TEAR + 10, TEAR + 11):                                  # the pop as the eye tears
        glow(fr.L, CX, CY, 34, 0.7, flat=0.6)
    if o <= 0.01:
        return
    # void: deep purple swirling, a few stars
    sw = fbm(H_R * np.cos(H_TH + 0.04 * f) + 50, H_R * np.sin(H_TH + 0.04 * f) + 80, 12, 31, 2)
    edge = np.clip(H_R / np.maximum(hr, 1e-6), 0, 1)
    vt = np.clip((sw * 1.6 + edge * 1.8 - 0.9).astype(int), 0, 3)
    fr.mask(hole_in, VOID_F[vt], 1.0)
    star = hole_in & ((np.floor(XX) * 7 + np.floor(YY) * 13 + (f // 4)) % 97 == 0) & (edge < 0.8)
    fr.mask(star, hexf("#d8c0ff"), 0.9)
    rim = hole_in & (H_R > hr - 1.6)
    fr.mask(rim, hexf(RIM), 1.0)
    fr.mask(hole_in & (H_R > hr - 0.8) & ((XX + YY + f) % 3 == 0), hexf(CORE), 1.0)
    # light: rim core and pool, the void's own pool
    glow_ring(fr.L, CX, CY, HOLE_R * o, 4, 0.45 * o, flat=0.5)
    glow_ring(fr.L, CX, CY, HOLE_R * o, 12, 0.2 * o, flat=0.5)
    glow(fr.L, CX, CY + 8, 75, 0.2 * o, flat=0.6)


# ---------------------------------------------------------------- the finger
def hw_at(s):
    return (17 + 4 * np.clip(s / 90, 0, 1) + 3 * np.clip((s - 90) / 110, 0, 1)
            + 1.6 * np.exp(-((s - 64) / 7) ** 2) + 1.6 * np.exp(-((s - 132) / 8) ** 2))


def glyph(seed):
    """3 to 4 strokes in an 8 x 10 box on a 3 x 3 grid, always with a spine."""
    pts = [(x, y) for y in (-5, 0, 5) for x in (-4, 0, 4)]
    segs = [((0, -5), (0, 5))]
    r = np.random.default_rng(seed)
    while len(segs) < 3 + seed % 2:
        a, b = pts[r.integers(9)], pts[r.integers(9)]
        if a != b and math.hypot(b[0] - a[0], b[1] - a[1]) <= 6.5 and (a, b) not in segs:
            segs.append((a, b))
    return segs


RUNES = [(s, (hsh(i, 2) - 0.5) * 6, glyph(i + 3)) for i, s in enumerate((44, 92, 112, 156, 180, 206, 232))]

# voronoi cells in finger space (v across, s up from the tip) for the crumble
CELL = 9.0
GV = np.arange(-4, 4)
GS = np.arange(-1, 30)
SEED_V = {(i, j): (i + 0.15 + 0.7 * hsh(i * 31 + j, 1)) * CELL for i in GV for j in GS}
SEED_S = {(i, j): (j + 0.15 + 0.7 * hsh(i * 31 + j, 2)) * CELL for i in GV for j in GS}
CELLS = {}
for (i, j), sv in SEED_V.items():
    ss = SEED_S[(i, j)]
    if ss < 0 or abs(sv) > hw_at(ss) + 2:
        continue
    r1, r2 = hsh(i * 7 + j, 4), hsh(i * 3 + j, 6)
    if ss < 130:
        rel = FADE + 2 + ss / 130 * 12 + r1 * 6
    else:
        rel = FADE + 14 + r1 * 14 if r2 < 0.4 else 1e9
    CELLS[(i, j)] = dict(v=sv, s=ss, rel=rel, vx=sv * 0.04 + (r2 - 0.5) * 1.2, vy=0.3 - r1 * 0.8,
                         size=1 + int(r2 * 3))


def voronoi(v, s):
    gi, gj = np.floor(v / CELL).astype(int), np.floor(s / CELL).astype(int)
    best, second = np.full(v.shape, 1e9), np.full(v.shape, 1e9)
    bi, bj = np.zeros(v.shape, int), np.zeros(v.shape, int)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            ii, jj = np.clip(gi + di, GV[0], GV[-1]), np.clip(gj + dj, GS[0], GS[-1])
            sv = (ii + 0.15 + 0.7 * ((np.sin((ii * 31 + jj) * 12.9898 + 78.233) * 43758.5453) % 1.0)) * CELL
            ss = (jj + 0.15 + 0.7 * ((np.sin((ii * 31 + jj) * 12.9898 + 2 * 78.233) * 43758.5453) % 1.0)) * CELL
            d = np.hypot(v - sv, s - ss)
            closer = d < best
            second = np.where(closer, best, np.minimum(second, d))
            bi, bj = np.where(closer, ii, bi), np.where(closer, jj, bj)
            best = np.where(closer, d, best)
    return bi, bj, second - best


def draw_finger(fr, f, hole_in, o, layer_front):
    ty = tip_y(f)
    if ty is None:
        return None
    sy = slice(0, int(min(H, ty + 3)))
    X, Y = XX[sy], YY[sy]
    v = X - FX
    s = ty - Y
    hw = hw_at(s)
    cap = np.where(s < 17, np.sqrt(np.clip(1 - ((17 - s) / 17) ** 2, 0, 1)), 1.0)
    inside = (s >= 0) & (np.abs(v) <= hw * cap)
    vis = hole_in[sy] | (Y >= CY + 23 * o * 0.85)
    inside &= vis & (Y >= CY - HOLE_R * 0.5 * o)
    # crumble: released cells leave the body
    bi, bj, gap = voronoi(v, s)
    gone = np.zeros(inside.shape, bool)
    if f >= FADE:
        for key, c in CELLS.items():
            if f >= c["rel"]:
                gone |= (bi == key[0]) & (bj == key[1])
    inside &= ~gone
    fr.fmask = np.zeros((H, W), bool)
    fr.fmask[sy] = inside
    if not inside.any():
        return ty
    vn = v / np.maximum(hw * cap, 1e-6)
    tex = noise(v + 60, s, 7, 41)
    shade = 0.6 - 0.36 * vn - 0.18 * vn ** 2 + 0.22 * (tex - 0.5)
    # knuckle creases and the nail
    crease = np.zeros(inside.shape, bool)
    lit = np.zeros(inside.shape, bool)
    for sk in (64, 132):
        for off, wd in ((-3.5, 0.45), (0, 0.7), (3.5, 0.5)):
            c = s - (sk + off + 3 * vn ** 2)
            crease |= (np.abs(c) < 0.55) & (np.abs(vn) < wd)
            lit |= (np.abs(c + 1) < 0.5) & (np.abs(vn) < wd - 0.1)
    nail_d = np.hypot(vn / 0.6, np.clip((20 - s) / 14, 0, None))
    nail = (nail_d < 1) & (s < 34)
    shade = np.where(nail, shade + 0.18, shade)
    tone = np.clip((shade * 5).astype(int), 0, 4)
    tone = np.where(lit, np.minimum(tone + 1, 5), tone)
    tone = np.where(crease | (nail & (nail_d > 0.86)) | ((np.abs(s - 34) < 0.6) & (np.abs(vn) < 0.6)), 1, tone)
    tone = np.where(nail & (np.abs(vn + 0.3) < 0.08) & (s > 10) & (s < 30), 5, tone)
    stone_cr = np.abs(noise(v + 7, s * 0.7, 16, 51) - 0.5) < 0.022
    tone = np.where(stone_cr, 1, tone)
    # silhouette: lit rim left, dark edge right and at the tip
    er = inside.copy()
    er[1:-1, 1:-1] = inside[1:-1, 1:-1] & inside[:-2, 1:-1] & inside[2:, 1:-1] & inside[1:-1, :-2] & inside[1:-1, 2:]
    edge = inside & ~er
    tone = np.where(edge & (vn < -0.2) & (s > 8), 4, np.where(edge, 0, tone))
    rgb = STONE_F[tone]
    # depth: the base fades into the void inside the rift
    depth = np.clip((CY + 14 - Y) / 30, 0, 1)[..., None]
    rgb = rgb * (1 - 0.8 * depth) + VOID_F[1] * 0.8 * depth
    # crumble cracks glow along the cell borders before they let go
    if f >= FADE:
        ck = ease_io((f - FADE) / 5)
        cr = inside & (gap < 0.6) & (noise(v, s, 10, 61) > 0.42)
        rgb = np.where(cr[..., None], rgb * (1 - 0.8 * ck) + hexf(RIM) * 0.8 * ck, rgb)
        fr.L[sy] += np.where(cr, 0.3 * ck, 0) + np.where(inside & (gap < 2.5), 0.05 * ck, 0)
    # runes: carved dark, then lit
    rg = rune_glow(f)
    rune = np.zeros(inside.shape, bool)
    for s0, v0, segs in RUNES:
        if not ((s >= s0 - 6) & (s <= s0 + 6)).any():
            continue
        for (ax, ay), (bx, by) in segs:
            ex, ey = bx - ax, by - ay
            px_, py_ = v - (v0 + ax), (s0 - ay) - s
            h = np.clip((px_ * ex + py_ * -ey) / (ex * ex + ey * ey or 1e-9), 0, 1)
            rune |= np.hypot(px_ - ex * h, py_ + ey * h) < 0.62
    rune &= inside
    if rg > 0.2:
        rc = hexf(CORE) if rg > 1.0 else hexf(RIM) * min(rg, 1) + STONE_F[0] * (1 - min(rg, 1))
        rgb = np.where(rune[..., None], rc, rgb)
    else:
        rgb = np.where(rune[..., None], STONE_F[0], rgb)
    if layer_front:
        fr.mask(inside, rgb, 1.0)
    else:
        fr.mask(inside, rgb, 1.0)
    # light: runes (core and pool), a faint void pool along the finger, the tip as it lands
    if rg > 0.05:
        for s0, v0, _ in RUNES:
            y0 = ty - s0
            if y0 > CY + 10 * o and y0 < ty:
                glow(fr.L, FX + v0, y0, 5, 0.55 * min(rg, 1.2))
                glow(fr.L, FX + v0, y0, 15, 0.25 * min(rg, 1.2))
    top = max(CY + 8, ty - 230)
    if ty > top:
        glow_line(fr.L, (FX, top), (FX, ty - 6), 40, 0.06 * (0.4 + rg))
    return ty


def draw_fragments(fr, f):
    if f < FADE:
        return
    for c in CELLS.values():
        t = f - c["rel"]
        if t < 0 or t > 26:
            continue
        ty = tip_y(int(c["rel"])) or GY
        if ty - c["s"] < CY + 14:              # still inside the rift: it never shows
            continue
        x = FX + c["v"] + c["vx"] * t
        y = ty - c["s"] + c["vy"] * t + 0.09 * t * t
        if y > GY + 16:
            continue
        a = 1 - ease_in(t / 26)
        sz = c["size"] - (1 if t > 14 else 0)
        if sz <= 0:
            fr.over([round(y)], [round(x)], hexf("#8a6cd0"), 0.6 * a)
            glow(fr.L, x, y, 4, 0.15 * a)
            continue
        ys, xs = np.mgrid[0:sz + 1, 0:sz + 1]
        ys, xs = ys.ravel() + round(y), xs.ravel() + round(x)
        tn = np.where((ys - round(y)) + (xs - round(x)) <= 0, 4, np.where((ys - round(y)) == sz, 1, 3))
        fr.over(ys, xs, STONE_F[tn], a)
        if t < 10:
            glow(fr.L, x + sz / 2, y + sz / 2, 6, 0.18 * (1 - t / 10))


# ---------------------------------------------------------------- ground: ring, cage, cracks, dust
RX, RY = 74, 19
GROUND_CRACKS = []
for i in range(11):
    a = i * math.tau / 11 + (hsh(i, 8) - 0.5) * 0.4
    ln = 34 + 40 * hsh(i, 9)
    pts = [(0.0, 0.0)]
    for k in range(1, 8):
        r = ln * k / 7
        j = (hsh(i * 13 + k, 10) - 0.5) * 6
        pts.append((math.cos(a) * r - math.sin(a) * j, (math.sin(a) * r + math.cos(a) * j) * 0.28))
    GROUND_CRACKS.append(pts)


def ring_k(f):
    if f < PRISON:
        return 0.0, 0.0
    grow = ease_out((f - PRISON) / 10)
    fade = 1 - ease_io((f - FADE - 4) / 24)
    return grow, fade


def draw_ring(fr, f, front):
    grow, fade = ring_k(f)
    if grow <= 0 or fade <= 0:
        return
    for k, (sc, a) in enumerate(((1.0, 0.95), (0.8, 0.7))):
        n = int(2 * math.pi * RX * sc * grow * 1.6) + 12
        th = np.linspace(0, math.tau, n, endpoint=False)
        side = np.sin(th) > 0
        th = th[side == front]
        if k == 1:
            th = th[np.sin(th * 18 + f * 0.15) > -0.3]
        ys = np.round(GY + RY * sc * grow * np.sin(th)).astype(int)
        xs = np.round(FX + RX * sc * grow * np.cos(th)).astype(int)
        fr.over(ys, xs, hexf(RIM if k == 0 else EDGE), a * fade)
    # glyph ticks between the two rings, turning slowly
    for i in range(16):
        th = i * math.tau / 16 + f * 0.012
        if (math.sin(th) > 0) != front:
            continue
        r0, r1 = 0.83, 0.97
        p = [(FX + RX * grow * r * math.cos(th + d), GY + RY * grow * r * math.sin(th + d))
             for r, d in ((r0, 0), (r1, 0), (r1, 0.06))]
        q = pixels(p)
        fr.over(q[:, 0], q[:, 1], hexf(CORE), 0.9 * fade)
    if front:
        glow_ring(fr.L, FX, GY, RX * grow, 4, 0.4 * fade, flat=RY / RX)
        glow_ring(fr.L, FX, GY, RX * grow * 0.9, 12, 0.18 * fade, flat=RY / RX)


SLABS = []
for i in range(11):
    a0 = i * math.tau / 11 + (hsh(i, 30) - 0.5) * 0.22
    a1 = (i + 1) * math.tau / 11 + (hsh(i + 1, 30) - 0.5) * 0.22 - 0.09
    SLABS.append(dict(a0=a0, a1=a1, am=(a0 + a1) / 2, rin=10 + 6 * hsh(i, 31), rout=44 + 24 * hsh(i, 32),
                      bulge=1.05 + 0.15 * hsh(i, 35), tilt=0.3 + 0.25 * hsh(i, 33), sink=2 + 3 * hsh(i, 34)))
GFLAT = 0.3


def gp(r, a, h):
    """Ground point at radius r and angle a round the impact, lifted h px."""
    return (FX + r * math.cos(a), GY + GFLAT * r * math.sin(a) - h)


def poly(pts):
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    sy = slice(int(max(0, min(ys))), int(min(H, max(ys) + 2)))
    sx = slice(int(max(0, min(xs))), int(min(W, max(xs) + 2)))
    X, Y = XX[sy, sx], YY[sy, sx]
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    m = np.ones(X.shape, bool)
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        m &= ((bx - ax) * (Y - ay) - (by - ay) * (X - ax)) * area >= 0
    return sy, sx, m


def fill(fr, pts, tone_fn, a):
    sy, sx, m = poly(pts)
    if not m.any():
        return None
    er = m.copy()
    er[1:-1, 1:-1] = m[1:-1, 1:-1] & m[:-2, 1:-1] & m[2:, 1:-1] & m[1:-1, :-2] & m[1:-1, 2:]
    tone = tone_fn(XX[sy, sx], YY[sy, sx], m & ~er)
    ys, xs = np.nonzero(m)
    fr.over(ys + sy.start, xs + sx.start, STONE_F[tone[ys, xs]], a)
    return m


def heave(f):
    if f < PRISON:
        return 0.0
    t = f - PRISON
    h = ease_out(t / 4) + 0.15 * math.sin(min(t, 8) / 8 * math.pi) * (t < 8)
    return h * (1 - 0.2 * ease_io((f - FADE) / 20))


def draw_crater(fr, f, front):
    """The broken ground: slabs round the impact, inner edges sunk, outer edges heaved up, purple light between."""
    hv = heave(f)
    if hv <= 0:
        return
    a = 1 - ease_io((f - (N - 20)) / 19)
    if front:
        glow(fr.L, FX, GY, 30, 0.3 * math.exp(-(f - PRISON) / 20) + 0.08 * a, flat=0.35)
    else:                                                             # the pit: hot void under the slabs
        sy, sx = win(FX, GY, 20, 7)
        d = np.hypot(XX[sy, sx] - FX, (YY[sy, sx] - GY) / GFLAT)
        ys, xs = np.nonzero(d < 18)
        hot = math.exp(-(f - PRISON) / 25)
        fr.over(ys + sy.start, xs + sx.start, VOID_F[2] * (1 - hot) + hexf(RIM) * hot, a)
    for sl in sorted(SLABS, key=lambda q: math.sin(q["am"])):
        if (math.sin(sl["am"]) > 0) != front:
            continue
        hi, ho = -sl["sink"] * hv, sl["tilt"] * (sl["rout"] - sl["rin"]) * hv
        a0, a1, rin, rout = sl["a0"], sl["a1"], sl["rin"], sl["rout"]
        am = sl["am"]
        mid = gp(rout * sl["bulge"], am, ho * 1.08)
        top = [gp(rin, a0, hi), gp(rout, a0, ho), mid, gp(rout, a1, ho), gp(rin, a1, hi)]
        # the broken outer edge, a short cliff toward the viewer on the near side
        if math.sin(am) > 0.1:
            th = 3 + ho * 0.35
            cliff = [gp(rout, a0, ho), mid, gp(rout, a1, ho), gp(rout, a1, ho - th), (mid[0], mid[1] + th),
                     gp(rout, a0, ho - th)]
            fill(fr, cliff, lambda X, Y, e: np.where(e, 0, np.where(noise(X, Y, 4, 70) > 0.55, 2, 1)), a)
        base = 3 if math.sin(am) < 0 else 2
        base += 1 if math.cos(am) > 0.4 else 0

        def tone_top(X, Y, e, base=base, am=am):
            t = base + np.where(noise(X + am * 40, Y, 6, 71) > 0.62, 1, 0) - np.where(noise(X, Y, 4, 72) < 0.3, 1, 0)
            return np.clip(np.where(e, 5 if math.sin(am) < 0.3 else 4, t), 0, 5)
        fill(fr, top, tone_top, a)
        # light leaks up through the gaps at the slab sides
        for ang in (a0, a1):
            p0, p1 = gp(rin, ang, 0), gp(rout * 0.9, ang, 0)
            glow_line(fr.L, p0, p1, 4, 0.2 * hv * a * math.exp(-(f - PRISON) / 40))



def draw_ground(fr, f):
    if f < PRISON:
        return
    t = f - PRISON
    grow = ease_out(t / 6)
    hot = math.exp(-t / 14)
    cold = 1 - ease_io((f - FADE - 10) / 28)
    for pts in GROUND_CRACKS:
        p = polyline_part([(FX + x, GY + y) for x, y in pts], grow)
        if len(p) < 2:
            continue
        q = pixels(p)
        col = hexf(RIM) * hot + hexf(CLOUD[2]) * (1 - hot)
        fr.over(q[:, 0], q[:, 1], col, max(cold, 0.45))
        if hot > 0.05:
            for a_, b_ in zip(p, p[1:]):
                glow_line(fr.L, a_, b_, 4, 0.35 * hot)
    # shock ring
    if t < 12:
        r = 20 + 100 * ease_out(t / 12)
        a = 1 - t / 12
        n = int(r * 10)
        th = np.linspace(0, math.tau, n, endpoint=False)
        fr.over(np.round(GY + r * 0.25 * np.sin(th)), np.round(FX + r * np.cos(th)), hexf(RIM), 0.8 * a)
        glow_ring(fr.L, FX, GY, r, 5, 0.3 * a, flat=0.25)
    glow(fr.L, FX, GY - 2, 18, 1.0 * hot ** 2 + 0.12)
    glow(fr.L, FX, GY - 6, 62, 0.2 + 0.4 * math.exp(-t / 5), flat=0.7)


def draw_flash(fr, f):
    t = f - PRISON
    if 0 <= t < 2:
        d = np.hypot(XX - FX, (YY - GY + 2) / 0.45)
        fr.mask(d < 24 - 6 * t, hexf(CORE), 1.0)
        fr.mask((d >= 24 - 6 * t) & (d < 30 - 6 * t), hexf(RIM), 0.9)


DUST = [dict(side=1 if i % 2 else -1, sp=0.6 + 0.4 * hsh(i, 12), r=4 + 4 * hsh(i, 13), d=hsh(i, 14) * 4,
             yo=(hsh(i, 15) - 0.5) * 8) for i in range(18)]
DEBRIS = [dict(vx=(hsh(i, 16) - 0.5) * 6, vy=-2.5 - 4 * hsh(i, 17), sz=1 + int(hsh(i, 18) * 3.5)) for i in range(26)]
DUST_C = [hexf(c) for c in ("#2a2238", "#4a3e60", "#7a6c96")]


def draw_dust(fr, f):
    if f < PRISON:
        return
    t = f - PRISON
    for p in DUST:
        u = t - p["d"]
        if u < 0 or u > 40:
            continue
        x = FX + p["side"] * (14 + 92 * p["sp"] * ease_out(u / 26))
        y = GY - 3 + p["yo"] - 10 * ease_out(u / 40)
        r = p["r"] * (0.6 + 0.8 * ease_out(u / 30))
        a = 0.6 * (1 - ease_in(u / 40))
        sy, sx = win(x, y, r + 1, r + 1)
        d = np.hypot(XX[sy, sx] - x, YY[sy, sx] - y)
        m = d < r
        if not m.any():
            continue
        lit = ((XX[sy, sx] - x) + (YY[sy, sx] - y)) / max(r, 1)
        tn = np.where(lit < -0.5, 2, np.where(lit < 0.4, 1, 0))
        ys, xs = np.nonzero(m)
        fr.over(ys + sy.start, xs + sx.start, np.stack(DUST_C)[tn[ys, xs]], a)
    for p in DEBRIS:
        if t > 22:
            continue
        x = FX + p["vx"] * t
        y = GY - 4 + p["vy"] * t + 0.35 * t * t
        if y > GY + 10:
            continue
        sz = p["sz"]
        ys, xs = np.mgrid[0:sz + 1, 0:sz + 1]
        fr.over(ys.ravel() + round(y), xs.ravel() + round(x), STONE_F[np.where((ys + xs).ravel() == 0, 4, 2)], 1.0)


def draw_slam(fr, f):
    """Speed streaks beside the finger in the three slam frames."""
    t = f - (DESC + EMERGE_N + HOLD_N)
    if t < 0 or f >= PRISON:
        return
    ty = tip_y(f)
    for i in range(6):
        side = -1 if i % 2 else 1
        x = FX + side * (24 + 6 * (i // 2) + hsh(i, 20) * 3)
        ln = 30 + 30 * hsh(i + f, 21)
        y1 = ty - 10 - hsh(i, 22) * 30
        q = pixels([(x, y1 - ln), (x, y1)])
        fr.over(q[:, 0], q[:, 1], hexf(RIM), 0.7)
        glow_line(fr.L, (x, y1 - ln), (x, y1), 4, 0.2)


# ---------------------------------------------------------------- caster
def foot_at(f):
    t = ease_io((f - FLY - 2) / 16)
    bob = 1.5 * math.sin((f - FLY) * 0.22) * ease_io((f - FLY - 16) / 8)
    return (FOOT[0] + 6 * t, FOOT[1] + (FLY_Y - FOOT[1]) * t + bob), t


FLY_Y = 152


def draw_caster(fr, f):
    foot, t = foot_at(f)
    speed = abs(foot_at(f + 1)[0][1] - foot[1])
    aim = cs.aim_from(foot, 0.44, (FX, GY))
    # the arm moves with the stone finger: down as it slides out, still while it hangs, a jab as it presses
    ty = tip_y(f)
    if f < DESC or ty is None and f < PRISON:
        w = 0.0
    elif f < FADE + 6:
        w = clamp((ty - CY) / (GY - CY))
    else:
        w = 1.0
    jab = 0.0
    if f >= DESC + EMERGE_N + HOLD_N:
        jab = 4 * math.exp(-max(f - PRISON, 0) / 7) if f >= PRISON else 2.0 * (f - DESC - EMERGE_N - HOLD_N + 1) / 4
    back = [(0, "rest"), (FLY + 8, "out")]
    up = cs.pose_at(f, [(0, "chest"), (FLY + 14, "raise")], back)
    down = cs.pose_at(f, [(0, "point"), (FADE + 18, "point"), (N - 4, "chest")], back, aim, jab)
    e = cs.lerp(up[0][0], down[0][0], w), cs.lerp(up[0][1], down[0][1], w)
    pose = (e, up[1])
    ch = charge(f)
    lift = min(1.0, 0.3 + 0.12 * speed + 0.4 * ch)
    flut = min(1.0, 0.35 + 0.1 * speed + 0.35 * ch)
    if f < FLY + 12:                                                  # the launch: a faint ring at the feet
        u = (f - FLY) / 12
        r = 6 + 22 * ease_out(u)
        th = np.linspace(0, math.tau, 80, endpoint=False)
        fr.over(np.round(FOOT[1] + r * 0.25 * np.sin(th)), np.round(FOOT[0] + r * np.cos(th)), hexf(RIM), 0.7 * (1 - u))
        glow_ring(fr.L, FOOT[0], FOOT[1], r, 4, 0.25 * (1 - u), flat=0.25)
    g = cs.draw(fr.over, (H, W), foot, 0.44, pose, f, lift, flut, hair="loose", palette=CAST)
    # light, tuned down from cs.body_light so its hip pool stays inside the cell
    glow_line(fr.L, g["feet"], g["head"], 7, 0.1)
    glow_line(fr.L, g["feet"], g["head"], 22, 0.07 * (0.5 + ch))
    glow(fr.L, *g["head"], 6, 0.12)
    for pts in g["hair"]:
        for a_, b_ in zip(pts, pts[1:]):
            glow_line(fr.L, a_, b_, 4, 0.06)
    glow(fr.L, *g["hip"], 46, 0.1 * (0.4 + 0.6 * ch), flat=0.8)
    # the fingertip: a strong flare once it points down, pulsing, brightest on the flare and the impact
    point = (0.55 + 0.45 * ease_io((f - DESC) / (PRISON - DESC))) * ease_io((f - FLY - 8) / 10) \
        * (1 - 0.6 * ease_io((f - FADE - 12) / 20))
    if point <= 0:
        return
    flare = math.exp(-max(f - PRISON, 0) / 6) * (f >= PRISON) + 0.5 * (DESC + EMERGE_N + HOLD_N <= f < PRISON)
    pulse = 0.5 + 0.5 * math.sin(f * 0.5)
    fx_, fy_ = g["finger"]
    glow(fr.L, fx_, fy_, 6, (0.6 + 0.1 * pulse + 0.4 * flare) * point)
    glow(fr.L, fx_, fy_, 18, (0.27 + 0.05 * pulse + 0.15 * flare) * point)
    glow(fr.L, fx_, fy_, 40, (0.08 + 0.12 * flare) * point)
    arm = int(round((2 + pulse + 4 * flare) * point))
    xs = [round(fx_)] * (2 * arm + 1) + list(range(round(fx_) - arm, round(fx_) + arm + 1))
    ys = list(range(round(fy_) - arm, round(fy_) + arm + 1)) + [round(fy_)] * (2 * arm + 1)
    fr.over(ys, xs, hexf(RIM), 0.8 * point)
    fr.over([round(fy_)], [round(fx_)], hexf(CORE), point)


# ---------------------------------------------------------------- frame
def render(f):
    fr = Frame()
    fr.fmask = None
    o, hole_in, hr = hole(f)
    draw_clouds(fr, f, hole_in, hr, o)
    L0 = fr.L.copy()
    draw_rift(fr, f, hole_in, hr, o)
    rift_L, fr.L = fr.L - L0, L0
    draw_ground(fr, f)
    draw_ring(fr, f, front=False)
    draw_crater(fr, f, front=False)
    draw_slam(fr, f)
    draw_finger(fr, f, hole_in, o, layer_front=False)
    if fr.fmask is not None:                     # the finger stands in front of the rim and the cracks
        rift_L = rift_L * (1 - 0.92 * fr.fmask)
    fr.L += rift_L
    draw_ring(fr, f, front=True)
    draw_crater(fr, f, front=True)
    draw_fragments(fr, f)
    draw_dust(fr, f)
    draw_flash(fr, f)
    draw_caster(fr, f)
    peak = math.exp(-max(f - PRISON, 0) / 8) if f >= PRISON else 0.0
    k = (0.05 * gather(f) + 0.18 * ease_io((f - DESC - 6) / 24)) * (1 - 0.6 * ease_io((f - FADE - 10) / 25))
    glow(fr.L, CX, 170, 200, k, flat=0.75)
    glow(fr.L, 150, 218, 150, 0.9 * k * ease_io((f - PRISON + 6) / 8), flat=0.8)
    glow(fr.L, FX, GY - 40, 120, 0.4 * peak, flat=0.6)
    col = (np.clip(fr.col, 0, 1) * 255).round().astype(np.uint8)
    return col, fr.L


def main():
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    cols, lights, finals, Ls = [], [], [], []
    cover, mean, bad = [], [], []
    for f in range(N):
        col, L = render(f)
        Lc = np.clip(L, 0, 1)
        lrgb = pfx.tint(np.repeat(Lc[..., None], 3, -1), LIGHT_RAMP)
        cols.append(col)
        lights.append(lrgb)
        Ls.append(L)
        finals.append(pfx.composite(col, lrgb))
        a = col[..., 3] > 0
        if not a.any():
            bad.append(f"frame {f}: empty colour")
            continue
        edge_c = a[0].any() or a[-1].any() or a[:, 0].any() or a[:, -1].any()
        edge_l = (L[0] > 0.02).any() or (L[-1] > 0.02).any() or (L[:, 0] > 0.02).any() or (L[:, -1] > 0.02).any()
        if edge_c or edge_l:
            bad.append(f"frame {f}: touches the edge ({'colour' if edge_c else 'light'})")
        ys, xs = np.nonzero(a)
        box = Lc[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        cover.append((box > 0.03).mean())
        mean.append(box[box > 0.03].mean() if (box > 0.03).any() else 0)

    def sheet(frames, path, cols_n=15):
        rows = math.ceil(len(frames) / cols_n)
        img = np.zeros((rows * H, cols_n * W, frames[0].shape[-1]), np.uint8)
        for i, fr_ in enumerate(frames):
            r, c = divmod(i, cols_n)
            img[r * H:(r + 1) * H, c * W:(c + 1) * W] = fr_
        Image.fromarray(img).save(path)

    sheet(finals, out / f"{NAME}.png")
    sheet(cols, out / f"{NAME}_color.png")
    sheet([(np.clip(lr, 0, 1) * 255).round().astype(np.uint8) for lr in lights], out / f"{NAME}_light.png")
    pfx.strip(finals, out / f"{NAME}_1x.png")
    keys = [4, 14, 26, 66, 82, 92, 100, 108, 112, 117, 118, 119, 120, 121, 130, 154, 178, 194]
    for bg, tag in (("#101018", "dark"), ("#5a5a66", "mid")):
        frames4 = []
        for k in keys:
            im = pfx.composite(cols[k], lights[k], bg)
            frames4.append(np.asarray(Image.fromarray(im).resize((W * 4, H * 4), Image.NEAREST)))
        rows = [np.concatenate(frames4[i:i + 6], 1) for i in range(0, len(frames4), 6)]
        Image.fromarray(np.concatenate(rows, 0)).save(out / f"{NAME}_4x_{tag}.png")
    pfx.gif(finals, out / f"{NAME}.gif", FPS, scale=4)
    pfx.gif(finals, out / f"{NAME}_2x.gif", FPS, scale=2)
    meta = dict(name=NAME, w=W, h=H, frames=N, cols=15, rows=math.ceil(N / 15), fps=FPS, loop=False,
                pivot=[FX, GY], glow=GLOW, light_gain=1.0, light_sheet=f"{NAME}_light.png",
                color_sheet=f"{NAME}_color.png", states=STATES)
    (out / f"{NAME}.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"light cover {np.median(cover):.0%}  mean {np.median(mean):.3f}  (strong: 75 to 95 %, 0.12 to 0.18)")
    for state, (a, b) in STATES.items():
        print(f"  {state:8s} cover {np.median(cover[a:b + 1]):.0%} mean {np.median(mean[a:b + 1]):.3f}")
    if bad:
        print("\n".join(bad[:20]), f"\n{len(bad)} bad frames")
        sys.exit(1)
    print(f"ok: {N} frames")


if __name__ == "__main__":
    main()
