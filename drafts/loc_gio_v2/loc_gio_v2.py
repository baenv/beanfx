"""Wind skill, a tornado cast for an RPG, redrawn to the pixelfx bar: 3/4 top-down, 256x128, 48 frames at 28 fps,
one-shot (1.7 s), mint to white wind. It is cast at the pivot and travels right (east); flip it for west.

Motion runs on a beat clock (14 beats a second, the timing of the first draft) so every frame is a moment in time,
not a step. Beats: 0 to 4 the dust whirl on the ground draws in at the cast spot; 4 to 5.5 the funnel shoots up with
a ring of wind blown out over the ground and a white peak; 5 to 18 it is thrown right, fast at first and slowing,
the top trailing behind the foot, dust, grit and wind streaks left in its wake; 18 to 24 it stops, the bands unwind
outward and thin, the leaves are flung off and tumble down under drag.

The wind bands are 1 px lines with a bright core and 1 px of tinted edge; the dust and the air column it carries
are translucent, lit from the top left. Light stays smooth: a tight core up the funnel axis and a wide low pool
round it, a light on each near band, a flat pool on the ground under the foot.
"""
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "kit"))
import pfx  # noqa: E402
from fxkit import fade, leaf  # noqa: E402
from fxlib import stroke  # noqa: E402
from light import glow, glow_line, glow_ring  # noqa: E402

NAME = "loc_gio_v2"
OUT = Path(__file__).resolve().parent / "out"
W, H = 256, 128
PX, PY = 48, 104  # pivot: the cast spot, the foot of the funnel on the ground
FPS = 28
BEATS = 14  # beats a second: the motion clock
DUR = 24 / BEATS  # 1.71 s
FRAMES = round(DUR * FPS)
TRAVEL = 150  # px the foot moves right between beat GO and STOP
GO, STOP = 5, 18
TAU = math.tau
TOP = 82  # funnel height at full
FLAT = 0.36  # how flat a horizontal circle lies in this 3/4 view

# wind: deep teal rim, teal, mint, pale mint, white; leaf: deep, mid, light, vein; dust: shadow, mid, light
PAL = ["#17404e", "#2a8086", "#62d0bc", "#c4f6e4", "#ffffff",
       "#24501c", "#4a9428", "#94cc44", "#d6ee8a",
       "#6e5a44", "#a88e6a", "#dcc6a0"]
LEAF = (5, 6, 7, 8)
LIGHT = ["#0c3a3a", "#3cc0a8", "#b8ffe8", "#ffffff"]  # light ramp, weak to strong

ys, xs = np.mgrid[0:H, 0:W].astype(float)
GX, GY = xs + 0.5, ys + 0.5
C = SimpleNamespace(x=GX, y=GY)


def h01(i, salt=0):
    return (math.sin(i * 12.9898 + salt * 78.233) * 43758.5453) % 1.0


def rgb(h):
    return pfx._hex(h) / 255.0


def radius(u):
    """Funnel radius at height fraction u: a narrow foot opening into a wide top."""
    return 5 + 23 * max(u, 0.0) ** 1.25


def base_x(b):
    """Where the foot stands at beat b: at the cast spot, then thrown right fast and slowing, then a slow drift."""
    if b <= GO:
        return float(PX)
    if b <= STOP:
        t = (b - GO) / (STOP - GO)
        return PX + TRAVEL * (1 - (1 - t) ** 2)
    return PX + TRAVEL + 1.5 * (b - STOP)


def speed(b):
    """Foot speed in px a beat."""
    return (base_x(b) - base_x(b - 0.25)) * 4


def sway(u, b):
    """The funnel axis bends a little and the bend travels up; moving, the top trails behind the foot."""
    return 3.0 * math.sin(u * math.pi * 1.2 - b * 0.8) * u - 0.4 * speed(b) * u


def arc_pts(cy, r, a0, span, n=14, cx=PX, climb=0.0):
    """Points (x, y, depth) along a horizontal circle of radius r round (cx, cy) seen in 3/4; climb px rises the
    arc along its span, so a band reads as a turn of a spiral and not a flat ring."""
    return [(cx + r * math.cos(a0 + span * k / n), cy - climb * k / n + r * FLAT * math.sin(a0 + span * k / n),
             math.sin(a0 + span * k / n)) for k in range(n + 1)]


# band tables: (distance past the half width, shade); a bright core and 1 px of tinted edge
FRONT = [(0.2, 3), (0.95, 2)]
FRONT_HOT = [(0.2, 4), (0.95, 3), (1.6, 2)]
BACK = [(0.2, 1)]


