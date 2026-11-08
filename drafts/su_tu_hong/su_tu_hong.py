"""su_tu_hong (Lion's Roar): a forward cone blast, general mode.

The caster draws a breath (motes pulled to the mouth), roars (white flash at the mouth), a golden lion-head ghost
forms in front of it and roars with it, and nested sound arcs roll out to the right, kicking up dust and shards
from the ground. The lion breaks into embers and the last arcs and dust settle.

Side view, facing east, mirror True. 192x128, 60 frames at 30 fps, one-shot. Soft style, glow strong.
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
import facing as fc  # noqa: E402
import fxkit as fk  # noqa: E402
import pfx  # noqa: E402

NAME = "su_tu_hong"
OUT = HERE / "out"
W, H, N, FPS = 192, 128, 60, 30
GROUND = 112
FOOT = (36.0, GROUND)
SC = 0.44                                   # caster about 34 px
PIVOT = [36, GROUND]

GOLD = ["#3a2410", "#8a5a1c", "#e0a030", "#ffe080", "#fffbe8"]
DUST = ["#3a2c22", "#6a5440", "#9a8060", "#c8b090"]
ROCK = ["#2a2018", "#5a4632", "#8a7050", "#c8a470"]
PAL = GOLD + DUST + ROCK                    # 0..4 gold, 5..8 dust, 9..12 rock
PAL_RGB = np.stack([pfx._hex(c) / 255.0 for c in PAL])
LIGHT_RAMP = ["#6a3a10", "#e09030", "#ffe090", "#ffffff"]

LION_C = (72.0, 74.0)
ARC_O = (87.0, 78.0)                        # the arcs start inside the lion's mouth
ARC_FLAT = 0.76
ARC_A = 0.82                                # half angle of the cone, radians
ARCS = [18, 22, 26, 30, 34]                 # emit frames
ARC_LIFE = 23

X, Y = np.meshgrid(np.arange(W, dtype=float), np.arange(H, dtype=float))


def ease(s):
    s = np.clip(s, 0.0, 1.0)
    return s * s * (3 - 2 * s)


def eout(s):
    s = np.clip(s, 0.0, 1.0)
    return 1 - (1 - s) ** 2


def smooth_noise(seed, cell=5):
    rng = np.random.default_rng(seed)
    gw, gh = W // cell + 2, H // cell + 2
    im = Image.fromarray((rng.random((gh, gw)) * 255).astype(np.uint8)).resize((gw * cell, gh * cell),
                                                                              Image.BILINEAR)
    return np.asarray(im, float)[:H, :W] / 255.0


NOISE = smooth_noise(7, 4) * 0.6 + smooth_noise(11, 2) * 0.4


class Frame:
    """Straight-alpha colour layer with over(), plus the summed light map L."""

    def __init__(self):
        self.rgb = np.zeros((H, W, 3))
        self.a = np.zeros((H, W))
        self.L = np.zeros((H, W))

    def over(self, ys, xs, rgb, a):
        ys, xs = np.asarray(ys), np.asarray(xs)
        rgb = np.broadcast_to(np.asarray(rgb, float), (len(ys), 3))
        a = np.broadcast_to(np.asarray(a, float), ys.shape)
        ok = (ys >= 0) & (ys < H) & (xs >= 0) & (xs < W)
        ys, xs, rgb, a = ys[ok], xs[ok], rgb[ok], a[ok]
        A = self.a[ys, xs]
        oa = a + A * (1 - a)
        c = (rgb * a[:, None] + self.rgb[ys, xs] * (A * (1 - a))[:, None]) / np.maximum(oa, 1e-6)[:, None]
        self.rgb[ys, xs] = c
        self.a[ys, xs] = oa

    def shades(self, m, alpha):
        """Paint a shade map of PAL indices (-1 empty) with alpha, a scalar or a per-pixel map."""
        ys, xs = np.nonzero(m >= 0)
        if not len(ys):
            return
        a = alpha[ys, xs] if np.ndim(alpha) == 2 else np.full(len(ys), float(alpha))
        self.over(ys, xs, PAL_RGB[m[ys, xs]], a)


def glow(L, x, y, r, k, flat=1.0):
    cs.glow(L, x, y, r, k, flat)


def body_light(L, g, charge):
    """cs.body_light with the hip pool cut to r 46, so the light stays inside a 128 px cell."""
    cs.glow_line(L, g["feet"], g["head"], 8, 0.12)
    cs.glow_line(L, g["feet"], g["head"], 22, 0.08)
    glow(L, *g["head"], 6, 0.12)
    for pts in g["hair"]:
        for a_, b_ in zip(pts, pts[1:]):
            cs.glow_line(L, a_, b_, 4, 0.08)
    glow(L, *g["hip"], 46, 0.1 * (0.4 + 0.6 * charge), flat=0.85)


def caster(fr, f):
    roar = ease((f - 15) / 3) * (1 - ease((f - 40) / 15))
    inhale = ease(f / 14) * (1 - ease((f - 16) / 4))
    shake = (1 if f % 2 else -1) * (16 <= f <= 30)
    foot = (FOOT[0] - 2 * ease((f - 15) / 4) * (1 - ease((f - 44) / 12)) + 0.5 * shake, FOOT[1])
    pose = cs.pose_at(f, [(0, "rest"), (7, "chest"), (15, "pull"), (40, "pull"), (52, "rest")],
                      [(0, "rest"), (15, "out"), (44, "out"), (54, "rest")])
    g = cs.draw(fr.over, (H, W), foot, SC, pose, f, 0.15 + 0.8 * roar, 0.2 + 0.7 * roar, hair="loose")
    body_light(fr.L, g, 0.3 + 0.7 * max(inhale, roar))
    return g


def mouth_of(g):
    hx, hy = g["head"]
    return hx + 3.0, hy + 1.5


def inhale_motes(fr, f, M):
    """Motes pulled from the cone ahead into the caster's mouth, and a faint ring closing on it."""
    if f > 16:
        return
    m = np.full((H, W), -1, int)
    for i in range(18):
        t = (f - fk.hsh(i, 1) * 6) / 9.0
        if t < 0 or t > 1:
            continue
        sx = 58 + fk.hsh(i, 2) * 76
        sy = 52 + fk.hsh(i, 3) * 50
        e = ease(t)
        bend = math.sin(t * math.pi) * (fk.hsh(i, 4) - 0.5) * 18
        x = sx + (M[0] - sx) * e
        y = sy + (M[1] - sy) * e + bend
        tone = 4 if t > 0.6 else 3
        for k in range(3):                       # a short trail away from the mouth
            tx = int(round(x + (sx - M[0]) * 0.03 * k))
            ty = int(round(y + (sy - M[1]) * 0.03 * k))
            if 0 <= tx < W and 0 <= ty < H:
                m[ty, tx] = max(m[ty, tx], tone - k)
        glow(fr.L, x, y, 3, 0.3 * (0.4 + 0.6 * t))
    fr.shades(m, 0.85)
    draw_in = ease(f / 14)
    glow(fr.L, M[0], M[1], 30, 0.25 * draw_in)
    glow(fr.L, M[0] + 40, M[1] - 2, 50, 0.12 * draw_in, flat=0.7)
    s = (f - 5) / 10
    if 0 <= s <= 1:
        R = 22 - 18 * ease(s)
        ring = np.where(np.abs(np.hypot(X - M[0], Y - M[1]) - R) < 0.7, 2, -1)
        fr.shades(ring, 0.35 * math.sin(s * math.pi))
        cs.glow_ring(fr.L, M[0], M[1], R, 3, 0.15 * math.sin(s * math.pi))


