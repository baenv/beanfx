"""Thunder aura around the body, redrawn to the pixelfx bar: a 3/4 top-down loop, 192x192, 60 frames at 30 fps
(2 s), yellow-white lightning. Arcs are 1 px white cores with 1 px of tinted edge; the light carries the
brightness. Two big strikes per half loop climb from a crackling ground ring: a 2 frame flash, one dark frame, a
dimmer re-strike along the same channel (dart leaders follow the old channel 40 to 80 ms later), then embers.
Short arcs crawl and flicker over an egg-shaped shell, re-jagged every other frame. Sparks fly off each strike
with speed, gravity and drag, stretched along their motion.

Light stays smooth: every hot part gets a wide low-k pool and a tight core, plus a pool round the body that swells
on each flash. Two colour layers, back (behind the body) and front (over it), split per segment by the shell depth,
plus one additive light layer. The preview puts a grey placeholder body between them; the sheets carry no body.

v3: the glow level (subtle, medium, strong) is the first argument; each writes out/<level>/.
"""
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "kit"))
import pfx  # noqa: E402
from fxlib import stroke  # noqa: E402
from light import glow, glow_line, glow_ring  # noqa: E402

NAME = "aura_thunder_v3"
# glow level from the brief: (core k, pool k, pool radius) multipliers; pick with argv, default medium
GLOWS = {"subtle": (0.9, 1.0, 0.8), "medium": (1.3, 2.6, 1.0), "strong": (1.35, 4.0, 1.1)}
GLOW = sys.argv[1] if len(sys.argv) > 1 else "medium"
CORE, POOL, SPREAD = GLOWS[GLOW]
OUT = Path(__file__).resolve().parent / "out" / GLOW
W = H = 192
PX, PY = 96, 152  # pivot: between the feet, raised so the ground light clears the bottom edge
FRAMES, FPS = 60, 30
T = FRAMES / FPS  # loop length in seconds
TAU = math.tau

PAL = ["#5a2008", "#c45410", "#ffb020", "#fff27a", "#ffffff"]  # rim, orange, amber, pale, white-hot
LIGHT = ["#7a3008", "#ffa020", "#ffe890", "#ffffff"]  # light ramp, weak to strong
SHELL_H = 98  # shell height above the feet
RING_RX, RING_RY = 42, 19

# band tables: (distance past the half width, shade), first match wins; thin by design
FLASH = [(0.0, 4), (0.9, 3), (1.6, 1)]
RESTRIKE = [(0.0, 4), (0.8, 2)]
CRAWL = [(0.0, 3), (0.8, 1)]
EMBER = [(0.0, 2), (0.7, 0)]

ys, xs = np.mgrid[0:H, 0:W].astype(float)
GX, GY = xs + 0.5, ys + 0.5
C = SimpleNamespace(x=GX, y=GY)


def rng(*k):
    return np.random.default_rng([abs(int(v)) for v in k])


def radius(u):
    """Shell radius at height fraction u: widest at the feet, hugging the shoulders, closing over the head."""
    u = min(max(u, 0.0), 1.0)
    return 24 + 18 * (1 - u) ** 2 - 11 * u ** 4


def shell(a, h):
    """Screen point and depth of shell angle a at height h px; depth > 0 is in front of the body."""
    r = radius(h / SHELL_H)
    return PX + r * math.cos(a), PY - h + r * 0.45 * math.sin(a), math.sin(a)


def jag(base, amp, seed, passes=2):
    """Base polyline (x, y, depth) broken by midpoint displacement, so kinks come at uneven spacing and angle."""
    g = rng(seed, 7)
    pts = list(base)
    for _ in range(passes):
        out = [pts[0]]
        for (x0, y0, d0), (x1, y1, d1) in zip(pts, pts[1:]):
            dx, dy = x1 - x0, y1 - y0
            ln = math.hypot(dx, dy) or 1.0
            o = float(np.clip(g.normal(0, 0.7), -1.4, 1.4)) * amp * ln
            out.append(((x0 + x1) / 2 - dy / ln * o, (y0 + y1) / 2 + dx / ln * o, (d0 + d1) / 2))
            out.append((x1, y1, d1))
        pts = out
    return pts


