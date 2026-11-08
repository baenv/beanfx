"""wind_burst: a top-down RPG wind AoE attack around a character, one-shot, general mode.

128x128 cell, 30 fps, 60 frames (2 s), pivot at the cell centre (the caster's feet). Soft style, glow medium.

| state    | frames | seconds | what moves                                                        |
|----------|--------|---------|-------------------------------------------------------------------|
| gather   | 0-23   | 0.80    | gust streaks spiral in from r 50 to 18, leaves and dust pulled in |
| hold     | 24-29  | 0.20    | a tight fast spin at r 15 to 18, light builds                     |
| burst    | 30-44  | 0.50    | 2-frame white flash, shock ring and gust crescents fly out        |
| dissolve | 45-59  | 0.50    | streaks thin and break, dust breaks up, leaves drift and settle   |
"""
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "kit"))
import fxlib  # noqa: E402
import light  # noqa: E402
import pfx  # noqa: E402
from fxkit import hsh, leaf, puff  # noqa: E402

NAME = "wind_burst"
W = H = 128
CX, CY = 64.0, 66.0          # ground centre (feet); drawn slightly low so lifted parts keep a top margin
FLAT = 0.62                  # top-down ground squash
FPS = 30

GATHER, GATHER_N = 0, 24
HOLD, HOLD_N = GATHER + GATHER_N, 6
BURST, BURST_N = HOLD + HOLD_N, 15
DISSOLVE, DISSOLVE_N = BURST + BURST_N, 15
FRAMES = DISSOLVE + DISSOLVE_N
PEAK = (BURST, BURST + 1)
STATES = {"gather": [GATHER, HOLD - 1], "hold": [HOLD, BURST - 1],
          "burst": [BURST, DISSOLVE - 1], "dissolve": [DISSOLVE, FRAMES - 1]}

R_IN, R_HOLD, R_OUT = 50.0, 16.0, 52.0   # streak radius at spawn, in the spin, at the end of the burst

# palette: wind 0-3 (translucent to white), dust 4-6 (translucent), leaves 7-10
PAL = ["#1f7a80a0", "#52c8b8c8", "#bdf4ece8", "#ffffff",
       "#8a7a6a2c", "#b6a28844", "#e2d4ba5c",
       "#2d6436", "#4f9645", "#8cc65e", "#d2ec9a"]
WIND = (0, 1, 2, 3)
DUST = (4, 5, 6)
LEAF = (7, 8, 9, 10)
LIGHT_RAMP = ["#0c4a54", "#3cc8bc", "#c2f8f0", "#ffffff"]

NS, NL, ND = 14, 8, 11       # streaks, leaves, dust puffs on the ring

Y, X = np.mgrid[0:H, 0:W].astype(float)
C = SimpleNamespace(x=X, y=Y)