def mouth_flash(fr, f, M):
    s = (f - 15) / 5
    if s < 0 or s > 1:
        return
    q = np.hypot(X - M[0], Y - M[1])
    m = np.full((H, W), -1, int)
    if f in (16, 17):
        m[q <= 2.6] = 4
        m[(q > 2.6) & (q <= 3.6)] = 3
    R = 3 + 9 * eout(s)
    m[(np.abs(q - R) < 0.6) & (X > M[0] - 2) & (m < 0)] = 3 if s < 0.5 else 2
    fr.shades(m, 1.0 - 0.6 * s)
    k = math.exp(-((f - 16.5) / 1.4) ** 2)
    glow(fr.L, *M, 6, 0.7 * k)
    glow(fr.L, *M, 18, 0.32 * k)


def lion(fr, f):
    """The golden lion-head ghost in profile, facing east, jaw open, mane streaming back."""
    show = ease((f - 14) / 6)
    gone = ease((f - 36) / 15)
    if show <= 0 or f > 52:
        return
    sl = 0.72 + 0.3 * show + 0.06 * gone
    cx = LION_C[0] + 4 * ease((f - 15) / 10) + 7 * gone
    cy = LION_C[1] - 2 * gone
    u, v = (X - cx) / sl, (Y - cy) / sl
    jaw = 0.6 * ease((f - 15) / 4) * (1 - 0.5 * gone) + 0.04 * math.sin(f * 1.7) * (f < 38)

    m = np.full((H, W), -1, int)
    mane = np.hypot((u + 3) / 12, (v + 1) / 11) < 1
    m[mane] = 1
    for j in range(15):
        phi = math.radians(-95 - 235 * j / 14)
        a0 = phi
        a1 = a0 + 0.7 * (((math.pi - a0 + math.pi) % math.tau) - math.pi)   # each lock bends back in the wind
        ln = 13 + 9 * fk.hsh(j, 61) + 5 * max(-math.cos(phi), 0)
        lock, pts = cs.strand(u, v, (-3 + 7 * math.cos(phi), -1 + 7 * math.sin(phi)), a0, a1, ln, 3.6, 0.5,
                              lambda k, j=j: 0.3 * math.sin(k * 0.8 - f * 0.45 + j * 1.3), n=8, mw=0.6 / sl)
        m[lock] = cs.shade(lock, 2 if j % 2 else 1)[lock]
        core = np.zeros_like(lock)
        for p0, p1 in zip(pts[1:5], pts[2:6]):
            core |= cs.seg_d(u, v, p0, p1) < 0.7
        m[core & lock] = 3
        mane |= lock
    m[np.hypot(u + 1, v + 12) < 3.6] = 2
    m[np.hypot(u + 0.6, v + 11.5) < 1.6] = 1
    face = np.hypot((u - 5) / 10.5, (v - 0.5) / 9.5) < 1
    upper = cs.seg_d(u, v, (8, -2.5), (19, -1.5)) < 4.2
    hinge = (7.0, 4.5)
    tip = (hinge[0] + 12 * math.cos(jaw), hinge[1] + 12 * math.sin(jaw))
    lower = cs.seg_d(u, v, hinge, tip) < 2.9
    head = face | upper
    m[head] = cs.shade(head, 3)[head]
    m[lower] = cs.shade(lower, 2)[lower]
    mouth = cs.tri(u, v, hinge, (19.5, 2.0), (tip[0] + 0.5, tip[1] - 1.5)) & ~upper & ~lower
    m[mouth] = 4
    m[np.hypot(u - 20.5, v + 3.2) < 2.0] = 1                               # nose
    m[cs.seg_d(u, v, (3, -8), (11.5, -8.6)) < 1.2] = 1                    # brow
    m[cs.seg_d(u, v, (6.5, -5.2), (10.5, -6.0)) < 0.9] = 4                # eye slit
    m[cs.tri(u, v, (16.5, 1.4), (19.0, 1.4), (17.8, 5.0))] = 4             # upper fang
    lt = (hinge[0] + 9.5 * math.cos(jaw), hinge[1] + 9.5 * math.sin(jaw))
    m[cs.tri(u, v, (lt[0] - 1.2, lt[1] - 1.5), (lt[0] + 1.2, lt[1] - 1.5), (lt[0] + 0.2, lt[1] - 4.8))
      & (jaw > 0.25)] = 4                                                   # lower fang
    m[np.hypot(u - 9, v - 4.5) < 1.0] = 1                                   # whisker dots
    m[np.hypot(u - 12, v - 3.8) < 0.8] = 1

    body = m >= 0
    er = body.copy()
    er[1:-1, 1:-1] = body[1:-1, 1:-1] & body[:-2, 1:-1] & body[2:, 1:-1] & body[1:-1, :-2] & body[1:-1, 2:]
    rim = body & ~er
    m[rim & (m < 3) & ~mane] = 3
    m[rim & mane] = np.maximum(m[rim & mane], 2)
    keep = NOISE + 0.25 * np.clip((u + 20) / 40, 0, 1) > gone * 1.3      # breaks up from the back of the mane
    m[~keep] = -1
    a = np.where(rim, 0.9, 0.6) * show * (1 - 0.5 * gone)
    a = np.where(m == 4, show, a)
    fr.shades(m, a)

    life = show * (1 - gone)
    fr.L += (m >= 0) * 0.06 * show * (1 - 0.6 * gone)
    mx, my = cx + sl * 20, cy + sl * 2.5
    glow(fr.L, cx + sl * 8.5, cy - sl * 5.6, 4, 0.4 * life)
    glow(fr.L, mx + 3, my, 6, 0.55 * life)
    glow(fr.L, mx + 8, my, 20, 0.25 * life)
    glow(fr.L, cx - 4, cy, 50, 0.1 * life)
    if gone > 0:
        em = np.full((H, W), -1, int)
        for i in range(16):
            age = f - (36 + fk.hsh(i, 21) * 12)
            if age < 0 or age > 10:
                continue
            a0 = fk.hsh(i, 22) * math.tau
            x = cx + math.cos(a0) * 18 * sl + age * (0.8 + fk.hsh(i, 23))
            y = cy + math.sin(a0) * 15 * sl - age * 0.6
            px, py = int(round(x)), int(round(y))
            if 1 <= px < W - 1 and 1 <= py < H - 1:
                em[py, px] = 4 if age < 4 else 3
                glow(fr.L, x, y, 3, 0.35 * (1 - age / 10))
        fr.shades(em, 0.9)