def path_glow(L, pts, r, k, back=0.6):
    """Light along a path, the segments joined by max so the kinks do not pile up; the back side is fainter."""
    if k <= 0.004:
        return
    P = np.zeros_like(L)
    for p, q in zip(pts, pts[1:]):
        s = np.zeros_like(L)
        f = 1.0 if p[2] > 0 else back
        glow_line(s, C, p[:2], q[:2], r, k * f)
        np.maximum(P, s, out=P)
    L += P


def lit_path(L, pts, r, k):
    """The pixelfx pair: a tight hot core and a wide soft pool along the same path."""
    path_glow(L, pts, r, k * CORE)
    path_glow(L, pts, r * 2.6 * SPREAD, k * 0.22 * min(POOL, 2.0))  # past 2x it buries the line in white


def paint_run(m, pts, w0, w1, table):
    """Tapered stroke of pts into shade map m, banded by table, keeping the brighter shade."""
    p = np.asarray([(x, y) for x, y, _ in pts], float)
    pad = table[-1][0] + max(w0, w1) + 2
    x0, y0 = int(max(0, p[:, 0].min() - pad)), int(max(0, p[:, 1].min() - pad))
    x1, y1 = int(min(W, p[:, 0].max() + pad + 1)), int(min(H, p[:, 1].max() + pad + 1))
    if x1 <= x0 or y1 <= y0:
        return
    d, _, _ = stroke(GX[y0:y1, x0:x1], GY[y0:y1, x0:x1], p, w0, w1)
    sub = np.full(d.shape, -1, np.int8)
    for lim, s in reversed(table):
        sub[d < lim] = s
    m[y0:y1, x0:x1] = np.maximum(m[y0:y1, x0:x1], sub)


def paint_path(layers, pts, w0, w1, table, back_drop=1):
    """Split a path into runs by depth sign and paint each into the front or back map; the back side loses
    back_drop shades so it reads as further away."""
    n = len(pts) - 1
    i = 0
    while i < n:
        front = (pts[i][2] + pts[i + 1][2]) / 2 > 0
        j = i + 1
        while j < n and ((pts[j][2] + pts[j + 1][2]) / 2 > 0) == front:
            j += 1
        t0, t1 = i / n, j / n
        tb = table if front else [(lim - 0.3, max(0, s - back_drop)) for lim, s in table]
        paint_run(layers["front" if front else "back"], pts[i:j + 1], w0 + (w1 - w0) * t0, w0 + (w1 - w0) * t1, tb)
        i = j


def strike_base(seed):
    """A strike: from the ground ring up and round the shell to near the crown."""
    g = rng(seed, 1)
    a0 = g.uniform(0, TAU)
    turn = g.choice([-1, 1]) * g.uniform(0.7, 1.3)
    top = g.uniform(0.82, 0.96) * SHELL_H
    n = 9
    pts = [shell(a0 + turn * k / n, top * (k / n) ** 0.9) for k in range(n + 1)]
    pts[0] = (PX + RING_RX * math.cos(a0), PY + RING_RY * math.sin(a0), pts[0][2])
    return pts


def branches(main, seed, count, grow=1.0):
    """Short side forks off the main path, heading out and up, each with its own small kinks."""
    g = rng(seed, 3)
    out = []
    for k in g.choice(np.arange(3, len(main) - 3), size=count, replace=False):
        x, y, d = main[k]
        side = 1 if x > PX else -1
        ln = g.uniform(10, 20) * grow
        ang = -math.pi / 2 + side * g.uniform(0.5, 1.1)
        p1 = (x + math.cos(ang) * ln * 0.5, y + math.sin(ang) * ln * 0.5, d)
        p2 = (x + math.cos(ang - side * 0.4) * ln, y + math.sin(ang - side * 0.4) * ln, d)
        out.append(jag([main[k], p1, p2], 0.35, seed * 7 + int(k), passes=1))
    return out


