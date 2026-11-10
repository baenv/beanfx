"""star_dragon_strike: a martial artist channels cosmic blue and gold embers round the hands, a dragon head of
burning stardust forms in front of the palms, roars with constellations pulsing inside, then shoots forward at
hyper-speed with a tail of cosmic dust and sparks, and bursts in a slow-motion impact at the far side.

General mode, soft style, glow strong. 400x200, 60 fps, 144 frames (2.4 s), one-shot.
The states below are in timeline frames; the sheet samples every SPEED-th one (SPEED 2 plays it twice as fast).

| state   | frames  | seconds   | what moves                                                   | carrier        |
|---------|---------|-----------|--------------------------------------------------------------|----------------|
| channel | 0-71    | 0.0-1.2   | embers spiral round the hands, tightening and speeding up    | caster, embers |
| summon  | 72-143  | 1.2-2.4   | embers and a stardust stream pour into a dragon head         | dust, head     |
| roar    | 144-179 | 2.4-3.0   | jaws open, stars pulse, head pulls back 10 px (anticipation)  | head           |
| launch  | 180-209 | 3.0-3.5   | head accelerates to the far side, dust tail and sparks       | head, tail     |
| impact  | 210-287 | 3.5-4.8   | white flash, rings, shards in slow motion, tail dissolves    | flash, dust    |

Colour: blue plasma body (6 tones), gold mane, horns and whiskers (6 tones). Light: two smooth additive maps, blue
and gold, tinted and summed. Research: Chinese dragon head parts (antler horns, long snout, whiskers, flame
mane); comet tails (a straight blue ion tail and a broad curved straw-yellow dust tail).
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "kit"))
import caster as cs  # noqa: E402
import pfx  # noqa: E402

NAME = "star_dragon_strike"
W, H, FPS = 400, 200, 60

CHANNEL, CHANNEL_N = 0, 72
SUMMON, SUMMON_N = CHANNEL + CHANNEL_N, 72
ROAR, ROAR_N = SUMMON + SUMMON_N, 36
LAUNCH, LAUNCH_N = ROAR + ROAR_N, 30
IMPACT, IMPACT_N = LAUNCH + LAUNCH_N, 78
N = IMPACT + IMPACT_N
SPEED = 2                                # timeline frames per sheet frame
STATES = {"channel": [CHANNEL, SUMMON - 1], "summon": [SUMMON, ROAR - 1], "roar": [ROAR, LAUNCH - 1],
          "launch": [LAUNCH, IMPACT - 1], "impact": [IMPACT, N - 1]}

FOOT, SC = (70.0, 168.0), 0.5            # caster about 39 px tall, the dragon head about 72 px long
C0 = (140.0, 112.0)                      # where the head forms
HIT_X, HIT_Y = 300.0, 110.0              # head centre at the end of the launch
IP = (328.0, 110.0)                      # impact point (the snout tip)

BL = ["#0c1240", "#1c2f86", "#2d62d6", "#5fa6ff", "#b8e4ff", "#ffffff"]   # plasma, deep to white-hot
GL = ["#3d1a05", "#8f4a0a", "#d98f1a", "#ffcf48", "#fff1b0", "#ffffff"]   # gold, deep to white-hot
RAMP_B = ["#0a1460", "#2a6cff", "#9fd4ff", "#ffffff"]
RAMP_G = ["#3a1400", "#ff8a1a", "#ffd98a", "#ffffff"]


def hexf(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


BLF = np.stack([hexf(c) for c in BL])
GLF = np.stack([hexf(c) for c in GL])
XX, YY = np.meshgrid(np.arange(W, dtype=float), np.arange(H, dtype=float))
rng = np.random.default_rng(7)
LAT = rng.random((256, 256))


def vn(x, y):
    """Smooth value noise 0..1."""
    xi, yi = np.floor(x), np.floor(y)
    fx, fy = x - xi, y - yi
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    xi, yi = xi.astype(int) & 255, yi.astype(int) & 255
    x1, y1 = (xi + 1) & 255, (yi + 1) & 255
    a = LAT[yi, xi] * (1 - fx) + LAT[yi, x1] * fx
    b = LAT[y1, xi] * (1 - fx) + LAT[y1, x1] * fx
    return a * (1 - fy) + b * fy


def ease(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def clamp01(t):
    return min(max(t, 0.0), 1.0)


# ---------------------------------------------------------------- frame buffer
class Frame:
    def __init__(self):
        self.P = np.zeros((H, W, 3))
        self.A = np.zeros((H, W))
        self.Lb = np.zeros((H, W))
        self.Lg = np.zeros((H, W))

    def over(self, ys, xs, rgb, a):
        ys, xs = np.asarray(ys).astype(int).ravel(), np.asarray(xs).astype(int).ravel()
        a = np.broadcast_to(np.asarray(a, float), ys.shape).copy() if np.ndim(a) else np.full(ys.shape, float(a))
        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W)
        ys, xs, a = ys[ok], xs[ok], a[ok]
        rgb = np.asarray(rgb, float)
        rgb = rgb[ok] if rgb.ndim == 2 else np.broadcast_to(rgb, (len(ys), 3))
        self.P[ys, xs] = self.P[ys, xs] * (1 - a[:, None]) + rgb * a[:, None]
        self.A[ys, xs] = self.A[ys, xs] * (1 - a) + a

    def dot(self, x, y, rgb, a):
        self.over([round(y)], [round(x)], rgb, a)

    def line(self, p0, p1, rgb, a):
        n = int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))) + 1
        t = np.linspace(0, 1, n + 1)
        xs = np.round(p0[0] + (p1[0] - p0[0]) * t)
        ys = np.round(p0[1] + (p1[1] - p0[1]) * t)
        pts = np.unique(np.stack([ys, xs], 1), axis=0)
        self.over(pts[:, 0], pts[:, 1], rgb, a)

    def color(self):
        a = np.clip(self.A, 0, 1)
        rgb = self.P / np.maximum(a, 1e-6)[..., None]
        return (np.concatenate([np.clip(rgb, 0, 1), a[..., None]], -1) * 255).round().astype(np.uint8)


# ---------------------------------------------------------------- caster
def caster_pose(f):
    target = (IP[0], IP[1] - 6)
    aim = cs.aim_from(FOOT, SC, target)
    if f < LAUNCH:
        jab = -4 * ease((f - ROAR) / (ROAR_N * 0.6)) if f >= ROAR else 0.0
    else:
        jab = -4 + 11 * ease((f - LAUNCH) / 6) - 3 * ease((f - LAUNCH - 10) / 40)
    front = [(0, "chest"), (34, "chest"), (56, "pull"), (SUMMON + 4, "point")]
    back = [(0, "rest"), (40, "out")]
    return cs.pose_at(f, front, back, aim, jab), jab


def hand_at(f):
    pose, _ = caster_pose(f)
    hx, hy = pose[0][1]
    return FOOT[0] + hx * SC, FOOT[1] + hy * SC


# ---------------------------------------------------------------- dragon head pose
def head_pose(f):
    """(cx, cy, ang, su, sv, jaw, vis, pulse): vis is the reveal (summon) or the remaining body (impact)."""
    pulse = 0.5 + 0.5 * math.sin(f * 0.3)
    if f < SUMMON:
        return C0[0], C0[1] + 3, -0.06, 0.8, 0.8, 0.05, 0.0, pulse
    if f < ROAR:
        t = (f - SUMMON) / SUMMON_N
        e = float(ease(t))
        s = 0.8 + 0.2 * e
        return C0[0], C0[1] + 3 * (1 - e), -0.06 + 0.03 * math.sin(f * 0.08), s, s, 0.05, 1.25 * e, pulse
    if f < LAUNCH:
        t = (f - ROAR) / ROAR_N
        pull = float(ease(t / 0.6))
        jaw = float(ease(t / 0.35))
        s = 1 + 0.06 * pull
        pulse = 0.5 + 0.5 * math.sin(t * math.tau * 3)
        return C0[0] - 10 * pull, C0[1] - 3 * pull, -0.06 - 0.2 * pull, s, s, jaw, 1.25, pulse
    if f < IMPACT:
        t = (f - LAUNCH + 1) / LAUNCH_N
        p = t ** 2.4
        speed = 2.4 * t ** 1.4
        x0, y0 = C0[0] - 10, C0[1] - 3
        ang = -0.26 * (1 - float(ease(t / 0.25)))
        s = 1.06 - 0.06 * t
        return (x0 + (HIT_X - x0) * p, y0 + (HIT_Y - y0) * p, ang, s * (1 + 0.12 * speed), s * (1 - 0.05 * speed),
                1 - 0.4 * t, 1.25, 1.0)
    t = (f - IMPACT) / IMPACT_N
    k = clamp01(t / 0.3)
    s = 1 + 0.25 * k
    return HIT_X + 10 * (1 - (1 - k) ** 2), HIT_Y, 0.0, s, s, 0.6, 1.25 * (1 - k * 1.1), 1.0


def to_world(f, u, v):
    cx, cy, ang, su, sv, *_ = head_pose(f)
    c, s = math.cos(ang), math.sin(ang)
    x, y = u * su, v * sv
    return cx + x * c - y * s, cy + x * s + y * c


NECK = (-10.0, 4.0)
STARS = [(-8, -3), (-1, -6), (7, -2), (14, -4), (22, -3), (3, 5), (-5, 4)]
STAR_LINKS = [(0, 1), (1, 2), (2, 3), (3, 4), (2, 5), (5, 6)]


def segd(u, v, a, b):
    ex, ey = b[0] - a[0], b[1] - a[1]
    h = np.clip(((u - a[0]) * ex + (v - a[1]) * ey) / (ex * ex + ey * ey or 1e-9), 0, 1)
    return np.hypot(u - a[0] - ex * h, v - a[1] - ey * h)


def ell(u, v, cx, cy, rx, ry):
    return 1 - np.hypot((u - cx) / rx, (v - cy) / ry)


def chain(u, v, pts, r0, r1):
    F = np.full(u.shape, -9.0)
    n = len(pts) - 1
    for k in range(n):
        r = r0 + (r1 - r0) * k / max(n - 1, 1)
        F = np.maximum(F, 1 - segd(u, v, pts[k], pts[k + 1]) / r)
    return F


def rot(u, v, ang, piv):
    c, s = math.cos(ang), math.sin(ang)
    du, dv = u - piv[0], v - piv[1]
    return piv[0] + du * c + dv * s, piv[1] - du * s + dv * c


def wave_pts(root, a, length, n, f, j, amp):
    pts, (x, y) = [root], root
    for k in range(n):
        an = a + amp * math.sin(k * 0.9 - f * 0.22 + j * 1.3) * (k + 1) / n
        x, y = x + math.cos(an) * length / n, y + math.sin(an) * length / n
        pts.append((x, y))
    return pts


def horn_pts(dx, dy):
    return [(-5 + dx, -10 + dy), (-14 + dx, -17 + dy), (-25 + dx, -21 + dy), (-34 + dx, -19 + dy)]


def draw_head(fr, f):
    cx, cy, ang, su, sv, jaw, vis, pulse = head_pose(f)
    if vis <= 0:
        return None
    R = 62 * max(su, sv)
    x0, x1 = int(max(cx - R, 0)), int(min(cx + R, W - 1))
    y0, y1 = int(max(cy - R, 0)), int(min(cy + R, H - 1))
    X, Y = XX[y0:y1 + 1, x0:x1 + 1], YY[y0:y1 + 1, x0:x1 + 1]
    c, s = math.cos(ang), math.sin(ang)
    dx, dy = X - cx, Y - cy
    u = (dx * c + dy * s) / su
    v = (-dx * s + dy * c) / sv
    burn = 0.2 * (vn(u * 0.4 + f * 0.15, v * 0.4) - 0.5)
    ua, va = rot(u, v, -0.22 * jaw, (2, 1))
    ul, vl = rot(u, v, 0.42 * jaw, (2, 2))
    parts = []   # painter's order: (field, material)
    parts.append((chain(u, v, horn_pts(3, -2), 2.2, 1.0) + burn, "gold_back"))
    parts.append((chain(u, v, [(-21, -20), (-23, -27), (-21, -31)], 1.6, 0.9) + burn, "gold_back"))
    for j in range(6):
        root = (-8 - j * 1.0, -8 + j * 3.4)
        a = math.pi - 0.38 + j * 0.15
        pts = wave_pts(root, a, 20 + (j * 7) % 9, 5, f, j, 0.3)
        parts.append((chain(u, v, pts, 3.6, 0.7) + burn * 1.5, "gold"))
    parts.append((ell(ul, vl, 5, 5, 7, 5), "blue"))
    parts.append((chain(ul, vl, [(4, 4), (16, 5), (25, 4)], 3.6, 2.6), "blue"))
    mouth = (va > 2) & (vl < 1.2) & (u > 4) & (ua < 26) & (ul < 24) & (jaw > 0.15)
    parts.append((np.where(mouth, np.clip(1 - (u - 4) / 24, 0.05, 1), -1.0), "hot"))
    parts.append((np.maximum.reduce([ell(u, v, 0, 0, 15, 11), ell(u, v, 9, -7, 9, 5)]) + burn, "blue"))
    parts.append((np.maximum.reduce([chain(ua, va, [(6, -3.5), (20, -2.5)], 6, 5), chain(ua, va, [(20, -3), (29, -1)], 4, 4),
                                     ell(ua, va, 28, -5, 4, 3.5)]) + burn * 0.5, "blue"))
    for j in range(3):
        pts = wave_pts((-1, 4 + j * 2.5), math.pi * 0.78 - j * 0.12, 11 + j * 2, 4, f, j + 6, 0.2)
        parts.append((chain(u, v, pts, 2.2, 0.6) + burn, "gold"))
    if jaw <= 0.15:
        parts.append((np.where((np.abs(va - 2.6) < 0.6) & (ua > 9) & (ua < 26), 0.05, -1.0), "seam"))
    parts.append((np.where((np.abs(v - (-8.6 + 0.02 * (u - 10) ** 2)) < 0.6) & (u > 5) & (u < 15), 0.05, -1.0),
                  "seam"))
    if jaw > 0.15:
        for fu in (17, 23):
            parts.append((1 - segd(ua, va, (fu, 1), (fu, 4)) / 1.0, "white"))
        parts.append((1 - segd(ul, vl, (20, 3), (20, 0)) / 1.0, "white"))
    parts.append((chain(u, v, horn_pts(0, 0), 2.6, 1.1) + burn, "gold"))
    parts.append((chain(u, v, [(-16, -17), (-18, -26), (-15, -31)], 1.8, 0.9) + burn, "gold"))
    parts.append((ell(u, v, 10, -6, 2.6, 1.7), "white"))

    shape = u.shape
    tone = np.full(shape, -1)
    mat = np.zeros(shape, int)            # 0 blue, 1 gold, 2 white
    for F, m in parts:
        inside = F > 0
        if not inside.any():
            continue
        t = np.where(F < 0.12, 1, np.where(F < 0.35, 2, np.where(F < 0.62, 3, 4)))
        if m == "gold_back":
            t, mm = np.maximum(t - 1, 0), 1
        elif m == "gold":
            mm = 1
        elif m == "hot":
            t, mm = np.where(F > 0.45, 5, np.where(F > 0.2, 4, 3)), 0
        elif m == "seam":
            t, mm = np.full(shape, 0), 0
        elif m == "white":
            t, mm = np.full(shape, 5), 2
        else:
            mm = 0
        tone = np.where(inside, t, tone)
        mat = np.where(inside, mm, mat)
    m = tone >= 0
    ul_ = np.zeros_like(m)
    ul_[1:, 1:] = m[:-1, :-1]
    dr_ = np.zeros_like(m)
    dr_[:-1, :-1] = m[1:, 1:]
    tone = np.where(m & ~ul_ & (tone < 5), np.minimum(tone + 1, 4), tone)
    tone = np.where(m & ~dr_ & ul_ & (tone < 5), np.maximum(tone - 1, 0), tone)
    # reveal from scattered stardust (summon) or burst into dust (impact)
    thr = 0.55 * vn(u * 0.25 + 20, v * 0.25 + 40) + 0.45 * vn(u * 1.7 + 50, v * 1.7 + 80)
    m &= thr < vis
    ys, xs = np.nonzero(m)
    tt, mt = tone[ys, xs], mat[ys, xs]
    rgb = np.where((mt == 1)[:, None], GLF[np.clip(tt, 0, 5)], BLF[np.clip(tt, 0, 5)])
    rgb = np.where((mt == 2)[:, None], 1.0, rgb)
    a = np.where(tt <= 1, 0.82, 1.0) * np.clip((vis - thr[ys, xs]) * 6, 0.35, 1)
    fr.over(ys + y0, xs + x0, rgb, a)

    # constellation inside the body
    k = min(vis, 1.0)
    wp = [to_world(f, *p) for p in STARS]
    for i, j in STAR_LINKS:
        fr.line(wp[i], wp[j], hexf("#cfeaff"), 0.45 * k)
    for i, p in enumerate(wp):
        b = 0.55 + 0.45 * math.sin(f * 0.35 + i * 1.9) if f < ROAR or f >= LAUNCH else pulse
        fr.dot(*p, 1.0, (0.6 + 0.4 * b) * k)
        if i in (2, 4, 0):
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                fr.dot(p[0] + ox, p[1] + oy, hexf("#b8e4ff"), 0.55 * b * k)
        cs.glow(fr.Lb, *p, 4, 0.22 * b * k)

    # whiskers, 1 px gold, waving back
    lip = to_world(f, 27, 0)
    for wpts in ([(27, 0), (18, 10), (6, 17), (-10, 21), (-24, 17)], [(24, -7), (30, -14), (26, -22), (14, -27)]):
        sw = [to_world(f, x + 2 * math.sin(f * 0.15 + q), y + 2 * math.cos(f * 0.12 + q))
              for q, (x, y) in enumerate(wpts)]
        sw[0] = to_world(f, *wpts[0])
        for a_, b_ in zip(sw, sw[1:]):
            fr.line(a_, b_, GLF[4], 0.85 * k)
            cs.glow_line(fr.Lg, a_, b_, 3, 0.08 * k)

    # head light: core and pool on the skull, eye, mouth, mane, horns
    hc = to_world(f, 4, -1)
    cs.glow(fr.Lb, *hc, 16 * su, 0.42 * k)
    cs.glow(fr.Lb, *hc, 48 * su, 0.19 * k)
    cs.glow(fr.Lg, *to_world(f, 10, -6), 5, 0.55 * k)
    if jaw > 0.1:
        cs.glow(fr.Lb, *to_world(f, 17, 1), 11, (0.35 + 0.25 * pulse) * jaw * k)
    cs.glow(fr.Lg, *to_world(f, -20, 0), 18, 0.2 * k)
    hp = [to_world(f, *p) for p in horn_pts(0, 0)]
    for a_, b_ in zip(hp, hp[1:]):
        cs.glow_line(fr.Lg, a_, b_, 4, 0.12 * k)
    return lip


# ---------------------------------------------------------------- body and tail spine
def pre_curve(f, n=40):
    nx, ny = to_world(f, *NECK)
    hx, hy = hand_at(f)
    s = np.linspace(0, 1, n)
    bx, by = nx + (hx - nx) * s, ny + (hy - ny) * s
    dx, dy = hx - nx, hy - ny
    L = math.hypot(dx, dy) or 1
    px, py = -dy / L, dx / L
    off = 13 * np.sin(np.pi * s) * np.sin(math.tau * s * 1.1 + f * 0.08)
    return np.stack([bx + px * off, by + py * off + 8 * np.sin(np.pi * s)], 1)


TL = 24


def spine(f, n=48):
    """Tail centreline from the neck backwards, (n, 2), and the tail state."""
    if f < LAUNCH:
        return pre_curve(f, n)
    g = min(f, IMPACT - 1)
    pc = pre_curve(LAUNCH - 1, 60)
    out = []
    for s in np.linspace(0, 1, n):
        t = g - s * TL
        if t >= LAUNCH - 1:
            tf = math.floor(t)
            a, b = np.array(to_world(tf, *NECK)), np.array(to_world(min(tf + 1, g), *NECK))
            out.append(a + (b - a) * (t - tf))
        else:
            q = min((LAUNCH - 1 - t) / 14, 1) * 59
            i = int(q)
            out.append(pc[i] + (pc[min(i + 1, 59)] - pc[i]) * (q - i))
    return np.array(out)


def tail_radius(t, f):
    base = 7.0 if f < LAUNCH else 6.0
    return base * (1 - t) ** 0.7 + 0.7


def spine_at(sp, s):
    q = np.clip(s, 0, 1) * (len(sp) - 1)
    i = np.minimum(q.astype(int), len(sp) - 2)
    w = (q - i)[:, None]
    p = sp[i] * (1 - w) + sp[i + 1] * w
    d = sp[i + 1] - sp[i]
    d /= np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-6)[:, None]
    return p, np.stack([-d[:, 1], d[:, 0]], 1)


def body_amount(f):
    if f < SUMMON:
        return 0.0
    if f < ROAR:
        return float(ease((f - SUMMON) / SUMMON_N * 1.2))
    if f < IMPACT:
        return 1.0
    return 1 - clamp01((f - IMPACT) / (IMPACT_N * 0.45))


def draw_tail(fr, f):
    amt = body_amount(f)
    if amt <= 0:
        return
    sp = spine(f)
    x0, x1 = int(max(sp[:, 0].min() - 22, 0)), int(min(sp[:, 0].max() + 22, W - 1))
    y0, y1 = int(max(sp[:, 1].min() - 22, 0)), int(min(sp[:, 1].max() + 22, H - 1))
    X, Y = XX[y0:y1 + 1, x0:x1 + 1], YY[y0:y1 + 1, x0:x1 + 1]
    D = np.full(X.shape, 1e9)
    T = np.zeros(X.shape)
    n = len(sp) - 1
    for k in range(n):
        a, b = sp[k], sp[k + 1]
        ex, ey = b - a
        h = np.clip(((X - a[0]) * ex + (Y - a[1]) * ey) / (ex * ex + ey * ey or 1e-9), 0, 1)
        d = np.hypot(X - a[0] - ex * h, Y - a[1] - ey * h)
        closer = d < D
        D = np.where(closer, d, D)
        T = np.where(closer, (k + h) / n, T)
    r = tail_radius(T, f)
    q = 1 - D / r
    brk = vn(X * 0.3 + f * 0.4, Y * 0.3) < 0.15 + 0.7 * T ** 1.5 + (1 - amt) * 0.9
    reach = T <= amt * 1.05 if f < ROAR else np.ones_like(T, bool)
    m = (q > 0) & ~brk & reach & (T > 0.04)
    tone = np.where(q < 0.3, 1, np.where(q < 0.6, 2, np.where(q < 0.85, 3, 4)))
    tone = np.where(D < 0.8, 5, tone)
    ys, xs = np.nonzero(m)
    tt = tone[ys, xs]
    a = (0.5 + 0.1 * tt) * (1 - 0.55 * T[ys, xs]) * min(amt * 1.3, 1)
    fr.over(ys + y0, xs + x0, BLF[tt], a)
    # light: core and a pool along the tail, from the distance map (no doubled joints)
    Ls = fr.Lb[y0:y1 + 1, x0:x1 + 1]
    fade = (1 - T) * amt * (T > 0.02)
    Ls += np.where(D < 5, (1 - D / 5) ** 2, 0) * 0.32 * fade
    Ls += np.where(D < 15, (1 - D / 15) ** 2, 0) * 0.14 * fade
    Ls += np.where(D < 24, (1 - D / 24) ** 2, 0) * 0.08 * fade
    # constellation along the body
    ss = np.array([0.14, 0.27, 0.4, 0.55])
    p, nrm = spine_at(sp, ss)
    p = p + nrm * np.array([2, -3, 2, -1])[:, None]
    vis = (ss <= amt) if f < ROAR else (np.ones(4, bool) * (amt > 0.3))
    for i in range(4):
        if vis[i]:
            if i < 3 and vis[i + 1]:
                fr.line(p[i], p[i + 1], hexf("#cfeaff"), 0.35 * amt)
            fr.dot(*p[i], 1.0, 0.9 * amt)
            cs.glow(fr.Lb, *p[i], 4, 0.2 * amt)


# ---------------------------------------------------------------- particles
def drag_pos(p0, v, age, dg):
    return p0 + v * (1 - dg ** age) / (1 - dg)


# embers round the hands
NE = 110
E_TH = rng.uniform(0, math.tau, NE)
E_W = rng.uniform(0.07, 0.15, NE)
E_R = rng.uniform(24, 40, NE)
E_B = rng.uniform(0, 36, NE)
E_GOLD = rng.random(NE) < 0.5
E_ABS = rng.uniform(SUMMON, SUMMON + 56, NE)
E_TGT = [STARS[i % len(STARS)] for i in range(NE)]
E_OFF = rng.normal(0, 1, (NE, 2))


def ember_pos(j, f, hand):
    tt = min(f, SUMMON + 60)
    th = E_TH[j] + E_W[j] * tt * (1 + tt / CHANNEL_N * 0.9)
    R = E_R[j] * (1 - 0.6 * float(ease(min(f, SUMMON) / CHANNEL_N)))
    x = hand[0] + R * math.cos(th)
    y = hand[1] + R * 0.42 * math.sin(th) + 2 * math.sin(th * 0.5 + j)
    return x, y, math.sin(th)


def draw_embers(fr, f, front):
    for j in range(NE):
        if f < E_B[j]:
            continue
        fade_in = clamp01((f - E_B[j]) / 10)
        ab = E_ABS[j]
        if f > ab + 14:
            continue
        pts = []
        for back in (0, SPEED, 2 * SPEED, 3 * SPEED):
            g = f - back
            if g < E_B[j]:
                break
            hx, hy = hand_at(g)
            x, y, depth = ember_pos(j, g, (hx, hy))
            if g > ab:
                k = float(ease((g - ab) / 14))
                tx, ty = to_world(g, *E_TGT[j])
                tx, ty = tx + E_OFF[j, 0] * 3, ty + E_OFF[j, 1] * 3
                x, y = x + (tx - x) * k, y + (ty - y) * k
                depth = 1
            pts.append((x, y, depth))
        if not pts or (pts[0][2] > 0) != front:
            continue
        pal = GLF if E_GOLD[j] else BLF
        for i, (x, y, _) in enumerate(pts):
            fr.dot(x, y, pal[4 - i] if i < 3 else pal[2], (1 - i * 0.25) * fade_in * (0.6 + 0.4 * (pts[0][2] > 0)))
        x, y, _ = pts[0]
        cs.glow(fr.Lg if E_GOLD[j] else fr.Lb, x, y, 4, 0.22 * fade_in)


# stardust along the body and tail
ND = 320
D_S = rng.random(ND) ** 0.85
D_O = np.clip(rng.normal(0, 1, ND), -2.2, 2.2)
D_GOLD = rng.random(ND) < 0.5
D_TONE = rng.integers(2, 6, ND)
D_V = rng.normal(0, 1, (ND, 2)) * 0.25 + np.array([-0.05, -0.08])
D_LIFE = rng.uniform(30, 120, ND)
D_GLINT = rng.random(ND) < 0.12


def dust_positions(f):
    sp = spine(f)
    if f < LAUNCH:
        s = (D_S - f * 0.012) % 1.0
    else:
        s = D_S
    p, nrm = spine_at(sp, s)
    spread = tail_radius(s, f) * 1.2 + (12 if f >= LAUNCH else 5) * s
    off = D_O * spread
    pos = p + nrm * off[:, None]
    pos[:, 1] += np.where(D_GOLD, 9 * s ** 2, 0) if f >= LAUNCH else 0
    return pos, s


def draw_dust(fr, f):
    if f < SUMMON:
        return
    if f < IMPACT:
        pos, s = dust_positions(f)
        amt = body_amount(f)
        alpha = np.where(s <= amt * 1.05, 1.0, 0.0) if f < ROAR else np.ones(ND)
        alpha = alpha * (1 - 0.4 * s)
    else:
        pos, s = dust_positions(IMPACT - 1)
        age = f - IMPACT + 1
        pos = pos + D_V * age
        alpha = np.clip(1 - age / D_LIFE, 0, 1) * (1 - 0.4 * s)
    tw = 0.6 + 0.4 * np.sin(f * 0.4 + np.arange(ND) * 2.1)
    for j in range(ND):
        a = alpha[j] * tw[j]
        if a <= 0.02:
            continue
        pal = GLF if D_GOLD[j] else BLF
        x, y = pos[j]
        fr.dot(x, y, pal[D_TONE[j]], a)
        L = fr.Lg if D_GOLD[j] else fr.Lb
        if D_GLINT[j]:
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                fr.dot(x + ox, y + oy, pal[3], 0.5 * a)
            cs.glow(L, x, y, 5, 0.28 * a)
        else:
            cs.glow(L, x, y, 3, 0.1 * a)


def make_bursts():
    """Sparks shed by the head (mane burning off, then the launch trail) and the impact shards."""
    out = []
    for b in range(SUMMON + 40, IMPACT):
        n = 2 if b < LAUNCH else 6
        for _ in range(n):
            if b < LAUNCH:
                lu, lv = rng.uniform(-30, -12), rng.uniform(-12, 12)
                v = np.array([rng.uniform(-0.8, -0.3), rng.uniform(-0.3, 0.05)])
                life, dg = rng.uniform(14, 30), 0.95
            else:
                lu, lv = rng.uniform(-22, 18), rng.uniform(-14, 14)
                v = np.array([rng.uniform(-1.0, -0.15), rng.uniform(-0.6, 0.6)])
                life, dg = rng.uniform(22, 70), 0.93
            out.append(dict(b=b, local=(lu, lv), v=v, life=life, dg=dg, gold=rng.random() < 0.55,
                            glint=rng.random() < 0.15))
    for _ in range(90):
        a = rng.uniform(0, math.tau)
        sp = rng.uniform(0.4, 1.9)
        out.append(dict(b=IMPACT, p0=np.array(IP) + rng.normal(0, 2, 2), v=np.array([math.cos(a), math.sin(a)]) * sp,
                        life=rng.uniform(40, 115), dg=0.965, gold=rng.random() < 0.5, glint=rng.random() < 0.2))
    return out


BURSTS = make_bursts()


def draw_sparks(fr, f):
    for sp in BURSTS:
        age = f - sp["b"]
        if age < 0 or age > sp["life"]:
            continue
        if "p0" not in sp:
            sp["p0"] = np.array(to_world(sp["b"], *sp["local"]))
        p = drag_pos(sp["p0"], sp["v"], age, sp["dg"])
        q = drag_pos(sp["p0"], sp["v"], max(age - 2 * SPEED, 0), sp["dg"])
        k = 1 - age / sp["life"]
        pal = GLF if sp["gold"] else BLF
        fr.line(q, p, pal[3], 0.45 * k)
        fr.dot(*p, pal[5] if k > 0.6 else pal[4], min(1, 0.4 + k))
        L = fr.Lg if sp["gold"] else fr.Lb
        if sp["glint"]:
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                fr.dot(p[0] + ox, p[1] + oy, pal[4], 0.6 * k)
            cs.glow(L, *p, 6, 0.3 * k)
        else:
            cs.glow(L, *p, 4, 0.2 * k)


RAYS = [(rng.uniform(0, math.tau), rng.uniform(18, 42)) for _ in range(11)]


def draw_impact(fr, f):
    age = f - IMPACT
    if age < 0:
        return
    t = age / IMPACT_N
    # flash disc: 2 white-hot frames, then shrinks
    if age < 6:
        r = 11 - age * 1.5
        m = np.hypot(XX - IP[0], YY - IP[1]) <= r
        ys, xs = np.nonzero(m)
        fr.over(ys, xs, 1.0, 1.0 if age < 2 else 0.8)
    flash = math.exp(-age / 9)
    cs.glow(fr.Lb, *IP, 20, 0.7 * flash)
    cs.glow(fr.Lg, *IP, 30, 0.35 * flash)
    # tapered rays
    if age < 16:
        k = 1 - age / 16
        for a, ln in RAYS:
            l0 = 4 + age * 1.2
            l1 = l0 + ln * k
            c, s = math.cos(a), math.sin(a)
            fr.line((IP[0] + c * l0, IP[1] + s * l0), (IP[0] + c * l1, IP[1] + s * l1), BLF[4], 0.8 * k)
            fr.line((IP[0] + c * l0, IP[1] + s * l0), (IP[0] + c * (l0 + (l1 - l0) * 0.4),
                                                      IP[1] + s * (l0 + (l1 - l0) * 0.4)), 1.0, k)
            cs.glow_line(fr.Lb, (IP[0] + c * l0, IP[1] + s * l0), (IP[0] + c * l1, IP[1] + s * l1), 4, 0.18 * k)
    # two rings in slow motion: blue fast, gold slow
    for R1, dur, pal, L, flat in ((46, 50, BLF, fr.Lb, 0.85), (30, 70, GLF, fr.Lg, 1.0)):
        if age < dur:
            e = 1 - (1 - age / dur) ** 2.5
            R = 6 + (R1 - 6) * e
            k = 1 - age / dur
            cs.ellipse_line(fr.over, IP[0], IP[1], R, R * flat, "#%02x%02x%02x" % tuple((pal[4] * 255).astype(int)),
                            0.85 * k, phase=age * 0.1, dash=7 if R1 == 30 else None)
            cs.glow_ring(L, IP[0], IP[1], R, 4, 0.28 * k, flat=flat)
    # lingering core ember
    if t > 0.05:
        k = 1 - t
        fr.dot(*IP, BLF[4], 0.8 * k)
        cs.glow(fr.Lb, *IP, 8, 0.25 * k)


# ---------------------------------------------------------------- scene pool and caster light
def scene_pool(fr, f):
    hx, hy = hand_at(f)
    if f < SUMMON:
        c, k = (hx + 10, hy - 8), 0.12 + 0.08 * float(ease(f / CHANNEL_N))
    elif f < ROAR:
        e = float(ease((f - SUMMON) / SUMMON_N))
        hc = to_world(f, 0, 0)
        c, k = (hx + (hc[0] - hx) * (0.4 + 0.5 * e), hy + (hc[1] - hy) * (0.4 + 0.5 * e)), 0.2
    elif f < IMPACT:
        c = to_world(f, 0, 0)
        k = 0.2 + (0.15 * head_pose(f)[7] if f < LAUNCH else 0.05)
    else:
        c, k = IP, 0.2 + 0.4 * math.exp(-(f - IMPACT) / 14)
    cx, cy = min(max(c[0], 122), W - 122), min(max(c[1], 68), H - 68)
    cs.glow(fr.Lb, cx, cy, 120, k * 0.65, flat=0.55)
    cs.glow(fr.Lg, cx, cy, 120, k * 0.35, flat=0.55)


def caster_light(fr, g, f):
    charge = float(ease(f / CHANNEL_N)) if f < LAUNCH else 1 - 0.5 * clamp01((f - LAUNCH) / 60)
    cs.glow_line(fr.Lg, g["feet"], g["head"], 7, 0.06 + 0.03 * charge)
    cs.glow_line(fr.Lg, g["feet"], g["head"], 18, 0.04)
    cs.glow(fr.Lg, *g["head"], 5, 0.08)
    hx, hy = hand_at(f)
    cs.glow(fr.Lb, hx, hy, 6, 0.3 + 0.25 * charge)
    cs.glow(fr.Lb, hx, hy, 18, 0.1 + 0.12 * charge)
    cs.glow(fr.Lg, hx, hy, 12, 0.12 * charge)
    cs.glow(fr.Lb, hx + 6, hy - 10, 60, 0.1 + 0.06 * charge, flat=0.8)


# ---------------------------------------------------------------- frames
def render(f):
    fr = Frame()
    pose, jab = caster_pose(f)
    speed = 0.0 if f < LAUNCH else max(0.0, 1 - (f - LAUNCH) / 40)
    lift = 0.35 + 0.35 * float(ease(f / (SUMMON + 20))) + 0.3 * speed
    flut = 0.4 + 0.3 * float(ease(f / CHANNEL_N)) + 0.3 * speed
    draw_embers(fr, f, front=False)
    g = cs.draw(fr.over, (H, W), FOOT, SC, pose, f * 0.5, lift, flut, hair="loose")
    caster_light(fr, g, f)
    draw_tail(fr, f)
    draw_dust(fr, f)
    draw_head(fr, f)
    draw_sparks(fr, f)
    draw_embers(fr, f, front=True)
    draw_impact(fr, f)
    scene_pool(fr, f)
    return fr


def light_rgb(Lb, Lg):
    b = pfx.tint(np.repeat(np.clip(Lb, 0, 1)[..., None], 3, -1), RAMP_B)
    g = pfx.tint(np.repeat(np.clip(Lg, 0, 1)[..., None], 3, -1), RAMP_G)
    return np.clip(b + g, 0, 1)


def grid(frames, cols):
    rows = math.ceil(len(frames) / cols)
    h, w = frames[0].shape[:2]
    out = np.zeros((rows * h, cols * w, 4), np.uint8)
    for i, im in enumerate(frames):
        r, c = divmod(i, cols)
        out[r * h:(r + 1) * h, c * w:(c + 1) * w] = im
    return out


def main():
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    finals, lights, bad, covers, means = [], [], [], [], []
    for f in range(0, N, SPEED):
        fr = render(f)
        col = fr.color()
        L = fr.Lb + fr.Lg
        lr = light_rgb(fr.Lb, fr.Lg)
        finals.append(pfx.composite(col, lr))
        lights.append((np.concatenate([lr, lr.max(-1, keepdims=True)], -1) * 255).round().astype(np.uint8))
        edge = np.concatenate([col[0, :, 3], col[-1, :, 3], col[:, 0, 3], col[:, -1, 3]]) > 5
        ledge = np.concatenate([L[0], L[-1], L[:, 0], L[:, -1]]) > 0.02
        if edge.any() or ledge.any() or not (col[..., 3] > 0).any():
            bad.append(f)
        ys, xs = np.nonzero(col[..., 3])
        if len(ys):
            box = np.clip(L[ys.min():ys.max() + 1, xs.min():xs.max() + 1], 0, 1)
            covers.append((box > 0.03).mean())
            means.append(box[box > 0.03].mean() if (box > 0.03).any() else 0)

    pfx.strip(finals, out / f"{NAME}.png")
    Image.fromarray(grid(finals, 12), "RGBA").save(out / f"{NAME}_sheet.png")
    Image.fromarray(grid(lights, 12), "RGBA").save(out / f"{NAME}_light_sheet.png")
    keys = list(range(0, len(finals), 8)) + [IMPACT // SPEED]
    keys = sorted(set(keys))
    for tag, bg in (("dark", "#101018"), ("mid", "#4a4e60")):
        ims = [pfx.composite(finals[i], np.zeros((H, W, 3)), bg) for i in keys]
        big = [np.asarray(Image.fromarray(im).resize((W * 4, H * 4), Image.NEAREST)) for im in ims]
        pfx.strip(big, out / f"{NAME}_keys_4x_{tag}.png")
    pfx.gif(finals, out / f"{NAME}.gif", FPS, scale=4)
    states = {k: [a // SPEED, b // SPEED] for k, (a, b) in STATES.items()}
    meta = dict(name=NAME, w=W, h=H, frames=len(finals), fps=FPS, cols=12, rows=math.ceil(len(finals) / 12), pivot=[FOOT[0], FOOT[1]],
                loop=False, glow="strong", light_gain=1.0, states=states,
                sheet=f"{NAME}_sheet.png", light_sheet=f"{NAME}_light_sheet.png")
    import json
    (out / f"{NAME}.json").write_text(json.dumps(meta, indent=2))
    print(f"frames {len(finals)} at {FPS} fps ({len(finals) / FPS:.1f} s), states {states}")
    print(f"light cover median {np.median(covers):.2f}, mean median {np.median(means):.3f} (strong: 0.75-0.95, 0.12-0.18)")
    if bad:
        print(f"FAIL edge or empty frames: {bad[:20]}{' ...' if len(bad) > 20 else ''} ({len(bad)})")
        sys.exit(1)
    print("edge check ok")


if __name__ == "__main__":
    main()
