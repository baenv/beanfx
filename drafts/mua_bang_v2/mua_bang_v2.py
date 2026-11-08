"""Ice and snow rain, a lasting AoE zone, redrawn to the pixelfx bar: 3/4 top-down, 160x160, 42 frames at 30 fps,
seamless loop (1.4 s), ice blue to white.

A cold cloud of translucent puffs, lit on top and dark underneath, hangs over a frosted ground ellipse. Ice shards
(faceted kites with a 1 px rim and a white ridge) fall fast on a slant from the wind with a faint streak, stick in
the ground for a moment with a flash, then shatter: small fragments fly out under gravity and bounce once, and a puff
of mist swells and thins. Snow falls slower in two layers: far flakes 1 px, faint and slow, near flakes a cross and
twice as fast, so the zone has depth. The frost is a thin translucent ice sheet with hoarfrost feathers and a
crystal rim; glints flash on it.

Light stays smooth: every hot part (shard tips, impacts, fragments, glints) gets a tight core and a wide low-k pool,
and the frost carries a faint cold pool. Every motion is a whole number of cycles over the loop, so the last frame
runs into the first.
"""
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "kit"))
import pfx  # noqa: E402
from fxkit import kite, lumpy, twinkle  # noqa: E402
from fxlib import line, noise, outline  # noqa: E402
from light import glow, glow_line, glow_ring  # noqa: E402

NAME = "mua_bang_v2"
OUT = Path(__file__).resolve().parent / "out"
W = H = 160
PX, PY = 80, 118  # pivot: the centre of the zone on the ground
FRAMES, FPS = 42, 30
T = FRAMES / FPS  # 1.4 s
TAU = math.tau
RX, RY = 56, 22  # the ground ellipse
CLOUD_Y = 46  # the cloud base, where ice and snow come out
SLANT = 0.28  # wind from the left: px right per px down

# ice: deep indigo rim, blue, light blue, pale, white
PAL = ["#1a2658", "#3d66ae", "#7cb6e8", "#c6ecff", "#ffffff"]
CLOUD = ["#232a44", "#3a4766", "#5d6f92", "#8c9fc0"]  # underside to lit top
LIGHT = ["#1a3a80", "#5aa0ff", "#bfe4ff", "#ffffff"]  # light ramp, weak to strong

ys, xs = np.mgrid[0:H, 0:W].astype(float)
GX, GY = xs + 0.5, ys + 0.5
C = SimpleNamespace(x=GX, y=GY)


def h01(i, salt=0):
    return (math.sin(i * 12.9898 + salt * 78.233) * 43758.5453) % 1.0


def rgb(hexes):
    return np.stack([pfx._hex(c) / 255.0 for c in hexes])


ICE_RGB, CLOUD_RGB = rgb(PAL), rgb(CLOUD)


def over(buf, a, col):
    """Straight-alpha over: alpha map a (h, w) of colour col (h, w, 3) or (3,) onto buf (h, w, 4) floats."""
    a = np.clip(a, 0, 1)[..., None]
    da = buf[..., 3:4]
    oa = a + da * (1 - a)
    buf[..., :3] = np.where(oa > 0, (col * a + buf[..., :3] * da * (1 - a)) / np.maximum(oa, 1e-6), 0)
    buf[..., 3:4] = oa


def over_shades(buf, m):
    """An opaque shade map of PAL indices onto buf."""
    on = m >= 0
    if on.any():
        col = ICE_RGB[np.clip(m, 0, len(PAL) - 1)]
        over(buf, on.astype(float), col)


def ground_spot(i, salt, spread=0.9):
    """A point inside the ground ellipse, spread evenly by a square root on the radius."""
    a = TAU * h01(i, salt)
    r = math.sqrt(h01(i, salt + 1)) * spread
    return PX + RX * r * math.cos(a), PY + RY * r * math.sin(a)