def _runs(m, pts, w, table, keep):
    """One band as a stroke thickest in the middle and pointed at both ends, banded by distance past its half
    width; only the segments whose depth passes keep. Its segments join by max, then it covers what lies under."""
    band = np.full(m.shape, -1, np.int8)
    n = len(pts) - 1
    pad = table[-1][0] + w + 3
    for i in range(n):
        p, q = pts[i], pts[i + 1]
        if not keep((p[2] + q[2]) / 2):
            continue
        t0, t1 = i / n, (i + 1) / n
        w0, w1 = w * math.sin(math.pi * t0) + 0.2, w * math.sin(math.pi * t1) + 0.2
        x0, x1 = int(max(0, min(p[0], q[0]) - pad)), int(min(W, max(p[0], q[0]) + pad + 1))
        y0, y1 = int(max(0, min(p[1], q[1]) - pad)), int(min(H, max(p[1], q[1]) + pad + 1))
        if x1 <= x0 or y1 <= y0:
            continue
        d, _, _ = stroke(GX[y0:y1, x0:x1], GY[y0:y1, x0:x1], [p[:2], q[:2]], w0, w1)
        seg = np.full(d.shape, -1, np.int8)
        for lim, s in reversed(table):
            seg[d < lim] = s
        np.maximum(band[y0:y1, x0:x1], seg, out=band[y0:y1, x0:x1])
    m[band >= 0] = band[band >= 0]


def draw_funnel(m, b, height, bx, widen=1.0, hot=False, n=9):
    """Stacked swirl bands round the funnel; each climbs and turns counterclockwise, shrinking to nothing as it
    wraps from the top back to the foot. Back halves first, so the near side covers the far side."""
    spin = -0.62 * b
    layers = []
    for i in range(n):
        s = ((i + 0.35 * b) % n) / n
        grow = min(1.0, s / 0.12, (1 - s) / 0.12)
        u = 0.06 + 0.94 * s
        h = height * u
        r = radius(u * height / TOP) * widen
        a0 = spin + i * 2.4 + 0.5 * h01(i, 3)
        span = (2.4 + 1.6 * h01(i, 5)) * grow
        if span < 0.4:
            continue
        cx = bx + sway(u, b)
        layers.append((arc_pts(PY - h, r, a0, -span, cx=cx, climb=(4 + 10 * u) * span / 4), 0.4 + 0.9 * u))
    for pts, w in layers:
        _runs(m, pts, w * 0.6, BACK, lambda d: d <= -0.15)
    for pts, w in layers:
        _runs(m, pts, w, FRONT_HOT if hot else FRONT, lambda d: d > -0.15)
    return layers


class Haze:
    """A translucent layer, premultiplied: blobs of colour laid over each other."""

    def __init__(self):
        self.P = np.zeros((H, W, 3))
        self.A = np.zeros((H, W))

    def lay(self, sl, alpha, color):
        a = np.clip(alpha, 0, 1)
        self.P[sl] = self.P[sl] * (1 - a[..., None]) + color * a[..., None]
        self.A[sl] = self.A[sl] * (1 - a) + a

    def rgba(self):
        a = np.clip(self.A, 0, 1)[..., None]
        c = self.P / np.maximum(a, 1e-6)
        return (np.concatenate([np.clip(c, 0, 1), a], -1) * 255).round().astype(np.uint8)


DUST_LIT, DUST_MID, DUST_SHADE = rgb("#dcc6a0"), rgb("#a88e6a"), rgb("#6e5a44")


def dust_blob(hz, cx, cy, r, a):
    """A soft dust puff lit from the top left: light at the top left, shadow at the bottom right, a soft edge."""
    if r < 0.8 or a <= 0.01:
        return
    x0, x1 = int(max(0, cx - r - 1)), int(min(W, cx + r + 2))
    y0, y1 = int(max(0, cy - r - 1)), int(min(H, cy + r + 2))
    if x1 <= x0 or y1 <= y0:
        return
    sl = (slice(y0, y1), slice(x0, x1))
    dx, dy = (GX[sl] - cx) / r, (GY[sl] - cy) / r
    d = np.hypot(dx, dy)
    alpha = a * np.clip(1 - d, 0, 1) ** 0.6
    t = np.clip(0.5 + 0.55 * (dx + dy), 0, 1)[..., None]
    color = np.where(t < 0.5, DUST_LIT + (DUST_MID - DUST_LIT) * t * 2, DUST_MID + (DUST_SHADE - DUST_MID) * (t * 2 - 1))
    hz.lay(sl, alpha, color)


AIR_LO, AIR_HI = rgb("#62d0bc"), rgb("#e4fff6")