def ease_out(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def ease_in(t):
    t = min(max(t, 0.0), 1.0)
    return t * t


def gp(r, th, z=0.0):
    """Ground point at radius r, angle th, lifted z px."""
    return CX + r * math.cos(th), CY + r * math.sin(th) * FLAT - z


def streak_state(i, f):
    """Head radius, head angle, arc span, spiral pitch (tail radius offset), width, life 0..1, lift."""
    ph = math.tau * i / NS + hsh(i, 1) * 0.5
    z = 2 + 16 * hsh(i, 2)
    dl = hsh(i, 3) * 6                       # spawn delay in frames
    sp = 0.8 + 0.4 * hsh(i, 4)               # speed factor
    if f < HOLD:
        t = max(f - dl, 0) / (GATHER_N - dl)
        if f < dl:
            return None
        r = R_IN + (R_HOLD + 4 - R_IN) * ease_in(t)
        th = ph + sp * (1.6 * t + 2.2 * t * t)
        span = 0.5 + 1.1 * t
        pitch = 10 * (1 - t) + 2              # tail lies outside: it moves in
        w = 1.2 + 0.9 * t
        life = min(1.0, (f - dl + 1) / 4)
        z *= 0.6 + 0.4 * t
    elif f < BURST:
        t = (f - HOLD) / HOLD_N
        r = R_HOLD + 4 - 4 * t
        th = ph + sp * 3.8 + sp * 0.9 * (f - HOLD + 1)
        span, pitch, w, life = 1.9, 1.0, 2.2, 1.0
        z *= 1.0 - 0.5 * t
    else:
        t = (f - BURST) / (BURST_N + DISSOLVE_N - 1)
        k = ease_out((f - BURST) / BURST_N)
        r = R_HOLD + (R_OUT - 16 * hsh(i, 5) - R_HOLD) * k
        th = ph + sp * 3.8 + sp * 0.9 * (HOLD_N + 1) + sp * (0.55 * k + 0.25 * t)
        span = 1.6 * (1 - 0.6 * t)
        pitch = -(8 + 20 * k) * (1 - 0.4 * t)     # tail inside: a pinwheel thrown out
        w = 2.4 - 1.4 * t
        life = 1.0 - ease_in(max(0.0, (f - DISSOLVE + 4 * hsh(i, 6)) / DISSOLVE_N))
        z *= 0.5 * (1 - t)
        if life <= 0.05:
            return None
    return r, th, span, pitch, w, life, z


def streak(m, L, i, f):
    s = streak_state(i, f)
    if s is None:
        return
    r, th, span, pitch, w, life, z = s
    n = 12
    pts = []
    for j in range(n + 1):
        u = j / n                                    # 0 tail, 1 head
        rr = r + pitch * (1 - u)
        pts.append(gp(rr, th - span * (1 - u), z * (0.6 + 0.4 * u)))
    d, t, side = fxlib.stroke(X, Y, pts, 0.3, w)
    on = d < 0
    if life < 1:                                     # break into dashes as it fades
        gap = np.sin(t * 9 + i * 2.1 + f * 0.7) > (1.6 * life - 0.7)
        on &= ~gap
    if not on.any():
        return
    piece = np.full(m.shape, -1, np.int8)
    piece[on] = WIND[0]
    piece[on & (t > 0.3)] = WIND[1]
    piece[on & (t > 0.6) & (d < -0.35)] = WIND[2]
    piece[on & (t > 0.72) & (np.abs(side) < 0.55) & (life > 0.5)] = WIND[3]
    m[piece >= 0] = piece[piece >= 0]
    # light: core near the head, pool along the hot half
    k = 0.27 * life
    own = np.zeros_like(L)                           # max over segments, so joints do not double up
    for j in range(n // 2, n):
        seg = np.zeros_like(L)
        light.glow_line(seg, C, pts[j], pts[j + 1], 3.0, k * (j / n))
        light.glow_line(seg, C, pts[j], pts[j + 1], 7.5, 0.4 * k)
        np.maximum(own, seg, out=own)
    L += own


def shock_ring(m, L, f):
    if f < BURST or f > BURST + 13:
        return
    k = ease_out((f - BURST) / 12)
    R = R_HOLD + (R_OUT - 2 - R_HOLD) * k
    life = 1 - (f - BURST) / 14
    d = np.hypot(X - CX, (Y - CY) / FLAT)
    e = np.abs(d - R)
    wdt = 2.6 - 1.4 * k
    on = e < wdt
    b = (np.sin(np.arctan2(Y - CY, X - CX) * 11 + f) + 1) / 2
    on &= b > (1 - life) * 1.1 - 0.1
    inner = d < R
    m[on] = WIND[1]
    m[on & inner & (e < wdt * 0.6)] = WIND[2]
    m[on & inner & (e < wdt * 0.3) & (life > 0.55)] = WIND[3]
    m[on & ~inner & (e > wdt * 0.6)] = WIND[0]
    L += np.where(e < 3, (1 - e / 3) ** 2 * 0.32 * life, 0.0)      # core along the ring
    L += np.where(e < 8, (1 - e / 8) ** 2 * 0.13 * life, 0.0)      # pool


def flash(m, L, f):
    if f not in PEAK:
        return
    k = 1.0 if f == PEAK[0] else 0.6
    d = np.hypot(X - CX, (Y - CY) / FLAT)
    R = 13 if f == PEAK[0] else 18
    m[d < R] = WIND[2]
    m[d < R - 3] = WIND[3] if f == PEAK[0] else WIND[2]
    m[(d >= R) & (d < R + 1.5)] = WIND[1]
    light.glow(L, C, CX, CY - 4, 24, 0.75 * k)


def dust(m, f):
    # gather: small puffs pulled in along the ground
    if f < BURST:
        for i in range(6):
            t = f / BURST
            th = math.tau * i / 6 + 2.4 * t * t + hsh(i, 9)
            r = 40 - 24 * ease_in(t) + 3 * hsh(i, 8)
            x, y = gp(r, th)
            rad = 2.2 + 2.6 * t
            puff(m, X, Y, x, y, rad, DUST, brk=0.4, seed=i, ph=f * 0.3)
        return
    # burst: a dust wave just behind the ring, breaking up and drifting out
    k = ease_out((f - BURST) / BURST_N)
    t = (f - BURST) / (FRAMES - 1 - BURST)
    for i in range(ND):
        th = math.tau * (i + hsh(i, 10) * 0.6) / ND
        r = R_HOLD + (R_OUT - 10 - 12 * hsh(i, 14) - R_HOLD) * k + 5 * t * hsh(i, 11)
        x, y = gp(r, th, 1.5 + 5 * t * hsh(i, 12))
        rad = 2.4 + 5.0 * k * (0.5 + 0.8 * hsh(i, 13)) - 1.5 * ease_in(t)
        brk = min(0.95, 0.35 + 0.9 * ease_in(t))
        if rad > 0.8:
            puff(m, X, Y, x, y, rad, DUST, brk=brk, seed=i * 3, ph=f * 0.2)


def leaves(m, f):
    for i in range(NL):
        ph = math.tau * i / NL + hsh(i, 20)
        dl = 4 * hsh(i, 21)
        if f < HOLD:
            if f < dl:
                continue
            t = (f - dl) / (GATHER_N - dl)
            r = 48 - 30 * ease_in(t)
            th = ph + 3.2 * t * t
            z = 4 + 14 * t * hsh(i, 22) + 4 * t
        elif f < BURST:
            r = 18 - 2 * (f - HOLD) / HOLD_N
            th = ph + 3.2 + 0.5 * (f - HOLD + 1)
            z = 8 + 10 * hsh(i, 22)
        else:
            k = ease_out((f - BURST) / 12)
            t = (f - BURST) / (FRAMES - 1 - BURST)
            r = 16 + (50 - 6 * hsh(i, 23) - 16) * k + 2 * t
            th = ph + 3.2 + 0.5 * (HOLD_N + 1) + 0.5 * k + 0.15 * t
            z = (8 + 10 * hsh(i, 22)) * (1 - ease_out(t * 1.3)) + 1
        x, y = gp(r, th, z)
        ang = th + math.pi / 2 + f * (0.45 + 0.3 * hsh(i, 24))
        roll = abs(math.cos(f * 0.35 + i))
        leaf(m, X, Y, x, y, ang, 6.5, 3.6, LEAF, roll=roll, bend=0.25)


def scene_light(L, f):
    if f < BURST:
        k = 0.04 + 0.12 * ease_in(f / BURST)
    elif f in PEAK:
        k = 0.4
    else:
        k = 0.12 * (1 - ease_in((f - BURST) / (FRAMES - BURST)))
    d = np.hypot(X - CX, (Y - CY) / 0.8) / 56
    L += np.where(d < 1, (1 - np.minimum(d, 1)) ** 2 * k, 0.0)
    if f >= HOLD:                                    # glints thrown with the gust
        for i in range(10):
            ff = f - HOLD - 3 * hsh(i, 30)
            if ff < 0 or ff > 18:
                continue
            k2 = ease_out(min(1, (f - HOLD) / 10))
            th = math.tau * hsh(i, 31) + 0.08 * f
            r = 14 + 34 * ease_out((f - BURST) / 14) if f >= BURST else 14
            x, y = gp(r + 4 * hsh(i, 32), th, 6 * hsh(i, 33))
            tw = math.sin(ff * 0.9) ** 2
            light.glow(L, C, x, y, 3.5, 0.5 * tw * k2)
            light.glow(L, C, x, y, 8, 0.12 * tw * k2)


def frame(f):
    m = np.full((H, W), -1, np.int16)
    L = np.zeros((H, W))
    dust(m, f)
    for i in range(NS):
        streak(m, L, i, f)
    leaves(m, f)
    shock_ring(m, L, f)
    flash(m, L, f)
    scene_light(L, f)
    col = pfx.paint(m, PAL)
    return col, L


def main():
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    cols, lights, finals, covers, means = [], [], [], [], []
    fail = []
    for f in range(FRAMES):
        col, L = frame(f)
        lt = pfx.tint(np.repeat(np.clip(L, 0, 1)[..., None], 3, -1), LIGHT_RAMP)
        cols.append(col)
        lights.append(lt)
        finals.append(pfx.composite(col, lt))
        a = col[..., 3] > 0
        if not a.any():
            fail.append(f"frame {f}: empty colour")
            continue
        edge = a | (L > 0.02)
        if edge[0].any() or edge[-1].any() or edge[:, 0].any() or edge[:, -1].any():
            fail.append(f"frame {f}: touches the cell edge")
        ys, xs = np.nonzero(a)
        box = np.clip(L[ys.min():ys.max() + 1, xs.min():xs.max() + 1], 0, 1)
        covers.append((box > 0.03).mean())
        means.append(box[box > 0.03].mean() if (box > 0.03).any() else 0.0)

    pfx.strip(finals, out / f"{NAME}.png")
    pfx.strip([np.concatenate([c[..., :3], c[..., 3:]], -1) for c in cols], out / f"{NAME}_color.png")
    lt8 = [np.concatenate([(l * 255).round().astype(np.uint8),
                           np.full((H, W, 1), 255, np.uint8)], -1) for l in lights]
    pfx.strip(lt8, out / f"{NAME}_light.png")
    from PIL import Image
    for bg, tag in (("#101018", "dark"), ("#5a6a5a", "mid")):
        fr = [pfx.composite(c, l, bg) for c, l in zip(cols, lights)]
        big = np.concatenate(fr, axis=1)
        Image.fromarray(big).resize((big.shape[1] * 4, big.shape[0] * 4), Image.NEAREST).save(
            out / f"{NAME}_{tag}_4x.png")
    pfx.gif(finals, out / f"{NAME}.gif", FPS, scale=4)
    meta = {"name": NAME, "w": W, "h": H, "frames": FRAMES, "fps": FPS, "pivot": [64, 64], "loop": False,
            "glow": "medium", "light_gain": 1.0, "states": STATES,
            "sheets": {"final": f"{NAME}.png", "color": f"{NAME}_color.png", "light": f"{NAME}_light.png"}}
    (out / f"{NAME}.json").write_text(json.dumps(meta, indent=2))

    print(f"light cover {np.median(covers) * 100:.0f} %  mean {np.median(means):.3f}  (medium: 50-80 %, 0.08-0.12)")
    if fail:
        print("\n".join(fail))
        sys.exit(1)
    print(f"ok: {FRAMES} frames, out/{NAME}.png")


if __name__ == "__main__":
    main()