def frost_layer():
    """The frost, drawn once: a thin translucent ice sheet thicker in patches, hoarfrost feathers (short 1 px
    strokes, pale at the tips), and a broken rim of crystals with spikes leaning out."""
    buf = np.zeros((H, W, 4))
    d = np.hypot((GX - PX) / RX, (GY - PY) / RY)
    n = noise(GX, GY * 2.2, 7, seed=3)
    inside = d < 1
    sheet = inside * (0.16 + 0.22 * np.clip((n - 0.45) / 0.35, 0, 1)) * np.clip((1 - d) / 0.15, 0, 1)
    over(buf, sheet, ICE_RGB[2] * 0.9 + 0.1)

    m = np.full((H, W), -1, np.int8)
    for i in range(22):
        x, y = ground_spot(i, 60, 0.95)
        if noise(np.array([x]), np.array([y * 2.2]), 7, seed=3)[0] < 0.5:
            continue
        for j in range(2 + int(2 * h01(i, 61))):
            a = TAU * h01(i * 7 + j, 62)
            ln = 2 + 2 * h01(i * 7 + j, 63)
            x1, y1 = x + math.cos(a) * ln, y + math.sin(a) * ln * 0.5
            line(m, x, y, x1, y1, 2, keep_max=True)
            line(m, x1, y1, x1, y1, 3, keep_max=True)
    rim = (d > 0.93) & (d < 1.0) & (noise(GX, GY * 2.2, 5, seed=8) > 0.42)
    m[rim] = np.maximum(m[rim], 2)
    for k in range(28):  # spikes leaning out of the rim
        a = TAU * (k + 0.5 * h01(k, 70)) / 28
        x0, y0 = PX + RX * 0.97 * math.cos(a), PY + RY * 0.97 * math.sin(a)
        ln = 2 + 3 * h01(k, 71)
        line(m, x0, y0, x0 + math.cos(a) * ln, y0 + math.sin(a) * ln * 0.45, 3 if k % 3 == 0 else 2, keep_max=True)
    front = GY > PY  # the near half of the frost catches more light
    m[(m == 2) & front & (noise(GX, GY, 3, seed=9) > 0.7)] = 3
    over_shades(buf, m)
    return buf


FROST = frost_layer()


def cloud(buf, L, t):
    """A low cold cloud of translucent puffs in two rows, back row higher and darker; each puff lit from the top
    left in 4 tones, its edge softened over the outer quarter, the underside dark. They bob once per loop."""
    ph = TAU * t / T
    for row, (n, lift, amax, dim) in enumerate(((6, 8, 0.78, 1), (7, 0, 0.9, 0))):
        for j in range(n):
            u = ((j + 0.5 + 0.6 * (h01(j, 7 + row) - 0.5)) / n) * 2 - 1
            mid = 1 - u * u
            cx = PX + u * RX * (0.95 - 0.1 * row) + 1.5 * math.sin(ph + j + row)
            cy = CLOUD_Y - 6 - lift - 5 * mid + 5 * h01(j, 2 + row) + 1.2 * math.cos(ph + 2 * j)
            r = 4 + 8 * mid + 6 * h01(j, 3 + row)
            d = lumpy(GX, GY, cx, cy, r, 0.14, j + 10 * row, ph, 4)
            a = np.where(d < 1, np.clip((1 - d) / 0.28, 0, 1) * amax, 0.0)
            if not a.any():
                continue
            # each puff lit from above and a bit left; the mass darkens smoothly toward its base
            top = np.clip((GY - (cy - r)) / (1.5 * r), 0, 1) + 0.15 * (GX - cx) / r
            tone = np.clip(3.4 - 3.6 * top - 1.4 * np.clip((GY - (CLOUD_Y - 14)) / 10, 0, 1), 0, 3)
            k = np.clip(np.floor(tone).astype(int) - dim, 0, 3)
            over(buf, a, CLOUD_RGB[k])


SHARDS = 14
FALL, STUCK, SHATTER = 0.28, 0.07, 0.42  # seconds
GRAV = 260.0  # px/s^2 for fragments