def arcs(fr, f):
    dx, dy = X - ARC_O[0], (Y - ARC_O[1]) / ARC_FLAT
    q = np.hypot(dx, dy)
    th = np.arctan2(dy, dx)
    for i, t0 in enumerate(ARCS):
        s = (f - t0) / ARC_LIFE
        if s < 0 or s > 1:
            continue
        r = 6 + 88 * eout(s)
        a = (1 - s) ** 0.8
        e = q - (r + 0.6 * np.sin(th * 7 + f * 0.9 + i * 2.0))
        ang = np.clip((ARC_A - np.abs(th)) / 0.2, 0, 1)
        brk = np.sin(th * 9 + i * 3.1 + s * 3) + 0.5 * np.sin(th * 23 - i * 1.7)
        on = (ang > 0) & (brk > -1.5 + 1.6 * s) & (Y < GROUND - 1)
        m = np.full((H, W), -1, int)
        m[on & (e > -1.0) & (e <= 0.0)] = 4 if s < 0.35 else 3
        m[on & (e > -2.0) & (e <= -1.0) & (s < 0.7)] = 3 if s < 0.35 else 2
        body = on & (e > -3.5 - 5 * (1 - s)) & (e <= -2.0)
        m[body] = 3
        fr.shades(m, np.where(body, 0.16 * a, 0.95 * a) * ang)
        d = np.abs(e)
        k = 0.5 * a * ang * np.where(on, 1.0, 0.35)
        fr.L += np.where(d < 2.6, (1 - d / 2.6) ** 2 * k, 0)
        fr.L += np.where(d < 9.0, (1 - d / 9.0) ** 2 * k * 0.45, 0)