def air_column(hz, height, b, bx, k=1.0):
    """The dust and air the funnel carries: a translucent column, densest at the axis and the foot, thinning up
    into the top, streaked by bands of flow that climb with the bands."""
    u = np.clip((PY - GY) / max(height, 1), 0, 1)
    cx = bx + np.array([sway(v, b) for v in u[:, 0]])[:, None]
    r = 5 + 23 * u ** 1.25
    q = np.abs(GX - cx) / (r * 0.62)
    inside = (GY <= PY) & (GY >= PY - height) & (q < 1)
    flow = 0.7 + 0.3 * np.sin((PY - GY) * 0.45 + b * 2.2 + (GX - cx) * 0.25)
    alpha = np.where(inside, 0.5 * k * (1 - q * q) * (1 - u) ** 0.6 * flow, 0)
    color = AIR_LO + (AIR_HI - AIR_LO) * np.clip(1 - q, 0, 1)[..., None]
    hz.lay((slice(None), slice(None)), alpha, color)


def ground_swirl(m, b):
    """The dust whirl before the funnel: thin spiral strokes on the ground drawing in."""
    for j in range(4):
        r = 34 - 6 * b - 3 * j
        if r < 8:
            continue
        pts = arc_pts(PY, r, -0.9 * b + j * TAU / 4, 1.6 + 0.3 * b, n=10)
        _runs(m, pts, 0.5 + 0.1 * b, [(0.2, 2), (0.95, 1)], lambda d: True)


def dust(hz, b, strength, bx, spread=1.0, rise=0.0):
    """Dust puffs whirling round the foot, each two lobes so it reads as a cloud, not a ball."""
    for j in range(7):
        a = -0.75 * b + j * TAU / 7 + 0.4 * h01(j, 1)
        r = (14 + 6 * h01(j, 2)) * spread
        cx = bx + r * math.cos(a)
        cy = PY + r * FLAT * math.sin(a) - 2 - rise * (1 + h01(j, 4))
        rad = (4.5 + 2.5 * h01(j, 6)) * strength
        front = 0.7 + 0.3 * math.sin(a)
        dust_blob(hz, cx, cy, rad, 0.4 * front * min(1.0, strength))
        dust_blob(hz, cx + rad * 0.8, cy - rad * 0.35, rad * 0.75, 0.32 * front * min(1.0, strength))
        dust_blob(hz, cx - rad * 0.7, cy + rad * 0.1, rad * 0.6, 0.28 * front * min(1.0, strength))


def grit(m, L, b, bx):
    """Grains of grit kicked back off the moving foot, and a spray of them flung out when it stops; each one a
    1 to 2 px streak along its motion that slows under drag and falls."""
    def grain(x0, y0, vx, vy, age, life, seed):
        if age < 0 or age > life:
            return
        D, G = 0.5, 0.9  # drag per beat, gravity px per beat^2
        e = math.exp(-D * age)
        x = x0 + vx * (1 - e) / D
        y = y0 + vy * (1 - e) / D + G * (age / D - (1 - e) / D ** 2)
        if y > PY + 6:
            return
        sp = math.hypot(vx * e, vy * e + G * (1 - e) / D)
        ln = min(3.0, sp * 0.35)
        ux, uy = vx * e / (sp or 1), (vy * e + G * (1 - e) / D) / (sp or 1)
        pts = [(x, y, 1.0), (x - ux * ln, y - uy * ln, 1.0)]
        _runs(m, pts, 0.4, [(0.2, 11 if h01(seed, 3) < 0.5 else 10)], lambda d: True)

    for g in range(GO + 1, STOP + 1):  # kicked back while it travels
        for j in range(2):
            s = g * 10 + j
            grain(base_x(g) - 3, PY - 1 - 3 * h01(s, 1), -2 - 3 * h01(s, 2) - 0.3 * speed(g),
                  -3 - 3 * h01(s, 4), b - g, 2.5 + h01(s, 5), s)
    for j in range(12):  # flung out at the stop
        a = TAU * j / 12 + 0.5 * h01(j, 6)
        sp = 6 + 5 * h01(j, 7)
        grain(base_x(STOP) + 8 * math.cos(a), PY - 2 - 10 * h01(j, 8), sp * math.cos(a), -2 - 4 * h01(j, 9),
              b - STOP - 0.3 * h01(j, 10), 3.5, 900 + j)


LEAVES = 7


def ride(j, b, height, bx):
    """Leaf j riding the spiral up at beat b: position and heading."""
    t = b - (3 + (j % 4))
    u = min(0.15 + 0.11 * t + 0.08 * h01(j, 7), 0.95)
    a = -0.9 * b + j * TAU / LEAVES
    r = radius(u * height / TOP) + 4
    return bx + sway(u, b) + r * math.cos(a), PY - height * u + r * FLAT * math.sin(a), a