def crawl_base(seed, rise):
    """A crawling arc: a short span across the shell at some height, rising rise px."""
    g = rng(seed, 2)
    a0 = g.uniform(0, TAU)
    span = g.choice([-1, 1]) * g.uniform(0.5, 1.1)
    h0 = g.uniform(8, SHELL_H * 0.8) + rise
    dh = g.uniform(-6, 18)
    return [shell(a0 + span * k / 5, min(h0 + dh * k / 5, SHELL_H)) for k in range(6)]


# strikes: (start s, seed, big); crawls: (start s, seed, life s); all wrap round the loop
STRIKES = [(0.00, 11, True), (0.03, 12, False), (0.50, 31, False), (1.00, 21, True), (1.04, 22, False),
           (1.53, 41, False)]
_g = rng(900)
CRAWLS = [((k + _g.uniform(0, 0.8)) * T / 44, 100 + k, _g.uniform(0.1, 0.22)) for k in range(44)]
SPARKS = 9
GRAVITY, DRAG = 160.0, 2.2  # px/s^2, 1/s


def age(t, s):
    return (t - s) % T


def spark_state(seed, i, a, v0):
    """Position offset and velocity of spark i, a seconds after launch: drag slows it, gravity pulls it down."""
    g = rng(seed, 5, i)
    sp = g.uniform(30, 75)
    ang = -math.pi / 2 + g.uniform(-1.4, 1.4)
    vx, vy = math.cos(ang) * sp, math.sin(ang) * sp
    e = math.exp(-DRAG * a)
    dx = vx * (1 - e) / DRAG
    dy = vy * (1 - e) / DRAG + GRAVITY * (a / DRAG - (1 - e) / DRAG ** 2)
    return dx, dy, vx * e, vy * e + GRAVITY * (1 - e) / DRAG, g.uniform(0.35, 0.6), g.integers(1, len(v0) - 1)