def streaks(fr, f):
    """Air rushing forward inside the cone."""
    m = np.full((H, W), -1, int)
    for i in range(14):
        age = f - (17 + fk.hsh(i, 31) * 20)
        if age < 0 or age > 12:
            continue
        th = (fk.hsh(i, 32) * 2 - 1) * ARC_A * 0.85
        rad = 12 + age * (6 + 3 * fk.hsh(i, 33))
        for k in range(int(5 + 8 * fk.hsh(i, 34))):
            x = ARC_O[0] + (rad - k) * math.cos(th)
            y = ARC_O[1] + (rad - k) * math.sin(th) * ARC_FLAT
            px, py = int(round(x)), int(round(y))
            if 1 <= px < W - 2 and 1 <= py < GROUND - 1:
                m[py, px] = max(m[py, px], 3 if k < 2 else 2)
        hx = ARC_O[0] + rad * math.cos(th)
        if hx < W - 8:
            glow(fr.L, hx, ARC_O[1] + rad * math.sin(th) * ARC_FLAT, 3, 0.25 * (1 - age / 12))
    fr.shades(m, 0.7)


def dust(fr, f):
    """Ground dust kicked up as the arcs pass, drifting forward and breaking up."""
    m = np.full((H, W), -1, int)
    alpha = np.zeros((H, W))
    for i in range(18):
        x0 = 66 + i * 6.2 + fk.hsh(i, 41) * 4
        age = f - (19 + (x0 - 66) / 112 * 16 + fk.hsh(i, 42) * 2)
        if age < 0:
            continue
        life = 1 - ease((age - 12) / 22)
        if life <= 0:
            continue
        e = eout(age / 26)
        cx = min(x0 + 9 * e * (0.6 + fk.hsh(i, 43)), W - 10)
        cy = GROUND - 2 - (5 + 6 * fk.hsh(i, 44)) * e
        r = min(1.5 + (3 + 3 * fk.hsh(i, 45)) * e, W - 4 - cx)
        piece = np.full((H, W), -1, int)
        fk.puff(piece, X, Y, cx, cy, r, (5, 6, 7), brk=0.0, seed=i, ph=f * 0.1)
        on = piece >= 0
        m[on] = piece[on]
        alpha[on] = np.maximum(alpha[on], 0.55 * life)
    fr.shades(m, alpha)