def leaves(m, b, height, bx):
    """Leaves riding the spiral up, fluttering; past the stop they fly off along the way they were going, slowed by
    drag, sinking and tumbling faster the faster they go."""
    for j in range(LEAVES):
        if b < 3 + (j % 4):
            continue
        if b <= STOP:
            cx, cy, a = ride(j, b, height, bx)
            spin = a * 1.7 + j
            roll = abs(math.cos(b * 1.3 + j))
        else:
            x0, y0, a0 = ride(j, STOP, TOP, base_x(STOP))
            x1, y1, _ = ride(j, STOP - 0.25, TOP, base_x(STOP - 0.25))
            vx, vy = (x0 - x1) * 4 * 0.8, (y0 - y1) * 4 * 0.8 - 2  # px a beat, thrown a little up
            tau, D, G = b - STOP, 0.55, 0.7
            e = math.exp(-D * tau)
            cx = x0 + vx * (1 - e) / D + 1.5 * math.sin(tau * 1.6 + j)
            cy = y0 + vy * (1 - e) / D + G * (tau / D - (1 - e) / D ** 2)
            sp = math.hypot(vx, vy) * e
            spin = a0 * 1.7 + j + tau * (0.6 + 0.12 * sp)
            roll = abs(math.cos(b * (1.3 + 0.08 * sp) + j))
        cx = min(max(cx, 8), W - 9)
        cy = min(max(cy, 8), H - 9)
        leaf(m, GX, GY, cx, cy, spin, 7 + (j % 3), 4.2, LEAF, roll=roll, bend=0.2 * math.sin(b + j))


def wake(m, hz, b):
    """What the moving funnel leaves behind: dust dropped at its past footholds that rises, swells and thins, and
    thin wind streaks trailing the foot while it is fast."""
    for g in range(GO + 1, STOP + 1):
        a = b - g
        if a < 0 or a > 6:
            continue
        x = base_x(g)
        for j, oy in enumerate((-2, 3)):
            r = 2.6 + 0.7 * a + 0.6 * h01(g, j)
            dust_blob(hz, x - 4 + 6 * h01(g, j + 4), PY + oy - 1.3 * a, r, 0.45 * (1 - a / 6))
    v = speed(b)
    if GO < b <= STOP + 1 and v > 3:
        bx = base_x(b)
        for j, (oy, k) in enumerate(((-5, 1.0), (1, 1.4), (6, 0.8))):
            x0 = bx - 10 - 4 * h01(int(b * 2), j)
            ln = min(v * 1.6 * k, x0 - 6)  # never past the cast spot's side of the cell
            pts = [(x0 - ln * t, PY + oy, 1.0) for t in (0, 0.5, 1)]
            _runs(m, pts, 0.7, [(0.2, 4 if v > 10 else 3), (0.95, 2 if v > 10 else 1)], lambda d: True)


def funnel_light(L, b, height, bx, layers, k):
    """The pixelfx pair up the axis (a tight core and a wide pool), a light on each near band, a flat ground pool."""
    top = (bx + sway(0.85, b), PY - height * 0.85)
    glow_line(L, C, (bx, PY - 2), top, 6, 0.2 * k)
    glow_line(L, C, (bx, PY - 4), top, 26, 0.1 * k)
    glow_ring(L, C, bx, PY, 0, 34, 0.08 * k, flat=FLAT)
    for pts, _ in layers:
        front = [p for p in pts if p[2] > 0.3]
        for p, q in zip(front, front[1:]):
            glow_line(L, C, p[:2], q[:2], 3, 0.05 * k)


