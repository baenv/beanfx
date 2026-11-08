"""Ten Thousand Souls Banner: a caster lifts a black soul banner, it unfurls in black mist, wailing ghost faces crawl out and
circle it, fill the sky, spiral into an orb above the banner, then pour from it at the target as one twisting stream,
burst in green will-o'-wisp fire, circle there, then fly home into the cloth. General mode, 320x320, 30 fps, one-shot,
glow medium, soft style, a small pale-green caster bottom left.

State table (30 fps, 204 frames, 6.8 s)
  state     frames    s    what moves                                                       carrier
  summon     0..29   1.0   caster raises the pole, black mist wells up, the cloth unrolls     banner, mist
  scatter   30..83   1.8   24 skulls pour out of the cloth and spread across the sky, drifting souls
  converge  84..113  1.0   they spiral in to an orb above the banner, which tightens; pole back souls, orb
  strike   114..161  1.6   the banner swings, the orb pours at the target as a twisting rope  souls, wisp fire
  return   162..203  1.4   souls circle the target, then arc back into the cloth; it droops   souls, mist
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
from fxlib import noise, stroke  # noqa: E402

NAME = "van_hon_phien"
W = H = 320
FPS = 30
SUMMON, SUMMON_N = 0, 30
SCATTER = SUMMON + SUMMON_N
SCATTER_N = 54
CONVERGE = SCATTER + SCATTER_N
CONVERGE_N = 30
STRIKE = CONVERGE + CONVERGE_N
STRIKE_N = 48
RETURN = STRIKE + STRIKE_N
RETURN_N = 42
N = RETURN + RETURN_N
STATES = {"summon": [SUMMON, SCATTER - 1], "scatter": [SCATTER, CONVERGE - 1], "converge": [CONVERGE, STRIKE - 1],
          "strike": [STRIKE, RETURN - 1], "return": [RETURN, N - 1]}

FOOT = (96, 262)
SC = 0.44
TGT = (258, 230)
SOULS = 24
TRAVEL = 15
BACK = 18
GLOW = "medium"

CLOTH = ["#07060b", "#120e1a", "#1e1729", "#2e2440", "#40325a"]
TRIM = "#1f5a44"
SOUL = ["#0c3226", "#1c6a4a", "#3aae78", "#8cf0b6", "#e6fff2"]
FACE = "#04120c"
MIST = ["#07050b", "#120d19", "#1f1729", "#30253e", "#2a4a42"]
WOOD = ["#1a120c", "#3a2818", "#5e4228"]
CAST = ["#12201c", "#2a4a3e", "#568a74", "#a4d8c2", "#eefff8"]
LIGHT_RAMP = ["#06301e", "#1fae64", "#a8ffd0", "#ffffff"]


def hexf(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


CLOTH_F = np.stack([hexf(c) for c in CLOTH])
SOUL_F = np.stack([hexf(c) for c in SOUL])
MIST_F = np.stack([hexf(c) for c in MIST])
YY, XX = np.mgrid[0:H, 0:W].astype(float)


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


def lerp2(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


# ---------------------------------------------------------------- canvas and light
class Frame:
    def __init__(self):
        self.col = np.zeros((H, W, 4))
        self.L = np.zeros((H, W))

    def over(self, ys, xs, rgb, a):
        ys = np.asarray(ys).astype(int).ravel()
        xs = np.asarray(xs).astype(int).ravel()
        rgb = np.asarray(rgb, float)
        rgb = np.broadcast_to(rgb, (len(ys), 3)) if rgb.ndim == 1 else rgb.reshape(-1, 3)
        a = np.broadcast_to(np.asarray(a, float), ys.shape).astype(float)
        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W) & (a > 0)
        ys, xs, rgb, a = ys[ok], xs[ok], rgb[ok], a[ok]
        ca = self.col[ys, xs, 3]
        na = a + ca * (1 - a)
        self.col[ys, xs, :3] = (rgb * a[:, None] + self.col[ys, xs, :3] * (ca * (1 - a))[:, None]) \
            / np.maximum(na, 1e-6)[:, None]
        self.col[ys, xs, 3] = na


def win(x, y, rx, ry):
    return (slice(int(max(0, y - ry)), int(min(H, y + ry + 2))), slice(int(max(0, x - rx)), int(min(W, x + rx + 2))))


def glow(L, x, y, r, k, flat=1.0):
    if k <= 0:
        return
    sy, sx = win(x, y, r, r * flat)
    if sy.start >= sy.stop or sx.start >= sx.stop:
        return
    d = np.hypot(XX[sy, sx] - x, (YY[sy, sx] - y) / flat) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def glow_line(L, p0, p1, r, k):
    if k <= 0:
        return
    (ax, ay), (bx, by) = p0, p1
    sy = slice(int(max(0, min(ay, by) - r)), int(min(H, max(ay, by) + r + 2)))
    sx = slice(int(max(0, min(ax, bx) - r)), int(min(W, max(ax, bx) + r + 2)))
    if sy.start >= sy.stop or sx.start >= sx.stop:
        return
    X, Y = XX[sy, sx], YY[sy, sx]
    ex, ey = bx - ax, by - ay
    h = np.clip(((X - ax) * ex + (Y - ay) * ey) / (ex * ex + ey * ey or 1e-9), 0, 1)
    d = np.hypot(X - ax - ex * h, Y - ay - ey * h) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def disc(fr, x, y, r, rgb, a):
    sy, sx = win(x, y, r + 1, r + 1)
    d = np.hypot(XX[sy, sx] - x, YY[sy, sx] - y)
    ys, xs = np.nonzero(d <= r)
    fr.over(ys + sy.start, xs + sx.start, rgb, a)


def ring_px(fr, x, y, r, rgb, a, flat=1.0):
    n = max(int(r * 8), 12)
    th = np.linspace(0, math.tau, n, endpoint=False)
    fr.over(np.round(y + r * flat * np.sin(th)), np.round(x + r * np.cos(th)), rgb, a)


# ---------------------------------------------------------------- the banner
def pole_angle(f):
    """0 upright, < 0 tilted back (left), > 0 swung toward the target."""
    a = 0.05 * math.sin(f * 0.12)
    a -= 0.35 * ease_io((f - CONVERGE - 20) / 10)
    a += 0.9 * ease_out((f - STRIKE) / 5)
    a -= 0.62 * ease_io((f - STRIKE - 10) / 22)
    a -= 0.2 * ease_io((f - RETURN - 8) / 20)
    return a


def unfurl(f):
    return 0.08 + 0.92 * ease_out((f - 6) / 20)


def activity(f):
    """How hard the cloth ripples and the runes burn."""
    return clamp(0.3 + 0.7 * ease_io((f - 6) / 20) - 0.5 * ease_io((f - RETURN - 14) / 16)
                 + 0.4 * math.exp(-max(f - STRIKE, 0) / 10) * (f >= STRIKE))


def pose(f):
    aim = cs.aim_from(FOOT, SC, TGT)
    jab = 3 * math.exp(-max(f - STRIKE, 0) / 5) if f >= STRIKE else 0.0
    return cs.pose_at(f, [(0, "chest"), (10, "raise"), (CONVERGE + 20, "raise"), (CONVERGE + 28, "pull"),
                          (STRIKE + 3, "point"), (STRIKE + 34, "point"), (RETURN + 20, "raise"), (N, "raise")],
                      [(0, "rest"), (10, "out"), (CONVERGE + 28, "behind"), (RETURN + 20, "out")], aim, jab)


def hand(f):
    (fe, fh), _ = pose(f)
    return (FOOT[0] + fh[0] * SC, FOOT[1] + fh[1] * SC)


def pole(f):
    """Butt, top, unit up vector d and unit across vector p."""
    a = pole_angle(f)
    d = (math.sin(a), -math.cos(a))
    p = (math.cos(a), math.sin(a))
    hx, hy = hand(f)
    return (hx - d[0] * 22, hy - d[1] * 22), (hx + d[0] * 88, hy + d[1] * 88), d, p


def cloth_point(u, w, f):
    """Cloth point at u across (-1..1) and w down (0 at the crossbar, 1 at the hem, past 1 in the tails)."""
    _, top, d, p = pole(f)
    da = (pole_angle(f + 0.5) - pole_angle(f - 0.5))
    act = activity(f)
    wind = -0.25 - 2.4 * da - 0.12 * act * math.sin(f * 0.13)
    hx, hy = wind, 1.0
    n = math.hypot(hx, hy)
    hx, hy = hx / n, hy / n
    length = 74 * unfurl(f)
    u = np.asarray(u, float)
    w = np.asarray(w, float)
    bx = top[0] - d[0] * 5 + p[0] * u * 15 * (1 - 0.12 * w)
    by = top[1] - d[1] * 5 + p[1] * u * 15 * (1 - 0.12 * w)
    rip = (1.5 + 3.6 * act) * w * np.sin(w * 5.5 - f * 0.34 + u * 0.9)
    return bx + hx * w * length - hy * rip, by + hy * w * length + hx * rip, np.cos(w * 5.5 - f * 0.34 + u * 0.9)


def glyph(seed):
    pts = [(x, y) for y in (-1, 0, 1) for x in (-1, 0, 1)]
    segs = [((0, -1), (0, 1))]
    r = np.random.default_rng(seed)
    while len(segs) < 3 + seed % 2:
        a, b = pts[r.integers(9)], pts[r.integers(9)]
        if a != b and math.hypot(b[0] - a[0], b[1] - a[1]) <= 1.5 and (a, b) not in segs:
            segs.append((a, b))
    return segs


RUNES = [(w, glyph(i + 11)) for i, w in enumerate((0.2, 0.4, 0.6, 0.8))]
UG, WG = np.meshgrid(np.linspace(-1, 1, 90), np.linspace(0, 1.3, 360))


def tail_keep(u, w):
    band = ((u + 1) / 2 * 3) % 1
    length = 1 + 0.26 * (1 - np.abs(band - 0.5) * 2) ** 0.7
    return (w <= 1) | ((band > 0.12) & (band < 0.88) & (w <= length))


KEEP = tail_keep(UG, WG)


def rune_glow(f):
    return clamp(0.2 + 0.8 * ease_io((f - 8) / 22)) * (0.75 + 0.25 * math.sin(f * 0.4)) \
        * (1 - 0.5 * ease_io((f - RETURN - 10) / 20)) + 0.5 * math.exp(-max(f - STRIKE, 0) / 6) * (f >= STRIKE)


def draw_banner(fr, f):
    butt, top, d, p = pole(f)
    # pole: 2 px dark wood with a lit left edge, a crossbar, a small finial with a green glint
    for k, off in enumerate((-0.5, 0.5)):
        q = pixels([(butt[0] + p[0] * off, butt[1] + p[1] * off), (top[0] + p[0] * off, top[1] + p[1] * off)])
        fr.over(q[:, 0], q[:, 1], hexf(WOOD[2 if k == 0 else 1]), 1.0)
    for off, tn in ((0, 1), (1, 0)):
        cb = pixels([(top[0] - d[0] * (5 - off) - p[0] * 17, top[1] - d[1] * (5 - off) - p[1] * 17),
                     (top[0] - d[0] * (5 - off) + p[0] * 17, top[1] - d[1] * (5 - off) + p[1] * 17)])
        fr.over(cb[:, 0], cb[:, 1], hexf(WOOD[tn]), 1.0)
    for s in (-17, 17):
        disc(fr, top[0] - d[0] * 5 + p[0] * s, top[1] - d[1] * 5 + p[1] * s, 1.6, hexf(WOOD[2]), 1.0)
    disc(fr, top[0] + d[0] * 2, top[1] + d[1] * 2, 2.4, hexf(WOOD[0]), 1.0)
    fr.over([round(top[1] + d[1] * 2)], [round(top[0] + d[0] * 2)], hexf(SOUL[3]), 1.0)
    glow(fr.L, top[0] + d[0] * 2, top[1] + d[1] * 2, 6, 0.3 * activity(f))
    # cloth: splat a dense (u, w) grid, then outline it
    uf = unfurl(f)
    keep = KEEP & (WG <= 1.3)
    if uf < 0.2:
        keep &= WG <= 1
    xs, ys, sl = cloth_point(UG[keep], WG[keep], f)
    u, w = UG[keep], WG[keep]
    tone = np.clip(np.round(2 + 1.2 * sl - 0.6 * w).astype(int), 0, 4)
    tone = np.where(np.abs(u) > 0.84, 5, tone)                            # green-black trim
    xi, yi = np.round(xs).astype(int), np.round(ys).astype(int)
    m = np.full((H, W), -1, int)
    ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
    order = np.argsort(w[ok])
    m[yi[ok][order], xi[ok][order]] = tone[ok][order]
    # runes in cloth space
    rg = rune_glow(f)
    if uf > 0.6:
        for wr, segs in RUNES:
            for (ax, ay), (bx, by) in segs:
                for t in np.linspace(0, 1, 14):
                    uu, ww = (ax + (bx - ax) * t) * 0.26, wr + (ay + (by - ay) * t) * 0.05
                    x, y, _ = cloth_point(uu, ww, f)
                    xx, yy = int(round(float(x))), int(round(float(y)))
                    if 0 <= xx < W and 0 <= yy < H and m[yy, xx] >= 0:
                        m[yy, xx] = 6
            x, y, _ = cloth_point(0.0, wr, f)
            glow(fr.L, float(x), float(y), 5, 0.4 * rg)
            glow(fr.L, float(x), float(y), 13, 0.16 * rg)
    inside = m >= 0
    er = inside.copy()
    er[1:-1, 1:-1] = inside[1:-1, 1:-1] & inside[:-2, 1:-1] & inside[2:, 1:-1] & inside[1:-1, :-2] & inside[1:-1, 2:]
    edge = inside & ~er & (m != 6)
    pal = np.concatenate([CLOTH_F, hexf(TRIM)[None], (hexf(SOUL[3]) * min(rg, 1) + CLOTH_F[1] * (1 - min(rg, 1)))[None]])
    m = np.where(edge, 0, m)
    yy, xx = np.nonzero(inside)
    fr.over(yy, xx, pal[m[yy, xx]], 1.0)
    return top


def banner_centre(f):
    x, y, _ = cloth_point(0.0, 0.5, f)
    return float(x), float(y)


# ---------------------------------------------------------------- souls
SOUL_P = []
for i in range(SOULS):
    SOUL_P.append(dict(
        u=(hsh(i, 1) - 0.5) * 1.2, w=0.25 + 0.6 * hsh(i, 2),
        sx=40 + 240 * ((i * 0.618 + 0.1 * hsh(i, 3)) % 1), sy=36 + 104 * hsh(i, 4),
        wa=0.05 + 0.04 * hsh(i, 5), wb=hsh(i, 6) * math.tau,
        sc=0.85 + 0.4 * hsh(i, 7), emerge=SCATTER + i * 0.9,
        theta=math.acos(1 - 2 * (i + 0.5) / SOULS), phi=i * 2.39996,      # a point on the orb (golden spiral)
        conv=CONVERGE + i * 0.15, launch=STRIKE + 2 + i * 1.0,
        tR=16 + 14 * hsh(i, 8), tph=hsh(i, 9) * math.tau, home=RETURN + 1 + i * 0.8,
        twist=hsh(i, 10) * math.tau))
ORB = (118, 92)
ORB_R = 30


def orb_r(f):
    """The orb tightens just before the strike."""
    return ORB_R * (1 - 0.25 * ease_io((f - CONVERGE - 20) / 10)) * (1 + 0.15 * ease_out((f - STRIKE) / 4))


def wander(s, f):
    return (s["sx"] + 9 * math.sin(f * s["wa"] + s["wb"]), s["sy"] + 6 * math.cos(f * s["wa"] * 1.3 + s["wb"]))


def on_orb(s, f):
    phi = s["phi"] + 0.09 * (f - CONVERGE)
    r = orb_r(f)
    x = r * math.sin(s["theta"]) * math.cos(phi)
    z = r * math.sin(s["theta"]) * math.sin(phi)
    y = r * math.cos(s["theta"]) * 0.85
    return (ORB[0] + x, ORB[1] + y), z / max(r, 1e-6)


def stream(s, t, f):
    """Position on the rope from the orb to the target at t (0..1), twisted round its axis."""
    a = ORB
    ctl = (0.5 * (a[0] + TGT[0]) + 30, min(a[1], TGT[1]) - 20)
    x = (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * ctl[0] + t * t * TGT[0]
    y = (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * ctl[1] + t * t * TGT[1]
    dx = 2 * (1 - t) * (ctl[0] - a[0]) + 2 * t * (TGT[0] - ctl[0])
    dy = 2 * (1 - t) * (ctl[1] - a[1]) + 2 * t * (TGT[1] - ctl[1])
    n = math.hypot(dx, dy) or 1
    ang = s["twist"] + t * 4 * math.pi + f * 0.25
    r = 12 * math.sin(math.pi * t)
    return (x - dy / n * r * math.cos(ang), y + dx / n * r * math.cos(ang)), math.sin(ang)


def target_orbit(s, f):
    th = s["tph"] + 0.2 * f
    return (TGT[0] + s["tR"] * math.cos(th), TGT[1] - 4 + s["tR"] * 0.5 * math.sin(th)), math.sin(th)


def soul_at(i, f):
    """(x, y), depth (-1 back, 1 front), scale and alpha; None when the soul is not out."""
    s = SOUL_P[i]
    if f < s["emerge"]:
        return None
    hit = s["launch"] + TRAVEL
    if f < s["conv"]:                                     # out of the cloth and up across the sky
        t = (f - s["emerge"]) / 28
        x, y, _ = cloth_point(s["u"], s["w"], f)
        x, y = float(x), float(y)
        wx, wy = wander(s, f)
        k = ease_out(t)
        ctl = ((x + wx) / 2 - 20 * math.cos(s["wb"]), min(y, wy) - 30)
        px = (1 - k) ** 2 * x + 2 * (1 - k) * k * ctl[0] + k * k * wx
        py = (1 - k) ** 2 * y + 2 * (1 - k) * k * ctl[1] + k * k * wy
        return (px, py), 0.5, s["sc"] * (0.35 + 0.65 * ease_out(t * 1.4)), ease_out(t * 2)
    if f < s["launch"]:                                   # spiral in from the sky onto the orb
        t = (f - s["conv"]) / 26
        (ox, oy), dep = on_orb(s, f)
        if t >= 1:
            return (ox, oy), dep, s["sc"] * (0.85 + 0.15 * (dep + 1) / 2), 1.0
        wx, wy = wander(s, s["conv"])
        k = ease_io(t)
        ang = k * 1.4                                # turn more as it closes in: a spiral, no jump
        dx, dy = wx - ORB[0], wy - ORB[1]
        rx = dx * math.cos(ang) - dy * math.sin(ang)
        ry = dx * math.sin(ang) + dy * math.cos(ang)
        px, py = ORB[0] + rx * (1 - k), ORB[1] + ry * (1 - k)
        return (px + (ox - ORB[0]) * k, py + (oy - ORB[1]) * k), dep * k + 0.5 * (1 - k), s["sc"], 1.0
    if f < hit:
        t = (f - s["launch"]) / TRAVEL
        tt = t ** 1.3
        (px, py), dep = stream(s, tt, f)
        if t < 0.25:
            (ox, oy), _ = on_orb(s, s["launch"])
            k = ease_io(t / 0.25)
            px, py = ox + (px - ox) * k, oy + (py - oy) * k
        return (px, py), dep, s["sc"], 1.0
    if f < s["home"]:
        u = clamp((f - hit) / 6)
        (tx, ty), dep = target_orbit(s, f)
        return (TGT[0] + (tx - TGT[0]) * u, TGT[1] + (ty - TGT[1]) * u), dep, s["sc"] * (0.85 + 0.15 * u), 0.9
    t = (f - s["home"]) / BACK
    if t >= 1:
        return None
    (ox, oy), _ = target_orbit(s, s["home"])
    x, y, _ = cloth_point(s["u"], s["w"], f)
    ctl = ((ox + float(x)) / 2 + 10, min(oy, float(y)) - 60 - 30 * hsh(i, 12))
    k = ease_io(t)
    px = (1 - k) ** 2 * ox + 2 * (1 - k) * k * ctl[0] + k * k * float(x)
    py = (1 - k) ** 2 * oy + 2 * (1 - k) * k * ctl[1] + k * k * float(y)
    return (px, py), 0.5, s["sc"] * (1 - 0.6 * ease_in(t)), 1 - ease_in(t)


def draw_orb(fr, f):
    """A dark translucent core behind the souls while they hold the orb, lit green from inside."""
    k = ease_io((f - CONVERGE - 8) / 16) * (1 - ease_io((f - STRIKE - 4) / 18))
    if k <= 0.01:
        return
    r = orb_r(f) * 0.8
    sy, sx = win(ORB[0], ORB[1], r + 2, r + 2)
    dx, dy = XX[sy, sx] - ORB[0], YY[sy, sx] - ORB[1]
    d = np.hypot(dx, dy / 0.9)
    sw = noise(np.arctan2(dy, dx) * 8 + f * 0.3, d * 0.4 - f * 0.2, 3, 81)
    m = d < r * (0.92 + 0.12 * sw)
    ys, xs = np.nonzero(m)
    dd = d[ys, xs] / r
    tone = np.where(dd > 0.85, 4, np.where(sw[ys, xs] > 0.55, 2, 1))
    fr.over(ys + sy.start, xs + sx.start, MIST_F[tone], 0.75 * k)
    glow(fr.L, ORB[0], ORB[1], 12, 0.4 * k)
    glow(fr.L, ORB[0], ORB[1], 40, 0.16 * k)


def draw_soul(fr, i, f, state):
    (x, y), dep, sc, al = state
    if al <= 0.02:
        return
    trail = [(x, y)]
    run = 0.0
    for k in range(1, 9):
        st = soul_at(i, f - k * 0.75)
        if st is None:
            break
        q = st[0]
        step = math.hypot(q[0] - trail[-1][0], q[1] - trail[-1][1])
        if run + step > 26 * sc:                       # a fast soul keeps a short tail, never a long chord
            rest = max(26 * sc - run, 0) / max(step, 1e-6)
            trail.append((trail[-1][0] + (q[0] - trail[-1][0]) * rest, trail[-1][1] + (q[1] - trail[-1][1]) * rest))
            break
        run += step
        trail.append(q)
    r = 6.0 * sc
    # tail: tapered stroke through the soul's recent path, waving
    if len(trail) >= 3:
        pts = np.array(trail, float)
        wav = np.sin(np.arange(len(pts)) * 1.3 - f * 0.6 + i) * np.linspace(0, 2.2, len(pts))
        seg = np.gradient(pts, axis=0)
        nrm = np.stack([-seg[:, 1], seg[:, 0]], 1) / np.maximum(np.hypot(seg[:, 0], seg[:, 1]), 1e-6)[:, None]
        pts = pts + nrm * wav[:, None]
        x0, y0 = pts.min(0) - 7
        x1, y1 = pts.max(0) + 7
        sy = slice(int(max(0, y0)), int(min(H, y1)))
        sx = slice(int(max(0, x0)), int(min(W, x1)))
        if sy.start < sy.stop and sx.start < sx.stop:
            d, t, _ = stroke(XX[sy, sx], YY[sy, sx], pts, r * 1.3, 0.4)
            m = d < 0
            ys, xs = np.nonzero(m)
            tt = t[ys, xs]
            tone = np.where(tt < 0.3, 3, np.where(tt < 0.65, 2, 1))
            tone = np.where(d[ys, xs] > -0.8, np.maximum(tone - 1, 0), tone)
            fr.over(ys + sy.start, xs + sx.start, SOUL_F[tone], al * 0.75 * (1 - tt) ** 0.7)
        glow_line(fr.L, trail[0], trail[min(4, len(trail) - 1)], 4, 0.07 * al)
    # skull: a cranium, a jaw that drops as it wails, big hollow eyes with a green spark, a nose hole, teeth
    wail = 0.5 + 0.5 * math.sin(f * 0.5 + i * 1.7)
    drop = 0.12 * r + 0.28 * r * wail
    sy, sx = win(x, y + 0.4 * r, r + 2, 1.3 * r + 2)
    dx, dy = XX[sy, sx] - x, YY[sy, sx] - y
    cran = np.hypot(dx, (dy + 0.1 * r) / 0.95) <= r * 0.92
    jy = 0.55 * r + drop
    jaw = (np.abs(dx) <= 0.55 * r) & (dy >= 0.45 * r + drop * 0.6) & (dy <= jy + 0.35 * r) \
        & (np.hypot(dx / (0.55 * r), (dy - jy) / (0.38 * r)) <= 1.25)
    cheek = (np.abs(dx) <= 0.62 * r) & (dy > 0.2 * r) & (dy < 0.55 * r)
    skull = cran | jaw | cheek
    er = skull.copy()
    er[1:-1, 1:-1] = skull[1:-1, 1:-1] & skull[:-2, 1:-1] & skull[2:, 1:-1] & skull[1:-1, :-2] & skull[1:-1, 2:]
    tone = np.where((dx + dy) < -0.55 * r, 4, np.where((dx + dy) > 0.6 * r, 2, 3))
    tone = np.where(skull & ~er, 0, tone)
    ys, xs = np.nonzero(skull)
    fr.over(ys + sy.start, xs + sx.start, SOUL_F[tone[ys, xs]], 0.97 * al)
    face = np.zeros(skull.shape, bool)
    er_ = max(0.3 * r, 1.0)
    for side in (-1, 1):
        face |= np.hypot((dx - side * 0.38 * r) / er_, (dy + 0.02 * r) / (er_ * 1.1)) <= 1
    face |= (np.abs(dx) <= max(0.12 * r, 0.5)) & (dy >= 0.25 * r) & (dy <= 0.42 * r)          # nose
    gap = (np.abs(dx) <= 0.48 * r) & (dy > 0.55 * r) & (dy < 0.45 * r + drop * 0.6 + 0.6)       # open mouth
    face |= gap
    ys, xs = np.nonzero(face & skull | gap)
    fr.over(ys + sy.start, xs + sx.start, hexf(FACE), al)
    teeth = jaw & (dy < 0.45 * r + drop * 0.6 + 1.6) & ~gap & ((np.floor(dx) % 2) == 0)
    ys, xs = np.nonzero(teeth)
    fr.over(ys + sy.start, xs + sx.start, SOUL_F[4], al)
    for side in (-1, 1):                                                                       # eye sparks
        ex_, ey_ = x + side * 0.38 * r, y + 0.05 * r
        fr.over([round(ey_)], [round(ex_)], SOUL_F[3], al)
        glow(fr.L, ex_, ey_, 3, 0.15 * al)
    glow(fr.L, x, y, 5 * sc, 0.22 * al)
    glow(fr.L, x, y, 14 * sc, 0.12 * al)


def pixels(pts):
    out = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        n = max(int(math.hypot(bx - ax, by - ay) * 2), 1)
        t = np.linspace(0, 1, n, endpoint=False)
        out.append(np.stack([ay + (by - ay) * t, ax + (bx - ax) * t], 1))
    p = np.round(np.concatenate(out + [np.array([[pts[-1][1], pts[-1][0]]])])).astype(int)
    return np.unique(p, axis=0)


# ---------------------------------------------------------------- mist
PUFFS = []
for i in range(34):                                       # wells up from the cloth as it unrolls
    PUFFS.append(dict(kind="cloth", t0=3 + i * 0.8, u=(hsh(i, 20) - 0.5) * 2, w=hsh(i, 21),
                      vx=-0.35 - 0.4 * hsh(i, 22), vy=-0.25 - 0.4 * hsh(i, 23), life=26 + 12 * hsh(i, 24),
                      r=4 + 4 * hsh(i, 25), back=hsh(i, 26) < 0.5))
for i in range(30):                                       # keeps pouring while the souls leave
    PUFFS.append(dict(kind="cloth", t0=SCATTER + i * 1.6, u=(hsh(i, 30) - 0.5) * 2, w=hsh(i, 31),
                      vx=(hsh(i, 32) - 0.6) * 0.8, vy=-0.3 - 0.3 * hsh(i, 33), life=24 + 10 * hsh(i, 34),
                      r=3 + 4 * hsh(i, 35), back=hsh(i, 36) < 0.6))
for i in range(SOULS):
    s_ = SOUL_P[i]
    for j, t0 in enumerate((s_["emerge"] + 8, s_["launch"] + 4, s_["launch"] + 10)):
        PUFFS.append(dict(kind="soul", soul=i, t0=t0, vx=(hsh(i * 3 + j, 40) - 0.5) * 0.5,
                          vy=-0.2 - 0.2 * hsh(i * 3 + j, 41), life=20 + 8 * hsh(i * 3 + j, 42),
                          r=3 + 3 * hsh(i * 3 + j, 43), back=j != 1))
    PUFFS.append(dict(kind="soul", soul=i, t0=s_["home"] + 6, vx=0.0, vy=-0.15, life=18,
                      r=3 + 2 * hsh(i, 44), back=False))


def puff_origin(p):
    if p["kind"] == "cloth":
        x, y, _ = cloth_point(p["u"], p["w"], p["t0"])
        return float(x), float(y)
    st = soul_at(p["soul"], p["t0"])
    return st[0] if st else None


ORIG = [puff_origin(p) for p in PUFFS]


def draw_mist(fr, f, back):
    for p, o in zip(PUFFS, ORIG):
        if o is None or p["back"] != back:
            continue
        t = f - p["t0"]
        if t < 0 or t > p["life"]:
            continue
        u = t / p["life"]
        # mist that is still out on the return is drawn home with the souls
        home = ease_in((f - RETURN - 6) / 30) if p["kind"] == "cloth" else 0.0
        bc = banner_centre(f)
        x = o[0] + p["vx"] * t + 3 * math.sin(t * 0.2 + p["r"])
        y = o[1] + p["vy"] * t
        x, y = x + (bc[0] - x) * home, y + (bc[1] - y) * home
        r = p["r"] * 1.6 * (0.5 + 0.8 * ease_out(u)) * (1 - 0.6 * home)
        a = 0.72 * math.sin(math.pi * min(u * 1.4, 1)) ** 0.8 * (1 - u) ** 0.5
        sy, sx = win(x, y, r + 1, r + 1)
        dx, dy = XX[sy, sx] - x, YY[sy, sx] - y
        dd = np.hypot(dx, dy)
        lob = r * (1 + 0.18 * noise(dx + p["r"] * 13, dy + t * 0.3, 3, 77))
        m = dd < lob
        ys, xs = np.nonzero(m)
        lit = (dx + dy)[ys, xs] / max(r, 1)
        tone = np.where(lit < -0.85, 4, np.where(lit < -0.4, 3, np.where(lit < 0.3, 2, 1)))
        fr.over(ys + sy.start, xs + sx.start, MIST_F[tone], a)


# ---------------------------------------------------------------- hits at the target
def draw_hits(fr, f):
    first = SOUL_P[0]["launch"] + TRAVEL
    heat = 0.0
    for i, s in enumerate(SOUL_P):
        h = s["launch"] + TRAVEL
        t = f - h
        heat += math.exp(-max(t, 0) / 8) * (t >= 0)
        if t < 0 or t > 12:
            continue
        r = 3 + 13 * ease_out(t / 9)
        a = 1 - t / 12
        ring_px(fr, TGT[0], TGT[1], r, hexf(SOUL[3]), 0.7 * a, flat=0.8)
        for k in range(4):
            ang = hsh(i * 5 + k, 50) * math.tau
            sp = 1.0 + 1.2 * hsh(i * 5 + k, 51)
            x = TGT[0] + math.cos(ang) * sp * t
            y = TGT[1] + math.sin(ang) * sp * t - 0.12 * t * t
            fr.over([round(y)], [round(x)], hexf(SOUL[4] if t < 5 else SOUL[2]), a)
            glow(fr.L, x, y, 3, 0.18 * a)
    # the head of the rope lands: a 2-frame white-green peak
    t = f - first
    if 0 <= t < 2:
        disc(fr, TGT[0], TGT[1], 11 - 3 * t, hexf(SOUL[4]), 1.0)
        disc(fr, TGT[0], TGT[1], 6 - 2 * t, hexf("#ffffff"), 1.0)
    if 0 <= t < 14:
        ring_px(fr, TGT[0], TGT[1], 12 + 30 * ease_out(t / 14), hexf(SOUL[3]), 0.8 * (1 - t / 14), flat=0.75)
    peak = math.exp(-max(t, 0) / 6) * (t >= 0)
    glow(fr.L, TGT[0], TGT[1], 14, 0.9 * peak)
    # will-o'-wisp fire on the target while the souls keep landing
    heat = clamp(heat / 3) * (1 - ease_io((f - RETURN - 6) / 16))
    if heat > 0.02:
        for j in range(6):
            bx = TGT[0] + (j - 2.5) * 5 + 2 * math.sin(f * 0.3 + j)
            hgt = (9 + 7 * hsh(j, 60)) * heat * (0.8 + 0.3 * math.sin(f * 0.7 + j * 2))
            if hgt < 2:
                continue
            pts = [(bx + 1.5 * math.sin(f * 0.5 + j + k), TGT[1] + 8 - hgt * k / 4) for k in range(5)]
            sy, sx = win(bx, TGT[1] + 8 - hgt / 2, 6, hgt / 2 + 4)
            d, tt, _ = stroke(XX[sy, sx], YY[sy, sx], pts, 4.5, 0.3)
            ys, xs = np.nonzero(d < 0)
            v = tt[ys, xs]
            tone = np.where(v < 0.25, 4, np.where(v < 0.6, 3, 2))
            fr.over(ys + sy.start, xs + sx.start, SOUL_F[tone], 0.9 * heat)
            glow(fr.L, bx, TGT[1] + 6, 6, 0.2 * heat)
        glow(fr.L, TGT[0], TGT[1] + 2, 40, 0.12 * heat + 0.3 * peak, flat=0.8)


# ---------------------------------------------------------------- caster
def draw_caster(fr, f):
    ch = activity(f)
    da = abs(pole_angle(f + 0.5) - pole_angle(f - 0.5))
    lift = min(1.0, 0.3 + 0.5 * ch + 3 * da)
    flut = min(1.0, 0.35 + 0.4 * ch + 3 * da)
    g = cs.draw(fr.over, (H, W), FOOT, SC, pose(f), f, lift, flut, hair="loose", palette=CAST)
    glow_line(fr.L, g["feet"], g["head"], 7, 0.06)
    glow_line(fr.L, g["feet"], g["head"], 18, 0.04 * (0.5 + ch))
    glow(fr.L, *g["head"], 5, 0.08)
    glow(fr.L, *g["hip"], 40, 0.06 * (0.4 + 0.6 * ch), flat=0.8)


# ---------------------------------------------------------------- frame
def render(f):
    fr = Frame()
    souls = [(i, soul_at(i, f)) for i in range(SOULS)]
    souls = [(i, s) for i, s in souls if s is not None]
    souls.sort(key=lambda q: q[1][1])
    draw_mist(fr, f, back=True)
    draw_orb(fr, f)
    for i, s in souls:
        if s[1] < 0:
            draw_soul(fr, i, f, s)
    draw_banner(fr, f)
    draw_caster(fr, f)
    draw_hits(fr, f)
    for i, s in souls:
        if s[1] >= 0:
            draw_soul(fr, i, f, s)
    draw_mist(fr, f, back=False)
    # scene pools: under the banner while it calls the souls, at the target on the strike
    bc = banner_centre(f)
    glow(fr.L, bc[0] + 12, bc[1] + 14, 92, (0.06 + 0.12 * activity(f)) * (1 - 0.4 * ease_io((f - STRIKE) / 12)), flat=0.9)
    sky = ease_io((f - SCATTER - 10) / 30) * (1 - ease_io((f - CONVERGE) / 24))
    glow(fr.L, 160, 96, 150, 0.15 * sky, flat=0.55)
    rope = ease_io((f - STRIKE - 2) / 10) * (1 - 0.5 * ease_io((f - RETURN + 4) / 26))
    glow(fr.L, (ORB[0] + TGT[0]) / 2 + 10, (ORB[1] + TGT[1]) / 2 - 4, 140, 0.18 * rope, flat=0.62)
    col = (np.clip(fr.col, 0, 1) * 255).round().astype(np.uint8)
    return col, fr.L


def main():
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    cols, lights, finals = [], [], []
    cover, mean, bad = [], [], []
    for f in range(N):
        col, L = render(f)
        Lc = np.clip(L, 0, 1)
        lrgb = pfx.tint(np.repeat(Lc[..., None], 3, -1), LIGHT_RAMP)
        cols.append(col)
        lights.append(lrgb)
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
    keys = [6, 22, 40, 56, 72, 86, 94, 104, 112, 118, 124, 132, 146, 160, 170, 180, 192, 203]
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
                pivot=list(FOOT), target=list(TGT), glow=GLOW, light_gain=1.0, light_sheet=f"{NAME}_light.png",
                color_sheet=f"{NAME}_color.png", states=STATES)
    (out / f"{NAME}.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"light cover {np.median(cover):.0%}  mean {np.median(mean):.3f}  (medium: 50 to 80 %, 0.08 to 0.12)")
    for state, (a, b) in STATES.items():
        print(f"  {state:7s} cover {np.median(cover[a:b + 1]):.0%} mean {np.median(mean[a:b + 1]):.3f}")
    if bad:
        print("\n".join(bad[:20]), f"\n{len(bad)} bad frames")
        sys.exit(1)
    print(f"ok: {N} frames")


if __name__ == "__main__":
    main()