def shards(fr, f):
    """Stone chips thrown forward and up by the blast, landing and fading."""
    m = np.full((H, W), -1, int)
    for i in range(10):
        x0 = 80 + fk.hsh(i, 51) * 76
        age = f - (20 + (x0 - 80) / 76 * 9)
        if age < 0:
            continue
        vx = 1.4 + 1.6 * fk.hsh(i, 52)
        vy = -2.2 - 1.6 * fk.hsh(i, 53)
        gr = 0.2
        tl = -2 * vy / gr
        ta = min(age, tl)
        x = x0 + vx * ta
        y = GROUND - 1 + vy * ta + 0.5 * gr * ta * ta
        if x > W - 8 or age > tl + 14:
            continue
        pts = fk.polygon(x, y, 1.6 + 1.2 * fk.hsh(i, 54), 5, i, ph=ta * 0.5 * (1 if i % 2 else -1))
        piece = np.full((H, W), -1, int)
        fk.facets(piece, X, Y, pts, (9, 10, 11, 12))
        m[piece >= 0] = piece[piece >= 0]
        if age < tl:
            glow(fr.L, x, y, 3, 0.12)
    fr.shades(m, 0.95)


def scene_light(fr, f):
    life = (0.45 + 0.55 * ease((f - 6) / 10)) * (1 - 0.25 * ease((f - 38) / 21))
    peak = math.exp(-((f - 19) / 5) ** 2)
    glow(fr.L, 102, 72, 78, 0.22 * life, flat=0.9)
    glow(fr.L, 118, 76, 56, 0.34 * peak, flat=0.8)
    glow(fr.L, 128, 72, 66, 0.13 * ease((f - 32) / 10), flat=0.85)   # afterglow of the air still ringing
    for t0 in ARCS:                               # a pool riding the wave front, so the far cone stays lit
        sa = (f - t0) / ARC_LIFE
        if 0 <= sa <= 1:
            fx_ = ARC_O[0] + (6 + 88 * eout(sa)) * 0.75
            glow(fr.L, fx_, 74, 50, 0.14 * (1 - sa) ** 0.6, flat=1.0)


