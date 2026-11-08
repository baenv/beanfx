"""Ten Thousand Swords v3: a golden caster with a avatar behind charges on the ground, rises inside a ring of
swords, the swords spiral slowly up into a tilted turning wheel, the caster points and sweeps, and the wheel pours a
slanted rain of swords onto the field. General mode, 640x480, 165 frames at 30 fps, one-shot, glow strong (gold).

States (frames): charge 0-21, swords appear and the caster rises 14-50, gather into the wheel 48-94, pull and
point 94-104, sword rain 104-134 (impacts to 142), dissolve and landing 140-164.
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

NAME = "van_kiem_quy_tong_v3"
W, H, N, FPS = 640, 480, 165, 30
GROUND = (206.0, 400.0)              # pivot: the caster's feet before the rise
HOVER = (236.0, 272.0)
C = (346.0, 134.0)                   # where the swords gather
T = (500.0, 396.0)                   # middle of the impact field
NS = 48
RAIN0, RAIN1 = 104, 134               # first and last launch of the rain
GATHER = 36.0                        # frames each sword takes to spiral into the wheel
FLY = 8.0
SC = 0.44                            # the caster's scale (about 34 px tall, shorter than a sword)
OUT = Path(__file__).parent / "out"

STEEL = ["#1c2240", "#4e5c82", "#9eabc4", "#dde6f2", "#ffffff"]   # 0 rim, 1 shadow, 2 mid, 3 lit, 4 edge
HILT = ["#5c2c0c", "#b0741c", "#f0c850"]                          # 5 dark, 6 mid, 7 lit
PAL = STEEL + HILT
BODY = cs.BODY                                                   # the golden figure, dark to hot
LIGHT_RAMP = ["#5a2a08", "#e0a020", "#ffe8a0", "#ffffff"]
SMOKE = ["#4a3c3c", "#7a6658", "#a8927a"]

YY, XX = np.mgrid[0:H, 0:W].astype(float)
rng = np.random.default_rng(11)


def hexf(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


PAL_RGB = np.stack([hexf(c) for c in PAL])


def ease_io(s):
    s = np.clip(s, 0, 1)
    return s * s * (3 - 2 * s)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def ang_lerp(a, b, t):
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + d * t


# ---- light (windowed falloffs, same curve as kit/light.py) ----
def _win(x0, x1, y0, y1):
    xa, xb = max(int(x0), 0), min(int(x1) + 2, W)
    ya, yb = max(int(y0), 0), min(int(y1) + 2, H)
    return slice(ya, max(yb, ya)), slice(xa, max(xb, xa))


def glow(L, x, y, r, k, flat=1.0):
    sy, sx = _win(x - r, x + r, y - r * flat, y + r * flat)
    d = np.hypot(XX[sy, sx] - x, (YY[sy, sx] - y) / flat) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def seg_d(X, Y, a, b):
    ex, ey = b[0] - a[0], b[1] - a[1]
    h = np.clip(((X - a[0]) * ex + (Y - a[1]) * ey) / (ex * ex + ey * ey or 1e-9), 0, 1)
    return np.hypot(X - a[0] - ex * h, Y - a[1] - ey * h)


def glow_line(L, p0, p1, r, k):
    sy, sx = _win(min(p0[0], p1[0]) - r, max(p0[0], p1[0]) + r, min(p0[1], p1[1]) - r, max(p0[1], p1[1]) + r)
    d = seg_d(XX[sy, sx], YY[sy, sx], p0, p1) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


def glow_ring(L, x, y, R, r, k, flat=1.0):
    sy, sx = _win(x - R - r, x + R + r, y - (R + r) * flat, y + (R + r) * flat)
    d = np.abs(np.hypot(XX[sy, sx] - x, (YY[sy, sx] - y) / flat) - R) / r
    L[sy, sx] += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)


# ---- colour ----
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

    def dot(self, x, y, col, a=1.0):
        self.over(np.array([int(round(y))]), np.array([int(round(x))]), hexf(col), a)

    def rgba(self):
        return np.dstack([self.rgb, self.a])


def ellipse_line(fr, cx, cy, rx, ry, col, a, phase=0.0, dash=None):
    n = max(int(2 * math.pi * max(rx, 1) * 1.6), 12)
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    if dash:
        th = th[np.sin(th * dash + phase) > -0.2]
    pts = np.unique(np.stack([np.round(cy + ry * np.sin(th)), np.round(cx + rx * np.cos(th))], 1).astype(int), axis=0)
    fr.over(pts[:, 0], pts[:, 1], hexf(col), a)


def line(fr, p0, p1, col0, col1, a0, a1):
    n = int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))) + 1
    t = np.linspace(0, 1, n)
    xs = np.round(p0[0] + (p1[0] - p0[0]) * t).astype(int)
    ys = np.round(p0[1] + (p1[1] - p0[1]) * t).astype(int)
    rgb = hexf(col0)[None] * (1 - t[:, None]) + hexf(col1)[None] * t[:, None]
    fr.over(ys, xs, rgb, a0 + (a1 - a0) * t)


def puff(fr, x, y, r, a):
    sy, sx = _win(x - r, x + r, y - r, y + r)
    X, Y = XX[sy, sx], YY[sy, sx]
    m = np.hypot(X - x, Y - y) <= r
    s = (X - x) + (Y - y)
    tone = np.where(s < -r * 0.3, 2, np.where(s > r * 0.5, 0, 1))
    ys, xs = np.nonzero(m)
    fr.over(ys + sy.start, xs + sx.start, np.stack([hexf(c) for c in SMOKE])[tone[ys, xs]], a)


# ---- sword: a sharp jian, 47 px from tip to pommel ----
BL = 32.0


def sword(fr, tip, ang, back=False, alpha=1.0, ground=None, hot=False):
    """Tip at `tip`, pointing along ang. The blade is 4 px with a white edge on the lit side and a dark rim on the
    other, tapering over 13 px to a one-pixel point. back darkens it a step; ground clips pixels below that y."""
    dx, dy = math.cos(ang), math.sin(ang)
    mx, my = tip[0] - dx * 23, tip[1] - dy * 23
    sy, sx = _win(mx - 26, mx + 26, my - 26, my + 26)
    X, Y = XX[sy, sx], YY[sy, sx]
    u = (tip[0] - X) * dx + (tip[1] - Y) * dy          # distance back from the tip
    v = -(X - tip[0]) * dy + (Y - tip[1]) * dx
    litdot = 0.7 * dy - 0.7 * dx                        # normal (-dy, dx) against a top-left light
    side = np.sign(v) * (1 if litdot >= 0 else -1)
    tone = np.full(u.shape, -1)
    hw = 0.2 + 1.85 * np.clip(u / 13.0, 0, 1)
    blade = (u >= -0.4) & (u <= BL) & (np.abs(v) <= hw)
    edge = np.abs(v) > hw - 0.85
    tone[blade] = 2
    tone[blade & (side > 0)] = 3
    tone[blade & (side > 0) & edge] = 4
    tone[blade & (side < 0)] = 1
    tone[blade & (side < 0) & edge] = 0
    tip_zone = blade & (u < (10 if hot else 5))
    tone[tip_zone & (side >= 0)] = 4
    tone[tip_zone & (side < 0)] = 2
    gu = u - BL + 0.05 * v * v                          # guard wings curve toward the tip
    guard = (gu >= 0) & (gu <= 2.8) & (np.abs(v) <= 6.2)
    tone[guard] = 6
    tone[guard & ((side > 0) | (gu < 0.9))] = 7
    tone[guard & (side < 0) & (np.abs(v) > 2.5)] = 5
    hilt = (u > BL + 2.8) & (u <= BL + 12) & (np.abs(v) <= 1.3)
    tone[hilt] = np.where(((u - BL) % 2.6) < 1.0, 5, 6)[hilt]
    pommel = (u > BL + 12) & (u <= BL + 15) & (np.abs(v) <= 2.2)
    tone[pommel] = 7
    tone[pommel & (side < 0) & (np.abs(v) > 1.2)] = 5
    if back:
        tone = np.where(tone >= 5, np.maximum(tone - 1, 5), np.where(tone >= 1, tone - 1, tone))
    if ground is not None:
        tone[Y > ground] = -1
    ys, xs = np.nonzero(tone >= 0)
    fr.over(ys + sy.start, xs + sx.start, PAL_RGB[tone[ys, xs]], alpha)
    return tip, (tip[0] - dx * BL, tip[1] - dy * BL)


# ---- timing ----
def foot_at(f):
    rise = ease_io((f - 22) / 28.0)
    down = ease_io((f - 142) / 22.0)
    h = rise * (1 - down)
    x, y = lerp(GROUND, HOVER, h)
    return x, y + math.sin(f * 0.25) * 2.0 * h


FRONT_KEYS = [(0, "chest"), (18, "chest"), (28, "raise"), (92, "raise"), (98, "pull"), (103, "point"),
              (140, "point"), (154, "rest"), (N, "rest")]
BACK_KEYS = [(0, "rest"), (20, "rest"), (28, "out"), (94, "out"), (103, "behind"), (140, "behind"), (152, "rest"),
             (N, "rest")]


def arm_pose(f, foot):
    """Front and back arm in local units; the finger sweeps across the field during the rain."""
    aim = T[0] - 60 + 110 * ease_io((f - RAIN0) / (RAIN1 - RAIN0))
    d = (aim - (foot[0] + 5.0), T[1] - (foot[1] - 56.0))
    n = math.hypot(*d)
    return cs.pose_at(f, FRONT_KEYS, BACK_KEYS, (d[0] / n, d[1] / n), math.exp(-((f - RAIN0) / 2.0) ** 2) * 3.0)


# ---- swords ----
A0 = math.atan2(T[1] - C[1], T[0] - C[0])            # the rain's slant
PERP = (-math.sin(A0), math.cos(A0))
AX = (math.cos(A0), math.sin(A0))
WHEEL = (70.0, 20.0)                                 # rx, ry of the tilted wheel round C
SPIN = 0.9                                           # wheel turn, rad per second
OMEGA = 2.4

order = rng.permutation(NS)
times = RAIN0 + (RAIN1 - RAIN0) * np.sort(rng.beta(1.6, 1.6, NS))
SW = []
for i in range(NS):
    SW.append(dict(
        base=2 * math.pi * i / NS + rng.uniform(-0.05, 0.05),
        slot=2 * math.pi * i / NS,
        spawn=14 + i * 0.42,
        gather=48 + rng.uniform(0, 10),
        launch=float(times[order[i]]),
        sticks=i % 3 == 0,
        puff=i % 2 == 0,
        sparks=[(rng.uniform(-2.6, -0.6), rng.uniform(-1.3, 1.3), rng.uniform(8, 14)) for _ in range(4)],
        streak=rng.uniform(0, 1, 10),
        motes=[(rng.uniform(-6, 6), rng.uniform(-10, 6), rng.uniform(0.3, 0.8), rng.uniform(0, 1)) for _ in range(3)],
    ))
CENT = C


def orbit_pos(s, f):
    fx, fy = foot_at(f)
    th = s["base"] + OMEGA * f / FPS
    return fx + 84 * math.cos(th), fy - 16 + 28 * math.sin(th), math.sin(th) < 0


def wheel_pos(s, f):
    th = s["slot"] + SPIN * f / FPS
    return C[0] + WHEEL[0] * math.cos(th), C[1] + WHEEL[1] * math.sin(th) + math.sin(f * 0.3 + s["slot"] * 3), \
        math.sin(th) < 0


def gather_pos(s, f):
    """Orbit round the rising caster, then a slow spiral up into a turning wheel slot round C."""
    ox, oy, back = orbit_pos(s, f)
    g = ease_io((f - s["gather"]) / GATHER)
    if g <= 0:
        return ox, oy, back
    wx, wy, wback = wheel_pos(s, f)
    if g >= 1:
        return wx, wy, wback
    q = 0.55                                          # the spiral is squashed upright so it stays in the cell
    r0, ph0 = math.hypot(ox - C[0], (oy - C[1]) / q), math.atan2((oy - C[1]) / q, ox - C[0])
    r1, ph1 = math.hypot(wx - C[0], (wy - C[1]) / q), math.atan2((wy - C[1]) / q, wx - C[0])
    gr = min(1.0, g * 1.5)                            # the radius closes before the sweep reaches the top
    r, ph = r0 + (r1 - r0) * gr, ph0 + ((ph1 - ph0) % (2 * math.pi)) * g
    return C[0] + r * math.cos(ph), C[1] + r * math.sin(ph) * q, (back if g < 0.5 else wback)


for s in SW:                                          # each sword falls along the slant from where it leaves the wheel
    x0, y0, _ = gather_pos(s, s["launch"])
    iy = T[1] + rng.uniform(-14, 14)
    s["imp"] = (x0 + (iy - y0) / math.tan(A0), iy)
    s["aim"] = math.atan2(iy - y0, s["imp"][0] - x0)


def sword_state(s, f):
    """(tip, ang, back, phase, progress)."""
    a = s["aim"]
    if f >= s["launch"] + FLY:
        return (s["imp"][0] + math.cos(a) * 10, s["imp"][1] + math.sin(a) * 10), a, False, "stuck", 1.0
    if f >= s["launch"]:
        x0, y0, _ = gather_pos(s, s["launch"])
        k = ((f - s["launch"]) / FLY) ** 1.6
        e = (s["imp"][0] + math.cos(a) * 10 - math.cos(a) * 23, s["imp"][1] + math.sin(a) * 10 - math.sin(a) * 23)
        cx, cy = x0 + (e[0] - x0) * k, y0 + (e[1] - y0) * k
        return (cx + math.cos(a) * 23, cy + math.sin(a) * 23), a, False, "fly", k
    x, y, back = gather_pos(s, f)
    x1, y1, _ = gather_pos(s, f + 0.3)
    x0, y0, _ = gather_pos(s, f - 0.3)
    va = math.atan2(y1 - y0, x1 - x0)
    ang = ang_lerp(va, A0, ease_io((f - s["gather"] - GATHER * 0.55) / (GATHER * 0.45)))
    return (x + math.cos(ang) * 23, y + math.sin(ang) * 23), ang, back, "air", 0.0


def draw(f):
    fr = Frame()
    L = fr.L
    foot = foot_at(f)
    fp = foot_at(f + 1)
    fm = foot_at(f - 1)
    vel = math.hypot(fp[0] - fm[0], fp[1] - fm[1]) / 2
    hov = ease_io((f - 22) / 28.0) * (1 - ease_io((f - 142) / 22.0))
    charge = ease_io((f + 2) / 16.0)
    lift = float(np.clip(0.25 + 0.3 * charge + 0.2 * hov + vel / 3, 0, 1))
    flut = float(np.clip(0.35 + 0.35 * hov + vel / 3, 0, 1))
    pose = arm_pose(f, foot)

    # avatar behind everything: 2.8x, hip behind the caster's, halo ring behind its head
    ghost = ease_io((f - 40) / 24.0) * (1 - ease_io((f - 136) / 22.0))
    if ghost > 0.01:
        S = 0.56                                      # about 44 px, its head above the caster's
        gfoot = (foot[0] - 4, foot[1] - 6)
        gp = arm_pose(f, gfoot)
        g = cs.draw(fr.over, (H, W), gfoot, S, gp, f * 0.7, lift * 0.6, flut * 0.7, ghost=ghost)
        cs.ghost_light(fr.over, L, g, ghost, f, ease_io((f - 100) / 4.0))

    # seal under the feet, rising with the caster as a platform
    seal = ease_io((f + 2) / 14.0) * (1 - 0.6 * ease_io((f - 142) / 20.0))
    rx = 14 + 30 * ease_io(f / 14.0)
    ellipse_line(fr, foot[0], foot[1], rx, rx * 0.3, BODY[3], 0.6 * seal)
    ellipse_line(fr, foot[0], foot[1], rx * 0.72, rx * 0.72 * 0.3, BODY[2], 0.5 * seal, f * 0.5, dash=11)
    glow_ring(L, foot[0], foot[1], rx, 7, 0.32 * seal, flat=0.3)
    glow(L, foot[0], foot[1] - 20, rx * 2.0, 0.14 * seal, flat=0.6)

    # charge motes spiralling up to the chest
    ch = charge * (1 - ease_io((f - 28) / 14.0))
    for j in range(30):
        if ch < 0.01:
            break
        life = ((f / 18.0) + j / 30) % 1.0
        th = j * 2.4 + life * 5
        rad = 36 * (1 - life)
        x = foot[0] + rad * math.cos(th)
        y = foot[1] - 4 - life * 30 + rad * 0.3 * math.sin(th)
        a = ch * min(1, (1 - life) * 2)
        fr.dot(x, y, "#ffffff" if life > 0.8 else BODY[3], 0.9 * a)
        glow(L, x, y, 7, 0.3 * a)

    # swords behind the caster
    items = []
    for s in SW:
        if f < s["spawn"]:
            continue
        tip, a, back, phase, k = sword_state(s, f)
        items.append((0 if back else (2 if phase == "stuck" else 1), s, tip, a, back, phase, k))
    items.sort(key=lambda t: (t[0], t[2][1]))

    def draw_sword(s, tip, a, back, phase, k):
        age = f - s["spawn"]
        mid = (tip[0] - math.cos(a) * 23, tip[1] - math.sin(a) * 23)
        if age < 2:
            glow(L, *mid, 12, 0.6)
            fr.dot(*mid, "#ffffff")
            return
        if phase == "stuck":
            st = f - (s["launch"] + FLY)
            fade = 1 - ease_io((st - 16) / 24.0) * 0.8
            if s["sticks"]:
                sword(fr, tip, a, alpha=fade, ground=s["imp"][1] + 1)
                glow(L, *s["imp"], 10, 0.22 * fade)
            if st < 1:
                glow(L, *s["imp"], 16, 0.35)
            ix, iy = s["imp"]
            if st < 4:
                for j in range(5):
                    th = math.pi * (1.1 + 0.8 * (j + s["streak"][j]) / 5)
                    ln = (8 + 12 * s["streak"][j + 5]) * (1 - st / 4) + 2
                    p0 = (ix + math.cos(th) * (3 + st * 3), iy + math.sin(th) * (3 + st * 3) * 0.6)
                    p1 = (ix + math.cos(th) * (3 + st * 3 + ln), iy + math.sin(th) * (3 + st * 3 + ln) * 0.6)
                    line(fr, p0, p1, "#ffffff", BODY[3], 1.0, 0.3)
            if st < 7:
                Rr = 4 + 16 * (1 - (1 - st / 7) ** 2)
                ellipse_line(fr, ix, iy, Rr, Rr * 0.3, "#fff0b0", 0.7 * (1 - st / 7))
            if s["puff"] and 1 <= st < 25:
                q = (st - 1) / 24
                puff(fr, ix - 4, iy - 2 - st * 0.4, 4 + 5 * q, 0.35 * (1 - q) ** 1.5)
            for vy, vx, life in s["sparks"]:
                if st < life:
                    q = st / life
                    px = s["imp"][0] + vx * st * 4
                    py = s["imp"][1] + vy * st * 3 + 0.22 * st * st
                    fr.dot(px, py, "#ffffff" if q < 0.4 else BODY[3], 1 - q * 0.6)
                    glow(L, px, py, 6, 0.35 * (1 - q))
            if s["sticks"] and st > 12:
                for mx, my, sp, ph in s["motes"]:
                    life = ((st - 12) * sp / 14.0 + ph) % 1.0
                    px = s["imp"][0] - math.cos(a) * 12 + mx + math.sin(life * 6 + ph * 9) * 3
                    py = s["imp"][1] + my * 0.3 - 8 - life * 52
                    am = (1 - life) * min(1, (st - 12) / 6)
                    fr.dot(px, py, BODY[3], 0.9 * am)
                    glow(L, px, py, 7, 0.3 * am)
            return
        if phase == "fly":
            dx, dy = math.cos(a), math.sin(a)
            grd = (tip[0] - dx * 34, tip[1] - dy * 34)
            tail = (grd[0] - dx * (20 + 80 * k), grd[1] - dy * (20 + 80 * k))
            line(fr, tail, grd, BODY[2], "#fff4c0", 0.0, 0.85)
            line(fr, (tail[0] + PERP[0], tail[1] + PERP[1]), (grd[0] + PERP[0], grd[1] + PERP[1]),
                 BODY[1], BODY[3], 0.0, 0.5)
            kl = min(1.0, 0.2 + k * 2.5)
            glow_line(L, tail, tip, 8, 0.32 * kl)
            glow_line(L, tail, tip, 24, 0.14 * kl)
        p0, p1 = sword(fr, tip, a, back=back, hot=phase == "fly")
        kk = (0.12 if back else 0.22) * (1 - 0.5 * ease_io((f - s["gather"] - GATHER * 0.5) / (GATHER * 0.5)))
        glow_line(L, p0, p1, 5, kk)
        glow_line(L, p0, p1, 15, kk * 0.45)
        if age < 4:
            glow(L, *mid, 12, 0.4 * (1 - age / 4))

    for it in items:
        if it[0] == 0:
            draw_sword(*it[1:])

    # the caster
    g = cs.draw(fr.over, (H, W), foot, SC, pose, f, lift, flut)
    cs.body_light(L, g, charge)
    point = ease_io((f - 100) / 3.0) * (1 - ease_io((f - 140) / 8.0))
    jab = math.exp(-((f - RAIN0) / 2.0) ** 2)
    if point > 0.01:
        cs.finger_light(L, g, point, jab)
        fr.dot(*g["finger"], "#ffffff")

    # air swords in front, then the stuck ones
    for it in items:
        if it[0] >= 1:
            draw_sword(*it[1:])
    air = [it[2] for it in items if it[5] == "air"]
    if len(air) > 3:
        mx, my = np.mean(air, 0)
        glow(L, mx, my, 100, 0.2 * min(1, len(air) / 10), flat=0.7)

    # the wheel: a dashed qi ellipse turning round the swords
    gath = ease_io((f - 60) / 16.0) * (1 - ease_io((f - 128) / 8.0))
    if gath > 0.01:
        ellipse_line(fr, C[0], C[1], WHEEL[0] + 12, WHEEL[1] + 6, BODY[3], 0.45 * gath, -f * 0.3, dash=13)
        glow_ring(L, C[0], C[1], WHEEL[0] + 12, 6, 0.22 * gath, flat=(WHEEL[1] + 6) / (WHEEL[0] + 12))
        glow(L, C[0], C[1], 90, 0.12 * gath, flat=0.5)

    # the rain: the field pool swells with the number of fresh impacts
    fresh = sum(1 for s in SW if 0 <= f - s["launch"] - FLY < 6)
    pool = min(0.6, 0.1 * fresh)
    scene = ease_io((f - 20) / 20.0) * (1 - 0.6 * ease_io((f - 144) / 20.0))
    glow(L, 330, 262, 250, 0.11 * scene, flat=0.75)
    glow(L, 310, 220, 290, 0.1 * scene, flat=0.78)           # low wide fill over the sky half
    field = ease_io((f - RAIN0) / 10.0) * (1 - 0.5 * ease_io((f - 146) / 18.0))
    glow(L, T[0], T[1] - 30, 150, 0.1 * field, flat=0.5)
    if field > 0:
        glow(L, T[0], T[1] - 10, 120, pool + 0.08 * field, flat=0.42)
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
            print(f"frame {f}: empty colour"); ok = False
            continue
        edge = np.zeros_like(a)
        edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
        if (a & edge).any() or ((Lc > 0.02) & edge).any():
            print(f"frame {f}: touches the cell edge"); ok = False
        ys, xs = np.nonzero(a)
        box = Lc[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        covers.append((box > 0.03).mean())
        means.append(box[box > 0.03].mean() if (box > 0.03).any() else 0)
    print(f"light cover {np.median(covers):.0%}  mean {np.median(means):.3f}  (strong: 75-95%, 0.12-0.18)")

    ncol = 10

    def grid(frames, path, n=ncol, scale=1):
        rows = math.ceil(len(frames) / n)
        img = np.zeros((rows * H, n * W, 4), np.uint8)
        for i, fr_ in enumerate(frames):
            r, c = divmod(i, n)
            img[r * H:(r + 1) * H, c * W:(c + 1) * W] = fr_
        im = Image.fromarray(img, "RGBA")
        if scale != 1:
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        im.save(path)
    grid(comps, OUT / f"{NAME}.png")
    grid(cols, OUT / f"{NAME}_color.png")
    grid([pfx.composite(np.zeros((H, W, 4), np.uint8), l) for l in lights], OUT / f"{NAME}_light.png")
    pick = list(range(0, N, 10))
    for bg, tag in (("#101018", "dark"), ("#5a6070", "mid")):
        grid([pfx.composite(cols[i], lights[i], bg) for i in pick], OUT / f"{NAME}_contact_{tag}.png", n=4)
        for i in (40, 70, 96, 118, 130):
            Image.fromarray(pfx.composite(cols[i], lights[i], bg), "RGBA").resize((W * 2, H * 2), Image.NEAREST).save(
                OUT / f"{NAME}_f{i:03d}_x2_{tag}.png")
    pfx.gif(comps, OUT / f"{NAME}.gif", FPS, scale=2)
    meta = dict(name=NAME, w=W, h=H, frames=N, fps=FPS, cols=ncol, loop=False, pivot=list(GROUND),
                target=list(T), glow="strong",
                states=dict(charge=[0, 21], appear_rise=[14, 50], gather=[48, 94], point=[94, 104],
                            rain=[RAIN0, RAIN1 + int(FLY)], dissolve=[140, N - 1]), light_gain=1.0,
                sheets=dict(composite=f"{NAME}.png", color=f"{NAME}_color.png", light=f"{NAME}_light.png"))
    (OUT / f"{NAME}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