def draw(f):
    b = f * BEATS / FPS
    m = np.full((H, W), -1, np.int8)
    hz = Haze()
    L = np.zeros((H, W))
    bx = base_x(b)
    if b < 4:  # anticipation: the dust whirl draws in, a small vortex starts
        ground_swirl(m, b)
        dust(hz, b, 0.6 + 0.12 * b, bx, spread=1.3 - 0.1 * b)
        if b >= 2:
            height = 10 + 10 * (b - 2)
            air_column(hz, height, b, bx, 0.5)
            layers = draw_funnel(m, b, height, bx, n=3)
            funnel_light(L, b, height, bx, layers, 0.5)
        glow(L, C, PX, PY - 4, 10, 0.1 + 0.05 * b)
        glow_ring(L, C, PX, PY, 0, 28, 0.03 + 0.02 * b, flat=FLAT)
    elif b <= STOP:
        height = TOP * min(1.0, 0.7 + 0.3 * (b - 4))
        peak = max(0.0, 1 - abs(b - 4.6) / 1.1)  # 1 at the white peak, 0 a beat either side
        wake(m, hz, b)
        dust(hz, b, 1.0, bx)
        air_column(hz, height, b, bx, 1.0 + 0.4 * peak)
        layers = draw_funnel(m, b, height, bx, hot=peak > 0.3)
        grit(m, L, b, bx)
        leaves(m, b, height, bx)
        if b < 7:  # the ring blown out over the ground at the cast spot
            s = (b - 4) / 3
            R = 24 + 18 * (1 - (1 - s) ** 2)
            pts = arc_pts(PY, R, 0, TAU, n=48)
            core = 4 if s < 0.25 else 3 if s < 0.55 else 2
            _runs(m, pts, 0.6, [(0.2, core), (0.95, core - 1)], lambda d: True)
            glow_ring(L, C, PX, PY, R, 4, 0.35 * (1 - s), flat=FLAT)
            glow_ring(L, C, PX, PY, R, 12, 0.08 * (1 - s), flat=FLAT)
        funnel_light(L, b, height, bx, layers, 1.0 + 1.2 * peak)
        if peak > 0:  # the white peak: a flash up the middle of the funnel
            glow(L, C, bx + sway(0.4, b), PY - height * 0.4, 12, 0.5 * peak)
    else:  # dissolve: the bands unwind outward and thin, the column clears
        k = b - STOP
        fun = np.full((H, W), -1, np.int8)
        wake(m, hz, b)
        air_column(hz, TOP * (1 - 0.06 * k), b, bx, max(0.0, 1 - 0.3 * k))
        layers = draw_funnel(fun, b, TOP * (1 - 0.06 * k), bx, widen=1 + 0.1 * k, n=max(3, 9 - int(k)))
        dust(hz, b, max(0.2, 1 - 0.15 * k), bx, spread=1 + 0.15 * k, rise=k)
        m[fun >= 0] = fun[fun >= 0]
        m[:] = fade(m, 0.13 * k)
        grit(m, L, b, bx)
        leaves(m, b, TOP, bx)
        funnel_light(L, b, TOP * (1 - 0.06 * k), bx, layers, max(0.0, 1 - k / 5))
    return m, hz, L


def light_rgb(L):
    """Summed light kept smooth: weak light takes the deep hue, strong light goes white."""
    return pfx.tint(np.repeat(np.clip(L, 0, 1)[..., None], 3, -1), LIGHT)


def over(dst, src):
    a = src[..., 3:4] / 255.0
    out = dst.copy()
    out[..., :3] = (dst[..., :3] * (1 - a) + src[..., :3] * a).round().astype(np.uint8)
    out[..., 3] = np.maximum(dst[..., 3], src[..., 3])
    return out


def scale(img, k):
    return img.repeat(k, 0).repeat(k, 1)


def frame_of(beat):
    return round(beat * FPS / BEATS)


def main():
    from PIL import Image
    OUT.mkdir(parents=True, exist_ok=True)
    colors, lights, finals, rgbs, sums = [], [], [], [], []
    for f in range(FRAMES):
        m, hz, L = draw(f)
        c = over(hz.rgba(), pfx.paint(m, PAL))
        rgbs.append(light_rgb(L))
        sums.append(L)
        colors.append(c)
        lights.append(pfx.composite(np.zeros((H, W, 4), np.uint8), rgbs[-1]))
        finals.append(pfx.composite(c, rgbs[-1]))

    pfx.strip(colors, OUT / f"{NAME}_color.png")
    pfx.strip(lights, OUT / f"{NAME}_light.png")
    pfx.strip(finals, OUT / f"{NAME}.png")
    meta = {"name": NAME, "w": W, "h": H, "frames": FRAMES, "fps": FPS, "loop": False, "pivot": [PX, PY],
            "peak": [frame_of(4), frame_of(5.5)],
            "travel": {"dx": TRAVEL, "from_frame": frame_of(GO), "to_frame": frame_of(STOP), "heading": "east"},
            "layers": {"color": f"{NAME}_color.png", "light": f"{NAME}_light.png (additive, smooth)",
                       "combined": f"{NAME}.png"}, "palette": PAL, "light_ramp": LIGHT}
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
        for msk, what in ((a, "colour"), (lit, "light")):
            if msk[0].any() or msk[-1].any() or msk[:, 0].any() or msk[:, -1].any():
                bad.append(f"frame {f}: {what} touches the cell edge")
    print("\n".join(bad) or f"ok: {FRAMES} frames {W}x{H} at {FPS} fps, written to {OUT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