def shards(m, frag, buf, L, t):
    """Falling shards, the flash where they land, the fragments and the mist."""
    ang = math.atan2(1, SLANT)
    ca, sa = math.cos(ang), math.sin(ang)
    for i in range(SHARDS):
        a = (t - (i * T / SHARDS + 0.15 * h01(i, 9))) % T
        lx, ly = ground_spot(i, 11)
        drop_h = ly - CLOUD_Y
        size = 0.85 + 0.35 * h01(i, 4)
        if a < FALL:  # falling, accelerating a little on the wind slant
            s = (a / FALL) ** 1.3
            y = CLOUD_Y + drop_h * s
            x = lx - SLANT * drop_h * (1 - s)
            ln = 11 * size
            kite(m, GX, GY, x, y, ang, ln, 3.6 * size, (1, 2, 3, 4), tail=0.9)
            tip = (x + ca * ln, y + sa * ln)
            tail_len = 16 * min(1.0, a / 0.06 + 0.2)
            back = (x - ca * tail_len, y - sa * tail_len)
            # a faint streak behind it, translucent, fading toward the cloud
            p = np.clip(((GX - back[0]) * ca + (GY - back[1]) * sa) / tail_len, 0, 1)
            dist = np.abs(-(GX - back[0]) * sa + (GY - back[1]) * ca)
            streak = (dist < 0.6) & (((GX - back[0]) * ca + (GY - back[1]) * sa) > 0) & (p < 1)
            over(buf, streak * 0.45 * p, ICE_RGB[3])
            glow_line(L, C, back, tip, 3, 0.12)
            glow(L, C, *tip, 4, 0.3)
            glow(L, C, *tip, 11, 0.05)
        elif a < FALL + STUCK:  # stuck in the ground, the flash
            k = (a - FALL) / STUCK
            kite(m, GX, GY, lx - ca * 3, ly - 4 * size, ang, 7 * size, 3.8 * size, (1, 2, 3, 4), tail=0.6)
            twinkle(frag, lx, ly - 1, 4 if k < 0.5 else 2, 4, 3)
            glow(L, C, lx, ly - 2, 7, 0.6 * (1 - 0.4 * k))
            glow_ring(L, C, lx, ly, 0, 20, 0.14, flat=0.45)
        elif a < FALL + STUCK + SHATTER:  # shattered: fragments under gravity, a puff of mist
            b = a - FALL - STUCK
            hot = 1 - b / SHATTER
            for j in range(5):
                th = -math.pi / 2 + (j - 2) * 0.62 + 0.3 * (h01(i, j) - 0.5)
                sp = 55 + 30 * h01(i, j + 5)
                vx, vy = math.cos(th) * sp, math.sin(th) * sp
                fx, fy = lx + vx * b, ly - 2 + vy * b + 0.5 * GRAV * b * b
                floor = ly + 1 + 3 * h01(i, j + 9)
                if fy > floor:  # one bounce, then it lies on the frost
                    tb = 2 * -vy / GRAV  # time of the first landing (roughly)
                    fy = floor - max(0.0, 0.3 * sp * math.sin(min(math.pi, (b - tb) * 9)))
                kite(frag, GX, GY, fx, fy, th + 9 * b, 4.2 - 1.0 * (j % 2) - 1.5 * b / SHATTER, 2.4, (2, 3, 4, 4), tail=0.4)
                glow(L, C, fx, fy, 3, 0.22 * hot)
                glow(L, C, fx, fy, 8, 0.04 * hot)
            mr = 3 + 9 * (b / SHATTER) ** 0.6
            md = np.hypot((GX - lx) / mr, (GY - (ly - 2 - 6 * b)) / (mr * 0.6))
            over(buf, np.where(md < 1, (1 - md * md) * 0.5 * hot, 0), ICE_RGB[3] * 0.6 + 0.4)
            glow_ring(L, C, lx, ly, 0, 16, 0.08 * hot, flat=0.45)


FAR, NEAR = 34, 14


def snow(buf, L, t, layer):
    """Far snow: 1 px faint flakes once per loop. Near snow: a cross with a white core, twice per loop."""
    n, cycles = ((FAR, 1), (NEAR, 2))[layer]
    m = np.full((H, W), -1, np.int8)
    for i in range(n):
        lx, ly = ground_spot(i, 30 + 10 * layer)
        s = (cycles * t / T + h01(i, 31 + layer)) % 1.0
        drop_h = ly - CLOUD_Y
        y = CLOUD_Y + drop_h * s
        x = lx - SLANT * 0.5 * drop_h * (1 - s) + 2.0 * math.sin(TAU * (t / T + h01(i, 33)))
        xi, yi = int(x), int(y)
        if layer == 0:
            m[yi, xi] = 3 if i % 3 else 2
        else:
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                m[yi + dy, xi + dx] = max(m[yi + dy, xi + dx], 4 if (dx, dy) == (0, 0) else 3)
            glow(L, C, x, y, 3, 0.07)
    on = m >= 0
    over(buf, on * (0.55 if layer == 0 else 1.0), ICE_RGB[np.clip(m, 0, 4)])