def draw(f):
    t = f / FPS
    lay = {"back": np.full((H, W), -1, np.int8), "front": np.full((H, W), -1, np.int8)}
    L = np.zeros((H, W))

    # how hard the scene is lit right now: 1 on a big flash, falling off over 0.25 s
    flash = 0.0
    for s, _, big in STRIKES:
        a = age(t, s)
        flash = max(flash, (1.0 if big else 0.6) * math.exp(-a / 0.08) * (a < 0.4))

    # ground ring: a thin broken jagged ellipse that turns; whole and hot on a flash
    g = rng(500 + f // 2)
    n = 48
    ring = []
    for k in range(n + 1):
        a = TAU * k / n
        r = 1 + g.uniform(-0.05, 0.05)
        ring.append((PX + RING_RX * r * math.cos(a), PY + RING_RY * r * math.sin(a), math.sin(a)))
    turn = TAU * t / T
    for k in range(n):
        a = TAU * (k + 0.5) / n
        on = math.sin(3 * (a - turn)) + 0.6 * math.sin(5 * a + 2 * turn)
        if on < 0.5 - 2.2 * flash:
            continue
        paint_path(lay, ring[k:k + 2], 0.6, 0.6, FLASH if flash > 0.5 else CRAWL)
    glow_ring(L, C, PX, PY, RING_RX, 5, (0.1 + 0.3 * flash) * CORE, flat=RING_RY / RING_RX)
    glow_ring(L, C, PX, PY, RING_RX, 16 * SPREAD, (0.05 + 0.08 * flash) * POOL, flat=RING_RY / RING_RX)

    for s, seed, big in STRIKES:
        a = age(t, s)
        fr = int(a * FPS + 1e-6)  # whole frames since the strike
        if fr > 14:
            continue
        base = strike_base(seed)
        main = jag(base, 0.7, seed * 10)
        k0 = 1.0 if big else 0.7
        if fr <= 1:  # the flash: the full channel and its forks
            paint_path(lay, main, 0.9 if big else 0.7, 0.4, FLASH)
            for b in branches(main, seed, 3 if big else 2):
                paint_path(lay, b, 0.6, 0.3, CRAWL)
                lit_path(L, b, 5, 0.2 * k0)
            lit_path(L, main, 9, 0.55 * k0)
            x, y, _ = main[0]
            glow(L, C, x, y, 10, 0.6 * k0 * CORE)
            glow_ring(L, C, x, y, 0, 30 * SPREAD, 0.12 * k0 * POOL, flat=0.3)  # the landing pool lies flat on the ground
        elif fr == 2:  # the dark gap between the return stroke and the dart leader: a faint afterglow only
            path_glow(L, main, 14, 0.06 * k0 * POOL)
        elif fr <= 4:  # the re-strike: the same channel, nudged, dimmer, no forks
            re = [(x + rng(seed, 9).uniform(-1, 1), y, d) for x, y, d in main]
            paint_path(lay, re, 0.6, 0.3, RESTRIKE)
            lit_path(L, re, 7, 0.32 * k0)
        else:  # embers: pieces of the channel left glowing, thinning out
            fade = 1 - (fr - 5) / 10
            for k in range(0, len(main) - 1, 2 + (fr - 5) // 3):
                if rng(seed, 11, k).uniform() < fade:
                    paint_path(lay, main[k:k + 2], 0.5, 0.5, EMBER, back_drop=0)
            path_glow(L, main, 6, 0.1 * fade * k0 * CORE)

        if big:  # sparks thrown off the strike
            for i in range(SPARKS):
                dx, dy, vx, vy, life, idx = spark_state(seed, i, a, main)
                if a > life:
                    continue
                x0, y0, d = main[idx]
                x, y = x0 + dx, y0 + dy
                sp = math.hypot(vx, vy)
                tail = min(6.0, sp / FPS * 1.2)
                u = (vx / (sp or 1), vy / (sp or 1))
                hot = 1 - a / life
                pts = [(x, y, d), (x - u[0] * tail, y - u[1] * tail, d)]
                paint_path(lay, pts, 0.5, 0.3, [(0.0, 4 if hot > 0.5 else 3)], back_drop=1)
                glow(L, C, x, y, 5, 0.3 * hot * CORE)
                glow(L, C, x, y, 12 * SPREAD, 0.05 * hot * POOL)

    for s, seed, life in CRAWLS:
        a = age(t, s)
        if a > life:
            continue
        hot = 1 - a / life
        path = jag(crawl_base(seed, rise=30 * a), 0.6, seed * 10 + f // 2)
        paint_path(lay, path, 0.6, 0.3, CRAWL if hot > 0.4 else EMBER)
        lit_path(L, path, 5, 0.22 * hot)

    # the pool round the body: always faintly lit, swelling on each flash
    glow(L, C, PX, PY - 44, 72, (0.05 + 0.12 * flash) * POOL)
    return lay, L


def light_rgb(L):
    """Summed light kept smooth: weak light takes the deep hue, strong light goes white."""
    return pfx.tint(np.repeat(np.clip(L, 0, 1)[..., None], 3, -1), LIGHT)


def body_mask():
    """A grey placeholder body for the preview only: legs, torso, head, 80 px tall."""
    torso = (np.abs(GX - PX) / 13) ** 2 + ((GY - (PY - 46)) / 22) ** 2 < 1
    legs = (np.abs(np.abs(GX - PX) - 6) < 4.5) & (GY > PY - 32) & (GY < PY - 1)
    head = np.hypot(GX - PX, GY - (PY - 74)) < 9
    return torso | legs | head


def over(dst, src):
    a = src[..., 3:4] / 255.0
    out = dst.copy()
    out[..., :3] = (dst[..., :3] * (1 - a) + src[..., :3] * a).round().astype(np.uint8)
    out[..., 3] = np.maximum(dst[..., 3], src[..., 3])
    return out


def scale(img, k):
    return img.repeat(k, 0).repeat(k, 1)


def main():
    from PIL import Image
    OUT.mkdir(parents=True, exist_ok=True)
    backs, fronts, lights, colors, finals, previews, sums = [], [], [], [], [], [], []
    body = np.zeros((H, W, 4), np.uint8)
    bm = body_mask()
    body[bm] = (70, 74, 86, 255)
    edge_bm = bm & ~np.roll(bm, 1, 0) | bm & ~np.roll(bm, 1, 1)
    body[edge_bm] = (40, 42, 52, 255)
    for f in range(FRAMES):
        lay, L = draw(f)
        b, fr = pfx.paint(lay["back"], PAL), pfx.paint(lay["front"], PAL)
        rgb = light_rgb(L)
        backs.append(b)
        fronts.append(fr)
        lights.append(pfx.composite(np.zeros((H, W, 4), np.uint8), rgb))
        col = over(b, fr)
        colors.append(col)
        finals.append(pfx.composite(col, rgb))
        previews.append((over(over(b, body), fr), rgb))
        sums.append(L)

    pfx.strip(backs, OUT / f"{NAME}_back.png")
    pfx.strip(fronts, OUT / f"{NAME}_front.png")
    pfx.strip(lights, OUT / f"{NAME}_light.png")
    pfx.strip(finals, OUT / f"{NAME}.png")
    meta = {"name": NAME, "w": W, "h": H, "frames": FRAMES, "fps": FPS, "loop": True, "pivot": [PX, PY],
            "layers": {"back": f"{NAME}_back.png", "front": f"{NAME}_front.png",
                       "light": f"{NAME}_light.png (additive, smooth)", "combined": f"{NAME}.png"},
            "order": "back, body, front, light (add)", "glow": GLOW, "light_gain": 1.0, "palette": PAL, "light_ramp": LIGHT}
    (OUT / f"{NAME}.json").write_text(json.dumps(meta, indent=1) + "\n")

    for bg, tag in (("#101018", "dark"), ("#6a7468", "mid")):
        frames = [pfx.composite(c, l, bg) for c, l in previews]
        Image.fromarray(scale(np.concatenate(frames, 1), 4)).save(OUT / f"{NAME}_4x_{tag}.png")
        Image.fromarray(np.concatenate(frames, 1)).save(OUT / f"{NAME}_1x_{tag}.png")
    pfx.gif([pfx.composite(c, l, "#101018") for c, l in previews], OUT / f"{NAME}.gif", FPS)
    pfx.gif([pfx.composite(c, l, "#6a7468") for c, l in previews], OUT / f"{NAME}_mid.gif", FPS)

    bad = []
    for f in range(FRAMES):
        a = colors[f][..., 3] > 0
        lit = sums[f] > 0.02
        if not a.any():
            bad.append(f"frame {f}: empty colour")
        for m, what in ((a, "colour"), (lit, "light")):
            if m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any():
                bad.append(f"frame {f}: {what} touches the cell edge")
    # light inside the drawing's box, the measure the glow levels are set by
    cover, mean = [], []
    for col, L in zip(colors, sums):
        ys_, xs_ = np.nonzero(col[..., 3])
        box = np.clip(L[ys_.min():ys_.max() + 1, xs_.min():xs_.max() + 1], 0, 1)
        cover.append((box > 0.03).mean())
        mean.append(box[box > 0.03].mean() if (box > 0.03).any() else 0.0)
    print(f"light {GLOW}: cover {np.median(cover):.0%}, mean {np.median(mean):.2f}")
    print("\n".join(bad) or f"ok: {FRAMES} frames {W}x{H} at {FPS} fps, written to {OUT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