def render(f):
    fr = Frame()
    scene_light(fr, f)
    dust(fr, f)
    g = caster(fr, f)
    M = mouth_of(g)
    inhale_motes(fr, f, M)
    lion(fr, f)
    streaks(fr, f)
    arcs(fr, f)
    shards(fr, f)
    mouth_flash(fr, f, M)
    col = np.concatenate([fr.rgb, fr.a[..., None]], -1)
    return (np.clip(col, 0, 1) * 255).round().astype(np.uint8), fr.L


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cols, lights, finals, bad, covers, means = [], [], [], [], [], []
    edge = np.zeros((H, W), bool)
    edge[[0, -1], :] = True
    edge[:, [0, -1]] = True
    for f in range(N):
        col, L = render(f)
        Lc = np.clip(L, 0, 1)
        light = pfx.tint(np.repeat(Lc[..., None], 3, -1), LIGHT_RAMP)
        cols.append(col)
        lights.append(light)
        finals.append(pfx.composite(col, light))
        a = col[..., 3] > 0
        if not a.any():
            bad.append(f"frame {f}: empty colour")
            continue
        if (a & edge).any():
            bad.append(f"frame {f}: colour touches the edge")
        if ((L > 0.02) & edge).any():
            bad.append(f"frame {f}: light touches the edge")
        ys, xs = np.nonzero(a)
        box = Lc[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        covers.append((box > 0.03).mean())
        means.append(box[box > 0.03].mean() if (box > 0.03).any() else 0)

    pfx.strip(finals, OUT / f"{NAME}.png")
    pfx.strip(cols, OUT / f"{NAME}_color.png")
    lsheet = (np.concatenate(lights, 1) * 255).round().astype(np.uint8)
    Image.fromarray(lsheet, "RGB").save(OUT / f"{NAME}_light.png")
    pfx.gif(finals, OUT / f"{NAME}.gif", FPS, scale=4)
    for bg, tag in (("#101018", "dark"), ("#5a6070", "mid")):
        rows = [np.concatenate([pfx.composite(c, l, bg) for c, l in zip(cols[r:r + 10], lights[r:r + 10])], 1)
                for r in range(0, N, 10)]
        img = Image.fromarray(np.concatenate(rows, 0)[..., :3])
        img.resize((img.width * 4, img.height * 4), Image.NEAREST).save(OUT / f"{NAME}_4x_{tag}.png")

    meta = dict(name=NAME, w=W, h=H, frames=N, fps=FPS, pivot=PIVOT, loop=False, glow="strong", light_gain=1.0,
                sheet=f"{NAME}.png", color=f"{NAME}_color.png", light=f"{NAME}_light.png", blend_light="add",
                states={"inhale": [0, 14], "roar": [15, 36], "fade": [37, 59]}, peak=[16, 18])
    meta.update(fc.meta("side", W, H, PIVOT))
    fc.check(meta)
    (OUT / f"{NAME}.json").write_text(json.dumps(meta, indent=1))

    print(f"light cover {np.median(covers) * 100:.0f} %  mean {np.median(means):.3f}  (strong: 75-95 %, 0.12-0.18)")
    if bad:
        print("\n".join(bad))
        sys.exit(1)
    print("ok:", OUT)


if __name__ == "__main__":
    main()