GLINTS = 9


def glints(m, L, t):
    """Glints on the frost: each flashes for 0.12 s once per loop, a tight core and a small pool."""
    for i in range(GLINTS):
        a = (t - i * T / GLINTS) % T
        if a > 0.12:
            continue
        k = 1 - abs(a / 0.12 - 0.4) / 0.6
        x, y = ground_spot(i, 50)
        twinkle(m, x, y, 2 if k > 0.6 else 1, 4, 3)
        glow(L, C, x, y, 4, 0.35 * k)
        glow(L, C, x, y, 10, 0.06 * k)


def draw(f):
    t = f / FPS
    L = np.zeros((H, W))
    buf = FROST.copy()
    glow_ring(L, C, PX, PY, 0, RX, 0.07, flat=RY / RX)  # the frost's faint cold pool
    g = np.full((H, W), -1, np.int8)
    glints(g, L, t)
    over_shades(buf, g)
    snow(buf, L, t, 0)
    falling = np.full((H, W), -1, np.int8)
    frag = np.full((H, W), -1, np.int8)
    shards(falling, frag, buf, L, t)
    over_shades(buf, outline(falling, 0))
    over_shades(buf, outline(frag, 0))  # a rim keeps the fragments apart from the frost
    snow(buf, L, t, 1)
    cloud(buf, L, t)
    col = (np.clip(buf, 0, 1) * 255).round().astype(np.uint8)
    col[..., 3] = np.where(buf[..., 3] < 0.02, 0, col[..., 3])
    return col, L


def light_rgb(L):
    """Summed light kept smooth: weak light takes the deep hue, strong light goes white."""
    return pfx.tint(np.repeat(np.clip(L, 0, 1)[..., None], 3, -1), LIGHT)


def scale(img, k):
    return img.repeat(k, 0).repeat(k, 1)


def main():
    from PIL import Image
    OUT.mkdir(parents=True, exist_ok=True)
    colors, rgbs, lights, finals, sums = [], [], [], [], []
    for f in range(FRAMES):
        c, L = draw(f)
        r = light_rgb(L)
        colors.append(c)
        rgbs.append(r)
        sums.append(L)
        lights.append(pfx.composite(np.zeros((H, W, 4), np.uint8), r))
        finals.append(pfx.composite(c, r))

    pfx.strip(colors, OUT / f"{NAME}_color.png")
    pfx.strip(lights, OUT / f"{NAME}_light.png")
    pfx.strip(finals, OUT / f"{NAME}.png")
    meta = {"name": NAME, "w": W, "h": H, "frames": FRAMES, "fps": FPS, "loop": True, "pivot": [PX, PY],
            "ground_ellipse": [RX, RY], "layers": {"color": f"{NAME}_color.png",
                                                   "light": f"{NAME}_light.png (additive, smooth)",
                                                   "combined": f"{NAME}.png"},
            "palette": PAL, "cloud": CLOUD, "light_ramp": LIGHT}
    (OUT / f"{NAME}.json").write_text(json.dumps(meta, indent=1) + "\n")

    for bg, tag in (("#101018", "dark"), ("#6a7468", "mid")):
        frames = [pfx.composite(c, l, bg) for c, l in zip(colors, rgbs)]
        Image.fromarray(np.concatenate(frames, 1)).save(OUT / f"{NAME}_1x_{tag}.png")
        Image.fromarray(scale(np.concatenate(frames, 1), 4)).save(OUT / f"{NAME}_4x_{tag}.png")
        pfx.gif(frames, OUT / f"{NAME}_{tag}.gif", FPS)

    bad = []
    for f in range(FRAMES):
        a = colors[f][..., 3] > 0
        lit = sums[f] > 0.02
        if not a.any():
            bad.append(f"frame {f}: empty colour")
        for m, what in ((a, "colour"), (lit, "light")):
            if m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any():
                bad.append(f"frame {f}: {what} touches the cell edge")
    print("\n".join(bad) or f"ok: {FRAMES} frames {W}x{H} at {FPS} fps, written to {OUT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
